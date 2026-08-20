from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from douban_weread.core.models import Edition
from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.providers.weread import WeReadProgress, WeReadSearchCandidate, WeReadShelfSnapshot
from douban_weread.reconciliation import DOUBAN_TO_WEREAD, run_reconciliation_batch
from douban_weread.storage import (
    CURRENT_RECONCILIATION_POLICY_VERSION,
    ReadingHistoryIndex,
    ReconciliationCheckpointStore,
    WeReadShelfIndex,
)


class ExactDouban:
    def __init__(self, subject_id: str, title: str, isbn: str) -> None:
        self.subject_id = subject_id
        self.title = title
        self.isbn = isbn

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        if subject_id != self.subject_id:
            return None
        return Edition(
            title=self.title,
            authors=["作者"],
            isbn=self.isbn,
            douban_id=subject_id,
        )

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        raise AssertionError("title search is not used in Douban-to-WeRead batch")


class RecordingWeRead:
    def __init__(self, title: str, isbn: str) -> None:
        self.title = title
        self.isbn = isbn
        self.search_counts: list[int] = []

    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        self.search_counts.append(count)
        return [
            WeReadSearchCandidate(
                book_id="9001",
                title=self.title,
                author="作者",
                soldout=False,
            )
        ]

    def get_book(self, book_id: str) -> Edition | None:
        return Edition(
            title=self.title,
            authors=["作者"],
            isbn=self.isbn,
            weread_id=book_id,
        )

    def get_progress(self, book_id: str) -> WeReadProgress | None:
        raise AssertionError("progress is not used in Douban-to-WeRead batch")


class ShelfBatchPolicyV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.shelf = WeReadShelfIndex(self.path)
        self.history = ReadingHistoryIndex(self.path)
        self.checkpoints = ReconciliationCheckpointStore(self.path)
        self.shelf.replace_full(
            WeReadShelfSnapshot(books=(), album_count=0, has_mp=False),
            synced_at="shelf-v1",
        )

    def _run(self, *, state: str, catalog_limit: int = 5):
        subject_id = "5001"
        title = "测试书"
        isbn = "9780000005001"
        self.history.replace_full(
            [HistoryEntry(subject_id, title, state)],
            synced_at="history-v1",
        )
        weread = RecordingWeRead(title, isbn)
        result = run_reconciliation_batch(
            DOUBAN_TO_WEREAD,
            limit=1,
            shelf_provider=self.shelf,
            history_provider=self.history,
            checkpoint_provider=self.checkpoints,
            weread_provider=weread,
            douban_provider=ExactDouban(subject_id, title, isbn),
            weread_catalog_limit=catalog_limit,
        )
        return result, weread

    def test_active_reading_uses_wider_catalog_window(self) -> None:
        result, weread = self._run(state="do", catalog_limit=5)

        self.assertEqual(result.generation.policy_version, CURRENT_RECONCILIATION_POLICY_VERSION)
        self.assertEqual(result.processed[0].catalog_search_limit_used, 10)
        self.assertEqual(weread.search_counts, [10])

    def test_wish_keeps_configured_base_catalog_window(self) -> None:
        result, weread = self._run(state="wish", catalog_limit=5)

        self.assertEqual(result.processed[0].catalog_search_limit_used, 5)
        self.assertEqual(weread.search_counts, [5])

    def test_policy_v1_checkpoint_does_not_block_policy_v2_batch(self) -> None:
        subject_id = "5001"
        title = "测试书"
        isbn = "9780000005001"
        self.history.replace_full(
            [HistoryEntry(subject_id, title, "do")],
            synced_at="history-v1",
        )
        self.checkpoints.mark_completed(
            DOUBAN_TO_WEREAD,
            subject_id,
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            policy_version=1,
            outcome="not_found",
        )
        weread = RecordingWeRead(title, isbn)

        result = run_reconciliation_batch(
            DOUBAN_TO_WEREAD,
            limit=1,
            shelf_provider=self.shelf,
            history_provider=self.history,
            checkpoint_provider=self.checkpoints,
            weread_provider=weread,
            douban_provider=ExactDouban(subject_id, title, isbn),
            weread_catalog_limit=5,
        )

        self.assertEqual(result.already_completed, 0)
        self.assertEqual(len(result.processed), 1)
        self.assertEqual(weread.search_counts, [10])
        self.assertEqual(
            self.checkpoints.completed_ids(
                DOUBAN_TO_WEREAD,
                shelf_sync_at="shelf-v1",
                history_sync_at="history-v1",
                policy_version=CURRENT_RECONCILIATION_POLICY_VERSION,
            ),
            {subject_id},
        )


if __name__ == "__main__":
    unittest.main()
