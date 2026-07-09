# PyInstaller spec for the Photoful server.
# Run from the backend/ directory:
#   pyinstaller photoful.spec --distpath dist --workpath build
#
# Produces a ONEDIR bundle at dist/photoful-server/ containing:
#   photoful-server(.exe)   — the executable
#   _internal/              — Python runtime, dependencies, prompts.json,
#                             and the built React frontend (frontend_dist/)
#
# Onedir (not onefile) on purpose: no temp-dir self-extraction on every
# launch, faster startup, and far fewer antivirus false positives — all of
# which matter for a Steam-distributed game. Electron ships this folder as
# an extraResource and spawns the executable.
#
# The server code is identical to the web app: threading async mode with
# simple-websocket. No gevent anywhere.

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("prompts.json", "."),
        ("../frontend/dist", "frontend_dist"),
    ],
    hiddenimports=[
        # Engine.IO's threading async driver is imported dynamically
        "engineio.async_drivers.threading",
        # WebSocket support for the threading mode (also imported dynamically)
        "simple_websocket",
        # Pillow image codecs
        "PIL._imaging",
        "PIL.JpegImagePlugin",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Not used anywhere — keep the bundle lean even if they happen to be
        # installed in the build environment.
        "gevent",
        "geventwebsocket",
        "eventlet",
        "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="photoful-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Console stays on: Electron captures stdout/stderr for logging, and
    # spawns with windowsHide so no console window appears on Windows.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="photoful-server",
)
