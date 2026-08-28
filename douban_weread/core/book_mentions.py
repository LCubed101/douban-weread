from __future__ import annotations

import re
from dataclasses import dataclass


# OCR can insert a line break inside a book title or occasionally recognize
# 《》 as the visually similar 〈〉 pair. Keep the extractor conservative by
# still requiring an explicit pair of Chinese title marks.
_BOOK_TITLE_RE = re.compile(r"[《〈](?P<title>[^《》〈〉]{1,120})[》〉]")
_HAN_SPACE_RE = re.compile(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])")


@dataclass(slots=True, frozen=True)
class BookMention:
    title: str
    source: str = "book_marks"


def extract_book_mentions(text: str) -> tuple[BookMention, ...]:
    """Extract high-confidence book mentions without calling any provider.

    V1.1 prefers precision over recall: only explicit Chinese book-title marks
    are accepted. OCR line breaks/spaces between Chinese title characters are
    repaired, while generic corner quotes such as 「系统」 remain ignored.
    Duplicate titles collapse while preserving first-seen order.
    """

    if not text:
        return ()

    seen: set[str] = set()
    mentions: list[BookMention] = []
    for match in _BOOK_TITLE_RE.finditer(text):
        title = _normalize_title(match.group("title"))
        if not title:
            continue
        key = _dedupe_key(title)
        if key in seen:
            continue
        seen.add(key)
        mentions.append(BookMention(title=title))
    return tuple(mentions)


def _normalize_title(value: str) -> str:
    normalized = " ".join(value.split()).strip(" ，,。；;：:、")
    previous = None
    while normalized != previous:
        previous = normalized
        normalized = _HAN_SPACE_RE.sub("", normalized)
    return normalized


def _dedupe_key(value: str) -> str:
    return "".join(value.split()).casefold()
