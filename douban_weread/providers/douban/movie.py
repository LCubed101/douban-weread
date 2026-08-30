from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .search import DEFAULT_USER_AGENT, DoubanProviderError

DEFAULT_MOVIE_BASE_URL = "https://movie.douban.com"
DEFAULT_MOVIE_SEARCH_BASE_URL = "https://search.douban.com/movie"
_SUBJECT_ID_RE = re.compile(r"(?:https?://movie\.douban\.com)?/subject/(?P<id>\d+)/?", re.IGNORECASE)
_SUBJECT_ID_ONLY_RE = re.compile(r"^\d+$")
_TITLE_RE = re.compile(
    r"<span[^>]+property=[\"']v:itemreviewed[\"'][^>]*>(?P<title>.*?)</span>",
    re.IGNORECASE | re.DOTALL,
)
_YEAR_RE = re.compile(r"<span[^>]+class=[\"']year[\"'][^>]*>\((?P<year>\d{4})\)</span>", re.IGNORECASE)


@dataclass(slots=True, frozen=True)
class DoubanMovieCandidate:
    douban_id: str
    title: str
    year: str | None
    media_type: str | None
    directors: tuple[str, ...]
    actors: tuple[str, ...]
    genres: tuple[str, ...]
    aliases: tuple[str, ...]
    subject_url: str


@dataclass(slots=True)
class _TextResponse:
    status: int
    body: str


Transport = Callable[[str, Mapping[str, str]], _TextResponse]


class _InfoParser(HTMLParser):
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
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if not self._in_info:
            return
        if tag == "div":
            self._depth -= 1
            if self._depth == 0:
                self._flush()
                self._in_info = False

    def handle_data(self, data: str) -> None:
        if self._in_info:
            self._parts.append(data)

    def _flush(self) -> None:
        text = " ".join("".join(self._parts).split())
        self._parts.clear()
        if text:
            self.lines.append(text)


class DoubanMovieSearchClient:
    """Read-only adapter for Douban Movie title discovery and subject pages.

    The lightweight ``/j/subject_suggest`` response already contains stable
    subject identity plus title/year metadata. Prefer those candidates directly
    instead of immediately refetching every subject page: live Douban may return
    a verification/anti-abuse HTML page for a detail request even when the
    suggest endpoint itself succeeds. Subject-page parsing remains available for
    fallback search results and explicit subject lookup.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_MOVIE_BASE_URL,
        search_base_url: str = DEFAULT_MOVIE_SEARCH_BASE_URL,
        timeout: float = 10.0,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: Transport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.search_base_url = search_base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent
        self._transport = transport or self._default_transport

    def search_by_title(self, title: str, *, count: int = 10) -> list[DoubanMovieCandidate]:
        query = title.strip()
        if not query:
            return []
        limit = max(1, min(count, 20))

        suggested = self._suggest_candidates(query, limit=limit)
        if suggested:
            return suggested

        ids = self._fallback_search_subject_ids(query, limit=limit)
        result: list[DoubanMovieCandidate] = []
        for subject_id in ids:
            item = self.get_by_subject_id(subject_id)
            if item is not None:
                result.append(item)
        return result

    def get_by_subject_id(self, subject_id: str) -> DoubanMovieCandidate | None:
        subject = subject_id.strip()
        if not _SUBJECT_ID_ONLY_RE.fullmatch(subject):
            raise ValueError("Douban movie subject_id must contain digits only.")
        url = f"{self.base_url}/subject/{subject}/"
        return self._parse_subject_page(self._get_text(url), subject_id=subject, subject_url=url)

    def _search_subject_ids(self, query: str, *, limit: int) -> list[str]:
        """Compatibility/debug helper returning discovery ids without detail fetches."""
        suggested = self._suggest_subject_ids(query, limit=limit)
        if suggested:
            return suggested
        return self._fallback_search_subject_ids(query, limit=limit)

    def _suggest_payload(self, query: str) -> list[dict[str, object]]:
        params = urlencode({"q": query})
        raw = self._get_text(f"{self.base_url}/j/subject_suggest?{params}")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def _suggest_subject_ids(self, query: str, *, limit: int) -> list[str]:
        ids: list[str] = []
        for item in self._suggest_payload(query):
            subject_id = str(item.get("id") or "").strip()
            if not _SUBJECT_ID_ONLY_RE.fullmatch(subject_id):
                continue
            if subject_id not in ids:
                ids.append(subject_id)
            if len(ids) >= limit:
                break
        return ids

    def _suggest_candidates(self, query: str, *, limit: int) -> list[DoubanMovieCandidate]:
        candidates: list[DoubanMovieCandidate] = []
        for item in self._suggest_payload(query):
            subject_id = str(item.get("id") or "").strip()
            title = self._clean(str(item.get("title") or ""))
            if not _SUBJECT_ID_ONLY_RE.fullmatch(subject_id) or not title:
                continue

            year_value = self._clean(str(item.get("year") or "")) or None
            type_value = self._clean(str(item.get("type") or "")) or None
            sub_title = self._clean(str(item.get("sub_title") or ""))
            aliases = (sub_title,) if sub_title and sub_title != title else ()

            url_value = self._clean(str(item.get("url") or ""))
            url_match = _SUBJECT_ID_RE.search(url_value)
            subject_url = (
                f"{self.base_url}/subject/{url_match.group('id')}/"
                if url_match
                else f"{self.base_url}/subject/{subject_id}/"
            )

            candidates.append(
                DoubanMovieCandidate(
                    douban_id=subject_id,
                    title=title,
                    year=year_value,
                    media_type=type_value,
                    directors=(),
                    actors=(),
                    genres=(),
                    aliases=aliases,
                    subject_url=subject_url,
                )
            )
            if len(candidates) >= limit:
                break
        return candidates

    def _fallback_search_subject_ids(self, query: str, *, limit: int) -> list[str]:
        params = urlencode({"search_text": query, "cat": "1002"})
        html = self._get_text(f"{self.search_base_url}/subject_search?{params}")
        ids: list[str] = []
        for match in _SUBJECT_ID_RE.finditer(html):
            subject_id = match.group("id")
            if subject_id not in ids:
                ids.append(subject_id)
            if len(ids) >= limit:
                break
        return ids

    def _get_text(self, url: str) -> str:
        response = self._transport(
            url,
            {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/json",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        if response.status < 200 or response.status >= 300:
            raise DoubanProviderError(f"Douban Movie request failed with HTTP {response.status}")
        return response.body

    def _default_transport(self, url: str, headers: Mapping[str, str]) -> _TextResponse:
        request = Request(url, headers=dict(headers), method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - expected provider URL
                return _TextResponse(
                    status=getattr(response, "status", 200),
                    body=response.read().decode("utf-8", errors="replace"),
                )
        except HTTPError as exc:
            raise DoubanProviderError(f"Douban Movie request failed with HTTP {exc.code}") from exc
        except URLError as exc:
            raise DoubanProviderError(f"Could not reach Douban Movie: {exc.reason}") from exc

    @classmethod
    def _parse_subject_page(
        cls,
        html: str,
        *,
        subject_id: str,
        subject_url: str,
    ) -> DoubanMovieCandidate | None:
        title_match = _TITLE_RE.search(html)
        if not title_match:
            return None
        title = cls._clean(title_match.group("title"))
        if not title:
            return None

        year_match = _YEAR_RE.search(html)
        parser = _InfoParser()
        parser.feed(html)
        info = cls._parse_info_lines(parser.lines)

        return DoubanMovieCandidate(
            douban_id=subject_id,
            title=title,
            year=year_match.group("year") if year_match else info.get("year"),
            media_type=info.get("media_type"),
            directors=tuple(info.get("directors", ())),
            actors=tuple(info.get("actors", ())),
            genres=tuple(info.get("genres", ())),
            aliases=tuple(info.get("aliases", ())),
            subject_url=subject_url,
        )

    @staticmethod
    def _parse_info_lines(lines: list[str]) -> dict[str, object]:
        result: dict[str, object] = {}
        mapping = {
            "导演:": "directors",
            "导演：": "directors",
            "主演:": "actors",
            "主演：": "actors",
            "类型:": "genres",
            "类型：": "genres",
            "又名:": "aliases",
            "又名：": "aliases",
        }
        for line in lines:
            for label, key in mapping.items():
                if line.startswith(label):
                    value = line[len(label) :].strip()
                    result[key] = tuple(x.strip() for x in re.split(r"\s*/\s*|、", value) if x.strip())
                    break
            if line.startswith(("首播:", "首播：")):
                result["media_type"] = "tv"
                result.setdefault("year", cls_year(line))
            elif line.startswith(("上映日期:", "上映日期：")):
                result.setdefault("media_type", "movie")
                result.setdefault("year", cls_year(line))
        return result

    @staticmethod
    def _clean(value: str) -> str:
        return " ".join(unescape(re.sub(r"<[^>]+>", "", value)).split())


def cls_year(value: str) -> str | None:
    match = re.search(r"(?:19|20)\d{2}", value)
    return match.group(0) if match else None
