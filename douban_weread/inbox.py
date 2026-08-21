from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

from douban_weread.core.models import Edition


_DOUBAN_SUBJECT_RE = re.compile(r"/subject/(?P<subject_id>\d+)/?")


class BookInboxInputKind(str, Enum):
    TEXT = "text"
    DOUBAN_URL = "douban_url"
    WEREAD_URL = "weread_url"
    IMAGE_PENDING = "image_pending"
    UNSUPPORTED = "unsupported"


@dataclass(slots=True, frozen=True)
class BookInboxRequest:
    """Provider-neutral representation of one user submission to the Book Inbox."""

    input_kind: BookInboxInputKind
    raw_text: str | None = None
    search_query: str | None = None
    douban_subject_id: str | None = None
    source_url: str | None = None
    image_key: str | None = None


@dataclass(slots=True, frozen=True)
class BookInboxConfirmation:
    """A candidate Edition that must be confirmed before any state-changing action."""

    request: BookInboxRequest
    candidate: Edition
    prompt: str = "你想加入的是这本吗？"


def request_from_text(text: str) -> BookInboxRequest:
    value = " ".join(text.split()).strip()
    if not value:
        return BookInboxRequest(input_kind=BookInboxInputKind.UNSUPPORTED)

    parsed = urlparse(value)
    host = parsed.netloc.casefold()
    if host in {"book.douban.com", "www.douban.com"}:
        match = _DOUBAN_SUBJECT_RE.search(parsed.path)
        if match:
            return BookInboxRequest(
                input_kind=BookInboxInputKind.DOUBAN_URL,
                raw_text=value,
                douban_subject_id=match.group("subject_id"),
                source_url=value,
            )

    if host.endswith("weread.qq.com"):
        return BookInboxRequest(
            input_kind=BookInboxInputKind.WEREAD_URL,
            raw_text=value,
            source_url=value,
        )

    return BookInboxRequest(
        input_kind=BookInboxInputKind.TEXT,
        raw_text=value,
        search_query=value,
    )


def request_from_image_key(image_key: str) -> BookInboxRequest:
    value = image_key.strip()
    if not value:
        return BookInboxRequest(input_kind=BookInboxInputKind.UNSUPPORTED)
    return BookInboxRequest(
        input_kind=BookInboxInputKind.IMAGE_PENDING,
        image_key=value,
    )
