const { app, BrowserWindow } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");

const SERVER_PORT = 5000;
const SERVER_URL  = `http://localhost:${SERVER_PORT}`;

let mainWindow   = null;
let serverProcess = null;

// ---------------------------------------------------------------------------
// Server binary path
// ---------------------------------------------------------------------------

function getServerBinary() {
  if (!app.isPackaged) {
    // Development: server must be started separately (make dev).
    return null;
  }
  const exe = process.platform === "win32"
    ? "quiplash-server.exe"
    : "quiplash-server";
  return path.join(process.resourcesPath, "server", exe);
}

// ---------------------------------------------------------------------------
// Start the bundled Flask server
// ---------------------------------------------------------------------------

function startServer() {
  const bin = getServerBinary();
  if (!bin) {
    console.log("[electron] Dev mode — expecting server already running on :5000");
    return;
  }

  console.log("[electron] Spawning server:", bin);
  serverProcess = spawn(bin, [], {
    env: { ...process.env, ASYNC_MODE: "threading" },
    // On macOS/Linux keep the console window hidden; Windows needs this too.
    windowsHide: true,
  });

  serverProcess.stdout.on("data", (d) => process.stdout.write(`[server] ${d}`));
  serverProcess.stderr.on("data", (d) => process.stderr.write(`[server] ${d}`));

  serverProcess.on("exit", (code) => {
    console.log(`[electron] Server exited with code ${code}`);
    serverProcess = null;
  });
}

// ---------------------------------------------------------------------------
// Poll /healthz until the server is ready
// ---------------------------------------------------------------------------

function waitForServer(retries = 40, intervalMs = 500) {
  return new Promise((resolve, reject) => {
    const attempt = () => {
      http
        .get(`${SERVER_URL}/healthz`, (res) => {
          if (res.statusCode === 200) {
            resolve();
          } else {
            retry();
          }
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
// Create the main window
// ---------------------------------------------------------------------------

async function createWindow() {
  startServer();

  try {
    await waitForServer();
  } catch (err) {
    console.error("[electron] Could not connect to server:", err.message);
    app.quit();
    return;
  }

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 720,
    title: "Photo Quiplash",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  mainWindow.loadURL(SERVER_URL);

  // Allow fullscreen toggle with F11 (default Electron behaviour handles it).
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (serverProcess) {
    console.log("[electron] Killing server process");
    serverProcess.kill();
  }
  // On macOS it's conventional to quit when all windows are closed.
  app.quit();
});

app.on("activate", () => {
  // macOS: re-open window when dock icon is clicked with no windows open.
  if (mainWindow === null) createWindow();
});
