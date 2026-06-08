import sqlite3
import json
import os
from typing import List, Dict, Optional, Any

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(_APP_ROOT, "data", "library.db")


class BookDatabase:
    """Minimal SQLite storage for books. (ratings come in a later version)"""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS books (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ol_key        TEXT UNIQUE,
                title         TEXT NOT NULL,
                author        TEXT,
                genres        TEXT,
                publish_year  INTEGER,
                cover_url     TEXT
            )
            """
        )
        self._conn.commit()

    def add_book(self, book: Dict[str, Any]) -> int:
        genres = json.dumps(book.get("genres", []), ensure_ascii=False)
        cur = self._conn.execute(
            """
            INSERT OR IGNORE INTO books
                (ol_key, title, author, genres, publish_year, cover_url)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                book.get("ol_key"),
                book.get("title", "Untitled"),
                book.get("author"),
                genres,
                book.get("publish_year"),
                book.get("cover_url"),
            ),
        )
        self._conn.commit()
        return cur.lastrowid or -1

    def add_books_bulk(self, books: List[Dict[str, Any]]) -> int:
        for b in books:
            self.add_book(b)
        return len(books)

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        d["genres"] = json.loads(d.get("genres") or "[]")
        return d

    def all_books(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM books ORDER BY title COLLATE NOCASE"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS c FROM books").fetchone()["c"]

    def close(self) -> None:
        self._conn.close()
