# build.spec — PyInstaller spec for YT Batch Downloader
# ─────────────────────────────────────────────────────────────────────────────
# FFmpeg is NOT bundled. Users must install FFmpeg separately and set the
# bin folder in Settings > Tools, or add it to their system PATH.
# Download FFmpeg: https://ffmpeg.org/download.html
#
# Build command (from the ytdl_app/ directory):
#   pyinstaller build.spec --clean
# ─────────────────────────────────────────────────────────────────────────────
import os
from pathlib import Path

# ── Locate customtkinter assets ───────────────────────────────────────────────
import customtkinter as _ctk
CTK_DIR = Path(_ctk.__file__).parent

# ── Locate yt_dlp_ejs scripts ────────────────────────────────────────────────
try:
    import yt_dlp_ejs as _yt_dlp_ejs
    YT_DLP_EJS_DIR = Path(_yt_dlp_ejs.__file__).parent
    _HAS_EJS = True
    print(f"[build.spec] yt_dlp_ejs: {YT_DLP_EJS_DIR}")
except ImportError:
    YT_DLP_EJS_DIR = None
    _HAS_EJS = False
    print("WARNING: yt_dlp_ejs not installed. Fix: pip install yt-dlp-ejs")

# ── Icon ──────────────────────────────────────────────────────────────────────
_SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
_ICON_PATH = os.path.join(_SPEC_DIR, "icon.ico")
ICON = _ICON_PATH if os.path.isfile(_ICON_PATH) else None

# ── datas ─────────────────────────────────────────────────────────────────────
_datas = [
    (str(CTK_DIR), "customtkinter"),
]
if _HAS_EJS and YT_DLP_EJS_DIR:
    _datas.append((str(YT_DLP_EJS_DIR), "yt_dlp_ejs"))

# ─────────────────────────────────────────────────────────────────────────────

a = Analysis(
    [os.path.join(_SPEC_DIR, "main.py")],
    pathex=[_SPEC_DIR],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        # ── App modules ───────────────────────────────────────────────────────
        "ffmpeg_manager",
        "conversion_worker",
        "js_runtime_manager",
        # ── yt-dlp-ejs ────────────────────────────────────────────────────────
        "yt_dlp_ejs",
        # ── CustomTkinter / Tk ────────────────────────────────────────────────
        "customtkinter",
        "tkinter",
        "tkinter.filedialog",
        "tkinter.messagebox",
        # ── Pillow ────────────────────────────────────────────────────────────
        "PIL",
        "PIL._imagingtk",
        "PIL.Image",
        "PIL.ImageDraw",
        "PIL.ImageFilter",
        # ── yt-dlp ────────────────────────────────────────────────────────────
        "yt_dlp",
        "yt_dlp.extractor",
        "yt_dlp.extractor.youtube",
        "yt_dlp.utils",
        "yt_dlp.compat",
        "yt_dlp.compat._legacy",
        "yt_dlp.compat._deprecated",
        "yt_dlp.utils._legacy",
        "yt_dlp.utils._deprecated",
        "mutagen",
        "certifi",
        # ── App packages ──────────────────────────────────────────────────────
        "engine", "engine.downloader",
        "ui", "ui.main_window", "ui.sidebar", "ui.dialogs",
        "ui.tab_downloader", "ui.tab_batch_queue",
        "ui.tab_history", "ui.tab_settings",
        "utils", "utils.logger", "utils.ffmpeg_checker",
        "utils.history_manager", "utils.settings_manager",
        "utils.url_validator", "utils.thumbnail_fetcher",
        "utils.update_checker",
        # ── stdlib ────────────────────────────────────────────────────────────
        "email", "email.mime", "email.mime.text", "email.mime.multipart",
        "email.header", "email.utils",
        "http", "http.client", "http.cookiejar", "http.cookies",
        "urllib", "urllib.request", "urllib.parse", "urllib.error",
        "urllib.response",
        "xml", "xml.etree", "xml.etree.ElementTree",
        "html", "html.parser",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["unittest", "pydoc", "doctest", "tkinter.test", "lib2to3"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="YTBatchDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    **({ "icon": ICON } if ICON else {}),
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
