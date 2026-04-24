# build.spec  — PyInstaller spec for YT Batch Downloader
# ─────────────────────────────────────────────────────────────────────────────
# FFmpeg is bundled automatically via imageio-ffmpeg.
# End users do NOT need to install FFmpeg.
#
# Build command (from the ytdl_app/ directory):
#   pyinstaller build.spec --clean
# ─────────────────────────────────────────────────────────────────────────────
import os
import sys
import glob
from pathlib import Path

# ── Locate customtkinter assets ───────────────────────────────────────────────
import customtkinter as _ctk
CTK_DIR = Path(_ctk.__file__).parent

# ── Locate imageio_ffmpeg package + verify the FFmpeg binary is present ───────
try:
    import imageio_ffmpeg as _iio_ffmpeg
    IIO_FFMPEG_DIR = Path(_iio_ffmpeg.__file__).parent
    _HAS_IMAGEIO_FFMPEG = True

    # Confirm the binary actually exists so we catch problems at build time
    try:
        _bundled_exe = _iio_ffmpeg.get_ffmpeg_exe()
        print(f"[build.spec] imageio-ffmpeg binary: {_bundled_exe}")
    except Exception as _e:
        print(f"[build.spec] WARNING: imageio_ffmpeg.get_ffmpeg_exe() failed: {_e}")
        print("[build.spec]          The bundled FFmpeg may be missing from the output.")

except ImportError:
    IIO_FFMPEG_DIR = None
    _HAS_IMAGEIO_FFMPEG = False
    print("=" * 70)
    print("ERROR: imageio_ffmpeg is not installed.")
    print("       FFmpeg will NOT be bundled — users must install it manually.")
    print("       Fix: pip install imageio-ffmpeg")
    print("=" * 70)

# ── Icon ──────────────────────────────────────────────────────────────────────
_SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
_ICON_PATH = os.path.join(_SPEC_DIR, "icon.ico")
ICON = _ICON_PATH if os.path.isfile(_ICON_PATH) else None

# ── datas list ────────────────────────────────────────────────────────────────
# Always include customtkinter; add imageio_ffmpeg when available.
_datas = [
    (str(CTK_DIR), "customtkinter"),
]
if _HAS_IMAGEIO_FFMPEG and IIO_FFMPEG_DIR is not None:
    # Bundle the entire imageio_ffmpeg package directory.
    # This includes the "binaries/" sub-folder which holds the static FFmpeg exe.
    _datas.append((str(IIO_FFMPEG_DIR), "imageio_ffmpeg"))

# Bundle yt_dlp_ejs so its JS solver scripts are available in frozen builds.
try:
    import yt_dlp_ejs as _yt_dlp_ejs
    _YT_DLP_EJS_DIR = Path(_yt_dlp_ejs.__file__).parent
    _datas.append((str(_YT_DLP_EJS_DIR), "yt_dlp_ejs"))
    print(f"[build.spec] yt_dlp_ejs bundled from: {_YT_DLP_EJS_DIR}")
except ImportError:
    print("WARNING: yt_dlp_ejs not installed. Fix: pip install yt-dlp-ejs")

# ─────────────────────────────────────────────────────────────────────────────

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
        # ── ffmpeg_manager + conversion_worker + js_runtime_manager ─────────────
        "ffmpeg_manager",
        "conversion_worker",
        "js_runtime_manager",
        # ── yt-dlp-ejs: JS challenge solver scripts (PyPI package) ────────────
        "yt_dlp_ejs",
        "yt_dlp_ejs.yt",
        "yt_dlp_ejs.yt.solver",
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
