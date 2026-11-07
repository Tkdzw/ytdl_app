"""
UI Tab: History — full-featured download history viewer.
Features: stats bar, live search/filter, per-row open-folder, CSV export.
"""
from __future__ import annotations

import csv
import os
import subprocess
import sys
import tkinter.filedialog as fd
from typing import Any

import customtkinter as ctk

from ui import theme
from ui.tooltip import add_tooltip

from utils.history_manager import HistoryManager
from utils.logger import AppLogger

_log = AppLogger.get_logger(__name__)

_STATUS_COLORS = {
    "success": theme.OK,
    "failed":  theme.BAD,
}

_STATUS_FILTER_OPTIONS = ["All", "Success", "Failed"]


class HistoryTab(ctk.CTkFrame):
    """Browse, search, filter, and export download history."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        history_manager: HistoryManager,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._history = history_manager
        self._all_records: list[dict[str, Any]] = []
        self._rows: list[ctk.CTkFrame] = []
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ── Header row ────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 8))

        ctk.CTkLabel(
            header,
            text="📜  Download History",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(side="left")

        for text, cmd, color in [
            ("🗑 Clear All", self._clear_history, "danger"),
            ("⬇ Export CSV",  self._export_csv,   "transparent"),
            ("🔄 Refresh",     self.refresh,        "transparent"),
        ]:
            danger = color == "danger"
            ctk.CTkButton(
                header, text=text, width=120, height=32,
                fg_color=theme.STOP_BTN if danger else "transparent",
                hover_color=theme.STOP_HOVER if danger else theme.HOVER,
                text_color="white" if danger else theme.TEXT,
                border_width=0 if danger else 1,
                font=theme.font(13),
                command=cmd,
            ).pack(side="right", padx=4)

        # ── Stats bar ─────────────────────────────────────────────────────────
        self._stats_frame = ctk.CTkFrame(self, fg_color=theme.PANEL_BG, corner_radius=8)
        self._stats_frame.pack(fill="x", padx=24, pady=(0, 12))
        self._stat_labels: dict[str, ctk.CTkLabel] = {}

        for key in ("total", "succeeded", "failed"):
            cell = ctk.CTkFrame(self._stats_frame, fg_color="transparent")
            cell.pack(side="left", padx=20, pady=10)
            val_lbl = ctk.CTkLabel(cell, text="0", font=ctk.CTkFont(size=20, weight="bold"))
            val_lbl.pack()
            colors = {"total": None, "succeeded": theme.OK, "failed": theme.BAD}
            if colors[key]:
                val_lbl.configure(text_color=colors[key])
            ctk.CTkLabel(
                cell, text=key.capitalize(),
                font=ctk.CTkFont(size=12), text_color=theme.MUTED,
            ).pack()
            self._stat_labels[key] = val_lbl

        # ── Search + filter row ───────────────────────────────────────────────
        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.pack(fill="x", padx=24, pady=(0, 8))

        ctk.CTkLabel(filter_row, text="Search:", font=ctk.CTkFont(size=13)).pack(side="left")
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())
        ctk.CTkEntry(
            filter_row,
            textvariable=self._search_var,
            placeholder_text="Filter by title or URL…",
            width=280,
        ).pack(side="left", padx=(8, 20))

        ctk.CTkLabel(filter_row, text="Status:", font=ctk.CTkFont(size=13)).pack(side="left")
        self._status_filter_var = ctk.StringVar(value="All")
        ctk.CTkSegmentedButton(
            filter_row,
            values=_STATUS_FILTER_OPTIONS,
            variable=self._status_filter_var,
            width=200,
            command=lambda _: self._apply_filter(),
        ).pack(side="left", padx=8)

        # ── Column headers ────────────────────────────────────────────────────
        col_header = ctk.CTkFrame(self, fg_color=theme.HEADER_BG, corner_radius=6)
        col_header.pack(fill="x", padx=24, pady=(0, 4))

        for col, width, expand in [
            ("  Title", 0,   True),
            ("Format",  70,  False),
            ("Date",    160, False),
            ("Status",  80,  False),
            ("",        42,  False),   # open-folder button column
        ]:
            lbl = ctk.CTkLabel(
                col_header, text=col,
                font=ctk.CTkFont(size=12, weight="bold"), anchor="w",
            )
            if expand:
                lbl.pack(side="left", padx=4, pady=8, expand=True, fill="x")
            else:
                lbl.configure(width=width)
                lbl.pack(side="left", padx=4, pady=8)

        # ── Scrollable list ───────────────────────────────────────────────────
        self._scroll = ctk.CTkScrollableFrame(self, label_text="")
        self._scroll.pack(fill="both", expand=True, padx=24, pady=(0, 20))

        self._empty_label = ctk.CTkLabel(
            self._scroll,
            text="No download history yet.",
            font=ctk.CTkFont(size=13),
            text_color=theme.MUTED,
        )
        self._empty_label.pack(pady=40)

        self.refresh()

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload from disk and re-render."""
        self._all_records = self._history.load_all()
        self._update_stats()
        self._apply_filter()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _update_stats(self) -> None:
        s = self._history.stats()
        self._stat_labels["total"].configure(text=str(s["total"]))
        self._stat_labels["succeeded"].configure(text=str(s["succeeded"]))
        self._stat_labels["failed"].configure(text=str(s["failed"]))

    def _apply_filter(self) -> None:
        query   = self._search_var.get().lower().strip()
        status  = self._status_filter_var.get().lower()  # "all" | "success" | "failed"

        filtered = [
            r for r in self._all_records
            if self._matches(r, query, status)
        ]
        self._render_rows(filtered)

    @staticmethod
    def _matches(record: dict, query: str, status_filter: str) -> bool:
        if status_filter != "all":
            if record.get("status", "") != status_filter:
                return False
        if query:
            haystack = (
                record.get("title", "").lower()
                + record.get("url", "").lower()
            )
            if query not in haystack:
                return False
        return True

    def _render_rows(self, records: list[dict[str, Any]]) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()

        if not records:
            self._empty_label.pack(pady=40)
            return

        self._empty_label.pack_forget()

        for record in records:
            row = self._make_row(record)
            row.pack(fill="x", pady=2)
            self._rows.append(row)

    def _make_row(self, record: dict) -> ctk.CTkFrame:
        status       = record.get("status", "")
        status_color = _STATUS_COLORS.get(status, theme.MUTED)
        filepath     = record.get("filepath", "")

        row = ctk.CTkFrame(
            self._scroll,
            fg_color=theme.ROW_BG,
            corner_radius=4,
        )

        # Title
        title = record.get("title", "Unknown")
        title_short = title if len(title) <= 58 else title[:55] + "…"
        ctk.CTkLabel(
            row, text=f"  {title_short}",
            font=ctk.CTkFont(size=12), anchor="w",
        ).pack(side="left", padx=4, pady=8, expand=True, fill="x")

        # Format
        ctk.CTkLabel(
            row, text=record.get("format", "—").upper(),
            width=70, font=ctk.CTkFont(size=12), anchor="w",
        ).pack(side="left", padx=4)

        # Date
        ctk.CTkLabel(
            row, text=record.get("date", "—"),
            width=160, font=ctk.CTkFont(size=12),
            text_color=theme.MUTED, anchor="w",
        ).pack(side="left", padx=4)

        # Status badge
        # status in words + symbol, not colour alone
        ctk.CTkLabel(
            row, text={"success": "✓ Done", "failed": "✗ Failed"}.get(status, status.capitalize()),
            width=80, font=ctk.CTkFont(size=12, weight="bold"),
            text_color=status_color, anchor="w",
        ).pack(side="left", padx=4)

        # Open-folder button
        folder_exists = filepath and os.path.exists(os.path.dirname(os.path.abspath(filepath)))
        folder_btn = ctk.CTkButton(
            row, text="📂", width=36, height=28,
            font=ctk.CTkFont(size=13),
            fg_color="transparent", text_color=theme.TEXT,
            hover_color=theme.HOVER,
            state="normal" if folder_exists else "disabled",
            command=lambda p=filepath: self._open_folder(p),
        )
        folder_btn.pack(side="left", padx=(0, 6))
        add_tooltip(folder_btn, "Open the folder this file was saved in"
                    if folder_exists else "The folder no longer exists")

        return row

    # ── Actions ───────────────────────────────────────────────────────────────

    def _clear_history(self) -> None:
        # Destructive and can't be undone, so ask first. (Downloaded files
        # are not touched — only this list.)
        from tkinter import messagebox
        count = len(self._all_records)
        if not count:
            return
        if not messagebox.askyesno(
            "Clear history?",
            f"Remove all {count} entries from your download history?\n\n"
            "Your downloaded files are NOT deleted — only this list. "
            "This can't be undone.",
            icon="warning", default="no", parent=self.winfo_toplevel(),
        ):
            return
        self._history.clear()
        self.refresh()
        _log.info("History cleared by user.")

    def _export_csv(self) -> None:
        path = fd.asksaveasfilename(
            title="Export history as CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="ytdl_history.csv",
        )
        if not path:
            return
        try:
            records = self._history.load_all()
            fieldnames = ["title", "url", "format", "date", "status", "filepath"]
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(records)
            _log.info("History exported to %s", path)
        except OSError as exc:
            _log.error("CSV export failed: %s", exc)

    @staticmethod
    def _open_folder(filepath: str) -> None:
        folder = os.path.dirname(os.path.abspath(filepath))
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as exc:
            _log.error("Could not open folder %s: %s", folder, exc)
