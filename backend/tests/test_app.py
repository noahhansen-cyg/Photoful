import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app
from rooms import rooms


@pytest.fixture(autouse=True)
def clear_rooms():
    rooms.clear()
    yield
    rooms.clear()


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# POST /api/rooms
# ---------------------------------------------------------------------------

def test_create_room_returns_201(client):
    response = client.post("/api/rooms")
    assert response.status_code == 201


def test_create_room_returns_json_with_room_code(client):
    response = client.post("/api/rooms")
    data = response.get_json()
    assert "room_code" in data


def test_create_room_code_is_4_uppercase_letters(client):
    response = client.post("/api/rooms")
    code = response.get_json()["room_code"]
    assert len(code) == 4
    assert code.isupper()
    assert code.isalpha()


def test_create_room_each_call_returns_unique_code(client):
    codes = [client.post("/api/rooms").get_json()["room_code"] for _ in range(10)]
    assert len(set(codes)) == 10


def test_create_room_stores_room_in_memory(client):
    response = client.post("/api/rooms")
    code = response.get_json()["room_code"]
    assert code in rooms


# ---------------------------------------------------------------------------
# GET /api/rooms/<code>
# ---------------------------------------------------------------------------

def test_check_room_returns_exists_true_for_valid_room(client):
    code = client.post("/api/rooms").get_json()["room_code"]
    response = client.get(f"/api/rooms/{code}")
    assert response.get_json() == {"exists": True}


def test_check_room_returns_exists_false_for_unknown_code(client):
    response = client.get("/api/rooms/ZZZZ")
    assert response.get_json() == {"exists": False}


def test_check_room_is_case_insensitive(client):
    code = client.post("/api/rooms").get_json()["room_code"]
    response = client.get(f"/api/rooms/{code.lower()}")
    assert response.get_json()["exists"] is True


def test_check_room_returns_200(client):
    response = client.get("/api/rooms/ZZZZ")
    assert response.status_code == 200
