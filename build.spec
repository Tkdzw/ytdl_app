# build.spec  (UPDATED — imageio-ffmpeg integrated)
# ─────────────────────────────────────────────────────────────────────────────
# PyInstaller spec for YT Batch Downloader with self-contained FFmpeg.
#
# Build command (from the ytdl_app/ directory):
#   pyinstaller build.spec --clean
#
# Or use the one-file variant:
#   pyinstaller --onefile --collect-all imageio_ffmpeg main.py
#
# Key change from original spec:
#   imageio_ffmpeg is collected entirely (binaries + package data) so the
#   bundled FFmpeg executable is included inside the frozen application.
#   No end-user installation of FFmpeg is required.
# ─────────────────────────────────────────────────────────────────────────────
import os
import sys
from pathlib import Path

# ── Locate customtkinter assets (themes/images bundled with the package) ─────
import customtkinter as _ctk
CTK_DIR = Path(_ctk.__file__).parent

# ── Locate imageio_ffmpeg data so the FFmpeg binary is bundled ────────────────
try:
    import imageio_ffmpeg as _iio_ffmpeg
    IIO_FFMPEG_DIR = Path(_iio_ffmpeg.__file__).parent
    _HAS_IMAGEIO_FFMPEG = True
except ImportError:
    IIO_FFMPEG_DIR = None
    _HAS_IMAGEIO_FFMPEG = False
    print("WARNING: imageio_ffmpeg not installed; FFmpeg binary will NOT be bundled.")
    print("         Install it with:  pip install imageio-ffmpeg")

# ── Icon: use icon.ico if present next to this spec ──────────────────────────
_SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
_ICON_PATH = os.path.join(_SPEC_DIR, "icon.ico")
ICON = _ICON_PATH if os.path.isfile(_ICON_PATH) else None

# ─────────────────────────────────────────────────────────────────────────────

# Build the datas list — always include customtkinter; add imageio_ffmpeg if present
_datas = [
    (str(CTK_DIR), "customtkinter"),
]
if _HAS_IMAGEIO_FFMPEG and IIO_FFMPEG_DIR is not None:
    # Include the entire imageio_ffmpeg package directory.
    # This bundles the static FFmpeg binary that ships with the package.
    _datas.append((str(IIO_FFMPEG_DIR), "imageio_ffmpeg"))

a = Analysis(
    [os.path.join(_SPEC_DIR, "main.py")],
    pathex=[_SPEC_DIR],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        # ── imageio_ffmpeg ────────────────────────────────────────────────────
        "imageio_ffmpeg",
        "imageio_ffmpeg._utils",
        "imageio_ffmpeg._definitions",
        # ── ffmpeg_manager + conversion_worker (new modules) ──────────────────
        "ffmpeg_manager",
        "conversion_worker",
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
        # ── yt-dlp core + extractors ──────────────────────────────────────────
        "yt_dlp",
        "yt_dlp.extractor",
        "yt_dlp.extractor.youtube",
        "yt_dlp.utils",
        "yt_dlp.compat",
        "yt_dlp.compat._legacy",
        "yt_dlp.compat._deprecated",
        "yt_dlp.utils._legacy",
        "yt_dlp.utils._deprecated",
        # ── Optional yt-dlp extras ────────────────────────────────────────────
        "mutagen",
        "certifi",
        # ── App packages ──────────────────────────────────────────────────────
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
        # ── stdlib networking ─────────────────────────────────────────────────
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
    **({
        "icon": ICON
    } if ICON else {}),
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
