from __future__ import annotations

import re
from dataclasses import dataclass


_BOOK_TITLE_RE = re.compile(r"《(?P<title>[^《》\n]{1,120})》")
_QUOTED_TITLE_RE = re.compile(r"「(?P<title>[^「」\n]{1,120})」")


@dataclass(slots=True, frozen=True)
class BookMention:
    title: str
    source: str = "explicit_title"


def extract_book_mentions(text: str) -> tuple[BookMention, ...]:
    """Extract high-confidence book mentions without calling any provider.

    V1.1 deliberately prefers precision over recall. Explicit Chinese book-title
    marks are accepted. Ambiguous prose is ignored rather than guessed.
    Duplicate titles collapse while preserving first-seen order.
    """

    if not text:
        return ()

    matches: list[tuple[int, str, str]] = []
    for pattern, source in (
        (_BOOK_TITLE_RE, "book_marks"),
        (_QUOTED_TITLE_RE, "corner_quotes"),
    ):
        for match in pattern.finditer(text):
            title = _normalize_title(match.group("title"))
            if title:
                matches.append((match.start(), title, source))

    matches.sort(key=lambda item: item[0])
    seen: set[str] = set()
    mentions: list[BookMention] = []
    for _, title, source in matches:
        key = _dedupe_key(title)
        if key in seen:
            continue
        seen.add(key)
        mentions.append(BookMention(title=title, source=source))
    return tuple(mentions)


def _normalize_title(value: str) -> str:
    return " ".join(value.split()).strip(" ，,。；;：:、")


def _dedupe_key(value: str) -> str:
    return "".join(value.split()).casefold()
