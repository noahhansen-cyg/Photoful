import gevent.monkey
gevent.monkey.patch_all()

import uuid
import random
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit, join_room
from flask_cors import CORS
import rooms as room_store

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
    return jsonify({"room_code": room["code"]}), 201


@app.route("/api/rooms/<code>", methods=["GET"])
def check_room(code):
    room = room_store.get_room(code.upper())
    return jsonify({"exists": room is not None})


# ---------------------------------------------------------------------------
# SocketIO events
# ---------------------------------------------------------------------------

@socketio.on("player:join")
def handle_join(data):
    code = data.get("room_code", "").upper()
    name = data.get("name", "TV")
    role = data.get("role", "player")  # "tv" or "player"

    room = room_store.get_room(code)
    if not room:
        emit("error", {"message": f"Room {code} not found"})
        return

    player = {
        "id": str(uuid.uuid4()),
        "socket_id": request.sid,
        "name": name,
        "role": role,
        "avatar_color": random.choice(AVATAR_COLORS),
    }

    room_store.add_player(code, player)
    join_room(code)

    # Tell everyone else in the room a new player joined
    emit("player:joined", {"player": player}, to=code, include_self=False)

    # Send the joining client the full current state
    emit("game:state", room_store.get_room_state(code))


@socketio.on("disconnect")
def handle_disconnect():
    code, player = room_store.remove_player(request.sid)
    if code and player:
        emit("player:left", {"player_id": player["id"]}, to=code)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, use_reloader=False)
