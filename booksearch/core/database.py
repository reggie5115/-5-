"""
database.py
-----------
SQLite-backed storage for the book recommendation platform.

Each book is stored with the metadata needed to build a feature vector:
title, author, genres (subjects), mood tags, publish year, page count,
and an Open Library identifier.

Genres and moods are stored as JSON arrays of strings. The vectorizer
(see recommender.py) turns these into a numeric vector space.
"""

import sqlite3
import json
import os
import threading
from typing import List, Dict, Optional, Any


# Store the database inside the app's own `data/` folder so the whole project
# is self-contained (easy to back up or carry on a USB stick). This file lives
# at <app>/core/database.py, so the app root is one directory up, and data/ is
# a sibling of core/ and gui/.
_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(_APP_ROOT, "data", "library.db")


class BookDatabase:
    """Thread-aware wrapper around a SQLite database of books."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        # check_same_thread=False so the GUI thread and worker threads can share it;
        # we guard writes with a lock.
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    # ------------------------------------------------------------------ #
    # Schema
    # ------------------------------------------------------------------ #
    def _create_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS books (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    ol_key        TEXT UNIQUE,
                    title         TEXT NOT NULL,
                    author        TEXT,
                    genres        TEXT,          -- JSON array
                    moods         TEXT,          -- JSON array
                    description   TEXT,
                    publish_year  INTEGER,
                    page_count    INTEGER,
                    rating        REAL,          -- average OL rating if any
                    cover_url     TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_ratings (
                    book_id  INTEGER PRIMARY KEY,
                    score    REAL NOT NULL,       -- 0..10 from the user
                    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
                )
                """
            )
            self._conn.commit()

    # ------------------------------------------------------------------ #
    # Inserts / updates
    # ------------------------------------------------------------------ #
    def add_book(self, book: Dict[str, Any]) -> int:
        """
        Insert a book (or update it if the ol_key already exists).
        Returns the row id of the book.
        """
        genres = json.dumps(book.get("genres", []), ensure_ascii=False)
        moods = json.dumps(book.get("moods", []), ensure_ascii=False)
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO books
                    (ol_key, title, author, genres, moods, description,
                     publish_year, page_count, rating, cover_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ol_key) DO UPDATE SET
                    title=excluded.title,
                    author=excluded.author,
                    genres=excluded.genres,
                    moods=excluded.moods,
                    description=excluded.description,
                    publish_year=excluded.publish_year,
                    page_count=excluded.page_count,
                    rating=excluded.rating,
                    cover_url=excluded.cover_url
                """,
                (
                    book.get("ol_key"),
                    book.get("title", "Untitled"),
                    book.get("author"),
                    genres,
                    moods,
                    book.get("description"),
                    book.get("publish_year"),
                    book.get("page_count"),
                    book.get("rating"),
                    book.get("cover_url"),
                ),
            )
            self._conn.commit()
            if cur.lastrowid:
                return cur.lastrowid
            # ON CONFLICT path doesn't return a lastrowid; look it up.
            row = self._conn.execute(
                "SELECT id FROM books WHERE ol_key = ?", (book.get("ol_key"),)
            ).fetchone()
            return row["id"] if row else -1

    def add_books_bulk(self, books: List[Dict[str, Any]]) -> int:
        count = 0
        for b in books:
            self.add_book(b)
            count += 1
        return count

    def set_user_rating(self, book_id: int, score: float) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO user_ratings (book_id, score)
                VALUES (?, ?)
                ON CONFLICT(book_id) DO UPDATE SET score = excluded.score
                """,
                (book_id, score),
            )
            self._conn.commit()

    def clear_user_rating(self, book_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM user_ratings WHERE book_id = ?", (book_id,)
            )
            self._conn.commit()

    def clear_all_ratings(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM user_ratings")
            self._conn.commit()

    def clear_all_books(self) -> None:
        """Wipe the entire library (books + ratings). Used for a fresh rebuild."""
        with self._lock:
            self._conn.execute("DELETE FROM user_ratings")
            self._conn.execute("DELETE FROM books")
            self._conn.commit()
            self._conn.execute("VACUUM")
            self._conn.commit()

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        d["genres"] = json.loads(d.get("genres") or "[]")
        d["moods"] = json.loads(d.get("moods") or "[]")
        return d

    def get_book(self, book_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM books WHERE id = ?", (book_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_book_by_key(self, ol_key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM books WHERE ol_key = ?", (ol_key,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def all_books(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM books ORDER BY title COLLATE NOCASE"
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def search_books(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Case-insensitive substring search over title and author."""
        like = f"%{query}%"
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM books
                WHERE title LIKE ? COLLATE NOCASE
                   OR author LIKE ? COLLATE NOCASE
                ORDER BY title COLLATE NOCASE
                LIMIT ?
                """,
                (like, like, limit),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def rated_books(self) -> List[Dict[str, Any]]:
        """All books the user has scored, with the score attached."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT b.*, r.score AS user_score
                FROM books b
                JOIN user_ratings r ON r.book_id = b.id
                ORDER BY r.score DESC
                """
            ).fetchall()
        out = []
        for r in rows:
            d = self._row_to_dict(r)
            d["user_score"] = r["user_score"]
            out.append(d)
        return out

    def unrated_books(self) -> List[Dict[str, Any]]:
        """All books the user has NOT scored (recommendation candidates)."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM books
                WHERE id NOT IN (SELECT book_id FROM user_ratings)
                ORDER BY title COLLATE NOCASE
                """
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM books").fetchone()
        return row["c"]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
