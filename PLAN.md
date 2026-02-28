# Photo Quiplash — Architecture & Design

## Overview

Three screens at any moment:
- **TV/Big Screen** — Shows prompts, photos, voting UI, scores (browser tab fullscreened on a TV)
- **Player Phone** — Submission and voting interface (mobile browser, no app install)
- **Host Phone** — Same as player phone but with a Start Game button; host is a regular player too

The server owns all state. Phones and TV are just views that re-render on every `game:state` broadcast.

---

## Architecture

```
┌─────────────────────────────────────────┐
│              Game Server                │
│  Flask + Flask-SocketIO + gevent        │
│  - Room management (in-memory)          │
│  - Game state machine                   │
│  - WebSocket hub                        │
│  - REST API for image uploads           │
│  - Prompt bank (prompts.json)           │
└────────┬──────────────┬─────────────────┘
         │              │
    WebSocket       HTTP/REST
         │              │
┌────────▼──────┐  ┌────▼────────────────┐
│  TV Browser   │  │  Player Phone       │
│  React + Vite │  │  React + Vite       │
└───────────────┘  └─────────────────────┘
```

---

## State Machine

```
LOBBY
  → (host taps Start Game, ≥2 players) → SUBMITTING

SUBMITTING  (120s)
  All prompts are active simultaneously. Each player sees all their assigned
  prompts at once and submits a photo for each.
  → (all players submitted for all prompts, OR timer expires) → VOTING

VOTING  (30s per prompt)
  TV shows two competing photos side-by-side.
  Non-competing players vote on their phone.
  → (all eligible players voted, OR timer expires) → SCORES

SCORES  (5s)
  TV shows both competing photos with round winner highlighted and points earned.
  No leaderboard yet — that's reserved for the end.
  → (more prompts remain) → VOTING (next prompt)
  → (all prompts done) → FINAL

FINAL
  Overall leaderboard with winner crown. Game over.
```

---

## Data Model

All state is in-memory (Python dicts). No database.

```python
# Room
{
    "room_code":           str,         # "ABCD"
    "state":               str,         # lobby | submitting | voting | scores | final
    "players":             list[Player],
    "prompts":             list[Prompt],
    "current_prompt_idx":  int,
    "timer_end":           float | None, # unix timestamp
    "timer_greenlet":      Greenlet | None,
    "host_id":             str | None,
}

# Player
{
    "id":           str,   # uuid
    "socket_id":    str,
    "name":         str,
    "role":         str,   # "player" | "host" | "tv"
    "avatar_color": str,   # hex colour
    "score":        int,
    "is_connected": bool,
}

# Prompt
{
    "prompt_id":   str,         # uuid
    "prompt_text": str,
    "player_ids":  [str, str],  # exactly 2 competing players
    "submissions": {player_id: {"image_url": str, "caption": str | None}},
    "votes":       {voter_id: voted_for_player_id},
    "score_deltas": {player_id: int},  # set after tallying
}
```

---

## WebSocket Event Contract

### Client → Server
| Event | Payload | Description |
|---|---|---|
| `player:join` | `{room_code, name, role}` | Join or rejoin a room |
| `host:claim` | `{room_code}` | In-lobby player claims the host role |
| `host:start` | `{room_code}` | Host starts the game (requires ≥2 players) |
| `submit:photo` | `{room_code, prompt_id, image_url, caption?}` | Player submits a photo |
| `submit:vote` | `{room_code, prompt_id, voted_for_id}` | Player casts a vote |

### Server → All Clients in Room
| Event | Payload | Description |
|---|---|---|
| `game:state` | (see below) | Full room state broadcast on every transition |

### Server → Joining Client Only
| Event | Payload | Description |
|---|---|---|
| `player:self` | `{player_id, role}` | Phone stores this to know its own identity |
| `error` | `{message}` | e.g. room not found, already started |

### `game:state` Payload
```json
{
  "room_code": "ABCD",
  "state": "lobby|submitting|voting|scores|final",
  "players": [{"id", "name", "role", "avatar_color", "score", "is_connected"}],
  "prompts": [...],
  "current_prompt": {
    "prompt_id": "...",
    "prompt_text": "Show us...",
    "player_ids": ["id1", "id2"],
    "submissions": {"id1": {"image_url": "/uploads/...", "caption": null}},
    "votes": {"voter_id": "id1"},
    "score_deltas": {"id1": 1000, "id2": 0}
  },
  "prompt_number": 1,
  "total_prompts": 3,
  "timer_end": 1234567890.0
}
```

---

## Image Upload Flow

Photos are large — they go over HTTP, not WebSocket.

```
1. Phone picks a photo (camera or camera roll)
2. browser-image-compression compresses to <1MB client-side
3. Phone POSTs multipart/form-data to /api/rooms/:code/upload
4. Server (Pillow): thumbnail to max 1280×1280, save as JPEG q=80
5. Server returns { image_url: "/uploads/<code>/<uuid>.jpg" }
6. Phone emits submit:photo with the image_url
```

---

## Prompt Assignment

`assign_prompts(players)`:
- Shuffle the player list
- `_make_pairs(n)` generates `ceil(n × PROMPTS_PER_PLAYER / 2)` pairs using a greedy algorithm: each iteration picks the two players with the highest remaining "need" (initialised to `PROMPTS_PER_PLAYER = 3`). Ties are shuffled for variety.
- Randomly sample that many prompts from the bank
- Result: every player appears in exactly `PROMPTS_PER_PLAYER` matchups (one player gets `PROMPTS_PER_PLAYER + 1` when n is odd — unavoidable)

---

## Scoring

- 1000 points per vote received
- Computed in `tally_scores(prompt)` after voting closes
- Applied to player scores in `apply_scores(room_code, prompt)`
- `score_deltas` stored on the prompt for display on the scores screen

---

## Timer System

Timers use gevent greenlets:

```python
def _start_timer(room_code, seconds, callback, socketio):
    def _run():
        gevent.sleep(seconds)
        room["timer_greenlet"] = None
        callback()
    return gevent.spawn(_run)
```

`cancel_timer(room)` kills the greenlet early (when all players act before time runs out).

Timeouts:
- Submit: 120s
- Vote: 30s
- Scores display: 5s

---

## Key Design Decisions

**All prompts before voting.** Rather than cycling prompt-by-prompt through the full loop, all players submit photos for all their prompts in one 90s window, then the game moves through each prompt's voting/scores phase in sequence. This keeps the submission energy high and avoids dead time waiting for a single pair.

**Scores screen shows photos, not leaderboard.** The leaderboard only appears at the very end. The scores screen shows the two competing photos with the round winner highlighted — keeps the focus on the content rather than standings mid-game.

**Host is a player.** The host joins via their phone just like anyone else. They get the Start Game button and also participate in prompts. No dedicated host screen needed.

**TV joins as role "tv".** The TV emits `player:join` with `role: "tv"` so it receives `game:state` broadcasts. It's excluded from player lists and prompt assignment.

**Reconnection.** Sockets reconnect automatically. On reconnect, clients re-emit `player:join`; the server restores their player record and re-broadcasts current state.

---

## File Map

| File | Responsibility |
|---|---|
| `backend/app.py` | Flask routes, socket event handlers, upload endpoint |
| `backend/game.py` | `assign_prompts`, `advance_state`, `start_game`, `tally_scores`, timer helpers |
| `backend/rooms.py` | In-memory room CRUD, `get_room_state` serialiser |
| `backend/bots.py` | Bot players for `make devtest` — auto-submit and auto-vote |
| `backend/prompts.json` | Bank of 46 photo prompts |
| `frontend/src/pages/TV.jsx` | All TV screens (lobby, submitting, voting, scores, final) |
| `frontend/src/pages/Phone.jsx` | All phone screens (join, lobby, submitting, voting, scores, final) |
| `frontend/src/pages/Home.jsx` | Create room / enter room code / host-or-player toggle |
| `frontend/src/socket.js` | Shared socket.io-client singleton |

---

## Sprint Status

### Sprint 1 — Skeleton ✅
- Flask + React project scaffolding
- Room creation, 4-letter codes
- TV and phone join the same room via WebSocket
- Player list syncs in real time

### Sprint 2 — Core Game Loop ✅
- Host joins from phone; Start Game button requires ≥2 players
- Prompt assignment (3 prompts per player, greedy pairing algorithm)
- Photo upload endpoint + Pillow server-side resize
- Multi-prompt submission phase (120s, all prompts active simultaneously)
- Voting phase per prompt (30s); TV hides photos for 3s then fades them in
- Scores screen shows competing photos + round winner (5s)
- Final leaderboard
- QR code in lobby (resolves local network IP automatically)
- Socket reconnection with state restore
- Bot players for local testing (`make devtest bots=N`); room code reprinted at end
- Ctrl+C on `make dev`/`make devtest` fully stops servers (no `make stop` needed)
- Full test suite: 167 backend (pytest) + 95 frontend (vitest)

### Sprint 3 — Polish (planned)
- Sound effects
- Mobile UI polish (large tap targets, no zoom on input focus)
- Room cleanup after session ends

### Sprint 4 — Production (planned)
- Deploy to Fly.io
- Move image storage to Cloudflare R2 or AWS S3
- Rate limiting on uploads
- Optional NSFW content moderation
