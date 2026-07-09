"""
End-to-end tests against the packaged server binary.

These cover what the in-process unit suites cannot: PyInstaller bundling
(hidden imports, sys._MEIPASS data files, the embedded React build), real
HTTP + Socket.IO transport in threading mode, the user-data uploads
directory, and a complete multiplayer game reaching `final` with correct
scores.

See conftest.py for how the binary is spawned and configured.
"""

import io
import re
import threading
import time

import pytest
import requests
import socketio
from PIL import Image


def _jpeg_bytes(width=400, height=400, color=(72, 144, 255)):
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _create_room(server):
    resp = requests.post(f"{server.base_url}/api/rooms", timeout=10)
    assert resp.status_code == 201
    return resp.json()["room_code"]


def _upload(server, room_code, photo_bytes):
    resp = requests.post(
        f"{server.base_url}/api/rooms/{room_code}/upload",
        files={"photo": ("test.jpg", io.BytesIO(photo_bytes), "image/jpeg")},
        timeout=10,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["image_url"]


class GameClient:
    """A scriptable player: real Socket.IO connection + recorded broadcasts."""

    def __init__(self, server, name, role):
        self.server = server
        self.name = name
        self.role = role
        self.player_id = None
        self.errors = []

        self._self_evt = threading.Event()
        self._cond = threading.Condition()
        self._states = []
        self._cursor = 0

        self.sio = socketio.Client(reconnection=False)
        self.sio.on("player:self", self._on_self)
        self.sio.on("game:state", self._on_state)
        self.sio.on("error", self._on_error)

    def _on_self(self, data):
        self.player_id = data["player_id"]
        self._self_evt.set()

    def _on_state(self, data):
        with self._cond:
            self._states.append(data)
            self._cond.notify_all()

    def _on_error(self, data):
        self.errors.append(data.get("message"))

    def join(self, room_code, transport="websocket"):
        self.sio.connect(
            self.server.base_url, transports=[transport], wait_timeout=10
        )
        self.sio.emit(
            "player:join",
            {"room_code": room_code, "name": self.name, "role": self.role},
        )
        assert self._self_evt.wait(10), f"{self.name} never received player:self"
        return self

    def emit(self, event, data):
        self.sio.emit(event, data)

    def next_state(self, pred, desc, timeout=30):
        """Consume recorded game:state broadcasts (in order) until one matches."""
        deadline = time.time() + timeout
        with self._cond:
            while True:
                while self._cursor < len(self._states):
                    snap = self._states[self._cursor]
                    self._cursor += 1
                    if pred(snap):
                        return snap
                remaining = deadline - time.time()
                if remaining <= 0:
                    seen = [s.get("state") for s in self._states[-10:]]
                    raise AssertionError(
                        f"Timed out waiting for {desc}; last states seen: {seen}"
                    )
                self._cond.wait(remaining)

    def wait_state(self, state, timeout=30, **fields):
        def pred(snap):
            return snap.get("state") == state and all(
                snap.get(k) == v for k, v in fields.items()
            )

        return self.next_state(pred, f"state={state} {fields}", timeout)

    def close(self):
        try:
            self.sio.disconnect()
        except Exception:
            pass


@pytest.fixture
def clients(server):
    created = []

    def make(name, role, room_code, transport="websocket"):
        c = GameClient(server, name, role).join(room_code, transport)
        created.append(c)
        return c

    yield make
    for c in created:
        c.close()


# ---------------------------------------------------------------------------
# The bundled SPA and static assets
# ---------------------------------------------------------------------------

def test_serves_bundled_spa(server):
    resp = requests.get(server.base_url, timeout=10)
    assert resp.status_code == 200
    assert '<div id="root">' in resp.text
    assert "Photoful" in resp.text

    # The built JS bundle referenced by index.html must be inside the binary.
    match = re.search(r'src="(/assets/[^"]+\.js)"', resp.text)
    assert match, "index.html does not reference a built /assets/ bundle"
    asset = requests.get(f"{server.base_url}{match.group(1)}", timeout=10)
    assert asset.status_code == 200
    assert "javascript" in asset.headers["Content-Type"]

    # Deep links must fall back to index.html for client-side routing.
    deep = requests.get(f"{server.base_url}/room/ZZZZ/tv", timeout=10)
    assert deep.status_code == 200
    assert '<div id="root">' in deep.text


# ---------------------------------------------------------------------------
# REST room lifecycle
# ---------------------------------------------------------------------------

def test_room_rest_lifecycle(server):
    code = _create_room(server)
    assert re.fullmatch(r"[A-Z]{4}", code)

    assert requests.get(
        f"{server.base_url}/api/rooms/{code}", timeout=10
    ).json() == {"exists": True}
    assert requests.get(
        f"{server.base_url}/api/rooms/ZZZZ", timeout=10
    ).json() == {"exists": False}

    # Uploads are rejected outside the submission phase / for unknown rooms.
    files = {"photo": ("t.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")}
    in_lobby = requests.post(
        f"{server.base_url}/api/rooms/{code}/upload", files=files, timeout=10
    )
    assert in_lobby.status_code == 400
    files = {"photo": ("t.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")}
    no_room = requests.post(
        f"{server.base_url}/api/rooms/ZZZZ/upload", files=files, timeout=10
    )
    assert no_room.status_code == 404


# ---------------------------------------------------------------------------
# Socket-level guards over real transport
# ---------------------------------------------------------------------------

def test_join_unknown_room_errors(server, clients):
    code = _create_room(server)
    client = clients("Ghost", "player", code)
    client.emit(
        "player:join", {"room_code": "QQQQ", "name": "Ghost2", "role": "player"}
    )
    deadline = time.time() + 10
    while not client.errors and time.time() < deadline:
        time.sleep(0.1)
    assert any("QQQQ" in (e or "") for e in client.errors)


def test_single_host_enforced(server, clients):
    code = _create_room(server)
    clients("Host1", "host", code)
    second = clients("Host2", "player", code)
    second.emit(
        "player:join", {"room_code": code, "name": "Host2b", "role": "host"}
    )
    deadline = time.time() + 10
    while not second.errors and time.time() < deadline:
        time.sleep(0.1)
    assert any("host" in (e or "").lower() for e in second.errors)


# ---------------------------------------------------------------------------
# A complete game — the core E2E scenario
# ---------------------------------------------------------------------------

def test_full_game(server, clients):
    code = _create_room(server)

    tv = clients("TV", "tv", code)
    host = clients("Hana", "host", code)
    players = [
        host,
        clients("Pia", "player", code),
        clients("Quinn", "player", code, transport="polling"),
        clients("Rex", "player", code),
    ]
    by_id = {}

    lobby = tv.wait_state("lobby")
    assert lobby["room_code"] == code

    host.emit("host:start", {"room_code": code})

    ledger = {}          # player_id -> expected total score
    big_photo_url = None  # oversized upload, checked for server-side resize
    total_rounds = 2

    for rnd in range(1, total_rounds + 1):
        submitting = tv.wait_state("submitting", round=rnd)
        by_id = {p.player_id: p for p in players}
        prompts = submitting["prompts"]
        assert len(prompts) == 4  # ceil(4 players * 2 prompts each / 2)
        for prompt in prompts:
            assert prompt["prompt_text"]
            assert len(prompt["player_ids"]) == 2

        # Every assigned player uploads a photo and submits it.
        for prompt in prompts:
            for pid in prompt["player_ids"]:
                if big_photo_url is None:
                    photo = _jpeg_bytes(2000, 800)  # must be resized to 1280px
                    big_photo_url = url = _upload(server, code, photo)
                else:
                    url = _upload(server, code, _jpeg_bytes())
                by_id[pid].emit("submit:photo", {
                    "room_code": code,
                    "prompt_id": prompt["prompt_id"],
                    "image_url": url,
                    "caption": f"by {by_id[pid].name}",
                })
        ledger = {p.player_id: ledger.get(p.player_id, 0) for p in players}

        tv.wait_state("voting_intro", round=rnd)

        # Each matchup: both non-competing players vote for player_ids[0].
        for k in range(1, len(prompts) + 1):
            voting = tv.wait_state("voting", round=rnd, prompt_number=k)
            current = voting["current_prompt"]
            competing = current["player_ids"]
            target = competing[0]
            voters = [p for p in players if p.player_id not in competing]
            assert len(voters) == 2
            for voter in voters:
                voter.emit("submit:vote", {
                    "room_code": code,
                    "prompt_id": current["prompt_id"],
                    "voted_for_id": target,
                })

            scores = tv.wait_state("scores", round=rnd, prompt_number=k)
            deltas = scores["current_prompt"]["score_deltas"]
            assert deltas == {target: 2 * 1000 * rnd, competing[1]: 0}
            for pid, pts in deltas.items():
                ledger[pid] += pts

        if rnd < total_rounds:
            tv.wait_state("round_intro")

    # Caption round: everyone captions the featured photo, then votes.
    caption_intro = tv.wait_state("caption_intro")
    cp = caption_intro["caption_prompt"]
    assert cp["featured_image_url"]
    assert set(cp["player_ids"]) == set(by_id)

    tv.wait_state("captioning")
    for p in players:
        p.emit("submit:caption", {
            "room_code": code,
            "caption_text": f"caption by {p.name}",
        })

    caption_voting = tv.wait_state("caption_voting")
    order = caption_voting["caption_prompt"]["player_ids"]
    for p in players:
        target = next(pid for pid in order if pid != p.player_id)
        p.emit("submit:caption_vote", {
            "room_code": code,
            "voted_for_id": target,
        })
    # order[0] gets a vote from everyone else; order[0] votes for order[1].
    expected_caption_deltas = {pid: 0 for pid in order}
    expected_caption_deltas[order[0]] = 3 * 1000 * total_rounds
    expected_caption_deltas[order[1]] = 1 * 1000 * total_rounds

    caption_scores = tv.wait_state("caption_scores")
    deltas = caption_scores["caption_prompt"]["score_deltas"]
    assert deltas == expected_caption_deltas
    for pid, pts in deltas.items():
        ledger[pid] += pts

    final = tv.wait_state("final")
    final_scores = {
        p["id"]: p["score"] for p in final["players"] if p["role"] != "tv"
    }
    assert final_scores == ledger
    assert sum(final_scores.values()) > 0

    # Uploads must be on disk in the isolated user-data dir and served back.
    room_uploads = server.uploads_root / code
    jpgs = sorted(room_uploads.glob("*.jpg"))
    assert len(jpgs) == 16  # 4 prompts x 2 submitters x 2 rounds

    served = requests.get(f"{server.base_url}{big_photo_url}", timeout=10)
    assert served.status_code == 200
    assert served.headers["Content-Type"] == "image/jpeg"
    img = Image.open(io.BytesIO(served.content))
    assert img.size == (1280, 512)  # 2000x800 resized to the 1280px cap

    # Restart: back to lobby with players kept and scores zeroed.
    host.emit("host:restart", {"room_code": code})
    lobby = tv.wait_state("lobby")
    restarted = {p["id"]: p["score"] for p in lobby["players"] if p["role"] != "tv"}
    assert restarted == {pid: 0 for pid in ledger}

    for c in [tv] + players:
        assert c.errors == [], f"{c.name} received errors: {c.errors}"
