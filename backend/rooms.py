import random
import string

# In-memory store: { room_code: { players: [], state: str, host_id: str|None } }
rooms = {}


def generate_room_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase, k=4))
        if code not in rooms:
            return code


def create_room():
    code = generate_room_code()
    rooms[code] = {
        "code": code,
        "state": "lobby",
        "host_id": None,
        "players": [],
    }
    return rooms[code]


def get_room(code):
    return rooms.get(code)


def add_player(code, player):
    """Add or re-connect a player. player = { id, socket_id, name, role, avatar_color, score }"""
    room = rooms.get(code)
    if not room:
        return False

    # Re-connection: update socket_id if player name already exists
    for existing in room["players"]:
        if existing["name"] == player["name"] and existing["role"] == player["role"]:
            existing["socket_id"] = player["socket_id"]
            existing["is_connected"] = True
            return True

    room["players"].append({**player, "is_connected": True, "score": 0})
    return True


def remove_player(socket_id):
    """Mark a player as disconnected by socket_id. Returns (room_code, player) or (None, None)."""
    for code, room in rooms.items():
        for player in room["players"]:
            if player["socket_id"] == socket_id:
                player["is_connected"] = False
                return code, player
    return None, None


def get_room_state(code):
    room = rooms.get(code)
    if not room:
        return None
    return {
        "room_code": code,
        "state": room["state"],
        "players": [p for p in room["players"] if p["is_connected"]],
    }
