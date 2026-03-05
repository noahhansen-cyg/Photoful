import random
import string

# In-memory store: { room_code: room_dict }
rooms = {}


def generate_room_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase, k=4))
        if code not in rooms:
            return code


def create_room():
    code = generate_room_code()
    rooms[code] = {
        "code":               code,
        "state":              "lobby",
        "host_id":            None,
        "players":            [],
        # Game round data
        "round":              1,    # current voting round (1-indexed)
        "prompts":            [],   # list of PromptAssignment dicts
        "current_prompt_idx": 0,
        "timer_end":          None, # unix timestamp (float) when current timer expires
        "timer_greenlet":     None, # gevent greenlet handle for cancellation
    }
    return rooms[code]


def get_room(code):
    return rooms.get(code)


def add_player(code, player):
    """
    Add or reconnect a player.
    Returns True if newly added, False if reconnected, None if room not found.
    """
    room = rooms.get(code)
    if not room:
        return None

    # Reconnection: same name + role → update socket_id
    for existing in room["players"]:
        if existing["name"] == player["name"] and existing["role"] == player["role"]:
            existing["socket_id"]    = player["socket_id"]
            existing["is_connected"] = True
            return False  # reconnected

    room["players"].append({**player, "is_connected": True, "score": 0})
    return True  # newly added


def remove_player(socket_id):
    """Mark a player as disconnected. Returns (room_code, player) or (None, None)."""
    for code, room in rooms.items():
        for player in room["players"]:
            if player["socket_id"] == socket_id:
                player["is_connected"] = False
                return code, player
    return None, None


def add_submission(code, prompt_id, player_id, image_url, caption=None):
    """Record a photo submission. Returns True on success, False if invalid."""
    room = rooms.get(code)
    if not room or room["state"] != "submitting":
        return False
    prompt = _find_prompt(room, prompt_id)
    if not prompt or player_id not in prompt["player_ids"]:
        return False
    prompt["submissions"][player_id] = {"image_url": image_url, "caption": caption}
    return True


def add_vote(code, prompt_id, voter_id, voted_for_id):
    """Record a vote. Returns True on success, False if invalid."""
    room = rooms.get(code)
    if not room or room["state"] != "voting":
        return False
    prompt = _find_prompt(room, prompt_id)
    if not prompt:
        return False
    if voter_id in prompt["player_ids"]:   # can't vote in your own matchup
        return False
    if voter_id in prompt["votes"]:        # can't vote twice
        return False
    if voted_for_id not in prompt["player_ids"]:
        return False
    prompt["votes"][voter_id] = voted_for_id
    return True


def get_current_prompt(code):
    room = rooms.get(code)
    if not room:
        return None
    idx = room["current_prompt_idx"]
    if not room["prompts"] or idx >= len(room["prompts"]):
        return None
    return room["prompts"][idx]


def get_room_state(code):
    room = rooms.get(code)
    if not room:
        return None

    connected_players = [
        {
            "id":           p["id"],
            "name":         p["name"],
            "score":        p.get("score", 0),
            "avatar_color": p["avatar_color"],
            "role":         p["role"],
        }
        for p in room["players"] if p["is_connected"]
    ]

    prompt = get_current_prompt(code)
    total  = len(room["prompts"])
    idx    = room["current_prompt_idx"]

    return {
        "room_code":      code,
        "state":          room["state"],
        "round":          room.get("round", 1),
        "players":        connected_players,
        "prompts":        room["prompts"],    # all prompts (used during submitting phase)
        "current_prompt": prompt,             # the active prompt for voting/scores
        "timer_end":      room.get("timer_end"),
        "prompt_number":  idx + 1 if total else 0,
        "total_prompts":  total,
    }


def reset_room(code):
    """
    Reset a finished room back to lobby so the same players can play again.
    Scores are zeroed; players, roles, and host assignment are preserved.
    """
    room = rooms.get(code)
    if not room:
        return False
    room["state"]               = "lobby"
    room["round"]               = 1
    room["prompts"]             = []
    room["current_prompt_idx"]  = 0
    room["timer_end"]           = None
    room["timer_greenlet"]      = None
    for p in room["players"]:
        p["score"] = 0
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_prompt(room, prompt_id):
    for p in room["prompts"]:
        if p["prompt_id"] == prompt_id:
            return p
    return None
