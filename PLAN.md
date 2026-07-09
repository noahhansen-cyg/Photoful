# Photoful — Architecture & Design

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
│  Flask + Flask-SocketIO (threading +    │
│  simple-websocket — identical in dev,   │
│  cloud, and the packaged desktop app)   │
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
  → (all players submitted for all prompts, OR timer expires) → VOTING_INTRO

VOTING_INTRO  (5s)
  Brief transition screen: "Round 1 — Let's Vote!" (round 1) or
  "Round 2 — Double Points!" (round 2). Gives players a moment to put
  their phones down after submitting before voting begins.
  → (timer expires) → VOTING

VOTING  (30s per prompt)
  TV shows two competing photos side-by-side.
  Non-competing players vote on their phone.
  → (all eligible players voted, OR timer expires) → SCORES

SCORES  (5s)
  TV shows both competing photos with round winner highlighted and points earned.
  No leaderboard yet — that's reserved for the end.
  → (more prompts remain in current round) → VOTING (next prompt)
  → (all prompts done, more rounds remain) → ROUND_INTRO
  → (all prompts done, round 2 complete) → CAPTION_INTRO

ROUND_INTRO  (7s)
  Brief announcement screen: "Round 2 — Double Points!"
  Votes are cleared; round counter increments; same photos replay at 2× points.
  → (timer expires) → VOTING (first prompt, round 2)

CAPTION_INTRO  (7s)
  Final round announcement: "Caption Challenge!"
  The highest-voted photo from round 2 is revealed on screen.
  → (timer expires) → CAPTIONING

CAPTIONING  (60s)
  All players type a funny text caption for the featured photo (no photo upload).
  TV shows the featured photo and submission progress count.
  → (all players submitted, OR timer expires) → CAPTION_VOTING

CAPTION_VOTING  (30s)
  TV shows the featured photo and all submitted captions as cards.
  All players vote for their favourite caption (can't vote for their own).
  3-second reveal delay before captions are shown (same pattern as photo voting).
  → (all eligible players voted, OR timer expires) → CAPTION_SCORES

CAPTION_SCORES  (5s)
  TV shows caption cards with vote counts and score deltas.
  Winner badge on the caption that earned the most votes.
  → FINAL

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
    "state":               str,         # lobby | submitting | voting_intro | voting | scores
                                        # | round_intro | caption_intro | captioning
                                        # | caption_voting | caption_scores | final
    "round":               int,         # current voting round (1-indexed); doubles points each round
    "players":             list[Player],
    "prompts":             list[Prompt],
    "current_prompt_idx":  int,
    "timer_end":           float | None, # unix timestamp
    "timer_greenlet":      Greenlet | None,
    "host_id":             str | None,
    "caption_prompt":      CaptionPrompt | None,  # set when caption round starts
}

# CaptionPrompt
{
    "prompt_id":            str,   # uuid
    "round_type":           str,   # "caption"
    "featured_image_url":   str,   # URL of the winning photo from round 2
    "featured_player_id":   str,   # who originally submitted the winning photo
    "featured_prompt_text": str,   # original prompt text for context
    "player_ids":           list[str],  # all players participate
    "submissions":          {player_id: {"caption": str}},  # text captions
    "votes":                {voter_id: voted_for_player_id},
    "score_deltas":         {player_id: int},  # set after tallying
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
| `submit:vote` | `{room_code, prompt_id, voted_for_id}` | Player casts a vote in a photo round |
| `submit:caption` | `{room_code, caption_text}` | Player submits a text caption (final round) |
| `submit:caption_vote` | `{room_code, voted_for_id}` | Player votes for a caption (final round) |
| `host:restart` | `{room_code}` | Host restarts the game from lobby (final state only) |

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
  "state": "lobby|submitting|voting_intro|voting|scores|round_intro|caption_intro|captioning|caption_voting|caption_scores|final",
  "round": 1,
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
  "timer_end": 1234567890.0,
  "caption_prompt": {
    "prompt_id": "...",
    "round_type": "caption",
    "featured_image_url": "/uploads/ABCD/abc123.jpg",
    "featured_player_id": "...",
    "featured_prompt_text": "Show us your best...",
    "player_ids": ["id1", "id2", "id3"],
    "submissions": {"id1": {"caption": "A funny caption"}},
    "votes": {"id2": "id1"},
    "score_deltas": {"id1": 2000}
  }
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

- `round × 1000` points per vote received (round 1 = 1000 pts, round 2 = 2000 pts)
- Computed in `tally_scores(prompt, points_per_vote)` after voting closes
- Applied to player scores in `apply_scores(room_code, prompt)` (reads `room["round"]`)
- `score_deltas` stored on the prompt for display on the scores screen; cleared between rounds

---

## Timer System

Timers use plain `threading.Timer`, so the exact same code runs in dev, in the
cloud deploy, and inside the PyInstaller binary — no gevent anywhere:

```python
def _start_timer(room_code, seconds, callback, socketio):
    def _fire():
        with _lock:                          # serialized with early-advance paths
            if room.get("timer") is not timer:
                return                       # cancelled/replaced while waiting
            room["timer"] = None
            callback()
    timer = threading.Timer(seconds, _fire)
```

`cancel_timer(room)` cancels the pending timer, and `advance_now(code, socketio,
expected_state=...)` atomically cancels + advances when all players act before
time runs out. The expected-state guard prevents two concurrent handlers (e.g.
the last two captions arriving simultaneously) from double-advancing the state
machine.

Timeouts:
- Submit: 120s
- Voting intro: 5s
- Vote: 30s
- Scores display: 5s
- Round intro: 7s
- Caption intro: 7s
- Captioning: 60s
- Caption scores: 5s

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
- Page refresh rejoins automatically via localStorage session persistence
- Upload error handling: 30s timeout, HTTP error check, visible error message
- Play Again button (host only) restarts with existing players after final
- Phone vote cards hidden for 3s to match TV reveal animation
- Scores screen display reduced from 10s to 5s
- Full test suite: 183 backend (pytest) + 110 frontend (vitest)

### Sprint 6 — Two-Round Gameplay ✅
- Second voting round after round 1 completes, with 2× points per vote (2000 pts)
- `ROUND_INTRO` state (7s) announces "Round 2 — Double Points!" between rounds
- Same photos replayed; votes cleared between rounds; `score_deltas` reset
- TV shows round badge ("Round 2 — 2× Points") during voting in round 2
- Phone shows "Round 2 — Double Points — get ready to vote!" during `round_intro`
- `room["round"]` field added to data model and `game:state` payload
- `tally_scores` and `apply_scores` updated to accept and apply round multiplier
- Full test suite updated: existing two-round boundary tests fixed; 12+ new tests added

### Sprint 7 — Caption Round (Final Round) ✅
- After round 2 completes, the highest-voted photo is selected (`find_best_photo`) and a caption round begins
- New states: `CAPTION_INTRO (7s) → CAPTIONING (60s) → CAPTION_VOTING (30s) → CAPTION_SCORES (5s) → FINAL`
- `room["caption_prompt"]` field stores all caption round data (featured photo, player_ids, text submissions, votes, score_deltas)
- All players (including host) submit a text caption via `submit:caption {room_code, caption_text}`
- All players vote for a favourite caption (excluding their own) via `submit:caption_vote {room_code, voted_for_id}`
- Points remain 2000 pts/vote (doubled from round 1); reuses existing `tally_scores`
- TV: `CaptionIntroScreen` (featured photo + announcement), `CaptioningScreen` (photo + progress count), `CaptionVotingScreen` (photo + caption cards with 3s reveal delay + vote counts), `CaptionScoresScreen` (photo + winner badge + score deltas)
- Phone: `CaptionIntroScreen` (announcement), `CaptionSubmitScreen` (textarea + submit), `CaptionVoteScreen` (caption buttons excluding own, 3s reveal delay), `caption_scores` waiting screen
- Bots auto-submit captions and auto-vote in the caption round
- Fallback: if no photo submissions exist after round 2, game goes directly to `final`
- Full test suite: 243 backend tests (41 new) + 173 frontend tests (15 new)

### Sprint 8 — Voting Intro Transition ✅
- Added `VOTING_INTRO` state (5s) between `submitting` and the first `voting` prompt in every round
- TV shows "Round 1 — Let's Vote!" (round 1) or "Round 2 — Double Points!" (round 2) with a TimerBar
- Phone shows the round number and a "Get ready to vote!" / "Double Points — time to vote!" hint
- Eliminates the jarring jump from the submission phase directly into photo comparison voting
- Full test suite: 245 backend tests + 180 frontend tests

### Sprint 3 — Polish (planned)
- Sound effects
- Mobile UI polish (large tap targets, no zoom on input focus)
- Room cleanup after session ends
- **Main menu** (see Sprint 5 — Distribution for detail)

### Sprint 4 — Production (planned)
- Deploy to Fly.io
- Move image storage to Cloudflare R2 or AWS S3
- Rate limiting on uploads
- Optional NSFW content moderation

### Sprint 5 — Distribution (planned)
- Package as a standalone executable (Windows + macOS)
- Steam launcher compatibility
- Main menu screen
- Online multiplayer (play over the internet, not just LAN)
- Local/Online mode toggle

---

## Sprint 5 — Distribution Detail

The four items below all stem from the same goal: turn the current "run in a terminal"
dev build into a packaged desktop app anyone can launch from Steam or a game launcher,
with both a LAN mode (current behaviour) and an internet mode.

---

### 5a — Executable Packaging

**Goal:** A double-clickable binary that boots the Flask server and opens the game UI
in a window (or browser tab) without the user needing Python, Node, or a terminal.

**Recommended approach — Electron wrapper:**

```
electron/
  main.js          # Electron entry point
  preload.js       # optional — bridge to renderer context
```

1. Build the Vite frontend to `frontend/dist/` (`npm run build`).
2. Bundle the Flask backend + Python dependencies with **PyInstaller** into a single
   binary (`backend/dist/server`). The Flask app then serves the built static files
   from `frontend/dist/` instead of relying on Vite dev server.
3. Electron `main.js`:
   - Spawns the PyInstaller binary as a child process.
   - Waits for the server to be ready (poll `http://localhost:5000/healthz`).
   - Opens a `BrowserWindow` pointing at `http://localhost:5000`.
   - On app quit, kills the server child process.
4. Use **electron-builder** to produce a platform installer:
   - Windows: `.exe` NSIS installer
   - macOS: `.dmg` / `.app` bundle

**Alternative — browser-only (no Electron):**
If a native window is not required, PyInstaller alone can bundle the Flask server.
At launch it opens `http://localhost:5000` in the user's default browser. Simpler,
but no custom window chrome and the browser tab can be closed accidentally.

**Steam compatibility:**
Steam just needs a launchable executable. The Electron `.exe` or the PyInstaller
binary can be set as the game's launch target in Steamworks. No special SDK
integration is required unless you want Steam achievements or the overlay.

**New files:**
- `electron/main.js`
- `electron/package.json`
- `Makefile` targets: `make build-backend`, `make build-frontend`, `make build-electron`, `make package`

---

### 5b — Main Menu

**Goal:** A home screen shown immediately on launch (instead of the raw "create/join"
room form) that acts as the game's entry point.

**Screens:**

```
┌─────────────────────────────────┐
│       📸  Photoful        │
│                                 │
│   [ Play Online  ]              │
│   [ Play Local   ]              │
│                                 │
│         Settings ⚙              │
└─────────────────────────────────┘
```

- **Play Online** — navigates to the existing Home page with a connection preset
  pointing at the cloud/relay server.
- **Play Local** — navigates to the existing Home page with a connection preset
  pointing at `localhost:5000` (the embedded server).
- **Settings** — volume, display preferences (future).

**Implementation:**
- New route `/` → `MainMenu.jsx` component.
- Existing Home.jsx becomes `/room` (create/join step).
- The chosen mode is stored in React context (or a tiny Zustand/jotai store) and
  read by `socket.js` to determine which server URL to connect to.
- The Electron main process can pass the mode via a query param on launch
  (`?mode=local` or `?mode=online`) to pre-select without user input.

---

### 5c — Online Multiplayer

**Goal:** Players can join a game hosted by someone on a completely different network —
no port forwarding, no shared Wi-Fi required.

**Recommended approach — Cloud-hosted relay (simplest, most reliable):**

The entire Flask app is deployed to a cloud service (Fly.io is already planned for
Sprint 4). Players connect their phones to the cloud URL; the host creates a room
there just like on LAN. No P2P, no tunnelling, no NAT traversal.

```
Host PC (Electron app, Online mode)
  └─ connects to https://photoful.fly.dev
       └─ creates room, gets room code

Player phones
  └─ open https://photoful.fly.dev
       └─ enter room code → join
```

The Electron app in Online mode is essentially a thin client that navigates to the
cloud URL (or opens it in the embedded BrowserWindow). The embedded Flask server
is **not** started in Online mode.

**Alternative — Cloudflare Tunnel / ngrok (host runs server locally):**

The host's Flask server runs locally, and a tunnel (e.g. `cloudflared tunnel` or
`ngrok http 5000`) exposes it on a public HTTPS URL. The host shares the URL /
room code with players.

Pros: no cloud hosting cost, game logic stays on host hardware.
Cons: requires the host to be running during the whole session; tunnel services
have bandwidth limits; URL changes each session unless a paid plan is used.

This could be automated inside the Electron app:
1. Spawn `cloudflared` alongside the Flask server.
2. Parse the tunnel URL from its stdout.
3. Display it in the main menu / lobby QR code.

**Chosen approach for Sprint 5:** Start with the cloud relay (deploy to Fly.io).
The Cloudflare Tunnel option can be added as a fallback or power-user feature later.

---

### 5d — Local / Online Mode Toggle

**Goal:** Players without internet (e.g. party at a cabin, convention floor) can still
play in LAN mode. Online is the default for ease; Local can be selected at the main menu.

**Behaviour difference:**

| | Online mode | Local mode |
|---|---|---|
| Flask server | NOT started (connects to cloud) | Started on `localhost:5000` |
| Room creation | On cloud server | On embedded server |
| QR code | Points to cloud URL | Points to local network IP (current behaviour) |
| Internet required | Yes | No (LAN only) |
| Player join URL | `https://photoful.fly.dev` | `http://192.168.x.x:5000` |

**Implementation:**
- `socket.js` reads a `MODE` env/config value: `"online"` → connects to cloud URL;
  `"local"` → connects to `http://localhost:5000`.
- Electron main process sets the mode based on user selection in `MainMenu.jsx`
  (passed as an environment variable or IPC message to the renderer).
- In non-Electron (plain browser) builds, the mode toggle can live as a settings
  page or URL param for development.
- The QR code component (`TV.jsx`) already reads the server's reported LAN IP;
  in Online mode it will display the cloud URL instead.
