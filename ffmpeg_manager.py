"""
ffmpeg_manager.py
─────────────────────────────────────────────────────────────────────────────
Thin FFmpeg resolver (used for the About dialog's version display).

FFmpeg is located in this order:
  1. Directory saved by the user in Settings > Tools (ffmpeg_bin_dir)
  2. System PATH via shutil.which

Use get_ffmpeg_path() if you need the full binary path, or rely on
engine/downloader.py's _resolve_ffmpeg_location() which yt-dlp calls
on every download.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from typing import Optional


class FFmpegNotFoundError(RuntimeError):
    """Raised when FFmpeg cannot be located."""


_cached_ffmpeg_path: Optional[str] = None


def get_ffmpeg_path(saved_dir: str = "") -> str:
    """
    Return the absolute path to the ffmpeg binary.

    Args:
        saved_dir: The directory stored in settings ("ffmpeg_bin_dir").
                   Pass an empty string to skip and go straight to PATH.

    Raises:
        FFmpegNotFoundError if ffmpeg cannot be found.
    """
    global _cached_ffmpeg_path

    # Always re-resolve if a saved_dir is provided (user may have changed it)
    if not saved_dir and _cached_ffmpeg_path and os.path.isfile(_cached_ffmpeg_path):
        return _cached_ffmpeg_path

    exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"

    # 1. User-supplied directory
    if saved_dir and os.path.isdir(saved_dir):
        candidate = os.path.join(saved_dir, exe_name)
        if os.path.isfile(candidate):
            _cached_ffmpeg_path = candidate
            return candidate

    # 2. System PATH
    found = shutil.which("ffmpeg")
    if found:
        _cached_ffmpeg_path = os.path.abspath(found)
        return _cached_ffmpeg_path

    raise FFmpegNotFoundError(
        "FFmpeg not found.\n"
        "Download it from https://ffmpeg.org/download.html and either:\n"
        "  • Set the bin folder in Settings > Tools, or\n"
        "  • Add it to your system PATH."
    )


def get_ffmpeg_version(saved_dir: str = "") -> str:
    """Return a short version string, e.g. '7.0'. Returns 'unknown' on failure."""
    try:
        path = get_ffmpeg_path(saved_dir)
        result = subprocess.run([path, "-version"], capture_output=True, timeout=8)
        first_line = result.stdout.decode(errors="replace").splitlines()[0]
        match = re.search(r"version\s+([^\s]+)", first_line)
        return match.group(1) if match else "unknown"
    except Exception:
        return "unknown"
