from __future__ import annotations

import unittest

from douban_weread.core.models import Edition
from douban_weread.reconciliation import (
    DoubanWorkInspector,
    ReadingState,
    ReconciliationAction,
    WorkStateRecord,
    reconcile_work_states,
)


def edition(subject_id: str, *, isbn: str, year: str = "2015-06") -> Edition:
    return Edition(
        title="荷马史诗·奥德赛",
        authors=["[古希腊] 荷马"],
        translators=["王焕生"],
        publisher="人民文学出版社",
        publish_date=year,
        isbn=isbn,
        douban_id=subject_id,
    )


class FakeSearch:
    def __init__(self, target: Edition, candidates: list[Edition]) -> None:
        self.target = target
        self.candidates = candidates

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        return self.target if self.target.douban_id == subject_id else None

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        return self.candidates[:count]


class FakeInterest:
    def __init__(self, states: dict[str, str | None]) -> None:
        self.states = states
        self.calls: list[str] = []

    def get_interest_status(self, subject_id: str) -> str | None:
        self.calls.append(subject_id)
        return self.states.get(subject_id)


class ReconciliationPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = edition("25837854", isbn="9787020102792")
        self.other = edition("1062694", isbn="9787020038848", year="1997-05")

    def decision(self, target_state: ReadingState, other_state: ReadingState):
        return reconcile_work_states(
            self.target,
            [
                WorkStateRecord(self.target, target_state, is_target=True),
                WorkStateRecord(self.other, other_state, is_target=False),
            ],
        )

    def test_target_read_is_never_downgraded_to_wish(self) -> None:
        decision = self.decision(ReadingState.READ, ReadingState.NONE)
        self.assertEqual(decision.action, ReconciliationAction.NOOP_ALREADY_READ)
        self.assertFalse(decision.safe_to_write_wish)

    def test_target_reading_is_never_downgraded_to_wish(self) -> None:
        decision = self.decision(ReadingState.READING, ReadingState.NONE)
        self.assertEqual(decision.action, ReconciliationAction.NOOP_ALREADY_READING)
        self.assertFalse(decision.safe_to_write_wish)

    def test_target_wish_is_noop(self) -> None:
        decision = self.decision(ReadingState.WISH, ReadingState.NONE)
        self.assertEqual(decision.action, ReconciliationAction.NOOP_ALREADY_WISH)
        self.assertFalse(decision.safe_to_write_wish)

    def test_other_read_edition_requires_reread_decision(self) -> None:
        decision = self.decision(ReadingState.NONE, ReadingState.READ)
        self.assertEqual(decision.action, ReconciliationAction.ASK_REREAD)
        self.assertTrue(decision.requires_user_decision)
        self.assertFalse(decision.safe_to_write_wish)

    def test_other_reading_edition_blocks_competing_wish(self) -> None:
        decision = self.decision(ReadingState.NONE, ReadingState.READING)
        self.assertEqual(decision.action, ReconciliationAction.REVIEW_OTHER_READING_EDITION)
        self.assertFalse(decision.safe_to_write_wish)

    def test_other_wish_edition_is_edition_mismatch_not_duplicate_write(self) -> None:
        decision = self.decision(ReadingState.NONE, ReadingState.WISH)
        self.assertEqual(decision.action, ReconciliationAction.REVIEW_OTHER_WISH_EDITION)
        self.assertFalse(decision.safe_to_write_wish)

    def test_no_existing_state_is_safe_to_wish_but_still_requires_confirmation(self) -> None:
        decision = self.decision(ReadingState.NONE, ReadingState.NONE)
        self.assertEqual(decision.action, ReconciliationAction.SAFE_TO_WISH)
        self.assertTrue(decision.safe_to_write_wish)
        self.assertTrue(decision.requires_user_decision)


class DoubanWorkInspectorTests(unittest.TestCase):
    def test_inspector_discovers_same_work_and_maps_douban_states(self) -> None:
        target = edition("25837854", isbn="9787020102792")
        older = edition("1062694", isbn="9787020038848", year="1997-05")
        unrelated = Edition(
            title="伊利亚特",
            authors=["荷马"],
            translators=["另一译者"],
            douban_id="9999999",
            isbn="9780000000000",
        )
        inspector = DoubanWorkInspector(
            FakeSearch(target, [target, older, unrelated]),
            FakeInterest({"25837854": None, "1062694": "collect", "9999999": "wish"}),
        )

        decision = inspector.inspect_subject("25837854")

        self.assertEqual(decision.action, ReconciliationAction.ASK_REREAD)
        self.assertEqual({record.edition.douban_id for record in decision.records}, {"25837854", "1062694"})
        self.assertEqual(
            {record.edition.douban_id: record.state for record in decision.records},
            {
                "25837854": ReadingState.NONE,
                "1062694": ReadingState.READ,
            },
        )

    def test_inspector_keeps_target_even_when_isbn_is_missing(self) -> None:
        target = edition("25837854", isbn="")
        inspector = DoubanWorkInspector(
            FakeSearch(target, [target]),
            FakeInterest({"25837854": None}),
        )

        decision = inspector.inspect_subject("25837854")

        self.assertTrue(any(record.is_target for record in decision.records))
        self.assertEqual(decision.action, ReconciliationAction.SAFE_TO_WISH)


if __name__ == "__main__":
    unittest.main()
