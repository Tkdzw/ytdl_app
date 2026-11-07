# build.spec — PyInstaller spec for YT Downloader
# ─────────────────────────────────────────────────────────────────────────────
# FFmpeg and Deno are bundled when vendor/ffmpeg and vendor/deno exist
# (build_windows.bat fills them via scripts/fetch_tools.ps1). They land in
# <app>/_internal/tools/, where utils/tool_setup.py looks first.
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

# ── App name / version (app_info.py is the single source of truth) ────────────
import sys as _sys
_sys.path.insert(0, _SPEC_DIR)
import app_info
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)
_ver = tuple(int(x) for x in app_info.VERSION.split(".")) + (0,)
# Shown in the .exe's Properties > Details tab
VERSION_INFO = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_ver, prodvers=_ver),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", app_info.DEVELOPER),
            StringStruct("FileDescription", app_info.APP_NAME),
            StringStruct("FileVersion", app_info.VERSION),
            StringStruct("InternalName", app_info.APP_ID),
            StringStruct("LegalCopyright", app_info.COPYRIGHT),
            StringStruct("OriginalFilename", f"{app_info.APP_ID}.exe"),
            StringStruct("ProductName", app_info.APP_NAME),
            StringStruct("ProductVersion", app_info.VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)
print(f"[build.spec] {app_info.APP_NAME} {app_info.VERSION}")

# ── datas ─────────────────────────────────────────────────────────────────────
_datas = [
    (str(CTK_DIR), "customtkinter"),
]
if _HAS_EJS and YT_DLP_EJS_DIR:
    _datas.append((str(YT_DLP_EJS_DIR), "yt_dlp_ejs"))

# ── Bundled tools (FFmpeg + Deno) ─────────────────────────────────────────────
for _tool, _exe in (("ffmpeg", "ffmpeg.exe"), ("deno", "deno.exe")):
    _src = os.path.join(_SPEC_DIR, "vendor", _tool)
    if os.path.isfile(os.path.join(_src, _exe)):
        _datas.append((_src, os.path.join("tools", _tool)))
        print(f"[build.spec] bundling {_tool}: {_src}")
    else:
        print(f"WARNING: vendor/{_tool} missing - run scripts/fetch_tools.ps1 "
              f"or the app will need {_tool} installed separately.")

# ─────────────────────────────────────────────────────────────────────────────

a = Analysis(
    [os.path.join(_SPEC_DIR, "main.py")],
    pathex=[_SPEC_DIR],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        # ── App modules ───────────────────────────────────────────────────────
        "ffmpeg_manager",
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
        "engine", "engine.downloader", "engine.download_queue",
        "ui", "ui.main_window", "ui.sidebar", "ui.dialogs",
        "ui.tab_downloader", "ui.queue_list", "ui.setup_dialog",
        "ui.tab_history", "ui.tab_settings",
        "utils", "utils.logger", "utils.tool_setup", "utils.error_messages",
        "utils.history_manager", "utils.settings_manager",
        "utils.url_validator", "utils.thumbnail_fetcher",
        "utils.update_checker",
        "app_info", "ui.theme", "ui.tooltip",
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
    name=app_info.APP_ID,
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
    version=VERSION_INFO,
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
    name=app_info.APP_ID,
)
