"""
UI: Sidebar navigation panel.
"""
from __future__ import annotations

from typing import Callable
import customtkinter as ctk

import app_info

from ui import theme


NAV_ITEMS = [
    ("📥", "Downloader"),
    ("📜", "History"),
    ("⚙️",  "Settings"),
]


class Sidebar(ctk.CTkFrame):
    """Left-side navigation rail with tab buttons."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        on_tab_change: Callable[[str], None],
        on_about: Callable[[], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, width=190, corner_radius=0, **kwargs)
        self.pack_propagate(False)

        self._on_tab_change = on_tab_change
        self._on_about = on_about
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._active_tab: str = NAV_ITEMS[0][1]
        self._update_badge: ctk.CTkLabel | None = None

        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        ctk.CTkLabel(
            self,
            text="YT Downloader",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(24, 4), padx=12)

        ctk.CTkLabel(
            self,
            text=f"Version {app_info.VERSION}",
            font=ctk.CTkFont(size=12),
            text_color=theme.MUTED,
        ).pack(padx=12, pady=(0, 20))

        ctk.CTkFrame(self, height=1, fg_color=theme.DIVIDER).pack(fill="x", padx=12, pady=(0, 16))

        for icon, label in NAV_ITEMS:
            btn = ctk.CTkButton(
                self,
                text=f"  {icon}  {label}",
                anchor="w",
                height=42,
                fg_color="transparent",
                text_color=("gray20", "gray80"),
                hover_color=theme.HOVER,
                font=ctk.CTkFont(size=14),
                command=lambda t=label: self._activate(t),
            )
            btn.pack(fill="x", padx=10, pady=2)
            self._buttons[label] = btn

        self._activate(self._active_tab)

        # ── Bottom area ───────────────────────────────────────────────────────
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=10, pady=12)

        self._update_badge = ctk.CTkLabel(
            bottom,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=theme.WARN,
        )
        self._update_badge.pack(pady=(0, 6))

        ctk.CTkButton(
            bottom,
            text="ℹ  About",
            height=32,
            fg_color="transparent",
            text_color=theme.MUTED,
            hover_color=theme.HOVER,
            font=ctk.CTkFont(size=12),
            command=self._show_about,
        ).pack(fill="x")

        ctk.CTkLabel(
            bottom,
            text=f"by {app_info.DEVELOPER}",
            font=ctk.CTkFont(size=12),
            text_color=theme.MUTED,
        ).pack(pady=(4, 0))

    # ── Public ────────────────────────────────────────────────────────────────

    def show_update_badge(self, installed: str, latest: str) -> None:
        """Display a subtle update hint in the sidebar."""
        if self._update_badge:
            self._update_badge.configure(text=f"yt-dlp {latest} available")

    def select(self, tab: str) -> None:
        """Switch tabs programmatically (keyboard shortcuts)."""
        if tab in self._buttons:
            self._activate(tab)

    # ── State ─────────────────────────────────────────────────────────────────

    def _activate(self, tab: str) -> None:
        self._active_tab = tab
        for name, btn in self._buttons.items():
            if name == tab:
                btn.configure(
                    fg_color=("gray75", "#1F6AA5"),
                    text_color=("gray10", "white"),
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=("gray20", "gray80"),
                )
        self._on_tab_change(tab)

    def _show_about(self) -> None:
        if self._on_about:
            self._on_about()
