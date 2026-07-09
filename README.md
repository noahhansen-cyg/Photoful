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
│   ├── app.py           # Flask app, REST routes, WebSocket events
│   ├── game.py          # State machine, prompt assignment, scoring
│   ├── rooms.py         # In-memory room/player state management
│   ├── bots.py          # Bot players for local testing (make devtest)
│   ├── prompts.json     # Bank of 46 photo prompts
│   ├── quiplash.spec    # PyInstaller spec — bundles server into a binary
│   ├── uploads/         # Uploaded photos (created at runtime)
│   └── requirements.txt
├── electron/
│   ├── main.js          # Electron main process — spawns Flask, opens BrowserWindow
│   └── package.json     # Electron + electron-builder config
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Home.jsx     # Create or join a room (with host/player toggle)
│       │   ├── TV.jsx       # TV display — all game screens
│       │   └── Phone.jsx    # Player phone — submission, voting, scores
│       └── socket.js        # Shared socket.io-client instance
└── PLAN.md              # Architecture and design notes
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

### Development

| Command | Description |
|---|---|
| `make dev` | Start backend (:5000) and frontend (:5173) together |
| `make devtest` | Start servers + 3 bot players for solo testing |
| `make stop` | Force-kill anything on ports 5000 and 5173 |
| `make install` | Install Python + Node dependencies in one shot |
| `make test` | Run all tests (backend + frontend) |
| `make test-backend` | Run backend pytest suite only |
| `make test-frontend` | Run frontend vitest suite only |

### Packaging

| Command | Description |
|---|---|
| `make build-frontend` | Build the React app into `frontend/dist/` |
| `make build-backend` | Bundle Flask + frontend into a single binary via PyInstaller |
| `make build-electron` | Wrap the binary in an Electron installer |
| `make package` | Full pipeline — outputs installer to `dist/` |
| `make packagetest` | Run the packaged server binary + 3 bot players for solo testing |

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
7. **Submitting (120s):** Each player sees all their assigned prompts at once. Take a photo for each, add an optional caption, and submit. The TV shows who has submitted with checkmarks
8. **Voting (30s per prompt):** The TV shows two competing photos side-by-side. Non-competing players vote on their phone by tapping a photo
9. **Scores (5s):** The TV shows both photos again with the round winner highlighted and points earned. Then auto-advances to the next prompt
10. After all 3 prompts → **Final leaderboard** with the overall winner

**Game flow:** `lobby → submitting (120s, all prompts) → voting (30s) → scores (5s) → [repeat voting/scores] → final`

**Finding your local IP:**
```bash
# macOS
ipconfig getifaddr en0
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

Override the bot count with `bots=N` (max 8): `make devtest bots=5`.

### Testing the packaged build

`make packagetest` is the same workflow but runs the PyInstaller server binary (`backend/dist/quiplash-server`) instead of the dev servers — the production frontend is served by the binary itself on port 5000, so the printed TV URL points there.

```bash
make build-backend   # or make package — either produces the binary
make packagetest     # or: make packagetest bots=5
# → open the printed TV URL (http://localhost:5000/room/CODE/tv)
# → navigate to http://localhost:5000 on your phone, enter the code, join as Host
```

Note: uploads in the packaged build go to the user-data directory (e.g. `~/Library/Application Support/PhotoQuiplash/uploads` on macOS), not `backend/uploads/`.

---

## Packaging as a Desktop App

`make package` produces a double-clickable installer that bundles the entire game — no Python, Node, or terminal required. It is compatible with Steam and other game launchers.

### How it works

1. **Vite build** — React app compiled to `frontend/dist/`
2. **PyInstaller** — Flask server + all Python dependencies + the built frontend bundled into a single binary (`backend/dist/quiplash-server`)
3. **Electron** — The binary is wrapped in an Electron app that spawns it on launch, waits for it to be ready, then opens a `1280×720` game window

### Output

| Platform | File |
|---|---|
| macOS | `dist/Photo Quiplash.dmg` (x64 + arm64) |
| Windows | `dist/Photo Quiplash Setup.exe` |

### Incremental build

```bash
make build-frontend   # step 1 only (fast, ~5s)
make build-backend    # steps 1–2 (slow first run, ~2–3 min)
make build-electron   # steps 1–3 (produces the installer)
```

### Uploaded photos

In the packaged app, photos are stored in a writable user-data directory rather than inside the bundle:

| Platform | Location |
|---|---|
| macOS | `~/Library/Application Support/PhotoQuiplash/uploads/` |
| Windows | `%APPDATA%\PhotoQuiplash\uploads\` |
| Linux | `~/.photoquiplash/uploads/` |

### Steam

Set the Electron `.exe` (Windows) or `.app` bundle (macOS) as the launch target in Steamworks. No Steamworks SDK integration is needed for basic launcher compatibility.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask, Flask-SocketIO |
| WebSockets (dev) | gevent + Flask-SocketIO |
| WebSockets (packaged) | threading async mode (avoids gevent/PyInstaller issues) |
| Image processing | Pillow (server-side resize to 1280px JPEG) |
| Frontend | React, Vite |
| Real-time client | socket.io-client |
| Routing | React Router |
| Image compression | browser-image-compression (client-side pre-compress) |
| QR codes | qrcode.react |
| Desktop app | Electron + electron-builder |
| Binary bundling | PyInstaller |
