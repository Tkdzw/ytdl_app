"""
Engine: yt-dlp download wrapper.
Runs inside a background thread; communicates back via callbacks.
"""
from __future__ import annotations

import os
import re
import shutil
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

import yt_dlp

from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)

_DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "YTBatchDL")

# Chrome 125 on Windows 11 — matches what yt-dlp's web client sends
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# extractor_args instructs yt-dlp which YouTube clients to try, in order.
# - "web":        most compatible, uses the JS-solved n-param, rarely 403s
# - "web_safari": Safari variant, good second choice
# - "ios":        good fallback, no JS needed, handles most age-restricted content
# - "mweb":       mobile web, light payload
# Clients that frequently 403 or are being phased out are intentionally omitted:
#   android_vr, android, android_music, tv_embedded
# Must be a list of separate names: yt-dlp treats each list element as one
# client, so a single comma-joined string is rejected as "unsupported client".
_YT_CLIENTS = ["web", "web_safari", "ios", "mweb"]

# HTTP headers that match a real Chrome browser session
_CHROME_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Sec-Fetch-Mode": "navigate",
}

# Strips ANSI colour codes yt-dlp embeds in error strings on Windows
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHFABCDJsu]|\[0;3[0-9]m|\033\[[^a-zA-Z]*[a-zA-Z]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text).strip()


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class ProgressData:
    status: str = ""
    percent: float = 0.0
    speed: str = ""
    eta: str = ""
    filename: str = ""


@dataclass
class DownloadRequest:
    url: str
    mode: str                        # "video" | "audio"
    video_format: str = "mp4"
    output_dir: str = field(default_factory=lambda: _DEFAULT_OUTPUT_DIR)
    audio_quality: str = "192"
    max_retries: int = 2
    rate_limit_kb: int = 0
    concurrent_fragments: int = 4
    embed_thumbnail: bool = False
    write_subtitles: bool = False
    subtitle_lang: str = "en"
    skip_existing: bool = True
    proxy_url: str = ""
    ffmpeg_location: str = ""        # directory containing ffmpeg binary
    js_runtime_name: str = ""        # "node" | "qjs" | "deno" | "bun"
    js_runtime_path: str = ""        # absolute path to JS runtime binary


@dataclass
class DownloadResult:
    url: str
    title: str
    filepath: str
    success: bool
    error_message: str = ""
    # Every final file produced (several for a playlist URL). ``filepath`` is
    # the first of these, kept for callers that only need one.
    filepaths: list[str] = field(default_factory=list)
    # 1-based position in the worker's request list, so callers can match
    # results to queue rows even when the same URL appears twice.
    index: int = 0


def _final_filepaths(info: dict, ydl: "yt_dlp.YoutubeDL") -> list[str]:
    """
    Return the on-disk paths of the finished files for *info*.

    ``prepare_filename`` gives the name *before* post-processing (e.g. .webm
    for an audio download that became .mp3), so prefer the ``filepath`` that
    yt-dlp records in ``requested_downloads`` after post-processors run.
    Playlists are walked recursively.
    """
    if not info:
        return []
    entries = info.get("entries")
    if entries is not None:
        paths: list[str] = []
        for entry in entries:
            if entry:
                paths.extend(_final_filepaths(entry, ydl))
        return paths
    paths = [
        d["filepath"]
        for d in info.get("requested_downloads") or []
        if d.get("filepath")
    ]
    if paths:
        return paths
    # Fallback (e.g. file skipped as already present): best guess
    return [ydl.prepare_filename(info)]


# ── Callback aliases ──────────────────────────────────────────────────────────

ProgressCallback = Callable[[ProgressData], None]
DoneCallback = Callable[[DownloadResult], None]
LogCallback = Callable[[str], None]
ItemStartCallback = Callable[[str, int, int], None]


# ── FFmpeg location resolver ──────────────────────────────────────────────────

def _resolve_ffmpeg_location(stored_dir: str) -> str:
    """
    Return the directory containing the ffmpeg binary.

    Resolution order:
      1. stored_dir from settings — the folder the user set in Settings > Tools.
         This is persisted across restarts and is always tried first.
      2. shutil.which("ffmpeg") — system PATH fallback for when the user
         has ffmpeg on PATH but hasn't set it in Settings yet.

    Returns "" if nothing is found so yt-dlp surfaces a clear error message.
    """
    # 1. User-supplied / previously saved path
    if stored_dir and os.path.isdir(stored_dir):
        exe = os.path.join(stored_dir, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if os.path.isfile(exe):
            _log.debug("FFmpeg from saved location: %s", exe)
            return stored_dir

    # 2. System PATH fallback
    found = shutil.which("ffmpeg")
    if found:
        directory = os.path.dirname(os.path.abspath(found))
        _log.info("FFmpeg found on system PATH: %s", found)
        return directory

    _log.warning(
        "FFmpeg not found. Set the FFmpeg bin folder in Settings > Tools."
    )
    return ""


# ── Engine ────────────────────────────────────────────────────────────────────

class DownloadEngine:
    """Wraps yt-dlp to download a single URL synchronously."""

    def download(
        self,
        request: DownloadRequest,
        on_progress: Optional[ProgressCallback] = None,
        on_log: Optional[LogCallback] = None,
    ) -> DownloadResult:
        os.makedirs(request.output_dir, exist_ok=True)
        ydl_opts = self._build_opts(request, on_progress, on_log)
        title = request.url
        filepaths: list[str] = []

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(request.url, download=True)
                if info:
                    title = info.get("title", request.url)
                    filepaths = _final_filepaths(info, ydl)
            return DownloadResult(url=request.url, title=title,
                                  filepath=filepaths[0] if filepaths else "",
                                  success=True, filepaths=filepaths)
        except yt_dlp.utils.DownloadError as exc:
            msg = _strip_ansi(str(exc))
            _log.error("DownloadError for %s: %s", request.url, msg)
            return DownloadResult(url=request.url, title=title,
                                  filepath="", success=False, error_message=msg)
        except Exception as exc:
            msg = _strip_ansi(f"Unexpected error: {exc}")
            _log.exception("Unexpected error for %s", request.url)
            return DownloadResult(url=request.url, title=title,
                                  filepath="", success=False, error_message=msg)

    def _build_opts(
        self,
        req: DownloadRequest,
        on_progress: Optional[ProgressCallback],
        on_log: Optional[LogCallback],
    ) -> dict:
        outtmpl = os.path.join(req.output_dir, "%(title)s.%(ext)s")

        base_opts: dict = {
            "outtmpl": outtmpl,
            "http_headers": _CHROME_HEADERS,
            "noprogress": True,
            "quiet": True,
            "no_warnings": False,
            "ignoreerrors": False,
            "progress_hooks": [self._make_progress_hook(on_progress)],
            "postprocessor_hooks": [],
            "retries": req.max_retries,
            "fragment_retries": req.max_retries,
            "concurrent_fragment_downloads": req.concurrent_fragments,
            "nooverwrites": req.skip_existing,
            # Tell yt-dlp which YouTube clients to try, in order.
            # This prevents it from defaulting to android_vr which 403s frequently.
            "extractor_args": {
                "youtube": {
                    "player_client": list(_YT_CLIENTS),
                    # Skip the dash manifest check — speeds up extraction
                    # and avoids a second request that can also 403
                    "skip": ["dash", "hls"],
                }
            },
        }

        if req.rate_limit_kb > 0:
            base_opts["ratelimit"] = req.rate_limit_kb * 1024

        if req.proxy_url:
            base_opts["proxy"] = req.proxy_url

        # ── FFmpeg ────────────────────────────────────────────────────────────
        ffmpeg_dir = _resolve_ffmpeg_location(req.ffmpeg_location)
        if ffmpeg_dir:
            base_opts["ffmpeg_location"] = ffmpeg_dir
            _log.debug("ffmpeg_location: %s", ffmpeg_dir)

        # ── JS runtime ────────────────────────────────────────────────────────
        js_runtimes = _build_js_runtimes_param(req.js_runtime_name, req.js_runtime_path)
        base_opts["js_runtimes"] = js_runtimes

        if on_log:
            base_opts["logger"] = _YtdlpLogger(on_log)

        if req.mode == "audio":
            base_opts.update(self._audio_opts(req.audio_quality, req.embed_thumbnail))
        else:
            base_opts.update(self._video_opts(
                req.video_format, req.embed_thumbnail,
                req.write_subtitles, req.subtitle_lang,
            ))

        return base_opts

    @staticmethod
    def _audio_opts(quality: str = "192", embed_thumbnail: bool = False) -> dict:
        pps: list[dict] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
             "preferredquality": quality}
        ]
        if embed_thumbnail:
            pps.append({"key": "EmbedThumbnail"})
        return {
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
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
        pps: list[dict] = [{"key": "FFmpegVideoConvertor", "preferedformat": merge_fmt}]
        if embed_thumbnail:
            pps.append({"key": "EmbedThumbnail"})
        opts: dict = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
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
                on_progress(ProgressData(
                    status="downloading",
                    percent=percent,
                    speed=_fmt_speed(d.get("speed") or 0),
                    eta=_fmt_eta(d.get("eta")),
                    filename=d.get("filename", ""),
                ))
            elif status == "finished":
                on_progress(ProgressData(
                    status="finished", percent=100.0,
                    filename=d.get("filename", ""),
                ))
        return hook


# ── JS runtimes param builder ─────────────────────────────────────────────────

def _build_js_runtimes_param(runtime_name: str, runtime_path: str) -> dict:
    name = (runtime_name or "").strip()
    path = (runtime_path or "").strip()
    if not name or name == "none":
        return {}
    if path and os.path.isfile(path):
        return {name: {"path": path}}
    if name in ("node", "qjs", "deno", "bun"):
        return {name: {}}
    return {}


# ── Worker ────────────────────────────────────────────────────────────────────

class DownloadWorker(threading.Thread):
    """Processes DownloadRequests sequentially in a daemon thread."""

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
        self._stop_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._stop_event.is_set()

    def run(self) -> None:
        total = len(self._requests)
        completed = failed = 0

        for index, req in enumerate(self._requests, start=1):
            if self._stop_event.is_set():
                if self._on_log:
                    self._on_log(f"⏹ Cancelled — {index-1}/{total} processed.")
                break

            if self._on_item_start:
                self._on_item_start(req.url, index, total)

            _log.info("[%d/%d] Starting: %s [%s]", index, total, req.url, req.mode)

            result = self._engine.download(
                req, on_progress=self._on_progress, on_log=self._on_log
            )
            result.index = index

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


# ── yt-dlp logger adapter ─────────────────────────────────────────────────────

class _YtdlpLogger:
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
        self._cb(f"[error] {_strip_ansi(msg)}")


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