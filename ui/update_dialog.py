"""
UI: "Update YT Downloader" window.

Checks GitHub for the latest release, shows what's new, then downloads,
verifies and installs it (utils/app_updater.py). States:

    checking → up to date | update available | error
    update available → downloading → installing (app closes)
"""
from __future__ import annotations

import threading
import webbrowser
from typing import Callable, Optional

import customtkinter as ctk

import app_info
from ui import theme
from utils import app_updater
from utils.app_updater import ReleaseInfo, UpdateCancelled, UpdateError
from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)

_open_dialog: Optional["UpdateDialog"] = None


def show_update_dialog(
    parent: ctk.CTk,
    release: Optional[ReleaseInfo] = None,
    busy_check: Optional[Callable[[], int]] = None,
    before_quit: Optional[Callable[[], None]] = None,
) -> None:
    """Open (or focus) the update window. *release* skips the check when the
    caller already has it. *busy_check* returns how many downloads are running;
    *before_quit* stops them before the app closes for the update."""
    global _open_dialog
    if _open_dialog is not None and _open_dialog.winfo_exists():
        _open_dialog.lift()
        _open_dialog.focus_force()
        return
    _open_dialog = UpdateDialog(parent, release, busy_check, before_quit)


class UpdateDialog(ctk.CTkToplevel):
    def __init__(self, parent, release, busy_check, before_quit) -> None:
        super().__init__(parent)
        self._app = parent
        self._busy_check = busy_check or (lambda: 0)
        self._before_quit = before_quit
        self._release: Optional[ReleaseInfo] = release
        self._cancel = threading.Event()
        self._downloading = False

        self.title(f"Update {app_info.APP_NAME}")
        self.geometry("540x470")
        self.minsize(480, 400)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _: self._close())
        self.after(60, self._focus)

        self._title = ctk.CTkLabel(self, text="", anchor="w", font=theme.font(18, "bold"))
        self._title.pack(fill="x", padx=24, pady=(20, 2))
        self._sub = ctk.CTkLabel(self, text="", anchor="w", justify="left", wraplength=480,
                                 text_color=theme.MUTED, font=theme.font(13))
        self._sub.pack(fill="x", padx=24)

        self._notes = ctk.CTkTextbox(self, font=theme.font(12), wrap="word")
        self._bar = ctk.CTkProgressBar(self)
        self._bar_label = ctk.CTkLabel(self, text="", anchor="w", font=theme.font(12),
                                       text_color=theme.MUTED)

        self._buttons = ctk.CTkFrame(self, fg_color="transparent")
        self._buttons.pack(side="bottom", fill="x", padx=24, pady=(8, 18))

        if release is not None:
            self._show_release(release)
        else:
            self._start_check()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _focus(self) -> None:
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _safe_after(self, fn, *args) -> None:
        try:
            self.after(0, lambda: self.winfo_exists() and fn(*args))
        except Exception:
            pass   # window closed

    def _set_buttons(self, *specs: tuple[str, Callable[[], None], bool]) -> None:
        """specs: (text, command, primary). Right-aligned, first is rightmost."""
        for w in self._buttons.winfo_children():
            w.destroy()
        for text, cmd, primary in specs:
            kw = {} if primary else dict(fg_color="transparent", border_width=1,
                                         text_color=theme.TEXT)
            ctk.CTkButton(self._buttons, text=text, width=120, command=cmd,
                          **kw).pack(side="right", padx=(8, 0))

    def _hide_middle(self) -> None:
        for w in (self._notes, self._bar, self._bar_label):
            w.pack_forget()

    def _close(self) -> None:
        if self._downloading:
            self._cancel.set()
        self.destroy()

    # ── Checking ──────────────────────────────────────────────────────────────

    def _start_check(self) -> None:
        self._hide_middle()
        self._title.configure(text="Checking for updates…")
        self._sub.configure(text=f"You have version {app_info.DISPLAY_VERSION}.", text_color=theme.MUTED)
        self._set_buttons(("Close", self._close, False))

        def work() -> None:
            try:
                info = app_updater.check_latest()
            except UpdateError as exc:
                self._safe_after(self._show_error, str(exc), self._start_check)
                return
            self._safe_after(self._show_release, info)
        threading.Thread(target=work, daemon=True, name="UpdateCheck").start()

    def _show_release(self, info: ReleaseInfo) -> None:
        self._release = info
        self._hide_middle()
        if not info.is_newer:
            self._title.configure(text="✓  You're up to date")
            self._sub.configure(text_color=theme.MUTED, text=(
                f"Version {app_info.DISPLAY_VERSION} is the latest version."))
            self._set_buttons(("Close", self._close, True))
            return

        self._title.configure(text=f"Version {info.display_version} is available")
        size = f"  ·  {info.asset_size / 2**20:.0f} MB download" if info.asset_size else ""
        when = f"  ·  released {info.published}" if info.published else ""
        self._sub.configure(text_color=theme.MUTED,
                            text=f"You have version {app_info.DISPLAY_VERSION}{when}{size}")
        self._notes.configure(state="normal")
        self._notes.delete("1.0", "end")
        self._notes.insert("1.0", _plain_notes(info.notes) or "No release notes.")
        self._notes.configure(state="disabled")
        self._notes.pack(fill="both", expand=True, padx=24, pady=(12, 0))

        if not app_updater.can_self_update():
            self._sub.configure(text=self._sub.cget("text") + "\n\nThis copy wasn't installed "
                                "with the installer (e.g. it runs from source), so it can't "
                                "update itself. Download the new version from GitHub.")
            self._set_buttons(("Open download page", lambda: webbrowser.open(info.page_url), True),
                              ("Later", self._close, False))
            return
        if not info.asset_url:
            self._sub.configure(text=self._sub.cget("text") + "\n\nThis release has no "
                                "installer attached yet. Try again later, or see GitHub.")
            self._set_buttons(("Open on GitHub", lambda: webbrowser.open(info.page_url), True),
                              ("Later", self._close, False))
            return
        self._set_buttons(("Update now", self._confirm_update, True),
                          ("Later", self._close, False),
                          ("View on GitHub", lambda: webbrowser.open(info.page_url), False))

    def _show_error(self, message: str, retry: Callable[[], None]) -> None:
        self._downloading = False
        self._hide_middle()
        self._title.configure(text="Couldn't update")
        self._sub.configure(text=message, text_color=theme.BAD)
        self._set_buttons(("Try again", retry, True), ("Close", self._close, False))

    # ── Downloading + installing ──────────────────────────────────────────────

    def _confirm_update(self) -> None:
        running = self._busy_check()
        if running:
            from tkinter import messagebox
            if not messagebox.askokcancel(
                    "Downloads in progress",
                    f"{running} download(s) are still running. Updating closes the app "
                    "and stops them; you can start them again afterwards.\n\nUpdate now?",
                    parent=self):
                return
        self._start_download()

    def _start_download(self) -> None:
        info = self._release
        assert info is not None
        self._cancel.clear()
        self._downloading = True
        self._hide_middle()
        self._title.configure(text=f"Downloading version {info.display_version}…")
        self._sub.configure(text_color=theme.MUTED,
                            text="You can keep using the app while this downloads.")
        self._bar.set(0)
        self._bar.pack(fill="x", padx=24, pady=(24, 4))
        self._bar_label.configure(text="Starting…")
        self._bar_label.pack(fill="x", padx=24)
        self._set_buttons(("Cancel", self._cancel_download, False))

        def progress(done: int, total: int) -> None:
            self._safe_after(self._show_progress, done, total)

        def work() -> None:
            try:
                path = app_updater.download_installer(info, progress, self._cancel.is_set)
            except UpdateCancelled:
                self._safe_after(self._show_release, info)
                return
            except UpdateError as exc:
                self._safe_after(self._show_error, str(exc), self._start_download)
                return
            except Exception as exc:          # never leave the window stuck
                _log.exception("Update download failed")
                self._safe_after(self._show_error, f"Unexpected error: {exc}", self._start_download)
                return
            self._safe_after(self._install, path)
        threading.Thread(target=work, daemon=True, name="UpdateDownload").start()

    def _show_progress(self, done: int, total: int) -> None:
        if total:
            self._bar.set(done / total)
            self._bar_label.configure(
                text=f"{done / 2**20:.1f} of {total / 2**20:.1f} MB  ({done / total:.0%})")
        else:
            self._bar_label.configure(text=f"{done / 2**20:.1f} MB")

    def _cancel_download(self) -> None:
        self._cancel.set()
        self._bar_label.configure(text="Cancelling…")

    def _install(self, path: str) -> None:
        self._downloading = False
        self._bar.set(1)
        self._title.configure(text="Installing…")
        self._sub.configure(text_color=theme.MUTED, text=(
            "Windows will ask for permission to install. The app closes now and "
            "reopens by itself when the update is done (about a minute)."))
        self._bar_label.configure(text="✓ Download verified")
        self._set_buttons()
        self.update_idletasks()
        try:
            app_updater.launch_installer(path)
        except UpdateError as exc:
            self._show_error(str(exc), lambda: self._install(path))
            return
        # Installer is running: stop downloads and get out of its way.
        try:
            if self._before_quit:
                self._before_quit()
        finally:
            self._app.after(800, self._app.destroy)


def _plain_notes(markdown: str) -> str:
    """Release notes are Markdown; make them read well as plain text."""
    import re
    lines = []
    for line in (markdown or "").replace("\r\n", "\n").split("\n"):
        line = re.sub(r"^\s*#{1,6}\s*", "", line)                # headings
        line = re.sub(r"^(\s*)[-*+]\s+", r"\1•  ", line)          # bullets
        line = re.sub(r"\*\*(.+?)\*\*|__(.+?)__",
                      lambda m: m.group(1) or m.group(2), line)  # bold
        line = re.sub(r"`([^`]*)`", r"\1", line)                  # code
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)      # links
        if re.fullmatch(r"\s*-{3,}\s*", line):                   # rules
            line = ""
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
