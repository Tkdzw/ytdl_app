"""
UI: Modal dialog helpers — per-video format picker, about.
(Tool setup lives in ui/setup_dialog.py.)
"""
from __future__ import annotations

import os
import sys
import threading
import webbrowser
from typing import Optional

import customtkinter as ctk

import app_info
from ui import theme
from ui.tooltip import add_tooltip


# ── Per-video format selector ─────────────────────────────────────────────────

class FormatDialog(ctk.CTkToplevel):
    """Asks the user to pick a container format for a single video URL."""

    FORMATS = ["mp4", "mkv", "webm"]

    def __init__(self, parent: ctk.CTk, url: str) -> None:
        super().__init__(parent)
        self.title("Choose Format")
        self.geometry("400x260")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.focus_force()

        self.chosen_format: Optional[str] = None

        short_url = url if len(url) <= 55 else url[:52] + "…"

        ctk.CTkLabel(
            self, text="Select video format",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(24, 4))

        ctk.CTkLabel(
            self, text=short_url,
            font=ctk.CTkFont(size=12), text_color=theme.MUTED,
        ).pack(padx=16)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20, fill="x", padx=40)

        for fmt in self.FORMATS:
            ctk.CTkButton(
                btn_frame, text=fmt.upper(),
                width=80, height=44,
                font=ctk.CTkFont(size=14, weight="bold"),
                command=lambda f=fmt: self._choose(f),
            ).pack(side="left", expand=True, padx=6)

        ctk.CTkButton(
            self, text="Cancel (skip this video)",
            width=200, fg_color="transparent",
            border_width=1, text_color=theme.MUTED,
            command=self.destroy,
        ).pack()

        # keyboard: Esc skips, 1/2/3 pick MP4/MKV/WEBM, Enter picks MP4
        self.bind("<Escape>", lambda _: self.destroy())
        self.bind("<Return>", lambda _: self._choose("mp4"))
        for i, fmt in enumerate(self.FORMATS, start=1):
            self.bind(str(i), lambda _e, f=fmt: self._choose(f))

    def _choose(self, fmt: str) -> None:
        self.chosen_format = fmt
        self.destroy()


# ── Video-in-playlist choice ──────────────────────────────────────────────────

class PlaylistChoiceDialog(ctk.CTkToplevel):
    """
    For links like watch?v=…&list=…: download just that video, or the whole
    playlist? ``choice`` is "video", "playlist" or None (skipped).
    ``apply_to_all`` is True when the user wants the same answer for the
    other such links in this paste.
    """

    def __init__(self, parent: ctk.CTk, url: str, remaining: int = 0) -> None:
        super().__init__(parent)
        self.title("Video or playlist?")
        self.geometry("520x300" if remaining else "520x260")
        self.resizable(False, False)
        self.transient(parent)
        self.choice: Optional[str] = None
        self._all_var = ctk.BooleanVar(value=False)

        ctk.CTkLabel(self, text="This link is a video inside a playlist",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(22, 4), padx=20, anchor="w")
        short = url if len(url) <= 70 else url[:67] + "…"
        ctk.CTkLabel(self, text=short, font=ctk.CTkFont(size=12), text_color=theme.MUTED,
                     ).pack(padx=20, anchor="w")
        ctk.CTkLabel(self, text="What would you like to download?", font=ctk.CTkFont(size=13),
                     ).pack(padx=20, pady=(12, 6), anchor="w")

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=4)
        ctk.CTkButton(row, text="Just this video", height=40, font=ctk.CTkFont(size=14, weight="bold"),
                      command=lambda: self._pick("video")).pack(side="left", expand=True, fill="x", padx=(0, 6))
        ctk.CTkButton(row, text="The whole playlist", height=40, font=ctk.CTkFont(size=14),
                      fg_color="transparent", text_color=theme.TEXT, border_width=1,
                      command=lambda: self._pick("playlist")).pack(side="left", expand=True, fill="x", padx=(6, 0))

        if remaining:
            ctk.CTkCheckBox(self, text=f"Do the same for the other {remaining} link(s) like this",
                            variable=self._all_var, font=ctk.CTkFont(size=12),
                            ).pack(padx=20, pady=(12, 0), anchor="w")
        ctk.CTkButton(self, text="Skip this link", width=140, fg_color="transparent",
                      text_color=theme.MUTED, border_width=1, command=self.destroy,
                      ).pack(pady=14)

        self.bind("<Escape>", lambda _: self.destroy())
        self.bind("<Return>", lambda _: self._pick("video"))
        self.after(50, self._grab)

    def _grab(self) -> None:
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception:
            pass

    @property
    def apply_to_all(self) -> bool:
        return bool(getattr(self, "_apply_all", False))

    def _pick(self, choice: str) -> None:
        self.choice = choice
        self._apply_all = self._all_var.get()
        self.destroy()


# ── About dialog ──────────────────────────────────────────────────────────────

class AboutDialog(ctk.CTkToplevel):
    """App name, version, developer, environment details, file locations,
    what's new and keyboard shortcuts. Tool versions load in the background
    so the window opens instantly."""

    def __init__(self, parent: ctk.CTk) -> None:
        super().__init__(parent)
        self.title(f"About {app_info.APP_NAME}")
        self.geometry("560x720")
        self.minsize(520, 560)
        self.transient(parent)
        self.bind("<Escape>", lambda _: self.destroy())
        self.after(50, self._focus)
        self._values: dict[str, ctk.CTkLabel] = {}

        # ── Header ────────────────────────────────────────────────────────────
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=28, pady=(22, 6))
        ctk.CTkLabel(head, text="📥", font=ctk.CTkFont(size=40)).pack(side="left", padx=(0, 14))
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(titles, text=app_info.APP_NAME, anchor="w",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(fill="x")
        ctk.CTkLabel(titles, anchor="w", text_color=theme.MUTED, font=ctk.CTkFont(size=13),
                     text=f"Version {app_info.VERSION}  ·  Released {_nice_date(app_info.RELEASE_DATE)}",
                     ).pack(fill="x")
        ctk.CTkLabel(titles, anchor="w", font=ctk.CTkFont(size=13),
                     text=f"Developed by {app_info.DEVELOPER}").pack(fill="x")
        ctk.CTkLabel(self, text=app_info.DESCRIPTION, anchor="w", text_color=theme.MUTED,
                     font=ctk.CTkFont(size=13)).pack(fill="x", padx=28, pady=(4, 0))

        body = ctk.CTkScrollableFrame(self, label_text="")
        body.pack(fill="both", expand=True, padx=16, pady=(10, 4))

        # ── What's new ────────────────────────────────────────────────────────
        self._heading(body, f"What's new in {app_info.VERSION}")
        for line in app_info.WHATS_NEW:
            item = ctk.CTkFrame(body, fg_color="transparent")
            item.pack(fill="x", padx=12, pady=1)
            ctk.CTkLabel(item, text="•", width=14, anchor="nw",
                         font=ctk.CTkFont(size=12)).pack(side="left", anchor="n")
            ctk.CTkLabel(item, text=line, anchor="w", justify="left", wraplength=440,
                         font=ctk.CTkFont(size=12)).pack(side="left", fill="x", expand=True)

        # ── Details (filled in the background) ────────────────────────────────
        self._heading(body, "Details")
        for name, value in [
            ("App version", app_info.VERSION),
            ("Build", "Installed app" if getattr(sys, "frozen", False) else "Running from source"),
            ("Windows", _os_version()),
            ("Python", _get_python_version()),
            ("yt-dlp", "checking…"),
            ("FFmpeg", "checking…"),
            ("JavaScript runtime", "checking…"),
            ("CustomTkinter", _get_ctk_version()),
        ]:
            self._values[name] = self._row(body, name, value)

        # ── Your files ────────────────────────────────────────────────────────
        self._heading(body, "Your files")
        from utils.settings_manager import SettingsManager
        downloads = SettingsManager().get("output_dir")
        data_dir = os.path.join(os.path.expanduser("~"), ".ytdl_app")
        for name, path, tip in [
            ("Downloads", downloads, "Where new downloads are saved"),
            ("Settings & history", data_dir, "settings.json and download_history.json"),
            ("Log files", os.path.join(data_dir, "logs"), "Useful when reporting a problem"),
        ]:
            self._folder_row(body, name, path)

        # ── Keyboard shortcuts ────────────────────────────────────────────────
        self._heading(body, "Keyboard shortcuts")
        for combo, what in [
            ("Ctrl+V", "Add links from the clipboard"),
            ("Ctrl+Enter", "Start downloading"),
            ("Ctrl+L", "Jump to the link box"),
            ("Ctrl+1 / 2 / 3", "Downloader / History / Settings"),
            ("Esc", "Close a dialog"),
        ]:
            self._row(body, combo, what, color=theme.TEXT)

        # ── Credits ───────────────────────────────────────────────────────────
        self._heading(body, "Credits")
        ctk.CTkLabel(
            body, anchor="w", justify="left", wraplength=470, font=ctk.CTkFont(size=12),
            text_color=theme.MUTED,
            text=(f"{app_info.CREDITS}\nFFmpeg is licensed under the GPL and Deno under "
                  f"the MIT licence; their licence files are included with the app.\n"
                  f"{app_info.COPYRIGHT}. All rights reserved."),
        ).pack(fill="x", padx=12, pady=(0, 8))

        links = ctk.CTkFrame(body, fg_color="transparent")
        links.pack(fill="x", padx=8, pady=(0, 8))
        for text, url in [("yt-dlp", "https://github.com/yt-dlp/yt-dlp"),
                          ("FFmpeg", "https://ffmpeg.org/"),
                          ("Deno", "https://deno.com/")]:
            ctk.CTkButton(links, text=text, width=100, height=30, fg_color="transparent",
                          text_color=theme.TEXT, border_width=1,
                          command=lambda u=url: webbrowser.open(u)).pack(side="left", padx=4)

        # ── Footer ────────────────────────────────────────────────────────────
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=28, pady=(6, 16))
        self._copy_btn = ctk.CTkButton(
            footer, text="Copy details", width=130, fg_color="transparent",
            text_color=theme.TEXT, border_width=1, command=self._copy_details)
        self._copy_btn.pack(side="left")
        add_tooltip(self._copy_btn, "Copies the version information — handy when reporting a problem.")
        ctk.CTkButton(footer, text="Close", width=100, command=self.destroy).pack(side="right")

        threading.Thread(target=self._load_versions, daemon=True).start()

    # ── Building helpers ──────────────────────────────────────────────────────

    def _focus(self) -> None:
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    @staticmethod
    def _heading(parent, text: str) -> None:
        ctk.CTkLabel(parent, text=text, anchor="w",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", padx=8, pady=(14, 4))
        theme.divider(parent, padx=8, pady=(0, 6))

    @staticmethod
    def _row(parent, name: str, value: str, color=theme.INFO) -> ctk.CTkLabel:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=1)
        ctk.CTkLabel(row, text=name, width=150, anchor="w",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        val = ctk.CTkLabel(row, text=value, anchor="w", justify="left", wraplength=320,
                           font=ctk.CTkFont(size=12), text_color=color)
        val.pack(side="left", fill="x", expand=True)
        return val

    def _folder_row(self, parent, name: str, path: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(row, text=name, width=150, anchor="w",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        short = path if len(path) <= 38 else "…" + path[-37:]
        lbl = ctk.CTkLabel(row, text=short, anchor="w", font=ctk.CTkFont(size=12),
                           text_color=theme.MUTED)
        lbl.pack(side="left", fill="x", expand=True)
        add_tooltip(lbl, path)
        ctk.CTkButton(row, text="Open", width=64, height=26, fg_color="transparent",
                      text_color=theme.TEXT, border_width=1,
                      command=lambda p=path: _open_folder(p)).pack(side="right")

    # ── Background version lookup ─────────────────────────────────────────────

    def _load_versions(self) -> None:
        results = {
            "yt-dlp": _get_ytdlp_version(),
            "FFmpeg": _get_ffmpeg_version(),
            "JavaScript runtime": _get_js_runtime_version(),
        }
        try:
            self.after(0, self._show_versions, results)
        except Exception:
            pass   # window closed meanwhile

    def _show_versions(self, results: dict) -> None:
        if not self.winfo_exists():
            return
        for name, value in results.items():
            self._values[name].configure(text=value)

    def _copy_details(self) -> None:
        lines = [f"{app_info.APP_NAME} {app_info.VERSION} ({app_info.RELEASE_DATE})"]
        lines += [f"{name}: {lbl.cget('text')}" for name, lbl in self._values.items()]
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self._copy_btn.configure(text="✓ Copied")
        self.after(1500, lambda: self._copy_btn.winfo_exists()
                   and self._copy_btn.configure(text="Copy details"))


def _nice_date(iso: str) -> str:
    try:
        from datetime import date
        d = date.fromisoformat(iso)
        return f"{d.day} {d.strftime('%B %Y')}"
    except ValueError:
        return iso


def _os_version() -> str:
    try:
        import platform
        if sys.platform == "win32":
            ver = sys.getwindowsversion()
            name = "Windows 11" if ver.build >= 22000 else f"Windows {platform.release()}"
            return f"{name} (build {ver.build})"
        return platform.platform()
    except Exception:
        return "unknown"


def _open_folder(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606 - local folder
        else:
            import subprocess
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])
    except Exception:
        pass


def _get_python_version() -> str:
    v = sys.version_info
    return f"{v.major}.{v.minor}.{v.micro}"


def _get_ytdlp_version() -> str:
    try:
        import yt_dlp.version
        return yt_dlp.version.__version__
    except Exception:
        return "not installed"


def _get_ctk_version() -> str:
    try:
        import customtkinter
        return getattr(customtkinter, "__version__", "unknown")
    except ImportError:
        return "unknown"


def _get_js_runtime_version() -> str:
    try:
        from utils.settings_manager import SettingsManager
        from utils.tool_setup import find_js_runtime
        result = find_js_runtime(SettingsManager().get("js_runtime_override_path") or "")
        if result.available:
            return f"{result.name} {result.version}"
        return "not found — click “Fix” on the home screen"
    except Exception:
        return "unknown"


def _get_ffmpeg_version() -> str:
    try:
        from ffmpeg_manager import get_ffmpeg_version
        from utils.settings_manager import SettingsManager
        version = get_ffmpeg_version(SettingsManager().get("_ffmpeg_location") or "")
        return version if version != "unknown" else "not found — click “Fix” on the home screen"
    except Exception:
        return "unknown"


def show_about(parent: ctk.CTk) -> None:
    AboutDialog(parent)
