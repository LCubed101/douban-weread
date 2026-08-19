from __future__ import annotations

from typing import Protocol

from douban_weread.core.models import Edition
from douban_weread.resolver import rank_editions

from .policy import (
    ReadingState,
    ReconciliationDecision,
    WorkStateRecord,
    reading_state_from_douban,
    reconcile_work_states,
)


class DoubanSearchProvider(Protocol):
    def get_by_subject_id(self, subject_id: str) -> Edition | None: ...

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]: ...


class DoubanInterestProvider(Protocol):
    def get_interest_status(self, subject_id: str) -> str | None: ...


class HistoryStatus(Protocol):
    complete: bool


class HistoryCandidate(Protocol):
    subject_id: str
    title: str
    state: str


class ReadingHistoryProvider(Protocol):
    def status(self) -> HistoryStatus: ...

    def find_title_candidates(
        self,
        title: str,
        *,
        limit: int = 30,
        min_similarity: float = 0.72,
    ) -> list[HistoryCandidate]: ...


class IncompleteHistoryBaselineError(RuntimeError):
    """Raised when exhaustive reconciliation requires a missing/stale baseline."""


_STATE_PRECEDENCE = {
    ReadingState.NONE: 0,
    ReadingState.WISH: 1,
    ReadingState.READING: 2,
    ReadingState.READ: 3,
}


def _reconcile_snapshot_and_live_state(
    snapshot_raw: str | None,
    live_raw: str | None,
) -> tuple[ReadingState, str | None]:
    """Keep the more conservative known state across snapshot and live reads.

    The local history snapshot is intentionally allowed to remember a stronger
    state than the current provider read. That prevents an old READ/READING
    record from being silently downgraded to WISH/NONE during a write-safety
    check. Unexpected provider values remain UNKNOWN and fail closed.
    """

    snapshot_state = reading_state_from_douban(snapshot_raw)
    live_state = reading_state_from_douban(live_raw)

    if snapshot_state is ReadingState.UNKNOWN or live_state is ReadingState.UNKNOWN:
        raw = live_raw if live_state is ReadingState.UNKNOWN else snapshot_raw
        return ReadingState.UNKNOWN, raw

    if _STATE_PRECEDENCE[snapshot_state] >= _STATE_PRECEDENCE[live_state]:
        return snapshot_state, snapshot_raw
    return live_state, live_raw


class DoubanWorkInspector:
    """Discover same-Work Douban editions and reconcile their reading states.

    Title search remains a useful live discovery path, but it is not exhaustive
    for forgotten reading history. When a complete local history provider is
    supplied, its title shortlist contributes additional subject IDs. Those IDs
    are resolved to full Edition metadata and must still pass the normal
    same-Work resolver before their state can affect reconciliation.
    """

    def __init__(
        self,
        search_provider: DoubanSearchProvider,
        interest_provider: DoubanInterestProvider,
        *,
        candidate_limit: int = 20,
        history_provider: ReadingHistoryProvider | None = None,
        history_candidate_limit: int = 30,
        require_complete_history: bool = False,
    ) -> None:
        self.search_provider = search_provider
        self.interest_provider = interest_provider
        self.candidate_limit = max(1, min(candidate_limit, 20))
        self.history_provider = history_provider
        self.history_candidate_limit = max(1, min(history_candidate_limit, 100))
        self.require_complete_history = require_complete_history

    def inspect_subject(self, subject_id: str) -> ReconciliationDecision:
        target = self.search_provider.get_by_subject_id(subject_id)
        if target is None:
            raise ValueError(f"Douban subject {subject_id} could not be resolved to an edition.")
        if not target.douban_id:
            raise ValueError("Resolved Douban edition is missing its subject ID.")

        history_candidates: list[HistoryCandidate] = []
        if self.history_provider is not None:
            history_status = self.history_provider.status()
            if not history_status.complete:
                if self.require_complete_history:
                    raise IncompleteHistoryBaselineError(
                        "Local reading-history baseline is not complete. "
                        "Run `douban-weread history sync --full` before exhaustive reconciliation."
                    )
            else:
                history_candidates = self.history_provider.find_title_candidates(
                    target.title,
                    limit=self.history_candidate_limit,
                )
        elif self.require_complete_history:
            raise IncompleteHistoryBaselineError(
                "A complete local reading-history baseline is required for exhaustive reconciliation."
            )

        candidates = self.search_provider.search_by_title(
            target.title,
            count=self.candidate_limit,
        )

        by_subject: dict[str, Edition] = {target.douban_id: target}
        for candidate in candidates:
            if candidate.douban_id:
                by_subject.setdefault(candidate.douban_id, candidate)

        history_states: dict[str, str] = {}
        for candidate in history_candidates:
            history_states[candidate.subject_id] = candidate.state
            if candidate.subject_id in by_subject:
                continue
            edition = self.search_provider.get_by_subject_id(candidate.subject_id)
            if edition is None:
                raise ValueError(
                    "Local history candidate could not be resolved to full Edition metadata: "
                    f"Douban subject {candidate.subject_id}. Refresh the baseline or retry later."
                )
            if edition.douban_id:
                by_subject.setdefault(edition.douban_id, edition)

        ranked = rank_editions(target, by_subject.values())
        same_work = [result.candidate for result in ranked if result.same_work]

        records: list[WorkStateRecord] = []
        for edition in same_work:
            if not edition.douban_id:
                continue
            live_raw = self.interest_provider.get_interest_status(edition.douban_id)
            if edition.douban_id in history_states:
                state, raw_state = _reconcile_snapshot_and_live_state(
                    history_states[edition.douban_id],
                    live_raw,
                )
            else:
                state = reading_state_from_douban(live_raw)
                raw_state = live_raw
            records.append(
                WorkStateRecord(
                    edition=edition,
                    state=state,
                    raw_state=raw_state,
                    is_target=edition.douban_id == target.douban_id,
                )
            )

        # The target is always inserted into by_subject, and an Edition compared
        # with itself is an exact ISBN match when ISBN exists. For ISBN-missing
        # records, keep a final defensive fallback so the selected subject is
        # never omitted from its own Work history.
        if not any(record.is_target for record in records):
            live_raw = self.interest_provider.get_interest_status(target.douban_id)
            if target.douban_id in history_states:
                state, raw_state = _reconcile_snapshot_and_live_state(
                    history_states[target.douban_id],
                    live_raw,
                )
            else:
                state = reading_state_from_douban(live_raw)
                raw_state = live_raw
            records.insert(
                0,
                WorkStateRecord(
                    edition=target,
                    state=state,
                    raw_state=raw_state,
                    is_target=True,
                ),
            )

        return reconcile_work_states(target, records)
