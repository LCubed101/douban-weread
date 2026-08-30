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


class DoubanMovieResolver:
    """Fail-closed resolver for Movie/TV titles.

    V1.2 intentionally auto-selects only when one exact title/alias match is
    present. Multiple exact matches (remakes, TV vs film, same-name works) stay
    ambiguous and must be confirmed by the user later in the Feishu layer.
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
        return MovieResolveResult(MovieResolveKind.NOT_FOUND, query, None, candidates)
