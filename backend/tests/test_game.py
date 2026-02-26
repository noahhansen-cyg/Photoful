import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import rooms as room_store
from rooms import rooms
import game


def setup_function():
    rooms.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_player_dicts(n):
    """Return a list of n minimal player dicts suitable for assign_prompts."""
    return [
        {
            "id":           f"p{i}",
            "name":         f"Player{i}",
            "role":         "player",
            "avatar_color": "#FF6B6B",
            "socket_id":    f"s{i}",
            "is_connected": True,
        }
        for i in range(1, n + 1)
    ]


def _room_with_n_players(n):
    """Create a room and add n players; return (room_code, player_ids)."""
    room = room_store.create_room()
    players = _make_player_dicts(n)
    for p in players:
        room_store.add_player(room["code"], p)
    stored_ids = [p["id"] for p in rooms[room["code"]]["players"]]
    return room["code"], stored_ids


def _connected(pid, name, role="player"):
    return {"id": pid, "name": name, "role": role, "is_connected": True}


# ---------------------------------------------------------------------------
# assign_prompts
# ---------------------------------------------------------------------------

def test_assign_prompts_returns_correct_count():
    players = _make_player_dicts(2)
    assert len(game.assign_prompts(players, num_prompts=3)) == 3


def test_assign_prompts_each_assignment_has_required_keys():
    players = _make_player_dicts(2)
    for p in game.assign_prompts(players, num_prompts=2):
        for key in ("prompt_id", "prompt_text", "player_ids", "submissions", "votes"):
            assert key in p, f"Missing key: {key}"


def test_assign_prompts_each_has_exactly_two_player_ids():
    players = _make_player_dicts(4)
    for p in game.assign_prompts(players, num_prompts=3):
        assert len(p["player_ids"]) == 2


def test_assign_prompts_submissions_and_votes_start_empty():
    players = _make_player_dicts(2)
    for p in game.assign_prompts(players, num_prompts=2):
        assert p["submissions"] == {}
        assert p["votes"] == {}


def test_assign_prompts_player_ids_come_from_input_list():
    players = _make_player_dicts(4)
    valid_ids = {p["id"] for p in players}
    for prompt in game.assign_prompts(players, num_prompts=3):
        for pid in prompt["player_ids"]:
            assert pid in valid_ids


def test_assign_prompts_different_prompts_selected_each_call():
    """Prompt texts should vary across calls (probabilistic — passes with overwhelming probability)."""
    players = _make_player_dicts(2)
    texts_a = {p["prompt_text"] for p in game.assign_prompts(players, num_prompts=3)}
    texts_b = {p["prompt_text"] for p in game.assign_prompts(players, num_prompts=3)}
    texts_c = {p["prompt_text"] for p in game.assign_prompts(players, num_prompts=3)}
    # At least one run should differ (all 24 prompts, picking 3 — extremely unlikely all match)
    assert not (texts_a == texts_b == texts_c)


# ---------------------------------------------------------------------------
# all_submitted
# ---------------------------------------------------------------------------

def test_all_submitted_false_when_no_submissions():
    prompt = {"player_ids": ["p1", "p2"], "submissions": {}}
    assert game.all_submitted(prompt) is False


def test_all_submitted_false_when_only_one_submitted():
    prompt = {
        "player_ids": ["p1", "p2"],
        "submissions": {"p1": {"image_url": "/img.jpg", "caption": None}},
    }
    assert game.all_submitted(prompt) is False


def test_all_submitted_true_when_both_submitted():
    prompt = {
        "player_ids": ["p1", "p2"],
        "submissions": {
            "p1": {"image_url": "/img1.jpg", "caption": None},
            "p2": {"image_url": "/img2.jpg", "caption": None},
        },
    }
    assert game.all_submitted(prompt) is True


# ---------------------------------------------------------------------------
# all_voted
# ---------------------------------------------------------------------------

def test_all_voted_true_when_no_eligible_voters():
    """Only competing players are connected — nobody left to vote."""
    prompt = {"player_ids": ["p1", "p2"], "votes": {}}
    connected = [_connected("p1", "A"), _connected("p2", "B")]
    assert game.all_voted(prompt, connected) is True


def test_all_voted_false_when_eligible_voter_has_not_voted():
    prompt = {"player_ids": ["p1", "p2"], "votes": {}}
    connected = [
        _connected("p1", "A"),
        _connected("p2", "B"),
        _connected("p3", "C"),  # eligible but hasn't voted
    ]
    assert game.all_voted(prompt, connected) is False


def test_all_voted_true_when_all_eligible_voted():
    prompt = {"player_ids": ["p1", "p2"], "votes": {"p3": "p1"}}
    connected = [
        _connected("p1", "A"),
        _connected("p2", "B"),
        _connected("p3", "C"),
    ]
    assert game.all_voted(prompt, connected) is True


def test_all_voted_multiple_eligible_partial():
    prompt = {"player_ids": ["p1", "p2"], "votes": {"p3": "p1"}}
    connected = [
        _connected("p1", "A"),
        _connected("p2", "B"),
        _connected("p3", "C"),
        _connected("p4", "D"),  # eligible but hasn't voted
    ]
    assert game.all_voted(prompt, connected) is False


def test_all_voted_host_role_excluded_from_eligible():
    """Host is not counted as an eligible voter (role != 'player')."""
    prompt = {"player_ids": ["p1", "p2"], "votes": {}}
    connected = [
        _connected("p1", "A"),
        _connected("p2", "B"),
        _connected("ph", "Host", role="host"),
    ]
    # No player-role non-competing → all voted
    assert game.all_voted(prompt, connected) is True


def test_all_voted_tv_role_excluded_from_eligible():
    prompt = {"player_ids": ["p1", "p2"], "votes": {}}
    connected = [
        _connected("p1", "A"),
        _connected("p2", "B"),
        _connected("tv", "TV", role="tv"),
    ]
    assert game.all_voted(prompt, connected) is True


# ---------------------------------------------------------------------------
# tally_scores
# ---------------------------------------------------------------------------

def test_tally_scores_no_votes_gives_zero_to_each():
    prompt = {"player_ids": ["p1", "p2"], "votes": {}}
    result = game.tally_scores(prompt)
    assert result == {"p1": 0, "p2": 0}


def test_tally_scores_one_vote_for_first_player():
    prompt = {"player_ids": ["p1", "p2"], "votes": {"p3": "p1"}}
    result = game.tally_scores(prompt)
    assert result["p1"] == game.POINTS_PER_VOTE
    assert result["p2"] == 0


def test_tally_scores_one_vote_for_second_player():
    prompt = {"player_ids": ["p1", "p2"], "votes": {"p3": "p2"}}
    result = game.tally_scores(prompt)
    assert result["p1"] == 0
    assert result["p2"] == game.POINTS_PER_VOTE


def test_tally_scores_multiple_votes_accumulated():
    prompt = {
        "player_ids": ["p1", "p2"],
        "votes": {"p3": "p1", "p4": "p1", "p5": "p2"},
    }
    result = game.tally_scores(prompt)
    assert result["p1"] == 2 * game.POINTS_PER_VOTE
    assert result["p2"] == game.POINTS_PER_VOTE


def test_tally_scores_returns_all_player_ids():
    """Even players with 0 votes appear in the result dict."""
    prompt = {"player_ids": ["p1", "p2"], "votes": {}}
    result = game.tally_scores(prompt)
    assert set(result.keys()) == {"p1", "p2"}


# ---------------------------------------------------------------------------
# apply_scores
# ---------------------------------------------------------------------------

def test_apply_scores_updates_player_score_in_room():
    code, player_ids = _room_with_n_players(2)
    p1_id, p2_id = player_ids[0], player_ids[1]
    prompt = {"player_ids": [p1_id, p2_id], "votes": {"voter": p1_id}}

    game.apply_scores(code, prompt)

    p1 = next(p for p in rooms[code]["players"] if p["id"] == p1_id)
    p2 = next(p for p in rooms[code]["players"] if p["id"] == p2_id)
    assert p1["score"] == game.POINTS_PER_VOTE
    assert p2["score"] == 0


def test_apply_scores_returns_deltas():
    code, player_ids = _room_with_n_players(2)
    p1_id, p2_id = player_ids[0], player_ids[1]
    prompt = {"player_ids": [p1_id, p2_id], "votes": {"v1": p1_id, "v2": p2_id}}

    deltas = game.apply_scores(code, prompt)

    assert deltas[p1_id] == game.POINTS_PER_VOTE
    assert deltas[p2_id] == game.POINTS_PER_VOTE


def test_apply_scores_accumulates_across_multiple_calls():
    code, player_ids = _room_with_n_players(2)
    p1_id, p2_id = player_ids[0], player_ids[1]

    prompt1 = {"player_ids": [p1_id, p2_id], "votes": {"v1": p1_id}}
    prompt2 = {"player_ids": [p1_id, p2_id], "votes": {"v2": p1_id}}
    game.apply_scores(code, prompt1)
    game.apply_scores(code, prompt2)

    p1 = next(p for p in rooms[code]["players"] if p["id"] == p1_id)
    assert p1["score"] == 2 * game.POINTS_PER_VOTE


def test_apply_scores_returns_empty_for_unknown_room():
    prompt = {"player_ids": ["p1", "p2"], "votes": {"v": "p1"}}
    # Should not raise, just returns deltas without room mutation
    deltas = game.apply_scores("XXXX", prompt)
    assert isinstance(deltas, dict)


# ---------------------------------------------------------------------------
# cancel_timer
# ---------------------------------------------------------------------------

def test_cancel_timer_kills_live_greenlet():
    mock_gl = MagicMock()
    mock_gl.dead = False
    room = {"timer_greenlet": mock_gl}

    game.cancel_timer(room)

    mock_gl.kill.assert_called_once()
    assert room["timer_greenlet"] is None


def test_cancel_timer_skips_dead_greenlet():
    mock_gl = MagicMock()
    mock_gl.dead = True
    room = {"timer_greenlet": mock_gl}

    game.cancel_timer(room)

    mock_gl.kill.assert_not_called()
    assert room["timer_greenlet"] is None


def test_cancel_timer_handles_none_greenlet():
    room = {"timer_greenlet": None}
    game.cancel_timer(room)  # should not raise
    assert room["timer_greenlet"] is None


# ---------------------------------------------------------------------------
# start_game — with timer mocked out
# ---------------------------------------------------------------------------

def _mock_socketio():
    m = MagicMock()
    m.emit = MagicMock()
    return m


def test_start_game_returns_false_for_unknown_room():
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        assert game.start_game("XXXX", mock_io) is False


def test_start_game_returns_false_with_fewer_than_two_players():
    code, _ = _room_with_n_players(1)
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        assert game.start_game(code, mock_io) is False


def test_start_game_returns_true_with_two_players():
    code, _ = _room_with_n_players(2)
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        assert game.start_game(code, mock_io) is True


def test_start_game_sets_state_to_submitting():
    code, _ = _room_with_n_players(2)
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.start_game(code, mock_io)
    assert rooms[code]["state"] == "submitting"


def test_start_game_assigns_prompts():
    code, _ = _room_with_n_players(2)
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.start_game(code, mock_io)
    assert len(rooms[code]["prompts"]) == 3


def test_start_game_sets_timer_end():
    code, _ = _room_with_n_players(2)
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.start_game(code, mock_io)
    assert rooms[code]["timer_end"] is not None


def test_start_game_broadcasts_game_state():
    code, _ = _room_with_n_players(2)
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.start_game(code, mock_io)
    mock_io.emit.assert_called_once_with("game:state", mock_io.emit.call_args[0][1], to=code)


# ---------------------------------------------------------------------------
# advance_state — with timer mocked out
# ---------------------------------------------------------------------------

def _room_in_submitting(n=2):
    code, player_ids = _room_with_n_players(n)
    players = [{"id": pid} for pid in player_ids]
    room = rooms[code]
    room["prompts"] = game.assign_prompts(
        [p for p in room["players"]], num_prompts=3
    )
    room["current_prompt_idx"] = 0
    room["state"] = "submitting"
    return code, player_ids


def test_advance_state_submitting_to_voting():
    code, _ = _room_in_submitting()
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "voting"


def test_advance_state_voting_to_scores():
    code, player_ids = _room_in_submitting()
    rooms[code]["state"] = "voting"
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "scores"


def test_advance_state_scores_to_next_submitting():
    code, _ = _room_in_submitting()
    rooms[code]["state"] = "scores"
    rooms[code]["current_prompt_idx"] = 0  # still prompts left
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "submitting"
    assert rooms[code]["current_prompt_idx"] == 1


def test_advance_state_scores_to_final_on_last_prompt():
    code, _ = _room_in_submitting()
    rooms[code]["state"] = "scores"
    rooms[code]["current_prompt_idx"] = 2  # last of 3
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "final"


def test_advance_state_final_clears_timer_end():
    code, _ = _room_in_submitting()
    rooms[code]["state"] = "scores"
    rooms[code]["current_prompt_idx"] = 2
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["timer_end"] is None


def test_advance_state_broadcasts_game_state():
    code, _ = _room_in_submitting()
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    mock_io.emit.assert_called_with("game:state", mock_io.emit.call_args[0][1], to=code)
