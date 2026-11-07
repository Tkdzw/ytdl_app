"""
Utility: locate and install the external tools the app needs.

* FFmpeg  — merges video+audio and converts to MP3 (required).
* A JavaScript runtime (Deno / Node.js / Bun / QuickJS) — yt-dlp needs one
  to solve YouTube's player challenges (strongly recommended).

Lookup order (first hit wins):
  1. A folder/binary the user chose in Settings > Tools.
  2. Copies bundled with the app (``tools/`` next to the frozen exe, or
     ``vendor/`` in a source checkout — filled by scripts/fetch_tools.ps1).
  3. The system PATH (refreshed from the registry, so tools installed while
     the app is running are found without a restart).
  4. Well-known install locations (WinGet, Scoop, Chocolatey, Homebrew…).

Installation uses WinGet (Microsoft's package manager, built into Windows
10/11): packages come from the official winget source, and nothing runs
unless the user clicks "Install" in the setup dialog.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from js_runtime_manager import (
    JsRuntimeResult,
    _check_bun,
    _check_deno,
    _check_node,
    _check_qjs,
    detect_js_runtime,
)
from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)

_IS_WIN = sys.platform == "win32"
_EXE = ".exe" if _IS_WIN else ""

# WinGet package ids. yt-dlp.FFmpeg is the FFmpeg build maintained by the
# yt-dlp project; Deno is yt-dlp's default JS runtime and installs per-user
# without admin rights.
FFMPEG_WINGET_ID = "yt-dlp.FFmpeg"
JS_WINGET_ID = "DenoLand.Deno"


# ── Bundled copies ────────────────────────────────────────────────────────────

def _bundle_roots() -> list[str]:
    """Folders that may hold bundled tools (``<root>/ffmpeg``, ``<root>/deno``)."""
    roots: list[str] = []
    if getattr(sys, "frozen", False):
        for base in (getattr(sys, "_MEIPASS", ""), os.path.dirname(sys.executable)):
            if base:
                roots.append(os.path.join(base, "tools"))
    project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    roots.append(os.path.join(project, "vendor"))
    return roots


def bundled_ffmpeg_dir() -> str:
    for root in _bundle_roots():
        d = os.path.join(root, "ffmpeg")
        if os.path.isfile(os.path.join(d, "ffmpeg" + _EXE)):
            return d
    return ""


def bundled_deno_path() -> str:
    for root in _bundle_roots():
        p = os.path.join(root, "deno", "deno" + _EXE)
        if os.path.isfile(p):
            return p
    return ""


# ── PATH refresh ──────────────────────────────────────────────────────────────

def refresh_path_from_registry() -> None:
    """
    Re-read the user + machine PATH from the registry into this process.

    Installers (WinGet included) update PATH in the registry, but a running
    process keeps the copy it started with. Merging it in lets us find a
    freshly installed tool without restarting the app.
    """
    if not _IS_WIN:
        return
    try:
        import winreg
    except ImportError:
        return
    parts: list[str] = []
    for hive, key in (
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ):
        try:
            with winreg.OpenKey(hive, key) as k:
                value, _ = winreg.QueryValueEx(k, "Path")
                parts.extend(os.path.expandvars(value).split(os.pathsep))
        except OSError:
            continue
    current = os.environ.get("PATH", "").split(os.pathsep)
    seen = {p.lower().rstrip("\\") for p in current if p}
    added = [p for p in parts if p and p.lower().rstrip("\\") not in seen]
    if added:
        os.environ["PATH"] = os.pathsep.join(current + added)
        _log.info("PATH refreshed from registry (+%d entries)", len(added))


# ── FFmpeg ────────────────────────────────────────────────────────────────────

def _has_ffmpeg(directory: str) -> bool:
    return bool(directory) and os.path.isfile(os.path.join(directory, "ffmpeg" + _EXE))


def _known_ffmpeg_locations() -> list[str]:
    if _IS_WIN:
        local = os.environ.get("LOCALAPPDATA", "")
        home = os.environ.get("USERPROFILE", "")
        prog = os.environ.get("ProgramFiles", r"C:\Program Files")
        return [
            os.path.join(local, r"Microsoft\WinGet\Links\ffmpeg.exe"),
            os.path.join(local, r"Microsoft\WinGet\Packages\yt-dlp.FFmpeg*\**\bin\ffmpeg.exe"),
            os.path.join(local, r"Microsoft\WinGet\Packages\*FFmpeg*\**\bin\ffmpeg.exe"),
            os.path.join(prog, r"WinGet\Packages\*FFmpeg*\**\bin\ffmpeg.exe"),
            os.path.join(home, r"scoop\shims\ffmpeg.exe"),
            os.path.join(home, r"scoop\apps\ffmpeg\current\bin\ffmpeg.exe"),
            r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
            r"C:\ffmpeg\bin\ffmpeg.exe",
            os.path.join(prog, r"ffmpeg\bin\ffmpeg.exe"),
        ]
    return [
        "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg",
        "/snap/bin/ffmpeg", os.path.expanduser("~/.local/bin/ffmpeg"),
    ]


def find_ffmpeg_dir(saved_dir: str = "") -> str:
    """Return the folder containing the ffmpeg binary, or "" if not found."""
    if _has_ffmpeg(saved_dir):
        return saved_dir
    bundled = bundled_ffmpeg_dir()
    if bundled:
        return bundled
    found = shutil.which("ffmpeg")
    if found:
        return os.path.dirname(os.path.abspath(found))
    for pattern in _known_ffmpeg_locations():
        matches = glob.glob(pattern, recursive=True) if "*" in pattern else (
            [pattern] if os.path.isfile(pattern) else [])
        if matches:
            return os.path.dirname(sorted(matches, key=len, reverse=True)[0])
    return ""


# ── JS runtime ────────────────────────────────────────────────────────────────

_CHECKERS = {"node": _check_node, "deno": _check_deno, "bun": _check_bun, "qjs": _check_qjs}


def runtime_name_for(path: str) -> str:
    base = os.path.basename(path).lower().replace(".exe", "")
    for name in ("node", "deno", "bun", "qjs", "quickjs"):
        if name in base:
            return "qjs" if name == "quickjs" else name
    return "node"


def find_js_runtime(override_path: str = "") -> JsRuntimeResult:
    """User override → bundled Deno → anything installed on the machine."""
    if override_path and os.path.isfile(override_path):
        name = runtime_name_for(override_path)
        checked = _CHECKERS[name](override_path)
        return checked or JsRuntimeResult(name=name, path=override_path,
                                          version="user", available=True)
    bundled = bundled_deno_path()
    if bundled:
        checked = _check_deno(bundled)
        if checked:
            return checked
    return detect_js_runtime()


# ── Combined status ───────────────────────────────────────────────────────────

@dataclass
class ToolStatus:
    ffmpeg_dir: str
    js: JsRuntimeResult

    @property
    def ffmpeg_ok(self) -> bool:
        return bool(self.ffmpeg_dir)

    @property
    def js_ok(self) -> bool:
        return self.js.available

    @property
    def all_ok(self) -> bool:
        return self.ffmpeg_ok and self.js_ok


def detect_tools(settings) -> ToolStatus:
    """Find both tools and store the results where the downloader reads them."""
    refresh_path_from_registry()
    ffmpeg_dir = find_ffmpeg_dir(settings.get("ffmpeg_bin_dir") or "")
    try:
        js = find_js_runtime(settings.get("js_runtime_override_path") or "")
    except Exception as exc:  # detection must never crash startup
        _log.error("JS runtime detection failed: %s", exc)
        js = JsRuntimeResult(name="none", path=None, version="", available=False)
    settings.update({
        "_ffmpeg_location": ffmpeg_dir,
        "_js_runtime_name": js.name if js.available else "",
        "_js_runtime_path": (js.path or "") if js.available else "",
    })
    _log.info("Tools: ffmpeg=%s | js=%s", ffmpeg_dir or "missing",
              f"{js.name} {js.version} ({js.path})" if js.available else "missing")
    return ToolStatus(ffmpeg_dir=ffmpeg_dir, js=js)


# ── WinGet installation ───────────────────────────────────────────────────────

def winget_available() -> bool:
    return _IS_WIN and shutil.which("winget") is not None


# winget's "already installed / no newer version" codes count as success:
# re-detection afterwards decides whether the tool is really usable.
_WINGET_OK_CODES = {0, 0x8A15002B - (1 << 32), 0x8A150061 - (1 << 32)}


def winget_install(package_id: str, on_line: Optional[Callable[[str], None]] = None) -> bool:
    """
    Install *package_id* from the official winget source. Blocking — run it
    in a background thread. Streams readable output lines to *on_line*.
    Returns True if winget reported success (or "already installed").
    """
    cmd = [
        "winget", "install", "--id", package_id, "--exact",
        "--source", "winget",
        "--accept-package-agreements", "--accept-source-agreements",
        "--disable-interactivity", "--silent",
    ]
    _log.info("Running: %s", " ".join(cmd))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=flags,
        )
    except OSError as exc:
        if on_line:
            on_line(f"Could not start winget: {exc}")
        return False

    buf = b""
    assert proc.stdout is not None
    while True:
        chunk = proc.stdout.read(256)
        if not chunk:
            break
        buf += chunk
        # winget redraws progress with \r; treat it as a line break too
        *lines, buf = buf.replace(b"\r", b"\n").split(b"\n")
        for raw in lines:
            line = _clean_winget_line(raw)
            if line and on_line:
                on_line(line)
    tail = _clean_winget_line(buf)
    if tail and on_line:
        on_line(tail)
    code = proc.wait()
    _log.info("winget install %s exited with %s", package_id, code)
    return code in _WINGET_OK_CODES


def _clean_winget_line(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace").strip()
    # drop spinner frames and progress-bar-only lines
    if not text or set(text) <= set("-\\|/ █▒░▓"):
        return ""
    if "█" in text or "▒" in text:
        return ""
    return text
