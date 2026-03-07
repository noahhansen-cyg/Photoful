import pytest
import sys
import os
import uuid
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

def test_assign_prompts_two_players_returns_three_prompts():
    """2 players → 3 total prompts (each player competes in all 3)."""
    players = _make_player_dicts(2)
    assert len(game.assign_prompts(players)) == game.PROMPTS_PER_PLAYER


def test_assign_prompts_four_players_returns_six_prompts():
    """4 players → 6 total prompts so every player appears in exactly 3."""
    players = _make_player_dicts(4)
    assert len(game.assign_prompts(players)) == game.PROMPTS_PER_PLAYER * 4 // 2


def test_assign_prompts_each_player_appears_in_three_prompts_even():
    """For even player counts every player appears in exactly PROMPTS_PER_PLAYER prompts."""
    for n in (2, 4, 6):
        players = _make_player_dicts(n)
        prompts = game.assign_prompts(players)
        counts = {p["id"]: 0 for p in players}
        for prompt in prompts:
            for pid in prompt["player_ids"]:
                counts[pid] += 1
        for pid, count in counts.items():
            assert count == game.PROMPTS_PER_PLAYER, (
                f"n={n}: player {pid} appeared in {count} prompts, expected {game.PROMPTS_PER_PLAYER}"
            )


def test_assign_prompts_each_player_appears_in_at_least_three_prompts_odd():
    """For odd player counts every player appears in PROMPTS_PER_PLAYER or PROMPTS_PER_PLAYER+1 prompts."""
    for n in (3, 5):
        players = _make_player_dicts(n)
        prompts = game.assign_prompts(players)
        counts = {p["id"]: 0 for p in players}
        for prompt in prompts:
            for pid in prompt["player_ids"]:
                counts[pid] += 1
        for pid, count in counts.items():
            assert count >= game.PROMPTS_PER_PLAYER, (
                f"n={n}: player {pid} appeared in only {count} prompts"
            )
            assert count <= game.PROMPTS_PER_PLAYER + 1, (
                f"n={n}: player {pid} appeared in {count} prompts (too many)"
            )


def test_assign_prompts_each_assignment_has_required_keys():
    players = _make_player_dicts(2)
    for p in game.assign_prompts(players):
        for key in ("prompt_id", "prompt_text", "player_ids", "submissions", "votes"):
            assert key in p, f"Missing key: {key}"


def test_assign_prompts_each_has_exactly_two_player_ids():
    players = _make_player_dicts(4)
    for p in game.assign_prompts(players):
        assert len(p["player_ids"]) == 2


def test_assign_prompts_submissions_and_votes_start_empty():
    players = _make_player_dicts(2)
    for p in game.assign_prompts(players):
        assert p["submissions"] == {}
        assert p["votes"] == {}


def test_assign_prompts_player_ids_come_from_input_list():
    players = _make_player_dicts(4)
    valid_ids = {p["id"] for p in players}
    for prompt in game.assign_prompts(players):
        for pid in prompt["player_ids"]:
            assert pid in valid_ids


def test_assign_prompts_different_prompts_selected_each_call():
    """Prompt texts should vary across calls (probabilistic — passes with overwhelming probability)."""
    players = _make_player_dicts(2)
    texts_a = {p["prompt_text"] for p in game.assign_prompts(players)}
    texts_b = {p["prompt_text"] for p in game.assign_prompts(players)}
    texts_c = {p["prompt_text"] for p in game.assign_prompts(players)}
    # At least one run should differ (24 prompts, picking 3 — extremely unlikely all match)
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
# all_prompts_submitted
# ---------------------------------------------------------------------------

def test_all_prompts_submitted_false_when_any_prompt_incomplete():
    prompts = [
        {"player_ids": ["p1", "p2"], "submissions": {"p1": {}, "p2": {}}},
        {"player_ids": ["p3", "p4"], "submissions": {"p3": {}}},  # p4 missing
    ]
    assert game.all_prompts_submitted(prompts) is False


def test_all_prompts_submitted_true_when_all_complete():
    prompts = [
        {"player_ids": ["p1", "p2"], "submissions": {"p1": {}, "p2": {}}},
        {"player_ids": ["p3", "p4"], "submissions": {"p3": {}, "p4": {}}},
    ]
    assert game.all_prompts_submitted(prompts) is True


def test_all_prompts_submitted_true_for_empty_list():
    assert game.all_prompts_submitted([]) is True


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


def test_all_voted_host_counts_as_eligible_voter():
    """Host is an eligible voter when not competing."""
    prompt = {"player_ids": ["p1", "p2"], "votes": {}}
    connected = [
        _connected("p1", "A"),
        _connected("p2", "B"),
        _connected("ph", "Host", role="host"),
    ]
    # Host hasn't voted yet → not all voted
    assert game.all_voted(prompt, connected) is False


def test_all_voted_host_vote_satisfies_eligibility():
    """all_voted is True once the host has voted."""
    prompt = {"player_ids": ["p1", "p2"], "votes": {"ph": "p1"}}
    connected = [
        _connected("p1", "A"),
        _connected("p2", "B"),
        _connected("ph", "Host", role="host"),
    ]
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
    # 2 players → PROMPTS_PER_PLAYER prompts each, all shared = PROMPTS_PER_PLAYER total
    assert len(rooms[code]["prompts"]) == game.PROMPTS_PER_PLAYER


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
    room = rooms[code]
    room["prompts"] = game.assign_prompts(room["players"])
    room["current_prompt_idx"] = 0
    room["state"] = "submitting"
    return code, player_ids


def test_advance_state_submitting_to_voting_intro():
    code, _ = _room_in_submitting()
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "voting_intro"
    assert rooms[code]["current_prompt_idx"] == 0
    assert rooms[code]["timer_end"] is not None


def test_advance_state_voting_intro_to_voting():
    code, _ = _room_in_submitting()
    rooms[code]["state"] = "voting_intro"
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "voting"
    assert rooms[code]["timer_end"] is not None


def test_voting_intro_timeout_constant_is_positive():
    assert game.VOTING_INTRO_TIMEOUT > 0


def test_advance_state_voting_to_scores():
    code, player_ids = _room_in_submitting()
    rooms[code]["state"] = "voting"
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "scores"


def test_advance_state_scores_to_next_voting():
    code, _ = _room_in_submitting()
    rooms[code]["state"] = "scores"
    rooms[code]["current_prompt_idx"] = 0  # still prompts left
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "voting"
    assert rooms[code]["current_prompt_idx"] == 1


def test_advance_state_scores_to_final_on_last_prompt():
    code, _ = _room_in_submitting()
    rooms[code]["state"] = "scores"
    rooms[code]["round"] = game.TOTAL_ROUNDS  # already on the last round
    last_idx = len(rooms[code]["prompts"]) - 1
    rooms[code]["current_prompt_idx"] = last_idx
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "final"


def test_advance_state_final_clears_timer_end():
    code, _ = _room_in_submitting()
    rooms[code]["state"] = "scores"
    rooms[code]["round"] = game.TOTAL_ROUNDS  # already on the last round
    last_idx = len(rooms[code]["prompts"]) - 1
    rooms[code]["current_prompt_idx"] = last_idx
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


# ---------------------------------------------------------------------------
# tally_scores — edge cases
# ---------------------------------------------------------------------------

def test_tally_scores_ignores_votes_for_non_competing_player():
    """Votes targeting a player not in player_ids are silently discarded."""
    prompt = {
        "player_ids": ["p1", "p2"],
        "votes": {"voter": "p99-not-in-matchup"},
    }
    result = game.tally_scores(prompt)
    assert result["p1"] == 0
    assert result["p2"] == 0


# ---------------------------------------------------------------------------
# advance_state — score_deltas stored on prompt after voting
# ---------------------------------------------------------------------------

def test_advance_state_voting_to_scores_stores_score_deltas_on_prompt():
    code, player_ids = _room_in_submitting()
    p1_id = player_ids[0]
    rooms[code]["state"] = "voting"
    # Add an eligible voter and register their vote for p1
    voter = {
        "id": "voter1", "name": "Voter", "role": "player",
        "avatar_color": "#fff", "socket_id": "sv1", "is_connected": True,
    }
    room_store.add_player(code, voter)
    rooms[code]["prompts"][0]["votes"] = {"voter1": p1_id}

    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)

    assert "score_deltas" in rooms[code]["prompts"][0]
    assert rooms[code]["prompts"][0]["score_deltas"][p1_id] == game.POINTS_PER_VOTE


# ---------------------------------------------------------------------------
# start_game — player filtering (disconnected & TV roles)
# ---------------------------------------------------------------------------

def test_start_game_excludes_disconnected_players():
    """A disconnected player does not count toward the 2-player minimum."""
    code, _ = _room_with_n_players(2)
    rooms[code]["players"][0]["is_connected"] = False
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        result = game.start_game(code, mock_io)
    assert result is False  # only 1 connected player → cannot start


def test_start_game_excludes_tv_players_from_prompt_assignments():
    """TV-role players should never appear in any prompt's player_ids."""
    code, _ = _room_with_n_players(2)
    tv = {
        "id": "tv1", "name": "TV", "role": "tv",
        "avatar_color": "#fff", "socket_id": "stv", "is_connected": True,
    }
    room_store.add_player(code, tv)
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.start_game(code, mock_io)
    all_assigned_ids = {pid for p in rooms[code]["prompts"] for pid in p["player_ids"]}
    assert "tv1" not in all_assigned_ids


# ---------------------------------------------------------------------------
# _make_pairs — direct unit tests
# ---------------------------------------------------------------------------

def test_make_pairs_returns_empty_for_zero_players():
    assert game._make_pairs(0) == []


def test_make_pairs_returns_empty_for_one_player():
    assert game._make_pairs(1) == []


def test_make_pairs_n2_returns_prompts_per_player_pairs():
    """2 players → exactly PROMPTS_PER_PLAYER pairs total."""
    pairs = game._make_pairs(2)
    assert len(pairs) == game.PROMPTS_PER_PLAYER


def test_make_pairs_total_length_scales_with_player_count():
    """Total pairs = ceil(n * PROMPTS_PER_PLAYER / 2)."""
    import math
    for n in range(2, 8):
        pairs = game._make_pairs(n)
        expected = math.ceil(n * game.PROMPTS_PER_PLAYER / 2)
        assert len(pairs) == expected, f"n={n}: got {len(pairs)}, expected {expected}"


def test_make_pairs_all_pairs_have_distinct_indices():
    """No pair should have the same index twice (a player vs themselves)."""
    for n in range(2, 8):
        for (i, j) in game._make_pairs(n):
            assert i != j, f"n={n}: pair ({i}, {j}) has the same index"


def test_make_pairs_each_index_appears_at_least_prompts_per_player_times():
    """Every player index must appear in at least PROMPTS_PER_PLAYER pairs."""
    for n in range(2, 8):
        pairs = game._make_pairs(n)
        counts = [0] * n
        for (i, j) in pairs:
            counts[i] += 1
            counts[j] += 1
        for idx, count in enumerate(counts):
            assert count >= game.PROMPTS_PER_PLAYER, (
                f"n={n}: index {idx} appears only {count} times "
                f"(expected >= {game.PROMPTS_PER_PLAYER})"
            )


def test_make_pairs_indices_within_valid_range():
    """All pair indices must be valid (0 to n-1)."""
    for n in range(2, 8):
        for (i, j) in game._make_pairs(n):
            assert 0 <= i < n, f"n={n}: index {i} out of range"
            assert 0 <= j < n, f"n={n}: index {j} out of range"


# ---------------------------------------------------------------------------
# load_prompts
# ---------------------------------------------------------------------------

def test_load_prompts_returns_a_list():
    prompts = game.load_prompts()
    assert isinstance(prompts, list)


def test_load_prompts_all_items_are_nonempty_strings():
    for p in game.load_prompts():
        assert isinstance(p, str), f"Expected str, got {type(p)}"
        assert len(p) > 0, "Prompt must be non-empty"


def test_load_prompts_has_enough_for_largest_game():
    """The prompt pool must be large enough for an 8-player game (12 prompts)."""
    prompts = game.load_prompts()
    max_pairs = game._make_pairs(8)  # ceil(8 * 3 / 2) = 12
    assert len(prompts) >= len(max_pairs), (
        f"Only {len(prompts)} prompts in pool, need at least {len(max_pairs)} "
        f"for an 8-player game"
    )


def test_load_prompts_returns_unique_strings():
    """All prompts in the pool should be distinct."""
    prompts = game.load_prompts()
    assert len(prompts) == len(set(prompts)), "Duplicate prompts found in prompts.json"


# ---------------------------------------------------------------------------
# Timeout constants
# ---------------------------------------------------------------------------

def test_submit_timeout_is_120_seconds():
    assert game.SUBMIT_TIMEOUT == 120, (
        f"SUBMIT_TIMEOUT is {game.SUBMIT_TIMEOUT}s — expected 120s"
    )


def test_start_game_timer_end_is_submit_timeout_from_now():
    """timer_end should be approximately now + SUBMIT_TIMEOUT."""
    import time as _time
    code, _ = _room_with_n_players(2)
    mock_io = _mock_socketio()
    before = _time.time()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.start_game(code, mock_io)
    after = _time.time()
    expected_min = before + game.SUBMIT_TIMEOUT
    expected_max = after  + game.SUBMIT_TIMEOUT
    assert expected_min <= rooms[code]["timer_end"] <= expected_max, (
        f"timer_end {rooms[code]['timer_end']:.2f} not in "
        f"[{expected_min:.2f}, {expected_max:.2f}]"
    )


# ---------------------------------------------------------------------------
# Timeout constants — SCORES_TIMEOUT
# ---------------------------------------------------------------------------

def test_scores_timeout_is_5_seconds():
    assert game.SCORES_TIMEOUT == 5, (
        f"SCORES_TIMEOUT is {game.SCORES_TIMEOUT}s — expected 5s"
    )


# ---------------------------------------------------------------------------
# Two-round gameplay
# ---------------------------------------------------------------------------

def test_tally_scores_uses_custom_points_per_vote():
    prompt = {
        "player_ids": ["p1", "p2"],
        "votes": {"voter1": "p1", "voter2": "p1"},
    }
    result = game.tally_scores(prompt, points_per_vote=2000)
    assert result["p1"] == 4000
    assert result["p2"] == 0


def test_apply_scores_uses_double_points_in_round_2():
    code, player_ids = _room_in_submitting()
    p1_id = player_ids[0]
    rooms[code]["state"] = "voting"
    rooms[code]["round"] = 2
    rooms[code]["prompts"][0]["votes"] = {"voter": p1_id}
    # Add a voter outside the matchup so the vote is valid
    voter = {
        "id": "voter", "name": "Voter", "role": "player",
        "avatar_color": "#fff", "socket_id": "sv", "is_connected": True,
    }
    room_store.add_player(code, voter)

    game.apply_scores(code, rooms[code]["prompts"][0])

    p1 = next(p for p in rooms[code]["players"] if p["id"] == p1_id)
    assert p1["score"] == game.POINTS_PER_VOTE * 2


def test_advance_state_scores_to_round_intro_after_last_prompt_round_1():
    code, _ = _room_in_submitting()
    rooms[code]["state"] = "scores"
    rooms[code]["round"] = 1
    last_idx = len(rooms[code]["prompts"]) - 1
    rooms[code]["current_prompt_idx"] = last_idx
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "round_intro"
    assert rooms[code]["round"] == 2


def test_round_intro_clears_votes_and_score_deltas():
    code, player_ids = _room_in_submitting()
    rooms[code]["state"] = "scores"
    rooms[code]["round"] = 1
    last_idx = len(rooms[code]["prompts"]) - 1
    rooms[code]["current_prompt_idx"] = last_idx
    # Pre-populate votes and score_deltas on all prompts
    for p in rooms[code]["prompts"]:
        p["votes"]        = {"voter": player_ids[0]}
        p["score_deltas"] = {player_ids[0]: 1000, player_ids[1]: 0}
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    for p in rooms[code]["prompts"]:
        assert p["votes"]        == {}
        assert p["score_deltas"] == {}


def test_advance_state_round_intro_to_submitting():
    code, _ = _room_in_submitting()
    rooms[code]["state"] = "round_intro"
    rooms[code]["round"] = 2
    rooms[code]["current_prompt_idx"] = len(rooms[code]["prompts"]) - 1
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "submitting"
    assert rooms[code]["current_prompt_idx"] == 0


def test_advance_state_round_intro_assigns_new_prompts():
    code, _ = _room_in_submitting()
    old_prompt_ids = {p["prompt_id"] for p in rooms[code]["prompts"]}
    rooms[code]["state"] = "round_intro"
    rooms[code]["round"] = 2
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    new_prompt_ids = {p["prompt_id"] for p in rooms[code]["prompts"]}
    # Fresh prompts generated — none of the old IDs should remain
    assert len(new_prompt_ids) > 0
    assert new_prompt_ids.isdisjoint(old_prompt_ids)


def test_advance_state_round_intro_sets_timer_end():
    code, _ = _room_in_submitting()
    rooms[code]["state"] = "round_intro"
    rooms[code]["round"] = 2
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["timer_end"] is not None


def test_advance_state_scores_to_final_after_round_2_last_prompt():
    code, _ = _room_in_submitting()
    rooms[code]["state"] = "scores"
    rooms[code]["round"] = game.TOTAL_ROUNDS
    last_idx = len(rooms[code]["prompts"]) - 1
    rooms[code]["current_prompt_idx"] = last_idx
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "final"


def test_round_intro_timeout_constant_is_positive():
    assert game.ROUND_INTRO_TIMEOUT > 0


def test_total_rounds_constant_is_two():
    assert game.TOTAL_ROUNDS == 2


# ---------------------------------------------------------------------------
# Caption round — find_best_photo
# ---------------------------------------------------------------------------

def _make_prompt_with_votes(player_ids, votes, submissions=None):
    subs = submissions or {}
    return {
        "prompt_id":   str(uuid.uuid4()),
        "prompt_text": "Best photo",
        "player_ids":  player_ids,
        "submissions": subs,
        "votes":       votes,
    }


def test_find_best_photo_returns_most_voted_submission():
    subs = {
        "p1": {"image_url": "/img1.jpg", "caption": None},
        "p2": {"image_url": "/img2.jpg", "caption": None},
    }
    prompt = _make_prompt_with_votes(["p1", "p2"],
                                     {"v1": "p1", "v2": "p1", "v3": "p2"},
                                     subs)
    result = game.find_best_photo([prompt])
    assert result["player_id"] == "p1"
    assert result["image_url"] == "/img1.jpg"


def test_find_best_photo_returns_none_when_no_submissions():
    prompt = _make_prompt_with_votes(["p1", "p2"], {"v1": "p1"})
    result = game.find_best_photo([prompt])
    assert result is None


def test_find_best_photo_fallback_when_no_votes():
    subs = {"p1": {"image_url": "/img1.jpg", "caption": None}}
    prompt = _make_prompt_with_votes(["p1", "p2"], {}, subs)
    result = game.find_best_photo([prompt])
    assert result is not None
    assert result["image_url"] == "/img1.jpg"


def test_find_best_photo_returns_none_when_prompts_empty():
    result = game.find_best_photo([])
    assert result is None


# ---------------------------------------------------------------------------
# Caption round — create_caption_prompt
# ---------------------------------------------------------------------------

def test_create_caption_prompt_includes_all_player_ids():
    players = _make_player_dicts(3)
    best = {"player_id": "p1", "image_url": "/img.jpg", "prompt_text": "A prompt"}
    cp = game.create_caption_prompt(players, best)
    assert set(cp["player_ids"]) == {"p1", "p2", "p3"}
    assert cp["round_type"] == "caption"
    assert cp["featured_image_url"] == "/img.jpg"
    assert cp["featured_player_id"] == "p1"
    assert cp["submissions"] == {}
    assert cp["votes"] == {}


# ---------------------------------------------------------------------------
# Caption round — all_captions_submitted / all_voted (caption)
# ---------------------------------------------------------------------------

def test_all_captions_submitted_true_when_all_submitted():
    cp = {
        "player_ids":  ["p1", "p2"],
        "submissions": {"p1": {"caption": "a"}, "p2": {"caption": "b"}},
    }
    players = [{"id": "p1", "role": "player", "is_connected": True},
               {"id": "p2", "role": "player", "is_connected": True}]
    assert game.all_captions_submitted(cp, players) is True


def test_all_captions_submitted_false_when_partial():
    cp = {
        "player_ids":  ["p1", "p2"],
        "submissions": {"p1": {"caption": "a"}},
    }
    players = [{"id": "p1", "role": "player", "is_connected": True},
               {"id": "p2", "role": "player", "is_connected": True}]
    assert game.all_captions_submitted(cp, players) is False


def test_all_voted_caption_round_allows_all_players_to_vote():
    cp = {
        "round_type": "caption",
        "player_ids": ["p1", "p2", "p3"],
        "votes":      {"p1": "p2", "p2": "p1", "p3": "p1"},
    }
    players = [{"id": "p1", "role": "player"}, {"id": "p2", "role": "player"},
               {"id": "p3", "role": "player"}]
    assert game.all_voted(cp, players) is True


def test_all_voted_caption_round_false_when_some_not_voted():
    cp = {
        "round_type": "caption",
        "player_ids": ["p1", "p2", "p3"],
        "votes":      {"p1": "p2"},
    }
    players = [{"id": "p1", "role": "player"}, {"id": "p2", "role": "player"},
               {"id": "p3", "role": "player"}]
    assert game.all_voted(cp, players) is False


# ---------------------------------------------------------------------------
# Caption round — advance_state transitions
# ---------------------------------------------------------------------------

def _room_in_scores_round2_last_prompt_with_submissions():
    """Create a room in scores state on the last prompt of round 2, with image submissions."""
    code, player_ids = _room_in_submitting()
    rooms[code]["state"] = "scores"
    rooms[code]["round"] = game.TOTAL_ROUNDS
    last_idx = len(rooms[code]["prompts"]) - 1
    rooms[code]["current_prompt_idx"] = last_idx
    # Add image submissions so find_best_photo has something to work with
    for p in rooms[code]["prompts"]:
        for pid in p["player_ids"]:
            p["submissions"][pid] = {"image_url": f"/img_{pid}.jpg", "caption": None}
        if p["player_ids"]:
            p["votes"] = {"voter_x": p["player_ids"][0]}
    return code, player_ids


def test_advance_state_scores_to_caption_intro_after_round_2():
    code, _ = _room_in_scores_round2_last_prompt_with_submissions()
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "caption_intro"
    assert rooms[code]["caption_prompt"] is not None
    assert rooms[code]["caption_prompt"]["round_type"] == "caption"


def test_advance_state_scores_to_final_if_no_best_photo():
    """Falls back to final when no photo submissions exist."""
    code, _ = _room_in_submitting()
    rooms[code]["state"] = "scores"
    rooms[code]["round"] = game.TOTAL_ROUNDS
    last_idx = len(rooms[code]["prompts"]) - 1
    rooms[code]["current_prompt_idx"] = last_idx
    # No submissions — find_best_photo returns None
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "final"


def test_advance_state_caption_intro_to_captioning():
    code, _ = _room_in_submitting()
    rooms[code]["state"] = "caption_intro"
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "captioning"
    assert rooms[code]["timer_end"] is not None


def test_advance_state_captioning_to_caption_voting():
    code, _ = _room_in_submitting()
    rooms[code]["state"] = "captioning"
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "caption_voting"
    assert rooms[code]["timer_end"] is not None


def test_advance_state_caption_voting_to_caption_scores():
    code, player_ids = _room_in_submitting()
    rooms[code]["state"] = "caption_voting"
    rooms[code]["round"] = 2
    players = rooms[code]["players"]
    cp = game.create_caption_prompt(players, {
        "player_id": player_ids[0],
        "image_url":  "/img.jpg",
        "prompt_text": "test prompt",
    })
    cp["votes"] = {"voter": player_ids[0]}
    rooms[code]["caption_prompt"] = cp
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "caption_scores"
    assert rooms[code]["caption_prompt"]["score_deltas"] is not None


def test_advance_state_caption_voting_uses_double_points():
    code, player_ids = _room_in_submitting()
    rooms[code]["state"] = "caption_voting"
    rooms[code]["round"] = 2
    p1_id = player_ids[0]
    players = rooms[code]["players"]
    cp = game.create_caption_prompt(players, {
        "player_id":   p1_id,
        "image_url":   "/img.jpg",
        "prompt_text": "test prompt",
    })
    # Two votes for p1
    cp["votes"] = {"voter1": p1_id, "voter2": p1_id}
    rooms[code]["caption_prompt"] = cp
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    p1 = next(p for p in rooms[code]["players"] if p["id"] == p1_id)
    assert p1["score"] == game.POINTS_PER_VOTE * 2 * 2  # 2 votes × 2× multiplier


def test_advance_state_caption_scores_to_final():
    code, _ = _room_in_submitting()
    rooms[code]["state"] = "caption_scores"
    mock_io = _mock_socketio()
    with patch("game._start_timer", return_value=MagicMock(dead=False)):
        game.advance_state(code, mock_io)
    assert rooms[code]["state"] == "final"
    assert rooms[code]["timer_end"] is None


def test_caption_intro_timeout_constant_is_positive():
    assert game.CAPTION_INTRO_TIMEOUT > 0


def test_caption_timeout_constant_is_positive():
    assert game.CAPTION_TIMEOUT > 0


# ---------------------------------------------------------------------------
# all_captions_submitted — no-eligible-players edge case
# ---------------------------------------------------------------------------

def test_all_captions_submitted_returns_true_when_no_eligible_players():
    """If the only connected role is 'tv', there's nobody to submit → True."""
    cp = {"submissions": {}, "player_ids": []}
    tv = {"id": "tv1", "role": "tv", "is_connected": True}
    assert game.all_captions_submitted(cp, [tv]) is True


# ---------------------------------------------------------------------------
# all_voted — caption round, no eligible players
# ---------------------------------------------------------------------------

def test_all_voted_caption_round_returns_true_when_no_eligible_players():
    """Caption round with only tv connected → eligible list empty → True."""
    prompt = {"round_type": "caption", "votes": {}, "player_ids": []}
    tv = {"id": "tv1", "role": "tv", "is_connected": True}
    assert game.all_voted(prompt, [tv]) is True


# ---------------------------------------------------------------------------
# advance_state — room not found
# ---------------------------------------------------------------------------

def test_advance_state_returns_early_when_room_not_found():
    """advance_state must not crash and must not emit when the room is gone."""
    mock_io = MagicMock()
    game.advance_state("ZZZZ", mock_io)   # room does not exist
    mock_io.emit.assert_not_called()


# ---------------------------------------------------------------------------
# _start_timer — greenlet body
# ---------------------------------------------------------------------------

def test_start_timer_calls_callback_after_delay():
    """The greenlet spawned by _start_timer must invoke the callback."""
    called = []
    code, _ = _room_with_n_players(2)
    gl = game._start_timer(code, 0.01, lambda: called.append(True), MagicMock())
    gl.join(timeout=2.0)
    assert called, "callback was never invoked"


def test_start_timer_clears_greenlet_ref_on_room():
    """After the sleep fires, timer_greenlet on the room must be set to None."""
    code, _ = _room_with_n_players(2)
    rooms[code]["timer_greenlet"] = "sentinel"
    gl = game._start_timer(code, 0.01, lambda: None, MagicMock())
    gl.join(timeout=2.0)
    assert rooms[code]["timer_greenlet"] is None
