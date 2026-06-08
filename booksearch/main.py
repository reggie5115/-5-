#!/usr/bin/env python3
"""
Inkwell -- a desktop book discovery & recommendation platform.

Run with:  python main.py

Features
--------
* Builds a local book database from Open Library (title, genres, moods, etc.).
* Treats each book as a point in a vector space (genres + moods + more).
* You rate books you've read on a 0-10 scale; it learns your taste vector.
* Recommends books you haven't rated, ranked by cosine similarity.
* Look up books not yet in the database and pull their details from the web.
* An AI librarian chatbot introduces the recommendations and answers questions.

The only hard dependency is Python's standard library (Tkinter ships with
most Python installs). If the `anthropic` package and an ANTHROPIC_API_KEY
environment variable are present, the chatbot uses Claude; otherwise it falls
back to a built-in offline librarian so the app always works.
"""

import sys
import os
import tkinter as tk
from tkinter import messagebox

# Make sure local packages import correctly regardless of CWD.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.main_window import MainWindow  # noqa: E402


def main():
    root = tk.Tk()

    # Improve scaling / appearance on high-DPI displays where supported.
    try:
        root.tk.call("tk", "scaling", 1.2)
    except tk.TclError:
        pass

    try:
        app = MainWindow(root)
    except Exception as exc:  # noqa: BLE001
        messagebox.showerror(
            "Startup error",
            f"Inkwell failed to start:\n\n{exc}")
        raise

    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main() 
