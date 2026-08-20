from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from douban_weread.core.models import Edition
from douban_weread.providers.weread import WeReadProgress
from douban_weread.resolver import EditionMatchResult, rank_editions
from douban_weread.storage import IndexedHistoryEntry, IndexedWeReadShelfBook

from .policy import (
    CrossPlatformStateDecision,
    ReadingState,
    WeReadReadingState,
    reading_state_from_douban,
    recommend_douban_state_from_weread,
    weread_reading_state_from_progress,
)


class CompleteStatus(Protocol):
    complete: bool


class ShelfProvider(Protocol):
    def status(self) -> CompleteStatus: ...

    def get(self, book_id: str) -> IndexedWeReadShelfBook | None: ...


class HistoryProvider(Protocol):
    def status(self) -> CompleteStatus: ...

    def get(self, subject_id: str) -> IndexedHistoryEntry | None: ...

    def find_title_candidates(
        self,
        title: str,
        *,
        limit: int = 30,
        min_similarity: float = 0.72,
    ) -> list[IndexedHistoryEntry]: ...


class WeReadVerificationProvider(Protocol):
    def get_book(self, book_id: str) -> Edition | None: ...

    def get_progress(self, book_id: str) -> WeReadProgress | None: ...


class DoubanVerificationProvider(Protocol):
    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]: ...

    def get_by_subject_id(self, subject_id: str) -> Edition | None: ...


@dataclass(slots=True, frozen=True)
class VerifiedDoubanCandidate:
    edition: Edition
    match: EditionMatchResult
    history_state: ReadingState


@dataclass(slots=True, frozen=True)
class ShelfVerificationResult:
    shelf_book: IndexedWeReadShelfBook
    weread_edition: Edition
    progress: WeReadProgress
    weread_state: WeReadReadingState
    verified_douban_candidates: tuple[VerifiedDoubanCandidate, ...]
    strongest_douban_state: ReadingState
    decision: CrossPlatformStateDecision
    douban_search_limit: int
    history_candidate_limit: int

    @property
    def best_match(self) -> VerifiedDoubanCandidate | None:
        return self.verified_douban_candidates[0] if self.verified_douban_candidates else None


_STATE_PRECEDENCE = {
    ReadingState.NONE: 0,
    ReadingState.WISH: 1,
    ReadingState.READING: 2,
    ReadingState.READ: 3,
    ReadingState.UNKNOWN: 4,
}


class IncompleteShelfVerificationBaselineError(RuntimeError):
    """Raised when lazy verification lacks one of the required complete local baselines."""


def verify_shelf_book(
    book_id: str,
    *,
    shelf_provider: ShelfProvider,
    history_provider: HistoryProvider,
    weread_provider: WeReadVerificationProvider,
    douban_provider: DoubanVerificationProvider,
    douban_search_limit: int = 3,
    history_candidate_limit: int = 5,
) -> ShelfVerificationResult:
    """Lazily verify one WeRead shelf item against bounded Douban evidence.

    This is deliberately read-only. It combines one local shelf record, full
    WeRead Edition metadata, official user-specific progress, a bounded public
    Douban title search, and a small shortlist from the complete local Douban
    history baseline. Only resolver-confirmed same-Work Douban candidates can
    influence the state recommendation.
    """

    shelf_status = shelf_provider.status()
    history_status = history_provider.status()
    if not shelf_status.complete or not history_status.complete:
        raise IncompleteShelfVerificationBaselineError(
            "Complete WeRead shelf and Douban history baselines are required before lazy verification."
        )

    normalized_id = book_id.strip()
    if not normalized_id:
        raise ValueError("WeRead bookId must not be blank")

    shelf_book = shelf_provider.get(normalized_id)
    if shelf_book is None:
        raise ValueError(
            f"WeRead bookId {normalized_id} is not present in the complete local shelf baseline."
        )

    weread_edition = weread_provider.get_book(normalized_id)
    if weread_edition is None:
        raise ValueError(f"WeRead bookId {normalized_id} could not be resolved to full Edition metadata.")

    progress = weread_provider.get_progress(normalized_id)
    if progress is None:
        raise ValueError(f"WeRead bookId {normalized_id} has no readable progress record.")

    weread_state = weread_reading_state_from_progress(
        progress.progress,
        is_started=progress.is_started,
        finish_time=progress.finish_time,
    )

    search_limit = max(1, min(douban_search_limit, 20))
    history_limit = max(1, min(history_candidate_limit, 30))

    by_subject: dict[str, Edition] = {}
    for edition in douban_provider.search_by_title(weread_edition.title, count=search_limit):
        if edition.douban_id:
            by_subject.setdefault(edition.douban_id, edition)

    history_candidates = history_provider.find_title_candidates(
        weread_edition.title,
        limit=history_limit,
    )
    for history_entry in history_candidates:
        if history_entry.subject_id in by_subject:
            continue
        edition = douban_provider.get_by_subject_id(history_entry.subject_id)
        if edition is not None and edition.douban_id:
            by_subject.setdefault(edition.douban_id, edition)

    ranked = rank_editions(weread_edition, by_subject.values())
    verified: list[VerifiedDoubanCandidate] = []
    for match in ranked:
        if not match.same_work or not match.candidate.douban_id:
            continue
        history_entry = history_provider.get(match.candidate.douban_id)
        state = (
            reading_state_from_douban(history_entry.state)
            if history_entry is not None
            else ReadingState.NONE
        )
        verified.append(
            VerifiedDoubanCandidate(
                edition=match.candidate,
                match=match,
                history_state=state,
            )
        )

    strongest_state = max(
        (candidate.history_state for candidate in verified),
        key=lambda state: _STATE_PRECEDENCE[state],
        default=ReadingState.NONE,
    )
    same_work_verified = bool(verified)
    exact_edition_verified = any(candidate.match.exact_edition for candidate in verified)

    decision = recommend_douban_state_from_weread(
        weread_state,
        strongest_state,
        same_work_verified=same_work_verified,
        exact_edition_verified=exact_edition_verified,
    )

    return ShelfVerificationResult(
        shelf_book=shelf_book,
        weread_edition=weread_edition,
        progress=progress,
        weread_state=weread_state,
        verified_douban_candidates=tuple(verified),
        strongest_douban_state=strongest_state,
        decision=decision,
        douban_search_limit=search_limit,
        history_candidate_limit=history_limit,
    )
