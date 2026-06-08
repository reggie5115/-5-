# Inkwell — Book Discovery & Recommendation Platform

A desktop application (Python + Tkinter) that recommends books you'll likely
enjoy. It builds a local book database from **Open Library**, represents every
book as a point in a **vector space** built from genres and moods, learns your
taste from books you rate 0–10, and recommends new titles ranked by cosine
similarity. An **AI librarian chatbot** then introduces your recommendations
and answers follow-up questions.

![overview](docs/overview.txt)

## Features

- **Local library** seeded from Open Library across many genres (title, author,
  genres, inferred moods, year, page count, cover).
- **Vector-space recommender** — genres + moods + title themes + recency +
  length form the axes; your ratings build a "taste vector"; candidates are
  scored by cosine similarity. Books you rate highly pull recommendations
  toward them; low-rated books push them away.
- **0–10 rating** of any book you've read, via a clean slider + star widget.
- **Add unknown books** — if a book isn't in your library, search Open Library
  to pull in its details (description, subjects, moods) and add it.
- **AI librarian chatbot** — introduces each recommendation in natural prose
  and answers questions like *"tell me about X"* or *"anything dark?"*.
  Uses Claude if configured, otherwise a built-in offline librarian.
- **Clean, modern UI** — warm "library" palette, sidebar navigation, cards,
  scrollable views, no external UI dependencies.

## Requirements

- **Python 3.8+** with **Tkinter** (ships with most Python installs).
  - Windows / macOS: included with the standard python.org installer.
  - Debian/Ubuntu Linux: `sudo apt install python3-tk`
  - Fedora: `sudo dnf install python3-tkinter`
- An internet connection on **first run** (to seed the library) and when using
  **Add a Book**. After seeding, browsing/rating/recommending work offline.

No third-party Python packages are required.

### Optional: smarter chatbot via Claude

The chatbot works fully offline out of the box. To have it use Anthropic's
Claude for richer, more natural introductions:

```bash
pip install anthropic
export ANTHROPIC_API_KEY="your-key-here"     # Windows: set ANTHROPIC_API_KEY=...
```

If the key/package aren't present, Inkwell automatically falls back to the
offline librarian — nothing breaks.

## Running

```bash
cd booksearch
python main.py
```

On first launch a short setup dialog fetches books from Open Library
(this takes ~10–20 seconds). After that the library is cached locally in
the app's own `data/library.db` file, so the whole project is self-contained
and easy to back up or move.

## How to use

1. **Library** — browse or search, click **Rate** on books you've read and
   give each a 0–10 score.
2. **My Ratings** — review/edit/remove your scores. These drive everything.
3. **Recommend** — click **Generate recommendations**. Cards appear on the
   right with a match %, and the AI librarian introduces them on the left.
   Ask it follow-up questions in the chat box.
4. **Add a Book** — can't find something? Search Open Library, pick the right
   edition, and it's added (and you can rate it immediately).

> Tip: rate at least 3–5 books, including some you *didn't* like (low scores),
> for the sharpest recommendations — disliked books actively steer results away
> from those traits.

## Project structure

```
booksearch/
├── main.py                 # entry point
├── core/
│   ├── database.py         # SQLite storage (books + your ratings)
│   ├── openlibrary.py      # Open Library client + mood inference
│   ├── recommender.py      # vector space + cosine-similarity engine
│   ├── chatbot.py          # AI librarian (Claude or offline fallback)
│   └── app_controller.py   # glue between GUI and core
└── gui/
    ├── theme.py            # colors, fonts, scrollable helper
    ├── widgets.py          # BookCard, StarRating, chips
    └── main_window.py      # the full windowed UI
```

## How the recommendation works (short version)

Each book becomes a vector. Axes = every genre + every mood (weighted a bit
higher, since "vibe" matters for matching) + recurring title words + normalized
publish year + normalized length. Your taste vector is the **rating-weighted,
mean-centered** sum of the vectors of books you rated: a book scored above your
personal average adds its vector; one below subtracts it. Each unrated book is
then scored by cosine similarity to that taste vector, mapped to a friendly
0–100% match, and annotated with the genres/moods it shares with your
favourites.

## Notes & limitations

- Moods are *inferred* from Open Library subjects via a keyword map (see
  `MOOD_KEYWORDS` in `openlibrary.py`) — Open Library has no explicit mood
  field. You can extend that map to taste.
- The recommender is intentionally dependency-free (pure Python math), so it's
  easy to run anywhere; for very large libraries you could swap in numpy.
- Cover images are fetched as URLs but not displayed in this build to keep the
  app lightweight and offline-friendly; the data is stored if you want to add
  image rendering (e.g. via Pillow).
