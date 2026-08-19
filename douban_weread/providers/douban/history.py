from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookies import SimpleCookie
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from .interest import DoubanAuthError
from .search import DEFAULT_USER_AGENT, DoubanProviderError


DEFAULT_BASE_URL = "https://book.douban.com"
_HISTORY_STATES = {"wish", "do", "collect"}
_SUBJECT_HREF_RE = re.compile(r"/subject/(?P<id>\d+)/?", re.IGNORECASE)
_TOTAL_RE = re.compile(r"[\(（]\s*(?P<count>\d+)\s*[\)）]")
_RANGE_TOTAL_RE = re.compile(r"\b\d+\s*-\s*\d+\s*/\s*(?P<count>\d+)\b")
_LOGIN_MARKERS = ("accounts.douban.com", "/login", "/signup")
_BLOCK_MARKERS = ("captcha", "sec.douban.com", "验证码")


@dataclass(slots=True, frozen=True)
class HistoryEntry:
    subject_id: str
    title: str
    state: str


@dataclass(slots=True)
class _HistoryResponse:
    status: int
    body: str
    url: str


HistoryTransport = Callable[[str, Mapping[str, str]], _HistoryResponse]


class _HistoryPageParser(HTMLParser):
    """Parse subject IDs/titles from one Douban user book-list page.

    Current Douban Book list pages use ``li.subject-item``. A ``div.item``
    fallback is kept for older/alternate markup, but title similarity is never
    used here to infer Work identity.

    The parser also captures the list's declared total when available. That
    lets the caller fail closed if Douban says a list is non-empty but a future
    HTML change causes the entry parser to return zero or only a partial list.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[tuple[str, str]] = []
        self.next_start: int | None = None
        self.declared_total: int | None = None

        self._item_tag: str | None = None
        self._item_depth = 0
        self._next_depth = 0
        self._active_subject: str | None = None
        self._active_text: list[str] = []
        self._titles: dict[str, str] = {}
        self._order: list[str] = []

        self._in_title = False
        self._title_text: list[str] = []
        self._page_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        classes = set((attrs_map.get("class") or "").split())

        if tag == "title":
            self._in_title = True

        if self._item_tag is not None:
            if tag == self._item_tag:
                self._item_depth += 1
        elif tag == "li" and "subject-item" in classes:
            self._item_tag = "li"
            self._item_depth = 1
        elif tag == "div" and "item" in classes:
            self._item_tag = "div"
            self._item_depth = 1

        if tag == "span":
            if self._next_depth:
                self._next_depth += 1
            elif "next" in classes:
                self._next_depth = 1

        if tag != "a":
            return

        href = attrs_map.get("href") or ""
        rel_tokens = set((attrs_map.get("rel") or "").split())
        is_next_link = self._next_depth > 0 or "next" in classes or "next" in rel_tokens
        if is_next_link:
            query = parse_qs(urlparse(href).query)
            start_values = query.get("start", [])
            if start_values and start_values[0].isdigit():
                self.next_start = int(start_values[0])

        if self._item_tag is None:
            return

        match = _SUBJECT_HREF_RE.search(href)
        if not match:
            return

        subject_id = match.group("id")
        if subject_id not in self._order:
            self._order.append(subject_id)

        title_attr = (attrs_map.get("title") or "").strip()
        if title_attr:
            self._titles[subject_id] = title_attr

        self._active_subject = subject_id
        self._active_text = []

    def handle_data(self, data: str) -> None:
        self._page_text.append(data)
        if self._in_title:
            self._title_text.append(data)
        if self._active_subject:
            self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._active_subject:
            text = " ".join("".join(self._active_text).split())
            if text:
                self._titles[self._active_subject] = text
            self._active_subject = None
            self._active_text = []

        if tag == "title":
            self._in_title = False

        if self._item_tag == tag:
            self._item_depth -= 1
            if self._item_depth <= 0:
                self._item_tag = None
                self._item_depth = 0

        if tag == "span" and self._next_depth:
            self._next_depth -= 1

    def close(self) -> None:
        super().close()
        self.entries = [
            (subject_id, self._titles.get(subject_id, "").strip())
            for subject_id in self._order
            if self._titles.get(subject_id, "").strip()
        ]

        title_text = " ".join("".join(self._title_text).split())
        total_match = _TOTAL_RE.search(title_text)
        if total_match:
            self.declared_total = int(total_match.group("count"))
            return

        page_text = " ".join(" ".join(self._page_text).split())
        range_match = _RANGE_TOTAL_RE.search(page_text)
        if range_match:
            self.declared_total = int(range_match.group("count"))


def _user_id_from_cookie(cookie_header: str) -> str | None:
    jar = SimpleCookie()
    try:
        jar.load(cookie_header)
    except Exception:
        return None
    dbcl2 = jar.get("dbcl2")
    if dbcl2 is None:
        return None
    value = dbcl2.value.strip().strip('"')
    user_id, sep, _ = value.partition(":")
    return user_id if sep and user_id.isdigit() else None


class DoubanBookHistoryClient:
    """Read-only adapter for a user's Douban Book wish/do/collect lists."""

    def __init__(
        self,
        cookie: str,
        *,
        user_id: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: HistoryTransport | None = None,
        max_pages: int = 1000,
    ) -> None:
        self.cookie_header = cookie.strip()
        self.user_id = user_id or _user_id_from_cookie(self.cookie_header)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent
        self._transport = transport or self._default_transport
        self.max_pages = max(1, max_pages)

    def fetch_all(self) -> list[HistoryEntry]:
        if not self.cookie_header:
            raise DoubanAuthError("DOUBAN_COOKIE is not set.")
        if not self.user_id:
            raise DoubanAuthError(
                "Could not derive the Douban user ID from dbcl2; use a fresh complete logged-in Cookie."
            )

        entries: list[HistoryEntry] = []
        for state in ("wish", "do", "collect"):
            entries.extend(self.fetch_state(state))
        return entries

    def fetch_state(self, state: str) -> list[HistoryEntry]:
        if state not in _HISTORY_STATES:
            raise ValueError(f"Unsupported Douban history state: {state}")
        if not self.user_id:
            raise DoubanAuthError("Douban user ID is unavailable for history sync.")

        result: list[HistoryEntry] = []
        seen: set[str] = set()
        start = 0
        declared_total: int | None = None

        for _ in range(self.max_pages):
            page = self._fetch_page(state, start=start)

            if page.declared_total is not None:
                if declared_total is None:
                    declared_total = page.declared_total
                elif page.declared_total != declared_total:
                    raise DoubanProviderError(
                        "Douban history declared-total changed during pagination; aborting safely."
                    )

            for subject_id, title in page.entries:
                if subject_id in seen:
                    continue
                seen.add(subject_id)
                result.append(HistoryEntry(subject_id=subject_id, title=title, state=state))

            if page.next_start is None:
                self._verify_complete_state(
                    state,
                    parsed_count=len(result),
                    declared_total=declared_total,
                )
                return result
            if page.next_start <= start:
                raise DoubanProviderError("Douban history pagination did not advance; aborting safely.")
            start = page.next_start

        raise DoubanProviderError(
            f"Douban history sync exceeded the safety limit of {self.max_pages} pages for state {state}."
        )

    @staticmethod
    def _verify_complete_state(
        state: str,
        *,
        parsed_count: int,
        declared_total: int | None,
    ) -> None:
        if declared_total is None:
            if parsed_count == 0:
                raise DoubanProviderError(
                    f"Douban history page for {state} yielded zero entries without a verifiable total; "
                    "refusing to record an empty baseline because the HTML structure may have changed."
                )
            return

        if parsed_count != declared_total:
            raise DoubanProviderError(
                f"Douban history completeness check failed for {state}: "
                f"page declared {declared_total} entries but parsed {parsed_count}. "
                "The local baseline was not replaced."
            )

    def _fetch_page(self, state: str, *, start: int) -> _HistoryPageParser:
        params = urlencode(
            {
                "start": start,
                "sort": "time",
                "rating": "all",
                "filter": "all",
                "mode": "grid",
            }
        )
        url = f"{self.base_url}/people/{self.user_id}/{state}?{params}"
        response = self._transport(url, self._headers())

        if response.status in {401, 403}:
            raise DoubanAuthError(
                f"Douban rejected the history request with HTTP {response.status}; refresh the browser session."
            )
        if response.status < 200 or response.status >= 300:
            raise DoubanProviderError(f"Douban history request failed with HTTP {response.status}")
        if self._looks_like_login(response.url, response.body):
            raise DoubanAuthError("Douban returned a login page during history sync.")
        if self._looks_blocked(response.body):
            raise DoubanAuthError(
                "Douban returned a captcha or anti-abuse page during history sync; do not bypass it programmatically."
            )

        parser = _HistoryPageParser()
        parser.feed(response.body)
        parser.close()
        return parser

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cookie": self.cookie_header,
            "Referer": f"{self.base_url}/",
        }

    def _default_transport(self, url: str, headers: Mapping[str, str]) -> _HistoryResponse:
        request = Request(url, headers=dict(headers), method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - expected provider URL
                return _HistoryResponse(
                    status=getattr(response, "status", 200),
                    body=response.read().decode("utf-8", errors="replace"),
                    url=response.geturl(),
                )
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return _HistoryResponse(status=exc.code, body=body, url=exc.geturl())
        except URLError as exc:
            raise DoubanProviderError(f"Could not reach Douban: {exc.reason}") from exc

    @staticmethod
    def _looks_like_login(url: str, body: str) -> bool:
        lowered_url = url.lower()
        lowered_body = body.lower()
        return any(marker in lowered_url for marker in _LOGIN_MARKERS) or (
            "登录豆瓣" in body and "accounts.douban.com" in lowered_body
        )

    @staticmethod
    def _looks_blocked(body: str) -> bool:
        lowered = body.lower()
        return any(marker in lowered for marker in _BLOCK_MARKERS)
