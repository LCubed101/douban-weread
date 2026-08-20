from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from douban_weread.storage import ReconciliationEvidence

from .shelf_batch import (
    DOUBAN_TO_WEREAD,
    WEREAD_TO_DOUBAN,
    _POLICY_VERSION_BY_DIRECTION,
)
from .shelf_preview import build_shelf_preview
from .shelf_verify import IncompleteShelfVerificationBaselineError


class BaselineStatus(Protocol):
    complete: bool
    last_full_sync_at: str | None


class ShelfProvider(Protocol):
    def status(self) -> BaselineStatus: ...

    def all_books(self) -> list[object]: ...


class HistoryProvider(Protocol):
    def status(self) -> BaselineStatus: ...

    def all_entries(self) -> list[object]: ...


class EvidenceProvider(Protocol):
    def list_generation(
        self,
        direction: str,
        *,
        shelf_sync_at: str,
        history_sync_at: str,
        policy_version: int,
    ) -> list[ReconciliationEvidence]: ...


@dataclass(slots=True, frozen=True)
class PlanCount:
    user_plan: str
    count: int


@dataclass(slots=True, frozen=True)
class DirectionEvidenceReport:
    direction: str
    policy_version: int
    candidate_total: int
    verified_total: int
    pending_total: int
    requires_user_action_total: int
    plan_counts: tuple[PlanCount, ...]
    evidence: tuple[ReconciliationEvidence, ...]
    orphaned_evidence_total: int


@dataclass(slots=True, frozen=True)
class ReconciliationEvidenceReport:
    shelf_sync_at: str
    history_sync_at: str
    directions: tuple[DirectionEvidenceReport, ...]

    def for_direction(self, direction: str) -> DirectionEvidenceReport:
        for item in self.directions:
            if item.direction == direction:
                return item
        raise KeyError(direction)


def build_reconciliation_evidence_report(
    *,
    shelf_provider: ShelfProvider,
    history_provider: HistoryProvider,
    evidence_provider: EvidenceProvider,
) -> ReconciliationEvidenceReport:
    """Summarize only verified normalized evidence for the current baselines.

    Candidate totals still come from the complete local baseline preview, but no
    pending item is classified until the current direction/policy generation has
    a persisted evidence row. This keeps partial batch coverage explicit and
    prevents a small verified sample from being presented as a full-library
    reconciliation result.
    """

    shelf_status = shelf_provider.status()
    history_status = history_provider.status()
    if not shelf_status.complete or not history_status.complete:
        raise IncompleteShelfVerificationBaselineError(
            "Both complete baselines are required before reading a reconciliation evidence report."
        )
    if not shelf_status.last_full_sync_at or not history_status.last_full_sync_at:
        raise IncompleteShelfVerificationBaselineError(
            "Complete baseline timestamps are required before reading a reconciliation evidence report."
        )

    preview = build_shelf_preview(
        history_provider.all_entries(),
        shelf_provider.all_books(),
    )
    candidate_ids = {
        WEREAD_TO_DOUBAN: {book.book_id for book in preview.weread_only_books},
        DOUBAN_TO_WEREAD: {
            entry.subject_id for entry in preview.active_douban_only_entries
        },
    }

    directions: list[DirectionEvidenceReport] = []
    for direction in (WEREAD_TO_DOUBAN, DOUBAN_TO_WEREAD):
        policy_version = _POLICY_VERSION_BY_DIRECTION[direction]
        rows = evidence_provider.list_generation(
            direction,
            shelf_sync_at=shelf_status.last_full_sync_at,
            history_sync_at=history_status.last_full_sync_at,
            policy_version=policy_version,
        )
        current_ids = candidate_ids[direction]
        current_rows = tuple(row for row in rows if row.item_id in current_ids)
        orphaned = len(rows) - len(current_rows)
        plan_counter = Counter(row.user_plan for row in current_rows)
        plan_counts = tuple(
            PlanCount(user_plan=plan, count=count)
            for plan, count in sorted(
                plan_counter.items(),
                key=lambda item: (-item[1], item[0]),
            )
        )
        candidate_total = len(current_ids)
        verified_total = len(current_rows)
        directions.append(
            DirectionEvidenceReport(
                direction=direction,
                policy_version=policy_version,
                candidate_total=candidate_total,
                verified_total=verified_total,
                pending_total=max(0, candidate_total - verified_total),
                requires_user_action_total=sum(
                    1 for row in current_rows if row.requires_user_action
                ),
                plan_counts=plan_counts,
                evidence=current_rows,
                orphaned_evidence_total=orphaned,
            )
        )

    return ReconciliationEvidenceReport(
        shelf_sync_at=shelf_status.last_full_sync_at,
        history_sync_at=history_status.last_full_sync_at,
        directions=tuple(directions),
    )
