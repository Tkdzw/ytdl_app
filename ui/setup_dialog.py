"""
UI: First-run / "Fix" setup dialog.

Shows whether FFmpeg and a JavaScript runtime are available and, when
WinGet is present, installs the missing ones with one click. After an
install the tools are re-detected and the rest of the app is updated
immediately — no restart needed.
"""
from __future__ import annotations

import threading
import tkinter.filedialog as fd
import webbrowser
from typing import Callable, Optional

import customtkinter as ctk

from ui import theme

from utils import tool_setup
from utils.logger import AppLogger
from utils.tool_setup import ToolStatus

_log = AppLogger.get_logger(__name__)

_OK, _BAD, _WARN = theme.OK, theme.BAD, theme.WARN

_FFMPEG_PAGE = "https://github.com/yt-dlp/FFmpeg-Builds#ffmpeg-static-auto-builds"
_DENO_PAGE = "https://docs.deno.com/runtime/getting_started/installation/"


class SetupDialog(ctk.CTkToplevel):
    """Check, install and re-detect FFmpeg + a JS runtime."""

    def __init__(
        self,
        parent: ctk.CTk,
        settings,
        status: ToolStatus,
        on_status_changed: Optional[Callable[[ToolStatus], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._status = status
        self._on_status_changed = on_status_changed
        self._busy = False
        self._winget = tool_setup.winget_available()

        self.title("Finish setting up")
        self.geometry("600x580")
        self.minsize(540, 540)
        self.transient(parent)
        self.after(50, self._focus)

        self._build()
        self._render_status()

    def _focus(self) -> None:
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception:
            pass

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        ctk.CTkLabel(
            self, text="Finish setting up",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(anchor="w", padx=24, pady=(20, 2))

        intro = (
            "This app uses two free helper tools. "
            + ("Click Install and they are set up for you."
               if self._winget else
               "Install them, then click Check again.")
        )
        ctk.CTkLabel(
            self, text=intro, font=ctk.CTkFont(size=13),
            text_color=theme.MUTED, wraplength=520, justify="left",
        ).pack(anchor="w", padx=24, pady=(0, 14))

        self._ffmpeg_row = self._tool_row(
            "FFmpeg", "Joins video with audio and makes MP3 files. Required.",
            install=lambda: self._install([tool_setup.FFMPEG_WINGET_ID]),
            page=_FFMPEG_PAGE,
            choose=self._choose_ffmpeg_folder,
        )
        self._js_row = self._tool_row(
            "Deno (JavaScript runtime)",
            "Lets the app read most YouTube videos. Strongly recommended.",
            install=lambda: self._install([tool_setup.JS_WINGET_ID]),
            page=_DENO_PAGE,
        )

        self._status_line = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=13), anchor="w",
        )
        self._status_line.pack(fill="x", padx=24, pady=(10, 4))

        self._log_box = ctk.CTkTextbox(
            self, height=90, font=ctk.CTkFont(family="Consolas", size=12),
            state="disabled",
        )
        self._log_box.pack(fill="both", expand=True, padx=24, pady=(0, 10))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(0, 18))

        self._install_all_btn = ctk.CTkButton(
            footer, text="Install everything missing", height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._install_missing,
        )
        if self._winget:
            self._install_all_btn.pack(side="left")

        self._close_btn = ctk.CTkButton(
            footer, text="Close", width=90, height=36,
            fg_color="transparent", text_color=theme.TEXT, border_width=1, command=self._close,
        )
        self._close_btn.pack(side="right")
        self._recheck_btn = ctk.CTkButton(
            footer, text="Check again", width=110, height=36,
            fg_color="transparent", text_color=theme.TEXT, border_width=1, command=self._recheck,
        )
        self._recheck_btn.pack(side="right", padx=8)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _: self._close())

    def _tool_row(self, name: str, desc: str, install, page: str, choose=None) -> dict:
        frame = ctk.CTkFrame(self, corner_radius=8)
        frame.pack(fill="x", padx=24, pady=4)

        text_col = ctk.CTkFrame(frame, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True, padx=14, pady=10)
        ctk.CTkLabel(text_col, text=name, font=ctk.CTkFont(size=14, weight="bold"),
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(text_col, text=desc, font=ctk.CTkFont(size=12), text_color=theme.MUTED,
                     anchor="w", wraplength=330, justify="left").pack(fill="x")
        state = ctk.CTkLabel(text_col, text="", font=ctk.CTkFont(size=12, weight="bold"),
                             anchor="w")
        state.pack(fill="x", pady=(2, 0))

        btns = ctk.CTkFrame(frame, fg_color="transparent")
        btns.pack(side="right", padx=12)
        if self._winget:
            action = ctk.CTkButton(btns, text="Install", width=96, command=install)
        else:
            action = ctk.CTkButton(btns, text="Download page", width=120,
                                   command=lambda: webbrowser.open(page))
        action.pack(pady=2)
        if choose:
            ctk.CTkButton(
                btns, text="Choose folder…", width=120 if not self._winget else 96,
                fg_color="transparent", text_color=theme.TEXT, border_width=1, command=choose,
                font=ctk.CTkFont(size=12),
            ).pack(pady=2)
        return {"state": state, "action": action}

    # ── Status ────────────────────────────────────────────────────────────────

    def _render_status(self) -> None:
        s = self._status
        self._set_row(self._ffmpeg_row, s.ffmpeg_ok,
                      f"✓ Ready  ({s.ffmpeg_dir})" if s.ffmpeg_ok else "✗ Not found")
        js_text = (f"✓ Ready  ({s.js.name} {s.js.version})" if s.js_ok
                   else "✗ Not found")
        self._set_row(self._js_row, s.js_ok, js_text)

        if s.all_ok:
            self._status_line.configure(text="✓ All set — you can start downloading.",
                                        text_color=_OK)
            self._install_all_btn.configure(state="disabled")
            self._close_btn.configure(text="Done")
        elif not self._busy:
            self._status_line.configure(
                text=("FFmpeg is required before downloads can start."
                      if not s.ffmpeg_ok else
                      "Almost there — Deno is recommended for YouTube."),
                text_color=_BAD if not s.ffmpeg_ok else _WARN,
            )

    @staticmethod
    def _set_row(row: dict, ok: bool, text: str) -> None:
        row["state"].configure(text=text, text_color=_OK if ok else _BAD)
        row["action"].configure(state="disabled" if ok else "normal")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for w in (self._install_all_btn, self._recheck_btn, self._close_btn,
                  self._ffmpeg_row["action"], self._js_row["action"]):
            w.configure(state=state)
        if not busy:
            self._render_status()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _install_missing(self) -> None:
        ids = []
        if not self._status.ffmpeg_ok:
            ids.append(tool_setup.FFMPEG_WINGET_ID)
        if not self._status.js_ok:
            ids.append(tool_setup.JS_WINGET_ID)
        if ids:
            self._install(ids)

    def _install(self, package_ids: list[str]) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self._status_line.configure(
            text="Installing… this can take a minute. Please keep this window open.",
            text_color=_WARN,
        )

        def work() -> None:
            results = {}
            for pkg in package_ids:
                self._log_threadsafe(f"── winget install {pkg}")
                results[pkg] = tool_setup.winget_install(pkg, self._log_threadsafe)
            status = tool_setup.detect_tools(self._settings)
            self.after(0, self._install_finished, results, status)

        threading.Thread(target=work, daemon=True, name="ToolInstall").start()

    def _install_finished(self, results: dict, status: ToolStatus) -> None:
        self._apply_status(status)
        self._set_busy(False)
        failed = [p for p, ok in results.items() if not ok]
        if failed and not status.all_ok:
            self._status_line.configure(
                text="Install didn't finish. See the messages above, or use "
                     "“Choose folder…” / the download page.",
                text_color=_BAD,
            )

    def _recheck(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self._status_line.configure(text="Checking…", text_color=theme.MUTED)

        def work() -> None:
            status = tool_setup.detect_tools(self._settings)
            self.after(0, lambda: (self._apply_status(status), self._set_busy(False)))

        threading.Thread(target=work, daemon=True).start()

    def _choose_ffmpeg_folder(self) -> None:
        folder = fd.askdirectory(parent=self, title="Choose the folder that contains ffmpeg")
        if not folder:
            return
        if not tool_setup.find_ffmpeg_dir(folder) == folder:
            self._status_line.configure(
                text="That folder doesn't contain ffmpeg — pick its “bin” folder.",
                text_color=_BAD,
            )
            return
        self._settings.set("ffmpeg_bin_dir", folder)
        self._recheck()

    def _apply_status(self, status: ToolStatus) -> None:
        self._status = status
        if self._on_status_changed:
            self._on_status_changed(status)

    def _close(self) -> None:
        if self._busy:
            return
        try:
            self.grab_release()
        except Exception:
            pass
        # hide now, destroy once pending CTk redraws have run (avoids Tk errors)
        self.withdraw()
        self.after(300, self.destroy)

    # ── Log ───────────────────────────────────────────────────────────────────

    def _log_threadsafe(self, line: str) -> None:
        try:
            self.after(0, self._append_log, line)
        except Exception:
            pass

    def _append_log(self, line: str) -> None:
        self._log_box.configure(state="normal")
        self._log_box.insert("end", line + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")
