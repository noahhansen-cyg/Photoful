# PyInstaller spec for Photo Quiplash backend server.
# Run from the backend/ directory:
#   pyinstaller quiplash.spec --distpath dist
#
# The resulting binary (dist/quiplash-server or dist/quiplash-server.exe) bundles:
#   - Flask + Flask-SocketIO (threading async mode) + all Python dependencies
#   - prompts.json
#   - The built React frontend (../frontend/dist → frontend_dist/ inside the archive)
#
# Static assets and prompts.json are accessed at runtime via sys._MEIPASS.
# Uploaded photos go to a writable user-data directory (see app.py:_get_upload_dir).

block_cipher = None

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("prompts.json", "."),
        ("../frontend/dist", "frontend_dist"),
    ],
    hiddenimports=[
        # Flask-SocketIO threading async driver
        "engineio.async_drivers.threading",
        "engineio.async_threading",
        # Flask-SocketIO itself (sometimes missed by the hook)
        "flask_socketio",
        # Pillow image codecs
        "PIL._imaging",
        "PIL.JpegImagePlugin",
        # Werkzeug internals used by Flask at runtime
        "werkzeug.serving",
        "werkzeug.debug",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude gevent entirely — not used in threading mode
        "gevent",
        "geventwebsocket",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="quiplash-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Keep console=True so server logs are visible during development/debugging.
    # Set to False for a silent release build.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
