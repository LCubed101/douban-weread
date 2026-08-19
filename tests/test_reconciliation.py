from __future__ import annotations

import unittest
from types import SimpleNamespace

from douban_weread.core.models import Edition
from douban_weread.reconciliation import (
    DoubanWorkInspector,
    IncompleteHistoryBaselineError,
    ReadingState,
    ReconciliationAction,
    WorkStateRecord,
    reading_state_from_douban,
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
    def __init__(
        self,
        target: Edition,
        candidates: list[Edition],
        extra_subjects: list[Edition] | None = None,
    ) -> None:
        self.target = target
        self.candidates = candidates
        self.subjects = {
            item.douban_id: item
            for item in [target, *candidates, *(extra_subjects or [])]
            if item.douban_id
        }
        self.subject_calls: list[str] = []

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        self.subject_calls.append(subject_id)
        return self.subjects.get(subject_id)

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        return self.candidates[:count]


class FakeInterest:
    def __init__(self, states: dict[str, str | None]) -> None:
        self.states = states
        self.calls: list[str] = []

    def get_interest_status(self, subject_id: str) -> str | None:
        self.calls.append(subject_id)
        return self.states.get(subject_id)


class FakeHistory:
    def __init__(self, candidates: list[SimpleNamespace] | None = None, *, complete: bool = True) -> None:
        self.candidates = candidates or []
        self.complete = complete
        self.lookup_calls: list[tuple[str, int]] = []

    def status(self):
        return SimpleNamespace(complete=self.complete)

    def find_title_candidates(
        self,
        title: str,
        *,
        limit: int = 30,
        min_similarity: float = 0.72,
    ):
        self.lookup_calls.append((title, limit))
        return self.candidates[:limit]


def history_candidate(subject_id: str, state: str, title: str = "荷马史诗·奥德赛") -> SimpleNamespace:
    return SimpleNamespace(subject_id=subject_id, title=title, state=state)


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

    def test_unknown_provider_state_fails_closed(self) -> None:
        self.assertEqual(reading_state_from_douban("unexpected"), ReadingState.UNKNOWN)
        decision = self.decision(ReadingState.NONE, ReadingState.UNKNOWN)
        self.assertEqual(decision.action, ReconciliationAction.REVIEW_UNKNOWN_STATE)
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

    def test_history_discovers_same_work_edition_missing_from_live_title_search(self) -> None:
        target = edition("25837854", isbn="9787020102792")
        older = edition("1062694", isbn="9787020038848", year="1997-05")
        history = FakeHistory([history_candidate("1062694", "collect")])
        search = FakeSearch(target, [target], extra_subjects=[older])
        inspector = DoubanWorkInspector(
            search,
            FakeInterest({"25837854": None, "1062694": None}),
            history_provider=history,
            require_complete_history=True,
        )

        decision = inspector.inspect_subject("25837854")

        self.assertEqual(decision.action, ReconciliationAction.ASK_REREAD)
        self.assertEqual(
            {record.edition.douban_id: record.state for record in decision.records},
            {"25837854": ReadingState.NONE, "1062694": ReadingState.READ},
        )
        self.assertIn("1062694", search.subject_calls)
        self.assertEqual(history.lookup_calls, [("荷马史诗·奥德赛", 30)])

    def test_complete_history_is_required_when_configured(self) -> None:
        target = edition("25837854", isbn="9787020102792")
        inspector = DoubanWorkInspector(
            FakeSearch(target, [target]),
            FakeInterest({"25837854": None}),
            history_provider=FakeHistory(complete=False),
            require_complete_history=True,
        )

        with self.assertRaisesRegex(IncompleteHistoryBaselineError, "history sync --full"):
            inspector.inspect_subject("25837854")

    def test_history_snapshot_prevents_live_state_downgrade(self) -> None:
        target = edition("25837854", isbn="9787020102792")
        history = FakeHistory([history_candidate("25837854", "collect")])
        inspector = DoubanWorkInspector(
            FakeSearch(target, [target]),
            FakeInterest({"25837854": None}),
            history_provider=history,
            require_complete_history=True,
        )

        decision = inspector.inspect_subject("25837854")

        self.assertEqual(decision.action, ReconciliationAction.NOOP_ALREADY_READ)
        target_record = next(record for record in decision.records if record.is_target)
        self.assertEqual(target_record.state, ReadingState.READ)

    def test_live_upgrade_overrides_weaker_history_snapshot(self) -> None:
        target = edition("25837854", isbn="9787020102792")
        history = FakeHistory([history_candidate("25837854", "wish")])
        inspector = DoubanWorkInspector(
            FakeSearch(target, [target]),
            FakeInterest({"25837854": "collect"}),
            history_provider=history,
            require_complete_history=True,
        )

        decision = inspector.inspect_subject("25837854")

        self.assertEqual(decision.action, ReconciliationAction.NOOP_ALREADY_READ)
        target_record = next(record for record in decision.records if record.is_target)
        self.assertEqual(target_record.state, ReadingState.READ)


if __name__ == "__main__":
    unittest.main()
