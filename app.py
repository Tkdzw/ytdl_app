"""
YT Downloader - Application Root
"""
from __future__ import annotations

import threading

import customtkinter as ctk

import app_info
from ui.main_window import MainWindow
from utils import tool_setup
from utils.history_manager import HistoryManager
from utils.logger import AppLogger
from utils.settings_manager import SettingsManager
from utils.tool_setup import ToolStatus


class YTDownloaderApp(ctk.CTk):
    """Root application class. Bootstraps all layers."""

    APP_TITLE    = f"{app_info.APP_NAME} {app_info.VERSION}"
    APP_GEOMETRY = "1160x780"
    MIN_SIZE     = (960, 660)

    def __init__(self) -> None:
        super().__init__()

        self.logger   = AppLogger.get_logger(__name__)
        self.settings = SettingsManager()
        self.history  = HistoryManager()

        # ── Find FFmpeg + JS runtime (saved paths, bundled copies, PATH…) ─────
        self.tools: ToolStatus = tool_setup.detect_tools(self.settings)

        # ── Appearance ────────────────────────────────────────────────────────
        mode = self.settings.get("appearance_mode")
        ctk.set_appearance_mode(mode)
        ctk.set_default_color_theme("blue")
        from ui.theme import apply_theme_overrides
        apply_theme_overrides()   # higher-contrast colours for both themes

        # ── Window ────────────────────────────────────────────────────────────
        self.title(self.APP_TITLE)
        self.geometry(self.APP_GEOMETRY)
        self.minsize(*self.MIN_SIZE)

        # ── UI ────────────────────────────────────────────────────────────────
        self._main_window = MainWindow(
            master=self,
            history_manager=self.history,
            settings=self.settings,
            tools=self.tools,
        )
        self._main_window.pack(fill="both", expand=True)

        if not self.tools.all_ok:
            self.after(400, self.show_setup)

        self.logger.info(
            "App started v%s | FFmpeg: %s | JS runtime: %s | Theme: %s",
            app_info.VERSION,
            self.tools.ffmpeg_dir or "missing",
            f"{self.tools.js.name} v{self.tools.js.version}"
            if self.tools.js_ok else "none",
            mode,
        )

    # ── Tools ─────────────────────────────────────────────────────────────────

    def show_setup(self) -> None:
        """Open the setup dialog (startup, or a "Fix" button)."""
        from ui.setup_dialog import SetupDialog
        SetupDialog(self, self.settings, self.tools,
                    on_status_changed=self.apply_tools)

    def apply_tools(self, status: ToolStatus) -> None:
        """Push a new tool status to every part of the UI (main thread)."""
        self.tools = status
        self._main_window.update_tools(status)

    def refresh_tools(self) -> None:
        """Re-detect tools in the background, then apply (e.g. after Settings edits)."""
        def work() -> None:
            status = tool_setup.detect_tools(self.settings)
            self.after(0, self.apply_tools, status)
        threading.Thread(target=work, daemon=True, name="ToolDetect").start()


# Old name, kept so existing scripts/imports keep working
YouTubeBatchDownloader = YTDownloaderApp
