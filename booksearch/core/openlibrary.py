"""
openlibrary.py
--------------
A small client for the Open Library API (https://openlibrary.org).

Two jobs:
  1. seed_books()      -> bulk-fetch books for a set of subjects to populate
                          the local database the first time the app runs.
  2. fetch_book()      -> look up a single book by title (+ optional author)
                          when the user wants to rate a book that isn't in the
                          local database yet.

Open Library is free and needs no API key. We also derive simple "mood"
tags from each book's subjects so the recommender has a mood dimension to
work with, exactly as the project asks for [title, genre, mood].

All network calls degrade gracefully: if the network is unavailable the
functions return empty/None and the caller falls back to whatever is local.
"""

import json
import time
import urllib.parse
import urllib.request
from typing import List, Dict, Optional, Any


OL_BASE = "https://openlibrary.org"
COVER_BASE = "https://covers.openlibrary.org/b/id"
USER_AGENT = "BookSearchPlatform/1.0 (educational project)"


# --------------------------------------------------------------------------- #
# Mood inference
# --------------------------------------------------------------------------- #
# Open Library gives "subjects" (genres/keywords) but no explicit mood. We map
# subject keywords to a small, fixed mood vocabulary so every book can be placed
# on the same mood axes. This keeps the vector space consistent.
MOOD_KEYWORDS = {
    "dark": ["murder", "horror", "war", "tragedy", "crime", "death", "gothic",
             "dystopia", "noir", "thriller"],
    "uplifting": ["humor", "comedy", "inspiration", "hope", "friendship",
                  "feel-good", "happiness", "self-help"],
    "romantic": ["romance", "love", "relationships", "marriage", "passion"],
    "adventurous": ["adventure", "quest", "journey", "exploration", "pirates",
                    "treasure", "survival", "expedition"],
    "reflective": ["philosophy", "memoir", "essays", "spirituality",
                   "meditation", "introspection", "biography"],
    "mysterious": ["mystery", "detective", "suspense", "secret", "espionage",
                   "investigation", "puzzle"],
    "whimsical": ["fantasy", "fairy tales", "magic", "wonder", "myth",
                  "fairy", "dragons"],
    "tense": ["suspense", "thriller", "conspiracy", "chase", "danger",
              "psychological"],
    "epic": ["epic", "saga", "empire", "battle", "kingdom", "history"],
    "cozy": ["cooking", "gardening", "domestic", "small town", "comfort",
             "slice of life"],
}


def infer_moods(subjects: List[str]) -> List[str]:
    """Return a list of mood tags inferred from a book's subjects."""
    if not subjects:
        return []
    text = " ".join(s.lower() for s in subjects)
    moods = []
    for mood, keywords in MOOD_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            moods.append(mood)
    return moods


def _normalize_subjects(subjects: List[str], limit: int = 12) -> List[str]:
    """Clean up subject strings: title-case-ish, dedupe, cap the count."""
    seen = set()
    cleaned = []
    for s in subjects or []:
        s = s.strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(s)
        if len(cleaned) >= limit:
            break
    return cleaned


def _http_get_json(url: str, timeout: float = 15.0) -> Optional[Any]:
    """GET a URL and parse JSON, returning None on any failure."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except Exception:
        return None


def _cover_url(cover_id: Optional[int]) -> Optional[str]:
    if not cover_id:
        return None
    return f"{COVER_BASE}/{cover_id}-M.jpg"


# --------------------------------------------------------------------------- #
# Bulk seeding by subject
# --------------------------------------------------------------------------- #
def _parse_search_doc(doc: Dict[str, Any],
                      seed_subject: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Turn one search.json doc into our book dict."""
    key = doc.get("key")
    if not key:
        return None
    authors = doc.get("author_name", [])
    subjects = _normalize_subjects(doc.get("subject", []))
    if seed_subject:
        pretty = seed_subject.replace("_", " ").title()
        if pretty not in subjects:
            subjects.insert(0, pretty)
    return {
        "ol_key": key,
        "title": doc.get("title", "Untitled"),
        "author": ", ".join(authors) if authors else None,
        "genres": subjects,
        "moods": infer_moods(subjects),
        "description": doc.get("first_sentence", [None])[0]
        if isinstance(doc.get("first_sentence"), list) else doc.get("first_sentence"),
        "publish_year": doc.get("first_publish_year"),
        "page_count": doc.get("number_of_pages_median"),
        "rating": doc.get("ratings_average"),
        "cover_url": _cover_url(doc.get("cover_i")),
    }


# Fields we ask the search API for — keeps responses small but complete.
_SEARCH_FIELDS = ",".join([
    "key", "title", "author_name", "first_publish_year",
    "subject", "cover_i", "number_of_pages_median",
    "ratings_average", "first_sentence",
])


def fetch_subject_search(subject: str, limit: int = 60,
                         sort: Optional[str] = None,
                         min_year: Optional[int] = None,
                         max_year: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Fetch works for a subject using the SEARCH API (not the subjects endpoint).

    The search API supports sorting and year filtering, which lets us pull
    modern, varied books instead of only the most-held public-domain classics
    that the subjects endpoint returns. Pages through results to reach `limit`.
    """
    slug = subject.lower().replace(" ", "_")
    per_page = 100  # search API max page size
    collected: List[Dict[str, Any]] = []
    page = 1

    # Build the year filter clause if requested.
    q = f"subject:{slug}"
    if min_year and max_year:
        q += f" AND first_publish_year:[{min_year} TO {max_year}]"
    elif min_year:
        q += f" AND first_publish_year:[{min_year} TO 2030]"

    while len(collected) < limit and page <= 5:
        params = {
            "q": q,
            "fields": _SEARCH_FIELDS,
            "limit": min(per_page, limit - len(collected)),
            "page": page,
        }
        if sort:
            params["sort"] = sort
        url = f"{OL_BASE}/search.json?{urllib.parse.urlencode(params)}"
        data = _http_get_json(url)
        if not data or not data.get("docs"):
            break
        for doc in data["docs"]:
            book = _parse_search_doc(doc, seed_subject=subject)
            if book:
                collected.append(book)
        if len(data["docs"]) < params["limit"]:
            break  # no more pages
        page += 1
        time.sleep(0.2)

    return collected


def fetch_subject(subject: str, limit: int = 60) -> List[Dict[str, Any]]:
    """
    Fetch a diverse set of books for a subject by combining several strategies:
      * highest-rated overall (quality classics + modern favourites)
      * most recent (modern books, breaks the public-domain bias)
      * a plain relevance pass (breadth)
    The union is deduped, giving a much more varied and contemporary mix than
    the old subjects-endpoint approach.
    """
    out: Dict[str, Any] = {}

    # Split the budget across strategies so no single flavour dominates.
    by_rating = fetch_subject_search(subject, limit=max(20, limit // 3),
                                     sort="rating")
    by_new = fetch_subject_search(subject, limit=max(20, limit // 3),
                                  sort="new", min_year=2000)
    by_relevance = fetch_subject_search(subject, limit=max(20, limit // 3))

    for batch in (by_rating, by_new, by_relevance):
        for b in batch:
            if b.get("ol_key"):
                out[b["ol_key"]] = b
    return list(out.values())


def seed_books(subjects: List[str], per_subject: int = 60,
               progress_cb=None) -> List[Dict[str, Any]]:
    """
    Fetch books across several subjects to populate the database, using the
    diversity-oriented fetch_subject above.
    `progress_cb(done, total, label)` is called as each subject finishes.
    """
    all_books = []
    total = len(subjects)
    for i, subj in enumerate(subjects, start=1):
        books = fetch_subject(subj, limit=per_subject)
        all_books.extend(books)
        if progress_cb:
            progress_cb(i, total, subj)
        time.sleep(0.2)  # be polite to the API
    # Dedupe by ol_key across all subjects.
    unique = {}
    for b in all_books:
        if b.get("ol_key"):
            unique[b["ol_key"]] = b
    return list(unique.values())


# --------------------------------------------------------------------------- #
# Single book lookup (for books not yet in the DB)
# --------------------------------------------------------------------------- #
def fetch_book(title: str, author: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Search Open Library for a single book by title (and optional author),
    returning the best match enriched with genres, moods, and a description.
    Returns None if nothing is found.
    """
    params = {"title": title, "limit": 5}
    if author:
        params["author"] = author
    query = urllib.parse.urlencode(params)
    url = f"{OL_BASE}/search.json?{query}"
    data = _http_get_json(url)
    if not data or not data.get("docs"):
        return None

    doc = data["docs"][0]
    work_key = doc.get("key")  # e.g. "/works/OL12345W"

    authors = doc.get("author_name", [])
    subjects = _normalize_subjects(doc.get("subject", []))

    book = {
        "ol_key": work_key,
        "title": doc.get("title", title),
        "author": ", ".join(authors) if authors else author,
        "genres": subjects,
        "moods": infer_moods(subjects),
        "description": None,
        "publish_year": doc.get("first_publish_year"),
        "page_count": doc.get("number_of_pages_median"),
        "rating": doc.get("ratings_average"),
        "cover_url": _cover_url(doc.get("cover_i")),
    }

    # Enrich with the work's description and richer subject list.
    if work_key:
        work = _http_get_json(f"{OL_BASE}{work_key}.json")
        if work:
            desc = work.get("description")
            if isinstance(desc, dict):
                desc = desc.get("value")
            book["description"] = desc
            work_subjects = _normalize_subjects(
                (book["genres"] or []) + (work.get("subjects", []) or [])
            )
            if work_subjects:
                book["genres"] = work_subjects
                book["moods"] = infer_moods(work_subjects)

    return book


def search_titles(title: str, limit: int = 8) -> List[Dict[str, Any]]:
    """
    Lightweight title search returning multiple candidates so the UI can let
    the user disambiguate. Each result has title/author/year/ol_key.
    """
    query = urllib.parse.urlencode({"title": title, "limit": limit})
    url = f"{OL_BASE}/search.json?{query}"
    data = _http_get_json(url)
    if not data or not data.get("docs"):
        return []
    results = []
    for doc in data["docs"][:limit]:
        results.append({
            "ol_key": doc.get("key"),
            "title": doc.get("title", ""),
            "author": ", ".join(doc.get("author_name", [])) or None,
            "publish_year": doc.get("first_publish_year"),
            "cover_url": _cover_url(doc.get("cover_i")),
        })
    return results
