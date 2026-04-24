"""
UI: Modal dialog helpers — FFmpeg warning, JS runtime warning, format picker, about.
"""
from __future__ import annotations

import sys
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
            "Fix: pip install imageio-ffmpeg"
        ),
        font=ctk.CTkFont(size=13),
        justify="center",
    ).pack(padx=24)

    ctk.CTkButton(dlg, text="OK", width=100, command=dlg.destroy).pack(pady=20)


# ── JS runtime warning ────────────────────────────────────────────────────────

def show_js_runtime_warning(parent: ctk.CTk) -> None:
    """
    Shown at startup when no JS runtime (node/qjs/deno/bun) is found.
    yt-dlp now requires one for YouTube extraction; without it many
    videos fail with 'This video is not available'.
    """
    if sys.platform == "win32":
        install_cmd = "winget install OpenJS.NodeJS"
        install_note = "Then restart the app."
    elif sys.platform == "darwin":
        install_cmd = "brew install node"
        install_note = "Then restart the app."
    else:
        install_cmd = "sudo apt install nodejs   # or: sudo dnf install nodejs"
        install_note = "Then restart the app."

    dlg = ctk.CTkToplevel(parent)
    dlg.title("JavaScript Runtime Not Found")
    dlg.geometry("520x300")
    dlg.resizable(False, False)
    dlg.grab_set()
    dlg.lift()
    dlg.focus_force()

    ctk.CTkLabel(
        dlg,
        text="⚠️  No JavaScript Runtime Found",
        font=ctk.CTkFont(size=17, weight="bold"),
        text_color="#DCDCAA",
    ).pack(pady=(24, 6))

    ctk.CTkLabel(
        dlg,
        text=(
            "yt-dlp now requires Node.js (or QuickJS/Deno/Bun)\n"
            "to extract YouTube videos. Without one, many videos\n"
            "will fail with \"This video is not available\"."
        ),
        font=ctk.CTkFont(size=13),
        justify="center",
    ).pack(padx=24)

    ctk.CTkFrame(dlg, height=1, fg_color="#444").pack(fill="x", padx=32, pady=14)

    ctk.CTkLabel(
        dlg,
        text="Install Node.js:",
        font=ctk.CTkFont(size=12, weight="bold"),
    ).pack()

    cmd_box = ctk.CTkEntry(
        dlg, width=380, font=ctk.CTkFont(family="Courier", size=12)
    )
    cmd_box.insert(0, install_cmd)
    cmd_box.configure(state="readonly")
    cmd_box.pack(pady=(4, 2))

    ctk.CTkLabel(
        dlg, text=install_note, font=ctk.CTkFont(size=11), text_color="gray"
    ).pack()

    btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
    btn_row.pack(pady=16)

    ctk.CTkButton(
        btn_row, text="Open nodejs.org", width=150,
        fg_color="transparent", border_width=1,
        command=lambda: webbrowser.open("https://nodejs.org/"),
    ).pack(side="left", padx=8)

    ctk.CTkButton(
        btn_row, text="Continue Anyway", width=150,
        fg_color="transparent", border_width=1,
        text_color="gray",
        command=dlg.destroy,
    ).pack(side="left", padx=8)


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
            font=ctk.CTkFont(size=11), text_color="gray",
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
            border_width=1, text_color="gray",
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
        self.geometry("440x400")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.focus_force()

        ctk.CTkLabel(
            self,
            text="📺  YT Batch Downloader",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(28, 4))

        ctk.CTkLabel(
            self, text="v1.0.0  ·  Production Edition",
            font=ctk.CTkFont(size=12), text_color="gray",
        ).pack()

        ctk.CTkFrame(self, height=1, fg_color="#333").pack(fill="x", padx=32, pady=16)

        versions_frame = ctk.CTkFrame(self, fg_color="transparent")
        versions_frame.pack(fill="x", padx=40)

        self._add_version_row(versions_frame, "Python",         _get_python_version())
        self._add_version_row(versions_frame, "yt-dlp",         _get_ytdlp_version())
        self._add_version_row(versions_frame, "CustomTkinter",  _get_ctk_version())
        self._add_version_row(versions_frame, "JS runtime",     _get_js_runtime_version())
        self._add_version_row(versions_frame, "FFmpeg",         _get_ffmpeg_version())

        ctk.CTkFrame(self, height=1, fg_color="#333").pack(fill="x", padx=32, pady=16)

        links_frame = ctk.CTkFrame(self, fg_color="transparent")
        links_frame.pack()

        for text, url in [
            ("yt-dlp Docs",    "https://github.com/yt-dlp/yt-dlp"),
            ("Node.js",        "https://nodejs.org/"),
        ]:
            ctk.CTkButton(
                links_frame, text=text, width=140, height=32,
                fg_color="transparent", border_width=1,
                command=lambda u=url: webbrowser.open(u),
            ).pack(side="left", padx=8)

        ctk.CTkButton(self, text="Close", width=100, command=self.destroy).pack(pady=20)

    @staticmethod
    def _add_version_row(parent: ctk.CTkFrame, name: str, version: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text=name + ":", width=130, anchor="w",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkLabel(row, text=version, anchor="w",
                     font=ctk.CTkFont(size=12), text_color="#4EC9B0").pack(side="left")


def _get_python_version() -> str:
    v = sys.version_info
    return f"{v.major}.{v.minor}.{v.micro}"


def _get_ytdlp_version() -> str:
    try:
        import yt_dlp.version
        return yt_dlp.version.__version__
    except Exception:
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


def _get_js_runtime_version() -> str:
    try:
        from js_runtime_manager import detect_js_runtime
        result = detect_js_runtime()
        if result.available:
            return f"{result.name} v{result.version}"
        return "not found"
    except Exception:
        return "unknown"


def _get_ffmpeg_version() -> str:
    try:
        from ffmpeg_manager import get_ffmpeg_version
        return get_ffmpeg_version()
    except Exception:
        return "unknown"


def show_about(parent: ctk.CTk) -> None:
    dlg = AboutDialog(parent)
    parent.wait_window(dlg)