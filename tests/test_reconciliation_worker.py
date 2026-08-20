from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from douban_weread.core.models import Edition
from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.providers.weread import WeReadProviderError, WeReadSearchCandidate, WeReadShelfSnapshot
from douban_weread.reconciliation import (
    ReconciliationWorkerStatus,
    get_reconciliation_worker_status,
    run_reconciliation_worker_tick,
)
from douban_weread.storage import (
    ReadingHistoryIndex,
    ReconciliationCheckpointStore,
    ReconciliationEvidence,
    ReconciliationEvidenceStore,
    ReconciliationWorkerStateStore,
    WeReadShelfIndex,
)


class WorkerWeRead:
    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        mapping = {
            "第一本": ("9001", "9780000001001"),
            "第二本": ("9002", "9780000001002"),
        }
        book_id, _ = mapping[keyword]
        return [WeReadSearchCandidate(book_id=book_id, title=keyword, author="作者", soldout=False)]

    def get_book(self, book_id: str) -> Edition | None:
        mapping = {
            "9001": ("第一本", "9780000001001"),
            "9002": ("第二本", "9780000001002"),
        }
        title, isbn = mapping[book_id]
        return Edition(title=title, authors=["作者"], isbn=isbn, weread_id=book_id)

    def get_progress(self, book_id: str):
        raise AssertionError("progress is not used for Douban-to-WeRead worker tests")


class FailingWorkerWeRead(WorkerWeRead):
    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        raise WeReadProviderError("temporary failure")


class WorkerDouban:
    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        mapping = {
            "1001": ("第一本", "9780000001001"),
            "1002": ("第二本", "9780000001002"),
        }
        if subject_id not in mapping:
            return None
        title, isbn = mapping[subject_id]
        return Edition(title=title, authors=["作者"], isbn=isbn, douban_id=subject_id)

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        return []


class ReconciliationWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.shelf = WeReadShelfIndex(self.path)
        self.history = ReadingHistoryIndex(self.path)
        self.checkpoints = ReconciliationCheckpointStore(self.path)
        self.evidence = ReconciliationEvidenceStore(self.path)
        self.state = ReconciliationWorkerStateStore(self.path)
        self.shelf.replace_full(
            WeReadShelfSnapshot(books=(), album_count=0, has_mp=False),
            synced_at="shelf-v1",
        )
        self.history.replace_full(
            [
                HistoryEntry("1001", "第一本", "do"),
                HistoryEntry("1002", "第二本", "do"),
            ],
            synced_at="history-v1",
        )

    def _status(self):
        return get_reconciliation_worker_status(
            shelf_provider=self.shelf,
            history_provider=self.history,
            evidence_provider=self.evidence,
            state_provider=self.state,
        )

    def _tick(self, weread, *, max_items: int = 1):
        return run_reconciliation_worker_tick(
            shelf_provider=self.shelf,
            history_provider=self.history,
            checkpoint_provider=self.checkpoints,
            evidence_provider=self.evidence,
            state_provider=self.state,
            weread_provider=weread,
            douban_provider=WorkerDouban(),
            max_items=max_items,
            batch_size=1,
            max_seconds=30,
        )

    def test_existing_manual_evidence_bootstraps_partial_status_without_worker_row(self) -> None:
        self.evidence.upsert(
            ReconciliationEvidence(
                direction="douban-to-weread",
                item_id="1001",
                shelf_sync_at="shelf-v1",
                history_sync_at="history-v1",
                policy_version=3,
                title="第一本",
                source_state="do",
                outcome="available_exact",
                user_plan="add_to_weread_shelf_exact",
                summary="available",
                requires_user_action=True,
                selected_douban_subject="1001",
                selected_weread_book_id="9001",
                shelf_membership="no",
            )
        )

        view = self._status()

        self.assertEqual(view.status, ReconciliationWorkerStatus.PARTIAL)
        self.assertEqual(view.tick_count, 0)
        self.assertEqual(view.coverage.douban_to_weread_verified, 1)
        self.assertEqual(view.coverage.douban_to_weread_pending, 1)

    def test_two_ticks_resume_from_evidence_and_reach_complete(self) -> None:
        first = self._tick(WorkerWeRead(), max_items=1)
        second = self._tick(WorkerWeRead(), max_items=1)

        self.assertEqual(first.view.status, ReconciliationWorkerStatus.PARTIAL)
        self.assertEqual(first.processed_this_tick, 1)
        self.assertEqual(first.view.tick_count, 1)
        self.assertEqual(second.view.status, ReconciliationWorkerStatus.COMPLETE)
        self.assertEqual(second.processed_this_tick, 1)
        self.assertEqual(second.view.tick_count, 2)
        self.assertEqual(second.view.coverage.pending_total, 0)

    def test_provider_failure_persists_paused_state_without_failed_evidence(self) -> None:
        result = self._tick(FailingWorkerWeRead(), max_items=1)

        self.assertEqual(result.view.status, ReconciliationWorkerStatus.PAUSED_PROVIDER)
        self.assertEqual(result.error_kind, "weread_provider")
        self.assertEqual(result.processed_this_tick, 0)
        self.assertEqual(result.view.tick_count, 1)
        self.assertEqual(result.view.coverage.douban_to_weread_verified, 0)
        self.assertEqual(result.view.coverage.douban_to_weread_pending, 2)

        rows = self.evidence.list_generation(
            "douban-to-weread",
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            policy_version=3,
        )
        self.assertEqual(rows, [])

    def test_status_reads_persisted_paused_state_locally(self) -> None:
        self._tick(FailingWorkerWeRead(), max_items=1)

        view = self._status()

        self.assertEqual(view.status, ReconciliationWorkerStatus.PAUSED_PROVIDER)
        self.assertEqual(view.last_error_kind, "weread_provider")
        self.assertEqual(view.last_stop_reason, "provider_failure")
        self.assertEqual(view.tick_count, 1)


if __name__ == "__main__":
    unittest.main()
