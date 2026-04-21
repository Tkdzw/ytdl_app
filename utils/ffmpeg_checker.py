"""
Utility: FFmpeg presence checker.

Search order:
  1. System PATH  (shutil.which)
  2. Frozen-app bundle  (PyInstaller _MEIPASS)
  3. Windows-specific well-known install locations:
       - WinGet  (versioned sub-folder under LocalAppData + ProgramFiles)
       - Scoop   (%USERPROFILE%/scoop/shims)
       - Chocolatey  (C:/ProgramData/chocolatey/bin)
       - Common manual extracts  (C:/ffmpeg/bin, C:/Program Files/ffmpeg/bin)
  4. macOS Homebrew  (/opt/homebrew/bin, /usr/local/bin)
  5. Linux common paths  (/usr/bin, /usr/local/bin, /snap/bin)

When FFmpeg is found via a fallback path the finder also injects that
directory into os.environ["PATH"] so that yt-dlp (which calls ffmpeg as
a subprocess) can locate it for the remainder of the process lifetime.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
from typing import Optional

from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)


class FFmpegChecker:
    """Static helper to validate FFmpeg installation."""

    # Cached result so we only probe once per run
    _ffmpeg_path: Optional[str] = None
    _checked: bool = False

    @classmethod
    def check(cls) -> bool:
        """
        Return True if ffmpeg can be located and executed.
        Side-effect: injects the discovered directory into PATH.
        """
        if cls._checked:
            return cls._ffmpeg_path is not None

        cls._checked = True
        path = cls._find()
        if path:
            cls._ffmpeg_path = path
            cls._inject_path(os.path.dirname(path))
            try:
                result = subprocess.run(
                    [path, "-version"],
                    capture_output=True,
                    timeout=6,
                )
                if result.returncode == 0:
                    first = result.stdout.decode(errors="replace").splitlines()[0]
                    _log.info("FFmpeg detected: %s  [%s]", first, path)
                    return True
                else:
                    _log.warning("FFmpeg at %s returned non-zero.", path)
            except Exception as exc:
                _log.error("FFmpeg probe failed: %s", exc)
            cls._ffmpeg_path = None
        else:
            _log.warning("FFmpeg not found anywhere. Downloads will be disabled.")

        return cls._ffmpeg_path is not None

    @classmethod
    def get_path(cls) -> Optional[str]:
        """Return the resolved ffmpeg executable path, or None."""
        cls.check()
        return cls._ffmpeg_path

    # ── Search ────────────────────────────────────────────────────────────────

    @classmethod
    def _find(cls) -> Optional[str]:
        # 1. PATH
        found = shutil.which("ffmpeg")
        if found:
            _log.debug("FFmpeg on PATH: %s", found)
            return found

        # 2. Bundled inside PyInstaller executable
        frozen = cls._find_frozen()
        if frozen:
            return frozen

        # 3. Platform-specific probing
        if sys.platform == "win32":
            return cls._find_windows()
        elif sys.platform == "darwin":
            return cls._find_mac()
        else:
            return cls._find_linux()

    # ── PyInstaller bundle ────────────────────────────────────────────────────

    @staticmethod
    def _find_frozen() -> Optional[str]:
        if not getattr(sys, "frozen", False):
            return None
        base = getattr(sys, "_MEIPASS", "")
        if not base:
            return None
        for sub in ("ffmpeg", "bin", ""):
            candidate = os.path.join(base, sub, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
            if os.path.isfile(candidate):
                _log.debug("Bundled FFmpeg: %s", candidate)
                return candidate
        return None

    # ── Windows ───────────────────────────────────────────────────────────────

    @staticmethod
    def _find_windows() -> Optional[str]:
        """
        Probe every known Windows FFmpeg install location.
        WinGet uses a versioned path like:
          %LOCALAPPDATA%/Microsoft/WinGet/Packages/yt-dlp.FFmpeg_*/ffmpeg-*/bin/ffmpeg.exe
        """
        local   = os.environ.get("LOCALAPPDATA", "")
        appdata = os.environ.get("APPDATA", "")
        prog64  = os.environ.get("ProgramFiles",   r"C:\Program Files")
        prog86  = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        home    = os.environ.get("USERPROFILE", "")

        # Explicit glob patterns — most specific first
        patterns: list[str] = [
            # WinGet — yt-dlp FFmpeg package (versioned)
            os.path.join(local,  r"Microsoft\WinGet\Packages\yt-dlp.FFmpeg*\**\bin\ffmpeg.exe"),
            # WinGet — generic ffmpeg packages
            os.path.join(local,  r"Microsoft\WinGet\Packages\*ffmpeg*\**\bin\ffmpeg.exe"),
            os.path.join(local,  r"Microsoft\WinGet\Packages\*FFmpeg*\**\bin\ffmpeg.exe"),
            os.path.join(prog64, r"WinGet\Packages\*ffmpeg*\**\bin\ffmpeg.exe"),
            # WinGet Links folder (symlinks created by newer WinGet)
            os.path.join(local,  r"Microsoft\WinGet\Links\ffmpeg.exe"),
            # Scoop
            os.path.join(home,   r"scoop\shims\ffmpeg.exe"),
            os.path.join(home,   r"scoop\apps\ffmpeg\current\bin\ffmpeg.exe"),
            # Chocolatey
            r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
            r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffmpeg.exe",
            # Common manual installs
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\ffmpeg\ffmpeg.exe",
            os.path.join(prog64, r"ffmpeg\bin\ffmpeg.exe"),
            os.path.join(prog86, r"ffmpeg\bin\ffmpeg.exe"),
            # yt-dlp sometimes ships its own ffmpeg
            os.path.join(appdata, r"yt-dlp\ffmpeg.exe"),
        ]

        for pattern in patterns:
            # Use glob for patterns with wildcards, direct check for plain paths
            if "*" in pattern or "**" in pattern:
                matches = glob.glob(pattern, recursive=True)
                if matches:
                    # Pick the newest-looking (longest path = deepest version dir)
                    best = sorted(matches, key=len, reverse=True)[0]
                    _log.info("FFmpeg found via glob [%s]: %s", pattern, best)
                    return best
            else:
                if os.path.isfile(pattern):
                    _log.info("FFmpeg found at fixed path: %s", pattern)
                    return pattern

        _log.warning("FFmpeg not found on Windows. Tried %d locations.", len(patterns))
        return None

    # ── macOS ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _find_mac() -> Optional[str]:
        candidates = [
            "/opt/homebrew/bin/ffmpeg",       # Apple Silicon Homebrew
            "/usr/local/bin/ffmpeg",           # Intel Homebrew
            "/opt/local/bin/ffmpeg",           # MacPorts
            os.path.expanduser("~/.local/bin/ffmpeg"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                _log.info("FFmpeg found (macOS): %s", c)
                return c
        return None

    # ── Linux ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _find_linux() -> Optional[str]:
        candidates = [
            "/usr/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "/snap/bin/ffmpeg",
            "/var/lib/flatpak/exports/bin/ffmpeg",
            os.path.expanduser("~/.local/bin/ffmpeg"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                _log.info("FFmpeg found (Linux): %s", c)
                return c
        return None

    # ── PATH injection ────────────────────────────────────────────────────────

    @staticmethod
    def _inject_path(directory: str) -> None:
        """
        Prepend *directory* to os.environ['PATH'] so yt-dlp subprocess
        calls can find ffmpeg without any further configuration.
        """
        if not directory:
            return
        current = os.environ.get("PATH", "")
        if directory.lower() not in current.lower():
            os.environ["PATH"] = directory + os.pathsep + current
            _log.info("Injected into PATH: %s", directory)
