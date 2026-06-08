"""
chatbot.py
----------
The "AI librarian" that introduces recommended books to the user in a warm,
conversational way.

Two modes:
  * If an Anthropic API key is available (env var ANTHROPIC_API_KEY) and the
    `anthropic` package is installed, the bot uses Claude to generate a fresh,
    natural introduction for each recommendation set.
  * Otherwise it falls back to a fully offline, template-based generator so
    the application still works with zero configuration or network access.

The public surface is a single class, BookChatbot, with:
    introduce(recommendations, rated_books) -> str
    answer(question, recommendations, rated_books) -> str
"""

import os
import random
from typing import List, Dict, Any, Optional


SYSTEM_PROMPT = (
    "You are a warm, knowledgeable librarian inside a desktop book-discovery "
    "app. You introduce a short list of book recommendations to a reader, "
    "explaining briefly why each suits their taste based on the genres and "
    "moods they've enjoyed. Keep it friendly and concise: a one-line opener, "
    "then one short paragraph (2-3 sentences) per book. Do not invent plot "
    "details you aren't given. Never use bullet lists; write in flowing prose."
)


class BookChatbot:
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model
        self._client = None
        self._mode = "offline"
        self._init_client()

    def _init_client(self) -> None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return
        try:
            import anthropic  # type: ignore
            self._client = anthropic.Anthropic(api_key=key)
            self._mode = "online"
        except Exception:
            self._client = None
            self._mode = "offline"

    @property
    def mode(self) -> str:
        return self._mode

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def introduce(
        self,
        recommendations: List[Dict[str, Any]],
        rated_books: List[Dict[str, Any]],
    ) -> str:
        if not recommendations:
            return ("I couldn't find anything to recommend yet. Try rating a "
                    "few more books you've read so I can learn your taste!")
        if self._mode == "online":
            try:
                return self._introduce_online(recommendations, rated_books)
            except Exception:
                # Network or API hiccup: fall back gracefully.
                return self._introduce_offline(recommendations, rated_books)
        return self._introduce_offline(recommendations, rated_books)

    def answer(
        self,
        question: str,
        recommendations: List[Dict[str, Any]],
        rated_books: List[Dict[str, Any]],
    ) -> str:
        if self._mode == "online":
            try:
                return self._answer_online(question, recommendations, rated_books)
            except Exception:
                return self._answer_offline(question, recommendations)
        return self._answer_offline(question, recommendations)

    # ------------------------------------------------------------------ #
    # Online (Claude) implementations
    # ------------------------------------------------------------------ #
    def _context_block(self, recommendations, rated_books) -> str:
        liked = sorted(rated_books, key=lambda b: b.get("user_score", 0),
                       reverse=True)[:5]
        liked_str = "; ".join(
            f"{b['title']} (you rated {b.get('user_score')}/10)" for b in liked
        ) or "none yet"

        rec_lines = []
        for r in recommendations:
            genres = ", ".join(r.get("genres", [])[:4]) or "unknown"
            moods = ", ".join(r.get("moods", [])) or "unspecified"
            match = r.get("match")
            match_str = f"{match}% match" if match is not None else "popular pick"
            desc = (r.get("description") or "").strip().replace("\n", " ")
            if len(desc) > 280:
                desc = desc[:280] + "..."
            rec_lines.append(
                f"- {r['title']} by {r.get('author') or 'Unknown'} "
                f"[{match_str}; genres: {genres}; mood: {moods}]"
                + (f" Summary: {desc}" if desc else "")
            )
        rec_str = "\n".join(rec_lines)
        return (f"Books the reader has enjoyed: {liked_str}.\n\n"
                f"Recommendations to introduce:\n{rec_str}")

    def _introduce_online(self, recommendations, rated_books) -> str:
        context = self._context_block(recommendations, rated_books)
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=900,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    "Please introduce these recommendations to me.\n\n" + context
                ),
            }],
        )
        return "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        ).strip()

    def _answer_online(self, question, recommendations, rated_books) -> str:
        context = self._context_block(recommendations, rated_books)
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=700,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    f"Here is the current recommendation context:\n\n{context}\n\n"
                    f"The reader asks: {question}\n\n"
                    "Answer helpfully, only using the information given."
                ),
            }],
        )
        return "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        ).strip()

    # ------------------------------------------------------------------ #
    # Offline template implementations
    # ------------------------------------------------------------------ #
    _OPENERS = [
        "I've pulled together a few books I think you'll love.",
        "Based on what you've enjoyed, here are some titles worth your time.",
        "Here's a little stack of recommendations tailored to your taste.",
        "I had a look through the shelves and these stood out for you.",
    ]

    def _introduce_offline(self, recommendations, rated_books) -> str:
        liked = sorted(rated_books, key=lambda b: b.get("user_score", 0),
                       reverse=True)
        parts = [random.choice(self._OPENERS)]

        if liked:
            top = liked[0]
            parts[0] += (f" Since you rated \u201c{top['title']}\u201d "
                         f"{top.get('user_score')}/10, I leaned in that direction.")

        for i, r in enumerate(recommendations, start=1):
            author = r.get("author") or "an unknown author"
            sentence = f"\n\n{i}. \u201c{r['title']}\u201d by {author}."

            match = r.get("match")
            if match is not None:
                sentence += f" It's about a {match:.0f}% match for your taste."

            reasons = r.get("reasons") or []
            if reasons:
                sentence += " " + reasons[0] + "."

            desc = (r.get("description") or "").strip()
            if desc:
                # First sentence or ~200 chars of the description.
                snippet = desc.split(". ")[0].strip()
                if len(snippet) > 200:
                    snippet = snippet[:200].rstrip() + "..."
                elif not snippet.endswith((".", "!", "?")):
                    snippet += "."
                sentence += f" {snippet}"
            elif r.get("genres"):
                g = ", ".join(r["genres"][:3])
                sentence += f" Expect themes around {g.lower()}."

            parts.append(sentence)

        parts.append("\n\nWant me to tell you more about any of these, or "
                     "narrow it down by mood?")
        return "".join(parts)

    def _answer_offline(self, question, recommendations) -> str:
        q = question.lower().strip()

        # Try to match a specific recommended title mentioned in the question.
        for r in recommendations:
            title_words = r["title"].lower().split()
            if r["title"].lower() in q or (
                len(title_words) > 1
                and sum(w in q for w in title_words) >= max(2, len(title_words) // 2)
            ):
                return self._describe_book_offline(r)

        # Mood-based filtering.
        for mood in ["dark", "uplifting", "romantic", "adventurous",
                     "reflective", "mysterious", "whimsical", "tense",
                     "epic", "cozy"]:
            if mood in q:
                matches = [r for r in recommendations
                           if mood in [m.lower() for m in r.get("moods", [])]]
                if matches:
                    titles = ", ".join(f"\u201c{m['title']}\u201d" for m in matches)
                    return (f"For a {mood} mood, I'd point you to {titles}. "
                            "Would you like a fuller description of any of them?")
                return (f"None of the current picks lean especially {mood}, but "
                        "I can re-run recommendations if you rate a few more "
                        f"{mood} books.")

        if any(w in q for w in ["shortest", "short", "quick", "page", "length"]):
            with_pages = [r for r in recommendations if r.get("page_count")]
            if with_pages:
                shortest = min(with_pages, key=lambda r: r["page_count"])
                return (f"The shortest of these is \u201c{shortest['title']}\u201d "
                        f"at about {shortest['page_count']} pages.")

        # Generic fallback: re-list the top picks.
        titles = ", ".join(f"\u201c{r['title']}\u201d" for r in recommendations[:5])
        return ("I can tell you more about any of the recommendations: "
                f"{titles}. Just name one, or ask me by mood "
                "(e.g. 'something uplifting').")

    @staticmethod
    def _describe_book_offline(r: Dict[str, Any]) -> str:
        author = r.get("author") or "an unknown author"
        lines = [f"\u201c{r['title']}\u201d is by {author}"]
        if r.get("publish_year"):
            lines[0] += f", first published in {r['publish_year']}"
        lines[0] += "."

        if r.get("genres"):
            lines.append(f"It sits in the {', '.join(r['genres'][:4]).lower()} "
                         "space.")
        if r.get("moods"):
            lines.append(f"The overall mood is {', '.join(r['moods'])}.")
        desc = (r.get("description") or "").strip()
        if desc:
            if len(desc) > 400:
                desc = desc[:400].rstrip() + "..."
            lines.append(desc)
        if r.get("match") is not None:
            lines.append(f"Overall it's roughly a {r['match']:.0f}% match for "
                         "your taste.")
        return " ".join(lines)
