"""
UI Tab: Downloader — URL input, mode selector, progress display.
"""
from __future__ import annotations

from typing import Optional, Callable

import customtkinter as ctk

from engine.downloader import (
    DownloadRequest,
    DownloadResult,
    DownloadWorker,
    ProgressData,
    _DEFAULT_OUTPUT_DIR,
)
from utils.history_manager import HistoryManager
from utils.settings_manager import SettingsManager
from utils.url_validator import validate_urls
from utils.thumbnail_fetcher import fetch_thumbnail_async
from utils.logger import AppLogger
from ui.dialogs import FormatDialog

_log = AppLogger.get_logger(__name__)


class DownloaderTab(ctk.CTkFrame):
    """Main download interface tab."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        history_manager: HistoryManager,
        settings: SettingsManager,
        ffmpeg_ok: bool,
        js_runtime=None,
        on_queue_update: Optional[Callable] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._history = history_manager
        self._settings = settings
        self._ffmpeg_ok = ffmpeg_ok
        self._js_runtime = js_runtime
        self._on_queue_update = on_queue_update
        self._worker: Optional[DownloadWorker] = None
        self._is_downloading = False
        self._queue_items: list[dict] = []
        self._completed_results: list[DownloadResult] = []
        self._conv_worker = None
        self._is_converting = False

        self._build()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 8))

        ctk.CTkLabel(
            header,
            text="📥  Download Videos",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(side="left")

        # Status chips (FFmpeg + JS runtime)
        chips = ctk.CTkFrame(header, fg_color="transparent")
        chips.pack(side="right")

        if not self._ffmpeg_ok:
            ctk.CTkLabel(
                chips,
                text="⚠ FFmpeg missing",
                text_color="#FF6B6B",
                font=ctk.CTkFont(size=12),
            ).pack(side="right", padx=(8, 0))

        js_ok = self._js_runtime and self._js_runtime.available
        if js_ok:
            rt = self._js_runtime
            ctk.CTkLabel(
                chips,
                text=f"✓ {rt.name} v{rt.version}",
                text_color="#4CAF50",
                font=ctk.CTkFont(size=11),
            ).pack(side="right", padx=(0, 12))
        else:
            ctk.CTkLabel(
                chips,
                text="⚠ No JS runtime — some videos may fail",
                text_color="#DCDCAA",
                font=ctk.CTkFont(size=11),
            ).pack(side="right", padx=(0, 12))

        # ── URL input + thumbnail ─────────────────────────────────────────────
        main_row = ctk.CTkFrame(self, fg_color="transparent")
        main_row.pack(fill="x", padx=24, pady=(0, 8))

        left = ctk.CTkFrame(main_row, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            left,
            text="Paste URLs (one per line):",
            font=ctk.CTkFont(size=13),
            anchor="w",
        ).pack(fill="x", pady=(0, 2))

        self._url_box = ctk.CTkTextbox(left, height=120, font=ctk.CTkFont(size=12))
        self._url_box.pack(fill="x")
        self._url_box.bind("<FocusOut>", lambda _: self._validate_urls_live())

        self._validation_label = ctk.CTkLabel(
            left, text="", font=ctk.CTkFont(size=11), anchor="w", text_color="gray"
        )
        self._validation_label.pack(fill="x", pady=(2, 0))

        thumb_panel = ctk.CTkFrame(
            main_row, width=180, fg_color=("gray90", "#1E1E1E"), corner_radius=8
        )
        thumb_panel.pack(side="right", fill="y", padx=(12, 0))
        thumb_panel.pack_propagate(False)
        self._thumb_label = ctk.CTkLabel(
            thumb_panel, text="Thumbnail\npreview",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        self._thumb_label.pack(expand=True)

        # ── Mode + output dir ─────────────────────────────────────────────────
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x", padx=24, pady=(8, 8))

        ctk.CTkLabel(controls, text="Mode:", font=ctk.CTkFont(size=13)).pack(side="left")
        self._mode_var = ctk.StringVar(value=self._settings.get("default_mode"))
        ctk.CTkSegmentedButton(
            controls, values=["Video", "Audio (MP3)"],
            variable=self._mode_var, width=200,
        ).pack(side="left", padx=(8, 24))

        ctk.CTkLabel(controls, text="Output folder:", font=ctk.CTkFont(size=13)).pack(side="left")
        self._outdir_var = ctk.StringVar(value=self._settings.get("output_dir"))
        ctk.CTkEntry(
            controls, textvariable=self._outdir_var,
            width=260, font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(8, 8))
        ctk.CTkButton(
            controls, text="Browse", width=70, command=self._browse_folder
        ).pack(side="left")

        # ── Post-download conversion panel ────────────────────────────────────
        self._build_conversion_panel()

        # ── Action buttons ────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(0, 12))

        self._download_btn = ctk.CTkButton(
            btn_row,
            text="▶  Start Download",
            width=180, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#1A7F3C", hover_color="#145C2C",
            command=self._start_download,
            state="normal" if self._ffmpeg_ok else "disabled",
        )
        self._download_btn.pack(side="left", padx=(0, 12))

        self._cancel_btn = ctk.CTkButton(
            btn_row, text="⏹  Cancel",
            width=120, height=40,
            font=ctk.CTkFont(size=13),
            fg_color="#7F1A1A", hover_color="#5C1414",
            command=self._cancel_download,
            state="disabled",
        )
        self._cancel_btn.pack(side="left", padx=(0, 16))

        self._current_item_label = ctk.CTkLabel(
            btn_row, text="", font=ctk.CTkFont(size=11), text_color="gray",
        )
        self._current_item_label.pack(side="left")

        # ── Progress ──────────────────────────────────────────────────────────
        prog_frame = ctk.CTkFrame(self)
        prog_frame.pack(fill="x", padx=24, pady=(0, 8))

        stats_row = ctk.CTkFrame(prog_frame, fg_color="transparent")
        stats_row.pack(fill="x", padx=16, pady=(12, 4))

        self._pct_label = ctk.CTkLabel(
            stats_row, text="0%",
            font=ctk.CTkFont(size=13, weight="bold"), width=45,
        )
        self._pct_label.pack(side="left")

        self._speed_label = ctk.CTkLabel(
            stats_row, text="Speed: —",
            font=ctk.CTkFont(size=12), text_color="gray",
        )
        self._speed_label.pack(side="left", padx=16)

        self._eta_label = ctk.CTkLabel(
            stats_row, text="ETA: —",
            font=ctk.CTkFont(size=12), text_color="gray",
        )
        self._eta_label.pack(side="left")

        self._status_label = ctk.CTkLabel(
            stats_row, text="Idle",
            font=ctk.CTkFont(size=12), text_color="#4EC9B0",
        )
        self._status_label.pack(side="right", padx=8)

        self._progress_bar = ctk.CTkProgressBar(prog_frame, height=10)
        self._progress_bar.pack(fill="x", padx=16, pady=(0, 12))
        self._progress_bar.set(0)

        # ── Log ───────────────────────────────────────────────────────────────
        log_header = ctk.CTkFrame(self, fg_color="transparent")
        log_header.pack(fill="x", padx=24)
        ctk.CTkLabel(
            log_header, text="Activity Log:",
            font=ctk.CTkFont(size=13), anchor="w",
        ).pack(side="left")
        ctk.CTkButton(
            log_header, text="Clear", width=55, height=24,
            fg_color="transparent", border_width=1,
            font=ctk.CTkFont(size=11),
            command=self._clear_log,
        ).pack(side="right")

        self._log_box = ctk.CTkTextbox(
            self, font=ctk.CTkFont(family="Courier", size=11), state="disabled",
        )
        self._log_box.pack(fill="both", expand=True, padx=24, pady=(4, 20))

    def _build_conversion_panel(self) -> None:
        conv_frame = ctk.CTkFrame(
            self, fg_color=("gray92", "#1A1A2E"), corner_radius=8
        )
        conv_frame.pack(fill="x", padx=24, pady=(0, 8))

        header_row = ctk.CTkFrame(conv_frame, fg_color="transparent")
        header_row.pack(fill="x", padx=16, pady=(10, 6))

        ctk.CTkLabel(
            header_row,
            text="🔄  Post-download Conversion  (powered by imageio-ffmpeg)",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")

        self._conv_enabled_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(
            header_row, text="Enable",
            variable=self._conv_enabled_var,
            onvalue=True, offvalue=False, width=80,
            command=self._on_conv_toggle,
        ).pack(side="right")

        self._conv_options_frame = ctk.CTkFrame(conv_frame, fg_color="transparent")
        self._conv_options_frame.pack(fill="x", padx=16, pady=(0, 10))

        ctk.CTkLabel(self._conv_options_frame, text="Format:",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        self._conv_format_var = ctk.StringVar(value="mp3")
        ctk.CTkSegmentedButton(
            self._conv_options_frame,
            values=["mp3", "wav", "mp4", "m4a"],
            variable=self._conv_format_var, width=220,
        ).pack(side="left", padx=(8, 24))

        ctk.CTkLabel(self._conv_options_frame, text="Bitrate:",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        self._conv_bitrate_var = ctk.StringVar(value="192k")
        ctk.CTkSegmentedButton(
            self._conv_options_frame,
            values=["128k", "192k", "256k", "320k"],
            variable=self._conv_bitrate_var, width=220,
        ).pack(side="left", padx=(8, 24))

        self._del_source_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self._conv_options_frame,
            text="Delete source after conversion",
            variable=self._del_source_var,
            font=ctk.CTkFont(size=11),
        ).pack(side="left")

        self._conv_options_frame.pack_forget()

    # ── Conversion toggle ─────────────────────────────────────────────────────

    def _on_conv_toggle(self) -> None:
        if self._conv_enabled_var.get():
            self._conv_options_frame.pack(fill="x", padx=16, pady=(0, 10))
            self._log_ui("🔄 Post-download conversion enabled.")
        else:
            self._conv_options_frame.pack_forget()
            self._log_ui("🔄 Post-download conversion disabled.")

    # ── URL validation ────────────────────────────────────────────────────────

    def _validate_urls_live(self) -> None:
        raw = self._url_box.get("1.0", "end").strip()
        if not raw:
            self._validation_label.configure(text="")
            self._thumb_label.configure(image=None, text="Thumbnail\npreview")
            return

        valid, invalid = validate_urls(raw)
        parts: list[str] = []
        if valid:
            parts.append(f"✅ {len(valid)} valid URL(s)")
        if invalid:
            parts.append(f"❌ {len(invalid)} invalid")
            for r in invalid[:3]:
                parts.append(f"   · {r.url[:60]}  ({r.reason})")
        self._validation_label.configure(text="\n".join(parts))

        if valid:
            first_url = valid[0].url
            if "youtube" in first_url or "youtu.be" in first_url:
                fetch_thumbnail_async(
                    first_url,
                    on_done=lambda img: self.after(0, self._apply_thumbnail, img),
                )

    def _apply_thumbnail(self, img) -> None:
        if img:
            self._thumb_label.configure(image=img, text="")
        else:
            self._thumb_label.configure(image=None, text="No preview")

    # ── Actions ───────────────────────────────────────────────────────────────

    def _browse_folder(self) -> None:
        import tkinter.filedialog as fd
        folder = fd.askdirectory(title="Select output folder")
        if folder:
            self._outdir_var.set(folder)

    def _start_download(self) -> None:
        raw = self._url_box.get("1.0", "end").strip()
        valid_results, invalid_results = validate_urls(raw)

        for r in invalid_results:
            self._log_ui(f"⚠ Skipping invalid URL: {r.url}  ({r.reason})")

        if not valid_results:
            self._log_ui("⚠ No valid URLs to download.")
            return

        urls = [r.url for r in valid_results]
        mode = "video" if self._mode_var.get() == "Video" else "audio"
        output_dir = self._outdir_var.get().strip() or _DEFAULT_OUTPUT_DIR
        ask_per_video = self._settings.get("ask_format_per_video")

        requests: list[DownloadRequest] = []

        if mode == "video":
            default_fmt = self._settings.get("default_video_format")
            for url in urls:
                if ask_per_video:
                    fmt = self._ask_format(url)
                    if fmt is None:
                        self._log_ui(f"⏭ Skipped (no format chosen): {url}")
                        continue
                else:
                    fmt = default_fmt
                requests.append(self._make_request(url, "video", fmt, output_dir))
        else:
            for url in urls:
                requests.append(self._make_request(url, "audio", "mp3", output_dir))

        if not requests:
            self._log_ui("No downloads queued.")
            return

        self._run_requests(requests)

    def retry_failed(self, items: list[dict]) -> None:
        """Re-run the queue items that failed (called from the Batch Queue tab)."""
        if self._is_downloading or self._is_converting:
            self._log_ui("⚠ Wait for the current batch to finish before retrying.")
            return
        requests = [i["request"] for i in items if i.get("request")]
        if not requests:
            return
        self._log_ui(f"↺ Retrying {len(requests)} failed download(s)…")
        self._run_requests(requests)

    def _run_requests(self, requests: list[DownloadRequest]) -> None:
        """Populate the queue and start a DownloadWorker for *requests*."""
        self._queue_items = [
            {
                "url": r.url,
                "mode": r.mode,
                "fmt": r.video_format if r.mode == "video" else "mp3",
                "status": "Pending",
                "request": r,
            }
            for r in requests
        ]
        self._completed_results = []
        if self._on_queue_update:
            self._on_queue_update(self._queue_items)

        self._set_downloading(True)

        # Log runtime status so user can see what's being used
        js_ok = self._js_runtime and self._js_runtime.available
        if js_ok:
            self._log_ui(
                f"▶ Starting {len(requests)} download(s)…  "
                f"[JS: {self._js_runtime.name} v{self._js_runtime.version}]"
            )
        else:
            self._log_ui(
                f"▶ Starting {len(requests)} download(s)…  "
                f"[⚠ No JS runtime — install Node.js if downloads fail]"
            )

        self._worker = DownloadWorker(
            requests=requests,
            on_progress=self._thread_safe_progress,
            on_item_start=self._thread_safe_item_start,
            on_item_done=self._thread_safe_item_done,
            on_log=self._thread_safe_log,
            on_all_done=self._thread_safe_all_done,
        )
        self._worker.start()

    def _make_request(self, url: str, mode: str, fmt: str, output_dir: str) -> DownloadRequest:
        return DownloadRequest(
            url=url,
            mode=mode,
            video_format=fmt,
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
            # JS runtime — critical for YouTube extraction
            js_runtime_name=self._settings.get("_js_runtime_name") or "",
            js_runtime_path=self._settings.get("_js_runtime_path") or "",
        )

    def _cancel_download(self) -> None:
        if self._worker:
            self._worker.stop()
            self._log_ui("⏹ Cancellation requested…")
        if self._conv_worker:
            self._conv_worker.stop()

    def _ask_format(self, url: str) -> Optional[str]:
        dlg = FormatDialog(self.winfo_toplevel(), url)
        self.wait_window(dlg)
        return dlg.chosen_format

    def _clear_log(self) -> None:
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    # ── Post-download conversion ──────────────────────────────────────────────

    def _start_conversion_batch(self, completed_results: list[DownloadResult]) -> bool:
        """Start converting the downloaded files. Returns True if a batch started."""
        if not self._conv_enabled_var.get():
            return False

        import os
        files = [
            path
            for r in completed_results if r.success
            for path in (r.filepaths or ([r.filepath] if r.filepath else []))
        ]
        if not files:
            self._log_ui("🔄 No files to convert.")
            return False

        output_format = self._conv_format_var.get()
        bitrate = self._conv_bitrate_var.get()
        delete_source = self._del_source_var.get()

        try:
            from conversion_worker import ConversionRequest, ConversionWorker
        except ImportError:
            self._log_ui("❌ conversion_worker module not found — skipping conversion.")
            return False

        ffmpeg_dir = self._settings.get("_ffmpeg_location") or ""
        conv_requests = []
        for path in files:
            base, ext = os.path.splitext(path)
            if ext.lower().lstrip(".") == output_format.lower():
                self._log_ui(
                    f"🔄 Skipping {os.path.basename(path)} — already {output_format.upper()}."
                )
                continue
            conv_requests.append(
                ConversionRequest(
                    input_file=path,
                    output_file=f"{base}.{output_format}",
                    output_format=output_format,
                    bitrate=bitrate,
                    delete_source=delete_source,
                    ffmpeg_dir=ffmpeg_dir,
                )
            )
        if not conv_requests:
            return False

        self._log_ui(
            f"🔄 Converting {len(conv_requests)} file(s) "
            f"to {output_format.upper()} @ {bitrate}…"
        )
        self._status_label.configure(text="Converting…", text_color="#DCDCAA")
        self._cancel_btn.configure(state="normal")
        self._download_btn.configure(state="disabled")
        self._is_converting = True

        self._conv_worker = ConversionWorker(
            requests=conv_requests,
            on_progress=self._thread_safe_conv_progress,
            on_item_done=self._thread_safe_conv_done,
            on_log=self._thread_safe_log,
            on_all_done=self._thread_safe_conv_all_done,
        )
        self._conv_worker.start()
        return True

    # ── Thread-safe callbacks ─────────────────────────────────────────────────

    def _thread_safe_progress(self, data: ProgressData) -> None:
        self.after(0, self._apply_progress, data)

    def _thread_safe_conv_progress(self, percent: float, time_str: str) -> None:
        self.after(0, self._apply_conv_progress, percent, time_str)

    def _thread_safe_item_start(self, url: str, index: int, total: int) -> None:
        self.after(0, self._apply_item_start, url, index, total)

    def _thread_safe_item_done(self, result: DownloadResult) -> None:
        self.after(0, self._apply_item_done, result)

    def _thread_safe_conv_done(self, result) -> None:
        self.after(0, self._apply_conv_done, result)

    def _thread_safe_log(self, msg: str) -> None:
        self.after(0, self._log_ui, msg)

    def _thread_safe_all_done(self) -> None:
        self.after(0, self._apply_all_done)

    def _thread_safe_conv_all_done(self) -> None:
        self.after(0, self._apply_conv_all_done)

    # ── UI updates (main thread) ──────────────────────────────────────────────

    def _apply_progress(self, data: ProgressData) -> None:
        self._progress_bar.set(data.percent / 100.0)
        self._pct_label.configure(text=f"{data.percent:.0f}%")
        self._speed_label.configure(text=f"Speed: {data.speed}")
        self._eta_label.configure(text=f"ETA: {data.eta}")
        if data.status == "finished":
            self._status_label.configure(text="Processing…", text_color="#DCDCAA")
        else:
            self._status_label.configure(text="Downloading", text_color="#4EC9B0")

    def _apply_conv_progress(self, percent: float, time_str: str) -> None:
        self._progress_bar.set(percent / 100.0)
        self._pct_label.configure(text=f"{percent:.0f}%")
        self._speed_label.configure(text=f"Time: {time_str}")
        self._status_label.configure(text="Converting…", text_color="#DCDCAA")

    def _apply_item_start(self, url: str, index: int, total: int) -> None:
        short = url if len(url) <= 55 else url[:52] + "…"
        self._current_item_label.configure(text=f"[{index}/{total}] {short}")
        if 0 < index <= len(self._queue_items):
            self._queue_items[index - 1]["status"] = "Downloading"
        if self._on_queue_update:
            self._on_queue_update(self._queue_items)

    def _apply_item_done(self, result: DownloadResult) -> None:
        if result.success:
            self._log_ui(f"✅ Done: {result.title}")
            if self._settings.get("auto_open_folder") and result.filepath:
                self._open_folder(result.filepath)
        else:
            self._log_ui(f"❌ Failed: {result.url}\n   {result.error_message}")

        fmt_label = "mp3"
        if 0 < result.index <= len(self._queue_items):
            item = self._queue_items[result.index - 1]
            fmt_label = item["fmt"]
            item["status"] = "Completed" if result.success else "Failed"
        self._completed_results.append(result)

        self._history.add_entry(
            title=result.title,
            url=result.url,
            fmt=fmt_label,
            status="success" if result.success else "failed",
            filepath=result.filepath,
        )
        if self._on_queue_update:
            self._on_queue_update(self._queue_items)

    def _apply_conv_done(self, result) -> None:
        import os
        name = os.path.basename(result.request.output_file)
        if result.success:
            self._log_ui(f"🔄 Converted: {name}")
        else:
            self._log_ui(f"❌ Conversion failed: {name}\n   {result.error_message}")

    def _apply_all_done(self) -> None:
        self._set_downloading(False)
        self._log_ui("🏁 All downloads finished.")
        self._status_label.configure(text="Done", text_color="#4CAF50")
        self._current_item_label.configure(text="")

        # Convert straight from this batch's results (not via history lookups,
        # which mismatch when the same URL is downloaded more than once).
        if self._conv_enabled_var.get() and not (self._worker and self._worker.is_cancelled):
            self._start_conversion_batch(self._completed_results)

    def _apply_conv_all_done(self) -> None:
        self._is_converting = False
        self._set_downloading(False)
        self._cancel_btn.configure(state="disabled")
        self._log_ui("🔄 All conversions finished.")
        self._status_label.configure(text="Done", text_color="#4CAF50")

    def _set_downloading(self, state: bool) -> None:
        self._is_downloading = state
        self._download_btn.configure(
            state="disabled" if state else ("normal" if self._ffmpeg_ok else "disabled")
        )
        self._cancel_btn.configure(state="normal" if state else "disabled")
        if not state:
            self._progress_bar.set(0)
            self._pct_label.configure(text="0%")
            self._speed_label.configure(text="Speed: —")
            self._eta_label.configure(text="ETA: —")

    def _log_ui(self, msg: str) -> None:
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")
        _log.info(msg)

    def on_settings_changed(self, key: str, value) -> None:
        if key == "output_dir":
            self._outdir_var.set(str(value))
        elif key == "default_mode":
            self._mode_var.set(str(value))

    @staticmethod
    def _open_folder(filepath: str) -> None:
        import os, sys, subprocess
        folder = os.path.dirname(os.path.abspath(filepath))
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as exc:
            _log.error("Could not open folder: %s", exc)
