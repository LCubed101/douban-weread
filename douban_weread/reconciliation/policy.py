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


def reading_state_from_douban(raw_state: str | None) -> ReadingState:
    return {
        None: ReadingState.NONE,
        "wish": ReadingState.WISH,
        "do": ReadingState.READING,
        "collect": ReadingState.READ,
    }.get(raw_state, ReadingState.UNKNOWN)


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
