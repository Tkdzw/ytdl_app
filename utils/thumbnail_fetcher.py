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
import threading
import urllib.parse
import urllib.request
from typing import Callable, Optional

from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)

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
) -> None:
    """
    Fetch (title, PIL image) for a YouTube *url* in the background and call
    ``on_done(title, image)``. Either value may be empty/None.
    """
    def worker() -> None:
        vid = extract_video_id(url)
        if not vid:
            on_done("", None)
            return
        title = ""
        try:
            data = json.loads(_get(_OEMBED + urllib.parse.quote(url, safe="")))
            title = data.get("title") or ""
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

    threading.Thread(target=worker, daemon=True, name="Preview").start()


def to_ctk_image(pil_image, size: tuple[int, int] = (96, 54)):
    """Wrap a PIL image for CustomTkinter. Call on the Tk main thread."""
    if pil_image is None:
        return None
    import customtkinter as ctk
    return ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=size)
