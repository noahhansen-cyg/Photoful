#!/usr/bin/env python3
"""
bots.py — Spawn bot players for local testing.

Usage:
  python bots.py                    → creates a new room with 3 bots, prints the TV URL
  python bots.py ABCD               → joins an existing room with 3 bots
  python bots.py --count 5          → creates a new room with 5 bots
  python bots.py ABCD --count 5    → joins an existing room with 5 bots

Bots (all join as regular players):
  AliceBot … HankBot — auto-submit a solid-blue JPEG for each assigned
  prompt and auto-vote in matchups they aren't competing in.
  Maximum 8 bots (room player limit).

You join as Host on your phone and start the game yourself.
Press Ctrl+C to stop.
"""

import argparse
import sys
import time
import io
import random
import threading

import requests
import socketio
from PIL import Image

BASE = "http://localhost:5000"


# ---------------------------------------------------------------------------
# Shared test image (generated once; reused for every submission)
# ---------------------------------------------------------------------------

def _make_test_photo():
    img = Image.new("RGB", (400, 400), color=(72, 144, 255))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


_TEST_PHOTO = _make_test_photo()


def _upload_photo(room_code):
    """POST the test image to the upload endpoint; return the image_url."""
    resp = requests.post(
        f"{BASE}/api/rooms/{room_code}/upload",
        files={"photo": ("bot.jpg", io.BytesIO(_TEST_PHOTO), "image/jpeg")},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["image_url"]


# ---------------------------------------------------------------------------
# Bot class
# ---------------------------------------------------------------------------

class Bot:
    def __init__(self, name, role, room_code):
        self.name      = name
        self.role      = role
        self.room_code = room_code

        self.player_id    = None
        self._submitted   = set()   # prompt_ids we have already submitted for
        self._voted       = set()   # prompt_ids we have already voted on
        self._game_over   = False

        self.sio = socketio.Client(logger=False, engineio_logger=False)
        self._register_handlers()

    # ------------------------------------------------------------------
    # Socket event handlers
    # ------------------------------------------------------------------

    def _register_handlers(self):

        @self.sio.event
        def connect():
            print(f"[{self.name}] connected — joining room {self.room_code}")
            self.sio.emit("player:join", {
                "room_code": self.room_code,
                "name":      self.name,
                "role":      self.role,
            })

        @self.sio.on("player:self")
        def on_self(data):
            self.player_id = data["player_id"]
            print(f"[{self.name}] assigned player_id={self.player_id[:8]}")

        @self.sio.on("game:state")
        def on_state(data):
            self._handle_state(data)

        @self.sio.on("error")
        def on_error(data):
            print(f"[{self.name}] server error: {data.get('message')}")

        @self.sio.event
        def disconnect():
            print(f"[{self.name}] disconnected")

    # ------------------------------------------------------------------
    # Game actions
    # ------------------------------------------------------------------

    def _handle_state(self, data):
        state  = data.get("state")
        prompt = data.get("current_prompt")

        if state == "submitting":
            for p in data.get("prompts", []):
                pid        = p["prompt_id"]
                player_ids = p.get("player_ids", [])
                submitted  = p.get("submissions", {})

                if (self.player_id in player_ids
                        and pid not in self._submitted
                        and self.player_id not in submitted):
                    self._submitted.add(pid)
                    threading.Thread(
                        target=self._do_submit, args=(pid,), daemon=True
                    ).start()

        elif state == "voting" and prompt:
            pid        = prompt["prompt_id"]
            player_ids = prompt.get("player_ids", [])
            votes      = prompt.get("votes", {})

            if (self.player_id not in player_ids
                    and self.role in ("player", "host")
                    and pid not in self._voted
                    and self.player_id not in votes):
                self._voted.add(pid)
                threading.Thread(
                    target=self._do_vote, args=(pid, player_ids), daemon=True
                ).start()

        elif state == "captioning":
            cp = data.get("caption_prompt", {}) or {}
            cp_id      = cp.get("prompt_id")
            player_ids = cp.get("player_ids", [])
            submitted  = cp.get("submissions", {})

            if (cp_id
                    and self.player_id in player_ids
                    and cp_id not in self._submitted
                    and self.player_id not in submitted):
                self._submitted.add(cp_id)
                threading.Thread(
                    target=self._do_submit_caption, daemon=True
                ).start()

        elif state == "caption_voting":
            cp = data.get("caption_prompt", {}) or {}
            cp_id      = cp.get("prompt_id")
            player_ids = cp.get("player_ids", [])
            votes      = cp.get("votes", {})

            if (cp_id
                    and self.player_id in player_ids
                    and self.role in ("player", "host")
                    and cp_id not in self._voted
                    and self.player_id not in votes):
                self._voted.add(cp_id)
                others = [pid for pid in player_ids if pid != self.player_id]
                if others:
                    threading.Thread(
                        target=self._do_caption_vote, args=(others,), daemon=True
                    ).start()

        elif state == "final" and not self._game_over:
            self._game_over = True
            self._print_results(data.get("players", []))

    def _do_submit(self, prompt_id):
        time.sleep(0.5)
        try:
            image_url = _upload_photo(self.room_code)
            self.sio.emit("submit:photo", {
                "room_code": self.room_code,
                "prompt_id": prompt_id,
                "image_url": image_url,
                "caption":   f"Photo by {self.name}",
            })
            print(f"[{self.name}] submitted photo for prompt {prompt_id[:8]}")
        except Exception as exc:
            print(f"[{self.name}] upload error: {exc}")

    def _do_submit_caption(self):
        time.sleep(0.5)
        self.sio.emit("submit:caption", {
            "room_code":    self.room_code,
            "caption_text": f"Caption by {self.name}",
        })
        print(f"[{self.name}] submitted caption for caption round")

    def _do_caption_vote(self, candidates):
        time.sleep(random.uniform(5, 10))
        voted_for = random.choice(candidates)
        self.sio.emit("submit:caption_vote", {
            "room_code":    self.room_code,
            "voted_for_id": voted_for,
        })
        print(f"[{self.name}] voted for caption by {voted_for[:8]}")

    def _do_vote(self, prompt_id, player_ids):
        time.sleep(random.uniform(5, 10))
        if not player_ids:
            return
        voted_for = player_ids[0]
        self.sio.emit("submit:vote", {
            "room_code":    self.room_code,
            "prompt_id":    prompt_id,
            "voted_for_id": voted_for,
        })
        print(f"[{self.name}] voted for {voted_for[:8]} on prompt {prompt_id[:8]}")

    def _print_results(self, players):
        print("\n=== GAME OVER ===")
        ranked = sorted(players, key=lambda p: p.get("score", 0), reverse=True)
        for rank, p in enumerate(ranked, start=1):
            marker = " 👑" if rank == 1 else ""
            print(f"  {rank}. {p['name']}: {p.get('score', 0)} pts{marker}")
        print("Bots staying connected — Ctrl+C to exit.\n")

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def connect(self, retries=10):
        for attempt in range(retries):
            try:
                self.sio.connect(BASE, transports=["polling"])
                return
            except Exception as exc:
                if attempt < retries - 1:
                    time.sleep(1)
                else:
                    print(f"[{self.name}] could not connect after {retries} attempts: {exc}")
                    raise

    def wait(self):
        self.sio.wait()

    def disconnect(self):
        try:
            self.sio.disconnect()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

BOT_NAMES = ["AliceBot", "BobBot", "CarolBot", "DaveBot", "EveBot", "FrankBot", "GraceBot", "HankBot"]
MAX_BOTS  = 8


def main():
    parser = argparse.ArgumentParser(description="Spawn bot players for local testing.")
    parser.add_argument("room_code", nargs="?", help="Existing room code to join (omit to create a new room)")
    parser.add_argument("--count", type=int, default=3, metavar="N",
                        help="Number of bots to spawn (1–8, default 3)")
    parser.add_argument("--tv-base", default="http://localhost:5173", metavar="URL",
                        help="Base URL for the printed TV link (default: Vite dev server; "
                             "use http://localhost:5000 when the packaged binary serves the frontend)")
    args = parser.parse_args()

    tv_base = args.tv_base.rstrip("/")

    count = max(1, min(args.count, MAX_BOTS))
    if count != args.count:
        print(f"Bot count clamped to {count} (allowed range: 1–{MAX_BOTS})")

    if args.room_code:
        code = args.room_code.strip().upper()
        print(f"Joining existing room: {code}")
    else:
        try:
            resp = requests.post(f"{BASE}/api/rooms", timeout=10)
            resp.raise_for_status()
        except Exception as exc:
            print(f"Could not reach server at {BASE}: {exc}")
            print("Make sure the backend is running (make dev or make devtest).")
            sys.exit(1)

        code = resp.json()["room_code"]
        print(f"\nCreated room:  {code}")
        print(f"Open TV at:    {tv_base}/room/{code}/tv\n")

    bots = [Bot(BOT_NAMES[i], "player", code) for i in range(count)]

    for bot in bots:
        bot.connect()
        time.sleep(0.3)   # slight stagger so joins aren't simultaneous

    print(f"All {count} bots connected. Join as Host on your phone and start the game.")
    print(f"\n{'─'*48}")
    print(f"  Room code : {code}")
    print(f"  TV URL    : {tv_base}/room/{code}/tv")
    print(f"{'─'*48}\n")

    try:
        bots[0].wait()
    except KeyboardInterrupt:
        print("\nShutting down bots…")
        for bot in bots:
            bot.disconnect()


if __name__ == "__main__":
    main()
