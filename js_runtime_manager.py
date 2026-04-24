"""
js_runtime_manager.py
─────────────────────────────────────────────────────────────────────────────
Detects an available JavaScript runtime for yt-dlp's YouTube extractor.

Since yt-dlp 2025.x, a JS runtime is REQUIRED to extract many YouTube videos.
Without one, yt-dlp falls back to a degraded client list and many videos fail
with "This video is not available" even though they are perfectly accessible.

Supported runtimes (in preference order)
──────────────────────────────────────────
    node    Node.js ≥ 20   — most common, ships with almost every dev machine
    qjs     QuickJS        — tiny standalone binary (~1 MB), no npm needed
    deno    Deno ≥ 2.0     — modern alternative runtime
    bun     Bun ≥ 1.0.31   — fast JS/TS runtime

Public API
──────────
    detect_js_runtime() -> JsRuntimeResult
        Returns the best available runtime, or a "none found" result.

    build_js_runtimes_param(result: JsRuntimeResult) -> dict | None
        Returns a value suitable for yt-dlp's ``js_runtimes`` YoutubeDL param.

    get_runtime_install_hint() -> str
        Returns a human-readable install suggestion for the UI.
"""

from __future__ import annotations

import glob
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

_log = logging.getLogger(__name__)

# ── Runtime registry ──────────────────────────────────────────────────────────

@dataclass
class JsRuntimeResult:
    name: str               # "node" | "qjs" | "deno" | "bun" | "none"
    path: Optional[str]     # absolute path to binary, or None
    version: str            # e.g. "22.3.0" or "unknown"
    available: bool         # True if a working binary was found

    @property
    def yt_dlp_key(self) -> str:
        """Key as expected by yt-dlp's js_runtimes param."""
        return self.name  # node / qjs / deno / bun


_NONE_RESULT = JsRuntimeResult(name="none", path=None, version="", available=False)


# ── Version extraction helpers ────────────────────────────────────────────────

def _run_version(path: str, args: list[str], ignore_nonzero: bool = False) -> str:
    """Run *path args* and return combined stdout+stderr, or '' on failure."""
    try:
        result = subprocess.run(
            [path] + args,
            capture_output=True,
            timeout=6,
            text=True,
            errors="replace",
        )
        if result.returncode != 0 and not ignore_nonzero:
            return ""
        return (result.stdout + result.stderr).strip()
    except Exception:
        return ""


def _check_node(path: str) -> Optional[JsRuntimeResult]:
    out = _run_version(path, ["--version"])
    if not out:
        return None
    # Node prints "v22.3.0"
    version = out.lstrip("v").split()[0]
    try:
        major = int(version.split(".")[0])
        if major < 20:
            _log.debug("Node at %s is v%s (< 20), skipping", path, version)
            return None
    except ValueError:
        pass
    return JsRuntimeResult(name="node", path=path, version=version, available=True)


def _check_qjs(path: str) -> Optional[JsRuntimeResult]:
    # qjs --help exits with code 1 but prints version info
    out = _run_version(path, ["--help"], ignore_nonzero=True)
    if not out or "QuickJS" not in out:
        return None
    import re
    m = re.search(r"QuickJS(?:-ng)?\s+version\s+(\S+)", out)
    version = m.group(1) if m else "unknown"
    return JsRuntimeResult(name="qjs", path=path, version=version, available=True)


def _check_deno(path: str) -> Optional[JsRuntimeResult]:
    out = _run_version(path, ["--version"])
    if not out or "deno" not in out.lower():
        return None
    import re
    m = re.search(r"deno\s+(\S+)", out, re.IGNORECASE)
    version = m.group(1) if m else "unknown"
    try:
        major, minor = int(version.split(".")[0]), int(version.split(".")[1])
        if major < 2:
            _log.debug("Deno at %s is v%s (< 2.0), skipping", path, version)
            return None
    except (ValueError, IndexError):
        pass
    return JsRuntimeResult(name="deno", path=path, version=version, available=True)


def _check_bun(path: str) -> Optional[JsRuntimeResult]:
    out = _run_version(path, ["--version"])
    if not out:
        return None
    version = out.strip().split()[0]
    return JsRuntimeResult(name="bun", path=path, version=version, available=True)


# ── Platform-specific search locations ────────────────────────────────────────

def _windows_node_candidates() -> list[str]:
    local = os.environ.get("LOCALAPPDATA", "")
    prog  = os.environ.get("ProgramFiles",  r"C:\Program Files")
    home  = os.environ.get("USERPROFILE",   "")

    patterns = [
        # WinGet
        os.path.join(local, r"Microsoft\WinGet\Packages\OpenJS.NodeJS*\**\node.exe"),
        os.path.join(local, r"Microsoft\WinGet\Links\node.exe"),
        # nvm-windows
        os.path.join(local, r"nvm\v*\node.exe"),
        # Volta
        os.path.join(local, r"Volta\bin\node.exe"),
        # Scoop
        os.path.join(home,  r"scoop\shims\node.exe"),
        os.path.join(home,  r"scoop\apps\nodejs\current\node.exe"),
        # Chocolatey
        r"C:\ProgramData\chocolatey\bin\node.exe",
        r"C:\ProgramData\chocolatey\lib\nodejs.commandline\tools\node.exe",
        # Standard installer
        os.path.join(prog,  r"nodejs\node.exe"),
        r"C:\nodejs\node.exe",
    ]
    return patterns


def _windows_qjs_candidates() -> list[str]:
    local = os.environ.get("LOCALAPPDATA", "")
    prog  = os.environ.get("ProgramFiles", r"C:\Program Files")
    home  = os.environ.get("USERPROFILE", "")

    return [
        os.path.join(local, r"Microsoft\WinGet\Links\qjs.exe"),
        os.path.join(local, r"Microsoft\WinGet\Packages\*quickjs*\**\qjs.exe"),
        os.path.join(home,  r"scoop\shims\qjs.exe"),
        os.path.join(home,  r"scoop\apps\quickjs\current\qjs.exe"),
        r"C:\ProgramData\chocolatey\bin\qjs.exe",
        os.path.join(prog,  r"quickjs\qjs.exe"),
    ]


def _posix_candidates(binary: str, extra_dirs: list[str] | None = None) -> list[str]:
    """Standard POSIX search paths for *binary*."""
    dirs = [
        "/usr/bin", "/usr/local/bin", "/opt/homebrew/bin",  # macOS Apple Silicon
        "/usr/local/opt/node/bin",                           # macOS Homebrew Node
        "/snap/bin",
        os.path.expanduser("~/.local/bin"),
        os.path.expanduser("~/bin"),
        os.path.expanduser("~/.nvm/versions/node"),          # nvm (wildcard below)
        "/opt/local/bin",                                    # MacPorts
    ]
    if extra_dirs:
        dirs.extend(extra_dirs)
    return [os.path.join(d, binary) for d in dirs]


def _find_binary(
    binary: str,
    checker,
    extra_patterns: list[str] | None = None,
) -> Optional[JsRuntimeResult]:
    """
    Search for *binary* using:
    1. shutil.which (respects PATH — catches nvm, pyenv-node, volta, etc.)
    2. Platform-specific hardcoded locations / glob patterns
    """
    # 1. PATH
    found = shutil.which(binary)
    if found:
        result = checker(found)
        if result:
            _log.debug("%s found on PATH: %s", binary, found)
            return result

    # 2. Explicit locations + glob patterns
    patterns = extra_patterns or []
    for pattern in patterns:
        if any(c in pattern for c in ("*", "?")):
            matches = glob.glob(pattern, recursive=True)
            for m in sorted(matches, key=len, reverse=True):
                result = checker(m)
                if result:
                    _log.debug("%s found via glob [%s]: %s", binary, pattern, m)
                    return result
        else:
            if os.path.isfile(pattern):
                result = checker(pattern)
                if result:
                    _log.debug("%s found at fixed path: %s", binary, pattern)
                    return result

    return None


# ── nvm special handling (POSIX) ──────────────────────────────────────────────

def _find_nvm_node() -> Optional[JsRuntimeResult]:
    """Search ~/.nvm/versions/node/ for the highest installed version."""
    nvm_dir = os.path.expanduser("~/.nvm/versions/node")
    if not os.path.isdir(nvm_dir):
        return None
    candidates = sorted(
        glob.glob(os.path.join(nvm_dir, "v*", "bin", "node")),
        reverse=True,  # highest version-string first
    )
    for candidate in candidates:
        if os.path.isfile(candidate):
            result = _check_node(candidate)
            if result:
                _log.debug("Node found via nvm: %s", candidate)
                return result
    return None


# ── Main detection ─────────────────────────────────────────────────────────────

def detect_js_runtime() -> JsRuntimeResult:
    """
    Probe for JavaScript runtimes in preference order:
    node → qjs → deno → bun.

    Returns the first one that is found and meets yt-dlp's minimum version
    requirements. Returns a ``JsRuntimeResult(available=False)`` if none found.
    """
    _log.info("Searching for a JavaScript runtime for yt-dlp...")

    if sys.platform == "win32":
        node_extras = _windows_node_candidates()
        qjs_extras  = _windows_qjs_candidates()
        deno_extras = [
            os.path.join(os.environ.get("USERPROFILE", ""), r".deno\bin\deno.exe"),
        ]
        bun_extras  = []
    else:
        node_extras = _posix_candidates("node") + _posix_candidates("nodejs")
        qjs_extras  = _posix_candidates("qjs")
        deno_extras = [os.path.expanduser("~/.deno/bin/deno")] + _posix_candidates("deno")
        bun_extras  = [os.path.expanduser("~/.bun/bin/bun")] + _posix_candidates("bun")

    # Try node first (most common)
    result = _find_binary("node", _check_node, node_extras)
    if not result:
        result = _find_nvm_node()
    if result:
        _log.info("JS runtime: node v%s at %s", result.version, result.path)
        return result

    # Try node alias (some distros)
    result = _find_binary("nodejs", _check_node, [])
    if result:
        result = JsRuntimeResult(name="node", path=result.path,
                                 version=result.version, available=True)
        _log.info("JS runtime: node (nodejs) v%s at %s", result.version, result.path)
        return result

    # Try QuickJS (tiny binary, great choice for bundled apps)
    result = _find_binary("qjs", _check_qjs, qjs_extras)
    if result:
        _log.info("JS runtime: qjs v%s at %s", result.version, result.path)
        return result

    # Try Deno
    result = _find_binary("deno", _check_deno, deno_extras)
    if result:
        _log.info("JS runtime: deno v%s at %s", result.version, result.path)
        return result

    # Try Bun
    result = _find_binary("bun", _check_bun, bun_extras)
    if result:
        _log.info("JS runtime: bun v%s at %s", result.version, result.path)
        return result

    _log.warning(
        "No JavaScript runtime found. "
        "YouTube downloads may fail for some videos. "
        "Install Node.js from https://nodejs.org/ to fix this."
    )
    return _NONE_RESULT


def build_js_runtimes_param(result: JsRuntimeResult) -> dict:
    """
    Build the ``js_runtimes`` dict for ``yt_dlp.YoutubeDL()``.

    When a runtime is found, passes its absolute path so yt-dlp uses
    exactly the binary we verified rather than re-searching PATH.
    When no runtime is found, passes an empty dict — yt-dlp will use
    its degraded client list (still works for many videos).
    """
    if not result.available or not result.path:
        return {}
    return {result.yt_dlp_key: {"path": result.path}}


def get_runtime_install_hint() -> str:
    """Return a user-friendly install suggestion string."""
    if sys.platform == "win32":
        return (
            "No JavaScript runtime found.\n"
            "Install Node.js to enable full YouTube support:\n"
            "  winget install OpenJS.NodeJS\n"
            "Then restart the app."
        )
    elif sys.platform == "darwin":
        return (
            "No JavaScript runtime found.\n"
            "Install Node.js to enable full YouTube support:\n"
            "  brew install node\n"
            "Then restart the app."
        )
    else:
        return (
            "No JavaScript runtime found.\n"
            "Install Node.js to enable full YouTube support:\n"
            "  sudo apt install nodejs   # Debian/Ubuntu\n"
            "  sudo dnf install nodejs   # Fedora\n"
            "Then restart the app."
        )
