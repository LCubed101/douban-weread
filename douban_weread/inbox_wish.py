from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from enum import Enum
from http.cookies import SimpleCookie
from typing import Protocol

from douban_weread.providers.douban import (
    DoubanAuthError,
    DoubanBookInterestClient,
    DoubanBookSearchClient,
    DoubanProviderError,
    DoubanWriteVerificationError,
)
from douban_weread.reconciliation import (
    DoubanWorkInspector,
    IncompleteHistoryBaselineError,
    ReconciliationAction,
    ReconciliationDecision,
)
from douban_weread.storage import ReadingHistoryIndex


class WishFlowKind(str, Enum):
    READY = "ready"
    ALREADY_WISH = "already_wish"
    BLOCKED = "blocked"
    WRITTEN = "written"


@dataclass(slots=True, frozen=True)
class WishFlowResult:
    kind: WishFlowKind
    subject_id: str
    title: str | None
    message: str
    decision: ReconciliationDecision | None = None


class SearchProvider(Protocol):
    def get_by_subject_id(self, subject_id: str): ...

    def search_by_title(self, title: str, *, count: int = 20): ...


class InterestProvider(Protocol):
    def get_interest_status(self, subject_id: str) -> str | None: ...

    def mark_wish(self, subject_id: str, *, confirmed: bool = False): ...


class HistoryProvider(Protocol):
    def status(self): ...

    def find_title_candidates(self, title: str, *, limit: int = 30, min_similarity: float = 0.72): ...

    def set_state(self, subject_id: str, title: str, state: str) -> None: ...


def _read_cookie_env() -> str:
    cookie = os.getenv("DOUBAN_COOKIE", "").strip()
    if "\n" not in cookie and cookie.lower().startswith("cookie:"):
        cookie = cookie.split(":", 1)[1].strip()
    return cookie


def default_interest_provider() -> DoubanBookInterestClient:
    return DoubanBookInterestClient(cookie=_read_cookie_env())


class DoubanWishFlow:
    """Two-step Want-to-Read flow for interactive clients such as Feishu.

    `preflight()` is read-only. `commit()` repeats the same Work-level safety
    inspection immediately before the write, so a stale first confirmation
    cannot authorize a later state change. The underlying interest client also
    performs read-back verification after the write.
    """

    def __init__(
        self,
        search_provider: SearchProvider | None = None,
        interest_provider: InterestProvider | None = None,
        history_provider: HistoryProvider | None = None,
    ) -> None:
        self.search_provider = search_provider or DoubanBookSearchClient()
        self.interest_provider = interest_provider or default_interest_provider()
        self.history_provider = history_provider or ReadingHistoryIndex()

    def preflight(self, subject_id: str) -> WishFlowResult:
        decision = self._inspect(subject_id)
        title = decision.target.title
        if decision.action is ReconciliationAction.NOOP_ALREADY_WISH:
            return WishFlowResult(
                kind=WishFlowKind.ALREADY_WISH,
                subject_id=subject_id,
                title=title,
                message=f"《{title}》已经在豆瓣标记为想读，不需要重复添加。",
                decision=decision,
            )
        if not decision.safe_to_write_wish:
            return WishFlowResult(
                kind=WishFlowKind.BLOCKED,
                subject_id=subject_id,
                title=title,
                message=(
                    f"《{title}》暂时不能安全加入豆瓣想读。"
                    f"需要先处理已有阅读状态或版本关系：{decision.reason}"
                ),
                decision=decision,
            )
        return WishFlowResult(
            kind=WishFlowKind.READY,
            subject_id=subject_id,
            title=title,
            message=f"《{title}》已通过豆瓣写入前检查。再次确认后才会加入想读。",
            decision=decision,
        )

    def commit(self, subject_id: str) -> WishFlowResult:
        # Re-run preflight at the moment of mutation to avoid trusting stale UI state.
        preflight = self.preflight(subject_id)
        if preflight.kind is not WishFlowKind.READY:
            return preflight

        result = self.interest_provider.mark_wish(subject_id, confirmed=True)
        title = preflight.title or preflight.decision.target.title  # type: ignore[union-attr]
        try:
            self.history_provider.set_state(subject_id, title, "wish")
        except (ValueError, OSError, sqlite3.Error):
            # The provider write has already been verified. A stale local cache is
            # recoverable by the next full history sync and must not be reported as
            # a failed remote write.
            pass

        return WishFlowResult(
            kind=WishFlowKind.WRITTEN,
            subject_id=result.subject_id,
            title=title,
            message=f"《{title}》已加入豆瓣想读，并完成写后验证。",
            decision=preflight.decision,
        )

    def _inspect(self, subject_id: str) -> ReconciliationDecision:
        inspector = DoubanWorkInspector(
            self.search_provider,
            self.interest_provider,
            candidate_limit=20,
            history_provider=self.history_provider,
            history_candidate_limit=30,
            require_complete_history=True,
        )
        return inspector.inspect_subject(subject_id)


WISH_FLOW_ERRORS = (
    DoubanAuthError,
    DoubanProviderError,
    DoubanWriteVerificationError,
    IncompleteHistoryBaselineError,
    ValueError,
    OSError,
    sqlite3.Error,
)
