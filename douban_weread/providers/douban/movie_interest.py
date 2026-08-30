from __future__ import annotations

from typing import Mapping

from .interest import (
    AuthStatus,
    DoubanBookInterestClient,
    InterestMutationResult,
    Transport,
)

DEFAULT_MOVIE_BASE_URL = "https://movie.douban.com"


class DoubanMovieInterestClient(DoubanBookInterestClient):
    """Authenticated adapter for Douban Movie `想看` state.

    Douban uses the same `wish` interest value for Movie/TV `想看` that Book
    uses for `想读`. This adapter deliberately uses movie.douban.com so movie
    writes never go through the Book host by accident. All inherited safety
    properties remain: explicit confirmation, auth checks, anti-abuse fail
    closed behavior, and post-write verification.
    """

    def __init__(
        self,
        cookie: str | None = None,
        *,
        base_url: str = DEFAULT_MOVIE_BASE_URL,
        timeout: float = 10.0,
        user_agent: str | None = None,
        transport: Transport | None = None,
    ) -> None:
        kwargs: dict[str, object] = {
            "cookie": cookie,
            "base_url": base_url,
            "timeout": timeout,
            "transport": transport,
        }
        if user_agent is not None:
            kwargs["user_agent"] = user_agent
        super().__init__(**kwargs)

    def mark_want_to_watch(self, subject_id: str, *, confirmed: bool = False) -> InterestMutationResult:
        return self.mark_wish(subject_id, confirmed=confirmed)

    def get_want_to_watch_status(self, subject_id: str) -> str | None:
        return self.get_interest_status(subject_id)

    def check_auth(self, *, probe_subject_id: str = "1295644") -> AuthStatus:
        # 1295644 is a stable public movie subject used only for a read-only
        # authenticated endpoint probe; callers may override it.
        return super().check_auth(probe_subject_id=probe_subject_id)
