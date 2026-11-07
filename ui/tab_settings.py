"""
UI Tab: Settings — user preferences with live persistence.

Everyday options are shown first ("Saving", "Downloads", "Appearance").
Technical ones (retries, speed limit, proxy, tool locations) live in a
collapsed "Advanced" section. Every option has a hover/focus tooltip.
"""
from __future__ import annotations

import os
import tkinter.filedialog as fd
from typing import Any

import customtkinter as ctk

from ui import theme
from ui.tooltip import add_tooltip
from utils.logger import AppLogger
from utils.settings_manager import SettingsManager

_log = AppLogger.get_logger(__name__)

_LABEL_WIDTH = 230


class SettingsTab(ctk.CTkFrame):
    """
    Settings panel. Every widget change persists immediately via
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
        self._advanced_open = False
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        ctk.CTkLabel(self, text="⚙️  Settings",
                     font=theme.font(22, "bold")).pack(anchor="w", padx=24, pady=(20, 2))
        ctk.CTkLabel(self, text="Changes are saved automatically. Hover over an option to see what it does.",
                     font=theme.font(13), text_color=theme.MUTED,
                     ).pack(anchor="w", padx=24, pady=(0, 12))

        scroll = ctk.CTkScrollableFrame(self, label_text="")
        scroll.pack(fill="both", expand=True, padx=24, pady=(0, 10))
        self._scroll = scroll

        self._section(scroll, "📁  Saving")
        self._build_saving_section(scroll)

        self._section(scroll, "🎬  Downloads")
        self._build_download_section(scroll)

        self._section(scroll, "🎨  Appearance")
        self._build_appearance_section(scroll)

        # ── Advanced (collapsed) ──────────────────────────────────────────────
        self._adv_toggle = ctk.CTkButton(
            scroll, text="▸  Advanced settings", anchor="w", height=34,
            font=theme.font(14, "bold"), fg_color="transparent",
            text_color=theme.TEXT, hover_color=theme.HOVER,
            command=self._toggle_advanced,
        )
        self._adv_toggle.pack(fill="x", padx=0, pady=(18, 0))
        add_tooltip(self._adv_toggle,
                    "Retries, speed limit, proxy and helper-tool locations. "
                    "Most people never need to change these.")
        self._adv_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._section(self._adv_frame, "⚡  Reliability & speed")
        self._build_performance_section(self._adv_frame)
        self._section(self._adv_frame, "🌐  Network")
        self._build_network_section(self._adv_frame)
        self._section(self._adv_frame, "🔧  Helper tools")
        self._build_tools_section(self._adv_frame)

        reset = ctk.CTkButton(
            self, text="↺  Reset all to defaults", width=200, height=36,
            fg_color="transparent", border_width=1, text_color=theme.MUTED,
            command=self._reset_defaults,
        )
        reset.pack(pady=(0, 16))
        add_tooltip(reset, "Puts every setting back to how it was when the app was installed.")

    def _toggle_advanced(self) -> None:
        self._advanced_open = not self._advanced_open
        if self._advanced_open:
            self._adv_toggle.configure(text="▾  Advanced settings")
            self._adv_frame.pack(fill="x", after=self._adv_toggle)
        else:
            self._adv_toggle.configure(text="▸  Advanced settings")
            self._adv_frame.pack_forget()

    @staticmethod
    def _section(parent: ctk.CTkFrame, title: str) -> None:
        ctk.CTkLabel(parent, text=title, font=theme.font(14, "bold"),
                     anchor="w").pack(fill="x", padx=4, pady=(16, 4))
        theme.divider(parent, padx=4, pady=(0, 8))

    # ── Saving ────────────────────────────────────────────────────────────────

    def _build_saving_section(self, parent: ctk.CTkFrame) -> None:
        row = self._make_row(parent, "Save downloads to:",
                             "The folder new downloads go into. You can also change it on the home screen.")
        var = ctk.StringVar(value=self._settings.get("output_dir"))
        self._vars["output_dir"] = var
        ctk.CTkEntry(row, textvariable=var, width=300,
                     font=theme.font(12)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Browse", width=70,
                      command=lambda: self._browse_folder(var)).pack(side="left")
        var.trace_add("write", lambda *_: self._save("output_dir", var.get()))

        self._row_checkbox(parent, "auto_open_folder", "Open the folder when downloads finish",
                           "Shows the saved files in File Explorer as soon as a batch is done.")
        self._row_checkbox(parent, "skip_existing", "Skip videos I've already downloaded",
                           "If a file with the same name is already in the folder, it isn't downloaded again.")

    # ── Downloads ─────────────────────────────────────────────────────────────

    def _build_download_section(self, parent: ctk.CTkFrame) -> None:
        self._segmented(parent, "default_mode", "Download by default:",
                        ["Video", "Audio (MP3)"],
                        "What the home screen starts with. You can switch it there any time.")
        self._segmented(parent, "video_quality", "Video quality:",
                        ["Best", "1080p", "720p", "480p"],
                        "1080p (Full HD) plays well everywhere. “Best” can be 4K: sharper, "
                        "but much bigger files that some older devices can't play.")
        self._segmented(parent, "default_video_format", "Video file type:",
                        ["mp4", "mkv", "webm"],
                        "MP4 works on almost every phone, TV and computer — keep this unless "
                        "you know you need MKV or WEBM.")
        row = self._segmented(parent, "audio_quality", "MP3 quality (kbps):",
                              ["128", "192", "256", "320"],
                              "Higher numbers sound better but make bigger files. 192 is a good balance.")
        self._row_checkbox(parent, "embed_thumbnail", "Add the video's picture to the file",
                           "Stores the thumbnail inside the file, so it shows as cover art in music "
                           "and video players.")
        self._row_checkbox(parent, "write_subtitles", "Also download subtitles",
                           "Saves a subtitle file next to the video (auto-generated ones when no "
                           "others exist), in the language below.")
        row4 = self._make_row(parent, "Subtitle language:",
                              "A short language code, e.g. en (English), fr (French), de (German), es (Spanish).")
        var4 = ctk.StringVar(value=self._settings.get("subtitle_lang"))
        self._vars["subtitle_lang"] = var4
        ctk.CTkEntry(row4, textvariable=var4, width=80, font=theme.font(13)).pack(side="left")
        ctk.CTkLabel(row4, text="e.g. en, fr, de", text_color=theme.MUTED,
                     font=theme.font(12)).pack(side="left", padx=8)
        var4.trace_add("write", lambda *_: self._save("subtitle_lang", var4.get()))

    # ── Appearance ────────────────────────────────────────────────────────────

    def _build_appearance_section(self, parent: ctk.CTkFrame) -> None:
        row = self._make_row(parent, "Theme:",
                             "“System” follows Windows' light/dark setting automatically.")
        var = ctk.StringVar(value=str(self._settings.get("appearance_mode")).capitalize())
        self._vars["appearance_mode"] = var
        ctk.CTkSegmentedButton(row, values=["System", "Light", "Dark"], variable=var,
                               command=self._apply_theme, font=theme.font(13)).pack(side="left")

    # ── Advanced: performance ─────────────────────────────────────────────────

    def _build_performance_section(self, parent: ctk.CTkFrame) -> None:
        self._slider(parent, "max_retries", "Retries if a download fails:", 0, 10,
                     "How many times to try again after a network hiccup before giving up.")
        self._slider(parent, "concurrent_fragments", "Parallel connections:", 1, 16,
                     "How many pieces of a video download at once. Higher can be faster on "
                     "good connections; lower is gentler on slow ones.")
        self._row_checkbox(parent, "ask_format_per_video", "Ask for the file type of every video",
                           "Shows a pop-up for each link to choose MP4, MKV or WEBM. "
                           "Useful only if you mix file types in one batch.")

    # ── Advanced: network ─────────────────────────────────────────────────────

    def _build_network_section(self, parent: ctk.CTkFrame) -> None:
        row = self._make_row(parent, "Speed limit (KB/s):",
                             "Caps download speed so other apps stay fast. 0 means no limit.")
        var = ctk.IntVar(value=int(self._settings.get("rate_limit_kb")))
        self._vars["rate_limit_kb"] = var
        ctk.CTkEntry(row, textvariable=var, width=90, font=theme.font(13)).pack(side="left")
        ctk.CTkLabel(row, text="0 = unlimited", text_color=theme.MUTED,
                     font=theme.font(12)).pack(side="left", padx=8)
        var.trace_add("write", lambda *_: self._save_int("rate_limit_kb", var))

        row2 = self._make_row(parent, "Proxy:",
                              "Only needed on networks that require one (some schools and offices). "
                              "Leave blank otherwise.")
        var2 = ctk.StringVar(value=self._settings.get("proxy_url"))
        self._vars["proxy_url"] = var2
        ctk.CTkEntry(row2, textvariable=var2, width=300, font=theme.font(12),
                     placeholder_text="http://host:port  (blank = none)").pack(side="left")
        var2.trace_add("write", lambda *_: self._save("proxy_url", var2.get()))

    # ── Advanced: helper tools ────────────────────────────────────────────────

    def _build_tools_section(self, parent: ctk.CTkFrame) -> None:
        # FFmpeg
        card = self._card(parent, "FFmpeg",
                          "Joins video and audio and makes MP3s. Found automatically "
                          "(bundled with the app, installed, or on PATH) — set a folder "
                          "only to use a specific copy.")
        self._ffmpeg_status_lbl = card["status"]
        var = ctk.StringVar(value=self._settings.get("ffmpeg_bin_dir") or "")
        self._vars["ffmpeg_bin_dir"] = var
        row = card["row"]
        ctk.CTkEntry(row, textvariable=var, width=300, font=theme.font(12),
                     placeholder_text="Folder containing ffmpeg  (blank = automatic)",
                     ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Browse", width=70,
                      command=lambda: self._browse_folder(var)).pack(side="left", padx=(0, 8))
        detect = ctk.CTkButton(row, text="Detect", width=70, command=self._detect_ffmpeg)
        detect.pack(side="left", padx=(0, 8))
        add_tooltip(detect, "Look for FFmpeg again and fill in the folder it finds.")
        ctk.CTkButton(row, text="Clear", width=60, fg_color="transparent", border_width=1,
                      text_color=theme.MUTED, command=lambda: var.set("")).pack(side="left")
        var.trace_add("write", lambda *_: self._on_ffmpeg_path_changed(var.get()))

        # JS runtime
        card = self._card(parent, "JavaScript runtime",
                          "Deno, Node.js (v20+), Bun or QuickJS — lets the app read most "
                          "YouTube videos. Found automatically; the home screen's “Fix” "
                          "button can install Deno for you.")
        self._js_status_lbl = card["status"]
        js_var = ctk.StringVar(value=self._settings.get("js_runtime_override_path") or "")
        self._vars["js_runtime_override_path"] = js_var
        row = card["row"]
        ctk.CTkEntry(row, textvariable=js_var, width=300, font=theme.font(12),
                     placeholder_text="Path to deno.exe / node.exe  (blank = automatic)",
                     ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row, text="Browse", width=70,
            command=lambda: self._browse_file(
                js_var, title="Select JS runtime executable",
                filetypes=[("Programs", "*.exe"), ("All files", "*.*")]
                if os.name == "nt" else [("All files", "*")]),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Clear", width=60, fg_color="transparent", border_width=1,
                      text_color=theme.MUTED, command=lambda: js_var.set("")).pack(side="left")
        js_var.trace_add("write", lambda *_: self._on_js_path_changed(js_var.get()))
        self._refresh_tool_status()

    def _card(self, parent, title: str, desc: str) -> dict:
        frame = ctk.CTkFrame(parent, fg_color=theme.CARD_BG, corner_radius=8)
        frame.pack(fill="x", padx=4, pady=(4, 8))
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 2))
        ctk.CTkLabel(header, text=title, font=theme.font(13, "bold"), anchor="w").pack(side="left")
        status = ctk.CTkLabel(header, text="", font=theme.font(12), anchor="e")
        status.pack(side="right")
        ctk.CTkLabel(frame, text=desc, font=theme.font(12), text_color=theme.MUTED,
                     anchor="w", justify="left", wraplength=640).pack(fill="x", padx=12, pady=(0, 6))
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 10))
        return {"status": status, "row": row}

    # ── Row helpers ───────────────────────────────────────────────────────────

    def _make_row(self, parent: ctk.CTkFrame, label: str, tip: str = "") -> ctk.CTkFrame:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=4, pady=4)
        lbl = ctk.CTkLabel(row, text=label, width=_LABEL_WIDTH, anchor="w", font=theme.font(13))
        lbl.pack(side="left")
        if tip:
            add_tooltip(lbl, tip)
            add_tooltip(row, tip)
        return row

    def _segmented(self, parent, key: str, label: str, values: list[str], tip: str) -> ctk.CTkFrame:
        row = self._make_row(parent, label, tip)
        var = ctk.StringVar(value=str(self._settings.get(key)))
        self._vars[key] = var
        seg = ctk.CTkSegmentedButton(row, values=values, variable=var, font=theme.font(13))
        seg.pack(side="left")
        add_tooltip(seg, tip)
        var.trace_add("write", lambda *_: self._save(key, var.get()))
        return row

    def _slider(self, parent, key: str, label: str, lo: int, hi: int, tip: str) -> None:
        row = self._make_row(parent, label, tip)
        var = ctk.IntVar(value=int(self._settings.get(key)))
        self._vars[key] = var
        value_lbl = ctk.CTkLabel(row, text=str(var.get()), width=28, font=theme.font(13))
        slider = ctk.CTkSlider(row, from_=lo, to=hi, number_of_steps=hi - lo, variable=var,
                               width=200, command=lambda v: self._save(key, int(v)))
        slider.pack(side="left", padx=(0, 12))
        value_lbl.pack(side="left")
        add_tooltip(slider, tip)
        # keep the number in sync however the value changes (drag, reset, reload)
        var.trace_add("write", lambda *_: value_lbl.configure(text=str(var.get())))

    def _row_checkbox(self, parent: ctk.CTkFrame, key: str, label: str, tip: str = "") -> None:
        var = ctk.BooleanVar(value=bool(self._settings.get(key)))
        self._vars[key] = var
        box = ctk.CTkCheckBox(parent, text=label, variable=var, font=theme.font(13),
                              command=lambda: self._save(key, var.get()))
        box.pack(anchor="w", padx=4, pady=4)
        add_tooltip(box, tip)

    def _browse_folder(self, var: ctk.StringVar) -> None:
        folder = fd.askdirectory(title="Select folder")
        if folder:
            var.set(folder)

    def _browse_file(self, var: ctk.StringVar, title: str = "Select file",
                     filetypes: list | None = None) -> None:
        path = fd.askopenfilename(title=title, filetypes=filetypes or [("All files", "*")])
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
            pass   # half-typed number

    def _apply_theme(self, value: str) -> None:
        self._save("appearance_mode", value.lower())
        ctk.set_appearance_mode(value.lower())

    # ── FFmpeg path handling ──────────────────────────────────────────────────

    def _on_ffmpeg_path_changed(self, value: str) -> None:
        """Persist the user-supplied FFmpeg folder and update the status badge."""
        stripped = value.strip()
        self._save("ffmpeg_bin_dir", stripped)
        if stripped:
            exe = os.path.join(stripped, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
            if os.path.isfile(exe):
                self._save("_ffmpeg_location", stripped)
                self._set_status(self._ffmpeg_status_lbl, True, "✓ Using this folder")
                _log.info("FFmpeg location set by user: %s", stripped)
            else:
                self._set_status(self._ffmpeg_status_lbl, False, "⚠ No ffmpeg in that folder")
        else:
            auto = self._auto_detect_ffmpeg()
            self._save("_ffmpeg_location", auto)
            self._set_status(self._ffmpeg_status_lbl, bool(auto),
                             "✓ Found automatically" if auto else "⚠ Not found")

    def _detect_ffmpeg(self) -> None:
        path = self._auto_detect_ffmpeg()
        if path:
            var = self._vars.get("ffmpeg_bin_dir")
            if var:
                var.set(path)
            self._set_status(self._ffmpeg_status_lbl, True, f"✓ Found: {path}")
        else:
            self._set_status(self._ffmpeg_status_lbl, False, "⚠ Couldn't find FFmpeg")

    @staticmethod
    def _auto_detect_ffmpeg() -> str:
        """Return the auto-detected FFmpeg folder (bundled, PATH, WinGet...), or ''."""
        from utils.tool_setup import find_ffmpeg_dir
        return find_ffmpeg_dir("")

    # ── JS runtime path handling ──────────────────────────────────────────────

    def _on_js_path_changed(self, value: str) -> None:
        stripped = value.strip()
        self._save("js_runtime_override_path", stripped)
        if stripped:
            if os.path.isfile(stripped):
                name = self._detect_runtime_name(stripped)
                self._save("_js_runtime_name", name)
                self._save("_js_runtime_path", stripped)
                self._set_status(self._js_status_lbl, True, f"✓ Using {name}")
                _log.info("JS runtime set by user: %s (%s)", stripped, name)
            else:
                self._set_status(self._js_status_lbl, False, "⚠ File not found")
        else:
            try:
                from utils.tool_setup import find_js_runtime
                result = find_js_runtime("")
                self._save("_js_runtime_name", result.name if result.available else "")
                self._save("_js_runtime_path", result.path or "")
                self._set_status(self._js_status_lbl, result.available,
                                 f"✓ Found {result.name} {result.version}" if result.available
                                 else "⚠ None found")
            except Exception:
                self._set_status(self._js_status_lbl, False, "⚠ Detection failed")

    @staticmethod
    def _detect_runtime_name(path: str) -> str:
        from utils.tool_setup import runtime_name_for
        return runtime_name_for(path)

    # ── Status badges ─────────────────────────────────────────────────────────

    @staticmethod
    def _set_status(label: ctk.CTkLabel, ok: bool, text: str) -> None:
        label.configure(text=text, text_color=theme.OK if ok else theme.BAD)

    def _refresh_tool_status(self) -> None:
        exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        saved = self._settings.get("ffmpeg_bin_dir") or ""
        loc = self._settings.get("_ffmpeg_location") or ""
        if saved and os.path.isfile(os.path.join(saved, exe)):
            self._set_status(self._ffmpeg_status_lbl, True, "✓ Using your folder")
        elif loc and os.path.isfile(os.path.join(loc, exe)):
            self._set_status(self._ffmpeg_status_lbl, True, "✓ Found automatically")
        else:
            self._set_status(self._ffmpeg_status_lbl, False, "⚠ Not found")
        name = self._settings.get("_js_runtime_name") or ""
        if name and name != "none":
            self._set_status(self._js_status_lbl, True, f"✓ Using {name}")
        else:
            self._set_status(self._js_status_lbl, False, "⚠ None found")

    # ── Reload / reset ────────────────────────────────────────────────────────

    def reload_from_settings(self) -> None:
        """Sync every widget with the stored settings (they can also be
        changed from the Downloader tab or the setup dialog)."""
        for key, var in self._vars.items():
            new_val = self._settings.get(key)
            try:
                if isinstance(var, ctk.BooleanVar):
                    new_val = bool(new_val)
                elif isinstance(var, ctk.IntVar):
                    new_val = int(new_val)
                elif key == "appearance_mode":
                    new_val = str(new_val).capitalize()
                else:
                    new_val = str(new_val) if new_val is not None else ""
                if var.get() != new_val:
                    var.set(new_val)
            except Exception:
                pass
        self._refresh_tool_status()

    def _reset_defaults(self) -> None:
        self._settings.reset_to_defaults()
        self.reload_from_settings()
        ctk.set_appearance_mode(str(self._settings.get("appearance_mode")))
        if self._on_changed:
            self._on_changed("__reset__", None)
        _log.info("Settings reset to defaults via UI.")
