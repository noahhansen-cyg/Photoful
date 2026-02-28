# Code Review Suggestions

Collected from automated reviews by Gemini and OpenAI Codex (February 2026).

---

## Gemini

### 1. Room Cleanup — Memory Leak
`backend/rooms.py` — Rooms stored in-memory dict are never removed. Long-running servers will OOM.
**Fix:** Track `last_activity` per room; run a background gevent task to prune stale rooms.

### 2. Upload Cleanup — Disk Growth
`backend/app.py`, `backend/rooms.py` — Uploaded images (`backend/uploads/<code>/`) are never deleted.
**Fix:** Delete upload directories when rooms expire or reach `final` state.

### 3. Fragile Reconnection Logic
`backend/rooms.py:42` — Reconnection matches on `name + role`, which risks session hijacking if two players use the same name.
**Fix:** Issue a unique `session_token` (UUID) on first join, persist in `localStorage`, and use it for reconnection auth.

### 4. Hardcoded Secret Key
`backend/app.py:28` — `SECRET_KEY = "dev-secret-change-in-prod"` is hardcoded.
**Fix:** Use `os.environ.get("SECRET_KEY", "fallback")`.

### 5. Frontend File Size & Styles
`frontend/src/pages/Phone.jsx`, `TV.jsx` — Large inline style objects make files long and hard to maintain.
**Fix:** Extract styles to separate files (e.g., `Phone.styles.js`) or use CSS modules. Memoize static components with `React.memo`.

### 6. Timer Grace Period
`backend/game.py:214` — Timer uses `gevent.sleep()` which may fire late under load.
**Fix:** Add 1-2s grace period before backend auto-advances to account for network latency.

### 7. Socket Listener Cleanup
`frontend/src/socket.js` — Ensure all listeners are removed on unmount to prevent browser memory leaks.

### 8. Docker Volumes for Uploads
`docker-compose.yml` — No volume mount for `uploads/` directory; images don't persist across restarts.

### 9. TV Reveal Animation
`frontend/src/pages/TV.jsx:150` — 3s delay for photo reveal could use a fade/pop-in animation for more impact.

---

## OpenAI Codex

### 1. [Critical] Host Lockout After Disconnect
`backend/rooms.py:55`, `backend/app.py:190` — `host_id` is never cleared when host disconnects in lobby, but `host:claim` blocks when `host_id` is set. Host role becomes permanently locked.
**Fix:** Clear stale `host_id` on disconnect in lobby, or treat disconnected host as unclaimed in `host:claim`.

### 2. [Critical] Session Takeover via Name Collision
`backend/rooms.py:46`, `backend/app.py:137` — Reconnect keyed on `name + role` enables accidental collisions and host takeover.
**Fix:** Use server-issued reconnect token/player ID persisted on client.

### 3. [High] Upload Failure Not Handled
`frontend/src/pages/Phone.jsx:219-227` — Phone marks upload as submitted even when `fetch` fails; does not check `res.ok` before emitting `submit:photo`.
**Fix:** Gate on `res.ok` and `data.image_url`; surface error UI; only set `submitted` after server acceptance.

### 4. [High] No Input Validation on `player:join`
`backend/app.py:124`, `frontend/src/pages/TV.jsx:288` — `name` and `role` are not validated. Empty names crash TV rendering (`name[0].toUpperCase()`).
**Fix:** Validate/normalize on backend: whitelist `role`, require non-empty bounded `name`.

### 5. [High] Client-Provided `image_url` Trusted
`backend/app.py:231`, `backend/rooms.py:73` — Server trusts client `image_url` in `submit:photo`; clients can inject arbitrary URLs.
**Fix:** Validate URL starts with `/uploads/<room>/` or bind submissions to upload tokens.

### 6. [Medium] 2-Player Vote Timeout Burns Full Timer
`backend/game.py:108`, `backend/app.py:287` — With 2 players, no eligible voters exist but auto-advance only triggers after vote events (which never come). Full timeout elapses.
**Fix:** On entering voting, immediately skip if `all_voted()` is already true.

### 7. [Medium] Timer Race Condition
`backend/app.py:253,289`, `backend/game.py:223` — Early-advance and timer callback both call `advance_state` without a generation guard.
**Fix:** Add per-room timer generation token; ignore stale callbacks.

### 8. [Medium] Upload Endpoint Not Hardened
`backend/app.py:86,103` — No explicit size limit, no guarded PIL decode path.
**Fix:** Set `MAX_CONTENT_LENGTH`; catch PIL decode errors; reject non-images.

### 9. [Medium] Heavy State Broadcast
`backend/rooms.py:125`, `backend/app.py:169,251,283` — Full prompt/vote internals sent to all clients on every change.
**Fix:** Send role-specific minimal payloads or delta events; omit voter identities from phone clients.

### 10. [Medium] No Room/Upload Lifecycle Cleanup
`backend/rooms.py:5`, `backend/app.py:99` — Memory and disk grow unbounded.
**Fix:** Add room TTL + garbage collection; delete upload directories on room expiry.

### 11. [Low] Blob Preview URLs Never Revoked
`frontend/src/pages/Phone.jsx:239` — `URL.createObjectURL` calls without `revokeObjectURL` leak memory on retakes.
**Fix:** Call `URL.revokeObjectURL` when replacing/unmounting preview.

### 12. [Low] Config & Docs Mismatches
`backend/app.py:30,32,309`, `README.md:105`, `backend/game.py:16` — Hardcoded dev secret, open CORS, timeout mismatch (README says 90s, code uses 120s).
**Fix:** Move config to env vars; align docs with actual constants.

### Coverage Gaps
- Missing tests for host disconnect/reclaim path (stale `host_id`)
- Missing frontend tests for failed upload response (`res.ok === false`)
