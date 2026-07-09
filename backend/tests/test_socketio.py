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
    with patch("game._start_timer", return_value=MagicMock()):
        client.emit("host:start", {"room_code": code})
    assert rooms[code]["state"] == "submitting"


def test_start_broadcasts_game_state(client):
    code = room_store.create_room()["code"]
    _join_and_become_host(client, code)
    _add_player_direct(code, "p2", "Bob")
    with patch("game._start_timer", return_value=MagicMock()):
        client.emit("host:start", {"room_code": code})
    received = client.get_received()
    assert "game:state" in _received_names(received)


def test_start_non_host_player_emits_error(client):
    code = room_store.create_room()["code"]
    # Alice joins as player (not host) — no host:claim
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    client.get_received()
    _add_player_direct(code, "p2", "Bob")
    with patch("game._start_timer", return_value=MagicMock()):
        client.emit("host:start", {"room_code": code})
    received = client.get_received()
    assert "error" in _received_names(received)
    assert rooms[code]["state"] == "lobby"


def test_start_too_few_players_emits_error(client):
    code = room_store.create_room()["code"]
    _join_and_become_host(client, code)
    # Only Alice (the host) — no second player
    with patch("game._start_timer", return_value=MagicMock()):
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


# ---------------------------------------------------------------------------
# submit:caption
# ---------------------------------------------------------------------------

def _setup_room_in_captioning(code, player_id):
    """Force the room into captioning state with a caption_prompt."""
    rooms[code]["state"] = "captioning"
    rooms[code]["caption_prompt"] = {
        "prompt_id":            "cp-1",
        "round_type":           "caption",
        "featured_image_url":   "/img.jpg",
        "featured_player_id":   player_id,
        "featured_prompt_text": "A prompt",
        "player_ids":           [player_id],
        "submissions":          {},
        "votes":                {},
        "score_deltas":         {},
    }


def test_submit_caption_records_caption(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    player_id = next(r["args"][0]["player_id"] for r in received if r["name"] == "player:self")
    _setup_room_in_captioning(code, player_id)
    client.emit("submit:caption", {"room_code": code, "caption_text": "My caption"})
    client.get_received()
    assert rooms[code]["caption_prompt"]["submissions"][player_id]["caption"] == "My caption"


def test_submit_caption_broadcasts_game_state(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    player_id = next(r["args"][0]["player_id"] for r in received if r["name"] == "player:self")
    _setup_room_in_captioning(code, player_id)
    client.emit("submit:caption", {"room_code": code, "caption_text": "My caption"})
    received = client.get_received()
    assert "game:state" in _received_names(received)


def test_submit_caption_advances_early_when_all_submitted(client):
    """When the sole player submits, the state should advance to caption_voting."""
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    player_id = next(r["args"][0]["player_id"] for r in received if r["name"] == "player:self")
    _setup_room_in_captioning(code, player_id)
    with patch("game._start_timer", return_value=MagicMock()):
        client.emit("submit:caption", {"room_code": code, "caption_text": "My caption"})
        client.get_received()
    assert rooms[code]["state"] == "caption_voting"


def test_submit_caption_advances_early_when_last_of_multiple_players_submits(client):
    """Alice's submission is the last — with Bob pre-submitted, state advances immediately."""
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    alice_id = next(r["args"][0]["player_id"] for r in received if r["name"] == "player:self")
    bob_id = "bob-player"
    _add_player_direct(code, bob_id, "Bob")
    # Caption prompt with both Alice and Bob assigned
    rooms[code]["state"] = "captioning"
    rooms[code]["caption_prompt"] = {
        "prompt_id":            "cp-1",
        "round_type":           "caption",
        "featured_image_url":   "/img.jpg",
        "featured_player_id":   bob_id,
        "featured_prompt_text": "A prompt",
        "player_ids":           [alice_id, bob_id],
        "submissions":          {bob_id: {"caption": "Bob's caption"}},  # Bob pre-submitted
        "votes":                {},
        "score_deltas":         {},
    }
    rooms[code]["timer"] = MagicMock()
    with patch("game._start_timer", return_value=MagicMock()):
        client.emit("submit:caption", {"room_code": code, "caption_text": "Alice's caption"})
        client.get_received()
    assert rooms[code]["state"] == "caption_voting"


def test_submit_caption_does_not_advance_early_when_not_all_submitted(client):
    """With Bob still pending, Alice submitting alone must NOT advance the state."""
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    alice_id = next(r["args"][0]["player_id"] for r in received if r["name"] == "player:self")
    bob_id = "bob-player"
    _add_player_direct(code, bob_id, "Bob")
    rooms[code]["state"] = "captioning"
    rooms[code]["caption_prompt"] = {
        "prompt_id":            "cp-1",
        "round_type":           "caption",
        "featured_image_url":   "/img.jpg",
        "featured_player_id":   bob_id,
        "featured_prompt_text": "A prompt",
        "player_ids":           [alice_id, bob_id],
        "submissions":          {},  # nobody submitted yet
        "votes":                {},
        "score_deltas":         {},
    }
    client.emit("submit:caption", {"room_code": code, "caption_text": "Alice's caption"})
    client.get_received()
    assert rooms[code]["state"] == "captioning"  # must still be waiting


def test_submit_caption_late_joiner_does_not_block_early_advance(client):
    """A player who joined after caption prompt was created must not block early advance."""
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    alice_id = next(r["args"][0]["player_id"] for r in received if r["name"] == "player:self")
    bob_id = "bob-player"
    _add_player_direct(code, bob_id, "Bob")
    late_id = "late-joiner"
    _add_player_direct(code, late_id, "Late")
    # Caption prompt has only Alice and Bob (Late joined after creation)
    rooms[code]["state"] = "captioning"
    rooms[code]["caption_prompt"] = {
        "prompt_id":            "cp-1",
        "round_type":           "caption",
        "featured_image_url":   "/img.jpg",
        "featured_player_id":   bob_id,
        "featured_prompt_text": "A prompt",
        "player_ids":           [alice_id, bob_id],  # Late NOT in here
        "submissions":          {bob_id: {"caption": "Bob's caption"}},
        "votes":                {},
        "score_deltas":         {},
    }
    rooms[code]["timer"] = MagicMock()
    with patch("game._start_timer", return_value=MagicMock()):
        client.emit("submit:caption", {"room_code": code, "caption_text": "Alice's caption"})
        client.get_received()
    assert rooms[code]["state"] == "caption_voting"


def test_submit_caption_unknown_room_emits_error(client):
    client.emit("submit:caption", {"room_code": "XXXX", "caption_text": "text"})
    received = client.get_received()
    assert "error" in _received_names(received)


# ---------------------------------------------------------------------------
# submit:caption_vote
# ---------------------------------------------------------------------------

def _setup_room_in_caption_voting(code, voter_id, candidate_id):
    """Force room into caption_voting with voter and candidate in the prompt."""
    rooms[code]["state"] = "caption_voting"
    rooms[code]["caption_prompt"] = {
        "prompt_id":            "cp-1",
        "round_type":           "caption",
        "featured_image_url":   "/img.jpg",
        "featured_player_id":   candidate_id,
        "featured_prompt_text": "A prompt",
        "player_ids":           [voter_id, candidate_id],
        "submissions":          {
            voter_id:     {"caption": "A"},
            candidate_id: {"caption": "B"},
        },
        "votes":        {},
        "score_deltas": {},
    }


def test_submit_caption_vote_records_vote(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    voter_id = next(r["args"][0]["player_id"] for r in received if r["name"] == "player:self")
    candidate_id = "other-player"
    _add_player_direct(code, candidate_id, "Bob")
    _setup_room_in_caption_voting(code, voter_id, candidate_id)
    client.emit("submit:caption_vote", {"room_code": code, "voted_for_id": candidate_id})
    client.get_received()
    assert rooms[code]["caption_prompt"]["votes"][voter_id] == candidate_id


def test_submit_caption_vote_broadcasts_game_state(client):
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    voter_id = next(r["args"][0]["player_id"] for r in received if r["name"] == "player:self")
    candidate_id = "other-player"
    _add_player_direct(code, candidate_id, "Bob")
    _setup_room_in_caption_voting(code, voter_id, candidate_id)
    client.emit("submit:caption_vote", {"room_code": code, "voted_for_id": candidate_id})
    received = client.get_received()
    assert "game:state" in _received_names(received)


def test_submit_caption_vote_advances_early_when_all_voted(client):
    """When the last eligible voter votes, the state advances to caption_scores."""
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    voter_id = next(r["args"][0]["player_id"] for r in received if r["name"] == "player:self")
    candidate_id = "other-player"
    _add_player_direct(code, candidate_id, "Bob")
    _setup_room_in_caption_voting(code, voter_id, candidate_id)
    # Pre-populate Bob's vote so Alice's vote completes all_voted
    rooms[code]["caption_prompt"]["votes"][candidate_id] = voter_id
    with patch("game._start_timer", return_value=MagicMock()):
        client.emit("submit:caption_vote", {"room_code": code, "voted_for_id": candidate_id})
        client.get_received()
    assert rooms[code]["state"] == "caption_scores"


def test_submit_caption_vote_unknown_room_emits_error(client):
    client.emit("submit:caption_vote", {"room_code": "XXXX", "voted_for_id": "p1"})
    received = client.get_received()
    assert "error" in _received_names(received)


# ---------------------------------------------------------------------------
# "Player not found" error paths — sender not in room
# ---------------------------------------------------------------------------

def test_claim_host_player_not_in_room_emits_error(client):
    """host:claim from a socket that never joined the room → 'Player not found'."""
    code = room_store.create_room()["code"]
    client.emit("host:claim", {"room_code": code})
    received = client.get_received()
    errors = [r for r in received if r["name"] == "error"]
    assert errors
    assert "not found" in errors[0]["args"][0]["message"].lower()


def test_submit_photo_player_not_in_room_emits_error(client):
    """submit:photo from a socket that never joined → 'Player not found'."""
    code = room_store.create_room()["code"]
    rooms[code]["state"] = "submitting"
    client.emit("submit:photo", {"room_code": code, "prompt_id": "pid-1", "image_url": "/img.jpg"})
    received = client.get_received()
    errors = [r for r in received if r["name"] == "error"]
    assert errors
    assert "not found" in errors[0]["args"][0]["message"].lower()


def test_submit_vote_player_not_in_room_emits_error(client):
    """submit:vote from a socket that never joined → 'Player not found'."""
    code = room_store.create_room()["code"]
    rooms[code]["state"] = "voting"
    client.emit("submit:vote", {"room_code": code, "prompt_id": "pid-1", "voted_for_id": "p1"})
    received = client.get_received()
    errors = [r for r in received if r["name"] == "error"]
    assert errors
    assert "not found" in errors[0]["args"][0]["message"].lower()


def test_submit_caption_player_not_in_room_emits_error(client):
    """submit:caption from a socket that never joined → 'Player not found'."""
    code = room_store.create_room()["code"]
    rooms[code]["state"] = "captioning"
    client.emit("submit:caption", {"room_code": code, "caption_text": "hi"})
    received = client.get_received()
    errors = [r for r in received if r["name"] == "error"]
    assert errors
    assert "not found" in errors[0]["args"][0]["message"].lower()


def test_submit_caption_vote_player_not_in_room_emits_error(client):
    """submit:caption_vote from a socket that never joined → 'Player not found'."""
    code = room_store.create_room()["code"]
    rooms[code]["state"] = "caption_voting"
    client.emit("submit:caption_vote", {"room_code": code, "voted_for_id": "p1"})
    received = client.get_received()
    errors = [r for r in received if r["name"] == "error"]
    assert errors
    assert "not found" in errors[0]["args"][0]["message"].lower()


# ---------------------------------------------------------------------------
# add_player returns None (race condition)
# ---------------------------------------------------------------------------

def test_join_add_player_fails_emits_error(client):
    """If add_player returns None (room vanished after get_room check), emit error."""
    code = room_store.create_room()["code"]
    with patch("app.room_store.add_player", return_value=None):
        client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
        received = client.get_received()
    assert "error" in _received_names(received)


# ---------------------------------------------------------------------------
# add_caption / add_caption_vote failure paths
# ---------------------------------------------------------------------------

def test_submit_caption_add_caption_fails_emits_error(client):
    """When add_caption returns False, the handler should emit an error."""
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    player_id = next(r["args"][0]["player_id"] for r in received if r["name"] == "player:self")
    _setup_room_in_captioning(code, player_id)
    with patch("app.room_store.add_caption", return_value=False):
        client.emit("submit:caption", {"room_code": code, "caption_text": "My caption"})
        received = client.get_received()
    assert "error" in _received_names(received)


def test_submit_caption_vote_add_fails_emits_error(client):
    """When add_caption_vote returns False, the handler should emit an error."""
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    voter_id = next(r["args"][0]["player_id"] for r in received if r["name"] == "player:self")
    candidate_id = "other-player"
    _add_player_direct(code, candidate_id, "Bob")
    _setup_room_in_caption_voting(code, voter_id, candidate_id)
    with patch("app.room_store.add_caption_vote", return_value=False):
        client.emit("submit:caption_vote", {"room_code": code, "voted_for_id": candidate_id})
        received = client.get_received()
    assert "error" in _received_names(received)


# ---------------------------------------------------------------------------
# Early advance — all photos submitted / all votes cast
# ---------------------------------------------------------------------------

def test_submit_photo_accepted_during_voting_intro_grace_window(client):
    """A submit:photo that arrives just after the timer fires (state=voting_intro)
    must still be recorded and the photo must appear during voting."""
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    player_id = next(r["args"][0]["player_id"] for r in received if r["name"] == "player:self")
    other_id = "p_other"
    _add_player_direct(code, other_id, "Bob")
    _setup_room_in_submitting(code, player_id, other_id)
    # Simulate: timer fired, state advanced to voting_intro before Alice's upload finished
    rooms[code]["state"] = "voting_intro"
    rooms[code]["timer"] = MagicMock()
    with patch("game._start_timer", return_value=MagicMock()):
        client.emit("submit:photo", {
            "room_code": code, "prompt_id": "pid-1", "image_url": "/late.jpg",
        })
        client.get_received()
    # Submission must be recorded despite the late arrival
    assert rooms[code]["prompts"][0]["submissions"][player_id]["image_url"] == "/late.jpg"


def test_submit_photo_during_voting_intro_advances_to_voting_when_all_done(client):
    """If the late submit completes all submissions, it should skip the rest of
    voting_intro and jump straight to voting."""
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    player_id = next(r["args"][0]["player_id"] for r in received if r["name"] == "player:self")
    other_id = "p_other"
    _add_player_direct(code, other_id, "Bob")
    _setup_room_in_submitting(code, player_id, other_id)
    # Bob already submitted; Alice's is the last one but arrives during voting_intro
    rooms[code]["prompts"][0]["submissions"][other_id] = {"image_url": "/bob.jpg", "caption": None}
    rooms[code]["state"] = "voting_intro"
    rooms[code]["timer"] = MagicMock()
    with patch("game._start_timer", return_value=MagicMock()):
        client.emit("submit:photo", {
            "room_code": code, "prompt_id": "pid-1", "image_url": "/late.jpg",
        })
        client.get_received()
    assert rooms[code]["state"] == "voting"


def test_submit_photo_advances_early_when_all_submitted(client):
    """When Alice's photo completes all submissions, the state advances immediately."""
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    player_id = next(r["args"][0]["player_id"] for r in received if r["name"] == "player:self")
    other_id = "p_other"
    _add_player_direct(code, other_id, "Bob")
    _setup_room_in_submitting(code, player_id, other_id)
    # Pre-populate the other player's submission so Alice's is the last one.
    rooms[code]["prompts"][0]["submissions"][other_id] = {"image_url": "/img.jpg", "caption": None}
    rooms[code]["timer"] = MagicMock()
    with patch("game._start_timer", return_value=MagicMock()):
        client.emit("submit:photo", {
            "room_code": code, "prompt_id": "pid-1", "image_url": "/img2.jpg",
        })
        client.get_received()
    assert rooms[code]["state"] == "voting_intro"


def test_submit_vote_advances_early_when_all_voted(client):
    """When Alice is the sole eligible voter and votes, the state advances immediately."""
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    received = client.get_received()
    voter_id = next(r["args"][0]["player_id"] for r in received if r["name"] == "player:self")
    # Set up voting state — Alice is NOT a competing player; no extra voters added.
    rooms[code]["state"] = "voting"
    rooms[code]["prompts"] = [{
        "prompt_id":   "pid-1",
        "prompt_text": "test prompt",
        "player_ids":  ["p1", "p2"],
        "submissions": {},
        "votes":       {},
    }]
    rooms[code]["current_prompt_idx"] = 0
    for pid, name in [("p1", "CompeteA"), ("p2", "CompeteB")]:
        _add_player_direct(code, pid, name)
    rooms[code]["timer"] = MagicMock()
    with patch("game._start_timer", return_value=MagicMock()):
        client.emit("submit:vote", {
            "room_code": code, "prompt_id": "pid-1", "voted_for_id": "p1",
        })
        client.get_received()
    assert rooms[code]["state"] == "scores"


# ---------------------------------------------------------------------------
# host:extend_timer
# ---------------------------------------------------------------------------

def test_extend_timer_host_extends_successfully(client):
    """Host can extend the submission timer."""
    code = room_store.create_room()["code"]
    _join_and_become_host(client, code)
    _setup_room_in_submitting(code, "some-player")
    rooms[code]["timer"] = MagicMock()
    with patch("game._start_timer", return_value=MagicMock()):
        client.emit("host:extend_timer", {"room_code": code})
        received = client.get_received()
    assert "game:state" in _received_names(received)
    assert rooms[code]["state"] == "submitting"


def test_extend_timer_broadcasts_updated_timer_end(client):
    """Extending the timer updates timer_end on the room."""
    import time
    code = room_store.create_room()["code"]
    _join_and_become_host(client, code)
    _setup_room_in_submitting(code, "some-player")
    rooms[code]["timer_end"] = time.time() + 10
    rooms[code]["timer"] = MagicMock()
    before = time.time()
    with patch("game._start_timer", return_value=MagicMock()):
        client.emit("host:extend_timer", {"room_code": code})
        client.get_received()
    # timer_end should have grown by approximately EXTEND_AMOUNT
    import game as game_module
    assert rooms[code]["timer_end"] >= before + game_module.EXTEND_AMOUNT


def test_extend_timer_non_host_emits_error(client):
    """A plain player cannot extend the timer."""
    code = room_store.create_room()["code"]
    client.emit("player:join", {"room_code": code, "name": "Alice", "role": "player"})
    client.get_received()
    _setup_room_in_submitting(code, "some-player")
    client.emit("host:extend_timer", {"room_code": code})
    received = client.get_received()
    assert "error" in _received_names(received)


def test_extend_timer_unknown_room_emits_error(client):
    client.emit("host:extend_timer", {"room_code": "XXXX"})
    received = client.get_received()
    assert "error" in _received_names(received)


def test_extend_timer_wrong_state_emits_error(client):
    """Cannot extend timer if the room is not in submitting state."""
    code = room_store.create_room()["code"]
    _join_and_become_host(client, code)
    rooms[code]["state"] = "voting"
    client.emit("host:extend_timer", {"room_code": code})
    received = client.get_received()
    assert "error" in _received_names(received)


def test_extend_timer_player_not_in_room_emits_error(client):
    """Socket that never joined a room cannot extend the timer."""
    code = room_store.create_room()["code"]
    rooms[code]["state"] = "submitting"
    client.emit("host:extend_timer", {"room_code": code})
    received = client.get_received()
    assert "error" in _received_names(received)
