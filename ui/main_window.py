"""
UI: MainWindow — wires sidebar + all tab frames together.
Owns the SettingsManager and propagates setting changes to other tabs.
"""
from __future__ import annotations

from typing import Any
import customtkinter as ctk

from utils.history_manager import HistoryManager
from utils.settings_manager import SettingsManager
from utils.update_checker import UpdateChecker
from ui.sidebar import Sidebar
from ui.tab_downloader import DownloaderTab
from ui.tab_batch_queue import BatchQueueTab
from ui.tab_history import HistoryTab
from ui.tab_settings import SettingsTab
from ui.dialogs import show_about


class MainWindow(ctk.CTkFrame):
    """
    Root content frame.
    Sidebar on left, content area on right.
    Owns SettingsManager; passes it to tabs that need it.
    """

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        history_manager: HistoryManager,
        settings: SettingsManager,
        ffmpeg_ok: bool,
        **kwargs,
    ) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent", **kwargs)
        self._history_manager = history_manager
        self._settings = settings
        self._ffmpeg_ok = ffmpeg_ok
        self._active_tab: str = "Downloader"

        self._build()
        self._run_update_check()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ── Sidebar ───────────────────────────────────────────────────────────
        self._sidebar = Sidebar(
            self,
            on_tab_change=self._switch_tab,
            on_about=self._show_about,
        )
        self._sidebar.pack(side="left", fill="y")

        # Separator
        ctk.CTkFrame(self, width=1, fg_color="#333333").pack(side="left", fill="y")

        # ── Content area ──────────────────────────────────────────────────────
        self._content = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self._content.pack(side="left", fill="both", expand=True)

        # ── Instantiate all tabs ──────────────────────────────────────────────
        self._batch_queue_tab = BatchQueueTab(self._content)

        self._downloader_tab = DownloaderTab(
            self._content,
            history_manager=self._history_manager,
            settings=self._settings,
            ffmpeg_ok=self._ffmpeg_ok,
            on_queue_update=self._on_queue_update,
        )

        self._history_tab = HistoryTab(
            self._content,
            history_manager=self._history_manager,
        )

        self._settings_tab = SettingsTab(
            self._content,
            settings=self._settings,
            on_settings_changed=self._on_settings_changed,
        )

        self._tab_map: dict[str, ctk.CTkFrame] = {
            "Downloader":  self._downloader_tab,
            "Batch Queue": self._batch_queue_tab,
            "History":     self._history_tab,
            "Settings":    self._settings_tab,
        }

        self._switch_tab("Downloader")

    # ── Tab switching ─────────────────────────────────────────────────────────

    def _switch_tab(self, tab_name: str) -> None:
        # Guard: sidebar fires _activate (→ this callback) during its own
        # __init__, before _tab_map has been created on this object.
        if not hasattr(self, "_tab_map"):
            return
        for frame in self._tab_map.values():
            frame.pack_forget()

        target = self._tab_map.get(tab_name)
        if target:
            target.pack(fill="both", expand=True)
            self._active_tab = tab_name

        if tab_name == "History":
            self._history_tab.refresh()

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_queue_update(self, items: list[dict[str, Any]]) -> None:
        self._batch_queue_tab.refresh(items)

    def _on_settings_changed(self, key: str, value: Any) -> None:
        """Propagate relevant setting changes to other tabs."""
        self._downloader_tab.on_settings_changed(key, value)

        # Live theme switching
        if key == "appearance_mode":
            ctk.set_appearance_mode(str(value))

    def _show_about(self) -> None:
        show_about(self.winfo_toplevel())

    # ── Update checker ────────────────────────────────────────────────────────

    def _run_update_check(self) -> None:
        def on_result(installed: str, latest: str, available: bool) -> None:
            if available:
                self.after(0, self._sidebar.show_update_badge, installed, latest)

        UpdateChecker(on_result=on_result).check_async()
