import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import rooms as room_store
from rooms import rooms


def setup_function():
    rooms.clear()


# ---------------------------------------------------------------------------
# generate_room_code / create_room
# ---------------------------------------------------------------------------

def test_create_room_returns_4_letter_uppercase_code():
    room = room_store.create_room()
    assert len(room["code"]) == 4
    assert room["code"].isupper()
    assert room["code"].isalpha()


def test_create_room_initial_state_is_lobby():
    room = room_store.create_room()
    assert room["state"] == "lobby"


def test_create_room_starts_with_no_players():
    room = room_store.create_room()
    assert room["players"] == []


def test_create_room_is_stored_in_rooms_dict():
    room = room_store.create_room()
    assert room["code"] in rooms


def test_create_room_codes_are_unique():
    codes = {room_store.create_room()["code"] for _ in range(20)}
    assert len(codes) == 20


# ---------------------------------------------------------------------------
# get_room
# ---------------------------------------------------------------------------

def test_get_room_returns_existing_room():
    room = room_store.create_room()
    found = room_store.get_room(room["code"])
    assert found is not None
    assert found["code"] == room["code"]


def test_get_room_returns_none_for_unknown_code():
    assert room_store.get_room("ZZZZ") is None


# ---------------------------------------------------------------------------
# add_player
# ---------------------------------------------------------------------------

def _make_player(**overrides):
    base = {
        "id": "player-1",
        "socket_id": "socket-abc",
        "name": "Alice",
        "role": "player",
        "avatar_color": "#FF6B6B",
    }
    return {**base, **overrides}


def test_add_player_returns_true_on_success():
    room = room_store.create_room()
    assert room_store.add_player(room["code"], _make_player()) is True


def test_add_player_returns_none_for_unknown_room():
    assert room_store.add_player("XXXX", _make_player()) is None


def test_add_player_stores_player_in_room():
    room = room_store.create_room()
    room_store.add_player(room["code"], _make_player(name="Alice"))
    assert len(rooms[room["code"]]["players"]) == 1
    assert rooms[room["code"]]["players"][0]["name"] == "Alice"


def test_add_player_marks_player_as_connected():
    room = room_store.create_room()
    room_store.add_player(room["code"], _make_player())
    assert rooms[room["code"]]["players"][0]["is_connected"] is True


def test_add_player_sets_initial_score_to_zero():
    room = room_store.create_room()
    room_store.add_player(room["code"], _make_player())
    assert rooms[room["code"]]["players"][0]["score"] == 0


def test_add_player_multiple_players():
    room = room_store.create_room()
    room_store.add_player(room["code"], _make_player(id="1", socket_id="s1", name="Alice"))
    room_store.add_player(room["code"], _make_player(id="2", socket_id="s2", name="Bob"))
    assert len(rooms[room["code"]]["players"]) == 2


def test_add_player_reconnects_existing_player_by_name_and_role():
    room = room_store.create_room()
    room_store.add_player(room["code"], _make_player(socket_id="old-socket"))
    # Same name + role, new socket = reconnection
    room_store.add_player(room["code"], _make_player(socket_id="new-socket"))
    assert len(rooms[room["code"]]["players"]) == 1
    assert rooms[room["code"]]["players"][0]["socket_id"] == "new-socket"


def test_add_player_reconnect_marks_player_connected():
    room = room_store.create_room()
    room_store.add_player(room["code"], _make_player(socket_id="old-socket"))
    room_store.remove_player("old-socket")
    room_store.add_player(room["code"], _make_player(socket_id="new-socket"))
    assert rooms[room["code"]]["players"][0]["is_connected"] is True


# ---------------------------------------------------------------------------
# remove_player
# ---------------------------------------------------------------------------

def test_remove_player_returns_room_code_and_player():
    room = room_store.create_room()
    room_store.add_player(room["code"], _make_player(socket_id="s1", name="Alice"))
    code, player = room_store.remove_player("s1")
    assert code == room["code"]
    assert player["name"] == "Alice"


def test_remove_player_marks_player_disconnected():
    room = room_store.create_room()
    room_store.add_player(room["code"], _make_player(socket_id="s1"))
    room_store.remove_player("s1")
    assert rooms[room["code"]]["players"][0]["is_connected"] is False


def test_remove_player_unknown_socket_returns_none_none():
    code, player = room_store.remove_player("no-such-socket")
    assert code is None
    assert player is None


def test_remove_player_only_affects_matching_socket():
    room = room_store.create_room()
    room_store.add_player(room["code"], _make_player(id="1", socket_id="s1", name="Alice"))
    room_store.add_player(room["code"], _make_player(id="2", socket_id="s2", name="Bob"))
    room_store.remove_player("s1")
    connected = [p for p in rooms[room["code"]]["players"] if p["is_connected"]]
    assert len(connected) == 1
    assert connected[0]["name"] == "Bob"


# ---------------------------------------------------------------------------
# get_room_state
# ---------------------------------------------------------------------------

def test_get_room_state_returns_none_for_unknown_room():
    assert room_store.get_room_state("XXXX") is None


def test_get_room_state_includes_room_code_and_state():
    room = room_store.create_room()
    state = room_store.get_room_state(room["code"])
    assert state["room_code"] == room["code"]
    assert state["state"] == "lobby"


def test_get_room_state_only_includes_connected_players():
    room = room_store.create_room()
    room_store.add_player(room["code"], _make_player(id="1", socket_id="s1", name="Alice"))
    room_store.add_player(room["code"], _make_player(id="2", socket_id="s2", name="Bob"))
    room_store.remove_player("s1")
    state = room_store.get_room_state(room["code"])
    assert len(state["players"]) == 1
    assert state["players"][0]["name"] == "Bob"


def test_get_room_state_empty_when_all_disconnected():
    room = room_store.create_room()
    room_store.add_player(room["code"], _make_player(socket_id="s1"))
    room_store.remove_player("s1")
    state = room_store.get_room_state(room["code"])
    assert state["players"] == []


def test_get_room_state_includes_sprint2_fields():
    room = room_store.create_room()
    state = room_store.get_room_state(room["code"])
    assert "current_prompt" in state
    assert "timer_end" in state
    assert "prompt_number" in state
    assert "total_prompts" in state


def test_get_room_state_current_prompt_none_in_lobby():
    room = room_store.create_room()
    state = room_store.get_room_state(room["code"])
    assert state["current_prompt"] is None


def test_get_room_state_total_prompts_zero_in_lobby():
    room = room_store.create_room()
    state = room_store.get_room_state(room["code"])
    assert state["total_prompts"] == 0


# ---------------------------------------------------------------------------
# add_submission
# ---------------------------------------------------------------------------

def _make_prompt(player_ids=None):
    return {
        "prompt_id":   "pid-1",
        "prompt_text": "Test prompt",
        "player_ids":  player_ids or ["p1", "p2"],
        "submissions": {},
        "votes":       {},
    }


def _room_in_submitting():
    """Return a room in 'submitting' state with one prompt and two players."""
    room = room_store.create_room()
    code = room["code"]
    room_store.add_player(code, _make_player(id="p1", socket_id="s1", name="Alice"))
    room_store.add_player(code, _make_player(id="p2", socket_id="s2", name="Bob"))
    rooms[code]["state"] = "submitting"
    rooms[code]["prompts"] = [_make_prompt(["p1", "p2"])]
    rooms[code]["current_prompt_idx"] = 0
    return code


def test_add_submission_returns_true_on_success():
    code = _room_in_submitting()
    assert room_store.add_submission(code, "pid-1", "p1", "/img.jpg") is True


def test_add_submission_stores_image_url_and_caption():
    code = _room_in_submitting()
    room_store.add_submission(code, "pid-1", "p1", "/img.jpg", caption="Nice photo")
    sub = rooms[code]["prompts"][0]["submissions"]["p1"]
    assert sub["image_url"] == "/img.jpg"
    assert sub["caption"] == "Nice photo"


def test_add_submission_caption_defaults_to_none():
    code = _room_in_submitting()
    room_store.add_submission(code, "pid-1", "p1", "/img.jpg")
    sub = rooms[code]["prompts"][0]["submissions"]["p1"]
    assert sub["caption"] is None


def test_add_submission_returns_false_for_unknown_room():
    assert room_store.add_submission("XXXX", "pid-1", "p1", "/img.jpg") is False


def test_add_submission_returns_false_when_not_submitting():
    code = _room_in_submitting()
    rooms[code]["state"] = "voting"
    assert room_store.add_submission(code, "pid-1", "p1", "/img.jpg") is False


def test_add_submission_returns_false_for_unknown_prompt():
    code = _room_in_submitting()
    assert room_store.add_submission(code, "bad-prompt-id", "p1", "/img.jpg") is False


def test_add_submission_returns_false_for_non_assigned_player():
    code = _room_in_submitting()
    assert room_store.add_submission(code, "pid-1", "p3-not-assigned", "/img.jpg") is False


def test_add_submission_both_players_can_submit():
    code = _room_in_submitting()
    assert room_store.add_submission(code, "pid-1", "p1", "/img1.jpg") is True
    assert room_store.add_submission(code, "pid-1", "p2", "/img2.jpg") is True
    assert len(rooms[code]["prompts"][0]["submissions"]) == 2


# ---------------------------------------------------------------------------
# add_vote
# ---------------------------------------------------------------------------

def _room_in_voting():
    """Return a room in 'voting' state with one prompt (no submissions needed)."""
    code = _room_in_submitting()
    rooms[code]["state"] = "voting"
    return code


def test_add_vote_returns_true_on_success():
    code = _room_in_voting()
    # p1 and p2 are competing; add p3 as voter
    room_store.add_player(code, _make_player(id="p3", socket_id="s3", name="Carol"))
    assert room_store.add_vote(code, "pid-1", "p3", "p1") is True


def test_add_vote_stores_vote():
    code = _room_in_voting()
    room_store.add_player(code, _make_player(id="p3", socket_id="s3", name="Carol"))
    room_store.add_vote(code, "pid-1", "p3", "p1")
    assert rooms[code]["prompts"][0]["votes"]["p3"] == "p1"


def test_add_vote_returns_false_for_unknown_room():
    assert room_store.add_vote("XXXX", "pid-1", "p3", "p1") is False


def test_add_vote_returns_false_when_not_voting():
    code = _room_in_voting()
    rooms[code]["state"] = "scores"
    assert room_store.add_vote(code, "pid-1", "p3", "p1") is False


def test_add_vote_returns_false_for_unknown_prompt():
    code = _room_in_voting()
    assert room_store.add_vote(code, "bad-id", "p3", "p1") is False


def test_add_vote_returns_false_when_competing_player_votes():
    code = _room_in_voting()
    # p1 is assigned to this prompt — can't vote on it
    assert room_store.add_vote(code, "pid-1", "p1", "p2") is False


def test_add_vote_returns_false_on_double_vote():
    code = _room_in_voting()
    room_store.add_player(code, _make_player(id="p3", socket_id="s3", name="Carol"))
    room_store.add_vote(code, "pid-1", "p3", "p1")
    assert room_store.add_vote(code, "pid-1", "p3", "p2") is False


def test_add_vote_returns_false_for_invalid_voted_for():
    code = _room_in_voting()
    room_store.add_player(code, _make_player(id="p3", socket_id="s3", name="Carol"))
    assert room_store.add_vote(code, "pid-1", "p3", "p99-does-not-exist") is False


# ---------------------------------------------------------------------------
# get_current_prompt
# ---------------------------------------------------------------------------

def test_get_current_prompt_returns_none_for_unknown_room():
    assert room_store.get_current_prompt("XXXX") is None


def test_get_current_prompt_returns_none_when_no_prompts():
    room = room_store.create_room()
    assert room_store.get_current_prompt(room["code"]) is None


def test_get_current_prompt_returns_first_prompt():
    code = _room_in_submitting()
    prompt = room_store.get_current_prompt(code)
    assert prompt is not None
    assert prompt["prompt_id"] == "pid-1"


def test_get_current_prompt_respects_current_prompt_idx():
    room = room_store.create_room()
    code = room["code"]
    rooms[code]["prompts"] = [
        _make_prompt(["p1", "p2"]),
        {**_make_prompt(["p1", "p2"]), "prompt_id": "pid-2", "prompt_text": "Second"},
    ]
    rooms[code]["current_prompt_idx"] = 1
    prompt = room_store.get_current_prompt(code)
    assert prompt["prompt_id"] == "pid-2"


# ---------------------------------------------------------------------------
# add_submission — edge cases
# ---------------------------------------------------------------------------

def test_add_submission_overwrites_existing_submission():
    """A player can resubmit; the second image_url replaces the first."""
    code = _room_in_submitting()
    room_store.add_submission(code, "pid-1", "p1", "/img_first.jpg")
    result = room_store.add_submission(code, "pid-1", "p1", "/img_second.jpg")
    assert result is True
    assert rooms[code]["prompts"][0]["submissions"]["p1"]["image_url"] == "/img_second.jpg"


# ---------------------------------------------------------------------------
# get_room_state — additional field checks
# ---------------------------------------------------------------------------

def test_get_room_state_includes_player_score():
    room = room_store.create_room()
    room_store.add_player(room["code"], _make_player(id="p1", socket_id="s1"))
    rooms[room["code"]]["players"][0]["score"] = 750
    state = room_store.get_room_state(room["code"])
    assert state["players"][0]["score"] == 750


def test_get_room_state_includes_prompts_field():
    """The prompts list is returned in state (needed during the submitting phase)."""
    code = _room_in_submitting()
    state = room_store.get_room_state(code)
    assert "prompts" in state
    assert len(state["prompts"]) == 1


def test_get_room_state_includes_role_in_player_data():
    """Player role is returned so the TV can filter out TV-role entries."""
    room = room_store.create_room()
    room_store.add_player(room["code"], _make_player(id="p1", socket_id="s1", role="host"))
    state = room_store.get_room_state(room["code"])
    assert state["players"][0]["role"] == "host"


# ---------------------------------------------------------------------------
# add_player — edge cases
# ---------------------------------------------------------------------------

def test_add_player_does_not_mutate_input_dict():
    """add_player must not modify the caller's dict (uses {**player, ...} spread)."""
    room = room_store.create_room()
    original = _make_player()
    snapshot = dict(original)
    room_store.add_player(room["code"], original)
    assert original == snapshot


# ---------------------------------------------------------------------------
# reset_room
# ---------------------------------------------------------------------------

def _room_with_final_state():
    """Return a room in 'final' state with two players, scored, and a sentinel timer."""
    room = room_store.create_room()
    code = room["code"]
    room_store.add_player(code, _make_player(id="p1", socket_id="s1", name="Alice"))
    room_store.add_player(code, _make_player(id="p2", socket_id="s2", name="Bob"))
    rooms[code]["state"]              = "final"
    rooms[code]["prompts"]            = [_make_prompt(["p1", "p2"])]
    rooms[code]["current_prompt_idx"] = 1
    rooms[code]["timer_end"]          = 9_999_999.0
    rooms[code]["timer_greenlet"]     = "sentinel-greenlet"
    rooms[code]["host_id"]            = "p1"
    for p in rooms[code]["players"]:
        p["score"] = 1000
    return code


def test_reset_room_returns_true():
    code = _room_with_final_state()
    assert room_store.reset_room(code) is True


def test_reset_room_returns_false_for_unknown_room():
    assert room_store.reset_room("XXXX") is False


def test_reset_room_sets_state_to_lobby():
    code = _room_with_final_state()
    room_store.reset_room(code)
    assert rooms[code]["state"] == "lobby"


def test_reset_room_clears_prompts():
    code = _room_with_final_state()
    room_store.reset_room(code)
    assert rooms[code]["prompts"] == []


def test_reset_room_resets_prompt_index():
    code = _room_with_final_state()
    room_store.reset_room(code)
    assert rooms[code]["current_prompt_idx"] == 0


def test_reset_room_clears_timer_end():
    code = _room_with_final_state()
    room_store.reset_room(code)
    assert rooms[code]["timer_end"] is None


def test_reset_room_clears_timer_greenlet():
    code = _room_with_final_state()
    room_store.reset_room(code)
    assert rooms[code]["timer_greenlet"] is None


def test_reset_room_zeroes_all_player_scores():
    code = _room_with_final_state()
    room_store.reset_room(code)
    for p in rooms[code]["players"]:
        assert p["score"] == 0


def test_reset_room_keeps_players():
    code = _room_with_final_state()
    room_store.reset_room(code)
    assert len(rooms[code]["players"]) == 2


def test_reset_room_preserves_host_id():
    code = _room_with_final_state()
    room_store.reset_room(code)
    assert rooms[code]["host_id"] == "p1"


# ---------------------------------------------------------------------------
# Round field
# ---------------------------------------------------------------------------

def test_create_room_initial_round_is_1():
    room = room_store.create_room()
    assert room["round"] == 1


def test_get_room_state_includes_round():
    room = room_store.create_room()
    state = room_store.get_room_state(room["code"])
    assert "round" in state
    assert state["round"] == 1


def test_reset_room_resets_round_to_1():
    code = _room_with_final_state()
    rooms[code]["round"] = 2
    room_store.reset_room(code)
    assert rooms[code]["round"] == 1
