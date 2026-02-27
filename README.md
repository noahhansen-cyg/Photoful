# Photo Quiplash

A party game like Quiplash, but with photos. A prompt appears — players take photos from their phones and submit them. Everyone votes. Chaos ensues.

---

## How It Works

- **TV/Big Screen** — Open in a browser, fullscreened on your TV or laptop
- **Player Phones** — Players join via their phone's browser. No app install needed
- One person joins as **Host** from their phone and starts the game
- Each prompt is assigned to exactly 2 players — they compete head-to-head

---

## Project Structure

```
quiplash_but_fun_and_pictures-/
├── backend/
│   ├── app.py          # Flask app, REST routes, WebSocket events
│   ├── game.py         # State machine, prompt assignment, scoring
│   ├── rooms.py        # In-memory room/player state management
│   ├── bots.py         # Bot players for local testing (make devtest)
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
└── PLAN.md             # Architecture and design notes
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
| `make devtest` | Start servers + 3 bot players for solo testing |
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

The frontend runs on `http://localhost:5173`. It proxies `/api`, `/socket.io`, and `/uploads` requests to the backend automatically — no CORS configuration needed.

---

## Playing the Game

1. Open `http://localhost:5173` on your computer → click **Create Room (TV)**
2. The TV shows a 4-letter room code, QR code, and join URL
3. On each phone, navigate to `http://<your-local-ip>:5173` (or scan the QR code)
4. One player enters the code, toggles to **Host**, and joins — they'll see a **Start Game** button
5. Other players enter the code and join as **Player** — they appear on the TV in real time
6. Host taps **Start Game** (requires at least 2 players)
7. **Submitting (90s):** Each player sees all their assigned prompts at once. Take a photo for each, add an optional caption, and submit. The TV shows who has submitted with checkmarks
8. **Voting (30s per prompt):** The TV shows two competing photos side-by-side. Non-competing players vote on their phone by tapping a photo
9. **Scores (10s):** The TV shows both photos again with the round winner highlighted and points earned. Then auto-advances to the next prompt
10. After all 3 prompts → **Final leaderboard** with the overall winner

**Game flow:** `lobby → submitting (90s, all prompts) → voting (30s) → scores (10s) → [repeat voting/scores] → final`

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

## Local Testing with Bots

`make devtest` starts the full stack plus 3 bot players (AliceBot, BobBot, CarolBot) that automatically join, submit photos, and vote. A room is created automatically and the TV URL is printed.

You join as Host from your phone and start the game yourself.

```bash
make devtest
# → open the printed TV URL in your browser
# → navigate to http://localhost:5173 on your phone, enter the code, join as Host
# → tap Start Game
```

Bots vote with a 5–10s random delay so you have time to vote first.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask, Flask-SocketIO |
| WebSockets | gevent + Flask-SocketIO |
| Image processing | Pillow (server-side resize to 1280px JPEG) |
| Frontend | React, Vite |
| Real-time client | socket.io-client |
| Routing | React Router |
| Image compression | browser-image-compression (client-side pre-compress) |
| QR codes | qrcode.react |
