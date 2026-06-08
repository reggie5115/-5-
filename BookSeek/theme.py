import json
import time
import urllib.parse
import urllib.request
from typing import List, Dict, Optional, Any

OL_BASE = "https://openlibrary.org"
COVER_BASE = "https://covers.openlibrary.org/b/id"
USER_AGENT = "BookSeek/0.1 (educational project)"


def _http_get_json(url: str, timeout: float = 15.0) -> Optional[Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _cover_url(cover_id: Optional[int]) -> Optional[str]:
    if not cover_id:
        return None
    return f"{COVER_BASE}/{cover_id}-M.jpg"


def fetch_subject(subject: str, limit: int = 50) -> List[Dict[str, Any]]:
    """First cut: use the /subjects/<name>.json endpoint."""
    slug = subject.lower().replace(" ", "_")
    url = f"{OL_BASE}/subjects/{slug}.json?limit={limit}"
    data = _http_get_json(url)
    if not data or not data.get("works"):
        return []
    books = []
    for w in data["works"]:
        authors = [a.get("name") for a in w.get("authors", []) if a.get("name")]
        books.append({
            "ol_key": w.get("key"),
            "title": w.get("title", "Untitled"),
            "author": ", ".join(authors) if authors else None,
            "genres": [subject.replace("_", " ").title()],
            "publish_year": w.get("first_publish_year"),
            "cover_url": _cover_url(w.get("cover_id")),
        })
    return books


def seed_books(subjects: List[str], per_subject: int = 50) -> List[Dict[str, Any]]:
    all_books = []
    for subj in subjects:
        all_books.extend(fetch_subject(subj, limit=per_subject))
        time.sleep(0.2)
    unique = {}
    for b in all_books:
        if b.get("ol_key"):
            unique[b["ol_key"]] = b
    return list(unique.values())
