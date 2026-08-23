from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .product_view import (
    ProductReconciliationBucket,
    ProductReconciliationItem,
    ProductReconciliationView,
)
from .user_plan import UserPlanKind


class ProductActionKind(str, Enum):
    """Stable UI intent for one verified reconciliation item.

    These are presentation/action intents only. They do not authorize or perform
    any Douban or WeRead mutation.
    """

    REVIEW_EDITION = "review_edition"
    REVIEW_IDENTITY = "review_identity"
    REVIEW_REREAD = "review_reread"
    REVIEW_STATE = "review_state"
    OPEN_WEREAD = "open_weread"
    UPDATE_DOUBAN_STATE = "update_douban_state"
    REMIND_DOUBAN_WRAP_UP = "remind_douban_wrap_up"
    NONE = "none"


@dataclass(slots=True, frozen=True)
class ReconciliationHomeModel:
    phase: str
    worker_status: str | None
    progress_label: str | None
    verified_total: int | None
    candidate_total: int | None
    pending_total: int | None
    requires_user_action_total: int | None
    aligned_total: int | None
    no_user_action_total: int | None
    review_total: int
    add_to_weread_total: int
    suggest_douban_state_total: int


@dataclass(slots=True, frozen=True)
class ReconciliationInboxItem:
    direction: str
    item_id: str
    title: str
    bucket: ProductReconciliationBucket
    user_plan: UserPlanKind
    action_kind: ProductActionKind
    summary: str
    selected_edition_title: str | None
    weread_book_id: str | None
    deep_link: str | None


@dataclass(slots=True, frozen=True)
class ReconciliationInboxSection:
    bucket: ProductReconciliationBucket
    count: int
    items: tuple[ReconciliationInboxItem, ...]


@dataclass(slots=True, frozen=True)
class ReconciliationActionInboxModel:
    total: int
    sections: tuple[ReconciliationInboxSection, ...]


@dataclass(slots=True, frozen=True)
class ReconciliationDetailModel:
    direction: str
    item_id: str
    title: str
    bucket: ProductReconciliationBucket
    user_plan: UserPlanKind
    action_kind: ProductActionKind
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


_ACTION_BY_PLAN = {
    UserPlanKind.REVIEW_EDITION: ProductActionKind.REVIEW_EDITION,
    UserPlanKind.REVIEW_IDENTITY: ProductActionKind.REVIEW_IDENTITY,
    UserPlanKind.REVIEW_REREAD: ProductActionKind.REVIEW_REREAD,
    UserPlanKind.REVIEW_STATE: ProductActionKind.REVIEW_STATE,
    UserPlanKind.ADD_TO_WEREAD_SHELF_EXACT: ProductActionKind.OPEN_WEREAD,
    UserPlanKind.ADD_TO_WEREAD_SHELF_ALTERNATIVE: ProductActionKind.OPEN_WEREAD,
    UserPlanKind.SUGGEST_DOUBAN_WISH: ProductActionKind.UPDATE_DOUBAN_STATE,
    UserPlanKind.SUGGEST_DOUBAN_READING: ProductActionKind.UPDATE_DOUBAN_STATE,
    UserPlanKind.REMIND_DOUBAN_WRAP_UP: ProductActionKind.REMIND_DOUBAN_WRAP_UP,
    UserPlanKind.ALIGNED: ProductActionKind.NONE,
    UserPlanKind.KEEP_DOUBAN_HISTORY: ProductActionKind.NONE,
    UserPlanKind.WEREAD_NOT_FOUND: ProductActionKind.NONE,
    UserPlanKind.WEREAD_UNAVAILABLE: ProductActionKind.NONE,
    UserPlanKind.WEREAD_COMING_SOON: ProductActionKind.NONE,
}

_INBOX_BUCKET_ORDER = (
    ProductReconciliationBucket.REVIEW,
    ProductReconciliationBucket.ADD_TO_WEREAD,
    ProductReconciliationBucket.SUGGEST_DOUBAN_STATE,
)


def build_reconciliation_home_model(view: ProductReconciliationView) -> ReconciliationHomeModel:
    counts = {item.bucket: item.count for item in view.bucket_counts}
    return ReconciliationHomeModel(
        phase=view.phase.value,
        worker_status=view.worker_status,
        progress_label=view.progress_label,
        verified_total=view.verified_total,
        candidate_total=view.candidate_total,
        pending_total=view.pending_total,
        requires_user_action_total=view.requires_user_action_total,
        aligned_total=view.aligned_total,
        no_user_action_total=view.no_user_action_total,
        review_total=counts.get(ProductReconciliationBucket.REVIEW, 0),
        add_to_weread_total=counts.get(ProductReconciliationBucket.ADD_TO_WEREAD, 0),
        suggest_douban_state_total=counts.get(ProductReconciliationBucket.SUGGEST_DOUBAN_STATE, 0),
    )


def build_reconciliation_action_inbox(view: ProductReconciliationView) -> ReconciliationActionInboxModel:
    """Return only verified items that currently require user action."""

    actionable = tuple(item for item in view.items if item.requires_user_action)
    sections: list[ReconciliationInboxSection] = []
    for bucket in _INBOX_BUCKET_ORDER:
        rows = tuple(item for item in actionable if item.bucket is bucket)
        if not rows:
            continue
        sections.append(
            ReconciliationInboxSection(
                bucket=bucket,
                count=len(rows),
                items=tuple(_inbox_item(item) for item in rows),
            )
        )

    represented = sum(section.count for section in sections)
    if represented != len(actionable):
        unknown = [item.user_plan.value for item in actionable if item.bucket not in _INBOX_BUCKET_ORDER]
        raise ValueError(
            "Actionable reconciliation items have no inbox section: " + ", ".join(unknown)
        )

    return ReconciliationActionInboxModel(total=len(actionable), sections=tuple(sections))


def get_reconciliation_detail(
    view: ProductReconciliationView,
    *,
    direction: str,
    item_id: str,
) -> ReconciliationDetailModel | None:
    """Return one current-generation verified detail row, or None if unverified/absent."""

    matches = [
        item
        for item in view.items
        if item.direction == direction and item.item_id == item_id
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("Product reconciliation view contains duplicate item identity")
    item = matches[0]
    return ReconciliationDetailModel(
        direction=item.direction,
        item_id=item.item_id,
        title=item.title,
        bucket=item.bucket,
        user_plan=item.user_plan,
        action_kind=_action_kind(item),
        requires_user_action=item.requires_user_action,
        summary=item.summary,
        source_state=item.source_state,
        douban_subject_id=item.douban_subject_id,
        weread_book_id=item.weread_book_id,
        selected_edition_title=item.selected_edition_title,
        shelf_membership=item.shelf_membership,
        match_kind=item.match_kind,
        weread_reading_state=item.weread_reading_state,
        weread_progress=item.weread_progress,
        strongest_douban_state=item.strongest_douban_state,
        suggested_douban_state=item.suggested_douban_state,
        deep_link=item.deep_link,
    )


def _inbox_item(item: ProductReconciliationItem) -> ReconciliationInboxItem:
    return ReconciliationInboxItem(
        direction=item.direction,
        item_id=item.item_id,
        title=item.title,
        bucket=item.bucket,
        user_plan=item.user_plan,
        action_kind=_action_kind(item),
        summary=item.summary,
        selected_edition_title=item.selected_edition_title,
        weread_book_id=item.weread_book_id,
        deep_link=item.deep_link,
    )


def _action_kind(item: ProductReconciliationItem) -> ProductActionKind:
    try:
        action = _ACTION_BY_PLAN[item.user_plan]
    except KeyError as exc:
        raise ValueError(f"User plan has no product action mapping: {item.user_plan.value}") from exc
    if item.requires_user_action and action is ProductActionKind.NONE:
        raise ValueError(
            f"Actionable item maps to no product action: {item.user_plan.value}"
        )
    return action
