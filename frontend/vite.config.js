import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test-setup.js",
  },
  server: {
    host: true, // bind to 0.0.0.0 so phones on the same WiFi can connect
    proxy: {
      "/api": "http://localhost:5000",
      "/uploads": "http://localhost:5000",
      "/socket.io": {
        target: "http://localhost:5000",
        ws: true,
      },
    },
  },
})
