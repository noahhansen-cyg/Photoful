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


def test_add_player_returns_false_for_unknown_room():
    assert room_store.add_player("XXXX", _make_player()) is False


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
