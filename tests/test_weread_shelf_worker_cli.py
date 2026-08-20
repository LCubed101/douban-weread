from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from douban_weread.core.models import Edition
from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.providers.weread import WeReadProviderError, WeReadSearchCandidate, WeReadShelfSnapshot
from douban_weread.storage import (
    ReadingHistoryIndex,
    ReconciliationCheckpointStore,
    ReconciliationEvidenceStore,
    ReconciliationWorkerStateStore,
    WeReadShelfIndex,
)
from douban_weread.weread_shelf_worker_cli import EXIT_OK, EXIT_PROVIDER_ERROR, run


class ExactWeRead:
    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        return [WeReadSearchCandidate(book_id="9001", title=keyword, author="作者", soldout=False)]

    def get_book(self, book_id: str) -> Edition | None:
        return Edition(
            title="三体",
            authors=["作者"],
            isbn="9780000001001",
            weread_id=book_id,
        )

    def get_progress(self, book_id: str):
        raise AssertionError("progress is not used in this test")


class FailingWeRead(ExactWeRead):
    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        raise WeReadProviderError("temporary failure")


class ExactDouban:
    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        return Edition(
            title="三体",
            authors=["作者"],
            isbn="9780000001001",
            douban_id=subject_id,
        )

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        return []


class WeReadShelfWorkerCliTests(unittest.TestCase):
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
            [HistoryEntry("1001", "三体", "do")],
            synced_at="history-v1",
        )

    def _kwargs(self, weread_factory):
        return dict(
            weread_client_factory=weread_factory,
            douban_client_factory=ExactDouban,
            shelf_factory=lambda: self.shelf,
            history_factory=lambda: self.history,
            checkpoint_factory=lambda: self.checkpoints,
            evidence_factory=lambda: self.evidence,
            state_factory=lambda: self.state,
        )

    def test_status_is_local_only_and_bootstraps_not_started(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        def must_not_build_provider():
            raise AssertionError("status must not construct a provider client")

        code = run(
            ["status"],
            **self._kwargs(must_not_build_provider),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_OK)
        output = stdout.getvalue()
        self.assertIn("Local reconciliation worker status", output)
        self.assertIn("State: not_started", output)
        self.assertIn("Total pending: 1", output)
        self.assertIn("no provider API is called", output)
        self.assertEqual(stderr.getvalue(), "")

    def test_tick_advances_and_persists_complete_state(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["tick", "--max-items", "1", "--batch-size", "1"],
            **self._kwargs(ExactWeRead),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_OK)
        output = stdout.getvalue()
        self.assertIn("Reconciliation worker tick", output)
        self.assertIn("Processed this tick: 1", output)
        self.assertIn("State: complete", output)
        self.assertIn("Total pending: 0", output)
        self.assertIn("No remote mutation is performed", output)
        self.assertEqual(stderr.getvalue(), "")

    def test_provider_failure_returns_paused_state_and_resumable_message(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["tick", "--max-items", "1", "--batch-size", "1"],
            **self._kwargs(FailingWeRead),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_PROVIDER_ERROR)
        self.assertIn("State: paused_provider", stdout.getvalue())
        self.assertIn("error kind: weread_provider", stderr.getvalue())
        self.assertIn("failed item was not checkpointed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
