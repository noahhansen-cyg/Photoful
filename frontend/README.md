# Frontend — Photo Quiplash

React 18 + Vite app. Runs on `http://localhost:5173` in development.

## Pages

| File | Route | Description |
|---|---|---|
| `Home.jsx` | `/` | Create a room (TV) or join with a code (phone) |
| `TV.jsx` | `/room/:code/tv` | All TV screens: lobby, submitting, voting, scores, final |
| `Phone.jsx` | `/room/:code/phone` | All phone screens: lobby, submitting, voting, scores, final |

## Dev Commands

```bash
npm run dev    # start dev server with HMR
npm test       # run vitest test suite
npm run build  # production build
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

## Tests

Tests live in `src/__tests__/`. Run with `npm test` or `make test-frontend` from the repo root.
