const { app, BrowserWindow, dialog } = require("electron");
const { spawn, spawnSync } = require("child_process");
const path = require("path");
const http = require("http");
const net = require("net");

let mainWindow    = null;
let serverProcess = null;
let serverPort    = null;
let quitting      = false;

// Ring buffer of recent server output, shown in the error dialog if the
// server dies so users can report something actionable.
const serverLog = [];
function logServer(chunk) {
  const line = chunk.toString();
  process.stdout.write(`[server] ${line}`);
  serverLog.push(line);
  while (serverLog.length > 50) serverLog.shift();
}

// ---------------------------------------------------------------------------
// Server binary (PyInstaller onedir bundle shipped as an extraResource)
// ---------------------------------------------------------------------------

function getServerBinary() {
  const exe = process.platform === "win32"
    ? "photoful-server.exe"
    : "photoful-server";
  return path.join(process.resourcesPath, "server", exe);
}

// Ask the OS for a free port instead of hardcoding one. Port 5000 in
// particular is taken by AirPlay Receiver on modern macOS.
function findFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

function startServer(port) {
  const bin = getServerBinary();
  console.log(`[electron] Spawning server on port ${port}:`, bin);

  serverProcess = spawn(bin, [], {
    env: { ...process.env, PORT: String(port) },
    windowsHide: true,
  });

  serverProcess.stdout.on("data", logServer);
  serverProcess.stderr.on("data", logServer);

  serverProcess.on("exit", (code) => {
    console.log(`[electron] Server exited with code ${code}`);
    serverProcess = null;
    if (!quitting) {
      dialog.showErrorBox(
        "Photoful — server stopped",
        `The game server exited unexpectedly (code ${code}).\n\nRecent log:\n` +
          serverLog.slice(-15).join("")
      );
      app.quit();
    }
  });

  serverProcess.on("error", (err) => {
    console.error("[electron] Failed to spawn server:", err.message);
  });
}

function stopServer() {
  if (!serverProcess) return;
  console.log("[electron] Stopping server process");
  const proc = serverProcess;
  serverProcess = null;
  if (process.platform === "win32") {
    // Kill the whole process tree; a bare .kill() can orphan children.
    spawnSync("taskkill", ["/pid", String(proc.pid), "/T", "/F"]);
  } else {
    proc.kill();
  }
}

// ---------------------------------------------------------------------------
// Poll /healthz until the server is ready
// ---------------------------------------------------------------------------

function waitForServer(url, retries = 60, intervalMs = 500) {
  return new Promise((resolve, reject) => {
    const attempt = () => {
      http
        .get(`${url}/healthz`, (res) => {
          res.resume();
          if (res.statusCode === 200) resolve();
          else retry();
        })
        .on("error", retry);
    };

    const retry = () => {
      if (retries-- <= 0) {
        reject(new Error("Server failed to start within the timeout"));
      } else {
        setTimeout(attempt, intervalMs);
      }
    };

    attempt();
  });
}

// ---------------------------------------------------------------------------
// Main window
// ---------------------------------------------------------------------------

async function resolveAppUrl() {
  if (!app.isPackaged) {
    // Development: use the live stack from `make dev` (Vite on :5173,
    // which proxies to Flask), or whatever ELECTRON_START_URL points at.
    return process.env.ELECTRON_START_URL || "http://localhost:5173";
  }

  // Reuse the already-running server if the window is being re-created
  // (macOS dock activate).
  if (serverProcess && serverPort) {
    return `http://127.0.0.1:${serverPort}`;
  }

  serverPort = await findFreePort();
  const url = `http://127.0.0.1:${serverPort}`;
  startServer(serverPort);
  await waitForServer(url);
  return url;
}

async function createWindow() {
  let url;
  try {
    url = await resolveAppUrl();
  } catch (err) {
    dialog.showErrorBox(
      "Photoful — could not start",
      `${err.message}\n\nRecent log:\n${serverLog.slice(-15).join("")}`
    );
    quitting = true;
    stopServer();
    app.quit();
    return;
  }

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 720,
    title: "Photoful",
    fullscreenable: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  mainWindow.loadURL(url);

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(createWindow);

  app.on("before-quit", () => {
    quitting = true;
    stopServer();
  });

  app.on("window-all-closed", () => {
    app.quit();
  });

  app.on("activate", () => {
    if (mainWindow === null && !quitting) createWindow();
  });
}
