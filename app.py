"""
YouTube Batch Downloader - Application Root
"""
import customtkinter as ctk

from ui.main_window import MainWindow
from utils.ffmpeg_checker import FFmpegChecker
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

        # ── Shared services ───────────────────────────────────────────────────
        self.logger   = AppLogger.get_logger(__name__)
        self.settings = SettingsManager()
        self.history  = HistoryManager()

        # FFmpegChecker.check() also injects the discovered dir into PATH,
        # so yt-dlp subprocess calls will find ffmpeg automatically.
        self.ffmpeg_ok: bool = FFmpegChecker.check()

        # Store the resolved absolute path so the download engine can pass
        # it to yt-dlp via ffmpeg_location — works even when ffmpeg is NOT
        # on the system PATH (WinGet versioned folders, Scoop shims, etc.)
        ffmpeg_path = FFmpegChecker.get_path()
        if ffmpeg_path:
            import os
            # Store just the directory; yt-dlp's ffmpeg_location wants a dir
            self.settings.set("_ffmpeg_location", os.path.dirname(ffmpeg_path))
            self.logger.info("FFmpeg location for yt-dlp: %s", os.path.dirname(ffmpeg_path))

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
        )
        self._main_window.pack(fill="both", expand=True)

        if not self.ffmpeg_ok:
            self.after(300, self._show_ffmpeg_warning)

        self.logger.info(
            "App started  |  FFmpeg OK: %s  |  Theme: %s",
            self.ffmpeg_ok, mode,
        )

    def _show_ffmpeg_warning(self) -> None:
        from ui.dialogs import show_ffmpeg_warning
        show_ffmpeg_warning(self)
