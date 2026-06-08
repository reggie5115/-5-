"""
widgets.py
----------
Reusable composite widgets: the BookCard (used in the library and
recommendation views) and a small star-rating display.
"""

import tkinter as tk
from typing import Dict, Any, Callable, Optional

from gui.theme import Theme, HoverButton


def _truncate(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "\u2026"


class Chip(tk.Label):
    """A small rounded-looking tag for genres/moods."""

    def __init__(self, master, text, fg=Theme.PRIMARY_DARK,
                 bg=Theme.SURFACE_ALT, fonts=None):
        super().__init__(
            master, text=f" {text} ", bg=bg, fg=fg,
            font=fonts["tiny"] if fonts else None,
            padx=6, pady=2, bd=0,
        )


class BookCard(tk.Frame):
    """
    A card showing a book's title, author, genres, moods and a contextual
    action. Two modes:
      * mode='library'  -> shows a "Rate" button.
      * mode='recommend'-> shows the match % and reasons.
    """

    def __init__(self, master, book: Dict[str, Any], fonts: Dict[str, Any],
                 mode: str = "library",
                 on_action: Optional[Callable[[Dict[str, Any]], None]] = None):
        super().__init__(master, bg=Theme.SURFACE, bd=0,
                         highlightbackground=Theme.BORDER,
                         highlightthickness=1)
        self.book = book
        self.fonts = fonts
        self.mode = mode
        self.on_action = on_action
        self._build()

    def _build(self):
        pad = 14
        container = tk.Frame(self, bg=Theme.SURFACE)
        container.pack(fill="both", expand=True, padx=pad, pady=pad)

        # --- Header row: title + (match badge or action) -------------- #
        header = tk.Frame(container, bg=Theme.SURFACE)
        header.pack(fill="x")

        title_area = tk.Frame(header, bg=Theme.SURFACE)
        title_area.pack(side="left", fill="x", expand=True)

        tk.Label(
            title_area, text=_truncate(self.book.get("title", "Untitled"), 60),
            bg=Theme.SURFACE, fg=Theme.TEXT, font=self.fonts["h2"],
            anchor="w", justify="left", wraplength=360,
        ).pack(anchor="w")

        author = self.book.get("author") or "Unknown author"
        meta = author
        if self.book.get("publish_year"):
            meta += f"  \u00b7  {self.book['publish_year']}"
        if self.book.get("page_count"):
            meta += f"  \u00b7  {self.book['page_count']} pp"
        tk.Label(
            title_area, text=_truncate(meta, 70), bg=Theme.SURFACE,
            fg=Theme.TEXT_MUTED, font=self.fonts["small"], anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        if self.mode == "recommend" and self.book.get("match") is not None:
            badge = tk.Label(
                header, text=f"{self.book['match']:.0f}%",
                bg=Theme.ACCENT, fg="white", font=self.fonts["body_bold"],
                padx=10, pady=6,
            )
            badge.pack(side="right", anchor="n")
        elif self.mode == "library":
            btn = HoverButton(
                header, text="Rate", command=self._fire,
                bg=Theme.PRIMARY, hover_bg=Theme.PRIMARY_DARK,
                font=self.fonts["small"], padx=14, pady=6,
            )
            btn.pack(side="right", anchor="n")

        # --- Genre / mood chips --------------------------------------- #
        tags = tk.Frame(container, bg=Theme.SURFACE)
        tags.pack(fill="x", pady=(10, 0))

        shown = 0
        for g in self.book.get("genres", [])[:4]:
            Chip(tags, g, fg=Theme.PRIMARY_DARK, bg=Theme.SURFACE_ALT,
                 fonts=self.fonts).pack(side="left", padx=(0, 5))
            shown += 1
        for m in self.book.get("moods", [])[:3]:
            Chip(tags, m, fg=Theme.ACCENT, bg="#EAF2EF",
                 fonts=self.fonts).pack(side="left", padx=(0, 5))
            shown += 1
        if shown == 0:
            tk.Label(tags, text="no tags yet", bg=Theme.SURFACE,
                     fg=Theme.TEXT_MUTED, font=self.fonts["tiny"]).pack(
                side="left")

        # --- Reasons (recommend mode only) ---------------------------- #
        if self.mode == "recommend" and self.book.get("reasons"):
            reasons = "  \u2022  ".join(self.book["reasons"])
            tk.Label(
                container, text=reasons, bg=Theme.SURFACE,
                fg=Theme.PRIMARY_DARK, font=self.fonts["small"],
                anchor="w", justify="left", wraplength=420,
            ).pack(anchor="w", pady=(10, 0))

        # --- Short description ---------------------------------------- #
        desc = self.book.get("description")
        if desc:
            tk.Label(
                container, text=_truncate(desc, 180), bg=Theme.SURFACE,
                fg=Theme.TEXT_MUTED, font=self.fonts["small"],
                anchor="w", justify="left", wraplength=440,
            ).pack(anchor="w", pady=(8, 0))

    def _fire(self):
        if self.on_action:
            self.on_action(self.book)


class StarRating(tk.Frame):
    """
    A 0..10 rating control rendered as a slider plus a numeric readout and a
    star strip. Calls on_change(value) as the user drags.
    """

    def __init__(self, master, fonts, initial: float = 5.0,
                 on_change: Optional[Callable[[float], None]] = None):
        super().__init__(master, bg=Theme.SURFACE)
        self.fonts = fonts
        self.on_change = on_change
        self.var = tk.DoubleVar(value=initial)

        row = tk.Frame(self, bg=Theme.SURFACE)
        row.pack(fill="x")

        self.scale = tk.Scale(
            row, from_=0, to=10, resolution=1, orient="horizontal",
            variable=self.var, showvalue=False, length=260,
            bg=Theme.SURFACE, fg=Theme.TEXT, troughcolor=Theme.SURFACE_ALT,
            highlightthickness=0, bd=0, sliderrelief="flat",
            activebackground=Theme.PRIMARY, command=self._changed,
        )
        self.scale.pack(side="left")

        self.readout = tk.Label(
            row, text=f"{int(initial)}/10", bg=Theme.SURFACE,
            fg=Theme.PRIMARY_DARK, font=self.fonts["h2"], width=6,
        )
        self.readout.pack(side="left", padx=(12, 0))

        self.stars = tk.Label(self, bg=Theme.SURFACE, fg=Theme.STAR,
                              font=self.fonts["body"])
        self.stars.pack(anchor="w", pady=(4, 0))
        self._render_stars(initial)

    def _changed(self, _val):
        v = self.var.get()
        self.readout.config(text=f"{int(v)}/10")
        self._render_stars(v)
        if self.on_change:
            self.on_change(v)

    def _render_stars(self, v):
        full = int(round(v / 2))  # 10 -> 5 stars
        self.stars.config(text="\u2605" * full + "\u2606" * (5 - full))

    def value(self) -> float:
        return self.var.get()
