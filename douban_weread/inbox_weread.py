from __future__ import annotations

import os
import re
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
    """Read-only WeRead lookup for either a resolved Edition or a title-only mention."""

    def __init__(
        self,
        provider: WeReadCatalogProvider | None = None,
        *,
        search_limit: int = 20,
    ) -> None:
        self.provider = provider or WeReadClient(api_key=os.getenv("WEREAD_API_KEY", ""))
        self.search_limit = max(1, min(search_limit, 20))

    def lookup(self, source_edition: Edition) -> WeReadLookupResult:
        aligned = align_to_weread(
            source_edition,
            self.provider,
            limit=self.search_limit,
        )
        if aligned.intent.weread_status is WeReadStatus.NOT_FOUND and source_edition.isbn:
            aligned = align_to_weread(
                source_edition,
                self.provider,
                limit=self.search_limit,
                search_keyword=source_edition.isbn,
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
                f"微信读书暂未通过标题或 ISBN 的当前有界搜索找到《{source_edition.title}》的同 Work 版本。"
                "这不是对整个微信读书目录的绝对否定。"
            ),
        )

    def lookup_title(self, title: str) -> WeReadLookupResult:
        """Resolve a recommendation that contains only a title.

        The title-only path deliberately uses official search evidence before
        requiring `/book/info`. This matters for books that WeRead exposes in
        search as sold out / waiting-to-be-published: those entries can have an
        exact title and deep link even when full book metadata is unavailable.

        Readable results still require a resolved Edition from `/book/info`.
        Waiting results may safely use the exact-title search candidate itself.
        Fuzzy/different titles remain fail-closed.
        """

        query = title.strip()
        if not query:
            raise ValueError("WeRead title lookup requires a non-empty title")

        wanted = _normalize_lookup_title(query)
        exact_available: tuple[object, Edition] | None = None
        exact_unavailable: tuple[object, Edition] | None = None

        candidates = self.provider.search_books(query, count=self.search_limit)
        for candidate in candidates:
            candidate_title = str(getattr(candidate, "title", "") or "").strip()
            if not candidate_title or _normalize_lookup_title(candidate_title) != wanted:
                continue

            book_id = str(getattr(candidate, "book_id", "") or "").strip()
            soldout = bool(getattr(candidate, "soldout", False))

            # A sold-out exact-title search candidate is sufficient evidence that
            # WeRead knows this book but it is not currently readable. Do not
            # discard it merely because `/book/info` has not exposed metadata yet.
            if soldout:
                edition = self.provider.get_book(book_id) if book_id else None
                if edition is None:
                    edition = _edition_from_search_candidate(candidate)
                if exact_unavailable is None:
                    exact_unavailable = (candidate, edition)
                continue

            # Positive readability remains conservative: require full book info
            # and confirm its normalized title is still exact.
            if not book_id:
                continue
            edition = self.provider.get_book(book_id)
            if edition is None or _normalize_lookup_title(edition.title) != wanted:
                continue
            exact_available = (candidate, edition)
            break

        if exact_available is not None:
            candidate, edition = exact_available
            deep_link = _candidate_deep_link(candidate, edition)
            return WeReadLookupResult(
                kind=WeReadLookupKind.EXACT,
                source_title=query,
                selected_edition=edition,
                deep_link=deep_link,
                message=_title_only_available_message(edition, deep_link=deep_link),
            )

        if exact_unavailable is not None:
            candidate, edition = exact_unavailable
            deep_link = _candidate_deep_link(candidate, edition)
            lines = [f"微信读书搜索到了同名《{edition.title}》，当前处于待上架/不可读状态。"]
            if deep_link:
                lines.append(f"查看微信读书：{deep_link}")
            return WeReadLookupResult(
                kind=WeReadLookupKind.UNAVAILABLE,
                source_title=query,
                selected_edition=edition,
                deep_link=deep_link,
                message="\n".join(lines),
            )

        return WeReadLookupResult(
            kind=WeReadLookupKind.NOT_FOUND,
            source_title=query,
            selected_edition=None,
            deep_link=None,
            message=(
                f"微信读书当前搜索没有找到可安全确认的同名《{query}》。"
                "为避免把相似书名误配成同一本，暂不自动选择其他结果。"
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


def _title_only_available_message(selected: Edition, *, deep_link: str | None) -> str:
    details = " · ".join(
        value
        for value in (
            selected.title,
            "、".join(selected.authors) if selected.authors else None,
            selected.publisher,
            selected.publish_date,
        )
        if value
    )
    lines = ["微信读书：找到同名可读版本。", details or selected.title]
    if deep_link:
        lines.append(f"可读链接：{deep_link}")
    return "\n".join(lines)


def _normalize_lookup_title(value: str) -> str:
    value = value.casefold().strip()
    return re.sub(r"[\s·•・:：,，.。!！?？—–_\-《》()（）\[\]【】]+", "", value)


def _edition_from_search_candidate(candidate: object) -> Edition:
    book_id = str(getattr(candidate, "book_id", "") or "").strip() or None
    title = str(getattr(candidate, "title", "") or "").strip()
    author = str(getattr(candidate, "author", "") or "").strip()
    publisher = str(getattr(candidate, "publisher", "") or "").strip() or None
    deep_link = str(getattr(candidate, "deep_link", "") or "").strip() or None
    return Edition(
        title=title,
        authors=[author] if author else [],
        publisher=publisher,
        weread_id=book_id,
        source_metadata={
            "provider": "weread_official_search",
            "deep_link": deep_link,
            "search_only": True,
        },
    )


def _candidate_deep_link(candidate: object, edition: Edition) -> str | None:
    value = str(getattr(candidate, "deep_link", "") or "").strip()
    if value:
        return value
    metadata_value = edition.source_metadata.get("deep_link")
    if isinstance(metadata_value, str) and metadata_value.strip():
        return metadata_value.strip()
    return None


WEREAD_LOOKUP_ERRORS = (WeReadProviderError, ValueError)
