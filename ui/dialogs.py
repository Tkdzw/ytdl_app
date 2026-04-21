"""
UI: Modal dialog helpers — FFmpeg warning, format picker, about dialog.
"""
from __future__ import annotations

import webbrowser
import customtkinter as ctk
from typing import Optional


# ── FFmpeg warning ────────────────────────────────────────────────────────────

def show_ffmpeg_warning(parent: ctk.CTk) -> None:
    dlg = ctk.CTkToplevel(parent)
    dlg.title("FFmpeg Not Found")
    dlg.geometry("440x220")
    dlg.resizable(False, False)
    dlg.grab_set()
    dlg.lift()
    dlg.focus_force()

    ctk.CTkLabel(
        dlg,
        text="⚠️  FFmpeg Not Found",
        font=ctk.CTkFont(size=18, weight="bold"),
        text_color="#FF6B6B",
    ).pack(pady=(28, 8))

    ctk.CTkLabel(
        dlg,
        text=(
            "FFmpeg is required to merge video/audio streams\n"
            "and convert to MP3. Downloads are disabled.\n\n"
            "Install FFmpeg and ensure it is on your system PATH."
        ),
        font=ctk.CTkFont(size=13),
        justify="center",
    ).pack(padx=24)

    ctk.CTkButton(
        dlg,
        text="OK",
        width=100,
        command=dlg.destroy,
    ).pack(pady=20)


# ── Per-video format selector ─────────────────────────────────────────────────

class FormatDialog(ctk.CTkToplevel):
    """
    Asks the user to pick a container format for a single video URL.
    Result is stored in self.chosen_format after the dialog closes.
    Call wait_window() before reading the result.
    """

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

        # Short URL label
        short_url = url if len(url) <= 55 else url[:52] + "…"

        ctk.CTkLabel(
            self,
            text="Select video format",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(24, 4))

        ctk.CTkLabel(
            self,
            text=short_url,
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(padx=16)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20, fill="x", padx=40)

        for fmt in self.FORMATS:
            ctk.CTkButton(
                btn_frame,
                text=fmt.upper(),
                width=80,
                height=44,
                font=ctk.CTkFont(size=14, weight="bold"),
                command=lambda f=fmt: self._choose(f),
            ).pack(side="left", expand=True, padx=6)

        ctk.CTkButton(
            self,
            text="Cancel (skip this video)",
            width=200,
            fg_color="transparent",
            border_width=1,
            text_color="gray",
            command=self.destroy,
        ).pack()

    def _choose(self, fmt: str) -> None:
        self.chosen_format = fmt
        self.destroy()


# ── About dialog ──────────────────────────────────────────────────────────────

class AboutDialog(ctk.CTkToplevel):
    """Application info, dependency versions, and links."""

    def __init__(self, parent: ctk.CTk) -> None:
        super().__init__(parent)
        self.title("About")
        self.geometry("420x360")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.focus_force()

        # ── Header ────────────────────────────────────────────────────────────
        ctk.CTkLabel(
            self,
            text="📺  YT Batch Downloader",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(28, 4))

        ctk.CTkLabel(
            self,
            text="v1.0.0  ·  Production Edition",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack()

        ctk.CTkFrame(self, height=1, fg_color="#333").pack(fill="x", padx=32, pady=16)

        # ── Dependency versions ───────────────────────────────────────────────
        versions_frame = ctk.CTkFrame(self, fg_color="transparent")
        versions_frame.pack(fill="x", padx=40)

        self._add_version_row(versions_frame, "Python", _get_python_version())
        self._add_version_row(versions_frame, "yt-dlp", _get_ytdlp_version())
        self._add_version_row(versions_frame, "CustomTkinter", _get_ctk_version())

        ctk.CTkFrame(self, height=1, fg_color="#333").pack(fill="x", padx=32, pady=16)

        # ── Links ─────────────────────────────────────────────────────────────
        links_frame = ctk.CTkFrame(self, fg_color="transparent")
        links_frame.pack()

        for text, url in [
            ("yt-dlp Docs", "https://github.com/yt-dlp/yt-dlp"),
            ("FFmpeg Download", "https://ffmpeg.org/download.html"),
        ]:
            ctk.CTkButton(
                links_frame,
                text=text,
                width=140,
                height=32,
                fg_color="transparent",
                border_width=1,
                command=lambda u=url: webbrowser.open(u),
            ).pack(side="left", padx=8)

        ctk.CTkButton(
            self, text="Close", width=100, command=self.destroy
        ).pack(pady=20)

    @staticmethod
    def _add_version_row(parent: ctk.CTkFrame, name: str, version: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text=name + ":", width=130, anchor="w",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkLabel(row, text=version, anchor="w",
                     font=ctk.CTkFont(size=12), text_color="#4EC9B0").pack(side="left")


def _get_python_version() -> str:
    import sys
    v = sys.version_info
    return f"{v.major}.{v.minor}.{v.micro}"


def _get_ytdlp_version() -> str:
    try:
        import yt_dlp
        return getattr(yt_dlp, "__version__", "unknown")
    except ImportError:
        return "not installed"


def _get_ctk_version() -> str:
    try:
        import customtkinter
        return getattr(customtkinter, "__version__", "unknown")
    except ImportError:
        return "unknown"


def show_about(parent: ctk.CTk) -> None:
    dlg = AboutDialog(parent)
    parent.wait_window(dlg)
