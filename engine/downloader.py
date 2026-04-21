"""
Engine: yt-dlp download wrapper.
Runs inside a background thread; communicates back via callbacks.
"""
import os
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

import yt_dlp

from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)

_DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "YTBatchDL")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ── Data types ───────────────────────────────────────────────────────────────

@dataclass
class ProgressData:
    status: str = ""          # "downloading" | "finished" | "error"
    percent: float = 0.0
    speed: str = ""
    eta: str = ""
    filename: str = ""


@dataclass
class DownloadRequest:
    url: str
    mode: str                        # "video" | "audio"
    video_format: str = "mp4"        # mp4 / mkv / webm  (video mode only)
    output_dir: str = field(default_factory=lambda: _DEFAULT_OUTPUT_DIR)
    audio_quality: str = "192"       # kbps for MP3
    max_retries: int = 2
    rate_limit_kb: int = 0           # 0 = unlimited
    concurrent_fragments: int = 4
    embed_thumbnail: bool = False
    write_subtitles: bool = False
    subtitle_lang: str = "en"
    skip_existing: bool = True
    proxy_url: str = ""
    ffmpeg_location: str = ""  # explicit path dir for yt-dlp ffmpeg_location


@dataclass
class DownloadResult:
    url: str
    title: str
    filepath: str
    success: bool
    error_message: str = ""


# ── Callbacks type aliases ───────────────────────────────────────────────────

ProgressCallback = Callable[[ProgressData], None]
DoneCallback = Callable[[DownloadResult], None]
LogCallback = Callable[[str], None]


# ── Engine ───────────────────────────────────────────────────────────────────

class DownloadEngine:
    """
    Wraps yt-dlp to download a single URL.
    Always runs in the calling thread; use DownloadWorker for background use.
    """

    def download(
        self,
        request: DownloadRequest,
        on_progress: Optional[ProgressCallback] = None,
        on_log: Optional[LogCallback] = None,
    ) -> DownloadResult:
        """
        Execute the download synchronously.
        Returns a DownloadResult regardless of success/failure.
        """
        os.makedirs(request.output_dir, exist_ok=True)

        ydl_opts = self._build_opts(request, on_progress, on_log)
        title = request.url
        filepath = ""

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(request.url, download=True)
                if info:
                    title = info.get("title", request.url)
                    filepath = ydl.prepare_filename(info)
            return DownloadResult(
                url=request.url,
                title=title,
                filepath=filepath,
                success=True,
            )
        except yt_dlp.utils.DownloadError as exc:
            msg = str(exc)
            _log.error("DownloadError for %s: %s", request.url, msg)
            return DownloadResult(
                url=request.url,
                title=title,
                filepath="",
                success=False,
                error_message=msg,
            )
        except Exception as exc:
            msg = f"Unexpected error: {exc}"
            _log.exception("Unexpected error for %s", request.url)
            return DownloadResult(
                url=request.url,
                title=title,
                filepath="",
                success=False,
                error_message=msg,
            )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_opts(
        self,
        req: DownloadRequest,
        on_progress: Optional[ProgressCallback],
        on_log: Optional[LogCallback],
    ) -> dict:
        outtmpl = os.path.join(req.output_dir, "%(title)s.%(ext)s")

        base_opts: dict = {
            "outtmpl": outtmpl,
            "http_headers": {"User-Agent": _USER_AGENT},
            "noprogress": True,
            "quiet": True,
            "no_warnings": False,
            "ignoreerrors": False,
            "progress_hooks": [self._make_progress_hook(on_progress)],
            "postprocessor_hooks": [],
            "retries": req.max_retries,
            "concurrent_fragment_downloads": req.concurrent_fragments,
            "nooverwrites": req.skip_existing,
        }

        if req.rate_limit_kb > 0:
            base_opts["ratelimit"] = req.rate_limit_kb * 1024

        if req.proxy_url:
            base_opts["proxy"] = req.proxy_url

        # Point yt-dlp directly at ffmpeg (handles non-PATH WinGet/Scoop installs)
        if req.ffmpeg_location:
            base_opts["ffmpeg_location"] = req.ffmpeg_location

        if on_log:
            base_opts["logger"] = _YtdlpLogger(on_log)

        if req.mode == "audio":
            base_opts.update(self._audio_opts(req.audio_quality, req.embed_thumbnail))
        else:
            base_opts.update(self._video_opts(
                req.video_format,
                req.embed_thumbnail,
                req.write_subtitles,
                req.subtitle_lang,
            ))

        return base_opts

    @staticmethod
    def _audio_opts(quality: str = "192", embed_thumbnail: bool = False) -> dict:
        pps: list[dict] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality,
            }
        ]
        if embed_thumbnail:
            pps.append({"key": "EmbedThumbnail"})
        return {
            "format": "bestaudio/best",
            "postprocessors": pps,
            "writethumbnail": embed_thumbnail,
        }

    @staticmethod
    def _video_opts(
        fmt: str,
        embed_thumbnail: bool = False,
        write_subtitles: bool = False,
        subtitle_lang: str = "en",
    ) -> dict:
        merge_fmt = fmt if fmt in ("mp4", "mkv", "webm") else "mp4"
        pps: list[dict] = [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": merge_fmt,
            }
        ]
        if embed_thumbnail:
            pps.append({"key": "EmbedThumbnail"})

        opts: dict = {
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": merge_fmt,
            "postprocessors": pps,
            "writethumbnail": embed_thumbnail,
        }

        if write_subtitles:
            opts.update({
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": [subtitle_lang],
            })

        return opts

    @staticmethod
    def _make_progress_hook(
        on_progress: Optional[ProgressCallback],
    ) -> Callable[[dict], None]:
        def hook(d: dict) -> None:
            if on_progress is None:
                return
            status = d.get("status", "")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
                downloaded = d.get("downloaded_bytes", 0)
                percent = min((downloaded / total) * 100, 100.0)
                speed_raw = d.get("speed") or 0
                speed = _fmt_speed(speed_raw)
                eta_raw = d.get("eta")
                eta = _fmt_eta(eta_raw)
                on_progress(
                    ProgressData(
                        status="downloading",
                        percent=percent,
                        speed=speed,
                        eta=eta,
                        filename=d.get("filename", ""),
                    )
                )
            elif status == "finished":
                on_progress(
                    ProgressData(
                        status="finished",
                        percent=100.0,
                        filename=d.get("filename", ""),
                    )
                )
        return hook


# ── Callback type for item-start notification ────────────────────────────────
ItemStartCallback = Callable[[str, int, int], None]   # url, index, total


# ── Worker: runs DownloadEngine in a background thread ───────────────────────

class DownloadWorker(threading.Thread):
    """
    Processes a list of DownloadRequests sequentially in a daemon thread.
    Callbacks are delivered from the worker thread; callers must dispatch
    UI updates via widget.after().

    Callback signatures:
        on_progress(ProgressData)
        on_item_start(url: str, index: int, total: int)
        on_item_done(DownloadResult)
        on_log(str)
        on_all_done()
    """

    def __init__(
        self,
        requests: list[DownloadRequest],
        on_progress: Optional[ProgressCallback] = None,
        on_item_start: Optional[ItemStartCallback] = None,
        on_item_done: Optional[DoneCallback] = None,
        on_log: Optional[LogCallback] = None,
        on_all_done: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(daemon=True)
        self._requests = requests
        self._on_progress = on_progress
        self._on_item_start = on_item_start
        self._on_item_done = on_item_done
        self._on_log = on_log
        self._on_all_done = on_all_done
        self._engine = DownloadEngine()
        self._stop_event = threading.Event()

    def stop(self) -> None:
        """Request graceful cancellation after the current download finishes."""
        self._stop_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._stop_event.is_set()

    def run(self) -> None:
        total = len(self._requests)
        completed = 0
        failed = 0

        for index, req in enumerate(self._requests, start=1):
            if self._stop_event.is_set():
                _log.info("Download worker cancelled after %d/%d items.", index - 1, total)
                if self._on_log:
                    self._on_log(f"⏹ Cancelled — {index-1}/{total} processed.")
                break

            # Notify UI that this item is starting
            if self._on_item_start:
                self._on_item_start(req.url, index, total)

            _log.info("[%d/%d] Starting: %s [%s]", index, total, req.url, req.mode)

            result = self._engine.download(
                req,
                on_progress=self._on_progress,
                on_log=self._on_log,
            )

            if result.success:
                completed += 1
            else:
                failed += 1

            if self._on_item_done:
                self._on_item_done(result)

        if self._on_log:
            self._on_log(
                f"━━ Session complete: {completed} succeeded, {failed} failed "
                f"of {total} total ━━"
            )
        if self._on_all_done:
            self._on_all_done()


# ── yt-dlp logger adapter ────────────────────────────────────────────────────

class _YtdlpLogger:
    """Redirects yt-dlp internal messages to the UI log callback."""

    def __init__(self, callback: LogCallback) -> None:
        self._cb = callback

    def debug(self, msg: str) -> None:
        if msg.startswith("[debug]"):
            return
        self._cb(f"[yt-dlp] {msg}")

    def info(self, msg: str) -> None:
        self._cb(f"[info] {msg}")

    def warning(self, msg: str) -> None:
        self._cb(f"[warn] {msg}")

    def error(self, msg: str) -> None:
        self._cb(f"[error] {msg}")


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_speed(bps: float) -> str:
    if bps <= 0:
        return "—"
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bps < 1024:
            return f"{bps:.1f} {unit}"
        bps /= 1024
    return f"{bps:.1f} TB/s"


def _fmt_eta(seconds: Optional[int]) -> str:
    if seconds is None or seconds < 0:
        return "—"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"
