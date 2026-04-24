"""
YouTube Batch Downloader – Application Root
─────────────────────────────────────────────────────────────────────────────
Startup sequence:
  1. Resolve FFmpeg  via imageio-ffmpeg (zero install)
  2. Detect JS runtime (node/qjs/deno/bun) for yt-dlp's YouTube extractor
  3. Store both in SettingsManager so DownloadEngine picks them up
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

        # ── Resolve FFmpeg ────────────────────────────────────────────────────
        self.ffmpeg_ok, ffmpeg_path = self._resolve_ffmpeg()
        if ffmpeg_path:
            import os
            self.settings.set("_ffmpeg_location", os.path.dirname(ffmpeg_path))
            self.logger.info("FFmpeg location: %s", os.path.dirname(ffmpeg_path))

        # ── Detect JS runtime for yt-dlp ──────────────────────────────────────
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

        # Deferred warnings (after mainloop starts)
        if not self.ffmpeg_ok:
            self.after(300, self._show_ffmpeg_warning)
        elif not self.js_runtime.available:
            self.after(500, self._show_js_runtime_warning)

        self.logger.info(
            "App started  |  FFmpeg OK: %s  |  JS runtime: %s  |  Theme: %s",
            self.ffmpeg_ok,
            f"{self.js_runtime.name} v{self.js_runtime.version}" if self.js_runtime.available else "none",
            mode,
        )

    # ── FFmpeg resolution ─────────────────────────────────────────────────────

    def _resolve_ffmpeg(self) -> tuple[bool, str | None]:
        """Try imageio-ffmpeg first, fall back to legacy FFmpegChecker."""
        try:
            from ffmpeg_manager import get_ffmpeg_path, FFmpegNotFoundError
            path = get_ffmpeg_path()
            self.logger.info("FFmpeg resolved via imageio-ffmpeg: %s", path)
            return True, path
        except ImportError:
            self.logger.warning("ffmpeg_manager not found; trying legacy checker.")
        except Exception as exc:
            self.logger.warning("ffmpeg_manager failed (%s); trying legacy checker.", exc)

        try:
            from utils.ffmpeg_checker import FFmpegChecker
            ok = FFmpegChecker.check()
            path = FFmpegChecker.get_path() if ok else None
            if ok:
                self.logger.info("FFmpeg resolved via legacy checker: %s", path)
            else:
                self.logger.error(
                    "FFmpeg not found. Install imageio-ffmpeg: pip install imageio-ffmpeg"
                )
            return ok, path
        except Exception as exc:
            self.logger.error("FFmpegChecker raised: %s", exc)
            return False, None

    # ── JS runtime detection ──────────────────────────────────────────────────

    def _detect_js_runtime(self):
        """
        Detect a JS runtime and store results in settings for DownloadEngine.
        Returns a JsRuntimeResult (or a stub SimpleNamespace if module missing).
        """
        try:
            from js_runtime_manager import detect_js_runtime
            result = detect_js_runtime()
            self.settings.set("_js_runtime_name", result.name)
            self.settings.set("_js_runtime_path", result.path or "")
            return result
        except ImportError:
            self.logger.warning("js_runtime_manager not found; JS runtime detection skipped.")
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
