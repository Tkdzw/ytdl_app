"""
Utility: Persistent settings manager backed by JSON.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any

from utils.logger import AppLogger

_SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".ytdl_app", "settings.json")
_log = AppLogger.get_logger(__name__)

DEFAULTS: dict[str, Any] = {
    "output_dir": os.path.join(os.path.expanduser("~"), "Downloads", "YTBatchDL"),
    "default_video_format": "mp4",
    "default_mode": "Video",
    "audio_quality": "192",
    "appearance_mode": "dark",
    "ask_format_per_video": True,
    "auto_open_folder": False,
    "max_retries": 2,
    "embed_thumbnail": False,
    "write_subtitles": False,
    "subtitle_lang": "en",
    "rate_limit_kb": 0,
    "concurrent_fragments": 4,
    "skip_existing": True,
    "proxy_url": "",
    # ── User-configurable tool paths (shown in Settings > Tools) ──────────────
    "ffmpeg_bin_dir": "",           # user-supplied FFmpeg folder (blank = auto)
    "js_runtime_override_path": "", # user-supplied JS runtime binary (blank = auto)
    # ── Auto-detected at startup (not shown directly in UI) ───────────────────
    "_ffmpeg_location": "",         # resolved FFmpeg directory used by yt-dlp
    "_js_runtime_name": "",         # "node" | "qjs" | "deno" | "bun" | ""
    "_js_runtime_path": "",         # absolute path to JS runtime binary
}


class SettingsManager:
    """Thread-safe settings store with JSON persistence."""

    def __init__(self, path: str = _SETTINGS_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._data: dict[str, Any] = {}
        self._load()

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._save()

    def update(self, values: dict[str, Any]) -> None:
        with self._lock:
            self._data.update(values)
            self._save()

    def reset_to_defaults(self) -> None:
        with self._lock:
            self._data = dict(DEFAULTS)
            self._save()
        _log.info("Settings reset to defaults.")

    def all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def _load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            self._data = {**DEFAULTS, **stored}
            _log.debug("Settings loaded from %s", self._path)
        except (FileNotFoundError, json.JSONDecodeError):
            _log.info("No settings file found; using defaults.")
            self._data = dict(DEFAULTS)
            self._save()

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            _log.error("Failed to save settings: %s", exc)
