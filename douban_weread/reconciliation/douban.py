from __future__ import annotations

from typing import Protocol

from douban_weread.core.models import Edition
from douban_weread.resolver import rank_editions

from .policy import (
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


class DoubanWorkInspector:
    """Discover same-Work Douban editions and reconcile their reading states."""

    def __init__(
        self,
        search_provider: DoubanSearchProvider,
        interest_provider: DoubanInterestProvider,
        *,
        candidate_limit: int = 10,
    ) -> None:
        self.search_provider = search_provider
        self.interest_provider = interest_provider
        self.candidate_limit = max(1, min(candidate_limit, 20))

    def inspect_subject(self, subject_id: str) -> ReconciliationDecision:
        target = self.search_provider.get_by_subject_id(subject_id)
        if target is None:
            raise ValueError(f"Douban subject {subject_id} could not be resolved to an edition.")
        if not target.douban_id:
            raise ValueError("Resolved Douban edition is missing its subject ID.")

        candidates = self.search_provider.search_by_title(
            target.title,
            count=self.candidate_limit,
        )

        by_subject: dict[str, Edition] = {target.douban_id: target}
        for candidate in candidates:
            if candidate.douban_id:
                by_subject.setdefault(candidate.douban_id, candidate)

        ranked = rank_editions(target, by_subject.values())
        same_work = [result.candidate for result in ranked if result.same_work]

        records: list[WorkStateRecord] = []
        for edition in same_work:
            if not edition.douban_id:
                continue
            raw_state = self.interest_provider.get_interest_status(edition.douban_id)
            records.append(
                WorkStateRecord(
                    edition=edition,
                    state=reading_state_from_douban(raw_state),
                    raw_state=raw_state,
                    is_target=edition.douban_id == target.douban_id,
                )
            )

        # The target is always inserted into by_subject, and an Edition compared
        # with itself is an exact ISBN match when ISBN exists. For ISBN-missing
        # records, keep a final defensive fallback so the selected subject is
        # never omitted from its own Work history.
        if not any(record.is_target for record in records):
            raw_state = self.interest_provider.get_interest_status(target.douban_id)
            records.insert(
                0,
                WorkStateRecord(
                    edition=target,
                    state=reading_state_from_douban(raw_state),
                    raw_state=raw_state,
                    is_target=True,
                ),
            )

        return reconcile_work_states(target, records)
