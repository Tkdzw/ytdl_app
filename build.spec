# build.spec
# ─────────────────────────────────────────────────────────────────────────────
# PyInstaller spec for YT Batch Downloader
# Run from the ytdl_app/ directory:
#   pyinstaller build.spec --clean
# ─────────────────────────────────────────────────────────────────────────────
import os
import sys
from pathlib import Path

# ── Locate customtkinter assets (themes/images bundled with the package) ─────
import customtkinter as _ctk
CTK_DIR = Path(_ctk.__file__).parent

# ── Icon: use icon.ico if present next to this spec, otherwise no icon ────────
_SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))   # folder containing build.spec
_ICON_PATH = os.path.join(_SPEC_DIR, "icon.ico")
ICON = _ICON_PATH if os.path.isfile(_ICON_PATH) else None

# ─────────────────────────────────────────────────────────────────────────────

a = Analysis(
    [os.path.join(_SPEC_DIR, "main.py")],
    pathex=[_SPEC_DIR],
    binaries=[],
    datas=[
        # CustomTkinter themes, images, fonts
        (str(CTK_DIR), "customtkinter"),
    ],
    hiddenimports=[
        # CustomTkinter / Tk
        "customtkinter",
        "tkinter",
        "tkinter.filedialog",
        "tkinter.messagebox",
        # Pillow
        "PIL",
        "PIL._imagingtk",
        "PIL.Image",
        "PIL.ImageDraw",
        "PIL.ImageFilter",
        # yt-dlp core + all extractors
        "yt_dlp",
        "yt_dlp.extractor",
        "yt_dlp.extractor.youtube",
        "yt_dlp.utils",
        "yt_dlp.compat",
        "yt_dlp.compat._legacy",
        "yt_dlp.compat._deprecated",
        "yt_dlp.utils._legacy",
        "yt_dlp.utils._deprecated",
        # Optional yt-dlp extras (present on some systems)
        "mutagen",
        "certifi",
        # App packages
        "engine",
        "engine.downloader",
        "ui",
        "ui.main_window",
        "ui.sidebar",
        "ui.dialogs",
        "ui.tab_downloader",
        "ui.tab_batch_queue",
        "ui.tab_history",
        "ui.tab_settings",
        "utils",
        "utils.logger",
        "utils.ffmpeg_checker",
        "utils.history_manager",
        "utils.settings_manager",
        "utils.url_validator",
        "utils.thumbnail_fetcher",
        "utils.update_checker",
        # stdlib networking chain required by urllib.request and yt-dlp
        "email",
        "email.mime",
        "email.mime.text",
        "email.mime.multipart",
        "email.header",
        "email.utils",
        "http",
        "http.client",
        "http.cookiejar",
        "http.cookies",
        "urllib",
        "urllib.request",
        "urllib.parse",
        "urllib.error",
        "urllib.response",
        "xml",
        "xml.etree",
        "xml.etree.ElementTree",
        "html",
        "html.parser",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Only exclude modules with zero transitive use in our code or deps.
        # IMPORTANT: do NOT exclude email, http, urllib, xml, difflib —
        # urllib.request imports email; yt-dlp needs http/urllib/xml.
        "unittest",
        "pydoc",
        "doctest",
        "tkinter.test",
        "lib2to3",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # False only for --onefile; keep True for folder build
    name="YTBatchDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                       # compress binaries (needs UPX on PATH, safe to omit)
    upx_exclude=[],
    console=False,                  # no black terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    **({"icon": ICON} if ICON else {}),   # only set icon if the file exists
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="YTBatchDownloader",
)
