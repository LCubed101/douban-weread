from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from douban_weread.core.models import Edition
from douban_weread.providers.douban import DoubanProviderError
from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.providers.weread import WeReadProviderError, WeReadSearchCandidate, WeReadShelfSnapshot
from douban_weread.reconciliation.onboarding import (
    FirstLoginReconciliationPhase,
    get_first_login_reconciliation_view,
    run_first_login_reconciliation_tick,
)
from douban_weread.storage import (
    ReadingHistoryIndex,
    ReconciliationCheckpointStore,
    ReconciliationEvidenceStore,
    ReconciliationWorkerStateStore,
    WeReadShelfIndex,
)


class HistoryBaselineClient:
    def __init__(self) -> None:
        self.calls = 0

    def fetch_all(self) -> list[HistoryEntry]:
        self.calls += 1
        return [HistoryEntry("1001", "第一本", "do")]


class FailingHistoryBaselineClient(HistoryBaselineClient):
    def fetch_all(self) -> list[HistoryEntry]:
        self.calls += 1
        raise DoubanProviderError("history unavailable")


class ShelfAndCatalogClient:
    def __init__(self) -> None:
        self.shelf_calls = 0
        self.search_calls = 0

    def sync_shelf(self) -> WeReadShelfSnapshot:
        self.shelf_calls += 1
        return WeReadShelfSnapshot(books=(), album_count=0, has_mp=False)

    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        self.search_calls += 1
        return [WeReadSearchCandidate(book_id="9001", title=keyword, author="作者", soldout=False)]

    def get_book(self, book_id: str) -> Edition | None:
        return Edition(
            title="第一本",
            authors=["作者"],
            isbn="9780000001001",
            weread_id=book_id,
        )

    def get_progress(self, book_id: str):
        raise AssertionError("progress is not needed for the Douban-to-WeRead onboarding case")


class FailingShelfClient(ShelfAndCatalogClient):
    def sync_shelf(self) -> WeReadShelfSnapshot:
        self.shelf_calls += 1
        raise WeReadProviderError("shelf unavailable")


class FailingCatalogClient(ShelfAndCatalogClient):
    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        self.search_calls += 1
        raise WeReadProviderError("catalog unavailable")


class DoubanCatalogClient:
    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        if subject_id != "1001":
            return None
        return Edition(
            title="第一本",
            authors=["作者"],
            isbn="9780000001001",
            douban_id=subject_id,
        )

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        return []


class FirstLoginReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.shelf = WeReadShelfIndex(self.path)
        self.history = ReadingHistoryIndex(self.path)
        self.checkpoints = ReconciliationCheckpointStore(self.path)
        self.evidence = ReconciliationEvidenceStore(self.path)
        self.state = ReconciliationWorkerStateStore(self.path)

    def _view(self):
        return get_first_login_reconciliation_view(
            shelf_provider=self.shelf,
            history_provider=self.history,
            evidence_provider=self.evidence,
            state_provider=self.state,
        )

    def _tick(self, *, shelf_client, history_client, weread_provider=None):
        return run_first_login_reconciliation_tick(
            shelf_provider=self.shelf,
            history_provider=self.history,
            checkpoint_provider=self.checkpoints,
            evidence_provider=self.evidence,
            state_provider=self.state,
            weread_provider=weread_provider or shelf_client,
            douban_provider=DoubanCatalogClient(),
            weread_shelf_client=shelf_client,
            douban_history_client=history_client,
            max_items=1,
            batch_size=1,
            max_seconds=30,
        )

    def test_local_view_reports_both_missing_baselines_before_any_provider_exists(self) -> None:
        view = self._view()

        self.assertEqual(view.phase, FirstLoginReconciliationPhase.NEEDS_BASELINES)
        self.assertEqual(view.missing_baselines, ("douban", "weread"))
        self.assertFalse(view.ready_for_reconciliation)
        self.assertIsNone(view.worker)

    def test_first_tick_syncs_missing_baselines_then_runs_bounded_worker(self) -> None:
        history_client = HistoryBaselineClient()
        weread = ShelfAndCatalogClient()

        result = self._tick(shelf_client=weread, history_client=history_client)

        self.assertEqual(result.baselines_synced, ("douban", "weread"))
        self.assertEqual(history_client.calls, 1)
        self.assertEqual(weread.shelf_calls, 1)
        self.assertEqual(weread.search_calls, 1)
        self.assertTrue(result.view.ready_for_reconciliation)
        self.assertEqual(result.view.missing_baselines, ())
        self.assertEqual(result.view.phase, FirstLoginReconciliationPhase.COMPLETE)
        self.assertIsNotNone(result.worker_tick)
        self.assertEqual(result.worker_tick.processed_this_tick, 1)

    def test_existing_complete_douban_baseline_is_not_refetched_when_only_shelf_is_missing(self) -> None:
        self.history.replace_full(
            [HistoryEntry("1001", "第一本", "do")],
            synced_at="history-v1",
        )
        history_client = HistoryBaselineClient()
        weread = ShelfAndCatalogClient()

        result = self._tick(shelf_client=weread, history_client=history_client)

        self.assertEqual(result.baselines_synced, ("weread",))
        self.assertEqual(history_client.calls, 0)
        self.assertEqual(weread.shelf_calls, 1)

    def test_successful_history_baseline_survives_shelf_provider_failure_and_retry_only_fills_missing_side(self) -> None:
        history_client = HistoryBaselineClient()
        failing_shelf = FailingShelfClient()

        first = self._tick(shelf_client=failing_shelf, history_client=history_client)

        self.assertEqual(first.view.phase, FirstLoginReconciliationPhase.PAUSED_PROVIDER)
        self.assertEqual(first.view.last_error_kind, "weread_baseline")
        self.assertEqual(first.baselines_synced, ("douban",))
        self.assertEqual(first.view.missing_baselines, ("weread",))
        self.assertTrue(self.history.status().complete)
        self.assertFalse(self.shelf.status().complete)
        self.assertIsNone(first.worker_tick)

        working_shelf = ShelfAndCatalogClient()
        retry = self._tick(
            shelf_client=working_shelf,
            history_client=None,
        )

        self.assertEqual(retry.baselines_synced, ("weread",))
        self.assertEqual(working_shelf.shelf_calls, 1)
        self.assertEqual(retry.view.phase, FirstLoginReconciliationPhase.COMPLETE)

    def test_history_provider_failure_does_not_create_an_empty_baseline(self) -> None:
        history_client = FailingHistoryBaselineClient()
        weread = ShelfAndCatalogClient()

        result = self._tick(shelf_client=weread, history_client=history_client)

        self.assertEqual(result.view.phase, FirstLoginReconciliationPhase.PAUSED_PROVIDER)
        self.assertEqual(result.view.last_error_kind, "douban_baseline")
        self.assertEqual(result.baselines_synced, ())
        self.assertFalse(self.history.status().complete)
        self.assertFalse(self.shelf.status().complete)
        self.assertEqual(weread.shelf_calls, 0)
        self.assertIsNone(result.worker_tick)

    def test_worker_provider_pause_is_exposed_as_product_phase_after_baselines_are_complete(self) -> None:
        self.history.replace_full(
            [HistoryEntry("1001", "第一本", "do")],
            synced_at="history-v1",
        )
        self.shelf.replace_full(
            WeReadShelfSnapshot(books=(), album_count=0, has_mp=False),
            synced_at="shelf-v1",
        )
        weread = FailingCatalogClient()

        result = self._tick(
            shelf_client=weread,
            history_client=None,
            weread_provider=weread,
        )

        self.assertEqual(result.baselines_synced, ())
        self.assertEqual(result.view.phase, FirstLoginReconciliationPhase.PAUSED_PROVIDER)
        self.assertEqual(result.view.last_error_kind, "weread_provider")
        self.assertIsNotNone(result.worker_tick)
        self.assertEqual(result.worker_tick.processed_this_tick, 0)
        self.assertEqual(result.view.worker.tick_count, 1)


if __name__ == "__main__":
    unittest.main()
