.PHONY: dev devtest packagetest stop test test-backend test-frontend install \
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

# Path to the PyInstaller server executable produced by build-backend / package
# (onedir bundle — the executable lives inside the dist/photoful-server/ folder)
SERVER_BIN := backend/dist/photoful-server/photoful-server

# Run the PACKAGED server binary + bot players, like devtest but against the
# real production build (frontend is served by the binary on :5000).
# Requires a prior `make build-backend` (or `make package`).
# Override the number of bots with bots=N (max 8): make packagetest bots=5
# Ctrl+C stops everything.
packagetest:
	@test -x "$(SERVER_BIN)" || { \
	  echo "Packaged server not found at $(SERVER_BIN)."; \
	  echo "Run 'make build-backend' (or 'make package') first."; \
	  exit 1; }
	@echo "Starting packaged server ($(SERVER_BIN)) and $(bots) bot players..."
	@echo "(Bots will create a room and print the TV URL once the server is up)"
	@trap 'lsof -ti:5000 | xargs kill -9 2>/dev/null; kill 0' INT; \
	  PORT=5000 ./$(SERVER_BIN) & \
	  (until curl -sf http://localhost:5000/healthz >/dev/null 2>&1; do sleep 0.5; done; \
	   cd backend && python bots.py --count $(bots) --tv-base http://localhost:5000) & \
	  wait

# Kill anything still holding the ports
stop:
	@echo "Stopping servers..."
	@lsof -ti:5000 | xargs kill -9 2>/dev/null || true
	@lsof -ti:5173 | xargs kill -9 2>/dev/null || true
	@echo "Done."

# Install all dependencies (run once after cloning)
install:
	@echo "Installing Python dependencies..."
	cd backend && pip install -r requirements.txt
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
