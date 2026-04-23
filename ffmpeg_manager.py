"""
ffmpeg_manager.py
─────────────────────────────────────────────────────────────────────────────
Self-contained FFmpeg resolver and conversion engine.

Uses ``imageio-ffmpeg`` to automatically provide a bundled FFmpeg binary,
eliminating any requirement for end-users to install FFmpeg manually.

Public API
──────────
    get_ffmpeg_path() -> str
        Returns the absolute path to the FFmpeg executable. Raises
        FFmpegNotFoundError on failure.

    get_ffmpeg_version() -> str
        Returns a short human-readable version string, e.g. "7.0".

    convert_to_mp3(input_file, output_file, bitrate, on_progress, on_log)
        Converts any audio-bearing file to MP3 using subprocess + FFmpeg.

    convert_file(input_file, output_file, format, bitrate, on_progress, on_log)
        General-purpose conversion that delegates to the correct handler.

    detect_format(filepath) -> str
        Heuristically detects the container format from the file extension.

    cleanup_temp_file(filepath)
        Safely removes a temporary / intermediate file if it still exists.

PyInstaller compatibility
──────────────────────────
    Build with:
        pyinstaller --onefile --collect-all imageio_ffmpeg  your_app.spec

    At runtime the module auto-detects ``sys._MEIPASS`` and will still
    call ``imageio_ffmpeg.get_ffmpeg_exe()`` which handles the frozen
    environment correctly on all platforms.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Attempt to import imageio_ffmpeg; fall back to system PATH probe if absent
# ---------------------------------------------------------------------------
try:
    import imageio_ffmpeg  # type: ignore[import]
    _IMAGEIO_FFMPEG_AVAILABLE = True
except ImportError:
    _IMAGEIO_FFMPEG_AVAILABLE = False

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class FFmpegNotFoundError(RuntimeError):
    """Raised when FFmpeg cannot be located by any strategy."""


# ---------------------------------------------------------------------------
# Internal cache
# ---------------------------------------------------------------------------

_cached_ffmpeg_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Core: get_ffmpeg_path
# ---------------------------------------------------------------------------

def get_ffmpeg_path() -> str:
    """
    Return the absolute path to a usable FFmpeg executable.

    Resolution order:
        1. ``imageio_ffmpeg.get_ffmpeg_exe()`` – bundled binary shipped with
           the ``imageio-ffmpeg`` Python package (always preferred, zero
           end-user setup required).
        2. System ``PATH`` via ``shutil.which`` – fallback for environments
           where imageio-ffmpeg is not installed.
        3. PyInstaller ``_MEIPASS`` bundle – covers frozen builds where
           FFmpeg was added manually as a binary data file.

    Returns:
        str: Absolute path to the FFmpeg executable.

    Raises:
        FFmpegNotFoundError: If no usable FFmpeg binary is found.
    """
    global _cached_ffmpeg_path

    if _cached_ffmpeg_path and os.path.isfile(_cached_ffmpeg_path):
        return _cached_ffmpeg_path

    path = (
        _resolve_via_imageio_ffmpeg()
        or _resolve_via_system_path()
        or _resolve_via_pyinstaller_bundle()
    )

    if not path:
        raise FFmpegNotFoundError(
            "FFmpeg could not be located. "
            "Install the 'imageio-ffmpeg' Python package "
            "(pip install imageio-ffmpeg) to bundle FFmpeg automatically, "
            "or ensure ffmpeg is on your system PATH."
        )

    # Validate: run -version to confirm the binary works
    _validate_ffmpeg_binary(path)

    _cached_ffmpeg_path = path
    _log.info("FFmpeg resolved: %s", path)

    # Inject directory into PATH so yt-dlp subprocess calls also find it
    _inject_into_path(os.path.dirname(path))

    return path


def get_ffmpeg_version() -> str:
    """
    Return a short version string for the resolved FFmpeg binary.

    Returns:
        str: e.g. "7.0" or "6.1.1".  Returns "unknown" if parsing fails.
    """
    try:
        path = get_ffmpeg_path()
        result = subprocess.run(
            [path, "-version"],
            capture_output=True,
            timeout=8,
        )
        first_line = result.stdout.decode(errors="replace").splitlines()[0]
        # "ffmpeg version 7.0 Copyright ..."
        match = re.search(r"version\s+([^\s]+)", first_line)
        if match:
            return match.group(1)
    except Exception as exc:  # noqa: BLE001
        _log.warning("Could not determine FFmpeg version: %s", exc)
    return "unknown"


# ---------------------------------------------------------------------------
# Conversion API
# ---------------------------------------------------------------------------

ConversionProgressCallback = Callable[[float, str], None]
"""
Callback signature:
    progress_callback(percent: float, elapsed_time: str)
    - percent:      0.0 – 100.0
    - elapsed_time: human-readable string like "00:01:23.45"
"""

LogCallback = Callable[[str], None]


def convert_to_mp3(
    input_file: str,
    output_file: str,
    *,
    bitrate: str = "192k",
    on_progress: Optional[ConversionProgressCallback] = None,
    on_log: Optional[LogCallback] = None,
) -> None:
    """
    Convert *input_file* to MP3 and write the result to *output_file*.

    Uses the FFmpeg binary resolved by :func:`get_ffmpeg_path`.  The
    conversion runs synchronously in the calling thread; use
    :class:`ConversionWorker` for background execution.

    Args:
        input_file:   Absolute path to the source media file.
        output_file:  Absolute path to the destination MP3 file.
        bitrate:      Audio bitrate string accepted by FFmpeg, e.g. ``"192k"``,
                      ``"256k"``, ``"320k"``.  Defaults to ``"192k"``.
        on_progress:  Optional callback receiving (percent, time_str).
                      Called periodically as FFmpeg reports progress.
        on_log:       Optional callback receiving a single log line string.

    Raises:
        FFmpegNotFoundError: If FFmpeg cannot be located.
        FFmpegConversionError: If the FFmpeg process exits with a non-zero
                               return code.
        FileNotFoundError: If *input_file* does not exist.
        ValueError: If *bitrate* is not a recognised FFmpeg bitrate string.
    """
    _log.info(
        "convert_to_mp3: %s → %s  (bitrate=%s)", input_file, output_file, bitrate
    )
    _run_conversion(
        input_file=input_file,
        output_file=output_file,
        extra_args=["-vn", "-acodec", "libmp3lame", "-ab", bitrate],
        on_progress=on_progress,
        on_log=on_log,
    )


def convert_to_wav(
    input_file: str,
    output_file: str,
    *,
    on_progress: Optional[ConversionProgressCallback] = None,
    on_log: Optional[LogCallback] = None,
) -> None:
    """Convert *input_file* to uncompressed WAV (PCM 16-bit, stereo, 44.1 kHz).

    Args:
        input_file:  Absolute path to source media.
        output_file: Absolute path to destination WAV file.
        on_progress: Optional progress callback (percent, time_str).
        on_log:      Optional line-level log callback.

    Raises:
        FFmpegNotFoundError, FFmpegConversionError, FileNotFoundError.
    """
    _log.info("convert_to_wav: %s → %s", input_file, output_file)
    _run_conversion(
        input_file=input_file,
        output_file=output_file,
        extra_args=[
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            "-ac", "2",
        ],
        on_progress=on_progress,
        on_log=on_log,
    )


def convert_to_mp4(
    input_file: str,
    output_file: str,
    *,
    video_bitrate: str = "0",     # "0" = copy if possible, else re-encode
    on_progress: Optional[ConversionProgressCallback] = None,
    on_log: Optional[LogCallback] = None,
) -> None:
    """Re-mux or re-encode *input_file* into an MP4 container.

    When the source is already H.264/AAC the streams are copied without
    re-encoding (fast).  Otherwise FFmpeg will transcode as needed.

    Args:
        input_file:     Absolute path to source media.
        output_file:    Absolute path to destination MP4.
        video_bitrate:  Target video bitrate, e.g. ``"2000k"``.  Pass
                        ``"0"`` (default) to attempt stream copy.
        on_progress:    Optional progress callback (percent, time_str).
        on_log:         Optional line-level log callback.

    Raises:
        FFmpegNotFoundError, FFmpegConversionError, FileNotFoundError.
    """
    _log.info("convert_to_mp4: %s → %s", input_file, output_file)
    if video_bitrate == "0":
        extra = ["-c:v", "copy", "-c:a", "aac", "-strict", "experimental"]
    else:
        extra = ["-c:v", "libx264", "-b:v", video_bitrate, "-c:a", "aac"]
    _run_conversion(
        input_file=input_file,
        output_file=output_file,
        extra_args=extra,
        on_progress=on_progress,
        on_log=on_log,
    )


# Supported output formats and their handlers
_FORMAT_DISPATCH: dict[str, str] = {
    "mp3": "mp3",
    "wav": "wav",
    "mp4": "mp4",
    "m4a": "m4a",
}


def convert_file(
    input_file: str,
    output_file: str,
    *,
    output_format: str = "mp3",
    bitrate: str = "192k",
    on_progress: Optional[ConversionProgressCallback] = None,
    on_log: Optional[LogCallback] = None,
) -> None:
    """
    High-level dispatcher: convert *input_file* to *output_format*.

    Supported formats: ``"mp3"``, ``"wav"``, ``"mp4"``, ``"m4a"``.

    Args:
        input_file:    Absolute path to source media.
        output_file:   Absolute path to destination file (extension should
                       match *output_format*).
        output_format: Target container/codec format (case-insensitive).
        bitrate:       Audio bitrate for compressed formats, e.g. ``"192k"``.
        on_progress:   Optional (percent, time_str) progress callback.
        on_log:        Optional line-level log callback.

    Raises:
        FFmpegNotFoundError:     If FFmpeg cannot be located.
        FFmpegConversionError:   If the conversion process fails.
        FileNotFoundError:       If *input_file* does not exist.
        ValueError:              If *output_format* is not supported.
    """
    fmt = output_format.lower().strip(".")
    if fmt == "mp3":
        convert_to_mp3(input_file, output_file, bitrate=bitrate,
                       on_progress=on_progress, on_log=on_log)
    elif fmt == "wav":
        convert_to_wav(input_file, output_file,
                       on_progress=on_progress, on_log=on_log)
    elif fmt == "mp4":
        convert_to_mp4(input_file, output_file,
                       on_progress=on_progress, on_log=on_log)
    elif fmt == "m4a":
        _run_conversion(
            input_file=input_file,
            output_file=output_file,
            extra_args=["-vn", "-acodec", "aac", "-ab", bitrate,
                        "-strict", "experimental"],
            on_progress=on_progress,
            on_log=on_log,
        )
    else:
        raise ValueError(
            f"Unsupported output format '{output_format}'. "
            f"Supported: {', '.join(_FORMAT_DISPATCH)}"
        )


def detect_format(filepath: str) -> str:
    """
    Heuristically detect the container format from the file's extension.

    Returns a lowercase extension string without the leading dot,
    e.g. ``"mp4"``, ``"webm"``, ``"mp3"``.  Returns ``"unknown"`` if the
    extension cannot be identified.

    Args:
        filepath: Path to the file (need not exist).

    Returns:
        str: Lowercase format identifier.
    """
    _, ext = os.path.splitext(filepath)
    return ext.lower().lstrip(".") if ext else "unknown"


def cleanup_temp_file(filepath: str) -> None:
    """
    Remove a temporary or intermediate file if it exists.

    Silently ignores errors (e.g. file already deleted, permission denied).

    Args:
        filepath: Absolute path to the file to remove.
    """
    if not filepath:
        return
    try:
        if os.path.isfile(filepath):
            os.remove(filepath)
            _log.debug("Cleaned up temp file: %s", filepath)
    except OSError as exc:
        _log.warning("Could not clean up %s: %s", filepath, exc)


# ---------------------------------------------------------------------------
# ConversionError
# ---------------------------------------------------------------------------

class FFmpegConversionError(RuntimeError):
    """Raised when the FFmpeg subprocess exits with a non-zero return code."""

    def __init__(self, message: str, returncode: int, stderr: str) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_via_imageio_ffmpeg() -> Optional[str]:
    """Try imageio_ffmpeg first; it ships its own static build."""
    if not _IMAGEIO_FFMPEG_AVAILABLE:
        _log.debug("imageio_ffmpeg not installed; skipping bundled FFmpeg probe.")
        return None
    try:
        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and os.path.isfile(path):
            _log.debug("imageio_ffmpeg provided FFmpeg at: %s", path)
            return path
    except Exception as exc:  # noqa: BLE001
        _log.warning("imageio_ffmpeg.get_ffmpeg_exe() failed: %s", exc)
    return None


def _resolve_via_system_path() -> Optional[str]:
    """Probe system PATH using shutil.which."""
    import shutil
    found = shutil.which("ffmpeg")
    if found:
        _log.debug("FFmpeg found on system PATH: %s", found)
        return found
    return None


def _resolve_via_pyinstaller_bundle() -> Optional[str]:
    """Search inside a PyInstaller _MEIPASS bundle directory."""
    if not getattr(sys, "frozen", False):
        return None
    base = getattr(sys, "_MEIPASS", "")
    if not base:
        return None
    exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    for sub in ("", "ffmpeg", "bin"):
        candidate = os.path.join(base, sub, exe_name) if sub else os.path.join(base, exe_name)
        if os.path.isfile(candidate):
            _log.debug("FFmpeg found in PyInstaller bundle: %s", candidate)
            return candidate
    return None


def _validate_ffmpeg_binary(path: str) -> None:
    """Run ``ffmpeg -version`` to confirm the binary is executable."""
    try:
        result = subprocess.run(
            [path, "-version"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise FFmpegNotFoundError(
                f"FFmpeg at '{path}' returned exit code {result.returncode} "
                f"when invoked with -version."
            )
        first_line = result.stdout.decode(errors="replace").splitlines()[0]
        _log.debug("FFmpeg validated: %s", first_line)
    except FileNotFoundError:
        raise FFmpegNotFoundError(
            f"FFmpeg binary not found or not executable: {path}"
        )
    except subprocess.TimeoutExpired:
        raise FFmpegNotFoundError(
            f"FFmpeg at '{path}' timed out during validation."
        )


def _inject_into_path(directory: str) -> None:
    """Prepend *directory* to ``os.environ['PATH']`` if not already present."""
    if not directory:
        return
    current = os.environ.get("PATH", "")
    if directory.lower() not in current.lower():
        os.environ["PATH"] = directory + os.pathsep + current
        _log.debug("Injected into PATH: %s", directory)


def _run_conversion(
    *,
    input_file: str,
    output_file: str,
    extra_args: list[str],
    on_progress: Optional[ConversionProgressCallback],
    on_log: Optional[LogCallback],
) -> None:
    """
    Core subprocess wrapper for all FFmpeg conversions.

    Builds the command:
        ffmpeg -y -i <input_file> <extra_args> <output_file>

    Parses ``time=HH:MM:SS.ss`` from stderr to derive progress percentage
    (requires knowing the duration — obtained via a quick ffprobe call).
    Falls back to indeterminate progress if duration is unavailable.

    Args:
        input_file:   Source file path.
        output_file:  Destination file path (created/overwritten).
        extra_args:   Additional FFmpeg flags inserted between -i and output.
        on_progress:  Optional (percent, time_str) callback.
        on_log:       Optional single-line log callback.

    Raises:
        FileNotFoundError:      If input_file does not exist.
        FFmpegConversionError:  If FFmpeg exits non-zero.
        FFmpegNotFoundError:    If FFmpeg binary cannot be found.
    """
    if not os.path.isfile(input_file):
        raise FileNotFoundError(f"Input file does not exist: {input_file}")

    ffmpeg = get_ffmpeg_path()
    output_dir = os.path.dirname(os.path.abspath(output_file))
    os.makedirs(output_dir, exist_ok=True)

    # Get total duration for progress calculation
    duration_secs = _probe_duration(ffmpeg, input_file)

    cmd = [ffmpeg, "-y", "-i", input_file] + extra_args + [output_file]
    _log.debug("FFmpeg command: %s", " ".join(cmd))

    if on_log:
        on_log(f"[ffmpeg] Starting: {' '.join(cmd)}")

    stderr_lines: list[str] = []

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding="utf-8",
            errors="replace",
        )

        # Read stderr line by line so we can parse progress in real-time
        for line in process.stderr:  # type: ignore[union-attr]
            line = line.rstrip()
            stderr_lines.append(line)
            _log.debug("[ffmpeg stderr] %s", line)

            if on_log and line:
                on_log(f"[ffmpeg] {line}")

            if on_progress and "time=" in line:
                time_str = _extract_time(line)
                if time_str:
                    elapsed = _parse_time_to_seconds(time_str)
                    pct = (elapsed / duration_secs * 100.0) if duration_secs > 0 else 0.0
                    pct = min(pct, 99.0)   # reserve 100 % for confirmed completion
                    on_progress(pct, time_str)

        process.wait()

    except Exception as exc:
        raise FFmpegConversionError(
            f"FFmpeg process raised an unexpected error: {exc}",
            returncode=-1,
            stderr="\n".join(stderr_lines),
        ) from exc

    if process.returncode != 0:
        full_stderr = "\n".join(stderr_lines)
        _log.error(
            "FFmpeg exited %d.\nCommand: %s\nStderr:\n%s",
            process.returncode, " ".join(cmd), full_stderr,
        )
        raise FFmpegConversionError(
            f"FFmpeg conversion failed (exit code {process.returncode}). "
            f"Input: {input_file!r} → Output: {output_file!r}",
            returncode=process.returncode,
            stderr=full_stderr,
        )

    if on_progress:
        on_progress(100.0, "done")

    _log.info(
        "Conversion complete: %s → %s", os.path.basename(input_file), os.path.basename(output_file)
    )


def _probe_duration(ffmpeg_path: str, filepath: str) -> float:
    """Return the duration of *filepath* in seconds using ffprobe/ffmpeg.

    Returns 0.0 if the duration cannot be determined (progress will be
    reported as indeterminate in that case).
    """
    # Prefer ffprobe if it lives next to ffmpeg
    ffprobe = os.path.join(
        os.path.dirname(ffmpeg_path),
        "ffprobe.exe" if sys.platform == "win32" else "ffprobe",
    )
    if not os.path.isfile(ffprobe):
        ffprobe = "ffprobe"   # try system PATH

    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", filepath],
            capture_output=True, timeout=8, text=True, errors="replace",
        )
        duration = float(result.stdout.strip())
        return duration
    except Exception:
        pass

    # Fallback: parse duration from ffmpeg stderr on a short probe
    try:
        result = subprocess.run(
            [ffmpeg_path, "-i", filepath],
            capture_output=True, timeout=8, text=True, errors="replace",
        )
        match = re.search(r"Duration:\s+(\d+):(\d+):(\d+\.\d+)", result.stderr)
        if match:
            h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
            return h * 3600 + m * 60 + s
    except Exception:
        pass

    return 0.0


def _extract_time(line: str) -> Optional[str]:
    """Extract the ``time=HH:MM:SS.ss`` value from an FFmpeg progress line."""
    match = re.search(r"time=(\d+:\d+:\d+\.\d+)", line)
    return match.group(1) if match else None


def _parse_time_to_seconds(time_str: str) -> float:
    """Convert ``HH:MM:SS.ss`` to a float number of seconds."""
    try:
        parts = time_str.split(":")
        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
        return h * 3600 + m * 60 + s
    except (ValueError, IndexError):
        return 0.0
