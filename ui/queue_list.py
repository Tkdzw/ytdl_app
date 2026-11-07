"""
UI: the download list shown on the home screen.

One row per link: thumbnail, title, what will be saved (format/quality,
length), a status in words (not just colour), a progress bar while
downloading, and the buttons that make sense for that row's state:

    Ready        → Remove
    Downloading  → Stop
    Completed    → Play · Open folder · Remove
    Failed       → Retry · Details · Remove
    Cancelled    → Retry · Remove
"""
from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from ui import theme

from engine.download_queue import (
    CANCELLED, COMPLETED, DOWNLOADING, FAILED, READY, QueueItem,
)

_STATUS_STYLE = {
    READY:       ("Waiting",          theme.MUTED),
    DOWNLOADING: ("Downloading",      theme.INFO),
    COMPLETED:   ("✓ Done",           theme.OK),
    FAILED:      ("✗ Failed",         theme.BAD),
    CANCELLED:   ("Stopped",          theme.WARN),
}

ActionCallback = Callable[[str, int], None]   # (action, item_id)


def fmt_duration(seconds: Optional[float]) -> str:
    if not seconds:
        return ""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def describe_request(item: QueueItem) -> str:
    r = item.request
    if r.mode == "audio":
        parts = [f"MP3 · {r.audio_quality} kbps"]
    else:
        q = "Best quality" if r.video_quality.lower() == "best" else r.video_quality
        parts = [f"{r.video_format.upper()} · {q}"]
    if item.duration:
        parts.append(fmt_duration(item.duration))
    return " · ".join(parts)


class _Row(ctk.CTkFrame):
    def __init__(self, master, item: QueueItem, on_action: ActionCallback) -> None:
        super().__init__(master, corner_radius=8, fg_color=theme.ROW_BG)
        self._item_id = item.id
        self._on_action = on_action
        self._shown_status: Optional[str] = None

        self._thumb = ctk.CTkLabel(
            self, text="🎬" if item.request.mode == "video" else "🎵",
            font=ctk.CTkFont(size=22), text_color=theme.MUTED,
            width=96, height=54, corner_radius=4,
            fg_color=theme.PANEL_BG,
        )
        self._thumb.grid(row=0, column=0, rowspan=3, padx=(10, 12), pady=10, sticky="w")

        self._title = ctk.CTkLabel(self, text="", anchor="w",
                                   font=ctk.CTkFont(size=13, weight="bold"))
        self._title.grid(row=0, column=1, sticky="ew", pady=(10, 0))

        self._sub = ctk.CTkLabel(self, text="", anchor="w",
                                 font=ctk.CTkFont(size=12), text_color=theme.MUTED)
        self._sub.grid(row=1, column=1, sticky="ew")

        self._detail = ctk.CTkLabel(self, text="", anchor="w", justify="left",
                                    font=ctk.CTkFont(size=12), wraplength=560)
        self._detail.grid(row=2, column=1, sticky="ew", pady=(0, 10))
        # keep long messages wrapped inside the text column as the window resizes
        self._detail.bind("<Configure>", lambda e: self._detail.configure(
            wraplength=max(300, e.width - 10)))

        self._bar = ctk.CTkProgressBar(self, height=6)
        self._bar.set(0)

        self._buttons = ctk.CTkFrame(self, fg_color="transparent")
        self._buttons.grid(row=0, column=2, rowspan=3, padx=10, sticky="e")

        self.grid_columnconfigure(1, weight=1)
        self.update_item(item)

    # ── Updates ───────────────────────────────────────────────────────────────

    def set_thumbnail(self, image) -> None:
        if image is not None:
            self._thumb.configure(image=image, text="")

    def update_item(self, item: QueueItem) -> None:
        title = item.display_title
        self._title.configure(text=title if len(title) <= 80 else title[:77] + "…")

        label, color = _STATUS_STYLE.get(item.status, (item.status, "gray"))
        sub = describe_request(item)
        self._sub.configure(text=f"{label}   ·   {sub}" if sub else label, text_color=color)

        if item.status == DOWNLOADING and item.stage == "processing":
            # FFmpeg is working; say what it is doing so 100% doesn't look frozen
            text = ("Converting to MP3…" if item.request.mode == "audio"
                    else "Merging video and audio…")
            self._detail.configure(text=text, text_color=theme.WARN)
            self._bar.set(1.0)
        elif item.status == DOWNLOADING:
            bits = [f"{item.percent:.0f}%"]
            if item.speed and item.speed != "—":
                bits.append(item.speed)
            if item.eta and item.eta != "—":
                bits.append(f"{item.eta} left")
            self._detail.configure(text="   ".join(bits), text_color=theme.MUTED)
            self._bar.set(item.percent / 100)
        elif item.status == FAILED:
            self._detail.configure(text=f"{item.error}\n{item.hint}".strip(),
                                   text_color=theme.BAD)
        elif item.status == COMPLETED and item.filepaths:
            import os
            name = os.path.basename(item.filepaths[0])
            more = f"  (+{len(item.filepaths) - 1} more)" if len(item.filepaths) > 1 else ""
            self._detail.configure(text=f"Saved as {name}{more}",
                                   text_color=theme.MUTED)
        else:
            self._detail.configure(text="")

        if item.status != self._shown_status:
            self._shown_status = item.status
            if item.status == DOWNLOADING:
                self._bar.grid(row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 8))
            else:
                self._bar.grid_remove()
            self._rebuild_buttons(item.status)

    # Which buttons each state shows (button keys, left to right)
    _ACTIONS = {
        READY:       ["remove_text"],
        DOWNLOADING: ["cancel"],
        COMPLETED:   ["play", "open", "remove"],
        FAILED:      ["retry", "details", "remove"],
        CANCELLED:   ["retry", "remove"],
    }
    _BUTTONS = {   # key: (label, action, primary)
        "remove_text": ("Remove", "remove", False),
        "cancel":      ("Stop", "cancel", False),
        "play":        ("▶ Play", "play", True),
        "open":        ("Open folder", "open", False),
        "retry":       ("↺ Retry", "retry", True),
        "details":     ("Details", "details", False),
        "remove":      ("✕", "remove", False),
    }

    def _rebuild_buttons(self, status: str) -> None:
        # Buttons are created once and only shown/hidden: destroying CTk
        # buttons while resize events are pending makes Tk log errors.
        if not hasattr(self, "_btn_widgets"):
            self._btn_widgets = {}
            for key, (text, action, primary) in self._BUTTONS.items():
                btn = ctk.CTkButton(
                    self._buttons, text=text, height=30,
                    width=36 if text == "✕" else 92,
                    font=ctk.CTkFont(size=12),
                    command=lambda a=action: self._on_action(a, self._item_id),
                )
                if not primary:
                    btn.configure(fg_color="transparent", border_width=1, text_color=theme.TEXT)
                self._btn_widgets[key] = btn
        for btn in self._btn_widgets.values():
            btn.pack_forget()
        for key in self._ACTIONS.get(status, []):
            self._btn_widgets[key].pack(side="left", padx=3)


class QueueList(ctk.CTkScrollableFrame):
    """Scrollable list of _Row widgets kept in sync with the queue."""

    def __init__(self, master, on_action: ActionCallback, **kwargs) -> None:
        super().__init__(master, label_text="", **kwargs)
        self._on_action = on_action
        self._rows: dict[int, _Row] = {}
        self._thumbs: dict[int, object] = {}
        self._empty = ctk.CTkLabel(
            self,
            text="Your downloads will appear here.\n"
                 "Paste one or more links above, then click “Start download”.",
            font=ctk.CTkFont(size=13), text_color=theme.MUTED, justify="center",
        )
        self._empty.pack(pady=30)

    def sync(self, items: list[QueueItem]) -> None:
        ids = {i.id for i in items}
        for item_id in [i for i in self._rows if i not in ids]:
            row = self._rows.pop(item_id)
            row.pack_forget()
            # destroy after pending resize events have run (avoids Tk errors)
            row.after(300, row.destroy)
            self._thumbs.pop(item_id, None)
        for item in items:
            row = self._rows.get(item.id)
            if row is None:
                row = _Row(self, item, self._on_action)
                row.pack(fill="x", pady=3, padx=2)
                self._rows[item.id] = row
                if item.id in self._thumbs:
                    row.set_thumbnail(self._thumbs[item.id])
            else:
                row.update_item(item)
        if items:
            self._empty.pack_forget()
        else:
            self._empty.pack(pady=30)

    def update_item(self, item: QueueItem) -> None:
        row = self._rows.get(item.id)
        if row:
            row.update_item(item)

    def set_thumbnail(self, item_id: int, image) -> None:
        self._thumbs[item_id] = image
        row = self._rows.get(item_id)
        if row:
            row.set_thumbnail(image)
