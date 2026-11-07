"""
UI: small hover tooltips.

``add_tooltip(widget, text)`` shows *text* in a little box after the pointer
rests on the widget for half a second, and hides it when the pointer leaves
or a key/click happens. Works with CustomTkinter widgets (it binds to the
widget and its inner canvas/label children, which receive the events).
"""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ui import theme

_DELAY_MS = 500


class _Tooltip:
    def __init__(self, widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self._job = None
        self._tip: tk.Toplevel | None = None
        for target in self._targets(widget):
            for seq, fn in (("<Enter>", self._schedule), ("<Leave>", self._hide),
                            ("<ButtonPress>", self._hide),
                            ("<FocusIn>", self._schedule),      # keyboard users
                            ("<FocusOut>", self._hide)):
                try:
                    target.bind(seq, fn, add="+")
                except NotImplementedError:
                    # some CTk widgets (e.g. CTkSegmentedButton) refuse .bind();
                    # bind on the underlying Tk widget instead
                    tk.Misc.bind(target, seq, fn, add="+")

    @staticmethod
    def _targets(widget) -> list:
        out = [widget]
        for child in widget.winfo_children():
            out.extend(_Tooltip._targets(child))
        return out

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._job = self.widget.after(_DELAY_MS, self._show)

    def _cancel(self) -> None:
        if self._job:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _show(self) -> None:
        if self._tip or not self.widget.winfo_exists():
            return
        dark = ctk.get_appearance_mode() == "Dark"
        bg, fg = ("#2B2B2B", "#F0F0F0") if dark else ("#FFFFE8", "#1A1A1A")
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)
        label = tk.Label(
            tip, text=self.text, justify="left", wraplength=360,
            background=bg, foreground=fg, relief="solid", borderwidth=1,
            font=("Segoe UI", 10), padx=8, pady=5,
        )
        label.pack()
        tip.wm_geometry(f"+{x}+{y}")
        self._tip = tip

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


def add_tooltip(widget, text: str) -> None:
    """Attach a hover/focus tooltip to *widget*."""
    if text:
        widget._tooltip = _Tooltip(widget, text)   # keep a reference
