"""
UI: shared colours and font sizes.

Every colour is a (light, dark) pair so it works in both appearance modes,
and each text colour is chosen to reach at least WCAG AA contrast (4.5:1)
on the app's backgrounds in that mode. Use these instead of hex literals or
Tk's "gray" (which is #BEBEBE — unreadable on light backgrounds).
"""
from __future__ import annotations

import customtkinter as ctk

# ── Text ──────────────────────────────────────────────────────────────────────
TEXT    = ("gray10", "gray92")      # normal text
MUTED   = ("gray30", "gray68")      # secondary text / hints
OK      = ("#155C26", "#5CC26B")    # success
BAD     = ("#A3221B", "#FF7B72")    # errors
WARN    = ("#664B00", "#E3C26B")    # warnings
INFO    = ("#07594A", "#4EC9B0")    # in progress

# ── Surfaces ──────────────────────────────────────────────────────────────────
DIVIDER    = ("gray78", "#3A3A3A")
HEADER_BG  = ("gray82", "#1C1C1C")  # table column headers
ROW_BG     = ("gray95", "#262626")  # list rows
PANEL_BG   = ("gray90", "#1E1E1E")  # stat bars, info panels
CARD_BG    = ("gray88", "#1F2230")  # grouped settings
HOVER      = ("gray82", "#2E3133")

BANNER_OK   = ("#DDF1E1", "#1F3324")
BANNER_WARN = ("#FBEFD6", "#3A311C")
BANNER_BAD  = ("#F9DEDC", "#3A1F1F")

# Action buttons (white text on these in both modes)
GO_BTN,   GO_HOVER   = ("#1A7F3C", "#1A7F3C"), ("#145C2C", "#145C2C")
STOP_BTN, STOP_HOVER = ("#9B2226", "#7F1A1A"), ("#7A1A1D", "#5C1414")

# ── Fonts ─────────────────────────────────────────────────────────────────────
MIN_FONT = 12   # nothing smaller than this anywhere


def apply_theme_overrides() -> None:
    """
    Adjust CustomTkinter's built-in "blue" theme for contrast. Call once,
    right after ``ctk.set_default_color_theme("blue")`` and before any
    widget is created.

    * Buttons/dropdowns: the light-mode blue (#3B8ED0) gives white text only
      ~3.4:1, so both modes use the darker #1F6AA5 (~5.6:1).
    * Segmented buttons: light mode used white text on light grey (~2:1);
      use dark text on light grey, with a pale-blue selected segment.
    * Disabled text: light mode's gray74 was barely visible.
    """
    t = ctk.ThemeManager.theme
    blue, blue_hover = ["#1F6AA5", "#1F6AA5"], ["#144870", "#144870"]
    t["CTkButton"].update(fg_color=blue, hover_color=blue_hover,
                          text_color=["#FFFFFF", "#F2F5F8"],
                          text_color_disabled=["gray45", "gray58"])
    t["CTkOptionMenu"].update(fg_color=blue, button_color=["#144870", "#144870"],
                              button_hover_color=["#0E3554", "#0E3554"],
                              text_color=["#FFFFFF", "#F2F5F8"])
    t["CTkSegmentedButton"].update(
        fg_color=["gray80", "gray29"], unselected_color=["gray80", "gray29"],
        unselected_hover_color=["gray72", "gray41"],
        selected_color=["#A9CBF0", "#1F6AA5"], selected_hover_color=["#93BCEA", "#144870"],
        text_color=["gray8", "#F2F5F8"], text_color_disabled=["gray45", "gray58"])


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=max(size, MIN_FONT), weight=weight)


def divider(parent, **pack) -> ctk.CTkFrame:
    line = ctk.CTkFrame(parent, height=1, fg_color=DIVIDER)
    line.pack(fill="x", **pack)
    return line
