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
├── backend/          # Python/Flask server
│   ├── app.py        # Flask app, REST routes, WebSocket events
│   ├── rooms.py      # In-memory room/player state management
│   └── requirements.txt
├── frontend/         # React + Vite
│   └── src/
│       ├── pages/
│       │   ├── Home.jsx    # Create or join a room
│       │   ├── TV.jsx      # TV lobby display
│       │   └── Phone.jsx   # Player phone interface
│       └── socket.js       # Shared socket.io-client instance
└── PLAN.md           # Full project plan and architecture
```

---

## Prerequisites

- Python 3.10+
- Node.js 20+

---

## Running Locally

### 1. Start the backend

```bash
cd backend
pip install -r requirements.txt
python app.py
```

The server runs on `http://localhost:5000`.

### 2. Start the frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:5173`. It proxies `/api` and `/socket.io` requests to the backend automatically — no CORS configuration needed.

---

## Playing the Game (Current State)

> **Sprint 1 complete** — the lobby skeleton works end-to-end. Game logic (prompts, photos, voting) is coming in Sprint 2+.

1. Open `http://localhost:5173` in a browser on your computer → click **Create Room (TV)**
2. The TV screen shows a 4-letter room code and a join URL
3. On your phone, navigate to `http://<your-local-ip>:5173` (e.g. `http://192.168.1.42:5173`)
4. Enter the room code → enter your name → join
5. Players appear on the TV screen in real time as they join

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
| Image processing | Pillow |
| Frontend | React, Vite |
| Real-time client | socket.io-client |
| Routing | React Router |
