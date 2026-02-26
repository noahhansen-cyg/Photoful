# Photo Quiplash — Extensive Project Plan

## Overview

This game has three "screens" at any moment:
- **TV/Big Screen** — Shows prompts, photos, voting UI, scores (a browser tab fullscreened)
- **Player Phone** — Submission interface, voting interface (mobile browser, no app install needed)
- **Host** — Could be a dedicated host screen or the TV itself advances rounds

The core challenge is real-time state sync between many phones and one TV. Everything else is product work.

---

## High-Level Architecture

```
┌─────────────────────────────────────────┐
│              Game Server                │
│  - Room management                      │
│  - Game state machine                   │
│  - WebSocket hub                        │
│  - REST API for image uploads           │
│  - Prompt bank                          │
└────────┬──────────────┬─────────────────┘
         │              │
    WebSocket       HTTP/REST
         │              │
┌────────▼──────┐  ┌────▼────────────────┐
│  TV Browser   │  │  Player Phone       │
│  (display)    │  │  (mobile browser)   │
└───────────────┘  └─────────────────────┘
```

---

## Phase 1 — Tech Stack Decisions

### Backend
**Python** is the right choice here because:
- **Flask-SocketIO** is a direct port of the socket.io API — event names and room logic map 1:1
- **Pillow** is the best image processing library across Python/Ruby/Go — dead simple resizing
- Fast to prototype, easy to read and maintain
- Straightforward to deploy anywhere

**Implemented:** **Flask** + **Flask-SocketIO** with **gevent** for async WebSocket handling (eventlet deprecated)

### Real-time Layer
**Flask-SocketIO** — wraps socket.io conventions (rooms, namespaces, reconnection) in idiomatic Python. Events look like this:

```python
@socketio.on("player:join")
def handle_join(data):
    join_room(data["roomCode"])
    emit("game:state", current_state, to=data["roomCode"])
```

### Image Storage
- **Development:** Store locally on disk
- **Production:** Cloudflare R2 or AWS S3 (cheap, scalable, pre-signed URLs for direct upload)

### Frontend (TV + Phone)
**React + Vite** — straightforward, widely documented, easy to find help for. Flask serves the built static files, or deploy frontend separately.

### Database
**SQLite** (via SQLAlchemy ORM) for a small game — you don't need Postgres. Rooms expire after a session anyway. For production scale, swap to Postgres.

---

## Phase 2 — Core Data Model

```python
# A room represents one full game session
class Room:
    id: str              # "XKCD" — 4 letter join code
    host_id: str
    state: str           # lobby | submitting | voting | results | ended
    current_round: int
    current_prompt_index: int
    players: list[Player]
    rounds: list[Round]
    created_at: datetime

class Player:
    id: str
    socket_id: str
    name: str
    avatar_color: str
    score: int
    is_connected: bool

class Round:
    prompts: list[PromptAssignment]  # which players get which prompts

class PromptAssignment:
    prompt_text: str
    assigned_player_ids: list[str]  # 2 players get the same prompt (like quiplash)
    submissions: list[Submission]

class Submission:
    player_id: str
    image_url: str
    caption: str | None  # optional text caption alongside photo
    votes: list[str]     # player_ids who voted for this
```

---

## Phase 3 — Game State Machine

The server owns all state. Phones and TV are just views.

```
LOBBY
  → (host starts game) → ASSIGNING_PROMPTS

ASSIGNING_PROMPTS
  → (server deals prompts) → SUBMITTING

SUBMITTING
  → (all submitted OR timer expires) → REVEALING

REVEALING  (show submissions one prompt at a time)
  → (advance through each matchup) → VOTING

VOTING  (per matchup)
  → (all voted OR timer expires) → SCORES

SCORES  (show who got what votes, update leaderboard)
  → (more prompts remain) → REVEALING
  → (all prompts done, more rounds remain) → ASSIGNING_PROMPTS
  → (game over) → FINAL_RESULTS

FINAL_RESULTS
  → (host restarts) → LOBBY
```

Every state transition broadcasts a WebSocket event to all clients in the room. The TV and phones re-render based on current state.

---

## Phase 4 — WebSocket Event Contract

Define every event up front. This is your API between frontend and backend.

### Server → All Clients
```python
# State changed
emit("game:state",    {"state", "round", "prompt", "timer", "submissions", "scores"}, to=room_code)
emit("player:joined", {"player": player},                                              to=room_code)
emit("player:left",   {"player_id": player_id},                                       to=room_code)
emit("timer:tick",    {"seconds_remaining": n},                                        to=room_code)
```

### Phone → Server
```python
@socketio.on("player:join")   # data: { room_code, name }
@socketio.on("submit:photo")  # data: { prompt_id, image_url, caption? }
@socketio.on("submit:vote")   # data: { prompt_id, submission_id }
```

### Server → Specific Phone
```python
emit("prompt:assigned", {"prompt_id": ..., "prompt_text": ...}, to=socket_id)
emit("submit:ack",      {"success": True},                       to=socket_id)
emit("your:score",      {"delta": 500, "total": 1500},           to=socket_id)
```

---

## Phase 5 — Image Upload Flow

Photos are large — don't send them through WebSocket. Use a two-step flow:

```
1. Phone selects photo from camera roll or takes new photo
2. Phone POSTs to /api/rooms/:roomCode/upload
   - Server validates: correct room, correct player, submission window open
   - Server resizes image (max 1280px wide, JPEG, ~80% quality) using `Pillow`
   - Server stores image, returns { imageUrl }
3. Phone sends WebSocket event "submit:photo" with the returned imageUrl
4. Server associates submission with prompt
```

This keeps WebSocket messages tiny and images handled properly.

**Image resize is critical** — players will try to upload 12MP iPhone RAW photos. Resize everything server-side before storing.

---

## Phase 6 — TV Display UI

The TV screen is a single fullscreen browser tab at `/room/:code/tv`. It should be designed for 1080p/4K displays viewed from 10 feet away. Think huge text, high contrast.

**Screens to build:**
1. **Lobby screen** — shows room code (big), QR code to join, player avatars popping in as they join
2. **"Take your photos!" screen** — prompt text shown to everyone, countdown timer, submission status (who has submitted, shown as checkmarks — not what they submitted)
3. **Reveal screen** — shows two photos side by side (or stacked) for each matchup. Big, dramatic reveal animation
4. **Voting screen** — photos visible, players vote on phones, live vote tally could be hidden until reveal
5. **Scores screen** — leaderboard with vote breakdown, whose photo got the most votes
6. **Final screen** — winner celebration

**QR Code:** Generate a QR code pointing to `https://yourdomain.com/join/XKCD` so players can join without typing. Use the `qrcode` Python package — generate it server-side and serve as a PNG or inline SVG.

---

## Phase 7 — Phone UI

The phone interface lives at `/room/:code/join`. It needs to be a slick mobile web experience.

**Phone screens:**
1. **Join screen** — enter name, pick avatar color
2. **Lobby waiting** — "Waiting for host to start..."
3. **Prompt screen** — shows the prompt text, big camera button, optional caption field, submit button
4. **Submission confirmed** — "Photo submitted! Wait for voting..."
5. **Voting screen** — shows two photos, tap to vote, can't vote for yourself
6. **Results screen** — shows how many votes you got this round

**Camera integration:**
```html
<input type="file" accept="image/*" capture="environment" />
```
This single HTML attribute opens the native camera on iOS and Android. No app needed.

**IMPORTANT UX detail:** Compress the image client-side before uploading using the `browser-image-compression` library. Don't make players wait 30 seconds for a 15MB photo to upload on hotel WiFi.

---

## Phase 8 — Prompt Bank

You need a library of prompts designed for photos, not text. These are fundamentally different from Quiplash prompts.

**Photo prompt categories:**
- **"Show us..."** — "Show us the most chaotic thing in your immediate area"
- **"Find something that..."** — "Find something that looks like it's judging you"
- **"Recreate..."** — "Recreate a Renaissance painting with objects nearby"
- **"Photo that best represents..."** — "A photo that best represents your Monday morning"
- **"Caption challenge"** — show a weird stock photo, players submit their own photo response

Store prompts in a JSON file to start. Later you can add a database table with categories, difficulty, NSFW flags, etc.

---

## Phase 9 — Hosting & Infrastructure

### Development
- Run Flask dev server locally (`flask run` or `python app.py`)
- Use `ngrok` to expose localhost so phones on your WiFi can connect during testing

### Production (cheapest viable path)
- **Fly.io** — $5/month for a persistent server with WebSocket support, easy deploys
- **Cloudflare R2** — free tier covers millions of image requests, $0.015/GB stored
- **Cloudflare CDN** — put in front of image URLs so photos load fast on the TV

### Domain
- Single domain, everything on it
- `/` — landing/marketing page
- `/join` — phone entry point
- `/host` — create a room
- `/room/:code/tv` — TV display
- `/room/:code/phone` — phone interface

---

## Phase 10 — Security & Edge Cases

These will bite you if ignored:

| Problem | Solution |
|---|---|
| Players submitting after window closes | Server validates timestamp on every submission |
| Someone joining mid-game | Allow spectator mode, or queue them for next round |
| Phone loses connection | Socket.io auto-reconnects, server preserves player state by name+roomCode |
| Player uploads NSFW photo | Start with trust, add optional content moderation (AWS Rekognition) later |
| Room code collision | Generate 4-letter codes, check for collisions before returning |
| 50 people in a room | Limit room size (8-10 is sweet spot), enforce server-side |
| TV browser refreshes | TV re-joins room by code, server replays current state |
| Same person voting twice | Track votes server-side by playerId, not client |

---

## Implementation Order (MVP to Polished)

### Sprint 1 — Skeleton (get anything working end-to-end)
- [ ] Server with one Socket.io room
- [ ] TV page joins room, phone page joins room
- [ ] Both see each other's messages in real time
- [ ] Basic room code system

### Sprint 2 — Core Game Loop
- [ ] Lobby → game start
- [ ] Prompt assignment (hard-code 1 round, 1 prompt)
- [ ] Photo upload endpoint + `Pillow` resizing
- [ ] Phone can submit a photo
- [ ] TV shows submitted photos
- [ ] Voting works
- [ ] Score tally

### Sprint 3 — Full Game Flow
- [ ] Multiple rounds
- [ ] Timer system
- [ ] Proper state machine
- [ ] Leaderboard/final results

### Sprint 4 — Polish
- [ ] QR code on lobby screen
- [ ] Animations (TV reveal is a big moment — make it feel good)
- [ ] Client-side image compression
- [ ] Reconnection handling
- [ ] Mobile UI polish (large tap targets, no zoom on input focus)

### Sprint 5 — Production Readiness
- [ ] Deploy to Fly.io
- [ ] Move image storage to R2/S3
- [ ] Room cleanup (delete rooms + images after 2 hours)
- [ ] Rate limiting on uploads
- [ ] Error handling + user-facing error messages

---

## Key Libraries Summary

```python
# Backend (pip packages)
flask
flask-socketio
eventlet            # async worker for Flask-SocketIO
pillow              # image resizing
sqlalchemy          # ORM
flask-sqlalchemy    # SQLAlchemy integration for Flask
qrcode[pil]        # QR code generation, server-side
nanoid              # room code generation (or just use secrets.token_hex)

# Frontend (npm packages)
react + vite
socket.io-client
browser-image-compression   # client-side compression before upload
```

---

## What Makes This Fun (Design Notes)

The hardest part isn't the code — it's making the game feel alive. A few things that matter a lot:

1. **The reveal is everything.** Build the "da-da-da-DUM" moment where photos are shown one at a time with a dramatic reveal. Sound effects help enormously.
2. **Show progress on the TV.** Showing "3/6 players submitted" as checkmarks builds anticipation without spoiling what people submitted.
3. **Captions are optional but powerful.** Letting players add a short caption to their photo adds a comedy layer on top of the image.
4. **Keep rounds short.** 60 seconds to submit, 30 seconds to vote. The game dies if people are waiting.
5. **"Quiplash" mechanic:** Assign the same prompt to exactly 2 players so there's a direct head-to-head comparison. Much funnier than open voting.
