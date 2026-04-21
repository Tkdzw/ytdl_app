"""
Utility: Persistent download history backed by JSON.
"""
import json
import os
import threading
from datetime import datetime
from typing import Any

from utils.logger import AppLogger

_HISTORY_PATH = os.path.join(os.path.expanduser("~"), ".ytdl_app", "download_history.json")
_log = AppLogger.get_logger(__name__)


class HistoryManager:
    """Thread-safe manager for download_history.json."""

    def __init__(self, path: str = _HISTORY_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        if not os.path.exists(self._path):
            self._write([])

    # ── Public API ───────────────────────────────────────────────────────────

    def add_entry(
        self,
        title: str,
        url: str,
        fmt: str,
        status: str,
        filepath: str = "",
    ) -> None:
        """Append a new download record."""
        entry: dict[str, Any] = {
            "title": title,
            "url": url,
            "format": fmt,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": status,
            "filepath": filepath,
        }
        with self._lock:
            records = self._read()
            records.insert(0, entry)          # newest first
            self._write(records)
        _log.debug("History entry added: %s [%s]", title, status)

    def load_all(self) -> list[dict[str, Any]]:
        """Return all history records (newest first)."""
        with self._lock:
            return self._read()

    def clear(self) -> None:
        """Wipe all history."""
        with self._lock:
            self._write([])

    # ── Internal ─────────────────────────────────────────────────────────────

    def _read(self) -> list[dict[str, Any]]:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            _log.warning("Could not read history file; resetting.")
            return []

    def _write(self, records: list[dict[str, Any]]) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            _log.error("Failed to write history: %s", exc)

    def stats(self) -> dict[str, int]:
        """Return aggregate counts from history."""
        with self._lock:
            records = self._read()
        total     = len(records)
        succeeded = sum(1 for r in records if r.get("status") == "success")
        failed    = total - succeeded
        formats: dict[str, int] = {}
        for r in records:
            fmt = r.get("format", "unknown")
            formats[fmt] = formats.get(fmt, 0) + 1
        return {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "formats": formats,        # type: ignore[dict-item]
        }
