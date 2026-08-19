from __future__ import annotations

import re
from typing import Any, Mapping

from douban_weread.core.models import Edition


_SPACE_RE = re.compile(r"\s+")
_DATE_RE = re.compile(r"(?P<year>\d{4})(?:\D+(?P<month>\d{1,2}))?")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return _SPACE_RE.sub(" ", str(value)).strip()


def normalize_people(value: Any) -> list[str]:
    """Normalize author/translator fields into a stable list of names."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = [value]

    result: list[str] = []
    for item in items:
        text = clean_text(item)
        if text and text not in result:
            result.append(text)
    return result


def normalize_isbn(value: Any) -> str | None:
    normalized = "".join(char for char in str(value or "") if char.isdigit() or char in "Xx").upper()
    if len(normalized) not in {10, 13}:
        return None
    return normalized


def normalize_publish_date(value: Any) -> str | None:
    """Normalize common Douban publication dates to YYYY or YYYY-MM.

    Unknown formats are preserved as cleaned text rather than discarded.
    """
    text = clean_text(value)
    if not text:
        return None

    match = _DATE_RE.search(text)
    if not match:
        return text

    year = match.group("year")
    month = match.group("month")
    if not month:
        return year

    month_number = int(month)
    if 1 <= month_number <= 12:
        return f"{year}-{month_number:02d}"
    return year


def extract_cover_url(raw: Mapping[str, Any]) -> str | None:
    images = raw.get("images")
    if isinstance(images, Mapping):
        for key in ("large", "medium", "small"):
            value = clean_text(images.get(key))
            if value:
                return value
    image = clean_text(raw.get("image"))
    return image or None


def normalize_douban_edition(raw: Any) -> Edition | None:
    """Map a raw Douban book payload to the provider-independent Edition model."""
    if not isinstance(raw, Mapping):
        return None

    title = clean_text(raw.get("title"))
    douban_id = clean_text(raw.get("id"))
    if not title or not douban_id:
        return None

    isbn = normalize_isbn(raw.get("isbn13")) or normalize_isbn(raw.get("isbn10"))

    return Edition(
        title=title,
        authors=normalize_people(raw.get("author")),
        translators=normalize_people(raw.get("translator")),
        publisher=clean_text(raw.get("publisher")) or None,
        publish_date=normalize_publish_date(raw.get("pubdate")),
        isbn=isbn,
        cover_url=extract_cover_url(raw),
        douban_id=douban_id,
        source_metadata=dict(raw),
    )
