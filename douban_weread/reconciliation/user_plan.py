from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from douban_weread.core.models import WeReadStatus

from .policy import CrossPlatformStateAction
from .shelf_batch import DOUBAN_TO_WEREAD, WEREAD_TO_DOUBAN, BatchItemResult


class UserPlanKind(str, Enum):
    """Stable product-level categories above provider/resolver details."""

    ALIGNED = "aligned"
    ADD_TO_WEREAD_SHELF_EXACT = "add_to_weread_shelf_exact"
    ADD_TO_WEREAD_SHELF_ALTERNATIVE = "add_to_weread_shelf_alternative"
    SUGGEST_DOUBAN_WISH = "suggest_douban_wish"
    SUGGEST_DOUBAN_READING = "suggest_douban_reading"
    REMIND_DOUBAN_WRAP_UP = "remind_douban_wrap_up"
    KEEP_DOUBAN_HISTORY = "keep_douban_history"
    REVIEW_REREAD = "review_reread"
    REVIEW_EDITION = "review_edition"
    REVIEW_IDENTITY = "review_identity"
    REVIEW_STATE = "review_state"
    WEREAD_UNAVAILABLE = "weread_unavailable"
    WEREAD_NOT_FOUND = "weread_not_found"
    WEREAD_COMING_SOON = "weread_coming_soon"


@dataclass(slots=True, frozen=True)
class UserReconciliationPlan:
    kind: UserPlanKind
    summary: str
    requires_user_action: bool
    deep_link: str | None = None


def user_plan_for_batch_item(item: BatchItemResult) -> UserReconciliationPlan:
    """Collapse a verified batch result into one user-facing product action.

    Provider status, resolver kind, progress, and checkpoint details remain
    available for diagnostics, but UI/CLI surfaces should use this stable layer
    when describing what the user should understand or do next.
    """

    if item.direction == WEREAD_TO_DOUBAN:
        return _weread_to_douban_plan(item)
    if item.direction == DOUBAN_TO_WEREAD:
        return _douban_to_weread_plan(item)
    raise ValueError(f"Unsupported reconciliation direction: {item.direction}")


def _weread_to_douban_plan(item: BatchItemResult) -> UserReconciliationPlan:
    verification = item.shelf_verification
    if verification is None:
        raise ValueError("WeRead-to-Douban batch item is missing shelf verification")

    decision = verification.decision
    action = decision.action

    if action is CrossPlatformStateAction.NOOP_ALIGNED:
        return UserReconciliationPlan(
            kind=UserPlanKind.ALIGNED,
            summary="The verified Work already has an aligned Douban reading state.",
            requires_user_action=False,
        )

    if action in {
        CrossPlatformStateAction.SUGGEST_WISH,
        CrossPlatformStateAction.SUGGEST_READING,
    } and not decision.exact_edition_verified:
        return UserReconciliationPlan(
            kind=UserPlanKind.REVIEW_EDITION,
            summary=(
                "The Work is verified, but the WeRead and Douban Editions are not exact; "
                "review the Edition before applying the suggested Douban state."
            ),
            requires_user_action=True,
        )

    if action is CrossPlatformStateAction.SUGGEST_WISH:
        return UserReconciliationPlan(
            kind=UserPlanKind.SUGGEST_DOUBAN_WISH,
            summary="The exact Work/Edition is on the WeRead shelf but not started; suggest marking it Want-to-Read on Douban.",
            requires_user_action=True,
        )
    if action is CrossPlatformStateAction.SUGGEST_READING:
        return UserReconciliationPlan(
            kind=UserPlanKind.SUGGEST_DOUBAN_READING,
            summary="WeRead shows verified active reading; suggest marking the verified Douban Work as Reading.",
            requires_user_action=True,
        )
    if action is CrossPlatformStateAction.REMIND_DOUBAN_WRAP_UP:
        return UserReconciliationPlan(
            kind=UserPlanKind.REMIND_DOUBAN_WRAP_UP,
            summary=(
                "WeRead shows verified completion. Keep the Douban finish step human: "
                "remind the user to mark Read and write their own note or review on Douban."
            ),
            requires_user_action=True,
        )
    if action is CrossPlatformStateAction.KEEP_HIGHER_DOUBAN_STATE:
        return UserReconciliationPlan(
            kind=UserPlanKind.KEEP_DOUBAN_HISTORY,
            summary="Douban already has a stronger historical state; keep it and do not downgrade from WeRead evidence.",
            requires_user_action=False,
        )
    if action is CrossPlatformStateAction.ASK_REREAD:
        return UserReconciliationPlan(
            kind=UserPlanKind.REVIEW_REREAD,
            summary="Douban already records Read while WeRead shows active reading; review this as a possible reread.",
            requires_user_action=True,
        )
    if action is CrossPlatformStateAction.REVIEW_IDENTITY:
        return UserReconciliationPlan(
            kind=UserPlanKind.REVIEW_IDENTITY,
            summary="Work identity is not verified strongly enough to copy reading state across platforms.",
            requires_user_action=True,
        )
    if action is CrossPlatformStateAction.REVIEW_UNKNOWN_STATE:
        return UserReconciliationPlan(
            kind=UserPlanKind.REVIEW_STATE,
            summary="At least one reading state is unknown or inconsistent; review before any synchronization.",
            requires_user_action=True,
        )

    raise ValueError(f"Unsupported WeRead-to-Douban state action: {action.value}")


def _douban_to_weread_plan(item: BatchItemResult) -> UserReconciliationPlan:
    alignment = item.catalog_alignment
    if alignment is None:
        raise ValueError("Douban-to-WeRead batch item is missing catalog alignment")

    intent = alignment.intent
    status = intent.weread_status
    deep_link = intent.source_url

    if status is WeReadStatus.AVAILABLE_EXACT:
        if intent.selected_edition is None or not intent.selected_edition.weread_id:
            return UserReconciliationPlan(
                kind=UserPlanKind.REVIEW_IDENTITY,
                summary="WeRead reports exact availability but no concrete selected Edition was resolved.",
                requires_user_action=True,
                deep_link=deep_link,
            )
        if item.selected_shelf_book is not None:
            return UserReconciliationPlan(
                kind=UserPlanKind.ALIGNED,
                summary="The exact resolved WeRead Edition is already on the current shelf.",
                requires_user_action=False,
                deep_link=deep_link,
            )
        return UserReconciliationPlan(
            kind=UserPlanKind.ADD_TO_WEREAD_SHELF_EXACT,
            summary="An exact WeRead Edition is available but is not on the current shelf.",
            requires_user_action=True,
            deep_link=deep_link,
        )

    if status is WeReadStatus.AVAILABLE_ALTERNATIVE:
        if intent.selected_edition is None or not intent.selected_edition.weread_id:
            return UserReconciliationPlan(
                kind=UserPlanKind.REVIEW_IDENTITY,
                summary="WeRead reports an alternative Edition but no concrete selected Edition was resolved.",
                requires_user_action=True,
                deep_link=deep_link,
            )
        if alignment.match is not None and alignment.match.requires_confirmation:
            return UserReconciliationPlan(
                kind=UserPlanKind.REVIEW_EDITION,
                summary="A same-Work WeRead Edition is available, but material Edition differences require review.",
                requires_user_action=True,
                deep_link=deep_link,
            )
        if item.selected_shelf_book is not None:
            return UserReconciliationPlan(
                kind=UserPlanKind.ALIGNED,
                summary="A verified alternative Edition of the Work is already on the current WeRead shelf.",
                requires_user_action=False,
                deep_link=deep_link,
            )
        return UserReconciliationPlan(
            kind=UserPlanKind.ADD_TO_WEREAD_SHELF_ALTERNATIVE,
            summary="A verified alternative WeRead Edition is available but is not on the current shelf.",
            requires_user_action=True,
            deep_link=deep_link,
        )

    if status is WeReadStatus.UNAVAILABLE:
        return UserReconciliationPlan(
            kind=UserPlanKind.WEREAD_UNAVAILABLE,
            summary="A same-Work WeRead Edition was found, but the current catalog marks it unavailable.",
            requires_user_action=False,
            deep_link=deep_link,
        )
    if status is WeReadStatus.NOT_FOUND:
        return UserReconciliationPlan(
            kind=UserPlanKind.WEREAD_NOT_FOUND,
            summary="No same-Work WeRead Edition was resolved within the bounded catalog search window.",
            requires_user_action=False,
        )
    if status is WeReadStatus.COMING_SOON:
        return UserReconciliationPlan(
            kind=UserPlanKind.WEREAD_COMING_SOON,
            summary="The WeRead catalog indicates this Work is coming soon.",
            requires_user_action=False,
            deep_link=deep_link,
        )

    raise ValueError(f"Unsupported WeRead catalog status: {status.value}")
