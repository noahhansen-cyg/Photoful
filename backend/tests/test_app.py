import pytest
import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from PIL import Image as PILImage
from app import app
import app as app_module
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


# ---------------------------------------------------------------------------
# POST /api/rooms/<code>/upload
# ---------------------------------------------------------------------------

def _jpeg_bytes():
    """Return a minimal in-memory JPEG as BytesIO."""
    img = PILImage.new("RGB", (100, 100), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    buf.seek(0)
    return buf


def _room_in_submitting(client):
    """Create a room and force its state to 'submitting'; return the code."""
    code = client.post("/api/rooms").get_json()["room_code"]
    rooms[code]["state"] = "submitting"
    return code


def test_upload_returns_201_with_image_url(client):
    code = _room_in_submitting(client)
    data = {"photo": (io.BytesIO(_jpeg_bytes().read()), "photo.jpg")}
    response = client.post(
        f"/api/rooms/{code}/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    assert "image_url" in response.get_json()


def test_upload_image_url_contains_room_code(client):
    code = _room_in_submitting(client)
    buf = _jpeg_bytes()
    response = client.post(
        f"/api/rooms/{code}/upload",
        data={"photo": (buf, "photo.jpg")},
        content_type="multipart/form-data",
    )
    url = response.get_json()["image_url"]
    assert code in url


def test_upload_returns_404_for_unknown_room(client):
    buf = _jpeg_bytes()
    response = client.post(
        "/api/rooms/ZZZZ/upload",
        data={"photo": (buf, "photo.jpg")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 404


def test_upload_returns_400_when_not_submitting(client):
    code = client.post("/api/rooms").get_json()["room_code"]
    # state remains "lobby"
    buf = _jpeg_bytes()
    response = client.post(
        f"/api/rooms/{code}/upload",
        data={"photo": (buf, "photo.jpg")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_upload_returns_400_when_no_photo_field(client):
    code = _room_in_submitting(client)
    response = client.post(
        f"/api/rooms/{code}/upload",
        data={},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_upload_is_case_insensitive_for_room_code(client):
    code = _room_in_submitting(client)
    buf = _jpeg_bytes()
    response = client.post(
        f"/api/rooms/{code.lower()}/upload",
        data={"photo": (buf, "photo.jpg")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# GET /api/server-info
# ---------------------------------------------------------------------------

def test_server_info_returns_200(client):
    response = client.get("/api/server-info")
    assert response.status_code == 200


def test_server_info_returns_local_ip(client):
    response = client.get("/api/server-info")
    data = response.get_json()
    assert "local_ip" in data
    # Should be a non-empty string (either a real IP or the "localhost" fallback)
    assert isinstance(data["local_ip"], str)
    assert len(data["local_ip"]) > 0


# ---------------------------------------------------------------------------
# GET /healthz
# ---------------------------------------------------------------------------

def test_healthz_returns_200(client):
    response = client.get("/healthz")
    assert response.status_code == 200


def test_healthz_body_is_ok(client):
    response = client.get("/healthz")
    assert response.data == b"ok"


# ---------------------------------------------------------------------------
# Packaging helpers — dev-mode behaviour
# ---------------------------------------------------------------------------

def test_not_frozen_in_dev():
    """In a normal Python process (not a PyInstaller bundle) _FROZEN must be False."""
    assert app_module._FROZEN is False


def test_async_mode_is_gevent_in_dev():
    """Dev mode must use gevent so the existing make-dev workflow is unchanged."""
    assert app_module.ASYNC_MODE == "gevent"


def test_frontend_dist_is_none_in_dev():
    """_FRONTEND_DIST must be None outside a frozen bundle (SPA route not registered)."""
    assert app_module._FRONTEND_DIST is None


def test_upload_dir_exists():
    """UPLOADS_DIR must exist as a directory immediately after module import."""
    assert os.path.isdir(app_module.UPLOADS_DIR)
