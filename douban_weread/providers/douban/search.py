from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from douban_weread.core.models import Edition
from douban_weread.providers.douban.normalize import normalize_douban_edition, normalize_isbn


DEFAULT_BASE_URL = "https://book.douban.com"
# Douban may reject obvious library/bot user agents with HTTP 418. Keep this
# browser-like default configurable so deployments can override it without
# changing provider logic.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/151.0.0.0 Safari/537.36"
)

_SUBJECT_ID_RE = re.compile(
    r"(?:https?://book\.douban\.com)?/subject/(?P<id>\d+)/?",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(
    r"<span[^>]+property=[\"']v:itemreviewed[\"'][^>]*>(?P<title>.*?)</span>",
    re.IGNORECASE | re.DOTALL,
)
_COVER_RE = re.compile(
    r"<div[^>]+id=[\"']mainpic[\"'][^>]*>.*?<img[^>]+src=[\"'](?P<src>[^\"']+)",
    re.IGNORECASE | re.DOTALL,
)


class DoubanProviderError(RuntimeError):
    """Raised when the Douban provider cannot complete a request."""


@dataclass(slots=True)
class _TextResponse:
    status: int
    body: str


Transport = Callable[[str, Mapping[str, str]], _TextResponse]


class _InfoParser(HTMLParser):
    """Collect text lines from the subject page's #info block."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_info = False
        self._depth = 0
        self._parts: list[str] = []
        self.lines: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if tag == "div" and attrs_map.get("id") == "info" and not self._in_info:
            self._in_info = True
            self._depth = 1
            return

        if not self._in_info:
            return

        if tag == "div":
            self._depth += 1
        elif tag == "br":
            self._flush_line()

    def handle_endtag(self, tag: str) -> None:
        if not self._in_info:
            return

        if tag == "div":
            self._depth -= 1
            if self._depth == 0:
                self._flush_line()
                self._in_info = False

    def handle_data(self, data: str) -> None:
        if self._in_info:
            self._parts.append(data)

    def _flush_line(self) -> None:
        text = " ".join("".join(self._parts).split())
        self._parts.clear()
        if text:
            self.lines.append(text)


class DoubanBookSearchClient:
    """Read-only Douban book web adapter.

    Douban's legacy ``api.douban.com/v2/book`` endpoint is no longer used as
    the primary path. Search runs against the public Douban Book web search,
    then candidate subject pages are parsed into the provider-independent
    :class:`Edition` model.

    Transport remains injectable so unit tests do not depend on live Douban.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: Transport | None = None,
        api_key: str | None = None,
    ) -> None:
        # ``api_key`` is accepted temporarily for backwards compatibility with
        # the early legacy-API adapter. The web provider does not use it.
        _ = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent
        self._transport = transport or self._default_transport

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        """Return normalized candidate Douban editions for a title query."""
        query = title.strip()
        if not query:
            return []

        # Keep web traffic conservative. The CLI defaults to 10 and the public
        # search page itself typically exposes only a limited candidate set.
        limit = max(1, min(count, 20))
        subject_ids = self._search_subject_ids(query, limit=limit)

        editions: list[Edition] = []
        for subject_id in subject_ids:
            edition = self._fetch_subject(subject_id)
            if edition is not None:
                editions.append(edition)
        return editions

    def search_by_isbn(self, isbn: str) -> Edition | None:
        """Return an exact edition by searching Douban Book for its ISBN."""
        normalized = normalize_isbn(isbn)
        if not normalized:
            return None

        # Search can return multiple subjects for noisy/duplicate catalog data,
        # so verify the parsed ISBN before calling the result exact.
        for subject_id in self._search_subject_ids(normalized, limit=10):
            edition = self._fetch_subject(subject_id)
            if edition is not None and edition.isbn == normalized:
                return edition
        return None

    def _search_subject_ids(self, query: str, *, limit: int) -> list[str]:
        params = urlencode({"search_text": query, "cat": "1001"})
        html = self._get_text(f"{self.base_url}/subject_search?{params}")

        subject_ids: list[str] = []
        for match in _SUBJECT_ID_RE.finditer(html):
            subject_id = match.group("id")
            if subject_id not in subject_ids:
                subject_ids.append(subject_id)
            if len(subject_ids) >= limit:
                break
        return subject_ids

    def _fetch_subject(self, subject_id: str) -> Edition | None:
        url = f"{self.base_url}/subject/{subject_id}/"
        html = self._get_text(url)
        return self._parse_subject_page(html, subject_id=subject_id, subject_url=url)

    def _get_text(self, url: str) -> str:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        response = self._transport(url, headers)
        if response.status < 200 or response.status >= 300:
            raise DoubanProviderError(f"Douban request failed with HTTP {response.status}")
        return response.body

    def _default_transport(self, url: str, headers: Mapping[str, str]) -> _TextResponse:
        request = Request(url, headers=dict(headers), method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - expected provider URL
                body = response.read().decode("utf-8", errors="replace")
                return _TextResponse(status=getattr(response, "status", 200), body=body)
        except HTTPError as exc:
            raise DoubanProviderError(f"Douban request failed with HTTP {exc.code}") from exc
        except URLError as exc:
            raise DoubanProviderError(f"Could not reach Douban: {exc.reason}") from exc

    @classmethod
    def _parse_subject_page(
        cls,
        html: str,
        *,
        subject_id: str,
        subject_url: str,
    ) -> Edition | None:
        title_match = _TITLE_RE.search(html)
        if not title_match:
            return None

        title = cls._clean_html_text(title_match.group("title"))
        if not title:
            return None

        parser = _InfoParser()
        parser.feed(html)
        info = cls._parse_info_lines(parser.lines)

        cover_match = _COVER_RE.search(html)
        cover_url = unescape(cover_match.group("src")) if cover_match else None

        raw: dict[str, object] = {
            "id": subject_id,
            "title": title,
            "author": info.get("authors", []),
            "translator": info.get("translators", []),
            "publisher": info.get("publisher"),
            "pubdate": info.get("publish_date"),
            "image": cover_url,
            "subject_url": subject_url,
            "source": "douban_web",
        }

        isbn = info.get("isbn")
        if isinstance(isbn, str):
            normalized_isbn = normalize_isbn(isbn)
            if normalized_isbn:
                raw["isbn13" if len(normalized_isbn) == 13 else "isbn10"] = normalized_isbn

        edition = normalize_douban_edition(raw)
        if edition is not None:
            edition.source_metadata["subject_url"] = subject_url
            edition.source_metadata["provider"] = "douban_web"
        return edition

    @staticmethod
    def _parse_info_lines(lines: list[str]) -> dict[str, object]:
        result: dict[str, object] = {}
        labels: tuple[tuple[str, str], ...] = (
            ("作者:", "authors"),
            ("作者：", "authors"),
            ("译者:", "translators"),
            ("译者：", "translators"),
            ("出版社:", "publisher"),
            ("出版社：", "publisher"),
            ("出版年:", "publish_date"),
            ("出版年：", "publish_date"),
            ("ISBN:", "isbn"),
            ("ISBN：", "isbn"),
        )

        for line in lines:
            for label, key in labels:
                if not line.startswith(label):
                    continue
                value = line[len(label) :].strip()
                if not value:
                    break
                if key in {"authors", "translators"}:
                    result[key] = [
                        item.strip()
                        for item in re.split(r"\s*/\s*|、|；|;", value)
                        if item.strip()
                    ]
                else:
                    result[key] = value
                break
        return result

    @staticmethod
    def _clean_html_text(value: str) -> str:
        text = re.sub(r"<[^>]+>", "", value)
        return " ".join(unescape(text).split())
