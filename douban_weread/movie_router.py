from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from douban_weread.providers.douban.movie import DoubanMovieCandidate, DoubanMovieSearchClient


class MovieResolveKind(str, Enum):
    EXACT = "exact"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


@dataclass(slots=True, frozen=True)
class MovieResolveResult:
    kind: MovieResolveKind
    query: str
    selected: DoubanMovieCandidate | None
    candidates: tuple[DoubanMovieCandidate, ...]


class MovieSearchLike(Protocol):
    def search_by_title(self, title: str, *, count: int = 10) -> list[DoubanMovieCandidate]: ...


def _normalize_title(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def _candidate_matches_title(candidate: DoubanMovieCandidate, query: str) -> bool:
    normalized = _normalize_title(query)
    if _normalize_title(candidate.title) == normalized:
        return True
    return any(_normalize_title(alias) == normalized for alias in candidate.aliases)


_SEASON_SUFFIX_RE = re.compile(
    r"^(?:第[一二三四五六七八九十百两\d]+季|season\d+)$",
    re.IGNORECASE,
)
_SEASON_SUFFIX_CAPTURE_RE = re.compile(
    r"^(?:第(?P<cn>[一二三四五六七八九十百两\d]+)季|season(?P<en>\d+))$",
    re.IGNORECASE,
)
_CN_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def _cn_number(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if value == "百":
        return 100
    if "百" in value:
        left, right = value.split("百", 1)
        hundreds = _CN_DIGITS.get(left, 1) * 100
        tail = _cn_number(right) if right else 0
        return hundreds + (tail or 0)
    if "十" in value:
        left, right = value.split("十", 1)
        tens = _CN_DIGITS.get(left, 1) * 10
        ones = _CN_DIGITS.get(right, 0) if right else 0
        return tens + ones
    if len(value) == 1:
        return _CN_DIGITS.get(value)
    return None


def _season_suffix(candidate: DoubanMovieCandidate, query: str) -> str | None:
    query_norm = _normalize_title(query)
    if not query_norm:
        return None
    for raw in (candidate.title, *candidate.aliases):
        value_norm = _normalize_title(raw)
        if not value_norm.startswith(query_norm) or value_norm == query_norm:
            continue
        suffix = value_norm[len(query_norm) :]
        if _SEASON_SUFFIX_RE.fullmatch(suffix):
            return suffix
    return None


def _season_number(candidate: DoubanMovieCandidate, query: str) -> int | None:
    suffix = _season_suffix(candidate, query)
    if not suffix:
        return None
    match = _SEASON_SUFFIX_CAPTURE_RE.fullmatch(suffix)
    if not match:
        return None
    if match.group("en"):
        return int(match.group("en"))
    return _cn_number(match.group("cn") or "")


def _is_series_season_variant(candidate: DoubanMovieCandidate, query: str) -> bool:
    """Return True only for conservative `<query> + season` title variants."""

    return _season_suffix(candidate, query) is not None


class DoubanMovieResolver:
    """Fail-closed resolver for Movie/TV titles.

    V1.2 auto-selects only when one exact title/alias match is present. Multiple
    exact matches stay ambiguous. A bare TV franchise query may resolve to an
    ambiguous family of per-season subjects (`流人` -> `流人 第一季`, ...). When
    Douban's first suggestion batch skips seasons, only gaps between season 1 and
    the highest returned season are probed with exact season-number searches; no
    season is ever invented or auto-selected.
    """

    def __init__(self, search: MovieSearchLike | None = None, *, limit: int = 10) -> None:
        self.search = search or DoubanMovieSearchClient()
        self.limit = max(1, min(limit, 20))

    def _complete_season_family(
        self,
        query: str,
        seasons: tuple[DoubanMovieCandidate, ...],
    ) -> tuple[DoubanMovieCandidate, ...]:
        numbered = {
            number: item
            for item in seasons
            if (number := _season_number(item, query)) is not None and number > 0
        }
        # Require multiple independent season hits before treating gaps as a
        # series-completion problem. This avoids probing arbitrary fuzzy results.
        if len(numbered) < 2:
            return seasons

        highest = min(max(numbered), self.limit)
        missing = [number for number in range(1, highest + 1) if number not in numbered]
        if not missing:
            return tuple(numbered[number] for number in sorted(numbered))

        by_id = {item.douban_id: item for item in seasons}
        for number in missing:
            target = f"{query} 第{number}季"
            try:
                found = self.search.search_by_title(target, count=min(self.limit, 5))
            except Exception:
                # Completion is optional. Preserve the safe candidates already
                # discovered if Douban throttles or rejects an extra probe.
                continue
            exact_season = [
                item
                for item in found
                if _is_series_season_variant(item, query)
                and _season_number(item, query) == number
            ]
            if len(exact_season) != 1:
                continue
            item = exact_season[0]
            by_id.setdefault(item.douban_id, item)
            numbered[number] = item

        ordered = [numbered[number] for number in sorted(numbered)]
        ordered_ids = {item.douban_id for item in ordered}
        extras = [item for item in by_id.values() if item.douban_id not in ordered_ids]
        return tuple((ordered + extras)[: self.limit])

    def resolve(self, title: str) -> MovieResolveResult:
        query = " ".join(title.split()).strip()
        if not query:
            return MovieResolveResult(MovieResolveKind.NOT_FOUND, query, None, ())

        candidates = tuple(self.search.search_by_title(query, count=self.limit))
        exact = tuple(item for item in candidates if _candidate_matches_title(item, query))
        if len(exact) == 1:
            return MovieResolveResult(MovieResolveKind.EXACT, query, exact[0], exact)
        if len(exact) > 1:
            return MovieResolveResult(MovieResolveKind.AMBIGUOUS, query, None, exact)

        seasons = tuple(item for item in candidates if _is_series_season_variant(item, query))
        if seasons:
            completed = self._complete_season_family(query, seasons)
            return MovieResolveResult(MovieResolveKind.AMBIGUOUS, query, None, completed)

        return MovieResolveResult(MovieResolveKind.NOT_FOUND, query, None, candidates)
