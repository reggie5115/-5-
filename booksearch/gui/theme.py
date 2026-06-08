"""
theme.py
--------
Centralized colors, fonts, and a few helper widgets so the whole app has a
consistent, clean look. Designed for a soft, modern "warm library" palette.
"""

import tkinter as tk
from tkinter import font as tkfont


class Theme:
    # Palette ---------------------------------------------------------- #
    BG = "#F5F1E8"            # warm paper background
    SURFACE = "#FFFFFF"       # cards / panels
    SURFACE_ALT = "#FAF6EC"   # subtle alternate surface
    SIDEBAR = "#2C2A28"       # deep charcoal-brown sidebar
    SIDEBAR_HOVER = "#3D3A36"
    SIDEBAR_ACTIVE = "#8C6A4A"

    PRIMARY = "#8C6A4A"       # leather brown accent
    PRIMARY_DARK = "#6E5238"
    PRIMARY_LIGHT = "#B7916B"
    ACCENT = "#3E7C6A"        # muted green for positive actions

    TEXT = "#2C2A28"          # near-black warm
    TEXT_MUTED = "#7A746B"
    TEXT_ON_DARK = "#F5F1E8"
    TEXT_ON_PRIMARY = "#FFFFFF"

    BORDER = "#E3DCCD"
    DANGER = "#B5524A"
    STAR = "#D9A441"

    # Fonts ------------------------------------------------------------ #
    @staticmethod
    def fonts():
        return {
            "title": tkfont.Font(family="Georgia", size=22, weight="bold"),
            "h1": tkfont.Font(family="Georgia", size=17, weight="bold"),
            "h2": tkfont.Font(family="Helvetica", size=13, weight="bold"),
            "body": tkfont.Font(family="Helvetica", size=11),
            "body_bold": tkfont.Font(family="Helvetica", size=11, weight="bold"),
            "small": tkfont.Font(family="Helvetica", size=10),
            "tiny": tkfont.Font(family="Helvetica", size=9),
            "chat": tkfont.Font(family="Helvetica", size=11),
            "sidebar": tkfont.Font(family="Helvetica", size=12, weight="bold"),
        }


class HoverButton(tk.Label):
    """A flat, rounded-feel button built on a Label for full color control."""

    def __init__(self, master, text, command=None,
                 bg=Theme.PRIMARY, fg=Theme.TEXT_ON_PRIMARY,
                 hover_bg=Theme.PRIMARY_DARK, font=None, padx=16, pady=8,
                 **kw):
        super().__init__(master, text=text, bg=bg, fg=fg, font=font,
                         padx=padx, pady=pady, cursor="hand2", **kw)
        self._bg = bg
        self._hover_bg = hover_bg
        self._command = command
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda e: self.config(bg=self._hover_bg))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))

    def _on_click(self, _event):
        if self._command:
            self._command()

    def set_command(self, command):
        self._command = command

    def set_colors(self, bg, hover_bg):
        self._bg = bg
        self._hover_bg = hover_bg
        self.config(bg=bg)


def make_scrollable(parent, bg=Theme.BG):
    """
    Create a vertically scrollable frame. Returns (outer_frame, inner_frame).
    Put content into inner_frame; outer_frame is what you pack/grid.
    """
    outer = tk.Frame(parent, bg=bg)
    canvas = tk.Canvas(outer, bg=bg, highlightthickness=0, bd=0)
    scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=bg)

    inner.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    window = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    def _resize(event):
        canvas.itemconfig(window, width=event.width)
    canvas.bind("<Configure>", _resize)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Mousewheel support (cross-platform).
    def _on_mousewheel(event):
        if event.num == 4:
            canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            canvas.yview_scroll(1, "units")
        else:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_wheel(_):
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_mousewheel)
        canvas.bind_all("<Button-5>", _on_mousewheel)

    def _unbind_wheel(_):
        canvas.unbind_all("<MouseWheel>")
        canvas.unbind_all("<Button-4>")
        canvas.unbind_all("<Button-5>")

    inner.bind("<Enter>", _bind_wheel)
    inner.bind("<Leave>", _unbind_wheel)

    return outer, inner
