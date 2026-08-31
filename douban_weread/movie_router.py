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
    r"^(?:第[一二三四五六七八九十百\d]+季|season\d+)$",
    re.IGNORECASE,
)


def _is_series_season_variant(candidate: DoubanMovieCandidate, query: str) -> bool:
    """Return True only for conservative `<query> + season` title variants.

    Douban stores many TV franchises only as per-season subjects, so a bare
    series query such as `流人` can legitimately return `流人 第一季`, `流人 第二季`,
    ... with no exact subject called simply `流人`. Treat those as an ambiguous
    TV-series family rather than as fuzzy matches, but never auto-select a season.
    """

    query_norm = _normalize_title(query)
    if not query_norm:
        return False

    for raw in (candidate.title, *candidate.aliases):
        value_norm = _normalize_title(raw)
        if not value_norm.startswith(query_norm) or value_norm == query_norm:
            continue
        suffix = value_norm[len(query_norm) :]
        if _SEASON_SUFFIX_RE.fullmatch(suffix):
            return True
    return False


class DoubanMovieResolver:
    """Fail-closed resolver for Movie/TV titles.

    V1.2 auto-selects only when one exact title/alias match is present. Multiple
    exact matches stay ambiguous. A bare TV franchise query may also resolve to
    an ambiguous family of per-season subjects (`流人` -> `流人 第一季`, ...); this
    keeps TV titles in the Movie/TV route without guessing which season the user
    meant. All unrelated fuzzy matches still fail closed.
    """

    def __init__(self, search: MovieSearchLike | None = None, *, limit: int = 10) -> None:
        self.search = search or DoubanMovieSearchClient()
        self.limit = max(1, min(limit, 20))

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
            return MovieResolveResult(MovieResolveKind.AMBIGUOUS, query, None, seasons)

        return MovieResolveResult(MovieResolveKind.NOT_FOUND, query, None, candidates)
