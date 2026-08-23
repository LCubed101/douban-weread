from __future__ import annotations

import unittest

from douban_weread.reconciliation import (
    CrossPlatformStateAction,
    ReadingState,
    WeReadReadingState,
    recommend_douban_state_from_weread,
    weread_reading_state_from_progress,
)


class CrossPlatformStatePolicyTests(unittest.TestCase):
    def test_zero_percent_not_started_is_unread(self) -> None:
        state = weread_reading_state_from_progress(0, is_started=False, finish_time=None)
        self.assertEqual(state, WeReadReadingState.UNREAD)

    def test_zero_percent_started_is_reading(self) -> None:
        state = weread_reading_state_from_progress(0, is_started=True, finish_time=None)
        self.assertEqual(state, WeReadReadingState.READING)

    def test_partial_progress_is_reading(self) -> None:
        state = weread_reading_state_from_progress(37, is_started=True, finish_time=None)
        self.assertEqual(state, WeReadReadingState.READING)

    def test_hundred_percent_requires_finish_time_to_be_read(self) -> None:
        complete = weread_reading_state_from_progress(100, is_started=True, finish_time=123)
        inconsistent = weread_reading_state_from_progress(100, is_started=True, finish_time=None)
        self.assertEqual(complete, WeReadReadingState.READ)
        self.assertEqual(inconsistent, WeReadReadingState.UNKNOWN)

    def test_unverified_work_never_produces_state_copy(self) -> None:
        decision = recommend_douban_state_from_weread(
            WeReadReadingState.READING,
            ReadingState.NONE,
            same_work_verified=False,
            exact_edition_verified=False,
        )
        self.assertEqual(decision.action, CrossPlatformStateAction.REVIEW_IDENTITY)
        self.assertFalse(decision.safe_to_auto_apply)
        self.assertTrue(decision.requires_user_decision)

    def test_unread_shelf_book_with_no_douban_state_only_suggests_wish(self) -> None:
        decision = recommend_douban_state_from_weread(
            WeReadReadingState.UNREAD,
            ReadingState.NONE,
            same_work_verified=True,
            exact_edition_verified=True,
        )
        self.assertEqual(decision.action, CrossPlatformStateAction.SUGGEST_WISH)
        self.assertEqual(decision.suggested_douban_state, ReadingState.WISH)
        self.assertFalse(decision.safe_to_auto_apply)
        self.assertTrue(decision.requires_user_decision)

    def test_reading_upgrades_none_or_wish_to_reading_suggestion(self) -> None:
        for current in (ReadingState.NONE, ReadingState.WISH):
            with self.subTest(current=current):
                decision = recommend_douban_state_from_weread(
                    WeReadReadingState.READING,
                    current,
                    same_work_verified=True,
                    exact_edition_verified=True,
                )
                self.assertEqual(decision.action, CrossPlatformStateAction.SUGGEST_READING)
                self.assertEqual(decision.suggested_douban_state, ReadingState.READING)
                self.assertFalse(decision.safe_to_auto_apply)

    def test_completed_weread_reminds_for_human_douban_wrap_up(self) -> None:
        for current in (ReadingState.NONE, ReadingState.WISH, ReadingState.READING):
            with self.subTest(current=current):
                decision = recommend_douban_state_from_weread(
                    WeReadReadingState.READ,
                    current,
                    same_work_verified=True,
                    exact_edition_verified=True,
                )
                self.assertEqual(
                    decision.action,
                    CrossPlatformStateAction.REMIND_DOUBAN_WRAP_UP,
                )
                self.assertEqual(decision.suggested_douban_state, current)
                self.assertFalse(decision.safe_to_auto_apply)
                self.assertTrue(decision.requires_user_decision)
                self.assertIn("human wrap-up", decision.reason)
                self.assertIn("never auto-apply", decision.reason)

    def test_completed_weread_and_douban_read_is_already_aligned(self) -> None:
        decision = recommend_douban_state_from_weread(
            WeReadReadingState.READ,
            ReadingState.READ,
            same_work_verified=True,
            exact_edition_verified=True,
        )
        self.assertEqual(decision.action, CrossPlatformStateAction.NOOP_ALIGNED)
        self.assertEqual(decision.suggested_douban_state, ReadingState.READ)
        self.assertFalse(decision.safe_to_auto_apply)
        self.assertFalse(decision.requires_user_decision)

    def test_douban_read_plus_weread_reading_is_possible_reread(self) -> None:
        decision = recommend_douban_state_from_weread(
            WeReadReadingState.READING,
            ReadingState.READ,
            same_work_verified=True,
            exact_edition_verified=False,
        )
        self.assertEqual(decision.action, CrossPlatformStateAction.ASK_REREAD)
        self.assertEqual(decision.suggested_douban_state, ReadingState.READ)
        self.assertFalse(decision.safe_to_auto_apply)
        self.assertTrue(decision.requires_user_decision)
        self.assertIn("Edition", decision.reason)


if __name__ == "__main__":
    unittest.main()
