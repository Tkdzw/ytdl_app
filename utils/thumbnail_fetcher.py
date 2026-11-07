"""
Utility: fetch a quick preview (title + thumbnail) for a pasted link.

YouTube links get their title from YouTube's public oEmbed endpoint and a
thumbnail from img.youtube.com — both fast, no API key, no yt-dlp run.
Other sites get no preview here; their title appears once the download
starts.

Network work happens on a background thread. The callback receives a PIL
image (not a Tk image): Tk objects must be created on the main thread, so
the UI converts it with ``to_ctk_image`` inside its ``after`` callback.
"""
from __future__ import annotations

import io
import json
import re
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import urllib.request
from typing import Callable, Optional

from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)

# At most 4 preview downloads at a time
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="Preview")

_THUMB_TEMPLATES = [
    "https://img.youtube.com/vi/{vid}/mqdefault.jpg",   # 320x180, always present
    "https://img.youtube.com/vi/{vid}/hqdefault.jpg",
]
_OEMBED = "https://www.youtube.com/oembed?format=json&url="
_UA = {"User-Agent": "Mozilla/5.0 (YTDownloader preview)"}


def extract_video_id(url: str) -> Optional[str]:
    """Extract the YouTube video ID from common URL forms."""
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


def _get(url: str, timeout: float = 6) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=timeout) as r:
        return r.read()


def fetch_preview_async(
    url: str,
    on_done: Callable[[str, Optional[object]], None],
    size: tuple[int, int] = (96, 54),
    want_title: bool = True,
) -> None:
    """
    Fetch (title, PIL image) for a YouTube *url* in the background and call
    ``on_done(title, image)``. Either value may be empty/None. Pass
    ``want_title=False`` when the title is already known (playlist entries).
    Runs on a small shared pool, so a 300-video playlist doesn't start 300
    threads or hit YouTube with 300 requests at once.
    """
    def worker() -> None:
        vid = extract_video_id(url)
        if not vid:
            on_done("", None)
            return
        title = ""
        try:
            if not want_title:
                raise LookupError("title not needed")
            data = json.loads(_get(_OEMBED + urllib.parse.quote(url, safe="")))
            title = data.get("title") or ""
        except LookupError:
            pass
        except Exception as exc:
            _log.debug("oEmbed failed for %s: %s", url, exc)
        image = None
        for template in _THUMB_TEMPLATES:
            try:
                from PIL import Image
                raw = _get(template.format(vid=vid))
                image = Image.open(io.BytesIO(raw)).convert("RGB").resize(size, Image.LANCZOS)
                break
            except Exception:
                continue
        on_done(title, image)

    _POOL.submit(worker)


def to_ctk_image(pil_image, size: tuple[int, int] = (96, 54)):
    """Wrap a PIL image for CustomTkinter. Call on the Tk main thread."""
    if pil_image is None:
        return None
    import customtkinter as ctk
    return ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=size)
