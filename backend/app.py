import gevent.monkey
gevent.monkey.patch_all()

import uuid
import random
import logging
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit, join_room
from flask_cors import CORS
import rooms as room_store

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
app.config["SECRET_KEY"] = "dev-secret-change-in-prod"

CORS(app, resources={r"/api/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

AVATAR_COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4",
    "#FFEAA7", "#DDA0DD", "#98D8C8", "#F7DC6F",
]


# ---------------------------------------------------------------------------
# REST routes
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# SocketIO events
# ---------------------------------------------------------------------------

@socketio.on("player:join")
def handle_join(data):
    code = data.get("room_code", "").upper()
    name = data.get("name", "TV")
    role = data.get("role", "player")
    sid  = request.sid[:8]  # abbreviated for readability

    room = room_store.get_room(code)
    if not room:
        log.warning("room=%-4s event=player:join error=room_not_found name=%s sid=%s", code, name, sid)
        emit("error", {"message": f"Room {code} not found"})
        return

    player = {
        "id": str(uuid.uuid4()),
        "socket_id": request.sid,
        "name": name,
        "role": role,
        "avatar_color": random.choice(AVATAR_COLORS),
    }

    reconnected = not room_store.add_player(code, player)
    action = "reconnected" if reconnected else "joined"
    log.info("room=%-4s event=player:join player=%-12s role=%-6s sid=%s action=%s",
             code, name, role, sid, action)

    join_room(code)

    emit("player:joined", {"player": player}, to=code, include_self=False)
    emit("game:state", room_store.get_room_state(code))


@socketio.on("disconnect")
def handle_disconnect():
    sid  = request.sid[:8]
    code, player = room_store.remove_player(request.sid)
    if code and player:
        log.info("room=%-4s event=disconnect    player=%-12s role=%-6s sid=%s",
                 code, player["name"], player["role"], sid)
        emit("player:left", {"player_id": player["id"]}, to=code)
    else:
        log.debug("event=disconnect sid=%s (no room found — likely TV or pre-join)", sid)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Starting Photo Quiplash server on :5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, use_reloader=False)
