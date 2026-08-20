from __future__ import annotations

import unittest

from douban_weread.reconciliation.shelf_preview import build_shelf_preview
from douban_weread.storage import IndexedHistoryEntry, IndexedWeReadShelfBook


def douban(subject_id: str, title: str, state: str) -> IndexedHistoryEntry:
    return IndexedHistoryEntry(
        subject_id=subject_id,
        title=title,
        state=state,
        title_key="unused",
        last_seen_at="2026-08-20T00:00:00+00:00",
    )


def weread(
    book_id: str,
    title: str,
    *,
    finished: bool = False,
    read_update_time: int | None = None,
) -> IndexedWeReadShelfBook:
    return IndexedWeReadShelfBook(
        book_id=book_id,
        title=title,
        author=None,
        deep_link=None,
        category=None,
        finish_reading=finished,
        read_update_time=read_update_time,
        secret=False,
        title_key="unused",
        last_seen_at="2026-08-20T00:00:00+00:00",
    )


class ShelfPreviewTests(unittest.TestCase):
    def test_exact_normalized_title_overlap_and_one_sided_counts(self) -> None:
        report = build_shelf_preview(
            [douban("1", "白夜行", "collect"), douban("2", "豆瓣独有", "wish")],
            [weread("10", "白 夜 行"), weread("20", "微信独有")],
        )

        self.assertEqual(report.shared_title_keys, 1)
        self.assertEqual(report.active_shared_title_keys, 0)
        self.assertEqual(report.douban_entries_with_exact_title, 1)
        self.assertEqual(report.active_douban_entries_with_exact_title, 0)
        self.assertEqual(report.weread_books_with_exact_title, 1)
        self.assertEqual([item.subject_id for item in report.douban_only_entries], ["2"])
        self.assertEqual([item.subject_id for item in report.active_douban_only_entries], ["2"])
        self.assertEqual([item.book_id for item in report.weread_only_books], ["20"])
        self.assertEqual([item.book_id for item in report.read_history_overlap_books], ["10"])

    def test_read_history_absence_from_shelf_is_not_active_sync_gap(self) -> None:
        report = build_shelf_preview(
            [
                douban("1", "过去读过", "collect"),
                douban("2", "现在想读", "wish"),
                douban("3", "正在读", "do"),
            ],
            [],
        )

        self.assertEqual(report.douban_wish, 1)
        self.assertEqual(report.douban_reading, 1)
        self.assertEqual(report.douban_read, 1)
        self.assertEqual(len(report.douban_only_entries), 3)
        self.assertEqual(
            [item.subject_id for item in report.active_douban_only_entries],
            ["2", "3"],
        )

    def test_weread_book_matching_douban_read_history_is_not_weread_only(self) -> None:
        report = build_shelf_preview(
            [douban("1", "已经读过", "collect")],
            [weread("10", "已经读过")],
        )

        self.assertEqual(report.weread_only_books, ())
        self.assertEqual([item.book_id for item in report.read_history_overlap_books], ["10"])

    def test_finished_weread_singleton_flags_possible_douban_state_conflict(self) -> None:
        report = build_shelf_preview(
            [douban("1", "同一本书", "wish")],
            [weread("10", "同一本书", finished=True, read_update_time=123)],
        )

        self.assertEqual(report.weread_finished, 1)
        self.assertEqual(report.weread_with_read_activity, 1)
        self.assertEqual(len(report.possible_state_conflicts), 1)
        conflict = report.possible_state_conflicts[0]
        self.assertEqual(conflict.douban_subject_id, "1")
        self.assertEqual(conflict.weread_book_id, "10")
        self.assertEqual(conflict.douban_state, "wish")

    def test_duplicate_title_group_is_ambiguous_and_not_promoted_to_state_conflict(self) -> None:
        report = build_shelf_preview(
            [douban("1", "重名书", "wish"), douban("2", "重名书", "collect")],
            [weread("10", "重名书", finished=True)],
        )

        self.assertEqual(report.ambiguous_shared_title_keys, 1)
        self.assertEqual(report.douban_entries_with_exact_title, 2)
        self.assertEqual(report.active_douban_entries_with_exact_title, 1)
        self.assertEqual(report.weread_books_with_exact_title, 1)
        self.assertEqual(report.possible_state_conflicts, ())


if __name__ == "__main__":
    unittest.main()
