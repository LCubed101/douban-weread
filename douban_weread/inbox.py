from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from urllib.parse import urlparse

from douban_weread.core.models import Edition


_DOUBAN_SUBJECT_RE = re.compile(r"/subject/(?P<subject_id>\d+)/?")
_ISBN_CANDIDATE_RE = re.compile(r"(?i)(?:ISBN(?:-1[03])?[:：]?\s*)?([0-9Xx][0-9Xx\-\s]{8,20}[0-9Xx])")


class BookInboxInputKind(str, Enum):
    TEXT = "text"
    ISBN = "isbn"
    DOUBAN_URL = "douban_url"
    WEREAD_URL = "weread_url"
    IMAGE_PENDING = "image_pending"
    UNSUPPORTED = "unsupported"


class BookInboxResolutionKind(str, Enum):
    CONFIRM = "confirm"
    MULTIPLE_CANDIDATES = "multiple_candidates"
    NOT_FOUND = "not_found"
    PENDING_IMAGE = "pending_image"
    UNSUPPORTED = "unsupported"


@dataclass(slots=True, frozen=True)
class BookInboxRequest:
    """Provider-neutral representation of one user submission to the Book Inbox."""

    input_kind: BookInboxInputKind
    raw_text: str | None = None
    search_query: str | None = None
    isbn: str | None = None
    douban_subject_id: str | None = None
    source_url: str | None = None
    image_key: str | None = None


@dataclass(slots=True, frozen=True)
class BookInboxConfirmation:
    """A candidate Edition that must be confirmed before any state-changing action."""

    request: BookInboxRequest
    candidate: Edition
    prompt: str = "你想加入的是这本吗？"


@dataclass(slots=True, frozen=True)
class BookInboxResolution:
    kind: BookInboxResolutionKind
    request: BookInboxRequest
    confirmation: BookInboxConfirmation | None = None
    candidates: tuple[Edition, ...] = ()
    message: str | None = None


class BookInboxDoubanProvider(Protocol):
    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]: ...

    def search_by_isbn(self, isbn: str) -> Edition | None: ...

    def get_by_subject_id(self, subject_id: str) -> Edition | None: ...


class BookInboxService:
    """Resolve one Inbox request into a safe, non-mutating confirmation decision."""

    def __init__(self, douban_provider: BookInboxDoubanProvider, *, search_limit: int = 5) -> None:
        self.douban_provider = douban_provider
        self.search_limit = max(1, min(search_limit, 10))

    def resolve(self, request: BookInboxRequest) -> BookInboxResolution:
        if request.input_kind is BookInboxInputKind.DOUBAN_URL:
            subject_id = request.douban_subject_id or ""
            edition = self.douban_provider.get_by_subject_id(subject_id)
            if edition is None:
                return BookInboxResolution(
                    kind=BookInboxResolutionKind.NOT_FOUND,
                    request=request,
                    message="没有找到这个豆瓣图书条目。",
                )
            return _confirm(request, edition)

        if request.input_kind is BookInboxInputKind.ISBN:
            isbn = request.isbn or ""
            edition = self.douban_provider.search_by_isbn(isbn)
            if edition is None:
                return BookInboxResolution(
                    kind=BookInboxResolutionKind.NOT_FOUND,
                    request=request,
                    message=f"没有找到 ISBN {isbn} 对应的豆瓣版本。",
                )
            return _confirm(request, edition)

        if request.input_kind is BookInboxInputKind.TEXT:
            query = request.search_query or ""
            candidates = tuple(
                self.douban_provider.search_by_title(query, count=self.search_limit)
            )
            if not candidates:
                return BookInboxResolution(
                    kind=BookInboxResolutionKind.NOT_FOUND,
                    request=request,
                    message=f"没有找到《{query}》的豆瓣候选版本。",
                )
            if len(candidates) == 1:
                return _confirm(request, candidates[0])
            return BookInboxResolution(
                kind=BookInboxResolutionKind.MULTIPLE_CANDIDATES,
                request=request,
                candidates=candidates,
                message="找到多个豆瓣版本，请先确认具体版本。",
            )

        if request.input_kind is BookInboxInputKind.IMAGE_PENDING:
            return BookInboxResolution(
                kind=BookInboxResolutionKind.PENDING_IMAGE,
                request=request,
                message="图片已经收到，正在等待图片识别。",
            )

        if request.input_kind is BookInboxInputKind.WEREAD_URL:
            return BookInboxResolution(
                kind=BookInboxResolutionKind.UNSUPPORTED,
                request=request,
                message="微信读书链接暂时不会猜测书籍身份，请先发送书名或豆瓣链接。",
            )

        return BookInboxResolution(
            kind=BookInboxResolutionKind.UNSUPPORTED,
            request=request,
            message="暂时无法识别这条消息。",
        )


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

    isbn = extract_isbn(value)
    if isbn and _looks_like_isbn_only(value, isbn):
        return BookInboxRequest(
            input_kind=BookInboxInputKind.ISBN,
            raw_text=value,
            isbn=isbn,
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


def extract_isbn(text: str) -> str | None:
    """Return one normalized ISBN-10/13 candidate from arbitrary text."""

    for match in _ISBN_CANDIDATE_RE.finditer(text):
        normalized = re.sub(r"[^0-9Xx]", "", match.group(1)).upper()
        if len(normalized) in {10, 13}:
            return normalized
    return None


def _looks_like_isbn_only(raw: str, isbn: str) -> bool:
    stripped = re.sub(r"(?i)ISBN(?:-1[03])?[:：]?", "", raw)
    compact = re.sub(r"[^0-9Xx]", "", stripped).upper()
    return compact == isbn


def _confirm(request: BookInboxRequest, edition: Edition) -> BookInboxResolution:
    confirmation = BookInboxConfirmation(request=request, candidate=edition)
    return BookInboxResolution(
        kind=BookInboxResolutionKind.CONFIRM,
        request=request,
        confirmation=confirmation,
        candidates=(edition,),
    )
