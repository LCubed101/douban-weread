from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from urllib.parse import urlparse

from douban_weread.core.models import Edition


_DOUBAN_SUBJECT_RE = re.compile(r"/subject/(?P<subject_id>\d+)/?")


class BookInboxInputKind(str, Enum):
    TEXT = "text"
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
            confirmation = BookInboxConfirmation(request=request, candidate=edition)
            return BookInboxResolution(
                kind=BookInboxResolutionKind.CONFIRM,
                request=request,
                confirmation=confirmation,
                candidates=(edition,),
            )

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
                confirmation = BookInboxConfirmation(request=request, candidate=candidates[0])
                return BookInboxResolution(
                    kind=BookInboxResolutionKind.CONFIRM,
                    request=request,
                    confirmation=confirmation,
                    candidates=candidates,
                )
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
                message="图片已经收到，图片识别将在下一步接入。",
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
