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

        self._build_section(scroll, "🎨  Appearance")
        self._build_appearance_section(scroll)

        # Reset button
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
        ctk.CTkLabel(row, text="Default output folder:", width=180, anchor="w").pack(side="left")

        var = ctk.StringVar(value=self._settings.get("output_dir"))
        self._vars["output_dir"] = var
        entry = ctk.CTkEntry(row, textvariable=var, width=280, font=ctk.CTkFont(size=11))
        entry.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row, text="Browse", width=70,
            command=lambda: self._browse_folder(var)
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
            row, values=["Video", "Audio (MP3)"], variable=var, width=200
        ).pack(side="left")
        var.trace_add("write", lambda *_: self._save("default_mode", var.get()))

        # Default video format
        row2 = self._make_row(parent, "Default video format:")
        var2 = ctk.StringVar(value=self._settings.get("default_video_format"))
        self._vars["default_video_format"] = var2
        ctk.CTkSegmentedButton(
            row2, values=["mp4", "mkv", "webm"], variable=var2, width=200
        ).pack(side="left")
        var2.trace_add("write", lambda *_: self._save("default_video_format", var2.get()))

        # Audio quality
        row3 = self._make_row(parent, "MP3 audio quality:")
        var3 = ctk.StringVar(value=self._settings.get("audio_quality"))
        self._vars["audio_quality"] = var3
        ctk.CTkSegmentedButton(
            row3, values=["128", "192", "256", "320"], variable=var3, width=240
        ).pack(side="left")
        ctk.CTkLabel(row3, text="kbps", text_color="gray", font=ctk.CTkFont(size=11)).pack(side="left", padx=6)
        var3.trace_add("write", lambda *_: self._save("audio_quality", var3.get()))

        self._row_checkbox(parent, "ask_format_per_video", "Ask format for each video individually")
        self._row_checkbox(parent, "embed_thumbnail",      "Embed thumbnail into file")
        self._row_checkbox(parent, "write_subtitles",      "Download subtitles (auto-generated)")

        # Subtitle language
        row4 = self._make_row(parent, "Subtitle language code:")
        var4 = ctk.StringVar(value=self._settings.get("subtitle_lang"))
        self._vars["subtitle_lang"] = var4
        entry = ctk.CTkEntry(row4, textvariable=var4, width=80)
        entry.pack(side="left")
        ctk.CTkLabel(row4, text="e.g. en, fr, de", text_color="gray",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=8)
        var4.trace_add("write", lambda *_: self._save("subtitle_lang", var4.get()))

    # ── Performance ───────────────────────────────────────────────────────────

    def _build_performance_section(self, parent: ctk.CTkFrame) -> None:
        # Max retries
        row = self._make_row(parent, "Max retries per download:")
        var = ctk.IntVar(value=int(self._settings.get("max_retries")))
        self._vars["max_retries"] = var
        ctk.CTkSlider(
            row, from_=0, to=10, number_of_steps=10,
            variable=var, width=180,
            command=lambda v: self._save("max_retries", int(v)),
        ).pack(side="left", padx=(0, 12))
        lbl = ctk.CTkLabel(row, text=str(var.get()), width=24)
        lbl.pack(side="left")
        var.trace_add("write", lambda *_: lbl.configure(text=str(var.get())))

        # Concurrent fragments
        row2 = self._make_row(parent, "Concurrent fragments:")
        var2 = ctk.IntVar(value=int(self._settings.get("concurrent_fragments")))
        self._vars["concurrent_fragments"] = var2
        ctk.CTkSlider(
            row2, from_=1, to=16, number_of_steps=15,
            variable=var2, width=180,
            command=lambda v: self._save("concurrent_fragments", int(v)),
        ).pack(side="left", padx=(0, 12))
        lbl2 = ctk.CTkLabel(row2, text=str(var2.get()), width=24)
        lbl2.pack(side="left")
        var2.trace_add("write", lambda *_: lbl2.configure(text=str(var2.get())))

    # ── Network ───────────────────────────────────────────────────────────────

    def _build_network_section(self, parent: ctk.CTkFrame) -> None:
        # Rate limit
        row = self._make_row(parent, "Rate limit (KB/s, 0 = unlimited):")
        var = ctk.IntVar(value=int(self._settings.get("rate_limit_kb")))
        self._vars["rate_limit_kb"] = var
        entry = ctk.CTkEntry(row, textvariable=var, width=90)
        entry.pack(side="left")
        var.trace_add("write", lambda *_: self._save_int("rate_limit_kb", var))

        # Proxy
        row2 = self._make_row(parent, "Proxy URL (leave blank for none):")
        var2 = ctk.StringVar(value=self._settings.get("proxy_url"))
        self._vars["proxy_url"] = var2
        ctk.CTkEntry(row2, textvariable=var2, width=300,
                     placeholder_text="http://user:pass@host:port",
                     font=ctk.CTkFont(size=11)).pack(side="left")
        var2.trace_add("write", lambda *_: self._save("proxy_url", var2.get()))

    # ── Appearance ────────────────────────────────────────────────────────────

    def _build_appearance_section(self, parent: ctk.CTkFrame) -> None:
        row = self._make_row(parent, "Theme:")
        var = ctk.StringVar(value=self._settings.get("appearance_mode").capitalize())
        self._vars["appearance_mode"] = var
        ctk.CTkSegmentedButton(
            row,
            values=["Dark", "Light", "System"],
            variable=var,
            command=self._apply_theme,
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
        folder = fd.askdirectory(title="Select output folder")
        if folder:
            var.set(folder)

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

    def _reset_defaults(self) -> None:
        self._settings.reset_to_defaults()
        # Refresh all widget variables
        for key, var in self._vars.items():
            new_val = self._settings.get(key)
            try:
                if isinstance(var, ctk.BooleanVar):
                    var.set(bool(new_val))
                elif isinstance(var, ctk.IntVar):
                    var.set(int(new_val))
                else:
                    var.set(str(new_val))
            except Exception:
                pass
        if self._on_changed:
            self._on_changed("__reset__", None)
        _log.info("Settings reset to defaults via UI.")
