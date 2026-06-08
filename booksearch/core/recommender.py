"""
recommender.py
--------------
The recommendation engine.

Idea (as requested in the brief):
  * Every book is turned into a point in a vector space.
  * The axes of that space come from the union of all genres and all moods
    across the library, plus a couple of numeric features (publish era,
    length). Title words are folded in too so that thematically-titled books
    cluster a little.
  * The user rates books they've read from 0..10. We build a single "taste
    vector" that is the rating-weighted, mean-centered average of the vectors
    of the books they rated. Books rated above the user's mean push the taste
    vector toward them; books rated below push it away.
  * We then score every unrated book by cosine similarity to the taste vector
    and return the top matches.

No third-party ML libraries are required — only the standard library and
(optionally) numpy if present. This keeps the desktop app easy to run.
"""

import math
import re
from typing import List, Dict, Any, Tuple


_WORD_RE = re.compile(r"[a-z][a-z'\-]+")
_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with",
    "at", "by", "from", "as", "is", "it", "its", "this", "that", "into",
    "vol", "volume", "book", "novel", "edition", "part",
}


def _title_tokens(title: str) -> List[str]:
    if not title:
        return []
    toks = _WORD_RE.findall(title.lower())
    return [t for t in toks if t not in _STOPWORDS and len(t) > 2]


class Recommender:
    """
    Builds a feature space from a list of book dicts and scores candidates
    against a user's ratings.
    """

    # Relative weights of each feature family in the combined vector.
    GENRE_WEIGHT = 1.0
    MOOD_WEIGHT = 1.4          # moods matter a bit more for "vibe" matching
    TITLE_WEIGHT = 0.35
    YEAR_WEIGHT = 0.5
    LENGTH_WEIGHT = 0.4

    def __init__(self, books: List[Dict[str, Any]]):
        self.books = books
        self._build_vocabulary()

    # ------------------------------------------------------------------ #
    # Vocabulary / axis construction
    # ------------------------------------------------------------------ #
    def _build_vocabulary(self) -> None:
        genres, moods, title_words = set(), set(), {}
        for b in self.books:
            for g in b.get("genres", []):
                genres.add(g.lower())
            for m in b.get("moods", []):
                moods.add(m.lower())
            for w in _title_tokens(b.get("title", "")):
                title_words[w] = title_words.get(w, 0) + 1

        # Keep only title words that appear in >=2 books, to reduce noise.
        common_title_words = {w for w, c in title_words.items() if c >= 2}

        self.genre_axes = sorted(genres)
        self.mood_axes = sorted(moods)
        self.title_axes = sorted(common_title_words)

        self.genre_index = {g: i for i, g in enumerate(self.genre_axes)}
        self.mood_index = {m: i for i, m in enumerate(self.mood_axes)}
        self.title_index = {w: i for i, w in enumerate(self.title_axes)}

        # Numeric feature normalization ranges.
        years = [b["publish_year"] for b in self.books if b.get("publish_year")]
        pages = [b["page_count"] for b in self.books if b.get("page_count")]
        self._year_min = min(years) if years else 1900
        self._year_max = max(years) if years else 2025
        self._page_min = min(pages) if pages else 50
        self._page_max = max(pages) if pages else 800

        self.dim = (len(self.genre_axes) + len(self.mood_axes)
                    + len(self.title_axes) + 2)

    # ------------------------------------------------------------------ #
    # Vectorization
    # ------------------------------------------------------------------ #
    def vectorize(self, book: Dict[str, Any]) -> List[float]:
        """Turn a single book dict into a feature vector."""
        vec = [0.0] * self.dim
        offset = 0

        # Genres (multi-hot, weighted)
        for g in book.get("genres", []):
            idx = self.genre_index.get(g.lower())
            if idx is not None:
                vec[offset + idx] = self.GENRE_WEIGHT
        offset += len(self.genre_axes)

        # Moods (multi-hot, weighted)
        for m in book.get("moods", []):
            idx = self.mood_index.get(m.lower())
            if idx is not None:
                vec[offset + idx] = self.MOOD_WEIGHT
        offset += len(self.mood_axes)

        # Title words (multi-hot, weighted)
        for w in _title_tokens(book.get("title", "")):
            idx = self.title_index.get(w)
            if idx is not None:
                vec[offset + idx] = self.TITLE_WEIGHT
        offset += len(self.title_axes)

        # Publish year (normalized 0..1)
        year = book.get("publish_year")
        if year and self._year_max > self._year_min:
            norm = (year - self._year_min) / (self._year_max - self._year_min)
            vec[offset] = norm * self.YEAR_WEIGHT
        offset += 1

        # Page count (normalized 0..1)
        pages = book.get("page_count")
        if pages and self._page_max > self._page_min:
            norm = (pages - self._page_min) / (self._page_max - self._page_min)
            vec[offset] = norm * self.LENGTH_WEIGHT
        offset += 1

        return vec

    # ------------------------------------------------------------------ #
    # Vector math (pure-python; numpy not required)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _dot(a: List[float], b: List[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    @staticmethod
    def _norm(a: List[float]) -> float:
        return math.sqrt(sum(x * x for x in a))

    def _cosine(self, a: List[float], b: List[float]) -> float:
        na, nb = self._norm(a), self._norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return self._dot(a, b) / (na * nb)

    # ------------------------------------------------------------------ #
    # Taste vector + recommendations
    # ------------------------------------------------------------------ #
    def build_taste_vector(
        self, rated_books: List[Dict[str, Any]]
    ) -> Tuple[List[float], float]:
        """
        Build the user's taste vector from rated books.

        Returns (taste_vector, mean_score). Each rated book contributes its
        vector scaled by (score - mean_score), so liked books pull the taste
        vector toward them and disliked books push it away.
        """
        if not rated_books:
            return [0.0] * self.dim, 5.0

        scores = [b.get("user_score", 5.0) for b in rated_books]
        mean_score = sum(scores) / len(scores)

        taste = [0.0] * self.dim
        for b in rated_books:
            weight = b.get("user_score", 5.0) - mean_score
            # If every score is identical, fall back to a gentle positive pull.
            if weight == 0:
                weight = (b.get("user_score", 5.0) - 5.0) or 0.1
            vec = self.vectorize(b)
            for i in range(self.dim):
                taste[i] += weight * vec[i]
        return taste, mean_score

    def recommend(
        self,
        rated_books: List[Dict[str, Any]],
        candidates: List[Dict[str, Any]],
        top_n: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Score `candidates` against the taste vector built from `rated_books`
        and return the top_n, each annotated with a 'match' field (0..100)
        and a 'reasons' list explaining the overlap.
        """
        taste, mean_score = self.build_taste_vector(rated_books)
        if self._norm(taste) == 0:
            # No usable signal (e.g. all ratings equal & == 5). Fall back to
            # ranking by Open Library rating then recency.
            ranked = sorted(
                candidates,
                key=lambda b: (b.get("rating") or 0, b.get("publish_year") or 0),
                reverse=True,
            )
            out = []
            for b in ranked[:top_n]:
                c = dict(b)
                c["match"] = None
                c["reasons"] = ["Popular pick (not enough rating signal yet)"]
                out.append(c)
            return out

        # Aggregate the genres/moods of the user's *liked* books for reasons.
        liked = [b for b in rated_books
                 if b.get("user_score", 5.0) >= mean_score]
        liked_genres = self._top_features(liked, "genres")
        liked_moods = self._top_features(liked, "moods")

        scored = []
        for cand in candidates:
            vec = self.vectorize(cand)
            sim = self._cosine(taste, vec)
            scored.append((sim, cand))

        scored.sort(key=lambda t: t[0], reverse=True)

        results = []
        # Map cosine (-1..1) onto a friendlier 0..100 match percentage.
        for sim, cand in scored[:top_n]:
            match = max(0.0, min(100.0, (sim + 1) / 2 * 100))
            c = dict(cand)
            c["match"] = round(match, 1)
            c["reasons"] = self._explain(cand, liked_genres, liked_moods)
            results.append(c)
        return results

    # ------------------------------------------------------------------ #
    # Explanations
    # ------------------------------------------------------------------ #
    @staticmethod
    def _top_features(books: List[Dict[str, Any]], field: str,
                      top: int = 8) -> List[str]:
        counts = {}
        for b in books:
            for v in b.get(field, []):
                counts[v.lower()] = counts.get(v.lower(), 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        return [k for k, _ in ranked[:top]]

    @staticmethod
    def _explain(cand: Dict[str, Any], liked_genres: List[str],
                 liked_moods: List[str]) -> List[str]:
        reasons = []
        cand_genres = {g.lower() for g in cand.get("genres", [])}
        cand_moods = {m.lower() for m in cand.get("moods", [])}

        gmatch = [g for g in liked_genres if g in cand_genres]
        mmatch = [m for m in liked_moods if m in cand_moods]

        if gmatch:
            pretty = ", ".join(g.title() for g in gmatch[:3])
            reasons.append(f"Shares genres you enjoy: {pretty}")
        if mmatch:
            pretty = ", ".join(m.title() for m in mmatch[:3])
            reasons.append(f"Matches the mood you like: {pretty}")
        if not reasons:
            reasons.append("Similar overall profile to your highly-rated books")
        return reasons
