# Frontend — Photo Quiplash

React 19 + Vite app. Runs on `http://localhost:5173` in development; served directly by the Flask backend in the packaged executable.

## Pages

| File | Route | Description |
|---|---|---|
| `Home.jsx` | `/` | Create a room (TV) or join with a code (phone) |
| `TV.jsx` | `/room/:code/tv` | All TV screens: lobby, submitting, voting, scores, final |
| `Phone.jsx` | `/room/:code/phone` | All phone screens: lobby, submitting, voting, scores, final |

## Dev Commands

```bash
npm run dev    # start dev server with HMR on :5173
npm test       # run vitest test suite
npm run build  # production build → frontend/dist/
```

## Key Dependencies

| Package | Purpose |
|---|---|
| `react-router-dom` | Client-side routing |
| `socket.io-client` | WebSocket connection to backend |
| `browser-image-compression` | Compress photos client-side before upload |
| `qrcode.react` | QR code display in lobby |

## Vite Proxy

In dev, `/api`, `/socket.io`, and `/uploads` are proxied to `http://localhost:5000` (see `vite.config.js`). No CORS config needed.

In the packaged binary, Flask serves everything from the same origin so no proxy is involved.

## Tests

Tests live in `src/__tests__/`. Run with `npm test` or `make test-frontend` from the repo root.

## Production Build

`npm run build` outputs to `frontend/dist/`. In the packaged app, the PyInstaller binary bundles this directory and Flask serves it via a catch-all route. React Router handles all client-side navigation after the initial page load.
