"""
UI Tab: Downloader — the home screen.

Paste links → they appear in the download list (with title + thumbnail) →
Start. The list shows every item's status with per-row actions; overall
progress, a finish banner and plain-language errors sit around it. The
raw yt-dlp log is still available behind "Show details".
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Callable, Optional

import customtkinter as ctk

from ui import theme

import dataclasses
import threading

from engine.download_queue import (
    CANCELLED, CHECKING, COMPLETED, DOWNLOADING, FAILED, READY,
    DownloadQueue, QueueItem, QueueWorker,
)
from engine.playlist import (
    PlaylistInfo, is_video_in_playlist, looks_like_playlist, playlist_url_for, probe_playlist,
)
from engine.downloader import DownloadRequest, DownloadResult, ProgressData, _DEFAULT_OUTPUT_DIR
from ui.dialogs import FormatDialog, PlaylistChoiceDialog
from ui.queue_list import QueueList
from utils.history_manager import HistoryManager
from utils.logger import AppLogger
from utils.settings_manager import SettingsManager
from utils.thumbnail_fetcher import fetch_preview_async, to_ctk_image
from utils.url_validator import validate_urls

_log = AppLogger.get_logger(__name__)

_AUDIO_LABEL = "Audio (MP3)"          # also the stored "default_mode" value
_VIDEO_QUALITIES = ["Best", "1080p", "720p", "480p"]
_AUDIO_QUALITIES = ["128 kbps", "192 kbps", "256 kbps", "320 kbps"]
_QUALITY_HINTS = {
    "Best":     "Highest available – can be 4K and very large",
    "1080p":    "Full HD – recommended",
    "720p":     "HD – smaller files",
    "480p":     "Smallest video files",
    "128 kbps": "Smallest files",
    "192 kbps": "Good quality – recommended",
    "256 kbps": "High quality",
    "320 kbps": "Highest quality – larger files",
}
_OK, _BAD, _WARN, _INFO = theme.OK, theme.BAD, theme.WARN, theme.INFO


class DownloaderTab(ctk.CTkFrame):
    """Main download interface tab."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        history_manager: HistoryManager,
        settings: SettingsManager,
        ffmpeg_ok: bool,
        js_runtime=None,
        on_fix_setup: Optional[Callable[[], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._history = history_manager
        self._settings = settings
        self._ffmpeg_ok = ffmpeg_ok
        self._js_runtime = js_runtime
        self._on_fix_setup = on_fix_setup
        self._queue = DownloadQueue()
        self._worker: Optional[QueueWorker] = None
        self._user_stopped = False
        self._run_ids: set[int] = set()       # items processed in the current run
        self._details_open = False
        self._start_requested = False         # Start pressed; begin as soon as playlists are read

        self._build()
        self._bind_keys()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Header + setup chip
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(18, 6))
        ctk.CTkLabel(header, text="📥  Download videos",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        self._chips = ctk.CTkFrame(header, fg_color="transparent")
        self._chips.pack(side="right")
        self._render_chips()

        # Link input
        input_row = ctk.CTkFrame(self, fg_color="transparent")
        input_row.pack(fill="x", padx=24)
        left = ctk.CTkFrame(input_row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        label_row = ctk.CTkFrame(left, fg_color="transparent")
        label_row.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(label_row, text="Paste links (one per line):", anchor="w",
                     font=ctk.CTkFont(size=13)).pack(side="left")
        ctk.CTkLabel(label_row, text="Ctrl+V anywhere adds links  ·  Ctrl+Enter starts",
                     font=theme.font(12), text_color=theme.MUTED).pack(side="right")
        self._url_box = ctk.CTkTextbox(left, height=72, font=ctk.CTkFont(size=13))
        self._url_box.pack(fill="x")
        self._url_box.bind("<FocusOut>", lambda _: self._validate_urls_live())
        self._url_box.bind("<<Paste>>", lambda _: self.after(50, self._validate_urls_live))
        self._validation_label = ctk.CTkLabel(left, text="", anchor="w", justify="left",
                                              font=ctk.CTkFont(size=12), text_color=theme.MUTED)
        self._validation_label.pack(fill="x", pady=(2, 0))

        ctk.CTkButton(
            input_row, text="+ Add to list", width=120, height=34,
            fg_color="transparent", text_color=theme.TEXT, border_width=1, command=self._add_from_box,
        ).pack(side="left", padx=(10, 0), anchor="n", pady=(26, 0))

        # What to download + quality
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x", padx=24, pady=(6, 4))
        ctk.CTkLabel(controls, text="Download:", font=ctk.CTkFont(size=13)).pack(side="left")
        self._mode_var = ctk.StringVar()
        self._type_menu = ctk.CTkOptionMenu(controls, variable=self._mode_var, width=150,
                                            command=lambda _: self._on_type_changed())
        self._type_menu.pack(side="left", padx=(8, 20))
        ctk.CTkLabel(controls, text="Quality:", font=ctk.CTkFont(size=13)).pack(side="left")
        self._quality_var = ctk.StringVar()
        self._quality_menu = ctk.CTkOptionMenu(controls, variable=self._quality_var, width=120,
                                               command=lambda _: self._on_quality_changed())
        self._quality_menu.pack(side="left", padx=(8, 12))
        self._quality_hint = ctk.CTkLabel(controls, text="", font=ctk.CTkFont(size=12),
                                          text_color=theme.MUTED)
        self._quality_hint.pack(side="left")
        self._refresh_type_menu()
        self._set_type_from_settings()

        # Output folder (remembered)
        out_row = ctk.CTkFrame(self, fg_color="transparent")
        out_row.pack(fill="x", padx=24, pady=(4, 8))
        ctk.CTkLabel(out_row, text="Save to:", font=ctk.CTkFont(size=13)).pack(side="left")
        self._outdir_var = ctk.StringVar(value=self._settings.get("output_dir"))
        ctk.CTkEntry(out_row, textvariable=self._outdir_var,
                     font=ctk.CTkFont(size=12)).pack(side="left", fill="x", expand=True, padx=8)
        ctk.CTkButton(out_row, text="Browse", width=70,
                      command=self._browse_folder).pack(side="left")
        self._outdir_var.trace_add("write", lambda *_: self._save_output_dir())

        # Actions + overall progress
        act = ctk.CTkFrame(self, fg_color="transparent")
        act.pack(fill="x", padx=24, pady=(2, 4))
        self._download_btn = ctk.CTkButton(
            act, text="▶  Start download", width=180, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=theme.GO_BTN, hover_color=theme.GO_HOVER, command=self._start_download,
        )
        self._download_btn.pack(side="left", padx=(0, 10))
        self._cancel_btn = ctk.CTkButton(
            act, text="■  Stop", width=100, height=40, font=ctk.CTkFont(size=13),
            fg_color=theme.STOP_BTN, hover_color=theme.STOP_HOVER, command=self._cancel_download,
            state="disabled",
        )
        self._cancel_btn.pack(side="left", padx=(0, 14))
        self._overall_label = ctk.CTkLabel(act, text="", font=ctk.CTkFont(size=13),
                                           anchor="w")
        self._overall_label.pack(side="left", fill="x", expand=True)
        self._clear_btn = ctk.CTkButton(act, text="Clear finished", width=110, height=30,
                                        fg_color="transparent", text_color=theme.TEXT, border_width=1,
                                        command=self._clear_finished)
        self._clear_btn.pack(side="right")
        self._retry_all_btn = ctk.CTkButton(act, text="↺ Retry failed", width=110, height=30,
                                            fg_color="transparent", text_color=theme.TEXT, border_width=1,
                                            command=self._retry_all_failed)
        self._retry_all_btn.pack(side="right", padx=6)

        self._overall_bar = ctk.CTkProgressBar(self, height=8)
        self._overall_bar.set(0)
        self._overall_bar.pack(fill="x", padx=24, pady=(2, 6))

        # Finish banner (hidden until a run completes)
        self._banner = ctk.CTkFrame(self, corner_radius=8, fg_color=theme.BANNER_OK)
        self._banner_label = ctk.CTkLabel(self._banner, text="", anchor="w",
                                          font=ctk.CTkFont(size=13, weight="bold"))
        self._banner_label.pack(side="left", padx=14, pady=8, fill="x", expand=True)
        ctk.CTkButton(self._banner, text="✕", width=30, height=28, fg_color="transparent", text_color=theme.TEXT,
                      command=self._hide_banner).pack(side="right", padx=(0, 8))
        self._banner_open = ctk.CTkButton(self._banner, text="Open folder", width=110, height=30,
                                          command=self._open_output_folder)
        self._banner_open.pack(side="right", padx=4)
        self._banner_play = ctk.CTkButton(self._banner, text="▶ Play", width=80, height=30,
                                          fg_color="transparent", text_color=theme.TEXT, border_width=1)
        self._banner_anchor = ctk.CTkFrame(self, height=0, fg_color="transparent")
        self._banner_anchor.pack(fill="x", padx=24)

        # Download list
        self._list = QueueList(self, on_action=self._on_row_action, height=220)
        self._list.pack(fill="both", expand=True, padx=24, pady=(4, 6))

        # Details (technical log), collapsed by default
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(0, 4))
        self._details_btn = ctk.CTkButton(
            footer, text="▸ Show details", width=120, height=26, anchor="w",
            fg_color="transparent", text_color=theme.MUTED,
            hover_color=theme.HOVER, command=self._toggle_details,
        )
        self._details_btn.pack(side="left")
        self._clear_log_btn = ctk.CTkButton(footer, text="Clear log", width=80, height=26,
                                            fg_color="transparent", text_color=theme.TEXT, border_width=1,
                                            command=self._clear_log)
        self._log_box = ctk.CTkTextbox(self, height=140, state="disabled",
                                       font=ctk.CTkFont(family="Consolas", size=12))

        self._apply_ffmpeg_state()
        self._refresh_overall()

    def _bind_keys(self) -> None:
        top = self.winfo_toplevel()
        top.bind("<Control-Return>", lambda _: self._start_download(), add="+")
        self._url_box.bind("<Control-Return>", lambda _: (self._start_download(), "break")[1])
        for seq in ("<Control-v>", "<Control-V>"):
            top.bind(seq, self._paste_anywhere, add="+")
        for seq in ("<Control-l>", "<Control-L>"):
            top.bind(seq, lambda _: (self._url_box.focus_set(), "break")[1], add="+")

    def _paste_anywhere(self, _event=None):
        """Ctrl+V while not typing in a text field: add clipboard links to the list."""
        if not self.winfo_ismapped():
            return None                       # another tab is showing
        focus = self.focus_get()
        if focus is not None and focus.winfo_class() in ("Entry", "Text", "TEntry"):
            return None                       # normal paste into that field
        try:
            text = self.clipboard_get()
        except Exception:
            return None
        if not text.strip():
            return None
        self._url_box.delete("1.0", "end")
        self._url_box.insert("1.0", text.strip())
        added = self._add_from_box()
        self._overall_label.configure(
            text=f"Added {added} link(s) from the clipboard." if added
            else "The clipboard doesn't contain a web link.",
            text_color=theme.TEXT if added else _WARN)
        return "break"

    # ── Setup chips ───────────────────────────────────────────────────────────

    def _render_chips(self) -> None:
        for child in self._chips.winfo_children():
            child.destroy()
        js_ok = bool(self._js_runtime and self._js_runtime.available)
        if not self._ffmpeg_ok:
            self._make_fix_chip("⚠ FFmpeg missing – Fix", _BAD).pack(side="right")
        elif not js_ok:
            self._make_fix_chip("⚠ Setup incomplete – Fix", _WARN).pack(side="right")
        else:
            ctk.CTkLabel(self._chips, text="✓ Ready", text_color=_OK,
                         font=ctk.CTkFont(size=12)).pack(side="right")

    def _make_fix_chip(self, text: str, color: str) -> ctk.CTkButton:
        return ctk.CTkButton(
            self._chips, text=text, command=self._fix_setup,
            height=28, fg_color="transparent", border_width=1,
            border_color=color, text_color=color,
            hover_color=theme.HOVER,
            font=ctk.CTkFont(size=12, weight="bold"),
        )

    def _fix_setup(self) -> None:
        if self._on_fix_setup:
            self._on_fix_setup()

    def update_tools(self, ffmpeg_ok: bool, js_runtime) -> None:
        """Called after the setup dialog installs/finds tools — no restart needed."""
        self._ffmpeg_ok = ffmpeg_ok
        self._js_runtime = js_runtime
        self._render_chips()
        self._apply_ffmpeg_state()

    def _apply_ffmpeg_state(self) -> None:
        running = self._is_running()
        self._download_btn.configure(
            state="normal" if (self._ffmpeg_ok and not running) else "disabled")
        if not self._ffmpeg_ok:
            self._overall_label.configure(
                text="FFmpeg is needed before you can download — click “Fix” above.",
                text_color=_BAD)
        elif self._overall_label.cget("text").startswith("FFmpeg is needed"):
            self._overall_label.configure(text="", text_color=theme.TEXT)

    # ── Type / quality pickers ────────────────────────────────────────────────

    def _video_label(self) -> str:
        fmt = str(self._settings.get("default_video_format") or "mp4").upper()
        return f"Video ({fmt})"

    def _is_audio(self) -> bool:
        return self._mode_var.get() == _AUDIO_LABEL

    def _refresh_type_menu(self) -> None:
        was_audio = self._mode_var.get() == _AUDIO_LABEL
        self._type_menu.configure(values=[self._video_label(), _AUDIO_LABEL])
        if self._mode_var.get():
            self._mode_var.set(_AUDIO_LABEL if was_audio else self._video_label())

    def _set_type_from_settings(self) -> None:
        audio = self._settings.get("default_mode") == _AUDIO_LABEL
        self._mode_var.set(_AUDIO_LABEL if audio else self._video_label())
        self._refresh_quality_menu()

    def _refresh_quality_menu(self) -> None:
        if self._is_audio():
            values = _AUDIO_QUALITIES
            current = f"{self._settings.get('audio_quality')} kbps"
        else:
            values = _VIDEO_QUALITIES
            current = str(self._settings.get("video_quality") or "1080p")
        if current not in values:
            current = values[1]
        self._quality_menu.configure(values=values)
        self._quality_var.set(current)
        self._quality_hint.configure(text=_QUALITY_HINTS.get(current, ""))

    def _on_type_changed(self) -> None:
        self._settings.set("default_mode", _AUDIO_LABEL if self._is_audio() else "Video")
        self._refresh_quality_menu()

    def _on_quality_changed(self) -> None:
        value = self._quality_var.get()
        if self._is_audio():
            self._settings.set("audio_quality", value.split()[0])
        else:
            self._settings.set("video_quality", value)
        self._quality_hint.configure(text=_QUALITY_HINTS.get(value, ""))

    def _save_output_dir(self) -> None:
        value = self._outdir_var.get().strip()
        if value and value != self._settings.get("output_dir"):
            self._settings.set("output_dir", value)

    def _browse_folder(self) -> None:
        import tkinter.filedialog as fd
        folder = fd.askdirectory(title="Choose where to save downloads")
        if folder:
            self._outdir_var.set(folder)

    # ── URL validation ────────────────────────────────────────────────────────

    def _validate_urls_live(self) -> None:
        raw = self._url_box.get("1.0", "end").strip()
        if not raw:
            self._validation_label.configure(text="")
            return
        valid, invalid = validate_urls(raw)
        parts: list[str] = []
        if valid:
            parts.append(f"✓ {len(valid)} link(s) ready to add")
        if invalid:
            parts.append(f"✗ {len(invalid)} line(s) aren't web links and will be skipped")
        self._validation_label.configure(
            text="   ".join(parts), text_color=_BAD if invalid and not valid else theme.MUTED)

    # ── Adding items ──────────────────────────────────────────────────────────

    def _add_from_box(self) -> int:
        """Move valid links from the text box into the list. Returns how many."""
        raw = self._url_box.get("1.0", "end").strip()
        if not raw:
            return 0
        valid, invalid = validate_urls(raw)
        for r in invalid:
            self._log_ui(f"⚠ Skipped (not a web link): {r.url}")
        added = 0
        self._remembered_choice: Optional[str] = None   # "same for the rest of this paste"
        mixed = [r.url for r in valid if is_video_in_playlist(r.url)]
        for r in valid:
            url, no_playlist = r.url, False
            if is_video_in_playlist(url):
                mixed.remove(url)
                choice = self._remembered_choice or self._ask_playlist_choice(url, len(mixed))
                if choice is None:
                    self._log_ui(f"⏭ Skipped: {url}")
                    continue
                if choice == "playlist":
                    url = playlist_url_for(url)
                else:
                    no_playlist = True
            request = self._build_request(url)
            if request is None:
                self._log_ui(f"⏭ Skipped (no format chosen): {url}")
                continue
            if no_playlist:
                request.no_playlist = True
            if looks_like_playlist(url):
                self._add_playlist(request)
            else:
                item = self._queue.add(request)
                self._fetch_preview(item)
            added += 1
        # keep only the lines that weren't added (invalid ones) so the user can fix them
        self._url_box.delete("1.0", "end")
        if invalid:
            self._url_box.insert("1.0", "\n".join(r.url for r in invalid))
        self._validate_urls_live()
        self._sync_list()
        return added

    def _ask_playlist_choice(self, url: str, remaining: int) -> Optional[str]:
        dlg = PlaylistChoiceDialog(self.winfo_toplevel(), url, remaining)
        self.wait_window(dlg)
        if dlg.apply_to_all and dlg.choice:
            self._remembered_choice = dlg.choice
        return dlg.choice

    # ── Playlists ─────────────────────────────────────────────────────────────

    _CONFIRM_ABOVE = 150   # ask before adding very long playlists / channels

    def _add_playlist(self, request: DownloadRequest) -> None:
        """Add a placeholder row, then list the playlist's videos in the
        background and replace the placeholder with one row per video."""
        item = self._queue.add(request, title="Playlist", status=CHECKING)
        self._log_ui(f"… Reading playlist: {request.url}")

        def work() -> None:
            info = probe_playlist(request.url, proxy=request.proxy_url)
            try:
                self.after(0, self._apply_playlist, item.id, request, info)
            except Exception:
                pass   # window closed

        threading.Thread(target=work, daemon=True, name="PlaylistProbe").start()

    def _apply_playlist(self, item_id: int, base: DownloadRequest,
                        info: Optional[PlaylistInfo]) -> None:
        if self._queue.get(item_id) is None:
            return                                      # removed meanwhile
        if info is None:
            # Couldn't list it (unknown site, private, network): download the
            # link as one item — the row still shows "Video n of m" progress.
            self._queue.mark_ready(item_id)
            self._log_ui(f"⚠ Couldn't list the videos in {base.url}; downloading it as one item.")
        else:
            count = len(info.entries)
            if count > self._CONFIRM_ABOVE:
                from tkinter import messagebox
                if not messagebox.askyesno(
                    "Large playlist",
                    f"“{info.title}” has {count} videos.\n\nAdd all of them to the list?",
                    parent=self.winfo_toplevel()):
                    self._queue.remove(item_id)
                    self._log_ui(f"⏭ Not added: {info.title} ({count} videos)")
                    self._sync_list()
                    self._after_playlist_read()
                    return
            specs = [{
                "request": dataclasses.replace(base, url=e.url, no_playlist=True),
                "title": e.title,
                "duration": e.duration,
                "group": info.title,
                "group_pos": (n, count),
            } for n, e in enumerate(info.entries, start=1)]
            for new in self._queue.replace(item_id, specs):
                self._fetch_preview(new, want_title=not new.title)
            skipped = f" ({info.skipped} private/deleted skipped)" if info.skipped else ""
            self._log_ui(f"✓ Added {count} videos from “{info.title}”{skipped}")
        self._sync_list()
        self._after_playlist_read()

    def _after_playlist_read(self) -> None:
        """If Start was pressed while playlists were being read, begin now."""
        if self._start_requested and not self._queue.has_pending_checks():
            if self._queue.has_work():
                self._ensure_worker()
            elif not self._is_running():
                self._start_requested = False
                self._overall_label.configure(text="Nothing to download.", text_color=_WARN)

    def _build_request(self, url: str) -> Optional[DownloadRequest]:
        output_dir = self._outdir_var.get().strip() or _DEFAULT_OUTPUT_DIR
        if self._is_audio():
            return self._make_request(url, "audio", "mp3", output_dir)
        fmt = self._settings.get("default_video_format")
        if self._settings.get("ask_format_per_video"):
            fmt = self._ask_format(url)
            if fmt is None:
                return None
        return self._make_request(url, "video", fmt, output_dir)

    def _make_request(self, url: str, mode: str, fmt: str, output_dir: str) -> DownloadRequest:
        return DownloadRequest(
            url=url,
            mode=mode,
            video_format=fmt,
            video_quality=str(self._settings.get("video_quality") or "best").lower(),
            output_dir=output_dir,
            audio_quality=self._settings.get("audio_quality"),
            max_retries=int(self._settings.get("max_retries")),
            rate_limit_kb=int(self._settings.get("rate_limit_kb")),
            concurrent_fragments=int(self._settings.get("concurrent_fragments")),
            embed_thumbnail=bool(self._settings.get("embed_thumbnail")),
            write_subtitles=bool(self._settings.get("write_subtitles")),
            subtitle_lang=self._settings.get("subtitle_lang"),
            skip_existing=bool(self._settings.get("skip_existing")),
            proxy_url=self._settings.get("proxy_url"),
            ffmpeg_location=self._settings.get("_ffmpeg_location") or "",
            js_runtime_name=self._settings.get("_js_runtime_name") or "",
            js_runtime_path=self._settings.get("_js_runtime_path") or "",
        )

    def _ask_format(self, url: str) -> Optional[str]:
        dlg = FormatDialog(self.winfo_toplevel(), url)
        self.wait_window(dlg)
        return dlg.chosen_format

    def _fetch_preview(self, item: QueueItem, want_title: bool = True) -> None:
        def done(title: str, pil_image) -> None:
            try:
                self.after(0, self._apply_preview, item.id, title, pil_image)
            except Exception:
                pass   # window closed
        fetch_preview_async(item.request.url, done, want_title=want_title)

    def _apply_preview(self, item_id: int, title: str, pil_image) -> None:
        item = self._queue.get(item_id)
        if not item:
            return
        if title and not item.title:
            item.title = title
        image = to_ctk_image(pil_image)
        if image is not None:
            self._list.set_thumbnail(item_id, image)
        self._list.update_item(item)

    # ── Start / stop ──────────────────────────────────────────────────────────

    def _is_running(self) -> bool:
        return bool(self._worker and self._worker.is_alive())

    def _start_download(self) -> None:
        if not self._ffmpeg_ok:
            self._fix_setup()
            return
        self._add_from_box()
        if not self._queue.has_work() and self._queue.has_pending_checks():
            self._start_requested = True
            self._overall_label.configure(
                text="Reading the playlist… downloading starts automatically.",
                text_color=_INFO)
            return
        if not self._queue.has_work():
            self._overall_label.configure(
                text="Paste a link above first." if not self._queue.items()
                else "Nothing waiting — everything in the list is finished.",
                text_color=_WARN)
            return
        self._start_requested = True
        self._ensure_worker()

    def _ensure_worker(self) -> None:
        if self._is_running() or not self._queue.has_work() or not self._ffmpeg_ok:
            return
        self._hide_banner()
        self._user_stopped = False
        self._run_ids = set()
        js_ok = self._js_runtime and self._js_runtime.available
        self._log_ui(
            f"▶ Starting {self._queue.stats()[READY]} download(s)… "
            + (f"[JS: {self._js_runtime.name} {self._js_runtime.version}]" if js_ok
               else "[⚠ Setup incomplete: no JavaScript runtime — some videos may fail]")
        )
        self._worker = QueueWorker(
            self._queue,
            on_item_start=lambda item: self.after(0, self._apply_item_start, item),
            on_progress=lambda item, data: self.after(0, self._apply_progress, item, data),
            on_item_done=lambda item, res: self.after(0, self._apply_item_done, item, res),
            on_log=lambda msg: self.after(0, self._log_ui, msg),
            on_all_done=lambda stopped: self.after(0, self._apply_all_done, stopped),
        )
        self._set_running(True)
        self._worker.start()

    def _cancel_download(self) -> None:
        if self._worker:
            self._user_stopped = True
            self._start_requested = False
            self._worker.stop()
            self._log_ui("■ Stopping…")
            self._overall_label.configure(text="Stopping…", text_color=_WARN)

    def _set_running(self, running: bool) -> None:
        self._cancel_btn.configure(state="normal" if running else "disabled")
        self._apply_ffmpeg_state()

    # ── Row actions ───────────────────────────────────────────────────────────

    def _on_row_action(self, action: str, item_id: int) -> None:
        item = self._queue.get(item_id)
        if not item:
            return
        if action == "remove":
            self._queue.remove(item_id)
        elif action == "cancel":
            self._queue.cancel(item_id)
        elif action == "retry":
            if self._queue.retry(item_id):
                self._ensure_worker()
        elif action == "play" and item.filepaths:
            _open_path(item.filepaths[0])
        elif action == "open":
            _reveal_in_folder(item.filepaths[0] if item.filepaths else item.request.output_dir)
        elif action == "details":
            self._show_error_details(item)
        self._sync_list()

    def _retry_all_failed(self) -> None:
        if self._queue.retry_failed():
            self._sync_list()
            self._ensure_worker()

    def _clear_finished(self) -> None:
        self._queue.clear_finished()
        self._hide_banner()
        self._sync_list()

    def _show_error_details(self, item: QueueItem) -> None:
        dlg = ctk.CTkToplevel(self.winfo_toplevel())
        dlg.title("What went wrong")
        dlg.geometry("560x340")
        dlg.transient(self.winfo_toplevel())
        ctk.CTkLabel(dlg, text=item.error or "The download failed.", anchor="w",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     wraplength=510, justify="left").pack(fill="x", padx=20, pady=(18, 2))
        ctk.CTkLabel(dlg, text=item.hint, anchor="w", text_color=theme.MUTED, wraplength=510,
                     justify="left", font=ctk.CTkFont(size=13)).pack(fill="x", padx=20)
        ctk.CTkLabel(dlg, text="Technical details:", anchor="w",
                     font=ctk.CTkFont(size=12)).pack(fill="x", padx=20, pady=(12, 2))
        box = ctk.CTkTextbox(dlg, font=ctk.CTkFont(family="Consolas", size=12))
        box.insert("1.0", f"{item.request.url}\n\n{item.error_detail}")
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=20)
        row = ctk.CTkFrame(dlg, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=12)

        def copy() -> None:
            dlg.clipboard_clear()
            dlg.clipboard_append(f"{item.request.url}\n{item.error_detail}")
        ctk.CTkButton(row, text="Copy details", width=110, fg_color="transparent", text_color=theme.TEXT,
                      border_width=1, command=copy).pack(side="left")
        ctk.CTkButton(row, text="Close", width=90, command=dlg.destroy).pack(side="right")
        dlg.bind("<Escape>", lambda _: dlg.destroy())
        dlg.after(50, dlg.lift)
        dlg.after(80, dlg.focus_force)

    # ── Worker callbacks (main thread) ────────────────────────────────────────

    def _apply_item_start(self, item: QueueItem) -> None:
        self._run_ids.add(item.id)
        self._sync_list()

    def _apply_progress(self, item: QueueItem, data: ProgressData) -> None:
        self._list.update_item(item)
        self._refresh_overall()

    def _apply_item_done(self, item: QueueItem, result: DownloadResult) -> None:
        if result.success:
            self._log_ui(f"✓ Done: {item.display_title}")
        elif result.cancelled:
            self._log_ui(f"■ Stopped: {item.display_title}")
        else:
            self._log_ui(f"✗ Failed: {item.request.url}\n   {result.error_message}")
        if not result.cancelled:
            r = item.request
            self._history.add_entry(
                title=item.display_title,
                url=r.url,
                fmt=(f"{r.video_format} {r.video_quality}" if r.mode == "video"
                     else f"mp3 {r.audio_quality}k"),
                status="success" if result.success else "failed",
                filepath=result.filepath,
            )
        self._sync_list()

    def _apply_all_done(self, stopped: bool) -> None:
        self._set_running(False)
        if not stopped and self._queue.has_work():
            # links were added while the last item was finishing
            self._ensure_worker()
            return
        if not stopped and self._queue.has_pending_checks():
            # a playlist is still being read; the worker restarts once it is
            self._sync_list()
            self._overall_label.configure(text="Reading the playlist…", text_color=_INFO)
            return
        self._start_requested = False
        self._sync_list()
        items = [i for i in self._queue.items() if i.id in self._run_ids]
        done = [i for i in items if i.status == COMPLETED]
        failed = [i for i in items if i.status == FAILED]
        waiting = self._queue.stats()[READY]
        if stopped:
            msg = "Stopped." + (f" {waiting} still waiting — click Start to continue."
                                if waiting else "")
            self._overall_label.configure(text=msg, text_color=_WARN)
            self._log_ui("■ Stopped by user.")
            return
        self._log_ui(f"━━ Finished: {len(done)} downloaded, {len(failed)} failed ━━")
        self._show_banner(done, failed)
        self._notify_finished()
        if self._settings.get("auto_open_folder") and done:
            self._open_output_folder()

    # ── Overall progress + banner ─────────────────────────────────────────────

    def _sync_list(self) -> None:
        self._list.sync(self._queue.items())
        self._refresh_overall()

    def _refresh_overall(self) -> None:
        stats = self._queue.stats()
        failed_or_stopped = stats[FAILED] + stats[CANCELLED]
        self._retry_all_btn.configure(state="normal" if failed_or_stopped else "disabled")
        self._clear_btn.configure(
            state="normal" if stats[COMPLETED] + failed_or_stopped else "disabled")
        if not self._ffmpeg_ok:
            return
        items = [i for i in self._queue.items() if i.id in self._run_ids or i.status == READY]
        if not self._is_running() or not items:
            if not self._is_running():
                self._overall_bar.set(0)
            return
        total = len(items)
        finished = sum(1 for i in items if i.status in (COMPLETED, FAILED, CANCELLED))
        current = next((i for i in items if i.status == DOWNLOADING), None)
        frac = (finished + (current.percent / 100 if current else 0)) / total
        self._overall_bar.set(frac)
        text = f"{finished} of {total} done"
        eta = self._estimate_remaining(items, current)
        if eta:
            text += f"  ·  {eta}"
        self._overall_label.configure(text=text, text_color=theme.TEXT)

    @staticmethod
    def _estimate_remaining(items: list[QueueItem], current: Optional[QueueItem]) -> str:
        durations = [i.finished_at - i.started_at for i in items
                     if i.status == COMPLETED and i.finished_at > i.started_at]
        waiting = sum(1 for i in items if i.status == READY)
        current_left = current.eta_seconds if current and current.eta_seconds else None
        if durations:
            avg = sum(durations) / len(durations)
            seconds = avg * waiting + (current_left if current_left is not None
                                       else avg * (1 - (current.percent / 100 if current else 1)))
        elif waiting == 0 and current_left is not None:
            seconds = current_left
        else:
            return ""   # not enough information yet
        if seconds < 60:
            return "less than a minute left"
        minutes = round(seconds / 60)
        return f"about {minutes} min left" if minutes < 90 else f"about {minutes // 60} h left"

    def _show_banner(self, done: list[QueueItem], failed: list[QueueItem]) -> None:
        if failed and done:
            text = f"✓ Finished — {len(done)} downloaded, {len(failed)} failed (see the list)."
            color = theme.BANNER_WARN
        elif failed:
            text = f"✗ {len(failed)} download(s) failed — see the list for what to do."
            color = theme.BANNER_BAD
        else:
            text = f"✓ All done — {len(done)} file(s) saved."
            color = theme.BANNER_OK
        self._banner.configure(fg_color=color)
        self._banner_label.configure(text=text)
        last = next((i for i in reversed(done) if i.filepaths), None)
        if last:
            self._banner_play.configure(command=lambda p=last.filepaths[0]: _open_path(p))
            self._banner_play.pack(side="right", padx=4, before=self._banner_open)
        else:
            self._banner_play.pack_forget()
        self._overall_bar.set(1 if done else 0)
        self._overall_label.configure(text="", text_color=theme.TEXT)
        self._banner.pack(fill="x", padx=24, pady=(0, 4), after=self._banner_anchor)

    def _hide_banner(self) -> None:
        self._banner.pack_forget()

    def _notify_finished(self) -> None:
        """Sound + flash the taskbar button if the window isn't in front."""
        top = self.winfo_toplevel()
        try:
            top.bell()
            if sys.platform == "win32":
                # TIMERNOFG: flashes only while the window is in the background
                import ctypes
                from ctypes import wintypes

                class FLASHWINFO(ctypes.Structure):
                    _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND),
                                ("dwFlags", wintypes.DWORD), ("uCount", wintypes.UINT),
                                ("dwTimeout", wintypes.DWORD)]
                hwnd = ctypes.windll.user32.GetParent(top.winfo_id())
                # FLASHW_ALL | FLASHW_TIMERNOFG: flash until the window is focused
                info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0x3 | 0xC, 0, 0)
                ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
        except Exception as exc:
            _log.debug("Finish notification failed: %s", exc)

    def _open_output_folder(self) -> None:
        folder = self._outdir_var.get().strip() or _DEFAULT_OUTPUT_DIR
        os.makedirs(folder, exist_ok=True)
        _open_path(folder)

    # ── Details log ───────────────────────────────────────────────────────────

    def _toggle_details(self) -> None:
        self._details_open = not self._details_open
        if self._details_open:
            self._details_btn.configure(text="▾ Hide details")
            self._clear_log_btn.pack(side="right")
            self._log_box.pack(fill="x", padx=24, pady=(0, 14))
        else:
            self._details_btn.configure(text="▸ Show details")
            self._clear_log_btn.pack_forget()
            self._log_box.pack_forget()

    def _clear_log(self) -> None:
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _log_ui(self, msg: str) -> None:
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        # keep the log from growing forever
        lines = int(self._log_box.index("end-1c").split(".")[0])
        if lines > 2000:
            self._log_box.delete("1.0", f"{lines - 2000}.0")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")
        _log.info(msg)

    # ── Settings sync ─────────────────────────────────────────────────────────

    def on_settings_changed(self, key: str, value) -> None:
        if key in ("output_dir", "__reset__"):
            if self._outdir_var.get() != self._settings.get("output_dir"):
                self._outdir_var.set(str(self._settings.get("output_dir")))
        if key in ("default_video_format", "__reset__"):
            self._refresh_type_menu()
        if key in ("default_mode", "video_quality", "audio_quality", "__reset__"):
            self._set_type_from_settings()


# ── Shell helpers ─────────────────────────────────────────────────────────────

def _open_path(path: str) -> None:
    """Open a file with its default app (play) or a folder in the file manager."""
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606 - local file chosen by the app
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:
        _log.error("Could not open %s: %s", path, exc)


def _reveal_in_folder(path: str) -> None:
    """Open the containing folder with the file selected, where supported."""
    if sys.platform == "win32" and os.path.isfile(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        _open_path(path if os.path.isdir(path) else os.path.dirname(path))
