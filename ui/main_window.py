"""
UI: MainWindow — wires sidebar + all tab frames together.
"""
from __future__ import annotations

from typing import Any
import customtkinter as ctk

from ui import theme

from utils.history_manager import HistoryManager
from utils.settings_manager import SettingsManager
from utils.tool_setup import ToolStatus
from utils.update_checker import UpdateChecker
from ui.sidebar import Sidebar
from ui.tab_downloader import DownloaderTab
from ui.tab_history import HistoryTab
from ui.tab_settings import SettingsTab
from ui.dialogs import show_about

# Settings whose change means FFmpeg / the JS runtime must be looked up again
_TOOL_KEYS = {"ffmpeg_bin_dir", "js_runtime_override_path"}


class MainWindow(ctk.CTkFrame):
    """
    Root content frame.
    Sidebar on left, content area on right.
    """

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        history_manager: HistoryManager,
        settings: SettingsManager,
        tools: ToolStatus,
        **kwargs,
    ) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent", **kwargs)
        self._history_manager = history_manager
        self._settings = settings
        self._tools = tools
        self._active_tab: str = "Downloader"
        self._tool_refresh_job = None

        self._build()
        self._run_update_check()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self._sidebar = Sidebar(
            self,
            on_tab_change=self._switch_tab,
            on_about=self._show_about,
        )
        self._sidebar.pack(side="left", fill="y")

        ctk.CTkFrame(self, width=1, fg_color=theme.DIVIDER).pack(side="left", fill="y")

        self._content = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self._content.pack(side="left", fill="both", expand=True)

        self._downloader_tab = DownloaderTab(
            self._content,
            history_manager=self._history_manager,
            settings=self._settings,
            ffmpeg_ok=self._tools.ffmpeg_ok,
            js_runtime=self._tools.js,
            on_fix_setup=lambda: self.winfo_toplevel().show_setup(),
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
            "History":     self._history_tab,
            "Settings":    self._settings_tab,
        }

        self._switch_tab("Downloader")

        # Ctrl+1/2/3 switch tabs
        top = self.winfo_toplevel()
        for i, name in enumerate(("Downloader", "History", "Settings"), start=1):
            top.bind(f"<Control-Key-{i}>", lambda _e, n=name: self._sidebar.select(n), add="+")

    # ── Tab switching ─────────────────────────────────────────────────────────

    def _switch_tab(self, tab_name: str) -> None:
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
        elif tab_name == "Settings":
            self._settings_tab.reload_from_settings()

    # ── Tools ─────────────────────────────────────────────────────────────────

    def update_tools(self, status: ToolStatus) -> None:
        self._tools = status
        self._downloader_tab.update_tools(status.ffmpeg_ok, status.js)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_settings_changed(self, key: str, value: Any) -> None:
        self._downloader_tab.on_settings_changed(key, value)
        if key == "appearance_mode":
            ctk.set_appearance_mode(str(value))
        if key in _TOOL_KEYS or key == "__reset__":
            # debounce: path fields save on every keystroke
            if self._tool_refresh_job:
                self.after_cancel(self._tool_refresh_job)
            self._tool_refresh_job = self.after(
                700, lambda: self.winfo_toplevel().refresh_tools())

    def _show_about(self) -> None:
        show_about(self.winfo_toplevel())

    # ── Update checker ────────────────────────────────────────────────────────

    def _run_update_check(self) -> None:
        def on_result(installed: str, latest: str, available: bool) -> None:
            if available:
                self.after(0, self._sidebar.show_update_badge, installed, latest)

        UpdateChecker(on_result=on_result).check_async()
