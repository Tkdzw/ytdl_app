"""
UI Tab: Batch Queue — live per-item download status with summary footer.
"""
from __future__ import annotations

from typing import Any, Callable, Optional
import customtkinter as ctk

_STATUS_COLORS = {
    "Pending":     "#888888",
    "Downloading": "#4EC9B0",
    "Completed":   "#4CAF50",
    "Failed":      "#FF6B6B",
    "Skipped":     "#DCDCAA",
}

_STATUS_ICONS = {
    "Pending":     "⏳",
    "Downloading": "⬇",
    "Completed":   "✅",
    "Failed":      "❌",
    "Skipped":     "⏭",
}


class BatchQueueTab(ctk.CTkFrame):
    """Live queue table with summary statistics footer."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        on_retry: Optional[Callable[[list[dict]], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._rows: list[ctk.CTkFrame] = []
        self._on_retry = on_retry
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 8))

        ctk.CTkLabel(
            header,
            text="📦  Batch Queue",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(side="left")

        self._retry_btn = ctk.CTkButton(
            header,
            text="↺  Retry Failed",
            width=120, height=32,
            fg_color="#7F4F1A",
            hover_color="#5C3914",
            state="disabled",
            command=self._retry_failed,
        )
        self._retry_btn.pack(side="right")

        ctk.CTkLabel(
            self,
            text="Downloads are processed one at a time for maximum stability.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(anchor="w", padx=24, pady=(0, 12))

        # Column headers
        col_header = ctk.CTkFrame(self, fg_color="#1C1C1C", corner_radius=6)
        col_header.pack(fill="x", padx=24, pady=(0, 4))

        for text, width, expand in [
            ("  #",    40,  False),
            ("URL",    0,   True),
            ("Mode",   90,  False),
            ("Format", 70,  False),
            ("Status", 120, False),
        ]:
            lbl = ctk.CTkLabel(
                col_header, text=text,
                font=ctk.CTkFont(size=12, weight="bold"), anchor="w",
            )
            if expand:
                lbl.pack(side="left", padx=8, pady=8, expand=True, fill="x")
            else:
                lbl.configure(width=width)
                lbl.pack(side="left", padx=8, pady=8)

        # Scrollable rows
        self._scroll = ctk.CTkScrollableFrame(self, label_text="")
        self._scroll.pack(fill="both", expand=True, padx=24, pady=(0, 8))

        self._empty_label = ctk.CTkLabel(
            self._scroll,
            text="No downloads queued yet.\nGo to the Downloader tab to add URLs.",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        self._empty_label.pack(pady=40)

        # Summary footer
        self._footer = ctk.CTkFrame(self, fg_color=("#ECECEC", "#1A1A1A"), corner_radius=6)
        self._footer.pack(fill="x", padx=24, pady=(0, 16))

        self._summary_labels: dict[str, ctk.CTkLabel] = {}
        for key, color in [
            ("total",   None),
            ("done",    "#4CAF50"),
            ("failed",  "#FF6B6B"),
            ("pending", "#888"),
        ]:
            cell = ctk.CTkFrame(self._footer, fg_color="transparent")
            cell.pack(side="left", padx=16, pady=8)
            val = ctk.CTkLabel(cell, text="0", font=ctk.CTkFont(size=16, weight="bold"))
            if color:
                val.configure(text_color=color)
            val.pack()
            ctk.CTkLabel(
                cell, text=key.capitalize(),
                font=ctk.CTkFont(size=10), text_color="gray",
            ).pack()
            self._summary_labels[key] = val

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, items: list[dict[str, Any]]) -> None:
        """Re-render the entire queue from an updated item list."""
        for row in self._rows:
            row.destroy()
        self._rows.clear()

        if not items:
            self._empty_label.pack(pady=40)
            self._update_footer([])
            return

        self._empty_label.pack_forget()

        for idx, item in enumerate(items, start=1):
            row = self._make_row(idx, item)
            row.pack(fill="x", pady=2)
            self._rows.append(row)

        self._update_footer(items)

        # Enable retry button if any failures exist
        has_failed = any(i.get("status") == "Failed" for i in items)
        self._retry_btn.configure(state="normal" if has_failed and self._on_retry else "disabled")
        self._items = items  # store for retry

    # ── Row builder ───────────────────────────────────────────────────────────

    def _make_row(self, idx: int, item: dict[str, Any]) -> ctk.CTkFrame:
        status = item.get("status", "Pending")
        color  = _STATUS_COLORS.get(status, "gray")
        icon   = _STATUS_ICONS.get(status, "")

        is_active = status == "Downloading"
        row_bg    = ("#E8F5E9", "#1F2F1F") if is_active else ("#F5F5F5", "#2A2A2A")

        row = ctk.CTkFrame(self._scroll, fg_color=row_bg, corner_radius=4)

        # Index
        ctk.CTkLabel(
            row, text=f"  {idx}",
            width=40, font=ctk.CTkFont(size=12), anchor="w",
        ).pack(side="left", padx=4, pady=8)

        # URL (truncated)
        url = item.get("url", "")
        short_url = url if len(url) <= 62 else url[:59] + "…"
        ctk.CTkLabel(
            row, text=short_url,
            font=ctk.CTkFont(size=11), anchor="w",
        ).pack(side="left", padx=4, expand=True, fill="x")

        # Mode
        ctk.CTkLabel(
            row, text=item.get("mode", "video").capitalize(),
            width=90, font=ctk.CTkFont(size=12), anchor="w",
        ).pack(side="left", padx=4)

        # Format
        ctk.CTkLabel(
            row, text=item.get("fmt", "—").upper(),
            width=70, font=ctk.CTkFont(size=12), anchor="w",
        ).pack(side="left", padx=4)

        # Status badge with icon
        status_text = f"{icon} {status}" if icon else status
        badge = ctk.CTkLabel(
            row, text=status_text,
            width=120, font=ctk.CTkFont(size=12, weight="bold"),
            text_color=color, anchor="w",
        )
        badge.pack(side="left", padx=8)

        # Animated spinner for active downloads
        if is_active:
            self._start_spinner(badge, status_text)

        return row

    def _start_spinner(self, label: ctk.CTkLabel, base_text: str) -> None:
        """Animate the downloading row with a spinning indicator."""
        frames = ["⬇", "↓", "⬇", "↑"]
        state = {"i": 0}

        def tick() -> None:
            try:
                if not label.winfo_exists():
                    return
                current_text = label.cget("text")
                # Stop if status changed (label text changed away from base)
                if "Downloading" not in current_text:
                    return
                frame = frames[state["i"] % len(frames)]
                label.configure(text=f"{frame} Downloading")
                state["i"] += 1
                label.after(400, tick)
            except Exception:
                pass

        label.after(400, tick)

    # ── Footer ────────────────────────────────────────────────────────────────

    def _update_footer(self, items: list[dict[str, Any]]) -> None:
        total   = len(items)
        done    = sum(1 for i in items if i.get("status") == "Completed")
        failed  = sum(1 for i in items if i.get("status") == "Failed")
        pending = sum(1 for i in items if i.get("status") in ("Pending", "Downloading"))

        self._summary_labels["total"].configure(text=str(total))
        self._summary_labels["done"].configure(text=str(done))
        self._summary_labels["failed"].configure(text=str(failed))
        self._summary_labels["pending"].configure(text=str(pending))

    # ── Retry ─────────────────────────────────────────────────────────────────

    def _retry_failed(self) -> None:
        if self._on_retry and hasattr(self, "_items"):
            failed_items = [i for i in self._items if i.get("status") == "Failed"]
            if failed_items:
                self._on_retry(failed_items)
