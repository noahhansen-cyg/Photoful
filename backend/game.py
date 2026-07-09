"""
game.py — Pure game logic: prompt assignment, state transitions, scoring.
No Flask/SocketIO imports here so everything is easily unit-testable.
"""

import json
import math
import random
import threading
import uuid
import time
import os

import rooms as room_store

# Serializes state transitions so a timer firing can never race an
# "everyone acted early" advance coming from a socket handler.
_lock = threading.RLock()

PROMPTS_PATH = os.path.join(os.path.dirname(__file__), "prompts.json")

# PHOTOFUL_TIMER_SCALE multiplies every phase duration. Defaults to 1 (real
# timings). The binary E2E suite sets it well below 1 so a full game — with its
# fixed intro/scores screens — finishes in seconds instead of minutes.
_TIMER_SCALE = float(os.environ.get("PHOTOFUL_TIMER_SCALE", "1"))

SUBMIT_TIMEOUT = 120 * _TIMER_SCALE  # seconds players have to submit photos for ALL their prompts
VOTE_TIMEOUT   = 30 * _TIMER_SCALE   # seconds players have to vote
SCORES_TIMEOUT = 5 * _TIMER_SCALE    # seconds scores screen is shown before advancing

POINTS_PER_VOTE       = 1000
PROMPTS_PER_PLAYER    = 2
VOTING_INTRO_TIMEOUT  = 5 * _TIMER_SCALE   # seconds the "Round N — Let's Vote!" screen is shown before voting
ROUND_INTRO_TIMEOUT   = 7 * _TIMER_SCALE   # seconds the "Round N!" screen is shown before next submitting phase
TOTAL_ROUNDS          = 2   # total number of photo voting rounds
CAPTION_INTRO_TIMEOUT = 7 * _TIMER_SCALE   # seconds showing featured photo before captioning
CAPTION_TIMEOUT       = 60 * _TIMER_SCALE  # seconds to submit text captions
EXTEND_AMOUNT         = 30 * _TIMER_SCALE  # seconds added to the submission timer per host extension


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


def find_best_photo(prompts):
    """
    Return {"player_id": ..., "image_url": ..., "prompt_text": ...} for the
    submission that received the most votes across the given prompts.
    Ties are broken randomly. Falls back to the first submission found when
    no votes were cast. Returns None if there are no submissions at all.
    """
    vote_counts = {}  # {player_id: [count, image_url, prompt_text]}
    for prompt in prompts:
        for voted_for_id in prompt["votes"].values():
            sub = prompt["submissions"].get(voted_for_id)
            if sub and sub.get("image_url"):
                if voted_for_id not in vote_counts:
                    vote_counts[voted_for_id] = [0, sub["image_url"], prompt["prompt_text"]]
                vote_counts[voted_for_id][0] += 1

    if vote_counts:
        max_votes = max(v[0] for v in vote_counts.values())
        winners   = [pid for pid, v in vote_counts.items() if v[0] == max_votes]
        winner_id = random.choice(winners)
        _, image_url, prompt_text = vote_counts[winner_id]
        return {"player_id": winner_id, "image_url": image_url, "prompt_text": prompt_text}

    # Fallback: return first submission found
    for prompt in prompts:
        for pid, sub in prompt["submissions"].items():
            if sub.get("image_url"):
                return {
                    "player_id":   pid,
                    "image_url":   sub["image_url"],
                    "prompt_text": prompt["prompt_text"],
                }
    return None


def create_caption_prompt(players, best_photo):
    """Create a single caption-round prompt for the featured photo."""
    return {
        "prompt_id":            str(uuid.uuid4()),
        "round_type":           "caption",
        "featured_image_url":   best_photo["image_url"],
        "featured_player_id":   best_photo["player_id"],
        "featured_prompt_text": best_photo["prompt_text"],
        "player_ids":           [p["id"] for p in players],
        "submissions":          {},
        "votes":                {},
        "score_deltas":         {},
    }


def all_submitted(prompt):
    """True when every assigned player has a submission for this prompt."""
    return all(pid in prompt["submissions"] for pid in prompt["player_ids"])


def all_prompts_submitted(prompts):
    """True when every assigned player has submitted for every prompt."""
    return all(all_submitted(p) for p in prompts)


def all_captions_submitted(caption_prompt, connected_players):
    """True when all connected player/host roles assigned to this prompt have submitted."""
    assigned = set(caption_prompt["player_ids"])
    eligible = [p for p in connected_players
                if p["role"] in ("player", "host") and p["id"] in assigned]
    if not eligible:
        return True
    return all(p["id"] in caption_prompt["submissions"] for p in eligible)


def all_voted(prompt, connected_players):
    """
    True when every connected, non-competing player has cast a vote.
    For caption-round prompts everyone is eligible (just can't vote for themselves).
    """
    if prompt.get("round_type") == "caption":
        eligible = [p for p in connected_players if p["role"] in ("player", "host")]
        if not eligible:
            return True
        return all(p["id"] in prompt["votes"] for p in eligible)

    competing = set(prompt["player_ids"])
    eligible = [p for p in connected_players
                if p["id"] not in competing and p["role"] in ("player", "host")]
    if not eligible:
        return True
    return all(p["id"] in prompt["votes"] for p in eligible)


def tally_scores(prompt, points_per_vote=POINTS_PER_VOTE):
    """Return {player_id: points_earned} for this prompt."""
    vote_counts = {}
    for pid in prompt["player_ids"]:
        vote_counts[pid] = 0
    for voted_for in prompt["votes"].values():
        if voted_for in vote_counts:
            vote_counts[voted_for] += points_per_vote
    return vote_counts


def apply_scores(room_code, prompt):
    """Add vote-based points to player scores in the room."""
    room = room_store.get_room(room_code)
    pts  = POINTS_PER_VOTE * room.get("round", 1) if room else POINTS_PER_VOTE
    deltas = tally_scores(prompt, pts)
    if not room:
        return deltas
    for player in room["players"]:
        player["score"] = player.get("score", 0) + deltas.get(player["id"], 0)
    return deltas


def advance_now(room_code, socketio, expected_state=None):
    """
    Cancel the running timer and advance immediately, as one atomic step.
    Called from socket handlers when all players have acted early.

    expected_state (a state name or tuple of names) guards against concurrent
    handlers double-advancing: when the last two players act at the same time,
    both handlers can see the phase as complete, but only the first one finds
    the room still in an expected state — the second becomes a no-op.
    """
    if isinstance(expected_state, str):
        expected_state = (expected_state,)
    with _lock:
        room = room_store.get_room(room_code)
        if not room:
            return
        if expected_state is not None and room["state"] not in expected_state:
            return
        cancel_timer(room)
        advance_state(room_code, socketio)


def advance_state(room_code, socketio):
    """
    Move the room to the next state in the game loop and broadcast game:state.
    Called when a timer fires or all players have acted early.
    """
    with _lock:
        _advance_state(room_code, socketio)


def _advance_state(room_code, socketio):
    room = room_store.get_room(room_code)
    if not room:
        return

    state  = room["state"]
    idx    = room["current_prompt_idx"]
    total  = len(room["prompts"])
    prompt = room["prompts"][idx] if idx < total else None

    if state == "submitting":
        # All prompts submitted — show a brief "Round N" intro before voting starts.
        room["current_prompt_idx"] = 0
        room["state"]    = "voting_intro"
        room["timer_end"] = time.time() + VOTING_INTRO_TIMEOUT
        room["timer"] = _start_timer(
            room_code, VOTING_INTRO_TIMEOUT, lambda: advance_state(room_code, socketio), socketio
        )

    elif state == "voting_intro":
        room["state"]    = "voting"
        room["timer_end"] = time.time() + VOTE_TIMEOUT
        room["timer"] = _start_timer(
            room_code, VOTE_TIMEOUT, lambda: advance_state(room_code, socketio), socketio
        )

    elif state == "voting":
        if prompt:
            score_deltas = apply_scores(room_code, prompt)
            prompt["score_deltas"] = score_deltas
        room["state"]    = "scores"
        room["timer_end"] = time.time() + SCORES_TIMEOUT
        room["timer"] = _start_timer(
            room_code, SCORES_TIMEOUT, lambda: advance_state(room_code, socketio), socketio
        )

    elif state == "scores":
        next_idx = idx + 1
        if next_idx < total:
            # Move to the next prompt's voting round (no second submitting phase).
            room["current_prompt_idx"] = next_idx
            room["state"]    = "voting"
            room["timer_end"] = time.time() + VOTE_TIMEOUT
            room["timer"] = _start_timer(
                room_code, VOTE_TIMEOUT, lambda: advance_state(room_code, socketio), socketio
            )
        elif room.get("round", 1) < TOTAL_ROUNDS:
            # End of a round — more rounds remain; clear votes, bump round, show intro.
            room["round"] = room.get("round", 1) + 1
            for p in room["prompts"]:
                p["votes"]        = {}
                p["score_deltas"] = {}
            room["state"]    = "round_intro"
            room["timer_end"] = time.time() + ROUND_INTRO_TIMEOUT
            room["timer"] = _start_timer(
                room_code, ROUND_INTRO_TIMEOUT, lambda: advance_state(room_code, socketio), socketio
            )
        else:
            # All photo rounds done — start the caption round.
            players = [p for p in room["players"]
                       if p["is_connected"] and p["role"] in ("player", "host")]
            best = find_best_photo(room["prompts"])
            if best and len(players) >= 2:
                room["caption_prompt"] = create_caption_prompt(players, best)
                room["state"]    = "caption_intro"
                room["timer_end"] = time.time() + CAPTION_INTRO_TIMEOUT
                room["timer"] = _start_timer(
                    room_code, CAPTION_INTRO_TIMEOUT, lambda: advance_state(room_code, socketio), socketio
                )
            else:
                room["state"]    = "final"
                room["timer_end"] = None

    elif state == "round_intro":
        # Intro timer fired — assign fresh prompts and start a new submission phase.
        players = [p for p in room["players"]
                   if p["is_connected"] and p["role"] in ("player", "host")]
        room["prompts"]            = assign_prompts(players)
        room["current_prompt_idx"] = 0
        room["state"]    = "submitting"
        room["timer_end"] = time.time() + SUBMIT_TIMEOUT
        room["timer"] = _start_timer(
            room_code, SUBMIT_TIMEOUT, lambda: advance_state(room_code, socketio), socketio
        )

    elif state == "caption_intro":
        room["state"]    = "captioning"
        room["timer_end"] = time.time() + CAPTION_TIMEOUT
        room["timer"] = _start_timer(
            room_code, CAPTION_TIMEOUT, lambda: advance_state(room_code, socketio), socketio
        )

    elif state == "captioning":
        room["state"]    = "caption_voting"
        room["timer_end"] = time.time() + VOTE_TIMEOUT
        room["timer"] = _start_timer(
            room_code, VOTE_TIMEOUT, lambda: advance_state(room_code, socketio), socketio
        )

    elif state == "caption_voting":
        cp = room.get("caption_prompt")
        if cp:
            pts    = POINTS_PER_VOTE * room.get("round", 1)
            deltas = tally_scores(cp, pts)
            cp["score_deltas"] = deltas
            for player in room["players"]:
                player["score"] = player.get("score", 0) + deltas.get(player["id"], 0)
        room["state"]    = "caption_scores"
        room["timer_end"] = time.time() + SCORES_TIMEOUT
        room["timer"] = _start_timer(
            room_code, SCORES_TIMEOUT, lambda: advance_state(room_code, socketio), socketio
        )

    elif state == "caption_scores":
        room["state"]    = "final"
        room["timer_end"] = None

    socketio.emit("game:state", room_store.get_room_state(room_code), to=room_code)


def start_game(room_code, socketio):
    """Called when the host fires host:start. Assigns prompts and begins round."""
    with _lock:
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
        room["timer"]               = _start_timer(
            room_code, SUBMIT_TIMEOUT, lambda: advance_state(room_code, socketio), socketio
        )

        socketio.emit("game:state", room_store.get_room_state(room_code), to=room_code)
        return True


def extend_timer(room_code, socketio):
    """
    Add EXTEND_AMOUNT seconds to the running submission timer.
    Only valid during the 'submitting' state.  Returns True on success.
    """
    with _lock:
        room = room_store.get_room(room_code)
        if not room or room["state"] != "submitting":
            return False
        cancel_timer(room)
        remaining  = max(0.0, (room.get("timer_end") or 0.0) - time.time())
        new_delay  = remaining + EXTEND_AMOUNT
        room["timer_end"] = time.time() + new_delay
        room["timer"]     = _start_timer(
            room_code, new_delay, lambda: advance_state(room_code, socketio), socketio
        )
        socketio.emit("game:state", room_store.get_room_state(room_code), to=room_code)
        return True


def cancel_timer(room):
    """Cancel the running phase timer if one exists."""
    with _lock:
        timer = room.get("timer")
        if timer:
            timer.cancel()
        room["timer"] = None


# ---------------------------------------------------------------------------
# Phase timer — plain threading.Timer so the exact same code runs in dev
# and in the packaged binary.
# ---------------------------------------------------------------------------

def _start_timer(room_code, seconds, callback, socketio):
    timer = None

    def _fire():
        with _lock:
            room = room_store.get_room(room_code)
            # A cancel() can lose the race with an already-firing Timer, so
            # only proceed if we are still the room's active timer.
            if not room or room.get("timer") is not timer:
                return
            room["timer"] = None
            callback()

    with _lock:
        room = room_store.get_room(room_code)
        timer = threading.Timer(seconds, _fire)
        timer.daemon = True
        if room is not None:
            room["timer"] = timer
        timer.start()
    return timer
