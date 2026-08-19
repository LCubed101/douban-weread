from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from douban_weread.core.models import Edition


DEFAULT_BASE_URL = "https://api.douban.com/v2/book"
DEFAULT_USER_AGENT = "douban-weread/0.1 (+https://github.com/LCubed101/douban-weread)"


class DoubanProviderError(RuntimeError):
    """Raised when the Douban provider cannot complete a request."""


@dataclass(slots=True)
class _JsonResponse:
    status: int
    payload: Mapping[str, Any]


Transport = Callable[[str, Mapping[str, str]], _JsonResponse]


class DoubanBookSearchClient:
    """Read-only Douban book search adapter.

    The client intentionally keeps transport and endpoint configuration
    injectable so tests do not depend on live Douban availability.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: Transport | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("DOUBAN_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent
        self._transport = transport or self._default_transport

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        """Return candidate Douban editions for a title query."""
        query = title.strip()
        if not query:
            return []

        params = {"q": query, "count": str(max(1, min(count, 100)))}
        payload = self._get_json(f"{self.base_url}/search", params)
        books = payload.get("books", [])
        if not isinstance(books, list):
            raise DoubanProviderError("Douban search response did not contain a valid books list")
        return [edition for item in books if (edition := self._to_edition(item)) is not None]

    def search_by_isbn(self, isbn: str) -> Edition | None:
        """Return the exact Douban edition for an ISBN when available."""
        normalized = self._normalize_isbn(isbn)
        if not normalized:
            return None

        try:
            payload = self._get_json(f"{self.base_url}/isbn/{normalized}", {})
        except DoubanProviderError as exc:
            # The legacy endpoint commonly uses 404 for an unknown ISBN.
            if "HTTP 404" in str(exc):
                return None
            raise
        return self._to_edition(payload)

    def _get_json(self, url: str, params: Mapping[str, str]) -> Mapping[str, Any]:
        merged = dict(params)
        if self.api_key:
            merged["apikey"] = self.api_key
        if merged:
            url = f"{url}?{urlencode(merged)}"

        response = self._transport(url, {"User-Agent": self.user_agent, "Accept": "application/json"})
        if response.status < 200 or response.status >= 300:
            raise DoubanProviderError(f"Douban request failed with HTTP {response.status}")
        return response.payload

    def _default_transport(self, url: str, headers: Mapping[str, str]) -> _JsonResponse:
        request = Request(url, headers=dict(headers), method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - expected provider URL
                body = response.read().decode("utf-8")
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise DoubanProviderError("Douban returned a non-object JSON response")
                return _JsonResponse(status=getattr(response, "status", 200), payload=payload)
        except HTTPError as exc:
            raise DoubanProviderError(f"Douban request failed with HTTP {exc.code}") from exc
        except URLError as exc:
            raise DoubanProviderError(f"Could not reach Douban: {exc.reason}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DoubanProviderError("Douban returned an invalid JSON response") from exc

    @classmethod
    def _to_edition(cls, raw: Any) -> Edition | None:
        if not isinstance(raw, Mapping):
            return None

        title = cls._clean_text(raw.get("title"))
        douban_id = cls._clean_text(raw.get("id"))
        if not title or not douban_id:
            return None

        authors = cls._join_people(raw.get("author"))
        translators = cls._join_people(raw.get("translator"))
        isbn = cls._normalize_isbn(raw.get("isbn13") or raw.get("isbn10") or "") or None

        images = raw.get("images")
        cover_url = None
        if isinstance(images, Mapping):
            cover_url = cls._clean_text(images.get("large") or images.get("medium") or images.get("small"))
        if not cover_url:
            cover_url = cls._clean_text(raw.get("image"))

        return Edition(
            title=title,
            author=authors,
            translator=translators or None,
            publisher=cls._clean_text(raw.get("publisher")) or None,
            publish_date=cls._clean_text(raw.get("pubdate")) or None,
            isbn=isbn,
            cover_url=cover_url or None,
            douban_id=douban_id,
        )

    @staticmethod
    def _clean_text(value: Any) -> str:
        if value is None:
            return ""
        return " ".join(str(value).split())

    @classmethod
    def _join_people(cls, value: Any) -> str:
        if isinstance(value, list):
            return " / ".join(filter(None, (cls._clean_text(item) for item in value)))
        return cls._clean_text(value)

    @staticmethod
    def _normalize_isbn(value: Any) -> str:
        return "".join(char for char in str(value) if char.isdigit() or char in "Xx").upper()
