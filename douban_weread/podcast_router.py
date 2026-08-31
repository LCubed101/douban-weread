from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from douban_weread.providers.xiaoyuzhou import XiaoyuzhouEpisodeCandidate, XiaoyuzhouSearchClient


class PodcastResolveKind(str, Enum):
    EXACT = "exact"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


@dataclass(slots=True, frozen=True)
class PodcastResolveResult:
    kind: PodcastResolveKind
    query: str
    podcast: str | None
    selected: XiaoyuzhouEpisodeCandidate | None
    candidates: tuple[XiaoyuzhouEpisodeCandidate, ...]


class PodcastSearchLike(Protocol):
    def search_episodes(self, keyword: str, *, limit: int = 10) -> list[XiaoyuzhouEpisodeCandidate]: ...


def _norm(value: str | None) -> str:
    return re.sub(r"[\W_]+", "", str(value or ""), flags=re.UNICODE).casefold()


def _episode_matches_title(item: XiaoyuzhouEpisodeCandidate, query: str) -> bool:
    return _norm(item.title) == _norm(query)


def _podcast_matches(item: XiaoyuzhouEpisodeCandidate, podcast: str | None) -> bool:
    if not podcast:
        return True
    return _norm(item.podcast_title) == _norm(podcast)


class XiaoyuzhouEpisodeResolver:
    """Fail-closed resolver for Xiaoyuzhou podcast episodes.

    V1.3 intentionally auto-selects only an exact episode-title match, optionally
    constrained by an exact podcast title. Keyword-only or fuzzy search results
    remain ambiguous/not-found until we have enough real usage data to define a
    safer ranking policy.
    """

    def __init__(self, search: PodcastSearchLike | None = None, *, limit: int = 10) -> None:
        self.search = search or XiaoyuzhouSearchClient()
        self.limit = max(1, min(limit, 20))

    def resolve(self, title: str, *, podcast: str | None = None) -> PodcastResolveResult:
        query = " ".join(title.split()).strip()
        podcast_query = " ".join(str(podcast or "").split()).strip() or None
        if not query:
            return PodcastResolveResult(PodcastResolveKind.NOT_FOUND, query, podcast_query, None, ())

        candidates = tuple(self.search.search_episodes(query, limit=self.limit))
        scoped = tuple(item for item in candidates if _podcast_matches(item, podcast_query))
        exact = tuple(item for item in scoped if _episode_matches_title(item, query))
        if len(exact) == 1:
            return PodcastResolveResult(PodcastResolveKind.EXACT, query, podcast_query, exact[0], exact)
        if len(exact) > 1:
            return PodcastResolveResult(PodcastResolveKind.AMBIGUOUS, query, podcast_query, None, exact)

        # If an exact podcast was supplied, return the scoped candidates so the
        # caller can inspect whether the search term was too fuzzy. Otherwise keep
        # all results visible for diagnostics, but never auto-pick one.
        visible = scoped if podcast_query else candidates
        return PodcastResolveResult(
            PodcastResolveKind.AMBIGUOUS if len(visible) > 1 else PodcastResolveKind.NOT_FOUND,
            query,
            podcast_query,
            None,
            visible,
        )
