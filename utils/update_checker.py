"""
Utility: yt-dlp version checker.
Compares the installed version against the latest PyPI release.
Runs in a background thread to avoid blocking startup.
"""
from __future__ import annotations

import threading
import urllib.request
import json
from typing import Callable, Optional

from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)
_PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"


def get_installed_version() -> str:
    """Return the installed yt-dlp version string, or 'unknown'."""
    try:
        import yt_dlp
        return getattr(yt_dlp, "__version__", "unknown")
    except ImportError:
        return "not installed"


def get_latest_version(timeout: int = 5) -> Optional[str]:
    """Fetch the latest yt-dlp version from PyPI. Returns None on failure."""
    try:
        with urllib.request.urlopen(_PYPI_URL, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data["info"]["version"]
    except Exception as exc:
        _log.debug("Could not fetch yt-dlp latest version: %s", exc)
        return None


class UpdateChecker:
    """
    Asynchronously checks whether yt-dlp has an update available.
    Calls on_result(installed, latest, update_available) when done.
    """

    def __init__(
        self,
        on_result: Callable[[str, str, bool], None],
    ) -> None:
        self._on_result = on_result

    def check_async(self) -> None:
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self) -> None:
        installed = get_installed_version()
        latest = get_latest_version()
        if latest is None:
            self._on_result(installed, "unknown", False)
            return
        update_available = installed != latest
        if update_available:
            _log.info("yt-dlp update available: %s → %s", installed, latest)
        self._on_result(installed, latest, update_available)
