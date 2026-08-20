from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum

from douban_weread.storage import ReconciliationEvidence

from .evidence_report import build_reconciliation_evidence_report
from .onboarding import (
    FirstLoginReconciliationPhase,
    get_first_login_reconciliation_view,
)
from .shelf_batch import DOUBAN_TO_WEREAD, WEREAD_TO_DOUBAN
from .user_plan import UserPlanKind
from .worker import WorkerStateProvider


class ProductReconciliationBucket(str, Enum):
    """Stable user-facing grouping above individual UserPlanKind values."""

    ALIGNED = "aligned"
    ADD_TO_WEREAD = "add_to_weread"
    SUGGEST_DOUBAN_STATE = "suggest_douban_state"
    REVIEW = "review"
    KEEP_DOUBAN_HISTORY = "keep_douban_history"
    WEREAD_NOT_FOUND = "weread_not_found"
    WEREAD_UNAVAILABLE = "weread_unavailable"
    WEREAD_COMING_SOON = "weread_coming_soon"


@dataclass(slots=True, frozen=True)
class ProductBucketCount:
    bucket: ProductReconciliationBucket
    count: int


@dataclass(slots=True, frozen=True)
class ProductReconciliationItem:
    """UI-safe detail row backed only by normalized current-generation evidence."""

    direction: str
    item_id: str
    title: str
    bucket: ProductReconciliationBucket
    user_plan: UserPlanKind
    requires_user_action: bool
    summary: str
    source_state: str | None
    douban_subject_id: str | None
    weread_book_id: str | None
    selected_edition_title: str | None
    shelf_membership: str | None
    match_kind: str | None
    weread_reading_state: str | None
    weread_progress: int | None
    strongest_douban_state: str | None
    suggested_douban_state: str | None
    deep_link: str | None


@dataclass(slots=True, frozen=True)
class ProductReconciliationView:
    """One local-only product payload suitable for home/progress/detail UI."""

    phase: FirstLoginReconciliationPhase
    ready_for_reconciliation: bool
    douban_baseline_complete: bool
    weread_baseline_complete: bool
    missing_baselines: tuple[str, ...]
    last_error_kind: str | None
    worker_status: str | None
    worker_ticks: int | None
    candidate_total: int | None
    verified_total: int | None
    pending_total: int | None
    requires_user_action_total: int | None
    aligned_total: int | None
    no_user_action_total: int | None
    bucket_counts: tuple[ProductBucketCount, ...]
    items: tuple[ProductReconciliationItem, ...]

    @property
    def progress_percent(self) -> int | None:
        if self.candidate_total is None or self.verified_total is None:
            return None
        if self.candidate_total == 0:
            return 100
        return int((self.verified_total * 100) / self.candidate_total)


_BUCKET_BY_PLAN = {
    UserPlanKind.ALIGNED: ProductReconciliationBucket.ALIGNED,
    UserPlanKind.ADD_TO_WEREAD_SHELF_EXACT: ProductReconciliationBucket.ADD_TO_WEREAD,
    UserPlanKind.ADD_TO_WEREAD_SHELF_ALTERNATIVE: ProductReconciliationBucket.ADD_TO_WEREAD,
    UserPlanKind.SUGGEST_DOUBAN_WISH: ProductReconciliationBucket.SUGGEST_DOUBAN_STATE,
    UserPlanKind.SUGGEST_DOUBAN_READING: ProductReconciliationBucket.SUGGEST_DOUBAN_STATE,
    UserPlanKind.SUGGEST_DOUBAN_READ: ProductReconciliationBucket.SUGGEST_DOUBAN_STATE,
    UserPlanKind.KEEP_DOUBAN_HISTORY: ProductReconciliationBucket.KEEP_DOUBAN_HISTORY,
    UserPlanKind.REVIEW_REREAD: ProductReconciliationBucket.REVIEW,
    UserPlanKind.REVIEW_EDITION: ProductReconciliationBucket.REVIEW,
    UserPlanKind.REVIEW_IDENTITY: ProductReconciliationBucket.REVIEW,
    UserPlanKind.REVIEW_STATE: ProductReconciliationBucket.REVIEW,
    UserPlanKind.WEREAD_NOT_FOUND: ProductReconciliationBucket.WEREAD_NOT_FOUND,
    UserPlanKind.WEREAD_UNAVAILABLE: ProductReconciliationBucket.WEREAD_UNAVAILABLE,
    UserPlanKind.WEREAD_COMING_SOON: ProductReconciliationBucket.WEREAD_COMING_SOON,
}

_BUCKET_SORT_ORDER = {
    ProductReconciliationBucket.REVIEW: 0,
    ProductReconciliationBucket.ADD_TO_WEREAD: 1,
    ProductReconciliationBucket.SUGGEST_DOUBAN_STATE: 2,
    ProductReconciliationBucket.ALIGNED: 3,
    ProductReconciliationBucket.KEEP_DOUBAN_HISTORY: 4,
    ProductReconciliationBucket.WEREAD_UNAVAILABLE: 5,
    ProductReconciliationBucket.WEREAD_COMING_SOON: 6,
    ProductReconciliationBucket.WEREAD_NOT_FOUND: 7,
}


def build_product_reconciliation_view(
    *,
    shelf_provider,
    history_provider,
    evidence_provider,
    state_provider: WorkerStateProvider,
) -> ProductReconciliationView:
    """Build one UI-ready local view without provider network calls or mutation.

    Missing baselines intentionally produce unknown coverage (`None`) instead of
    zeroes. Once both baselines are complete, only current baseline/policy
    evidence is classified; pending candidates remain explicitly pending.
    """

    onboarding = get_first_login_reconciliation_view(
        shelf_provider=shelf_provider,
        history_provider=history_provider,
        evidence_provider=evidence_provider,
        state_provider=state_provider,
    )
    if not onboarding.ready_for_reconciliation:
        return ProductReconciliationView(
            phase=onboarding.phase,
            ready_for_reconciliation=False,
            douban_baseline_complete=onboarding.douban_baseline_complete,
            weread_baseline_complete=onboarding.weread_baseline_complete,
            missing_baselines=onboarding.missing_baselines,
            last_error_kind=onboarding.last_error_kind,
            worker_status=None,
            worker_ticks=None,
            candidate_total=None,
            verified_total=None,
            pending_total=None,
            requires_user_action_total=None,
            aligned_total=None,
            no_user_action_total=None,
            bucket_counts=(),
            items=(),
        )

    report = build_reconciliation_evidence_report(
        shelf_provider=shelf_provider,
        history_provider=history_provider,
        evidence_provider=evidence_provider,
    )
    rows = tuple(
        row
        for direction in (WEREAD_TO_DOUBAN, DOUBAN_TO_WEREAD)
        for row in report.for_direction(direction).evidence
    )
    items = tuple(sorted((_product_item(row) for row in rows), key=_item_sort_key))
    bucket_counter = Counter(item.bucket for item in items)
    bucket_counts = tuple(
        ProductBucketCount(bucket=bucket, count=bucket_counter[bucket])
        for bucket in ProductReconciliationBucket
        if bucket_counter[bucket]
    )

    candidate_total = sum(item.candidate_total for item in report.directions)
    verified_total = sum(item.verified_total for item in report.directions)
    pending_total = sum(item.pending_total for item in report.directions)
    requires_user_action_total = sum(
        item.requires_user_action_total for item in report.directions
    )
    aligned_total = bucket_counter[ProductReconciliationBucket.ALIGNED]
    no_user_action_total = verified_total - requires_user_action_total
    worker = onboarding.worker

    return ProductReconciliationView(
        phase=onboarding.phase,
        ready_for_reconciliation=True,
        douban_baseline_complete=True,
        weread_baseline_complete=True,
        missing_baselines=(),
        last_error_kind=onboarding.last_error_kind,
        worker_status=worker.status.value if worker is not None else None,
        worker_ticks=worker.tick_count if worker is not None else None,
        candidate_total=candidate_total,
        verified_total=verified_total,
        pending_total=pending_total,
        requires_user_action_total=requires_user_action_total,
        aligned_total=aligned_total,
        no_user_action_total=no_user_action_total,
        bucket_counts=bucket_counts,
        items=items,
    )


def _product_item(row: ReconciliationEvidence) -> ProductReconciliationItem:
    try:
        plan = UserPlanKind(row.user_plan)
    except ValueError as exc:
        raise ValueError(
            f"Unknown persisted user plan cannot be shown safely: {row.user_plan}"
        ) from exc
    try:
        bucket = _BUCKET_BY_PLAN[plan]
    except KeyError as exc:  # defensive guard if a new enum value is added later
        raise ValueError(f"User plan has no product bucket: {plan.value}") from exc

    return ProductReconciliationItem(
        direction=row.direction,
        item_id=row.item_id,
        title=row.title,
        bucket=bucket,
        user_plan=plan,
        requires_user_action=row.requires_user_action,
        summary=row.summary,
        source_state=row.source_state,
        douban_subject_id=row.selected_douban_subject,
        weread_book_id=row.selected_weread_book_id,
        selected_edition_title=row.selected_edition_title,
        shelf_membership=row.shelf_membership,
        match_kind=row.match_kind,
        weread_reading_state=row.weread_reading_state,
        weread_progress=row.weread_progress,
        strongest_douban_state=row.strongest_douban_state,
        suggested_douban_state=row.suggested_douban_state,
        deep_link=row.deep_link,
    )


def _item_sort_key(item: ProductReconciliationItem) -> tuple[object, ...]:
    return (
        0 if item.requires_user_action else 1,
        _BUCKET_SORT_ORDER[item.bucket],
        item.title.casefold(),
        item.direction,
        item.item_id,
    )
