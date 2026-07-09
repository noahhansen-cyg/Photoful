"""
Fixtures for end-to-end tests against the packaged PyInstaller binary.

The `server` fixture spawns the actual `photoful-server` executable (the one
`make build-backend` produces and the Electron app ships) and tears it down
when the session ends. Tests talk to it over real HTTP and Socket.IO — the
same transports phones and the Electron window use.

The binary is started with:
  - PORT            → a free port picked at fixture setup
  - PHOTOFUL_TIMER_SCALE=0.2 → every game phase runs at 5x speed so a full
    game (fixed intro/scores screens included) finishes in ~30 s
  - HOME / APPDATA  → a temp dir, so the user-data uploads directory is
    isolated and assertable

Run with `make test-binary` (rebuilds the bundle first), or directly:
    cd backend && python -m pytest tests_e2e/ -v
The suite skips with an explanation if the binary has not been built.
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

TIMER_SCALE = "0.2"
# First launch of a fresh binary can be slow on Windows CI runners
# (Defender scans the unpacked bundle), so the startup budget is generous.
STARTUP_TIMEOUT = 90  # seconds to wait for /healthz after spawning


def _binary_path():
    override = os.environ.get("PHOTOFUL_BINARY")
    if override:
        return Path(override)
    exe = "photoful-server.exe" if sys.platform == "win32" else "photoful-server"
    return Path(__file__).resolve().parent.parent / "dist" / "photoful-server" / exe


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _uploads_root(home):
    """Mirror app.py:_get_upload_dir for a frozen server with HOME/APPDATA=home."""
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Photoful" / "uploads"
    if sys.platform == "win32":
        return home / "Photoful" / "uploads"
    return home / ".photoful" / "uploads"


class ServerHandle:
    def __init__(self, base_url, uploads_root, proc, log_path):
        self.base_url = base_url
        self.uploads_root = uploads_root
        self.proc = proc
        self.log_path = log_path


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    binary = _binary_path()
    if not binary.is_file():
        pytest.skip(
            f"Packaged server binary not found at {binary} — "
            "run `make build-backend` first (or set PHOTOFUL_BINARY)."
        )

    home = tmp_path_factory.mktemp("photoful-home")
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    env = {
        **os.environ,
        "PORT": str(port),
        "PHOTOFUL_TIMER_SCALE": TIMER_SCALE,
        "HOME": str(home),
        "APPDATA": str(home),
    }

    log_path = home / "server.log"
    log_file = open(log_path, "wb")
    proc = subprocess.Popen(
        [str(binary)], env=env, stdout=log_file, stderr=subprocess.STDOUT
    )

    try:
        deadline = time.time() + STARTUP_TIMEOUT
        while True:
            if proc.poll() is not None:
                pytest.fail(
                    f"Server binary exited with code {proc.returncode} before "
                    f"becoming healthy.\n--- server log ---\n"
                    f"{log_path.read_text(errors='replace')}"
                )
            try:
                if requests.get(f"{base_url}/healthz", timeout=1).status_code == 200:
                    break
            except requests.ConnectionError:
                pass
            if time.time() > deadline:
                pytest.fail(
                    f"Server did not respond to /healthz within {STARTUP_TIMEOUT}s."
                    f"\n--- server log ---\n{log_path.read_text(errors='replace')}"
                )
            time.sleep(0.25)

        yield ServerHandle(base_url, _uploads_root(home), proc, log_path)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        log_file.close()
