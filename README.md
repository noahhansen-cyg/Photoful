# Photo Quiplash

A party game like Quiplash, but with photos. A prompt appears on the TV — players take photos from their phones and submit them. Everyone votes. Chaos ensues.

---

## How It Works

- **TV/Big Screen** — Open in a browser, fullscreened on your TV or laptop
- **Player Phones** — Players join via their phone's browser. No app install needed
- The host creates a room on the TV, players join with the 4-letter room code

---

## Project Structure

```
quiplash_but_fun_and_pictures-/
├── backend/
│   ├── app.py          # Flask app, REST routes, WebSocket events
│   ├── game.py         # State machine, prompt assignment, scoring
│   ├── rooms.py        # In-memory room/player state management
│   ├── prompts.json    # Bank of 24 photo prompts
│   ├── uploads/        # Uploaded photos (created at runtime)
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Home.jsx    # Create or join a room (with host/player toggle)
│       │   ├── TV.jsx      # TV display — all game screens
│       │   └── Phone.jsx   # Player phone — submission, voting, scores
│       └── socket.js       # Shared socket.io-client instance
└── PLAN.md             # Full project plan and architecture
```

---

## Prerequisites

- Python 3.10+
- Node.js 20+
- `make`

---

## Quick Start

```bash
make install   # install all dependencies (run once after cloning)
make dev       # start backend + frontend together
```

`Ctrl+C` stops both servers. If a port gets stuck: `make stop`.

---

## All Make Commands

| Command | Description |
|---|---|
| `make dev` | Start backend (:5000) and frontend (:5173) together |
| `make stop` | Force-kill anything on ports 5000 and 5173 |
| `make install` | Install Python + Node dependencies in one shot |
| `make test` | Run all tests (backend + frontend) |
| `make test-backend` | Run backend pytest suite only |
| `make test-frontend` | Run frontend vitest suite only |

---

## Running Manually

### Backend

```bash
cd backend
pip install -r requirements.txt
python app.py
```

The server runs on `http://localhost:5000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:5173`. It proxies `/api` and `/socket.io` requests to the backend automatically — no CORS configuration needed.

---

## Playing the Game

1. Open `http://localhost:5173` on your computer → click **Create Room (TV)**
2. The TV shows a 4-letter room code and join URL
3. On each phone, navigate to `http://<your-local-ip>:5173`
4. One player enters the code, toggles to **Host**, and joins — they'll see a **Start Game** button
5. Other players enter the code and join as **Player** — they appear on the TV in real time
6. Host taps **Start Game** (requires at least 2 players)
7. Assigned players see their prompt and a camera button — take a photo, add an optional caption, submit
8. After all photos are in (or 60s expires) → TV reveals both photos side-by-side
9. Non-competing players vote on their phone by tapping a photo (30s)
10. TV shows score deltas and the updated leaderboard (5s), then auto-advances
11. Repeat for all 3 prompts → final leaderboard with winner

**Game flow:** `lobby → submitting (60s) → voting (30s) → scores (5s) → [repeat] → final`

**Finding your local IP:**
```bash
# macOS
ipconfig getifaddr en0
```

Or use [ngrok](https://ngrok.com) to get a public URL that works over any network:
```bash
ngrok http 5173
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask, Flask-SocketIO |
| WebSockets | gevent + Flask-SocketIO |
| Image processing | Pillow (server-side resize) |
| Frontend | React, Vite |
| Real-time client | socket.io-client |
| Routing | React Router |
| Image compression | browser-image-compression (client-side pre-compress) |
