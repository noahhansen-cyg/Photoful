.PHONY: dev devtest packagetest stop test test-backend test-frontend \
        test-binary install \
        build-frontend build-backend build-electron package package-dir

# Start both servers. Ctrl+C stops everything cleanly.
dev:
	@echo "Starting backend on :5000 and frontend on :5173..."
	@trap 'lsof -ti:5000 -ti:5173 | xargs kill -9 2>/dev/null; kill 0' INT; \
	  (cd backend && python app.py) & \
	  (cd frontend && npm run dev) & \
	  wait

bots ?= 3

# Start servers + bot players for end-to-end testing without extra browser windows.
# Bots create a room automatically and print the TV URL; open it in your browser.
# Override the number of bots with bots=N (max 8): make devtest bots=5
# Ctrl+C stops everything.
devtest:
	@echo "Starting backend, frontend, and $(bots) bot players..."
	@echo "(Bot players will create a room and print the TV URL after ~3 s)"
	@trap 'lsof -ti:5000 -ti:5173 | xargs kill -9 2>/dev/null; kill 0' INT; \
	  (cd backend && python app.py) & \
	  (cd frontend && npm run dev) & \
	  (sleep 3 && cd backend && python bots.py --count $(bots)) & \
	  wait

# Port the packaged app's embedded server listens on during packagetest.
# Fixed (instead of the app's usual random free port) so the bots can find it.
port ?= 5017

# Full end-to-end test of the DESKTOP app (macOS): runs the complete `make
# package` pipeline (dmg + unpacked .app in dist/), launches the actual
# packaged application, then joins bot players to the room you create in it.
#   1. The Photoful window opens at the main menu — click "Play".
#   2. Type the room code shown on the TV screen at the prompt in this terminal.
#   3. Bots join that room; claim Host from your phone/browser and start the game.
# Override the number of bots with bots=N (max 8): make packagetest bots=5
# Ctrl+C stops the bots and quits the app.
packagetest: package
	@APP_BIN="$$(ls -d dist/mac*/Photoful.app 2>/dev/null | head -1)/Contents/MacOS/Photoful"; \
	test -x "$$APP_BIN" || { \
	  echo "Packaged app not found under dist/mac*/Photoful.app — did the build fail?"; \
	  exit 1; }; \
	echo ""; \
	echo "Launching packaged app on port $(port): $$APP_BIN"; \
	trap 'kill $$APP_PID 2>/dev/null; lsof -ti:$(port) | xargs kill -9 2>/dev/null' INT TERM EXIT; \
	PHOTOFUL_PORT=$(port) "$$APP_BIN" & APP_PID=$$!; \
	until curl -sf http://localhost:$(port)/healthz >/dev/null 2>&1; do \
	  kill -0 $$APP_PID 2>/dev/null || { echo "App exited before its server came up."; exit 1; }; \
	  sleep 0.5; \
	done; \
	echo ""; \
	echo "Server is up. In the Photoful window, click Play to create a room."; \
	printf "Enter the room code shown on the TV screen: "; \
	read CODE; \
	cd backend && PHOTOFUL_URL=http://localhost:$(port) \
	  python bots.py "$$CODE" --count $(bots) --tv-base http://localhost:$(port)

# Kill anything still holding the ports
stop:
	@echo "Stopping servers..."
	@lsof -ti:5000 | xargs kill -9 2>/dev/null || true
	@lsof -ti:5173 | xargs kill -9 2>/dev/null || true
	@lsof -ti:$(port) | xargs kill -9 2>/dev/null || true
	@echo "Done."

# Install all dependencies (run once after cloning)
install:
	@echo "Installing Python dependencies..."
	cd backend && pip install -r requirements-dev.txt
	@echo "Installing Node dependencies..."
	cd frontend && npm install
	@echo "All dependencies installed."

# Run all tests
test: test-backend test-frontend

test-backend:
	@echo "Running backend tests..."
	cd backend && python -m pytest tests/ -v

test-frontend:
	@echo "Running frontend tests..."
	cd frontend && npm test

# Automated end-to-end tests against the packaged server binary: spawns the
# real PyInstaller executable and plays a complete game over HTTP + Socket.IO
# (see backend/tests_e2e/). Rebuilds the bundle first so the tests always
# exercise the current code; to rerun against an existing build:
#   cd backend && python -m pytest tests_e2e/ -v
test-binary: build-backend
	@echo "Running binary end-to-end tests..."
	cd backend && python -m pytest tests_e2e/ -v

# ---------------------------------------------------------------------------
# Packaging — produce a distributable Electron app
# ---------------------------------------------------------------------------

# 1. Build the Vite frontend into frontend/dist/
build-frontend:
	@echo "Building React frontend..."
	cd frontend && npm run build

# 2. Bundle the Flask backend + built frontend into a onedir bundle via
#    PyInstaller (same threading/simple-websocket runtime as the web app).
#    Output:   backend/dist/photoful-server/  (folder with the executable inside)
build-backend: build-frontend
	@echo "Installing PyInstaller..."
	pip install pyinstaller
	@echo "Bundling backend with PyInstaller..."
	rm -rf backend/dist backend/build
	cd backend && pyinstaller photoful.spec --distpath dist --workpath build

# 3. Package the Electron wrapper + backend bundle into a platform installer.
#    Output:  dist/Photoful-<ver>.dmg / .zip        (macOS)
#             dist/Photoful Setup <ver>.exe / .zip  (Windows)
#             dist/Photoful-<ver>.AppImage / .tar.gz (Linux)
#    The unpacked builds (dist/mac*, dist/win-unpacked, dist/linux-unpacked)
#    are what you upload to Steam depots.
build-electron: build-backend
	@echo "Installing Electron dependencies..."
	cd electron && npm install
	@echo "Building Electron installer..."
	cd electron && npm run package

# Quick unpacked build (no installer) — fastest way to test the desktop app:
#   dist/mac-arm64/Photoful.app, dist/win-unpacked/, dist/linux-unpacked/
package-dir: build-backend
	cd electron && npm install && npm run package:dir

# Convenience target: run the full packaging pipeline.
package: build-electron
	@echo ""
	@echo "Done. Installer is in dist/"
