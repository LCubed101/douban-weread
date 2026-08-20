from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from douban_weread.core.models import Edition
from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.providers.weread import WeReadProgress, WeReadSearchCandidate, WeReadShelfBook, WeReadShelfSnapshot
from douban_weread.reconciliation import DOUBAN_TO_WEREAD, WEREAD_TO_DOUBAN, run_reconciliation_evidence_scan
from douban_weread.storage import (
    ReadingHistoryIndex,
    ReconciliationCheckpointStore,
    ReconciliationEvidenceStore,
    WeReadShelfIndex,
)


class FakeWeRead:
    def __init__(self) -> None:
        self.search_calls: list[str] = []
        self.book_calls: list[str] = []
        self.progress_calls: list[str] = []

    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        self.search_calls.append(keyword)
        mapping = {
            "豆瓣在读一": ("9001", "9780000001001"),
            "豆瓣在读二": ("9002", "9780000001002"),
        }
        book_id, _ = mapping[keyword]
        return [WeReadSearchCandidate(book_id=book_id, title=keyword, author="作者", soldout=False)]

    def get_book(self, book_id: str) -> Edition | None:
        self.book_calls.append(book_id)
        mapping = {
            "9001": ("豆瓣在读一", "9780000001001"),
            "9002": ("豆瓣在读二", "9780000001002"),
            "7001": ("微信独有一", "9780000007001"),
            "7002": ("微信独有二", "9780000007002"),
        }
        title, isbn = mapping[book_id]
        return Edition(title=title, authors=["作者"], isbn=isbn, weread_id=book_id)

    def get_progress(self, book_id: str) -> WeReadProgress | None:
        self.progress_calls.append(book_id)
        return WeReadProgress(book_id=book_id, progress=0, is_started=False)


class FakeDouban:
    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        mapping = {
            "1001": ("豆瓣在读一", "9780000001001"),
            "1002": ("豆瓣在读二", "9780000001002"),
        }
        if subject_id not in mapping:
            return None
        title, isbn = mapping[subject_id]
        return Edition(title=title, authors=["作者"], isbn=isbn, douban_id=subject_id)

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        mapping = {
            "微信独有一": ("2001", "9780000007001"),
            "微信独有二": ("2002", "9780000007002"),
        }
        subject_id, isbn = mapping[title]
        return [Edition(title=title, authors=["作者"], isbn=isbn, douban_id=subject_id)]


class ReconciliationEvidenceScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.shelf = WeReadShelfIndex(self.path)
        self.history = ReadingHistoryIndex(self.path)
        self.checkpoints = ReconciliationCheckpointStore(self.path)
        self.evidence = ReconciliationEvidenceStore(self.path)
        self.weread = FakeWeRead()
        self.douban = FakeDouban()

        self.shelf.replace_full(
            WeReadShelfSnapshot(
                books=(
                    WeReadShelfBook(book_id="7001", title="微信独有一", author="作者"),
                    WeReadShelfBook(book_id="7002", title="微信独有二", author="作者"),
                ),
                album_count=0,
                has_mp=False,
            ),
            synced_at="shelf-v1",
        )
        self.history.replace_full(
            [
                HistoryEntry("1001", "豆瓣在读一", "do"),
                HistoryEntry("1002", "豆瓣在读二", "do"),
            ],
            synced_at="history-v1",
        )

    def _run(self, *, max_items: int, batch_size: int):
        return run_reconciliation_evidence_scan(
            directions="both",
            max_items=max_items,
            batch_size=batch_size,
            shelf_provider=self.shelf,
            history_provider=self.history,
            checkpoint_provider=self.checkpoints,
            evidence_provider=self.evidence,
            weread_provider=self.weread,
            douban_provider=self.douban,
        )

    def test_both_directions_are_processed_round_robin(self) -> None:
        result = self._run(max_items=2, batch_size=1)

        self.assertEqual(result.processed_total, 2)
        self.assertEqual(
            [step.direction for step in result.steps],
            [DOUBAN_TO_WEREAD, WEREAD_TO_DOUBAN],
        )
        self.assertEqual([step.cumulative_processed for step in result.steps], [1, 2])
        self.assertEqual(result.stop_reason, "max_items")

    def test_second_scan_resumes_from_persisted_evidence_and_checkpoints(self) -> None:
        first = self._run(max_items=2, batch_size=1)
        second = self._run(max_items=2, batch_size=1)

        self.assertEqual(first.processed_total, 2)
        self.assertEqual(second.processed_total, 2)
        d2w = self.evidence.list_generation(
            DOUBAN_TO_WEREAD,
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            policy_version=3,
        )
        w2d = self.evidence.list_generation(
            WEREAD_TO_DOUBAN,
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            policy_version=2,
        )
        self.assertEqual({row.item_id for row in d2w}, {"1001", "1002"})
        self.assertEqual({row.item_id for row in w2d}, {"7001", "7002"})

    def test_scan_limits_are_hard_clamped(self) -> None:
        result = self._run(max_items=100, batch_size=100)

        self.assertEqual(result.requested_max_items, 100)
        self.assertEqual(result.effective_max_items, 20)
        self.assertEqual(result.requested_batch_size, 100)
        self.assertEqual(result.effective_batch_size, 5)
        self.assertEqual(result.processed_total, 4)
        self.assertEqual(result.stop_reason, "complete")


if __name__ == "__main__":
    unittest.main()
