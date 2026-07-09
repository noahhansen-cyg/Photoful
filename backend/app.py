import sys
import os

_FROZEN = getattr(sys, "frozen", False)

import uuid
import random
import logging
import socket
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room
from PIL import Image
import rooms as room_store
import game

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")

# One async mode everywhere — dev and the packaged binary both run threading
# mode with real WebSocket support via simple-websocket, so the desktop build
# is byte-for-byte identical to what runs in development.
# cors_allowed_origins="*" stays: in dev the Vite proxy forwards the socket.io
# handshake with an Origin (:5173) that differs from the backend's Host.
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

PORT = int(os.environ.get("PORT", "5000"))


def _get_upload_dir():
    """Return a writable uploads directory.

    In a PyInstaller bundle sys._MEIPASS is read-only, so we use a
    platform-appropriate user-data directory instead.
    """
    if _FROZEN:
        if sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support/Photoful")
        elif sys.platform == "win32":
            base = os.path.join(os.environ.get("APPDATA", "~"), "Photoful")
        else:
            base = os.path.expanduser("~/.photoful")
        d = os.path.join(base, "uploads")
    else:
        d = os.path.join(os.path.dirname(__file__), "uploads")
    os.makedirs(d, exist_ok=True)
    return d


UPLOADS_DIR = _get_upload_dir()


def _get_frontend_dist():
    """Return the path to the built React app, or None if it isn't built.

    The same SPA-serving code path runs everywhere: the PyInstaller bundle
    ships it under sys._MEIPASS, while an unfrozen server uses ../frontend/dist
    when a build exists (in dev you normally use the Vite server on :5173).
    """
    if _FROZEN:
        return os.path.join(sys._MEIPASS, "frontend_dist")
    local = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
    )
    if os.path.exists(os.path.join(local, "index.html")):
        return local
    return None


_FRONTEND_DIST = _get_frontend_dist()

AVATAR_COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4",
    "#FFEAA7", "#DDA0DD", "#98D8C8", "#F7DC6F",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_local_ip():
    """Return the machine's LAN IP (the interface used to reach the internet)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


# ---------------------------------------------------------------------------
# REST routes
# ---------------------------------------------------------------------------

@app.route("/api/server-info")
def server_info():
    return jsonify({"local_ip": get_local_ip()})


@app.route("/api/rooms", methods=["POST"])
def create_room():
    room = room_store.create_room()
    log.info("room=%-4s event=room_created", room["code"])
    return jsonify({"room_code": room["code"]}), 201


@app.route("/api/rooms/<code>", methods=["GET"])
def check_room(code):
    code = code.upper()
    room = room_store.get_room(code)
    exists = room is not None
    log.info("room=%-4s event=room_check exists=%s", code, exists)
    return jsonify({"exists": exists})


@app.route("/api/rooms/<code>/upload", methods=["POST"])
def upload_photo(code):
    code = code.upper()
    room = room_store.get_room(code)
    if not room:
        return jsonify({"error": "Room not found"}), 404
    if room["state"] not in ("submitting", "voting_intro"):
        return jsonify({"error": "Not in submission phase"}), 400
    if "photo" not in request.files:
        return jsonify({"error": "No photo in request"}), 400

    file = request.files["photo"]
    filename = f"{uuid.uuid4()}.jpg"
    room_dir = os.path.join(UPLOADS_DIR, code)
    os.makedirs(room_dir, exist_ok=True)
    dest = os.path.join(room_dir, filename)

    img = Image.open(file.stream).convert("RGB")
    img.thumbnail((1280, 1280), Image.LANCZOS)
    img.save(dest, "JPEG", quality=80)

    image_url = f"/uploads/{code}/{filename}"
    log.info("room=%-4s event=photo_upload file=%s", code, filename)
    return jsonify({"image_url": image_url}), 201


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOADS_DIR, filename)


@app.route("/healthz")
def healthz():
    """Liveness probe — Electron polls this before opening the BrowserWindow."""
    return "ok", 200


# ---------------------------------------------------------------------------
# SocketIO events
# ---------------------------------------------------------------------------

@socketio.on("player:join")
def handle_join(data):
    code = data.get("room_code", "").upper()
    name = data.get("name", "TV")
    role = data.get("role", "player")   # "tv" | "player" | "host"
    sid  = request.sid[:8]

    room = room_store.get_room(code)
    if not room:
        log.warning("room=%-4s event=player:join error=room_not_found name=%s sid=%s", code, name, sid)
        emit("error", {"message": f"Room {code} not found"})
        return

    # Enforce single host
    if role == "host" and room["host_id"] is not None:
        existing_host = next(
            (p for p in room["players"] if p["role"] == "host" and p["name"] == name), None
        )
        if not existing_host:
            log.warning("room=%-4s event=player:join error=host_taken name=%s", code, name)
            emit("error", {"message": "A host has already joined this room"})
            return

    player = {
        "id":           str(uuid.uuid4()),
        "socket_id":    request.sid,
        "name":         name,
        "role":         role,
        "avatar_color": random.choice(AVATAR_COLORS),
    }

    result = room_store.add_player(code, player)
    if result is None:
        emit("error", {"message": "Room not found"})
        return

    if role == "host" and result is True:
        room["host_id"] = player["id"]

    action = "reconnected" if result is False else "joined"
    log.info("room=%-4s event=player:join player=%-12s role=%-6s sid=%s action=%s",
             code, name, role, sid, action)

    # Resolve the stored player ID (may differ from new uuid on reconnect)
    stored = next((p for p in room["players"] if p["name"] == name and p["role"] == role), player)

    join_room(code)
    emit("player:self", {"player_id": stored["id"], "role": role})
    socketio.emit("game:state", room_store.get_room_state(code), to=code)


@socketio.on("host:claim")
def handle_claim_host(data):
    code = data.get("room_code", "").upper()
    sid  = request.sid[:8]

    room = room_store.get_room(code)
    if not room:
        emit("error", {"message": "Room not found"})
        return
    if room["state"] != "lobby":
        emit("error", {"message": "Cannot claim host after game has started"})
        return

    sender = next((p for p in room["players"] if p["socket_id"] == request.sid), None)
    if not sender:
        emit("error", {"message": "Player not found"})
        return

    if room["host_id"] is not None:
        emit("error", {"message": "A host has already been assigned"})
        return

    sender["role"] = "host"
    room["host_id"] = sender["id"]
    log.info("room=%-4s event=host:claim  player=%-12s sid=%s", code, sender["name"], sid)

    emit("player:self", {"player_id": sender["id"], "role": "host"})
    socketio.emit("game:state", room_store.get_room_state(code), to=code)


@socketio.on("host:start")
def handle_start(data):
    code = data.get("room_code", "").upper()
    sid  = request.sid[:8]

    room = room_store.get_room(code)
    if not room:
        emit("error", {"message": "Room not found"})
        return
    if room["state"] != "lobby":
        emit("error", {"message": "Game already started"})
        return

    sender = next((p for p in room["players"] if p["socket_id"] == request.sid), None)
    if not sender or sender["role"] != "host":
        emit("error", {"message": "Only the host can start the game"})
        return

    log.info("room=%-4s event=host:start host=%s sid=%s", code, sender["name"], sid)

    success = game.start_game(code, socketio)
    if not success:
        emit("error", {"message": "Need at least 2 players to start"})


@socketio.on("submit:photo")
def handle_submit_photo(data):
    code      = data.get("room_code", "").upper()
    prompt_id = data.get("prompt_id", "")
    image_url = data.get("image_url", "")
    caption   = data.get("caption")
    sid       = request.sid[:8]

    room = room_store.get_room(code)
    if not room:
        emit("error", {"message": "Room not found"})
        return

    sender = next((p for p in room["players"] if p["socket_id"] == request.sid), None)
    if not sender:
        emit("error", {"message": "Player not found"})
        return

    ok = room_store.add_submission(code, prompt_id, sender["id"], image_url, caption)
    if not ok:
        emit("error", {"message": "Could not record submission"})
        return

    log.info("room=%-4s event=submit:photo player=%-12s sid=%s", code, sender["name"], sid)
    socketio.emit("game:state", room_store.get_room_state(code), to=code)

    if game.all_prompts_submitted(room["prompts"]):
        log.info("room=%-4s event=all_submitted — advancing early", code)
        # voting_intro included: a late upload that completes the set during
        # the intro skips the rest of it and jumps straight to voting.
        game.advance_now(code, socketio,
                         expected_state=("submitting", "voting_intro"))


@socketio.on("submit:vote")
def handle_vote(data):
    code         = data.get("room_code", "").upper()
    prompt_id    = data.get("prompt_id", "")
    voted_for_id = data.get("voted_for_id", "")
    sid          = request.sid[:8]

    room = room_store.get_room(code)
    if not room:
        emit("error", {"message": "Room not found"})
        return

    sender = next((p for p in room["players"] if p["socket_id"] == request.sid), None)
    if not sender:
        emit("error", {"message": "Player not found"})
        return

    ok = room_store.add_vote(code, prompt_id, sender["id"], voted_for_id)
    if not ok:
        emit("error", {"message": "Could not record vote"})
        return

    log.info("room=%-4s event=submit:vote voter=%-12s for=%s sid=%s",
             code, sender["name"], voted_for_id[:8], sid)
    socketio.emit("game:state", room_store.get_room_state(code), to=code)

    prompt = room_store.get_current_prompt(code)
    connected = [p for p in room["players"] if p["is_connected"]]
    if prompt and game.all_voted(prompt, connected):
        log.info("room=%-4s event=all_voted — advancing early", code)
        game.advance_now(code, socketio, expected_state="voting")


@socketio.on("submit:caption")
def handle_submit_caption(data):
    code         = data.get("room_code", "").upper()
    caption_text = data.get("caption_text", "").strip()
    sid          = request.sid[:8]

    room = room_store.get_room(code)
    if not room:
        emit("error", {"message": "Room not found"})
        return

    sender = next((p for p in room["players"] if p["socket_id"] == request.sid), None)
    if not sender:
        emit("error", {"message": "Player not found"})
        return

    ok = room_store.add_caption(code, sender["id"], caption_text)
    if not ok:
        emit("error", {"message": "Could not record caption"})
        return

    log.info("room=%-4s event=submit:caption player=%-12s sid=%s", code, sender["name"], sid)
    socketio.emit("game:state", room_store.get_room_state(code), to=code)

    cp        = room.get("caption_prompt")
    connected = [p for p in room["players"] if p["is_connected"]]
    if cp and game.all_captions_submitted(cp, connected):
        log.info("room=%-4s event=all_captions_submitted — advancing early", code)
        game.advance_now(code, socketio, expected_state="captioning")


@socketio.on("submit:caption_vote")
def handle_caption_vote(data):
    code         = data.get("room_code", "").upper()
    voted_for_id = data.get("voted_for_id", "")
    sid          = request.sid[:8]

    room = room_store.get_room(code)
    if not room:
        emit("error", {"message": "Room not found"})
        return

    sender = next((p for p in room["players"] if p["socket_id"] == request.sid), None)
    if not sender:
        emit("error", {"message": "Player not found"})
        return

    ok = room_store.add_caption_vote(code, sender["id"], voted_for_id)
    if not ok:
        emit("error", {"message": "Could not record caption vote"})
        return

    log.info("room=%-4s event=submit:caption_vote voter=%-12s for=%s sid=%s",
             code, sender["name"], voted_for_id[:8], sid)
    socketio.emit("game:state", room_store.get_room_state(code), to=code)

    cp        = room.get("caption_prompt")
    connected = [p for p in room["players"] if p["is_connected"]]
    if cp and game.all_voted(cp, connected):
        log.info("room=%-4s event=all_caption_votes — advancing early", code)
        game.advance_now(code, socketio, expected_state="caption_voting")


@socketio.on("host:restart")
def handle_restart(data):
    code = data.get("room_code", "").upper()
    sid  = request.sid[:8]

    room = room_store.get_room(code)
    if not room:
        emit("error", {"message": "Room not found"})
        return
    if room["state"] != "final":
        emit("error", {"message": "Game is not finished yet"})
        return

    sender = next((p for p in room["players"] if p["socket_id"] == request.sid), None)
    if not sender or sender["role"] != "host":
        emit("error", {"message": "Only the host can restart the game"})
        return

    game.cancel_timer(room)
    room_store.reset_room(code)
    log.info("room=%-4s event=host:restart host=%s sid=%s", code, sender["name"], sid)
    socketio.emit("game:state", room_store.get_room_state(code), to=code)


@socketio.on("host:extend_timer")
def handle_extend_timer(data):
    code = data.get("room_code", "").upper()
    sid  = request.sid[:8]

    room = room_store.get_room(code)
    if not room:
        emit("error", {"message": "Room not found"})
        return

    sender = next((p for p in room["players"] if p["socket_id"] == request.sid), None)
    if not sender or sender["role"] != "host":
        emit("error", {"message": "Only the host can extend the timer"})
        return

    success = game.extend_timer(code, socketio)
    if not success:
        emit("error", {"message": "Cannot extend timer right now"})
        return

    log.info("room=%-4s event=host:extend_timer host=%s sid=%s", code, sender["name"], sid)


@socketio.on("disconnect")
def handle_disconnect():
    sid  = request.sid[:8]
    code, player = room_store.remove_player(request.sid)
    if code and player:
        log.info("room=%-4s event=disconnect    player=%-12s role=%-6s sid=%s",
                 code, player["name"], player["role"], sid)
        socketio.emit("game:state", room_store.get_room_state(code), to=code)
    else:
        log.debug("event=disconnect sid=%s (no room found)", sid)


# ---------------------------------------------------------------------------
# Serve the built React SPA — only active in the packaged binary.
# All /api/ and /uploads/ routes take precedence because they are registered
# first and Flask's routing engine prefers more-specific rules.
# ---------------------------------------------------------------------------

if _FRONTEND_DIST:
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_react(path):
        full = os.path.join(_FRONTEND_DIST, path)
        if path and os.path.exists(full):
            return send_from_directory(_FRONTEND_DIST, path)
        # Fall back to index.html so React Router handles client-side routing.
        return send_from_directory(_FRONTEND_DIST, "index.html")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Starting Photoful server on http://0.0.0.0:%d (LAN: http://%s:%d)",
             PORT, get_local_ip(), PORT)
    # Identical invocation in dev and in the packaged binary. Werkzeug is a
    # perfectly good server for a LAN party game; allow_unsafe_werkzeug just
    # acknowledges we are using it outside `flask run`.
    socketio.run(
        app,
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )
