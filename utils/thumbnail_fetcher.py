"""
Utility: Async thumbnail fetcher.
Downloads a YouTube thumbnail image and returns a CTkImage.
"""
from __future__ import annotations

import io
import threading
import urllib.request
from typing import Callable, Optional

from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)

# Standard YouTube thumbnail URL patterns (highest quality → fallback)
_THUMB_TEMPLATES = [
    "https://img.youtube.com/vi/{vid}/maxresdefault.jpg",
    "https://img.youtube.com/vi/{vid}/hqdefault.jpg",
    "https://img.youtube.com/vi/{vid}/mqdefault.jpg",
]


def _extract_video_id(url: str) -> Optional[str]:
    """Extract the YouTube video ID from common URL forms."""
    import re
    patterns = [
        r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def fetch_thumbnail_async(
    url: str,
    on_done: Callable[["object | None"], None],  # CTkImage or None
    size: tuple[int, int] = (160, 90),
) -> None:
    """
    Fetch a YouTube thumbnail for *url* in a background thread.
    Calls on_done(ctk_image_or_none) on completion.
    Import of CTkImage is deferred to avoid circular imports.
    """
    def _worker() -> None:
        vid = _extract_video_id(url)
        if not vid:
            _log.debug("Could not extract video ID from: %s", url)
            on_done(None)
            return

        img_bytes: Optional[bytes] = None
        for template in _THUMB_TEMPLATES:
            thumb_url = template.format(vid=vid)
            try:
                with urllib.request.urlopen(thumb_url, timeout=6) as resp:
                    img_bytes = resp.read()
                break
            except Exception:
                continue

        if img_bytes is None:
            on_done(None)
            return

        try:
            from PIL import Image
            import customtkinter as ctk
            pil_img = Image.open(io.BytesIO(img_bytes)).resize(size, Image.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)
            on_done(ctk_img)
        except Exception as exc:
            _log.debug("Thumbnail conversion failed: %s", exc)
            on_done(None)

    threading.Thread(target=_worker, daemon=True).start()
