"""
YouTube Batch Downloader - Application Root
"""
from __future__ import annotations

import shutil

import customtkinter as ctk

from ui.main_window import MainWindow
from utils.logger import AppLogger
from utils.history_manager import HistoryManager
from utils.settings_manager import SettingsManager


class YouTubeBatchDownloader(ctk.CTk):
    """Root application class. Bootstraps all layers."""

    APP_TITLE    = "YT Batch Downloader"
    APP_GEOMETRY = "1160x740"
    MIN_SIZE     = (960, 620)

    def __init__(self) -> None:
        super().__init__()

        self.logger   = AppLogger.get_logger(__name__)
        self.settings = SettingsManager()
        self.history  = HistoryManager()

        # ── Validate saved FFmpeg path, fall back to PATH ─────────────────────
        self.ffmpeg_ok = self._check_ffmpeg()

        # ── Detect JS runtime ─────────────────────────────────────────────────
        self.js_runtime = self._detect_js_runtime()

        # ── Appearance ────────────────────────────────────────────────────────
        mode = self.settings.get("appearance_mode")
        ctk.set_appearance_mode(mode)
        ctk.set_default_color_theme("blue")

        # ── Window ────────────────────────────────────────────────────────────
        self.title(self.APP_TITLE)
        self.geometry(self.APP_GEOMETRY)
        self.minsize(*self.MIN_SIZE)

        # ── UI ────────────────────────────────────────────────────────────────
        self._main_window = MainWindow(
            master=self,
            history_manager=self.history,
            settings=self.settings,
            ffmpeg_ok=self.ffmpeg_ok,
            js_runtime=self.js_runtime,
        )
        self._main_window.pack(fill="both", expand=True)

        if not self.ffmpeg_ok:
            self.after(300, self._show_ffmpeg_warning)
        elif not self.js_runtime.available:
            self.after(500, self._show_js_runtime_warning)

        self.logger.info(
            "App started | FFmpeg OK: %s | JS runtime: %s | Theme: %s",
            self.ffmpeg_ok,
            f"{self.js_runtime.name} v{self.js_runtime.version}"
            if self.js_runtime.available else "none",
            mode,
        )

    # ── FFmpeg check ──────────────────────────────────────────────────────────

    def _check_ffmpeg(self) -> bool:
        """
        Verify FFmpeg is available.

        Checks the user-saved path from settings first, then falls back to
        system PATH. Updates _ffmpeg_location in settings if PATH is used so
        yt-dlp can find it immediately without re-searching.
        """
        import os

        saved_dir = self.settings.get("ffmpeg_bin_dir") or ""

        # 1. Check user-saved directory
        if saved_dir and os.path.isdir(saved_dir):
            exe = os.path.join(saved_dir, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
            if os.path.isfile(exe):
                self.settings.set("_ffmpeg_location", saved_dir)
                self.logger.info("FFmpeg from saved path: %s", exe)
                return True
            else:
                self.logger.warning(
                    "Saved FFmpeg path '%s' does not contain ffmpeg binary.", saved_dir
                )

        # 2. System PATH
        found = shutil.which("ffmpeg")
        if found:
            directory = os.path.dirname(os.path.abspath(found))
            self.settings.set("_ffmpeg_location", directory)
            self.logger.info("FFmpeg found on system PATH: %s", found)
            return True

        self.logger.error(
            "FFmpeg not found. Set the FFmpeg bin folder in Settings > Tools."
        )
        self.settings.set("_ffmpeg_location", "")
        return False

    # ── JS runtime ────────────────────────────────────────────────────────────

    def _detect_js_runtime(self):
        """Detect a JS runtime, respecting any user override in settings."""
        import os

        # Check for a user-supplied override first
        override = self.settings.get("js_runtime_override_path") or ""
        if override and os.path.isfile(override):
            from types import SimpleNamespace
            name = _guess_runtime_name(override)
            self.settings.set("_js_runtime_name", name)
            self.settings.set("_js_runtime_path", override)
            self.logger.info("JS runtime from user override: %s (%s)", override, name)
            return SimpleNamespace(available=True, name=name, path=override, version="user")

        # Auto-detect
        try:
            from js_runtime_manager import detect_js_runtime
            result = detect_js_runtime()
            self.settings.set("_js_runtime_name", result.name)
            self.settings.set("_js_runtime_path", result.path or "")
            return result
        except Exception as exc:
            self.logger.error("JS runtime detection failed: %s", exc)

        from types import SimpleNamespace
        return SimpleNamespace(available=False, name="none", path=None, version="")

    # ── Warnings ──────────────────────────────────────────────────────────────

    def _show_ffmpeg_warning(self) -> None:
        from ui.dialogs import show_ffmpeg_warning
        show_ffmpeg_warning(self)

    def _show_js_runtime_warning(self) -> None:
        from ui.dialogs import show_js_runtime_warning
        show_js_runtime_warning(self)


def _guess_runtime_name(path: str) -> str:
    base = __import__("os").path.basename(path).lower().replace(".exe", "")
    for name in ("node", "qjs", "deno", "bun"):
        if name in base:
            return name
    return "node"
