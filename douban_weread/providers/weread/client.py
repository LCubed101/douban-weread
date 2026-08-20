from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from json import JSONDecodeError
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from douban_weread.core.models import Edition
from douban_weread.providers.weread.shelf import WeReadShelfSnapshot, parse_shelf_payload


DEFAULT_GATEWAY_URL = "https://i.weread.qq.com/api/agent/gateway"
DEFAULT_SKILL_VERSION = "1.0.4"


class WeReadProviderError(RuntimeError):
    """Raised when the official WeRead Agent Gateway cannot serve a request."""


class WeReadAuthError(WeReadProviderError):
    """Raised when a WeRead API key is missing or rejected."""


@dataclass(slots=True)
class WeReadSearchCandidate:
    book_id: str
    title: str
    author: str | None = None
    publisher: str | None = None
    soldout: bool = False
    deep_link: str | None = None
    search_idx: int | None = None
    source_metadata: dict[str, object] = field(default_factory=dict, repr=False)


@dataclass(slots=True, frozen=True)
class WeReadProgress:
    book_id: str
    progress: int
    is_started: bool
    update_time: int | None = None
    reading_time_seconds: int | None = None
    finish_time: int | None = None
    source_metadata: dict[str, object] = field(default_factory=dict, repr=False, compare=False)

    @property
    def reading_state(self) -> str:
        """Conservatively map official progress evidence to a coarse state."""
        if self.progress == 100:
            return "read" if self.finish_time is not None else "unknown"
        if 0 < self.progress < 100 or self.is_started:
            return "reading"
        if self.progress == 0 and not self.is_started:
            return "unread"
        return "unknown"


@dataclass(slots=True)
class _JsonResponse:
    status: int
    body: str


Transport = Callable[[str, dict[str, str], bytes], _JsonResponse]


class WeReadClient:
    """Read-only client for Tencent's official WeChatReading Agent Gateway."""

    def __init__(
        self,
        *,
        api_key: str,
        gateway_url: str = DEFAULT_GATEWAY_URL,
        skill_version: str = DEFAULT_SKILL_VERSION,
        timeout: float = 10.0,
        transport: Transport | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.gateway_url = gateway_url.rstrip("/")
        self.skill_version = skill_version.strip() or DEFAULT_SKILL_VERSION
        self.timeout = timeout
        self._transport = transport or self._default_transport

    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        query = keyword.strip()
        if not query:
            return []

        payload = self._call(
            "/store/search",
            keyword=query,
            scope=10,
            count=max(1, min(count, 100)),
        )

        candidates: list[WeReadSearchCandidate] = []
        seen: set[str] = set()
        for group in payload.get("results", []) or []:
            if not isinstance(group, dict):
                continue
            for item in group.get("books", []) or []:
                if not isinstance(item, dict):
                    continue
                info = item.get("bookInfo")
                if not isinstance(info, dict):
                    continue
                book_id = str(info.get("bookId") or "").strip()
                title = str(info.get("title") or "").strip()
                if not book_id or not title or book_id in seen:
                    continue
                seen.add(book_id)
                candidates.append(
                    WeReadSearchCandidate(
                        book_id=book_id,
                        title=title,
                        author=_optional_text(info.get("author")),
                        publisher=_optional_text(info.get("publisher")),
                        soldout=_as_bool_flag(info.get("soldout")),
                        deep_link=_optional_text(info.get("deepLink")),
                        search_idx=_optional_int(item.get("searchIdx")),
                        source_metadata={
                            "provider": "weread_official",
                            "group_title": group.get("title"),
                            "group_scope": group.get("scope"),
                            "book_info": dict(info),
                        },
                    )
                )
        return candidates

    def get_book(self, book_id: str) -> Edition | None:
        normalized_id = book_id.strip()
        if not normalized_id:
            return None

        payload = self._call("/book/info", bookId=normalized_id)
        title = _optional_text(payload.get("title"))
        if not title:
            return None

        returned_id = _optional_text(payload.get("bookId")) or normalized_id
        author_raw = payload.get("author")
        translator_raw = payload.get("translator")
        return Edition(
            title=title,
            authors=_people_field(author_raw),
            translators=_people_field(translator_raw),
            publisher=_optional_text(payload.get("publisher")),
            publish_date=_normalize_publish_time(payload.get("publishTime")),
            isbn=_normalize_isbn(payload.get("isbn")),
            cover_url=_optional_text(payload.get("cover")),
            weread_id=returned_id,
            source_metadata={
                "provider": "weread_official",
                "deep_link": payload.get("deepLink"),
                "raw_author": author_raw,
                "raw_translator": translator_raw,
                "raw": dict(payload),
            },
        )

    def get_progress(self, book_id: str) -> WeReadProgress | None:
        """Fetch official read-only progress for one exact WeRead bookId."""
        normalized_id = book_id.strip()
        if not normalized_id:
            return None

        payload = self._call("/book/getprogress", bookId=normalized_id)
        raw_book = payload.get("book")
        if not isinstance(raw_book, dict):
            raise WeReadProviderError("WeRead progress response is missing book metadata")

        progress = _optional_int(raw_book.get("progress"))
        if progress is None or not 0 <= progress <= 100:
            raise WeReadProviderError("WeRead progress response has invalid progress")

        returned_id = _optional_text(payload.get("bookId")) or normalized_id
        return WeReadProgress(
            book_id=returned_id,
            progress=progress,
            is_started=_as_bool_flag(raw_book.get("isStartReading")),
            update_time=_optional_int(raw_book.get("updateTime")),
            reading_time_seconds=_optional_int(raw_book.get("recordReadingTime")),
            finish_time=_optional_int(raw_book.get("finishTime")),
            source_metadata={"provider": "weread_official", "raw": dict(payload)},
        )

    def sync_shelf(self) -> WeReadShelfSnapshot:
        """Fetch one complete read-only shelf snapshot through official `/shelf/sync`."""
        payload = self._call("/shelf/sync")
        try:
            return parse_shelf_payload(payload)
        except ValueError as exc:
            raise WeReadProviderError(f"WeRead shelf response is invalid: {exc}") from exc

    def _call(self, api_name: str, **params: object) -> dict[str, object]:
        if not self.api_key:
            raise WeReadAuthError("WEREAD_API_KEY is required")
        if not self.api_key.startswith("wrk-"):
            raise WeReadAuthError("WEREAD_API_KEY has an unexpected format")

        body = {
            "api_name": api_name,
            "skill_version": self.skill_version,
            **params,
        }
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        response = self._transport(self.gateway_url, headers, encoded)
        if not 200 <= response.status < 300:
            raise WeReadProviderError(f"WeRead request failed with HTTP {response.status}")

        try:
            payload = json.loads(response.body)
        except JSONDecodeError as exc:
            raise WeReadProviderError("WeRead returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise WeReadProviderError("WeRead returned an unexpected response shape")

        upgrade = payload.get("upgrade_info")
        if upgrade:
            message = upgrade.get("message") if isinstance(upgrade, dict) else None
            suffix = f": {message}" if isinstance(message, str) and message.strip() else ""
            raise WeReadProviderError(f"WeRead skill upgrade required{suffix}")

        errcode = payload.get("errcode", payload.get("errCode", 0))
        if errcode not in (None, 0, "0"):
            errmsg = payload.get("errmsg", payload.get("errMsg", "request failed"))
            safe_message = str(errmsg).strip() or "request failed"
            if str(errcode) in {"-2010", "-2012"}:
                raise WeReadAuthError(f"WeRead authentication failed ({errcode}): {safe_message}")
            raise WeReadProviderError(f"WeRead gateway error ({errcode}): {safe_message}")

        return payload

    def _default_transport(self, url: str, headers: dict[str, str], body: bytes) -> _JsonResponse:
        request = Request(url, data=body, headers=headers, method="POST")  # noqa: S310 - fixed provider URL
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - expected provider URL
                charset = response.headers.get_content_charset() or "utf-8"
                return _JsonResponse(status=response.status, body=response.read().decode(charset, errors="replace"))
        except HTTPError as exc:
            raise WeReadProviderError(f"WeRead request failed with HTTP {exc.code}") from exc
        except URLError as exc:
            raise WeReadProviderError(f"WeRead request failed: {exc.reason}") from exc


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_bool_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none"}
    return bool(value)


def _people_field(value: object) -> list[str]:
    """Normalize documented string/list person fields without guessing delimiters."""
    if isinstance(value, list):
        return [text for item in value if (text := _optional_text(item))]
    text = _optional_text(value)
    return [text] if text else []


def _normalize_publish_time(value: object) -> str | None:
    text = _optional_text(value)
    if not text:
        return None
    match = re.match(r"^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?", text)
    if not match:
        return text
    year, month, day = match.groups()
    if day:
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return f"{year}-{int(month):02d}"


def _normalize_isbn(value: object) -> str | None:
    text = _optional_text(value)
    if not text:
        return None
    normalized = re.sub(r"[^0-9Xx]", "", text)
    return normalized.upper() or None
