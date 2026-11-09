"""
Engine: yt-dlp download wrapper.
Runs inside a background thread; communicates back via callbacks.
"""
from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

import yt_dlp

from utils.logger import AppLogger
from utils.tool_setup import find_ffmpeg_dir

_log = AppLogger.get_logger(__name__)

_DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "YTBatchDL")

# Chrome 125 on Windows 11 — matches what yt-dlp's web client sends
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

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
    title: str = ""
    duration: Optional[float] = None   # seconds, when known
    eta_seconds: Optional[float] = None
    # Set when one URL downloads several videos (a playlist that wasn't expanded)
    playlist_index: int = 0
    playlist_count: int = 0
    playlist_title: str = ""


@dataclass
class DownloadRequest:
    url: str
    mode: str                        # "video" | "audio"
    video_format: str = "mp4"
    video_quality: str = "best"      # "best" or a max height like "1080p"
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
    no_playlist: bool = False        # watch?v=…&list=…: download only the video


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
    cancelled: bool = False


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
LogCallback = Callable[[str], None]
CancelCheck = Callable[[], bool]


# ── Engine ────────────────────────────────────────────────────────────────────

class DownloadEngine:
    """Wraps yt-dlp to download a single URL synchronously."""

    def download(
        self,
        request: DownloadRequest,
        on_progress: Optional[ProgressCallback] = None,
        on_log: Optional[LogCallback] = None,
        cancel_check: Optional[CancelCheck] = None,
    ) -> DownloadResult:
        """
        Download one URL. If *cancel_check* returns True while the download
        runs, it is stopped at the next progress tick (within a second or so)
        and its partial files are removed.
        """
        os.makedirs(request.output_dir, exist_ok=True)
        partials: set[str] = set()
        ydl_opts = self._build_opts(request, on_progress, on_log, cancel_check, partials)
        title = request.url
        filepaths: list[str] = []

        def cancelled() -> bool:
            return bool(cancel_check and cancel_check())

        try:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(request.url, download=True)
                    if info:
                        title = info.get("title", request.url)
                        filepaths = _final_filepaths(info, ydl)
            except _PlaylistNotMedia as pl:
                # The site's "mp4" link served an HLS playlist. Fetch it again
                # as a stream; yt-dlp's generic extractor spots #EXTM3U itself.
                _remove_file(pl.filepath)
                if on_log:
                    on_log("[info] Link served an HLS playlist, not a video file; "
                           "retrying as a stream")
                title = pl.title or title
                retry_opts = dict(ydl_opts)
                retry_opts["http_headers"] = {**_CHROME_HEADERS, **pl.headers}
                safe_title = (title.replace("%", "%%").replace("/", "_")
                              .replace("\\", "_"))
                retry_opts["outtmpl"] = os.path.join(
                    request.output_dir, safe_title + ".%(ext)s")
                with yt_dlp.YoutubeDL(retry_opts) as ydl:
                    # extra_info only fills keys the extractor left unset,
                    # so this restores the page's thumbnail for embedding.
                    extra = {"thumbnail": pl.thumbnail} if pl.thumbnail else {}
                    info = ydl.extract_info(pl.url, download=True, extra_info=extra)
                    if info:
                        filepaths = _final_filepaths(info, ydl)
            return DownloadResult(url=request.url, title=title,
                                  filepath=filepaths[0] if filepaths else "",
                                  success=True, filepaths=filepaths)
        except Exception as exc:
            if cancelled() or isinstance(exc, yt_dlp.utils.DownloadCancelled):
                _remove_partials(partials)
                _log.info("Cancelled: %s", request.url)
                return DownloadResult(url=request.url, title=title, filepath="",
                                      success=False, error_message="Cancelled",
                                      cancelled=True)
            msg = _strip_ansi(str(exc))
            if isinstance(exc, yt_dlp.utils.DownloadError):
                _log.error("DownloadError for %s: %s", request.url, msg)
            else:
                msg = f"Unexpected error: {msg}"
                _log.exception("Unexpected error for %s", request.url)
            return DownloadResult(url=request.url, title=title,
                                  filepath="", success=False, error_message=msg)

    def _build_opts(
        self,
        req: DownloadRequest,
        on_progress: Optional[ProgressCallback],
        on_log: Optional[LogCallback],
        cancel_check: Optional[CancelCheck] = None,
        partials: Optional[set] = None,
    ) -> dict:
        outtmpl = os.path.join(req.output_dir, "%(title)s.%(ext)s")

        base_opts: dict = {
            "outtmpl": outtmpl,
            "http_headers": _CHROME_HEADERS,
            "noprogress": True,
            "quiet": True,
            "no_warnings": False,
            "ignoreerrors": False,
            "progress_hooks": [self._make_progress_hook(on_progress, cancel_check, partials)],
            "postprocessor_hooks": [_make_pp_hook(cancel_check)],
            "retries": req.max_retries,
            "fragment_retries": req.max_retries,
            "concurrent_fragment_downloads": req.concurrent_fragments,
            "nooverwrites": req.skip_existing,
            "noplaylist": req.no_playlist,
            # No YouTube "player_client"/"skip" override: yt-dlp picks the
            # clients that currently work and updates that choice with each
            # release. A hard-coded list goes stale — YouTube started requiring
            # PO tokens (mweb) and serving SABR-only streams (ios, web), which
            # left a single 360p format. Skipping HLS also hides the m3u8
            # formats that are sometimes the only 1440p/4K source.
        }

        if req.rate_limit_kb > 0:
            base_opts["ratelimit"] = req.rate_limit_kb * 1024

        if req.proxy_url:
            base_opts["proxy"] = req.proxy_url

        # ── FFmpeg ────────────────────────────────────────────────────────────
        ffmpeg_dir = find_ffmpeg_dir(req.ffmpeg_location)
        if ffmpeg_dir:
            base_opts["ffmpeg_location"] = ffmpeg_dir
            _log.debug("ffmpeg_location: %s", ffmpeg_dir)

        # ── JS runtime ────────────────────────────────────────────────────────
        js_runtimes = _build_js_runtimes_param(req.js_runtime_name, req.js_runtime_path)
        if js_runtimes:
            # Only override when we found one; an empty dict would switch off
            # yt-dlp's own default (Deno on PATH).
            base_opts["js_runtimes"] = js_runtimes

        if on_log:
            base_opts["logger"] = _YtdlpLogger(on_log)

        if req.mode == "audio":
            base_opts.update(self._audio_opts(req.audio_quality, req.embed_thumbnail))
        else:
            base_opts.update(self._video_opts(
                req.video_format, req.video_quality, req.embed_thumbnail,
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
        quality: str = "best",
        embed_thumbnail: bool = False,
        write_subtitles: bool = False,
        subtitle_lang: str = "en",
    ) -> dict:
        merge_fmt = fmt if fmt in ("mp4", "mkv", "webm") else "mp4"
        pps: list[dict] = [{"key": "FFmpegVideoConvertor", "preferedformat": merge_fmt}]
        if embed_thumbnail:
            pps.append({"key": "EmbedThumbnail"})
        opts: dict = {
            "format": _VIDEO_FORMAT,
            "format_sort": _video_format_sort(merge_fmt, quality),
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
        cancel_check: Optional[CancelCheck] = None,
        partials: Optional[set] = None,
    ) -> Callable[[dict], None]:
        stream_state: dict = {}

        def hook(d: dict) -> None:
            # Raising here is yt-dlp's supported way to abort a download.
            if cancel_check and cancel_check():
                raise yt_dlp.utils.DownloadCancelled("Cancelled by user")
            if partials is not None and d.get("tmpfilename"):
                partials.add(d["tmpfilename"])
            info = d.get("info_dict") or {}
            status = d.get("status", "")
            if status == "finished":
                _check_not_playlist(d.get("filename", ""), info)
            if on_progress is None:
                return
            if status not in ("downloading", "finished"):
                return
            percent, is_last_stream = _overall_percent(d, info, stream_state)
            idx = info.get("playlist_index") or 0
            count = info.get("n_entries") or 0
            if count > 1 and idx:
                # one row downloading several videos: spread 0–100 % over them
                percent = ((idx - 1) + percent / 100) / count * 100
            finished = status == "finished" and is_last_stream
            on_progress(ProgressData(
                status="finished" if finished else "downloading",
                percent=min(percent, 100.0),
                speed="" if finished else _fmt_speed(d.get("speed") or 0),
                eta="" if finished else _fmt_eta(d.get("eta")),
                filename=d.get("filename", ""),
                title=info.get("title") or "",
                duration=info.get("duration"),
                eta_seconds=None if finished else d.get("eta"),
                playlist_index=idx if count > 1 else 0,
                playlist_count=count if count > 1 else 0,
                playlist_title=(info.get("playlist_title") or info.get("playlist") or "")
                if count > 1 else "",
            ))
        return hook


# Share of a video's bytes that is the picture (the rest is the audio track).
# Used to blend the separate video and audio downloads into one smooth bar.
_VIDEO_SHARE = 90.0


def _overall_percent(d: dict, info: dict, state: dict) -> tuple[float, bool]:
    """
    Progress (0–100) for the *whole* item, plus whether this is its last stream.

    For best quality, yt-dlp downloads the picture and the sound as two
    separate files, each reporting 0→100 %. Shown raw, the bar fills twice.
    Here the picture counts for the first 90 % and the sound for the last 10 %.
    """
    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
    if d.get("status") == "finished":
        p = 100.0
    elif total:
        p = min(d.get("downloaded_bytes", 0) / total * 100, 100.0)
    elif d.get("fragment_count"):
        p = min((d.get("fragment_index") or 0) / d["fragment_count"] * 100, 100.0)
    else:
        p = 0.0

    key = (info.get("id"), info.get("playlist_index"))
    if state.get("key") != key:            # a new video started
        state.clear()
        state["key"] = key
    vcodec, acodec = info.get("vcodec"), info.get("acodec")
    video_only = vcodec not in (None, "none") and acodec == "none"
    audio_only = vcodec == "none" and acodec not in (None, "none")
    if video_only:
        state["saw_video"] = True
        return p * _VIDEO_SHARE / 100, False          # the sound still follows
    if audio_only and state.get("saw_video"):
        return _VIDEO_SHARE + p * (100 - _VIDEO_SHARE) / 100, True
    return p, True                                     # single combined/audio file


def _make_pp_hook(cancel_check: Optional[CancelCheck]) -> Callable[[dict], None]:
    """Stop before the next FFmpeg step when cancelled (a running step finishes)."""
    def hook(d: dict) -> None:
        if cancel_check and cancel_check() and d.get("status") == "started":
            raise yt_dlp.utils.DownloadCancelled("Cancelled by user")
    return hook


class _PlaylistNotMedia(Exception):
    """A plain HTTP download turned out to be an HLS playlist (text), not media."""

    def __init__(self, url: str, filepath: str, title: str, headers: dict,
                 thumbnail: str = "") -> None:
        super().__init__(f"{url} is an HLS playlist")
        self.url = url
        self.filepath = filepath
        self.title = title
        self.headers = headers
        self.thumbnail = thumbnail


def _check_not_playlist(filepath: str, info: dict) -> None:
    """
    Raise _PlaylistNotMedia when a direct download saved an m3u8 playlist.

    Some sites link a URL ending in .mp4 that the CDN answers with an HLS
    master playlist. yt-dlp's generic extractor trusts the extension, saves
    the ~1 KB playlist as "video.mp4", and post-processing then fails
    (ffprobe finds no streams -> KeyError 'streams').
    """
    if info.get("protocol") not in ("http", "https") or not filepath:
        return
    try:
        if os.path.getsize(filepath) > 1024 * 1024:
            return
        with open(filepath, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return
    if not head.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"#EXTM3U"):
        return
    headers = dict(info.get("http_headers") or {})
    page = info.get("webpage_url")
    if page and "Referer" not in headers:
        headers["Referer"] = page
    raise _PlaylistNotMedia(info.get("url") or "", filepath,
                            info.get("title") or "", headers,
                            info.get("thumbnail") or "")


def _remove_file(path: str) -> None:
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError as exc:
        _log.debug("Could not remove %s: %s", path, exc)


def _remove_partials(paths: set) -> None:
    """Delete a cancelled download's leftovers (.part, .ytdl, fragments)."""
    for path in paths:
        for candidate in [path, path + ".ytdl", *glob.glob(glob.escape(path) + "-Frag*")]:
            try:
                if os.path.isfile(candidate):
                    os.remove(candidate)
            except OSError as exc:
                _log.debug("Could not remove partial %s: %s", candidate, exc)


# ── Format selection ──────────────────────────────────────────────────────────

def _max_height(quality: str) -> Optional[int]:
    """'1080p' -> 1080; 'best' / anything unparseable -> None (no cap)."""
    digits = "".join(c for c in (quality or "") if c.isdigit())
    return int(digits) if digits else None


_VIDEO_FORMAT = "bv*+ba/b"


def _video_format_sort(container: str, quality: str) -> list[str]:
    """
    yt-dlp ``format_sort`` keys for *container* capped at *quality*.

    Resolution is ranked first, so the container never costs quality:
    ``res:1080`` picks the largest video at or below 1080p, or the closest
    one above it when nothing smaller exists. Frame rate comes next, and only
    then the codec preferences, which break ties at the chosen resolution:

    - mp4 prefers SDR H.264 + AAC (plays on practically every device and TV),
      but takes VP9/AV1 when that is the only way to reach the resolution.
    - webm prefers the best of AV1/VP9 + Opus, since H.264/AAC cannot go in
      a webm file.
    - mkv takes whatever is best.
    The file is merged into *container* afterwards whichever streams win.
    """
    h = _max_height(quality)
    keys = [f"res:{h}" if h else "res"]
    if container == "mp4":
        # SDR before frame rate: an HDR stream looks washed out on the
        # ordinary screens mp4 is chosen for.
        keys += ["hdr:sdr", "fps", "vcodec:h264", "acodec:aac"]
    elif container == "webm":
        keys += ["fps", "vcodec", "acodec:opus"]
    else:
        keys += ["fps"]
    return keys


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