"""
YouTube Batch Downloader – Application Root
─────────────────────────────────────────────────────────────────────────────
FFmpeg is provided automatically via imageio-ffmpeg (zero user setup).
Falls back to system PATH / legacy FFmpegChecker if imageio-ffmpeg is absent.
"""
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

        # ── Shared services ───────────────────────────────────────────────────
        self.logger   = AppLogger.get_logger(__name__)
        self.settings = SettingsManager()
        self.history  = HistoryManager()

        # ── Resolve FFmpeg (imageio-ffmpeg first, legacy checker as fallback) ─
        self.ffmpeg_ok, ffmpeg_path = self._resolve_ffmpeg()

        if ffmpeg_path:
            import os
            ffmpeg_dir = os.path.dirname(ffmpeg_path)
            self.settings.set("_ffmpeg_location", ffmpeg_dir)
            self.logger.info("FFmpeg location stored for yt-dlp: %s", ffmpeg_dir)

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

        # Only show the warning if FFmpeg truly could not be found
        if not self.ffmpeg_ok:
            self.after(300, self._show_ffmpeg_warning)

        self.logger.info(
            "App started  |  FFmpeg OK: %s  |  Theme: %s",
            self.ffmpeg_ok, mode,
        )

    # ── FFmpeg resolution ─────────────────────────────────────────────────────

    def _resolve_ffmpeg(self) -> tuple[bool, str | None]:
        """
        Resolve FFmpeg using a two-strategy cascade:

        Strategy 1: ffmpeg_manager (uses imageio-ffmpeg bundled binary).
                    This is the primary path — zero user setup required.
        Strategy 2: Legacy FFmpegChecker (system PATH, WinGet, Scoop, etc.)
                    Retained for environments where imageio-ffmpeg is absent.

        Returns:
            (ffmpeg_ok: bool, ffmpeg_path: str | None)
        """
        # ── Strategy 1: imageio-ffmpeg bundled binary ─────────────────────────
        try:
            from ffmpeg_manager import get_ffmpeg_path, FFmpegNotFoundError
            path = get_ffmpeg_path()
            self.logger.info("FFmpeg resolved via imageio-ffmpeg: %s", path)
            return True, path
        except ImportError:
            self.logger.warning(
                "ffmpeg_manager module not found. "
                "Ensure ffmpeg_manager.py is present in the project root."
            )
        except Exception as exc:
            self.logger.warning(
                "ffmpeg_manager failed (%s); falling back to legacy checker.", exc
            )

        # ── Strategy 2: Legacy FFmpegChecker ─────────────────────────────────
        try:
            from utils.ffmpeg_checker import FFmpegChecker
            ok = FFmpegChecker.check()
            path = FFmpegChecker.get_path() if ok else None
            if ok:
                self.logger.info("FFmpeg resolved via legacy checker: %s", path)
            else:
                self.logger.error(
                    "FFmpeg not found by any strategy. "
                    "Install imageio-ffmpeg: pip install imageio-ffmpeg"
                )
            return ok, path
        except Exception as exc:
            self.logger.error("Legacy FFmpegChecker raised: %s", exc)
            return False, None

    def _show_ffmpeg_warning(self) -> None:
        from ui.dialogs import show_ffmpeg_warning
        show_ffmpeg_warning(self)
