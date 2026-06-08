"""
app_controller.py
-----------------
Glue layer between the GUI and the core modules. The GUI calls these methods
(often from background threads) so the Tk widgets stay responsive.
"""

from typing import List, Dict, Any, Optional, Callable

from core.database import BookDatabase
from core.recommender import Recommender
from core.chatbot import BookChatbot
from core import openlibrary as ol


# A broad set of subjects to seed a fresh library with, chosen to spread
# across genres and moods so the vector space has plenty of variety. Each
# subject is fetched with rating/recency/relevance passes (see openlibrary.py)
# so the mix is contemporary and varied, not just public-domain classics.
DEFAULT_SUBJECTS = [
    # Core fiction genres
    "fantasy", "science_fiction", "mystery", "romance", "thriller",
    "horror", "historical_fiction", "adventure", "dystopia",
    "fiction", "literary_fiction", "short_stories",
    # Crime / suspense
    "crime", "detective_and_mystery_stories", "espionage", "suspense",
    "noir", "true_crime",
    # Sub-genres & moods
    "humor", "comedy", "satire", "magical_realism", "gothic",
    "western", "war", "coming_of_age", "urban_fantasy",
    "epic_fantasy", "space_opera", "cyberpunk", "steampunk",
    "paranormal", "supernatural", "time_travel", "apocalyptic",
    "contemporary_romance", "fantasy_romance", "romantic_suspense",
    # Audience
    "young_adult", "children", "juvenile_fiction", "new_adult",
    "graphic_novels", "comics", "manga",
    # Non-fiction
    "biography", "autobiography", "memoir", "history",
    "philosophy", "psychology", "science", "self_help",
    "travel", "cooking", "art", "poetry", "drama",
    "business", "economics", "politics", "technology",
    "health", "fitness", "nature", "environment",
    "music", "film", "sports", "religion",
    # Classics & literature
    "classics", "classic_literature",
]


class AppController:
    def __init__(self):
        self.db = BookDatabase()
        self.chatbot = BookChatbot()
        self.last_recommendations: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    # Library / seeding
    # ------------------------------------------------------------------ #
    def library_size(self) -> int:
        return self.db.count()

    def needs_seeding(self) -> bool:
        return self.db.count() == 0

    def seed_library(self, progress_cb: Optional[Callable] = None,
                     per_subject: int = 60) -> int:
        """Fetch default subjects from Open Library and store them."""
        books = ol.seed_books(DEFAULT_SUBJECTS, per_subject=per_subject,
                              progress_cb=progress_cb)
        if books:
            self.db.add_books_bulk(books)
        return self.db.count()

    def rebuild_library(self, progress_cb: Optional[Callable] = None,
                        per_subject: int = 60) -> int:
        """
        Wipe the existing library and rebuild it from scratch with the current
        (diverse) subject list. This clears the old classic-heavy data so the
        fresh, varied mix isn't diluted by it. Note: this also clears ratings.
        """
        self.db.clear_all_books()
        return self.seed_library(progress_cb=progress_cb,
                                 per_subject=per_subject)

    # ------------------------------------------------------------------ #
    # Searching the local library
    # ------------------------------------------------------------------ #
    def search_local(self, query: str) -> List[Dict[str, Any]]:
        if not query.strip():
            return self.db.all_books()[:100]
        return self.db.search_books(query)

    def all_books(self) -> List[Dict[str, Any]]:
        return self.db.all_books()

    # ------------------------------------------------------------------ #
    # Online lookup for unknown books
    # ------------------------------------------------------------------ #
    def search_online_candidates(self, title: str) -> List[Dict[str, Any]]:
        return ol.search_titles(title)

    def fetch_and_add_book(self, title: str,
                           author: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Look the book up online, store it, and return the stored record
        (with its new local id). Returns None if not found.
        """
        # Already local?
        existing = self.db.search_books(title, limit=1)
        if existing and existing[0]["title"].lower() == title.lower():
            return existing[0]

        book = ol.fetch_book(title, author)
        if not book:
            return None
        book_id = self.db.add_book(book)
        return self.db.get_book(book_id)

    def add_book_record(self, book: Dict[str, Any]) -> Dict[str, Any]:
        """Store a pre-fetched book record and return it with its local id."""
        book_id = self.db.add_book(book)
        return self.db.get_book(book_id)

    # ------------------------------------------------------------------ #
    # Ratings
    # ------------------------------------------------------------------ #
    def rate_book(self, book_id: int, score: float) -> None:
        self.db.set_user_rating(book_id, score)

    def unrate_book(self, book_id: int) -> None:
        self.db.clear_user_rating(book_id)

    def clear_ratings(self) -> None:
        self.db.clear_all_ratings()

    def rated_books(self) -> List[Dict[str, Any]]:
        return self.db.rated_books()

    # ------------------------------------------------------------------ #
    # Recommendations + chatbot
    # ------------------------------------------------------------------ #
    def get_recommendations(self, top_n: int = 8) -> List[Dict[str, Any]]:
        rated = self.db.rated_books()
        candidates = self.db.unrated_books()
        if not rated or not candidates:
            self.last_recommendations = []
            return []
        rec = Recommender(self.db.all_books())
        self.last_recommendations = rec.recommend(rated, candidates, top_n=top_n)
        return self.last_recommendations

    def chatbot_introduce(self) -> str:
        return self.chatbot.introduce(self.last_recommendations,
                                      self.db.rated_books())

    def chatbot_answer(self, question: str) -> str:
        return self.chatbot.answer(question, self.last_recommendations,
                                   self.db.rated_books())

    @property
    def chatbot_mode(self) -> str:
        return self.chatbot.mode

    def close(self) -> None:
        self.db.close()
