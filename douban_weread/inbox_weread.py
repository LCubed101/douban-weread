from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from douban_weread.alignment import align_to_weread
from douban_weread.core.models import Edition, WeReadStatus
from douban_weread.providers.weread import WeReadClient, WeReadProviderError


class WeReadCatalogProvider(Protocol):
    def search_books(self, keyword: str, *, count: int = 10): ...

    def get_book(self, book_id: str) -> Edition | None: ...


class WeReadLookupKind(str, Enum):
    EXACT = "exact"
    ALTERNATIVE = "alternative"
    UNAVAILABLE = "unavailable"
    NOT_FOUND = "not_found"


@dataclass(slots=True, frozen=True)
class WeReadLookupResult:
    kind: WeReadLookupKind
    source_title: str
    selected_edition: Edition | None
    deep_link: str | None
    message: str


class WeReadEditionLookup:
    """Read-only post-Douban lookup for a readable WeRead Edition."""

    def __init__(
        self,
        provider: WeReadCatalogProvider | None = None,
        *,
        search_limit: int = 5,
    ) -> None:
        self.provider = provider or WeReadClient(api_key=os.getenv("WEREAD_API_KEY", ""))
        self.search_limit = max(1, min(search_limit, 20))

    def lookup(self, source_edition: Edition) -> WeReadLookupResult:
        aligned = align_to_weread(
            source_edition,
            self.provider,
            limit=self.search_limit,
        )
        intent = aligned.intent
        selected = intent.selected_edition
        deep_link = intent.source_url

        if intent.weread_status is WeReadStatus.AVAILABLE_EXACT and selected is not None:
            return WeReadLookupResult(
                kind=WeReadLookupKind.EXACT,
                source_title=source_edition.title,
                selected_edition=selected,
                deep_link=deep_link,
                message=_available_message(source_edition, selected, exact=True, deep_link=deep_link),
            )

        if intent.weread_status is WeReadStatus.AVAILABLE_ALTERNATIVE and selected is not None:
            return WeReadLookupResult(
                kind=WeReadLookupKind.ALTERNATIVE,
                source_title=source_edition.title,
                selected_edition=selected,
                deep_link=deep_link,
                message=_available_message(source_edition, selected, exact=False, deep_link=deep_link),
            )

        if intent.weread_status is WeReadStatus.UNAVAILABLE:
            title = selected.title if selected is not None else source_edition.title
            return WeReadLookupResult(
                kind=WeReadLookupKind.UNAVAILABLE,
                source_title=source_edition.title,
                selected_edition=selected,
                deep_link=deep_link,
                message=f"微信读书找到了同一作品的《{title}》，但当前目录状态显示不可读。",
            )

        return WeReadLookupResult(
            kind=WeReadLookupKind.NOT_FOUND,
            source_title=source_edition.title,
            selected_edition=None,
            deep_link=None,
            message=(
                f"微信读书暂未在当前搜索范围内找到《{source_edition.title}》的可读同 Work 版本。"
                "这不是对整个微信读书目录的绝对否定。"
            ),
        )


def _available_message(
    source: Edition,
    selected: Edition,
    *,
    exact: bool,
    deep_link: str | None,
) -> str:
    relation = "找到同一版本" if exact else "没有找到完全相同版本，但找到了同一作品的可读版本"
    details = " · ".join(
        value
        for value in (
            selected.title,
            "、".join(selected.authors) if selected.authors else None,
            selected.publisher,
            selected.publish_date,
            selected.isbn,
        )
        if value
    )
    lines = [f"微信读书：{relation}。", details or selected.title]
    if not exact and source.isbn and selected.isbn and source.isbn != selected.isbn:
        lines.append(f"豆瓣 ISBN：{source.isbn}；微信读书 ISBN：{selected.isbn}")
    if deep_link:
        lines.append(f"可读链接：{deep_link}")
    return "\n".join(lines)


WEREAD_LOOKUP_ERRORS = (WeReadProviderError, ValueError)
