# Photoful

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
photoful/
├── backend/
│   ├── app.py           # Flask app, REST routes, WebSocket events
│   ├── game.py          # State machine, prompt assignment, scoring
│   ├── rooms.py         # In-memory room/player state management
│   ├── bots.py          # Bot players for local testing (make devtest)
│   ├── prompts.json     # Bank of 46 photo prompts
│   ├── photoful.spec    # PyInstaller spec — bundles server into a binary
│   ├── tests/           # Unit tests (in-process, no network)
│   ├── tests_e2e/       # End-to-end tests against the packaged binary
│   ├── uploads/         # Uploaded photos (created at runtime)
│   └── requirements.txt # runtime deps (requirements-dev.txt adds test deps)
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
| `make test` | Run all unit tests (backend + frontend) |
| `make test-backend` | Run backend pytest suite only |
| `make test-frontend` | Run frontend vitest suite only |
| `make test-binary` | Build the server binary, then run automated end-to-end tests against it |

### Packaging

| Command | Description |
|---|---|
| `make build-frontend` | Build the React app into `frontend/dist/` |
| `make build-backend` | Bundle Flask + frontend into `backend/dist/photoful-server/` via PyInstaller |
| `make build-electron` | Wrap the server bundle in an Electron installer |
| `make package-dir` | Fast unpacked desktop build (no installer) for local testing |
| `make package` | Full pipeline — outputs installer to `dist/` |
| `make packagetest` | Build the full desktop package, launch the app, and join bots to your room |

---

## Running Manually

### Backend

```bash
cd backend
pip install -r requirements-dev.txt
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

### Automated binary tests

`make test-binary` builds the PyInstaller bundle and runs `backend/tests_e2e/` against the actual executable: it spawns the binary, verifies the embedded React app is served, and plays a complete 4-player game (both photo rounds, the caption round, restart) over real HTTP + Socket.IO connections — the same transports phones use. Game timers run at 5x speed via `PHOTOFUL_TIMER_SCALE`, so the whole suite takes under a minute after the build.

The same suite runs in CI on Linux, macOS, and Windows on every push and pull request (`.github/workflows/build.yml`), so packaging breakage — a missing hidden import, an asset that didn't make it into the bundle — is caught on every shipping platform before merge.

```bash
make test-binary                              # rebuild bundle + run suite
cd backend && python -m pytest tests_e2e/ -v  # rerun against the existing build
```

### Interactive test of the desktop app

`make packagetest` tests the real desktop app end-to-end: it runs the full `make package` pipeline (dmg installer + unpacked `.app` in `dist/`), launches the packaged application itself (macOS), and joins bot players to the room you create in its window. The app is pinned to a known port (`PHOTOFUL_PORT`, default 5017, override with `port=N`) so the bots can reach the embedded server.

```bash
make packagetest     # or: make packagetest bots=5
# → the Photoful window opens; click Play
# → type the room code from the TV screen at the terminal prompt; bots join
# → navigate to http://localhost:5017 on your phone/browser, enter the code, join as Host
# → Ctrl+C stops the bots and quits the app
```

Note: uploads in the packaged build go to the user-data directory (e.g. `~/Library/Application Support/Photoful/uploads` on macOS), not `backend/uploads/`.

---

## Packaging as a Desktop App

`make package` produces a double-clickable installer that bundles the entire game — no Python, Node, or terminal required. It is compatible with Steam and other game launchers.

**The desktop app is the product.** The React frontend is not a separate web app — it is the game's UI, compiled into the binary and served by the embedded Flask server to the game window and to players' phones over LAN. Development mode (`make dev`) runs the exact same Flask + Flask-SocketIO threading/simple-websocket stack; the only packaged-app differences are where uploads are written (user-data dir) and that the port is picked dynamically at launch.

### How it works

1. **Vite build** — React app compiled to `frontend/dist/`
2. **PyInstaller (onedir)** — Flask server + dependencies + the built frontend bundled into `backend/dist/photoful-server/` (a folder, not a single-file exe: faster startup, no temp-dir self-extraction, far fewer antivirus false positives)
3. **Electron** — ships that folder as a resource; on launch it picks a **free port** (never a hardcoded one — macOS AirPlay squats on 5000), spawns the server with `PORT=<port>`, waits for `/healthz`, and opens a `1280×720` game window. Phones join over LAN exactly like the web version, via the QR code on the TV screen

### Output

| Platform | Installer | Steam depot (unpacked) |
|---|---|---|
| macOS | `dist/Photoful-<ver>.dmg` / `.zip` | `dist/mac*/Photoful.app` |
| Windows | `dist/Photoful Setup <ver>.exe` / `.zip` | `dist/win-unpacked/` |
| Linux | `dist/Photoful-<ver>.AppImage` / `.tar.gz` | `dist/linux-unpacked/` |

### Incremental build

```bash
make build-frontend   # step 1 only (fast, ~5s)
make build-backend    # steps 1–2 (slow first run, ~2–3 min)
make package-dir      # steps 1–3, unpacked app only (fastest way to test)
make build-electron   # steps 1–3 (produces the installer)
```

To test the desktop app locally: `make package-dir`, then open `dist/mac-arm64/Photoful.app` (or the `-unpacked` folder on Windows/Linux).

You can also test the exact server the app will ship without Electron:

```bash
make build-backend
PORT=8934 ./backend/dist/photoful-server/photoful-server
# open http://localhost:8934 — full game, same as the web app
```

### Building for all three platforms

PyInstaller can't cross-compile, so each OS builds its own bundle. The GitHub Actions workflow `.github/workflows/package.yml` builds macOS, Windows, and Linux in one go — trigger it from the Actions tab, or push a tag like `v0.2.0`. Each platform uploads two artifacts: the installers, and the unpacked directory for Steam.

### Uploaded photos

In the packaged app, photos are stored in a writable user-data directory rather than inside the bundle:

| Platform | Location |
|---|---|
| macOS | `~/Library/Application Support/Photoful/uploads/` |
| Windows | `%APPDATA%\Photoful\uploads\` |
| Linux | `~/.photoful/uploads/` |

### Steam

1. In Steamworks, create one depot per platform and upload the unpacked builds (`dist/mac*/Photoful.app`, `dist/win-unpacked/`, `dist/linux-unpacked/`) via SteamPipe/steamcmd.
2. Launch options: `Photoful.exe` (Windows), `Photoful.app` (macOS), `photoful` (Linux).
3. No Steamworks SDK integration is needed for basic launcher compatibility. Players' phones connect over the local network, so the game needs no Steam networking.
4. For public release you will want code signing (macOS notarization, Windows Authenticode) — unsigned builds trigger Gatekeeper/SmartScreen warnings outside Steam, though Steam's own client bypasses most of this.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask, Flask-SocketIO |
| WebSockets | threading async mode + simple-websocket — identical in dev and the packaged app |
| Image processing | Pillow (server-side resize to 1280px JPEG) |
| Frontend | React, Vite |
| Real-time client | socket.io-client |
| Routing | React Router |
| Image compression | browser-image-compression (client-side pre-compress) |
| QR codes | qrcode.react |
| Desktop app | Electron + electron-builder |
| Binary bundling | PyInstaller |
