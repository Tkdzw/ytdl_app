"""
conversion_worker.py
─────────────────────────────────────────────────────────────────────────────
Threaded conversion engine that wraps ``ffmpeg_manager`` and surfaces clean
Qt-compatible signals for GUI integration.

Because this app uses *customtkinter* (Tkinter-based, not Qt), the worker
uses ``threading.Thread`` and plain Python callbacks instead of QObject
signals — exactly the same pattern already used by ``DownloadWorker``.

Usage example (inside a CTk frame)
────────────────────────────────────
    from conversion_worker import ConversionRequest, ConversionWorker

    req = ConversionRequest(
        input_file="/tmp/video.webm",
        output_file="/tmp/audio.mp3",
        output_format="mp3",
        bitrate="192k",
    )
    worker = ConversionWorker(
        requests=[req],
        on_progress=lambda pct, t: print(f"{pct:.1f}% at {t}"),
        on_item_done=lambda r: print("Done:", r),
        on_all_done=lambda: print("All finished"),
    )
    worker.start()
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from ffmpeg_manager import (
    FFmpegConversionError,
    FFmpegNotFoundError,
    cleanup_temp_file,
    convert_file,
    detect_format,
    get_ffmpeg_path,
    get_ffmpeg_version,
)

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ConversionRequest:
    """Describes a single file-conversion job."""

    input_file: str
    """Absolute path to the source media file."""

    output_file: str
    """Absolute path the converted file should be written to.
    If empty, auto-generated next to *input_file* with the new extension."""

    output_format: str = "mp3"
    """Target format: ``"mp3"`` | ``"wav"`` | ``"mp4"`` | ``"m4a"``."""

    bitrate: str = "192k"
    """Audio bitrate string, e.g. ``"192k"``, ``"256k"``, ``"320k"``."""

    delete_source: bool = False
    """If True, source file is deleted after a successful conversion."""

    def __post_init__(self) -> None:
        # Auto-generate output path if not provided
        if not self.output_file:
            base, _ = os.path.splitext(self.input_file)
            self.output_file = f"{base}.{self.output_format.lower()}"


@dataclass
class ConversionResult:
    """Outcome of a single conversion job."""

    request: ConversionRequest
    success: bool
    error_message: str = ""
    output_file: str = ""


# ---------------------------------------------------------------------------
# Callback type aliases
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[float, str], None]
"""(percent: float, time_str: str) — percent is 0–100."""

ItemDoneCallback = Callable[[ConversionResult], None]
LogCallback = Callable[[str], None]


# ---------------------------------------------------------------------------
# ConversionWorker
# ---------------------------------------------------------------------------

class ConversionWorker(threading.Thread):
    """
    Processes a list of :class:`ConversionRequest` objects sequentially
    in a background daemon thread.

    All callbacks are invoked from the worker thread.  For Tkinter GUI
    updates, wrap them with ``widget.after(0, callback, ...)``.

    Signals / callbacks
    ────────────────────
    on_progress(percent: float, time_str: str)
        Fired periodically during each conversion.

    on_item_start(req: ConversionRequest, index: int, total: int)
        Fired just before each conversion begins.

    on_item_done(result: ConversionResult)
        Fired when each conversion completes (success or failure).

    on_log(message: str)
        Fired for every FFmpeg log line and status message.

    on_all_done()
        Fired when the entire batch is finished (or cancelled).
    """

    def __init__(
        self,
        requests: List[ConversionRequest],
        *,
        on_progress: Optional[ProgressCallback] = None,
        on_item_start: Optional[Callable[[ConversionRequest, int, int], None]] = None,
        on_item_done: Optional[ItemDoneCallback] = None,
        on_log: Optional[LogCallback] = None,
        on_all_done: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(daemon=True, name="ConversionWorker")
        self._requests = requests
        self._on_progress = on_progress
        self._on_item_start = on_item_start
        self._on_item_done = on_item_done
        self._on_log = on_log
        self._on_all_done = on_all_done
        self._stop_event = threading.Event()

    # ── Control ───────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Request graceful cancellation after the current item finishes."""
        self._stop_event.set()
        _log.info("ConversionWorker cancellation requested.")

    @property
    def is_cancelled(self) -> bool:
        return self._stop_event.is_set()

    # ── Thread entry ──────────────────────────────────────────────────────────

    def run(self) -> None:
        total = len(self._requests)
        succeeded = 0
        failed = 0

        self._emit_log(
            f"[conversion] Batch starting: {total} item(s), "
            f"FFmpeg {get_ffmpeg_version()}"
        )

        for index, req in enumerate(self._requests, start=1):
            if self._stop_event.is_set():
                self._emit_log(
                    f"[conversion] ⏹ Cancelled after {index - 1}/{total} items."
                )
                break

            if self._on_item_start:
                self._on_item_start(req, index, total)

            self._emit_log(
                f"[conversion] [{index}/{total}] {os.path.basename(req.input_file)}"
                f" → {req.output_format.upper()}"
            )

            result = self._convert_one(req)

            if result.success:
                succeeded += 1
            else:
                failed += 1

            if self._on_item_done:
                self._on_item_done(result)

        self._emit_log(
            f"[conversion] ━━ Batch complete: "
            f"{succeeded} succeeded, {failed} failed of {total} total ━━"
        )

        if self._on_all_done:
            self._on_all_done()

    # ── Private ───────────────────────────────────────────────────────────────

    def _convert_one(self, req: ConversionRequest) -> ConversionResult:
        """Run a single conversion; return a :class:`ConversionResult`."""
        try:
            convert_file(
                req.input_file,
                req.output_file,
                output_format=req.output_format,
                bitrate=req.bitrate,
                on_progress=self._on_progress,
                on_log=self._on_log,
            )

            if req.delete_source and os.path.isfile(req.input_file):
                cleanup_temp_file(req.input_file)

            return ConversionResult(
                request=req,
                success=True,
                output_file=req.output_file,
            )

        except (FFmpegNotFoundError, FFmpegConversionError, FileNotFoundError) as exc:
            msg = str(exc)
            _log.error("Conversion failed for %s: %s", req.input_file, msg)
            self._emit_log(f"[conversion] ❌ Error: {msg}")
            return ConversionResult(
                request=req,
                success=False,
                error_message=msg,
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"Unexpected error during conversion: {exc}"
            _log.exception("Unexpected conversion error for %s", req.input_file)
            self._emit_log(f"[conversion] ❌ Unexpected error: {exc}")
            return ConversionResult(
                request=req,
                success=False,
                error_message=msg,
            )

    def _emit_log(self, message: str) -> None:
        _log.info(message)
        if self._on_log:
            self._on_log(message)
