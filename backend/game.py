"""
game.py — Pure game logic: prompt assignment, state transitions, scoring.
No Flask/SocketIO imports here so everything is easily unit-testable.
"""

import json
import math
import random
import uuid
import time
import os

import rooms as room_store

PROMPTS_PATH = os.path.join(os.path.dirname(__file__), "prompts.json")
SUBMIT_TIMEOUT = 90   # seconds players have to submit photos for ALL their prompts
VOTE_TIMEOUT   = 30   # seconds players have to vote
SCORES_TIMEOUT = 10   # seconds scores screen is shown before advancing

POINTS_PER_VOTE = 1000
PROMPTS_PER_PLAYER = 3


def load_prompts():
    with open(PROMPTS_PATH) as f:
        return json.load(f)


def _make_pairs(n):
    """
    Return a list of (i, j) index pairs so each index 0..n-1 appears in
    exactly PROMPTS_PER_PLAYER pairs.  For odd n, one index will appear in
    PROMPTS_PER_PLAYER+1 pairs (unavoidable — total slot count is odd).

    Runs exactly ceil(n * PROMPTS_PER_PLAYER / 2) iterations, always pairing
    the two players with the highest remaining need so no one is left short.
    Ties are shuffled for opponent variety.
    """
    if n < 2:
        return []

    total = math.ceil(n * PROMPTS_PER_PLAYER / 2)
    needs = [PROMPTS_PER_PLAYER] * n
    pairs = []

    for _ in range(total):
        order    = sorted(range(n), key=lambda i: needs[i], reverse=True)
        top_need = needs[order[0]]
        top  = [i for i in order if needs[i] == top_need]
        rest = [i for i in order if needs[i] < top_need]
        random.shuffle(top)

        if len(top) >= 2:
            i, j = top[0], top[1]
        else:
            i, j = top[0], rest[0]

        pairs.append((i, j))
        needs[i] -= 1
        needs[j] -= 1

    return pairs


def assign_prompts(players):
    """
    Given a list of player dicts, return a list of PromptAssignment dicts.
    Each prompt is assigned to exactly 2 players.  Every player appears in
    exactly PROMPTS_PER_PLAYER prompts (one player may get PROMPTS_PER_PLAYER+1
    when the player count is odd).
    """
    shuffled = players[:]
    random.shuffle(shuffled)

    pairs        = _make_pairs(len(shuffled))
    prompt_texts = random.sample(load_prompts(), len(pairs))

    return [
        {
            "prompt_id":   str(uuid.uuid4()),
            "prompt_text": text,
            "player_ids":  [shuffled[i]["id"], shuffled[j]["id"]],
            "submissions": {},
            "votes":       {},
        }
        for (i, j), text in zip(pairs, prompt_texts)
    ]


def all_submitted(prompt):
    """True when every assigned player has a submission for this prompt."""
    return all(pid in prompt["submissions"] for pid in prompt["player_ids"])


def all_prompts_submitted(prompts):
    """True when every assigned player has submitted for every prompt."""
    return all(all_submitted(p) for p in prompts)


def all_voted(prompt, connected_players):
    """
    True when every connected, non-competing player has cast a vote.
    Competing players don't vote on their own matchup.
    """
    competing = set(prompt["player_ids"])
    eligible = [p for p in connected_players
                if p["id"] not in competing and p["role"] in ("player", "host")]
    if not eligible:
        return True
    return all(p["id"] in prompt["votes"] for p in eligible)


def tally_scores(prompt):
    """Return {player_id: points_earned} for this prompt."""
    vote_counts = {}
    for pid in prompt["player_ids"]:
        vote_counts[pid] = 0
    for voted_for in prompt["votes"].values():
        if voted_for in vote_counts:
            vote_counts[voted_for] += POINTS_PER_VOTE
    return vote_counts


def apply_scores(room_code, prompt):
    """Add vote-based points to player scores in the room."""
    deltas = tally_scores(prompt)
    room = room_store.get_room(room_code)
    if not room:
        return deltas
    for player in room["players"]:
        player["score"] = player.get("score", 0) + deltas.get(player["id"], 0)
    return deltas


def advance_state(room_code, socketio):
    """
    Move the room to the next state in the game loop and broadcast game:state.
    Called when a timer fires or all players have acted early.
    """
    room = room_store.get_room(room_code)
    if not room:
        return

    state  = room["state"]
    idx    = room["current_prompt_idx"]
    total  = len(room["prompts"])
    prompt = room["prompts"][idx] if idx < total else None

    if state == "submitting":
        # All prompts were submitted simultaneously; start voting from the first prompt.
        room["current_prompt_idx"] = 0
        room["state"]    = "voting"
        room["timer_end"] = time.time() + VOTE_TIMEOUT
        room["timer_greenlet"] = _start_timer(
            room_code, VOTE_TIMEOUT, lambda: advance_state(room_code, socketio), socketio
        )

    elif state == "voting":
        if prompt:
            score_deltas = apply_scores(room_code, prompt)
            prompt["score_deltas"] = score_deltas
        room["state"]    = "scores"
        room["timer_end"] = time.time() + SCORES_TIMEOUT
        room["timer_greenlet"] = _start_timer(
            room_code, SCORES_TIMEOUT, lambda: advance_state(room_code, socketio), socketio
        )

    elif state == "scores":
        next_idx = idx + 1
        if next_idx < total:
            # Move to the next prompt's voting round (no second submitting phase).
            room["current_prompt_idx"] = next_idx
            room["state"]    = "voting"
            room["timer_end"] = time.time() + VOTE_TIMEOUT
            room["timer_greenlet"] = _start_timer(
                room_code, VOTE_TIMEOUT, lambda: advance_state(room_code, socketio), socketio
            )
        else:
            room["state"]    = "final"
            room["timer_end"] = None

    socketio.emit("game:state", room_store.get_room_state(room_code), to=room_code)


def start_game(room_code, socketio):
    """Called when the host fires host:start. Assigns prompts and begins round."""
    room = room_store.get_room(room_code)
    if not room:
        return False

    players = [p for p in room["players"]
               if p["is_connected"] and p["role"] in ("player", "host")]
    if len(players) < 2:
        return False

    room["prompts"]             = assign_prompts(players)
    room["current_prompt_idx"]  = 0
    room["state"]               = "submitting"
    room["timer_end"]           = time.time() + SUBMIT_TIMEOUT
    room["timer_greenlet"]      = _start_timer(
        room_code, SUBMIT_TIMEOUT, lambda: advance_state(room_code, socketio), socketio
    )

    socketio.emit("game:state", room_store.get_room_state(room_code), to=room_code)
    return True


def cancel_timer(room):
    """Kill the running timer greenlet if one exists."""
    gl = room.get("timer_greenlet")
    if gl and not gl.dead:
        gl.kill()
    room["timer_greenlet"] = None


# ---------------------------------------------------------------------------
# Internal helper — imported here to avoid circular import at module level
# ---------------------------------------------------------------------------

def _start_timer(room_code, seconds, callback, socketio):
    import gevent

    def _run():
        gevent.sleep(seconds)
        room = room_store.get_room(room_code)
        if room:
            room["timer_greenlet"] = None
        callback()

    return gevent.spawn(_run)
