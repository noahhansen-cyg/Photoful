"""
Browser-level E2E: the TV lobby must advertise a phone-reachable join URL.

Regression coverage for the packaged-app QR bug: the Electron window loads
the TV from http://127.0.0.1:<port>, and the lobby must swap that loopback
host for the machine's LAN IP — otherwise the QR code sends phones to
127.0.0.1 and nobody can join. The HTTP/Socket.IO suite can't catch this
because the bug lives in the bundled React code, so these tests render the
real TV page from the binary in a headless browser, exactly as the Electron
window does.

The join URL is asserted via the visible text under the QR code; the same
variable feeds both (frontend unit tests pin that equivalence).
"""

import socket
from urllib.parse import urlparse

import pytest
import requests

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _lan_ip():
    """Mirror app.py:get_local_ip — the IP the server advertises for phones."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def _create_room(server):
    resp = requests.post(f"{server.base_url}/api/rooms", timeout=10)
    assert resp.status_code == 201
    return resp.json()["room_code"]


@pytest.fixture(scope="module")
def join_url(server, page):
    """Load the TV lobby the way the Electron window does and read the join URL."""
    from playwright.sync_api import expect

    if _lan_ip() is None:
        pytest.skip("no LAN interface on this machine — QR would show localhost")
    code = _create_room(server)
    page.goto(f"{server.base_url}/room/{code}/tv")
    # The lobby renders window.location.host first and swaps in the LAN IP
    # once its /api/server-info fetch resolves — wait out that swap. On a
    # regression the text stays loopback; swallow the timeout so the asserts
    # below report the actual URL instead.
    locator = page.get_by_test_id("join-url")
    try:
        expect(locator).not_to_contain_text("127.0.0.1", timeout=10_000)
    except AssertionError:
        pass
    return code, locator.inner_text()


def test_join_url_uses_lan_ip_not_loopback(server, join_url):
    code, url = join_url
    parsed = urlparse(url)
    assert parsed.hostname not in LOOPBACK_HOSTS, (
        f"TV lobby advertises {url} — phones cannot reach a loopback address"
    )
    assert parsed.hostname == _lan_ip()
    assert parsed.port == urlparse(server.base_url).port
    assert parsed.path == f"/room/{code}/phone"


def test_join_url_serves_the_phone_page(page, join_url):
    """The advertised URL must actually work: the server listens on the LAN
    interface and serves the phone join page there, not just on loopback."""
    _, url = join_url
    page.goto(url)
    page.get_by_placeholder("Your name").wait_for(timeout=10_000)
