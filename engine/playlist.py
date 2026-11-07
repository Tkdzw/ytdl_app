"""
Engine: playlist detection and expansion.

A playlist (or channel) link is expanded into one queue item per video
before downloading, so every video gets its own row, progress bar, retry
button and history entry. Expansion uses yt-dlp's "flat" mode, which only
lists the entries (id, title, length) without resolving any video, so it is
quick even for long playlists.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

import yt_dlp

from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)

_YT_HOST = re.compile(r"^(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)$", re.I)
_YT_CHANNEL = re.compile(r"^/(?:@[^/]+|channel/[^/]+|c/[^/]+|user/[^/]+)(?:/(?:videos|shorts|streams|playlists))?/?$", re.I)
# Other sites' collection URLs that yt-dlp treats as playlists
_OTHER_COLLECTIONS = re.compile(r"/(?:sets|album|showcase|playlist|playlists)/", re.I)

# Entries yt-dlp lists but that can never be downloaded
_UNAVAILABLE_TITLES = {"[private video]", "[deleted video]", "[unavailable video]"}


@dataclass
class PlaylistEntry:
    url: str
    title: str = ""
    duration: Optional[float] = None


@dataclass
class PlaylistInfo:
    title: str
    entries: list[PlaylistEntry] = field(default_factory=list)
    skipped: int = 0            # private / deleted entries left out


def _parts(url: str):
    p = urllib.parse.urlparse(url.strip())
    return p, urllib.parse.parse_qs(p.query)


def is_youtube(url: str) -> bool:
    return bool(_YT_HOST.match(_parts(url)[0].netloc))


def is_video_in_playlist(url: str) -> bool:
    """A single video opened from a playlist, e.g. watch?v=ID&list=PL…"""
    p, q = _parts(url)
    if not _YT_HOST.match(p.netloc) or "list" not in q:
        return False
    has_video = "v" in q or p.netloc.lower().endswith("youtu.be") or p.path.startswith("/shorts/")
    # "RD…" lists are YouTube Mixes — endless auto-generated radio, not a real playlist
    return has_video and not q["list"][0].startswith("RD")


def looks_like_playlist(url: str) -> bool:
    """True for links that point at a list of videos rather than one video."""
    p, q = _parts(url)
    if _YT_HOST.match(p.netloc):
        if p.path.rstrip("/") == "/playlist" and "list" in q:
            return True
        return bool(_YT_CHANNEL.match(p.path))
    return bool(_OTHER_COLLECTIONS.search(p.path))


def playlist_url_for(url: str) -> str:
    """For watch?v=…&list=… return the plain playlist URL."""
    _, q = _parts(url)
    return f"https://www.youtube.com/playlist?list={q['list'][0]}" if "list" in q else url


def probe_playlist(url: str, proxy: str = "", _depth: int = 0) -> Optional[PlaylistInfo]:
    """
    List the videos in a playlist/channel link. Returns None if the link is
    not a playlist or can't be read (the caller then downloads it as-is).
    Blocking — call from a background thread.
    """
    opts = {
        "extract_flat": "in_playlist",
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreerrors": True,
    }
    if proxy:
        opts["proxy"] = proxy
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        _log.info("Playlist probe failed for %s: %s", url, exc)
        return None
    if not info or info.get("_type") not in ("playlist", "multi_video") or "entries" not in info:
        return None

    result = PlaylistInfo(title=info.get("title") or "Playlist")
    for entry in info.get("entries") or []:
        if not entry:
            result.skipped += 1
            continue
        entry_url = entry.get("url") or entry.get("webpage_url") or ""
        # A channel lists its tabs (Videos, Shorts, Live) as nested playlists
        if entry.get("_type") == "url" and (entry.get("ie_key") or "").endswith("Tab") and _depth < 2:
            nested = probe_playlist(entry_url, proxy, _depth + 1)
            if nested:
                result.entries.extend(nested.entries)
                result.skipped += nested.skipped
            continue
        title = entry.get("title") or ""
        if title.strip().lower() in _UNAVAILABLE_TITLES or not entry_url:
            result.skipped += 1
            continue
        if not entry_url.startswith("http") and is_youtube(url):
            entry_url = f"https://www.youtube.com/watch?v={entry_url}"
        result.entries.append(PlaylistEntry(url=entry_url, title=title,
                                            duration=entry.get("duration")))
    _log.info("Playlist %r: %d videos (%d unavailable skipped)",
              result.title, len(result.entries), result.skipped)
    return result if result.entries else None
