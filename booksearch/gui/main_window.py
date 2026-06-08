"""
main_window.py
--------------
The main application window. A left sidebar switches between four views:

  * Library      - browse/search the local book database, rate books.
  * My Ratings   - see and manage the books you've scored.
  * Recommend    - generate recommendations from your ratings.
  * Add a Book   - look up a book online if it's not in the database.

The Recommend view also hosts the AI librarian chatbot, which introduces the
recommendations and answers follow-up questions.

All network/CPU work happens on background threads; results are marshalled
back onto the Tk main loop with `after()` so the UI never freezes.
"""

import threading
import queue
import tkinter as tk
from tkinter import messagebox
from typing import List, Dict, Any, Optional

from core.app_controller import AppController
from gui.theme import Theme, HoverButton, make_scrollable
from gui.widgets import BookCard, StarRating


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.controller = AppController()
        self.fonts = Theme.fonts()

        # A queue lets background threads ask the UI thread to run callbacks.
        self._ui_queue: "queue.Queue" = queue.Queue()
        self.root.after(80, self._drain_queue)

        self.current_view = None
        self.nav_buttons: Dict[str, HoverButton] = {}

        self._setup_window()
        self._build_layout()

        # Decide whether we need to populate the library on first launch.
        if self.controller.needs_seeding():
            self._show_view("library")
            self.root.after(300, self._seed_first_run)
        else:
            self._show_view("library")

    # ------------------------------------------------------------------ #
    # Window chrome
    # ------------------------------------------------------------------ #
    def _setup_window(self):
        self.root.title("Inkwell \u2014 Book Discovery")
        self.root.configure(bg=Theme.BG)
        self.root.geometry("1080x720")
        self.root.minsize(940, 620)

    def _build_layout(self):
        # Sidebar -------------------------------------------------------#
        self.sidebar = tk.Frame(self.root, bg=Theme.SIDEBAR, width=210)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        brand = tk.Frame(self.sidebar, bg=Theme.SIDEBAR)
        brand.pack(fill="x", pady=(26, 30), padx=20)
        tk.Label(brand, text="\U0001F4D6", bg=Theme.SIDEBAR,
                 fg=Theme.TEXT_ON_DARK, font=("Helvetica", 26)).pack(anchor="w")
        tk.Label(brand, text="Inkwell", bg=Theme.SIDEBAR,
                 fg=Theme.TEXT_ON_DARK, font=self.fonts["title"]).pack(
            anchor="w")
        tk.Label(brand, text="your book companion", bg=Theme.SIDEBAR,
                 fg=Theme.PRIMARY_LIGHT, font=self.fonts["tiny"]).pack(
            anchor="w")

        nav_items = [
            ("library", "\U0001F4DA  Library"),
            ("ratings", "\u2B50  My Ratings"),
            ("recommend", "\u2728  Recommend"),
            ("add", "\u2795  Add a Book"),
        ]
        for key, label in nav_items:
            btn = HoverButton(
                self.sidebar, text=label,
                command=lambda k=key: self._show_view(k),
                bg=Theme.SIDEBAR, hover_bg=Theme.SIDEBAR_HOVER,
                fg=Theme.TEXT_ON_DARK, font=self.fonts["sidebar"],
                padx=20, pady=12, anchor="w",
            )
            btn.config(anchor="w")
            btn.pack(fill="x")
            self.nav_buttons[key] = btn

        # Status area at the bottom of the sidebar.
        self.status_frame = tk.Frame(self.sidebar, bg=Theme.SIDEBAR)
        self.status_frame.pack(side="bottom", fill="x", padx=20, pady=18)
        self.status_label = tk.Label(
            self.status_frame, text="", bg=Theme.SIDEBAR,
            fg=Theme.PRIMARY_LIGHT, font=self.fonts["tiny"],
            anchor="w", justify="left", wraplength=170,
        )
        self.status_label.pack(anchor="w")
        self._update_status()

        # Main content area --------------------------------------------#
        self.content = tk.Frame(self.root, bg=Theme.BG)
        self.content.pack(side="left", fill="both", expand=True)

    def _update_status(self):
        mode = ("AI: Claude connected" if self.controller.chatbot_mode == "online"
                else "AI: offline librarian")
        self.status_label.config(
            text=f"{self.controller.library_size()} books in library\n{mode}"
        )

    # ------------------------------------------------------------------ #
    # Threading helpers
    # ------------------------------------------------------------------ #
    def _run_bg(self, fn, on_done=None, on_error=None):
        def worker():
            try:
                result = fn()
                if on_done:
                    self._ui_queue.put(lambda: on_done(result))
            except Exception as exc:  # noqa: BLE001
                if on_error:
                    self._ui_queue.put(lambda: on_error(exc))
                else:
                    self._ui_queue.put(
                        lambda: messagebox.showerror("Error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _drain_queue(self):
        try:
            while True:
                cb = self._ui_queue.get_nowait()
                cb()
        except queue.Empty:
            pass
        self.root.after(80, self._drain_queue)

    # ------------------------------------------------------------------ #
    # View switching
    # ------------------------------------------------------------------ #
    def _clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()

    def _show_view(self, key: str):
        self.current_view = key
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.set_colors(Theme.SIDEBAR_ACTIVE, Theme.SIDEBAR_ACTIVE)
            else:
                btn.set_colors(Theme.SIDEBAR, Theme.SIDEBAR_HOVER)

        self._clear_content()
        if key == "library":
            self._build_library_view()
        elif key == "ratings":
            self._build_ratings_view()
        elif key == "recommend":
            self._build_recommend_view()
        elif key == "add":
            self._build_add_view()
        self._update_status()

    def _view_header(self, title: str, subtitle: str) -> tk.Frame:
        header = tk.Frame(self.content, bg=Theme.BG)
        header.pack(fill="x", padx=32, pady=(28, 8))
        tk.Label(header, text=title, bg=Theme.BG, fg=Theme.TEXT,
                 font=self.fonts["title"]).pack(anchor="w")
        tk.Label(header, text=subtitle, bg=Theme.BG, fg=Theme.TEXT_MUTED,
                 font=self.fonts["body"]).pack(anchor="w", pady=(2, 0))
        return header

    # ================================================================== #
    # LIBRARY VIEW
    # ================================================================== #
    def _build_library_view(self):
        self._view_header("Library",
                          "Browse the collection and rate books you've read.")

        bar = tk.Frame(self.content, bg=Theme.BG)
        bar.pack(fill="x", padx=32, pady=(8, 12))

        self.lib_search_var = tk.StringVar()
        entry = tk.Entry(bar, textvariable=self.lib_search_var,
                         font=self.fonts["body"], bg=Theme.SURFACE,
                         fg=Theme.TEXT, relief="flat",
                         highlightthickness=1,
                         highlightbackground=Theme.BORDER,
                         highlightcolor=Theme.PRIMARY)
        entry.pack(side="left", fill="x", expand=True, ipady=8, ipadx=8)
        entry.bind("<Return>", lambda e: self._do_library_search())

        HoverButton(bar, text="Search", command=self._do_library_search,
                    font=self.fonts["body"], padx=20, pady=9).pack(
            side="left", padx=(10, 0))

        # Scrollable results region.
        self.lib_outer, self.lib_inner = make_scrollable(self.content)
        self.lib_outer.pack(fill="both", expand=True, padx=24, pady=(4, 20))

        self._do_library_search()

    def _do_library_search(self):
        query = self.lib_search_var.get() if hasattr(self, "lib_search_var") else ""
        for c in self.lib_inner.winfo_children():
            c.destroy()
        loading = tk.Label(self.lib_inner, text="Loading\u2026",
                           bg=Theme.BG, fg=Theme.TEXT_MUTED,
                           font=self.fonts["body"])
        loading.pack(pady=20)

        def work():
            return self.controller.search_local(query)

        def done(books):
            loading.destroy()
            self._render_book_list(self.lib_inner, books, mode="library",
                                   on_action=self._open_rating_dialog,
                                   empty_msg="No books match your search.")

        self._run_bg(work, on_done=done)

    # ================================================================== #
    # RATINGS VIEW
    # ================================================================== #
    def _build_ratings_view(self):
        self._view_header("My Ratings",
                          "Books you've scored. These power your recommendations.")

        bar = tk.Frame(self.content, bg=Theme.BG)
        bar.pack(fill="x", padx=32, pady=(4, 8))
        HoverButton(bar, text="Clear all ratings",
                    command=self._clear_all_ratings,
                    bg=Theme.DANGER, hover_bg="#9B453E",
                    font=self.fonts["small"], padx=14, pady=7).pack(
            side="right")

        self.rate_outer, self.rate_inner = make_scrollable(self.content)
        self.rate_outer.pack(fill="both", expand=True, padx=24, pady=(4, 20))
        self._refresh_ratings_list()

    def _refresh_ratings_list(self):
        for c in self.rate_inner.winfo_children():
            c.destroy()
        rated = self.controller.rated_books()
        if not rated:
            self._empty_state(
                self.rate_inner,
                "You haven't rated any books yet.",
                "Head to the Library and click \u201cRate\u201d on books you've read.")
            return
        for b in rated:
            self._rated_row(self.rate_inner, b)

    def _rated_row(self, parent, book):
        card = tk.Frame(parent, bg=Theme.SURFACE,
                        highlightbackground=Theme.BORDER, highlightthickness=1)
        card.pack(fill="x", pady=6, padx=4)
        inner = tk.Frame(card, bg=Theme.SURFACE)
        inner.pack(fill="x", padx=14, pady=12)

        left = tk.Frame(inner, bg=Theme.SURFACE)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=book["title"], bg=Theme.SURFACE, fg=Theme.TEXT,
                 font=self.fonts["body_bold"], anchor="w",
                 wraplength=420, justify="left").pack(anchor="w")
        tk.Label(left, text=book.get("author") or "Unknown",
                 bg=Theme.SURFACE, fg=Theme.TEXT_MUTED,
                 font=self.fonts["small"], anchor="w").pack(anchor="w")

        score = int(book.get("user_score", 0))
        stars = "\u2605" * (score // 2) + "\u2606" * (5 - score // 2)
        score_box = tk.Frame(inner, bg=Theme.SURFACE)
        score_box.pack(side="left", padx=16)
        tk.Label(score_box, text=f"{score}/10", bg=Theme.SURFACE,
                 fg=Theme.PRIMARY_DARK, font=self.fonts["h2"]).pack()
        tk.Label(score_box, text=stars, bg=Theme.SURFACE, fg=Theme.STAR,
                 font=self.fonts["small"]).pack()

        HoverButton(inner, text="Edit",
                    command=lambda b=book: self._open_rating_dialog(b),
                    bg=Theme.PRIMARY, hover_bg=Theme.PRIMARY_DARK,
                    font=self.fonts["tiny"], padx=12, pady=5).pack(
            side="left", padx=(0, 6))
        HoverButton(inner, text="Remove",
                    command=lambda b=book: self._remove_rating(b),
                    bg=Theme.SURFACE_ALT, hover_bg="#EFE7D6",
                    fg=Theme.DANGER,
                    font=self.fonts["tiny"], padx=12, pady=5).pack(side="left")

    def _remove_rating(self, book):
        self.controller.unrate_book(book["id"])
        self._refresh_ratings_list()
        self._update_status()

    def _clear_all_ratings(self):
        if messagebox.askyesno("Clear ratings",
                               "Remove all of your ratings? This can't be undone."):
            self.controller.clear_ratings()
            self._refresh_ratings_list()

    # ================================================================== #
    # RECOMMEND VIEW  (+ chatbot)
    # ================================================================== #
    def _build_recommend_view(self):
        self._view_header(
            "Recommendations",
            "Tailored picks from your ratings, introduced by your AI librarian.")

        bar = tk.Frame(self.content, bg=Theme.BG)
        bar.pack(fill="x", padx=32, pady=(4, 10))
        HoverButton(bar, text="\u2728  Generate recommendations",
                    command=self._generate_recommendations,
                    bg=Theme.ACCENT, hover_bg="#336657",
                    font=self.fonts["body_bold"], padx=20, pady=10).pack(
            side="left")

        # Split: left = chatbot, right = recommendation cards.
        split = tk.Frame(self.content, bg=Theme.BG)
        split.pack(fill="both", expand=True, padx=24, pady=(6, 18))

        # --- Chatbot panel (left) ------------------------------------- #
        chat_panel = tk.Frame(split, bg=Theme.SURFACE,
                              highlightbackground=Theme.BORDER,
                              highlightthickness=1, width=420)
        chat_panel.pack(side="left", fill="both", padx=(0, 12))
        chat_panel.pack_propagate(False)

        chat_head = tk.Frame(chat_panel, bg=Theme.PRIMARY)
        chat_head.pack(fill="x")
        tk.Label(chat_head, text="\U0001F916  AI Librarian", bg=Theme.PRIMARY,
                 fg="white", font=self.fonts["h2"], pady=12, padx=14).pack(
            anchor="w")

        self.chat_log = tk.Text(
            chat_panel, bg=Theme.SURFACE, fg=Theme.TEXT,
            font=self.fonts["chat"], wrap="word", bd=0,
            highlightthickness=0, padx=14, pady=14, state="disabled",
            spacing1=2, spacing3=8,
        )
        self.chat_log.pack(fill="both", expand=True)
        self.chat_log.tag_configure("bot", foreground=Theme.TEXT,
                                    lmargin1=4, lmargin2=4)
        self.chat_log.tag_configure("user", foreground=Theme.PRIMARY_DARK,
                                    font=self.fonts["body_bold"],
                                    lmargin1=4, lmargin2=4)
        self.chat_log.tag_configure("system", foreground=Theme.TEXT_MUTED,
                                    font=self.fonts["small"])

        chat_input_row = tk.Frame(chat_panel, bg=Theme.SURFACE_ALT)
        chat_input_row.pack(fill="x")
        self.chat_entry = tk.Entry(
            chat_input_row, font=self.fonts["body"], bg=Theme.SURFACE,
            fg=Theme.TEXT, relief="flat", highlightthickness=1,
            highlightbackground=Theme.BORDER, highlightcolor=Theme.PRIMARY)
        self.chat_entry.pack(side="left", fill="x", expand=True,
                             padx=(10, 6), pady=10, ipady=7, ipadx=6)
        self.chat_entry.bind("<Return>", lambda e: self._send_chat())
        HoverButton(chat_input_row, text="Send", command=self._send_chat,
                    font=self.fonts["small"], padx=16, pady=8).pack(
            side="left", padx=(0, 10), pady=10)

        self._chat_system("Click \u201cGenerate recommendations\u201d and I'll "
                          "introduce some books picked just for you.")

        # --- Recommendation cards (right) ----------------------------- #
        self.rec_outer, self.rec_inner = make_scrollable(split)
        self.rec_outer.pack(side="left", fill="both", expand=True)
        self._empty_state(
            self.rec_inner,
            "No recommendations yet.",
            "Rate a few books, then click Generate.")

    def _chat_system(self, text):
        self.chat_log.config(state="normal")
        self.chat_log.insert("end", text + "\n\n", "system")
        self.chat_log.config(state="disabled")
        self.chat_log.see("end")

    def _chat_bot(self, text):
        self.chat_log.config(state="normal")
        self.chat_log.insert("end", "Librarian\n", "user")
        self.chat_log.insert("end", text + "\n\n", "bot")
        self.chat_log.config(state="disabled")
        self.chat_log.see("end")

    def _chat_user(self, text):
        self.chat_log.config(state="normal")
        self.chat_log.insert("end", "You\n", "user")
        self.chat_log.insert("end", text + "\n\n", "bot")
        self.chat_log.config(state="disabled")
        self.chat_log.see("end")

    def _generate_recommendations(self):
        rated = self.controller.rated_books()
        if not rated:
            messagebox.showinfo(
                "Rate some books first",
                "Go to the Library and rate at least one or two books "
                "you've read, then come back here.")
            return

        for c in self.rec_inner.winfo_children():
            c.destroy()
        tk.Label(self.rec_inner, text="Finding books for you\u2026",
                 bg=Theme.BG, fg=Theme.TEXT_MUTED,
                 font=self.fonts["body"]).pack(pady=20)
        self._chat_system("Thinking about what you'd enjoy\u2026")

        def work():
            recs = self.controller.get_recommendations(top_n=8)
            intro = self.controller.chatbot_introduce() if recs else ""
            return recs, intro

        def done(result):
            recs, intro = result
            for c in self.rec_inner.winfo_children():
                c.destroy()
            if not recs:
                self._empty_state(
                    self.rec_inner, "No candidates available.",
                    "Your library may be too small \u2014 add more books.")
                self._chat_bot("I don't have enough books to recommend from "
                               "yet. Try adding a few via \u201cAdd a Book.\u201d")
                return
            self._render_book_list(self.rec_inner, recs, mode="recommend")
            if intro:
                self._chat_bot(intro)

        self._run_bg(work, on_done=done)

    def _send_chat(self):
        text = self.chat_entry.get().strip()
        if not text:
            return
        self.chat_entry.delete(0, "end")
        self._chat_user(text)

        if not self.controller.last_recommendations:
            self._chat_bot("Generate some recommendations first and then I can "
                           "tell you all about them!")
            return

        def work():
            return self.controller.chatbot_answer(text)

        def done(answer):
            self._chat_bot(answer)

        self._run_bg(work, on_done=done)

    # ================================================================== #
    # ADD-A-BOOK VIEW
    # ================================================================== #
    def _build_add_view(self):
        self._view_header(
            "Add a Book",
            "Not in the library? Search Open Library to pull in its details.")

        # --- Library expansion card ----------------------------------- #
        grow = tk.Frame(self.content, bg=Theme.SURFACE_ALT,
                        highlightbackground=Theme.BORDER, highlightthickness=1)
        grow.pack(fill="x", padx=32, pady=(8, 4))
        grow_inner = tk.Frame(grow, bg=Theme.SURFACE_ALT)
        grow_inner.pack(fill="x", padx=18, pady=14)

        grow_left = tk.Frame(grow_inner, bg=Theme.SURFACE_ALT)
        grow_left.pack(side="left", fill="x", expand=True)
        tk.Label(grow_left, text="Grow your library",
                 bg=Theme.SURFACE_ALT, fg=Theme.TEXT,
                 font=self.fonts["body_bold"]).pack(anchor="w")
        self.grow_status = tk.Label(
            grow_left,
            text=f"You currently have {self.controller.library_size()} books. "
                 "Fetch more from Open Library across many genres.",
            bg=Theme.SURFACE_ALT, fg=Theme.TEXT_MUTED,
            font=self.fonts["small"], anchor="w", justify="left",
            wraplength=520)
        self.grow_status.pack(anchor="w", pady=(2, 0))

        self.grow_btn = HoverButton(
            grow_inner, text="\u2795  Fetch more books",
            command=self._expand_library,
            bg=Theme.PRIMARY, hover_bg=Theme.PRIMARY_DARK,
            font=self.fonts["small"], padx=16, pady=9)
        self.grow_btn.pack(side="left", padx=(12, 0))

        self.rebuild_btn = HoverButton(
            grow_inner, text="\u21BB  Rebuild fresh",
            command=self._rebuild_library,
            bg=Theme.SURFACE, hover_bg="#EFE7D6", fg=Theme.PRIMARY_DARK,
            font=self.fonts["small"], padx=16, pady=9)
        self.rebuild_btn.pack(side="left", padx=(8, 0))

        form = tk.Frame(self.content, bg=Theme.SURFACE,
                        highlightbackground=Theme.BORDER, highlightthickness=1)
        form.pack(fill="x", padx=32, pady=(8, 12))
        inner = tk.Frame(form, bg=Theme.SURFACE)
        inner.pack(fill="x", padx=18, pady=18)

        tk.Label(inner, text="Title", bg=Theme.SURFACE, fg=Theme.TEXT,
                 font=self.fonts["body_bold"]).grid(row=0, column=0,
                                                    sticky="w")
        self.add_title_var = tk.StringVar()
        title_entry = tk.Entry(inner, textvariable=self.add_title_var,
                               font=self.fonts["body"], bg=Theme.SURFACE_ALT,
                               relief="flat", highlightthickness=1,
                               highlightbackground=Theme.BORDER,
                               highlightcolor=Theme.PRIMARY, width=44)
        title_entry.grid(row=1, column=0, sticky="we", ipady=7, ipadx=6,
                         pady=(2, 10))

        tk.Label(inner, text="Author (optional)", bg=Theme.SURFACE,
                 fg=Theme.TEXT, font=self.fonts["body_bold"]).grid(
            row=2, column=0, sticky="w")
        self.add_author_var = tk.StringVar()
        tk.Entry(inner, textvariable=self.add_author_var,
                 font=self.fonts["body"], bg=Theme.SURFACE_ALT,
                 relief="flat", highlightthickness=1,
                 highlightbackground=Theme.BORDER,
                 highlightcolor=Theme.PRIMARY, width=44).grid(
            row=3, column=0, sticky="we", ipady=7, ipadx=6, pady=(2, 12))

        inner.columnconfigure(0, weight=1)

        HoverButton(inner, text="Search Open Library",
                    command=self._do_online_search,
                    bg=Theme.ACCENT, hover_bg="#336657",
                    font=self.fonts["body_bold"], padx=18, pady=9).grid(
            row=4, column=0, sticky="w")
        title_entry.bind("<Return>", lambda e: self._do_online_search())

        # Results region.
        self.add_outer, self.add_inner = make_scrollable(self.content)
        self.add_outer.pack(fill="both", expand=True, padx=24, pady=(6, 18))
        self._empty_state(self.add_inner,
                          "Search results will appear here.",
                          "Type a title above and press Search.")

    def _rebuild_library(self):
        """Wipe and rebuild the library fresh (clears old classic-heavy data)."""
        if not messagebox.askyesno(
                "Rebuild library",
                "This clears your current library AND your ratings, then "
                "downloads a fresh, more varied set of books from Open "
                "Library.\n\nThis can take a minute. Continue?"):
            return
        self.grow_btn.config(text="Rebuilding\u2026")
        self.rebuild_btn.config(text="Working\u2026")
        self.grow_status.config(text="Clearing old library\u2026")

        def progress(done_n, total, label):
            self._ui_queue.put(
                lambda: self.grow_status.config(
                    text=f"Fetching \u201c{label}\u201d\u2026 ({done_n}/{total} "
                         "genres)"))

        def work():
            return self.controller.rebuild_library(progress_cb=progress,
                                                   per_subject=60)

        def done(total_count):
            self.grow_btn.config(text="\u2795  Fetch more books")
            self.rebuild_btn.config(text="\u21BB  Rebuild fresh")
            self.grow_status.config(
                text=f"Done \u2014 rebuilt with {total_count} books. "
                     "Your ratings were reset; rate some books to get "
                     "recommendations.")
            self._update_status()

        def err(_exc):
            self.grow_btn.config(text="\u2795  Fetch more books")
            self.rebuild_btn.config(text="\u21BB  Rebuild fresh")
            self.grow_status.config(
                text="Couldn't reach Open Library. Check your connection "
                     "and try again.")

        self._run_bg(work, on_done=done, on_error=err)

    def _expand_library(self):
        """Fetch more books from Open Library into the existing database."""
        start_count = self.controller.library_size()
        self.grow_btn.config(text="Fetching\u2026")
        # Make the label show live progress.
        self.grow_status.config(text="Contacting Open Library\u2026")

        def progress(done_n, total, label):
            self._ui_queue.put(
                lambda: self.grow_status.config(
                    text=f"Fetching \u201c{label}\u201d\u2026 ({done_n}/{total} "
                         "genres)"))

        def work():
            # seed_library merges by ol_key, so existing books aren't
            # duplicated; only genuinely new titles are added.
            return self.controller.seed_library(progress_cb=progress,
                                                per_subject=60)

        def done(total_count):
            added = total_count - start_count
            self.grow_btn.config(text="\u2795  Fetch more books")
            self.grow_status.config(
                text=f"Done \u2014 added {added} new book(s). "
                     f"You now have {total_count} in your library.")
            self._update_status()

        def err(_exc):
            self.grow_btn.config(text="\u2795  Fetch more books")
            self.grow_status.config(
                text="Couldn't reach Open Library. Check your connection "
                     "and try again.")

        self._run_bg(work, on_done=done, on_error=err)

    def _do_online_search(self):
        title = self.add_title_var.get().strip()
        if not title:
            messagebox.showinfo("Enter a title", "Please type a book title.")
            return
        author = self.add_author_var.get().strip() or None

        for c in self.add_inner.winfo_children():
            c.destroy()
        tk.Label(self.add_inner, text="Searching Open Library\u2026",
                 bg=Theme.BG, fg=Theme.TEXT_MUTED,
                 font=self.fonts["body"]).pack(pady=20)

        def work():
            return self.controller.search_online_candidates(title)

        def done(results):
            for c in self.add_inner.winfo_children():
                c.destroy()
            if not results:
                self._empty_state(
                    self.add_inner, "No matches found online.",
                    "Check the spelling, or try without the author.")
                return
            tk.Label(self.add_inner,
                     text="Pick the right edition to add it to your library:",
                     bg=Theme.BG, fg=Theme.TEXT_MUTED,
                     font=self.fonts["small"]).pack(anchor="w", pady=(0, 6),
                                                    padx=4)
            for r in results:
                self._online_result_row(r)

        def err(exc):
            for c in self.add_inner.winfo_children():
                c.destroy()
            self._empty_state(
                self.add_inner, "Couldn't reach Open Library.",
                "Check your internet connection and try again.")

        self._run_bg(work, on_done=done, on_error=err)

    def _online_result_row(self, result):
        card = tk.Frame(self.add_inner, bg=Theme.SURFACE,
                        highlightbackground=Theme.BORDER, highlightthickness=1)
        card.pack(fill="x", pady=6, padx=4)
        inner = tk.Frame(card, bg=Theme.SURFACE)
        inner.pack(fill="x", padx=14, pady=12)

        left = tk.Frame(inner, bg=Theme.SURFACE)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=result.get("title", "Untitled"),
                 bg=Theme.SURFACE, fg=Theme.TEXT,
                 font=self.fonts["body_bold"], anchor="w",
                 wraplength=420, justify="left").pack(anchor="w")
        meta = result.get("author") or "Unknown author"
        if result.get("publish_year"):
            meta += f"  \u00b7  {result['publish_year']}"
        tk.Label(left, text=meta, bg=Theme.SURFACE, fg=Theme.TEXT_MUTED,
                 font=self.fonts["small"], anchor="w").pack(anchor="w")

        HoverButton(inner, text="Add & rate",
                    command=lambda r=result: self._add_online_book(r),
                    bg=Theme.PRIMARY, hover_bg=Theme.PRIMARY_DARK,
                    font=self.fonts["small"], padx=14, pady=7).pack(
            side="left")

    def _add_online_book(self, result):
        title = result.get("title", "")
        author = result.get("author")

        def work():
            # fetch_book does a richer lookup (description, subjects, moods).
            full = self.controller.fetch_and_add_book(title, author)
            return full

        def done(book):
            if not book:
                messagebox.showerror(
                    "Couldn't add",
                    "Sorry, I couldn't retrieve full details for that book.")
                return
            self._update_status()
            messagebox.showinfo(
                "Added",
                f"\u201c{book['title']}\u201d is now in your library.")
            self._open_rating_dialog(book)

        self._run_bg(work, on_done=done)

    # ================================================================== #
    # Shared rendering helpers
    # ================================================================== #
    def _render_book_list(self, parent, books: List[Dict[str, Any]],
                          mode="library", on_action=None,
                          empty_msg="Nothing here yet."):
        if not books:
            self._empty_state(parent, empty_msg, "")
            return
        for b in books:
            card = BookCard(parent, b, self.fonts, mode=mode,
                            on_action=on_action)
            card.pack(fill="x", pady=7, padx=4)

    def _empty_state(self, parent, title, subtitle):
        wrap = tk.Frame(parent, bg=Theme.BG)
        wrap.pack(fill="both", expand=True, pady=50)
        tk.Label(wrap, text="\U0001F4DA", bg=Theme.BG, fg=Theme.TEXT_MUTED,
                 font=("Helvetica", 40)).pack()
        tk.Label(wrap, text=title, bg=Theme.BG, fg=Theme.TEXT,
                 font=self.fonts["h2"]).pack(pady=(8, 2))
        if subtitle:
            tk.Label(wrap, text=subtitle, bg=Theme.BG, fg=Theme.TEXT_MUTED,
                     font=self.fonts["small"]).pack()

    # ------------------------------------------------------------------ #
    # Rating dialog
    # ------------------------------------------------------------------ #
    def _open_rating_dialog(self, book: Dict[str, Any]):
        dlg = tk.Toplevel(self.root)
        dlg.title("Rate this book")
        dlg.configure(bg=Theme.SURFACE)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)

        # Center over the main window.
        self.root.update_idletasks()
        w, h = 440, 300
        x = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        pad = tk.Frame(dlg, bg=Theme.SURFACE)
        pad.pack(fill="both", expand=True, padx=24, pady=20)

        tk.Label(pad, text=book.get("title", "Untitled"), bg=Theme.SURFACE,
                 fg=Theme.TEXT, font=self.fonts["h1"], wraplength=380,
                 justify="left").pack(anchor="w")
        tk.Label(pad, text=book.get("author") or "Unknown author",
                 bg=Theme.SURFACE, fg=Theme.TEXT_MUTED,
                 font=self.fonts["body"]).pack(anchor="w", pady=(2, 16))

        tk.Label(pad, text="How much did you enjoy it? (0\u201310)",
                 bg=Theme.SURFACE, fg=Theme.TEXT,
                 font=self.fonts["body_bold"]).pack(anchor="w", pady=(0, 6))

        # Pre-fill with an existing score if present.
        existing = book.get("user_score")
        rating = StarRating(pad, self.fonts,
                            initial=existing if existing is not None else 5.0)
        rating.pack(anchor="w", pady=(0, 18))

        btn_row = tk.Frame(pad, bg=Theme.SURFACE)
        btn_row.pack(fill="x")

        def save():
            self.controller.rate_book(book["id"], rating.value())
            self._update_status()
            dlg.destroy()
            # Refresh whichever list is visible.
            if self.current_view == "ratings":
                self._refresh_ratings_list()
            elif self.current_view == "library":
                self._do_library_search()

        HoverButton(btn_row, text="Save rating", command=save,
                    bg=Theme.ACCENT, hover_bg="#336657",
                    font=self.fonts["body_bold"], padx=18, pady=9).pack(
            side="left")
        HoverButton(btn_row, text="Cancel", command=dlg.destroy,
                    bg=Theme.SURFACE_ALT, hover_bg="#EFE7D6",
                    fg=Theme.TEXT, font=self.fonts["body"],
                    padx=18, pady=9).pack(side="left", padx=(10, 0))

    # ------------------------------------------------------------------ #
    # First-run seeding
    # ------------------------------------------------------------------ #
    def _seed_first_run(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Setting up your library")
        dlg.configure(bg=Theme.SURFACE)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        w, h = 460, 200
        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        tk.Label(dlg, text="\U0001F4DA  Building your library",
                 bg=Theme.SURFACE, fg=Theme.TEXT,
                 font=self.fonts["h1"]).pack(pady=(24, 6))
        msg = tk.Label(dlg, text="Fetching books from Open Library\u2026",
                       bg=Theme.SURFACE, fg=Theme.TEXT_MUTED,
                       font=self.fonts["body"], wraplength=400)
        msg.pack(pady=(0, 14))

        bar_bg = tk.Frame(dlg, bg=Theme.SURFACE_ALT, height=10, width=380)
        bar_bg.pack()
        bar_bg.pack_propagate(False)
        bar_fill = tk.Frame(bar_bg, bg=Theme.ACCENT, height=10, width=0)
        bar_fill.place(x=0, y=0)

        def progress(done_n, total, label):
            frac = done_n / max(total, 1)
            self._ui_queue.put(
                lambda: bar_fill.config(width=int(380 * frac)))
            self._ui_queue.put(
                lambda: msg.config(text=f"Loading \u201c{label}\u201d\u2026 "
                                        f"({done_n}/{total})"))

        def work():
            return self.controller.seed_library(progress_cb=progress,
                                                per_subject=60)

        def done(count):
            dlg.destroy()
            self._update_status()
            if count == 0:
                messagebox.showwarning(
                    "Offline",
                    "Couldn't reach Open Library, so the library is empty.\n\n"
                    "Check your internet connection, then restart the app, or "
                    "use \u201cAdd a Book\u201d once you're online.")
            else:
                self._do_library_search()

        def err(exc):
            dlg.destroy()
            messagebox.showwarning(
                "Setup issue",
                f"Could not build the library automatically.\n{exc}\n\n"
                "You can still add books manually once online.")

        self._run_bg(work, on_done=done, on_error=err)

    # ------------------------------------------------------------------ #
    def on_close(self):
        try:
            self.controller.close()
        finally:
            self.root.destroy()
