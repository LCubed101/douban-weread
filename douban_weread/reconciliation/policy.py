from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from douban_weread.core.models import Edition


class ReadingState(str, Enum):
    NONE = "none"
    WISH = "wish"
    READING = "reading"
    READ = "read"
    UNKNOWN = "unknown"


class ReconciliationAction(str, Enum):
    SAFE_TO_WISH = "safe_to_wish"
    NOOP_ALREADY_WISH = "noop_already_wish"
    NOOP_ALREADY_READING = "noop_already_reading"
    NOOP_ALREADY_READ = "noop_already_read"
    REVIEW_OTHER_WISH_EDITION = "review_other_wish_edition"
    REVIEW_OTHER_READING_EDITION = "review_other_reading_edition"
    REVIEW_UNKNOWN_STATE = "review_unknown_state"
    ASK_REREAD = "ask_reread"


class WeReadReadingState(str, Enum):
    UNREAD = "unread"
    READING = "reading"
    READ = "read"
    UNKNOWN = "unknown"


class CrossPlatformStateAction(str, Enum):
    NOOP_ALIGNED = "noop_aligned"
    SUGGEST_WISH = "suggest_wish"
    SUGGEST_READING = "suggest_reading"
    SUGGEST_READ = "suggest_read"
    KEEP_HIGHER_DOUBAN_STATE = "keep_higher_douban_state"
    ASK_REREAD = "ask_reread"
    REVIEW_IDENTITY = "review_identity"
    REVIEW_UNKNOWN_STATE = "review_unknown_state"


@dataclass(slots=True)
class WorkStateRecord:
    edition: Edition
    state: ReadingState
    raw_state: str | None = None
    is_target: bool = False


@dataclass(slots=True)
class ReconciliationDecision:
    target: Edition
    records: list[WorkStateRecord]
    action: ReconciliationAction
    safe_to_write_wish: bool
    requires_user_decision: bool
    reason: str


@dataclass(slots=True, frozen=True)
class CrossPlatformStateDecision:
    weread_state: WeReadReadingState
    douban_state: ReadingState
    suggested_douban_state: ReadingState
    action: CrossPlatformStateAction
    same_work_verified: bool
    exact_edition_verified: bool
    safe_to_auto_apply: bool
    requires_user_decision: bool
    reason: str


def reading_state_from_douban(raw_state: str | None) -> ReadingState:
    return {
        None: ReadingState.NONE,
        "wish": ReadingState.WISH,
        "do": ReadingState.READING,
        "collect": ReadingState.READ,
    }.get(raw_state, ReadingState.UNKNOWN)


def weread_reading_state_from_progress(
    progress: int,
    *,
    is_started: bool,
    finish_time: int | None,
) -> WeReadReadingState:
    """Map official WeRead progress evidence conservatively.

    `readUpdateTime` is intentionally not an input. Live `/shelf/sync`
    validation showed that field can be populated even for a 0%-progress,
    never-started book.
    """
    if not 0 <= progress <= 100:
        return WeReadReadingState.UNKNOWN
    if progress == 100:
        return WeReadReadingState.READ if finish_time is not None else WeReadReadingState.UNKNOWN
    if 0 < progress < 100:
        return WeReadReadingState.READING
    if progress == 0 and not is_started:
        return WeReadReadingState.UNREAD
    if progress == 0 and is_started:
        return WeReadReadingState.READING
    return WeReadReadingState.UNKNOWN


def recommend_douban_state_from_weread(
    weread_state: WeReadReadingState,
    douban_state: ReadingState,
    *,
    same_work_verified: bool,
    exact_edition_verified: bool,
) -> CrossPlatformStateDecision:
    """Recommend, but never auto-apply, a Douban state from verified WeRead evidence.

    Work identity must be verified before any cross-platform state suggestion.
    Exact Edition identity is recorded separately because a same-Work alternative
    Edition can support a Work-level state suggestion while still requiring
    Edition review before a concrete write.

    v0.2 is deliberately read-only: every state-changing suggestion has
    `safe_to_auto_apply=False`.
    """
    if not same_work_verified:
        return CrossPlatformStateDecision(
            weread_state=weread_state,
            douban_state=douban_state,
            suggested_douban_state=douban_state,
            action=CrossPlatformStateAction.REVIEW_IDENTITY,
            same_work_verified=False,
            exact_edition_verified=exact_edition_verified,
            safe_to_auto_apply=False,
            requires_user_decision=True,
            reason="Work identity is not verified; do not copy reading state across platforms.",
        )

    if weread_state is WeReadReadingState.UNKNOWN or douban_state is ReadingState.UNKNOWN:
        return CrossPlatformStateDecision(
            weread_state=weread_state,
            douban_state=douban_state,
            suggested_douban_state=douban_state,
            action=CrossPlatformStateAction.REVIEW_UNKNOWN_STATE,
            same_work_verified=True,
            exact_edition_verified=exact_edition_verified,
            safe_to_auto_apply=False,
            requires_user_decision=True,
            reason="At least one platform has an unknown reading state; fail closed.",
        )

    edition_note = (
        " Exact Edition identity is verified."
        if exact_edition_verified
        else " The Work is verified, but the Edition differs or is not exact; review Edition choice before any write."
    )

    if weread_state is WeReadReadingState.UNREAD:
        if douban_state is ReadingState.NONE:
            return CrossPlatformStateDecision(
                weread_state=weread_state,
                douban_state=douban_state,
                suggested_douban_state=ReadingState.WISH,
                action=CrossPlatformStateAction.SUGGEST_WISH,
                same_work_verified=True,
                exact_edition_verified=exact_edition_verified,
                safe_to_auto_apply=False,
                requires_user_decision=True,
                reason=(
                    "The verified Work is on the WeRead shelf but has not been started; "
                    "treat Want-to-Read as a suggestion, not an automatic equivalence."
                    + edition_note
                ),
            )
        if douban_state is ReadingState.WISH:
            return CrossPlatformStateDecision(
                weread_state=weread_state,
                douban_state=douban_state,
                suggested_douban_state=ReadingState.WISH,
                action=CrossPlatformStateAction.NOOP_ALIGNED,
                same_work_verified=True,
                exact_edition_verified=exact_edition_verified,
                safe_to_auto_apply=False,
                requires_user_decision=False,
                reason="WeRead is unread and Douban is already Want-to-Read; no state change is needed." + edition_note,
            )
        return CrossPlatformStateDecision(
            weread_state=weread_state,
            douban_state=douban_state,
            suggested_douban_state=douban_state,
            action=CrossPlatformStateAction.KEEP_HIGHER_DOUBAN_STATE,
            same_work_verified=True,
            exact_edition_verified=exact_edition_verified,
            safe_to_auto_apply=False,
            requires_user_decision=False,
            reason="WeRead is unread; do not downgrade an existing Douban Reading/Read state." + edition_note,
        )

    if weread_state is WeReadReadingState.READING:
        if douban_state in {ReadingState.NONE, ReadingState.WISH}:
            return CrossPlatformStateDecision(
                weread_state=weread_state,
                douban_state=douban_state,
                suggested_douban_state=ReadingState.READING,
                action=CrossPlatformStateAction.SUGGEST_READING,
                same_work_verified=True,
                exact_edition_verified=exact_edition_verified,
                safe_to_auto_apply=False,
                requires_user_decision=True,
                reason="WeRead has verified in-progress reading evidence; suggest upgrading Douban to Reading." + edition_note,
            )
        if douban_state is ReadingState.READING:
            return CrossPlatformStateDecision(
                weread_state=weread_state,
                douban_state=douban_state,
                suggested_douban_state=ReadingState.READING,
                action=CrossPlatformStateAction.NOOP_ALIGNED,
                same_work_verified=True,
                exact_edition_verified=exact_edition_verified,
                safe_to_auto_apply=False,
                requires_user_decision=False,
                reason="Both platforms indicate Reading; no state change is needed." + edition_note,
            )
        return CrossPlatformStateDecision(
            weread_state=weread_state,
            douban_state=douban_state,
            suggested_douban_state=ReadingState.READ,
            action=CrossPlatformStateAction.ASK_REREAD,
            same_work_verified=True,
            exact_edition_verified=exact_edition_verified,
            safe_to_auto_apply=False,
            requires_user_decision=True,
            reason=(
                "Douban already records this Work as Read while WeRead shows active reading; "
                "treat this as a possible reread and never downgrade the historical Read state automatically."
                + edition_note
            ),
        )

    if weread_state is WeReadReadingState.READ:
        if douban_state is ReadingState.READ:
            return CrossPlatformStateDecision(
                weread_state=weread_state,
                douban_state=douban_state,
                suggested_douban_state=ReadingState.READ,
                action=CrossPlatformStateAction.NOOP_ALIGNED,
                same_work_verified=True,
                exact_edition_verified=exact_edition_verified,
                safe_to_auto_apply=False,
                requires_user_decision=False,
                reason="Both platforms indicate Read; no state change is needed." + edition_note,
            )
        return CrossPlatformStateDecision(
            weread_state=weread_state,
            douban_state=douban_state,
            suggested_douban_state=ReadingState.READ,
            action=CrossPlatformStateAction.SUGGEST_READ,
            same_work_verified=True,
            exact_edition_verified=exact_edition_verified,
            safe_to_auto_apply=False,
            requires_user_decision=True,
            reason="WeRead has verified completed-reading evidence; suggest upgrading Douban to Read." + edition_note,
        )

    return CrossPlatformStateDecision(
        weread_state=weread_state,
        douban_state=douban_state,
        suggested_douban_state=douban_state,
        action=CrossPlatformStateAction.REVIEW_UNKNOWN_STATE,
        same_work_verified=True,
        exact_edition_verified=exact_edition_verified,
        safe_to_auto_apply=False,
        requires_user_decision=True,
        reason="The cross-platform reading state could not be reconciled safely.",
    )


def reconcile_work_states(
    target: Edition,
    records: list[WorkStateRecord],
) -> ReconciliationDecision:
    """Choose a conservative action from all known states for one Work.

    State precedence is used only to prevent accidental downgrade. It does not
    silently copy state between editions and it does not infer a reread.
    Unknown states fail closed rather than being treated as NONE.
    """

    target_record = next((record for record in records if record.is_target), None)
    target_state = target_record.state if target_record else ReadingState.UNKNOWN

    if target_state is ReadingState.UNKNOWN:
        return ReconciliationDecision(
            target=target,
            records=records,
            action=ReconciliationAction.REVIEW_UNKNOWN_STATE,
            safe_to_write_wish=False,
            requires_user_decision=True,
            reason="The selected edition has an unknown reading state; do not treat it as unmarked.",
        )

    if target_state is ReadingState.READ:
        return ReconciliationDecision(
            target=target,
            records=records,
            action=ReconciliationAction.NOOP_ALREADY_READ,
            safe_to_write_wish=False,
            requires_user_decision=False,
            reason="The selected edition is already marked read; do not downgrade it to Want-to-Read.",
        )

    if target_state is ReadingState.READING:
        return ReconciliationDecision(
            target=target,
            records=records,
            action=ReconciliationAction.NOOP_ALREADY_READING,
            safe_to_write_wish=False,
            requires_user_decision=False,
            reason="The selected edition is already marked reading; do not downgrade it to Want-to-Read.",
        )

    if target_state is ReadingState.WISH:
        return ReconciliationDecision(
            target=target,
            records=records,
            action=ReconciliationAction.NOOP_ALREADY_WISH,
            safe_to_write_wish=False,
            requires_user_decision=False,
            reason="The selected edition is already marked Want-to-Read.",
        )

    other_records = [record for record in records if not record.is_target]

    if any(record.state is ReadingState.UNKNOWN for record in other_records):
        return ReconciliationDecision(
            target=target,
            records=records,
            action=ReconciliationAction.REVIEW_UNKNOWN_STATE,
            safe_to_write_wish=False,
            requires_user_decision=True,
            reason=(
                "At least one same-Work edition has an unknown reading state. "
                "Fail closed until the provider state can be interpreted."
            ),
        )

    if any(record.state is ReadingState.READ for record in other_records):
        return ReconciliationDecision(
            target=target,
            records=records,
            action=ReconciliationAction.ASK_REREAD,
            safe_to_write_wish=False,
            requires_user_decision=True,
            reason=(
                "Another edition of the same Work is already marked read. "
                "Treat the new target as a possible reread and ask before changing state."
            ),
        )

    if any(record.state is ReadingState.READING for record in other_records):
        return ReconciliationDecision(
            target=target,
            records=records,
            action=ReconciliationAction.REVIEW_OTHER_READING_EDITION,
            safe_to_write_wish=False,
            requires_user_decision=True,
            reason=(
                "Another edition of the same Work is currently marked reading. "
                "Do not create a competing Want-to-Read state automatically."
            ),
        )

    if any(record.state is ReadingState.WISH for record in other_records):
        return ReconciliationDecision(
            target=target,
            records=records,
            action=ReconciliationAction.REVIEW_OTHER_WISH_EDITION,
            safe_to_write_wish=False,
            requires_user_decision=True,
            reason=(
                "Another edition of the same Work is already marked Want-to-Read. "
                "This is an edition mismatch that should be reviewed rather than duplicated."
            ),
        )

    return ReconciliationDecision(
        target=target,
        records=records,
        action=ReconciliationAction.SAFE_TO_WISH,
        safe_to_write_wish=True,
        requires_user_decision=True,
        reason=(
            "No existing Want-to-Read, reading, or read state was found for the resolved Work. "
            "The selected edition may proceed to an explicitly confirmed Want-to-Read write."
        ),
    )
