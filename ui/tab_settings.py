"""
UI Tab: Settings — all user-configurable preferences with live persistence.
"""
from __future__ import annotations

import os
import tkinter.filedialog as fd
from typing import Any

import customtkinter as ctk

from utils.settings_manager import SettingsManager
from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)


class SettingsTab(ctk.CTkFrame):
    """
    Full settings panel. Every widget change persists immediately via
    SettingsManager. A callback notifies other tabs when key settings change.
    """

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        settings: SettingsManager,
        on_settings_changed: callable | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._settings = settings
        self._on_changed = on_settings_changed
        self._vars: dict[str, ctk.Variable] = {}
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        ctk.CTkLabel(
            self,
            text="⚙️  Settings",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(anchor="w", padx=24, pady=(20, 4))

        ctk.CTkLabel(
            self,
            text="All changes are saved automatically.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(anchor="w", padx=24, pady=(0, 16))

        scroll = ctk.CTkScrollableFrame(self, label_text="")
        scroll.pack(fill="both", expand=True, padx=24, pady=(0, 12))

        self._build_section(scroll, "📁  Output")
        self._build_output_section(scroll)

        self._build_section(scroll, "🎬  Download Defaults")
        self._build_download_section(scroll)

        self._build_section(scroll, "⚡  Performance")
        self._build_performance_section(scroll)

        self._build_section(scroll, "🌐  Network")
        self._build_network_section(scroll)

        self._build_section(scroll, "🔧  Tools")
        self._build_tools_section(scroll)

        self._build_section(scroll, "🎨  Appearance")
        self._build_appearance_section(scroll)

        ctk.CTkButton(
            self,
            text="↺  Reset All to Defaults",
            width=200,
            height=36,
            fg_color="transparent",
            border_width=1,
            text_color=("gray30", "gray70"),
            command=self._reset_defaults,
        ).pack(pady=(0, 16))

    # ── Section label ─────────────────────────────────────────────────────────

    @staticmethod
    def _build_section(parent: ctk.CTkFrame, title: str) -> None:
        ctk.CTkLabel(
            parent,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=4, pady=(16, 4))
        ctk.CTkFrame(parent, height=1, fg_color="#333").pack(fill="x", padx=4, pady=(0, 8))

    # ── Output section ────────────────────────────────────────────────────────

    def _build_output_section(self, parent: ctk.CTkFrame) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(row, text="Default output folder:", width=200, anchor="w").pack(side="left")

        var = ctk.StringVar(value=self._settings.get("output_dir"))
        self._vars["output_dir"] = var
        ctk.CTkEntry(row, textvariable=var, width=260,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row, text="Browse", width=70,
            command=lambda: self._browse_folder(var),
        ).pack(side="left")
        var.trace_add("write", lambda *_: self._save("output_dir", var.get()))

        self._row_checkbox(parent, "auto_open_folder", "Auto-open output folder when done")
        self._row_checkbox(parent, "skip_existing",    "Skip if file already exists")

    # ── Download defaults ─────────────────────────────────────────────────────

    def _build_download_section(self, parent: ctk.CTkFrame) -> None:
        # Default mode
        row = self._make_row(parent, "Default mode:")
        var = ctk.StringVar(value=self._settings.get("default_mode"))
        self._vars["default_mode"] = var
        ctk.CTkSegmentedButton(
            row, values=["Video", "Audio (MP3)"], variable=var, width=200,
        ).pack(side="left")
        var.trace_add("write", lambda *_: self._save("default_mode", var.get()))

        # Default video format
        row2 = self._make_row(parent, "Default video format:")
        var2 = ctk.StringVar(value=self._settings.get("default_video_format"))
        self._vars["default_video_format"] = var2
        ctk.CTkSegmentedButton(
            row2, values=["mp4", "mkv", "webm"], variable=var2, width=200,
        ).pack(side="left")
        var2.trace_add("write", lambda *_: self._save("default_video_format", var2.get()))

        # Audio quality
        row3 = self._make_row(parent, "MP3 audio quality:")
        var3 = ctk.StringVar(value=self._settings.get("audio_quality"))
        self._vars["audio_quality"] = var3
        ctk.CTkSegmentedButton(
            row3, values=["128", "192", "256", "320"], variable=var3, width=240,
        ).pack(side="left")
        ctk.CTkLabel(row3, text="kbps", text_color="gray",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=6)
        var3.trace_add("write", lambda *_: self._save("audio_quality", var3.get()))

        self._row_checkbox(parent, "ask_format_per_video",
                           "Ask format for each video individually")
        self._row_checkbox(parent, "embed_thumbnail",  "Embed thumbnail into file")
        self._row_checkbox(parent, "write_subtitles",  "Download subtitles (auto-generated)")

        # Subtitle language
        row4 = self._make_row(parent, "Subtitle language code:")
        var4 = ctk.StringVar(value=self._settings.get("subtitle_lang"))
        self._vars["subtitle_lang"] = var4
        ctk.CTkEntry(row4, textvariable=var4, width=80).pack(side="left")
        ctk.CTkLabel(row4, text="e.g. en, fr, de", text_color="gray",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=8)
        var4.trace_add("write", lambda *_: self._save("subtitle_lang", var4.get()))

    # ── Performance ───────────────────────────────────────────────────────────

    def _build_performance_section(self, parent: ctk.CTkFrame) -> None:
        # Max retries
        row = self._make_row(parent, "Max retries per download:")
        var = ctk.IntVar(value=int(self._settings.get("max_retries")))
        self._vars["max_retries"] = var
        lbl = ctk.CTkLabel(row, text=str(var.get()), width=24)
        ctk.CTkSlider(
            row, from_=0, to=10, number_of_steps=10, variable=var, width=180,
            command=lambda v: (self._save("max_retries", int(v)),
                               lbl.configure(text=str(int(v)))),
        ).pack(side="left", padx=(0, 12))
        lbl.pack(side="left")

        # Concurrent fragments
        row2 = self._make_row(parent, "Concurrent fragments:")
        var2 = ctk.IntVar(value=int(self._settings.get("concurrent_fragments")))
        self._vars["concurrent_fragments"] = var2
        lbl2 = ctk.CTkLabel(row2, text=str(var2.get()), width=24)
        ctk.CTkSlider(
            row2, from_=1, to=16, number_of_steps=15, variable=var2, width=180,
            command=lambda v: (self._save("concurrent_fragments", int(v)),
                               lbl2.configure(text=str(int(v)))),
        ).pack(side="left", padx=(0, 12))
        lbl2.pack(side="left")

    # ── Network ───────────────────────────────────────────────────────────────

    def _build_network_section(self, parent: ctk.CTkFrame) -> None:
        # Rate limit
        row = self._make_row(parent, "Rate limit (KB/s, 0 = unlimited):")
        var = ctk.IntVar(value=int(self._settings.get("rate_limit_kb")))
        self._vars["rate_limit_kb"] = var
        ctk.CTkEntry(row, textvariable=var, width=90).pack(side="left")
        var.trace_add("write", lambda *_: self._save_int("rate_limit_kb", var))

        # Proxy
        row2 = self._make_row(parent, "Proxy URL (leave blank for none):")
        var2 = ctk.StringVar(value=self._settings.get("proxy_url"))
        self._vars["proxy_url"] = var2
        ctk.CTkEntry(
            row2, textvariable=var2, width=300,
            placeholder_text="http://user:pass@host:port",
            font=ctk.CTkFont(size=11),
        ).pack(side="left")
        var2.trace_add("write", lambda *_: self._save("proxy_url", var2.get()))

    # ── Tools section (FFmpeg + JS runtime) ───────────────────────────────────

    def _build_tools_section(self, parent: ctk.CTkFrame) -> None:
        # ── FFmpeg binary location ────────────────────────────────────────────
        ffmpeg_frame = ctk.CTkFrame(
            parent, fg_color=("gray92", "#1A1A2E"), corner_radius=8
        )
        ffmpeg_frame.pack(fill="x", padx=4, pady=(4, 8))

        header = ctk.CTkFrame(ffmpeg_frame, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            header,
            text="FFmpeg Binary Location",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(side="left")

        # Detected-at-startup badge
        self._ffmpeg_status_lbl = ctk.CTkLabel(
            header,
            text=self._get_ffmpeg_status_text(),
            font=ctk.CTkFont(size=11),
            text_color=self._get_ffmpeg_status_color(),
            anchor="e",
        )
        self._ffmpeg_status_lbl.pack(side="right")

        ctk.CTkLabel(
            ffmpeg_frame,
            text=(
                "Leave blank to use the auto-detected bundled FFmpeg (recommended).\n"
                "Set a custom folder only if you need a specific build."
            ),
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=12, pady=(0, 6))

        path_row = ctk.CTkFrame(ffmpeg_frame, fg_color="transparent")
        path_row.pack(fill="x", padx=12, pady=(0, 10))

        var = ctk.StringVar(value=self._settings.get("ffmpeg_bin_dir") or "")
        self._vars["ffmpeg_bin_dir"] = var

        entry = ctk.CTkEntry(
            path_row,
            textvariable=var,
            placeholder_text="e.g. C:\\ffmpeg\\bin  (blank = auto)",
            font=ctk.CTkFont(size=11),
            width=300,
        )
        entry.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            path_row, text="Browse", width=70,
            command=lambda: self._browse_folder(var),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            path_row, text="Detect", width=70,
            command=self._detect_ffmpeg,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            path_row, text="Clear", width=60,
            fg_color="transparent", border_width=1,
            text_color=("gray30", "gray70"),
            command=lambda: var.set(""),
        ).pack(side="left")

        var.trace_add("write", lambda *_: self._on_ffmpeg_path_changed(var.get()))

        # ── JS Runtime location ───────────────────────────────────────────────
        js_frame = ctk.CTkFrame(
            parent, fg_color=("gray92", "#1A1A2E"), corner_radius=8
        )
        js_frame.pack(fill="x", padx=4, pady=(0, 4))

        js_header = ctk.CTkFrame(js_frame, fg_color="transparent")
        js_header.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            js_header,
            text="JavaScript Runtime (for YouTube)",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(side="left")

        self._js_status_lbl = ctk.CTkLabel(
            js_header,
            text=self._get_js_status_text(),
            font=ctk.CTkFont(size=11),
            text_color=self._get_js_status_color(),
            anchor="e",
        )
        self._js_status_lbl.pack(side="right")

        ctk.CTkLabel(
            js_frame,
            text=(
                "Node.js (v20+), QuickJS, Deno, or Bun. Required for YouTube downloads.\n"
                "Leave blank to use the auto-detected runtime."
            ),
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=12, pady=(0, 6))

        js_path_row = ctk.CTkFrame(js_frame, fg_color="transparent")
        js_path_row.pack(fill="x", padx=12, pady=(0, 10))

        js_var = ctk.StringVar(
            value=self._settings.get("js_runtime_override_path") or ""
        )
        self._vars["js_runtime_override_path"] = js_var

        ctk.CTkEntry(
            js_path_row,
            textvariable=js_var,
            placeholder_text="e.g. C:\\Program Files\\nodejs\\node.exe  (blank = auto)",
            font=ctk.CTkFont(size=11),
            width=300,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            js_path_row, text="Browse", width=70,
            command=lambda: self._browse_file(
                js_var,
                title="Select JS runtime executable",
                filetypes=[("Executables", "*.exe"), ("All files", "*.*")]
                if os.name == "nt" else [("All files", "*")],
            ),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            js_path_row, text="Clear", width=60,
            fg_color="transparent", border_width=1,
            text_color=("gray30", "gray70"),
            command=lambda: js_var.set(""),
        ).pack(side="left")

        js_var.trace_add("write", lambda *_: self._on_js_path_changed(js_var.get()))

    # ── Appearance ────────────────────────────────────────────────────────────

    def _build_appearance_section(self, parent: ctk.CTkFrame) -> None:
        row = self._make_row(parent, "Theme:")
        var = ctk.StringVar(value=self._settings.get("appearance_mode").capitalize())
        self._vars["appearance_mode"] = var
        ctk.CTkSegmentedButton(
            row, values=["Dark", "Light", "System"],
            variable=var, command=self._apply_theme,
        ).pack(side="left")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_row(parent: ctk.CTkFrame, label: str) -> ctk.CTkFrame:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(row, text=label, width=240, anchor="w").pack(side="left")
        return row

    def _row_checkbox(self, parent: ctk.CTkFrame, key: str, label: str) -> None:
        var = ctk.BooleanVar(value=bool(self._settings.get(key)))
        self._vars[key] = var
        ctk.CTkCheckBox(
            parent, text=label, variable=var,
            command=lambda: self._save(key, var.get()),
        ).pack(anchor="w", padx=4, pady=3)

    def _browse_folder(self, var: ctk.StringVar) -> None:
        folder = fd.askdirectory(title="Select folder")
        if folder:
            var.set(folder)

    def _browse_file(
        self,
        var: ctk.StringVar,
        title: str = "Select file",
        filetypes: list | None = None,
    ) -> None:
        path = fd.askopenfilename(
            title=title,
            filetypes=filetypes or [("All files", "*")],
        )
        if path:
            var.set(path)

    def _save(self, key: str, value: Any) -> None:
        self._settings.set(key, value)
        if self._on_changed:
            self._on_changed(key, value)

    def _save_int(self, key: str, var: ctk.IntVar) -> None:
        try:
            self._save(key, var.get())
        except Exception:
            pass

    def _apply_theme(self, value: str) -> None:
        self._save("appearance_mode", value.lower())
        ctk.set_appearance_mode(value.lower())

    # ── FFmpeg path handling ──────────────────────────────────────────────────

    def _on_ffmpeg_path_changed(self, value: str) -> None:
        """Persist the user-supplied FFmpeg folder and update the status badge."""
        stripped = value.strip()
        self._save("ffmpeg_bin_dir", stripped)

        if stripped:
            # User set an explicit path — validate it immediately
            exe = os.path.join(
                stripped, "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
            )
            if os.path.isfile(exe):
                # Push it into the internal key yt-dlp reads
                self._save("_ffmpeg_location", stripped)
                self._ffmpeg_status_lbl.configure(
                    text="✓ Valid path", text_color="#4CAF50"
                )
                _log.info("FFmpeg location set by user: %s", stripped)
            else:
                self._ffmpeg_status_lbl.configure(
                    text="⚠ ffmpeg not found in folder", text_color="#FF6B6B"
                )
        else:
            # Blank — revert to auto-detected path
            auto = self._auto_detect_ffmpeg()
            self._save("_ffmpeg_location", auto)
            if auto:
                self._ffmpeg_status_lbl.configure(
                    text=f"✓ Auto: {auto}", text_color="#4CAF50"
                )
            else:
                self._ffmpeg_status_lbl.configure(
                    text="⚠ Not found", text_color="#FF6B6B"
                )

    def _detect_ffmpeg(self) -> None:
        """Trigger a live re-detection and populate the entry with the result."""
        path = self._auto_detect_ffmpeg()
        if path:
            var = self._vars.get("ffmpeg_bin_dir")
            if var:
                var.set(path)
            self._ffmpeg_status_lbl.configure(
                text=f"✓ Detected: {path}", text_color="#4CAF50"
            )
        else:
            self._ffmpeg_status_lbl.configure(
                text="⚠ Could not detect", text_color="#FF6B6B"
            )

    @staticmethod
    def _auto_detect_ffmpeg() -> str:
        """Return the directory containing ffmpeg from system PATH, or ''."""
        import shutil
        found = shutil.which("ffmpeg")
        return os.path.dirname(os.path.abspath(found)) if found else ""

    # ── JS runtime path handling ──────────────────────────────────────────────

    def _on_js_path_changed(self, value: str) -> None:
        stripped = value.strip()
        self._save("js_runtime_override_path", stripped)

        if stripped:
            if os.path.isfile(stripped):
                # Detect which runtime this is and push into internal settings
                name = self._detect_runtime_name(stripped)
                self._save("_js_runtime_name", name)
                self._save("_js_runtime_path", stripped)
                self._js_status_lbl.configure(
                    text=f"✓ {name} set", text_color="#4CAF50"
                )
                _log.info("JS runtime set by user: %s (%s)", stripped, name)
            else:
                self._js_status_lbl.configure(
                    text="⚠ File not found", text_color="#FF6B6B"
                )
        else:
            # Blank — revert to auto-detected runtime
            try:
                from js_runtime_manager import detect_js_runtime
                result = detect_js_runtime()
                self._save("_js_runtime_name", result.name)
                self._save("_js_runtime_path", result.path or "")
                if result.available:
                    self._js_status_lbl.configure(
                        text=f"✓ Auto: {result.name} v{result.version}",
                        text_color="#4CAF50",
                    )
                else:
                    self._js_status_lbl.configure(
                        text="⚠ No runtime found", text_color="#FF6B6B"
                    )
            except Exception:
                self._js_status_lbl.configure(
                    text="⚠ Detection failed", text_color="#FF6B6B"
                )

    @staticmethod
    def _detect_runtime_name(path: str) -> str:
        """Guess the runtime name from the binary filename."""
        base = os.path.basename(path).lower().replace(".exe", "")
        for name in ("node", "nodejs", "qjs", "quickjs", "deno", "bun"):
            if name in base:
                return "node" if "node" in name else name
        return "node"  # safe default

    # ── Status badge helpers ──────────────────────────────────────────────────

    def _get_ffmpeg_status_text(self) -> str:
        # Check user-saved directory first
        saved = self._settings.get("ffmpeg_bin_dir") or ""
        if saved and os.path.isdir(saved):
            exe = os.path.join(saved, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
            if os.path.isfile(exe):
                return f"✓ Saved: {saved}"
        # Fall back to _ffmpeg_location written at startup
        loc = self._settings.get("_ffmpeg_location") or ""
        if loc and os.path.isdir(loc):
            exe = os.path.join(loc, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
            if os.path.isfile(exe):
                return f"✓ PATH: {loc}"
        return "⚠ Not found — set path below"

    def _get_ffmpeg_status_color(self) -> str:
        return "#4CAF50" if "✓" in self._get_ffmpeg_status_text() else "#FF6B6B"

    def _get_js_status_text(self) -> str:
        name = self._settings.get("_js_runtime_name") or ""
        path = self._settings.get("_js_runtime_path") or ""
        if name and name != "none":
            return f"✓ {name} detected" + (f" ({path})" if path else "")
        return "⚠ No runtime found"

    def _get_js_status_color(self) -> str:
        return "#4CAF50" if "✓" in self._get_js_status_text() else "#FF6B6B"

    # ── Reset ─────────────────────────────────────────────────────────────────

    def _reset_defaults(self) -> None:
        self._settings.reset_to_defaults()
        for key, var in self._vars.items():
            new_val = self._settings.get(key)
            try:
                if isinstance(var, ctk.BooleanVar):
                    var.set(bool(new_val))
                elif isinstance(var, ctk.IntVar):
                    var.set(int(new_val))
                else:
                    var.set(str(new_val) if new_val is not None else "")
            except Exception:
                pass
        if self._on_changed:
            self._on_changed("__reset__", None)
        _log.info("Settings reset to defaults via UI.")
