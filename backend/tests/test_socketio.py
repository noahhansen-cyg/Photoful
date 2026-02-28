"""
Tests for Flask-SocketIO event handlers in app.py.

Uses flask_socketio.test_client which processes events in-process (no real
network sockets) — all emits are synchronous during tests.
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app, socketio
from rooms import rooms
import rooms as room_store


@pytest.fixture(autouse=True)
def clear_rooms():
    rooms.clear()
    yield
    rooms.clear()


@pytest.fixture
def client():
    app.config["TESTING"] = True
    c = socketio.test_client(app)
    yield c
    if c.is_connected():
        c.disconnect()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _received_names(received):
    return [r["name"] for r in received]


def _find_event(received, name):
    return next((r for r in received if r["name"] == name), None)


def _join_and_become_host(client, code, name="Alice"):
    """Join as a player then claim the host role."""
    client.emit("player:join", {"room_code": code, "name": name, "role": "player"})
    client.get_received()
    client.emit("host:claim", {"room_code": code})
    client.get_received()


def _add_player_direct(code, pid, name, role="player"):
    """Add a player directly to the room store (bypassing SocketIO)."""
    room_store.add_player(code, {
        "id": pid, "socket_id": f"s_{pid}", "name": name,
        "role": role, "avatar_color": "#fff",
    })


def _setup_room_in_submitting(code, player_id, other_id="p_other"):
    """Force the room into submitting state with one prompt."""
    rooms[code]["state"] = "submitting"
    rooms[code]["prompts"] = [{
        "prompt_id":   "pid-1",
        "prompt_text": "Show us your pet",
        "player_ids":  [player_id, other_id],
        "submissions": {},
        "votes":       {},
    }]
    rooms[code]["current_prompt_idx"] = 0


def _setup_room_in_voting(code, voter_id):
    """Force room into voting state; voter_id is NOT a competing player."""
    rooms[code]["state"] = "voting"
    rooms[code]["prompts"] = [{
        "prompt_id":   "pid-1",
        "prompt_text": "test prompt",
        "player_ids":  ["p1", "p2"],
        "submissions": {},
        "votes":       {},
    }]
    rooms[code]["current_prompt_idx"] = 0
    # Add competing players so vote validation works
    for pid, name in [("p1", "CompeteA"), ("p2", "CompeteB")]:
        if not any(p["id"] == pid for p in rooms[code]["players"]):
            _add_player_direct(code, pid, name)
    # Add a second non-competing voter so all_voted() doesn't trigger
    # advance_state (which would need a timer mock)
    _add_player_direct(code, "p4", "Dave")


# ---------------------------------------------------------------------------
# handle_join
# ---------------------------------------------------------------------------

def test_join_emits_player_self(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    assert "player:self" in _received_names(received)


def test_join_player_self_has_player_id_and_role(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    event = _find_event(received, "player:self")
    assert event is not None
    data = event["args"][0]
    assert "player_id" in data
    assert data["role"] == "player"


def test_join_emits_game_state(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    assert "game:state" in _received_names(received)


def test_join_adds_player_to_room(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    assert any(p["name"] == "Alice" for p in rooms[code]["players"])


def test_join_unknown_room_emits_error(client):
    client.emit("player:join", {"room_code": "XXXX", "name": "Alice", "role": "player"})
    received = client.get_received()
    assert "error" in _received_names(received)


def test_join_second_host_different_name_emits_error(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Host1", "role": "host"})
    client.get_received()
    client2 = socketio.test_client(app)
    try:
        client2.emit("player:join", {"room_code": code, "name": "Host2", "role": "host"})
        received = client2.get_received()
        assert "error" in _received_names(received)
    finally:
        if client2.is_connected():
            client2.disconnect()


def test_join_reconnect_same_name_and_role_does_not_duplicate_player(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    client.get_received()
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    client.get_received()
    assert len(rooms[code]["players"]) == 1


def test_join_host_role_sets_room_host_id(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Eve", "role": "host"})
    client.get_received()
    assert rooms[code]["host_id"] is not None


def test_join_tv_role_does_not_set_host_id(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "TV", "role": "tv"})
    client.get_received()
    assert rooms[code]["host_id"] is None


# ---------------------------------------------------------------------------
# handle_claim_host
# ---------------------------------------------------------------------------

def test_claim_host_emits_player_self_with_host_role(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    client.get_received()
    client.emit("host:claim", {"room_code": code})
    received = client.get_received()
    event = _find_event(received, "player:self")
    assert event is not None
    assert event["args"][0]["role"] == "host"


def test_claim_host_sets_room_host_id(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    client.get_received()
    client.emit("host:claim", {"room_code": code})
    client.get_received()
    assert rooms[code]["host_id"] is not None


def test_claim_host_broadcasts_game_state(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    client.get_received()
    client.emit("host:claim", {"room_code": code})
    received = client.get_received()
    assert "game:state" in _received_names(received)


def test_claim_host_second_claim_emits_error(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    client.get_received()
    client.emit("host:claim", {"room_code": code})
    client.get_received()

    client2 = socketio.test_client(app)
    try:
        client2.emit("player:join", {"room_code": code, "name": "Bob", "role": "player"})
        client2.get_received()
        client2.emit("host:claim", {"room_code": code})
        received = client2.get_received()
        assert "error" in _received_names(received)
    finally:
        if client2.is_connected():
            client2.disconnect()


def test_claim_host_unknown_room_emits_error(client):
    client.emit("host:claim", {"room_code": "XXXX"})
    received = client.get_received()
    assert "error" in _received_names(received)


def test_claim_host_after_game_started_emits_error(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    client.get_received()
    rooms[code]["state"] = "submitting"  # game has started
    client.emit("host:claim", {"room_code": code})
    received = client.get_received()
    assert "error" in _received_names(received)


# ---------------------------------------------------------------------------
# handle_start
# ---------------------------------------------------------------------------

def test_start_transitions_room_to_submitting(client):
    code = room_store.create_room()["code"]
    _join_and_become_host(client, code)
    _add_player_direct(code, "p2", "Bob")
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        client.emit("host:start", {"room_code": code})
    assert rooms[code]["state"] == "submitting"


def test_start_broadcasts_game_state(client):
    code = room_store.create_room()["code"]
    _join_and_become_host(client, code)
    _add_player_direct(code, "p2", "Bob")
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        client.emit("host:start", {"room_code": code})
    received = client.get_received()
    assert "game:state" in _received_names(received)


def test_start_non_host_player_emits_error(client):
    code = room_store.create_room()["code"]
    # Alice joins as player (not host) — no host:claim
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    client.get_received()
    _add_player_direct(code, "p2", "Bob")
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        client.emit("host:start", {"room_code": code})
    received = client.get_received()
    assert "error" in _received_names(received)
    assert rooms[code]["state"] == "lobby"


def test_start_too_few_players_emits_error(client):
    code = room_store.create_room()["code"]
    _join_and_become_host(client, code)
    # Only Alice (the host) — no second player
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        client.emit("host:start", {"room_code": code})
    received = client.get_received()
    assert "error" in _received_names(received)
    assert rooms[code]["state"] == "lobby"


def test_start_game_already_started_emits_error(client):
    code = room_store.create_room()["code"]
    _join_and_become_host(client, code)
    rooms[code]["state"] = "submitting"  # simulate game already in progress
    client.emit("host:start", {"room_code": code})
    received = client.get_received()
    assert "error" in _received_names(received)


def test_start_unknown_room_emits_error(client):
    client.emit("host:start", {"room_code": "XXXX"})
    received = client.get_received()
    assert "error" in _received_names(received)


# ---------------------------------------------------------------------------
# handle_submit_photo
# ---------------------------------------------------------------------------

def test_submit_photo_records_submission(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    player_id = _find_event(received, "player:self")["args"][0]["player_id"]

    _setup_room_in_submitting(code, player_id)
    client.emit("submit:photo", {
        "room_code": code,
        "prompt_id": "pid-1",
        "image_url": "/uploads/test.jpg",
    })
    assert player_id in rooms[code]["prompts"][0]["submissions"]


def test_submit_photo_stores_image_url_and_caption(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    player_id = _find_event(received, "player:self")["args"][0]["player_id"]

    _setup_room_in_submitting(code, player_id)
    client.emit("submit:photo", {
        "room_code": code,
        "prompt_id": "pid-1",
        "image_url": "/uploads/test.jpg",
        "caption":   "My cat!",
    })
    sub = rooms[code]["prompts"][0]["submissions"][player_id]
    assert sub["image_url"] == "/uploads/test.jpg"
    assert sub["caption"] == "My cat!"


def test_submit_photo_broadcasts_game_state(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    player_id = _find_event(received, "player:self")["args"][0]["player_id"]

    _setup_room_in_submitting(code, player_id)
    client.emit("submit:photo", {
        "room_code": code,
        "prompt_id": "pid-1",
        "image_url": "/uploads/test.jpg",
    })
    received = client.get_received()
    assert "game:state" in _received_names(received)


def test_submit_photo_unknown_room_emits_error(client):
    client.emit("submit:photo", {
        "room_code": "XXXX",
        "prompt_id": "pid-1",
        "image_url": "/uploads/test.jpg",
    })
    received = client.get_received()
    assert "error" in _received_names(received)


def test_submit_photo_wrong_prompt_id_emits_error(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    player_id = _find_event(received, "player:self")["args"][0]["player_id"]

    _setup_room_in_submitting(code, player_id)
    client.emit("submit:photo", {
        "room_code": code,
        "prompt_id": "wrong-prompt-id",
        "image_url": "/uploads/test.jpg",
    })
    received = client.get_received()
    assert "error" in _received_names(received)


def test_submit_photo_non_assigned_player_emits_error(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Carol", "role": "player"})
    received = client.get_received()
    player_id = _find_event(received, "player:self")["args"][0]["player_id"]

    # Set up prompt with OTHER players — Carol is NOT assigned
    rooms[code]["state"] = "submitting"
    rooms[code]["prompts"] = [{
        "prompt_id":   "pid-1",
        "prompt_text": "test",
        "player_ids":  ["p1", "p2"],  # Carol not in here
        "submissions": {},
        "votes":       {},
    }]
    rooms[code]["current_prompt_idx"] = 0

    client.emit("submit:photo", {
        "room_code": code,
        "prompt_id": "pid-1",
        "image_url": "/uploads/test.jpg",
    })
    received = client.get_received()
    assert "error" in _received_names(received)


# ---------------------------------------------------------------------------
# handle_vote
# ---------------------------------------------------------------------------

def test_submit_vote_records_vote(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Carol", "role": "player"})
    received = client.get_received()
    voter_id = _find_event(received, "player:self")["args"][0]["player_id"]

    _setup_room_in_voting(code, voter_id)
    client.emit("submit:vote", {
        "room_code":    code,
        "prompt_id":    "pid-1",
        "voted_for_id": "p1",
    })
    assert rooms[code]["prompts"][0]["votes"][voter_id] == "p1"


def test_submit_vote_broadcasts_game_state(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Carol", "role": "player"})
    received = client.get_received()
    voter_id = _find_event(received, "player:self")["args"][0]["player_id"]

    _setup_room_in_voting(code, voter_id)
    client.emit("submit:vote", {
        "room_code":    code,
        "prompt_id":    "pid-1",
        "voted_for_id": "p1",
    })
    received = client.get_received()
    assert "game:state" in _received_names(received)


def test_submit_vote_unknown_room_emits_error(client):
    client.emit("submit:vote", {
        "room_code":    "XXXX",
        "prompt_id":    "pid-1",
        "voted_for_id": "p1",
    })
    received = client.get_received()
    assert "error" in _received_names(received)


def test_submit_vote_competing_player_emits_error(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    player_id = _find_event(received, "player:self")["args"][0]["player_id"]

    # Alice IS competing in this prompt
    rooms[code]["state"] = "voting"
    rooms[code]["prompts"] = [{
        "prompt_id":   "pid-1",
        "prompt_text": "test",
        "player_ids":  [player_id, "p2"],
        "submissions": {},
        "votes":       {},
    }]
    rooms[code]["current_prompt_idx"] = 0

    client.emit("submit:vote", {
        "room_code":    code,
        "prompt_id":    "pid-1",
        "voted_for_id": "p2",
    })
    received = client.get_received()
    assert "error" in _received_names(received)


def test_submit_vote_double_vote_emits_error(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Carol", "role": "player"})
    received = client.get_received()
    voter_id = _find_event(received, "player:self")["args"][0]["player_id"]

    _setup_room_in_voting(code, voter_id)
    client.emit("submit:vote", {"room_code": code, "prompt_id": "pid-1", "voted_for_id": "p1"})
    client.get_received()
    # Second vote for same prompt
    client.emit("submit:vote", {"room_code": code, "prompt_id": "pid-1", "voted_for_id": "p2"})
    received = client.get_received()
    assert "error" in _received_names(received)


# ---------------------------------------------------------------------------
# handle_disconnect
# ---------------------------------------------------------------------------

def test_disconnect_marks_player_disconnected(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    client.get_received()
    client.disconnect()
    assert rooms[code]["players"][0]["is_connected"] is False


def test_disconnect_broadcasts_game_state_to_room(client):
    code = room_store.create_room()["code"]
    observer = socketio.test_client(app)
    try:
        observer.emit("player:join", {"room_code": code, "name": "Observer", "role": "player"})
        observer.get_received()
        client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
        client.get_received()
        observer.get_received()  # clear the broadcast from Alice joining

        client.disconnect()

        received = observer.get_received()
        assert "game:state" in _received_names(received)
    finally:
        if observer.is_connected():
            observer.disconnect()


def test_disconnect_player_not_in_any_room_is_harmless():
    """A socket that never joined a room disconnecting should not raise."""
    app.config["TESTING"] = True
    c = socketio.test_client(app)
    # Disconnect without joining any room — should not raise
    c.disconnect()


# ---------------------------------------------------------------------------
# handle_restart (host:restart)
# ---------------------------------------------------------------------------

def test_restart_resets_room_to_lobby(client):
    code = room_store.create_room()["code"]
    _join_and_become_host(client, code)
    rooms[code]["state"] = "final"
    client.emit("host:restart", {"room_code": code})
    client.get_received()
    assert rooms[code]["state"] == "lobby"


def test_restart_emits_game_state(client):
    code = room_store.create_room()["code"]
    _join_and_become_host(client, code)
    rooms[code]["state"] = "final"
    client.emit("host:restart", {"room_code": code})
    received = client.get_received()
    assert "game:state" in _received_names(received)


def test_restart_requires_final_state(client):
    code = room_store.create_room()["code"]
    _join_and_become_host(client, code)
    # Room is still in "lobby" — restart must be rejected
    client.emit("host:restart", {"room_code": code})
    received = client.get_received()
    assert "error" in _received_names(received)
    assert rooms[code]["state"] == "lobby"


def test_restart_requires_host_role(client):
    code = room_store.create_room()["code"]
    # Alice joins as a plain player (no host:claim)
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    client.get_received()
    rooms[code]["state"] = "final"
    client.emit("host:restart", {"room_code": code})
    received = client.get_received()
    assert "error" in _received_names(received)


def test_restart_unknown_room_emits_error(client):
    client.emit("host:restart", {"room_code": "XXXX"})
    received = client.get_received()
    assert "error" in _received_names(received)
