from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from douban_weread.core.models import Edition
from douban_weread.providers.douban import DoubanProviderError
from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.providers.weread import (
    WeReadProgress,
    WeReadProviderError,
    WeReadSearchCandidate,
    WeReadShelfBook,
    WeReadShelfSnapshot,
)
from douban_weread.storage import (
    ReadingHistoryIndex,
    ReconciliationCheckpointStore,
    ReconciliationEvidenceStore,
    WeReadShelfIndex,
)
from douban_weread.weread_shelf_scan_cli import EXIT_OK, EXIT_PROVIDER_ERROR, run


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
        raise AssertionError("progress should not be called for Douban-to-WeRead scan")


class FailingWeRead(ExactWeRead):
    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        raise WeReadProviderError("temporary provider failure")


class BothDirectionWeRead(ExactWeRead):
    def get_book(self, book_id: str) -> Edition | None:
        if book_id == "7001":
            return Edition(
                title="微信独有",
                authors=["作者"],
                isbn="9780000007001",
                weread_id=book_id,
            )
        return super().get_book(book_id)

    def get_progress(self, book_id: str) -> WeReadProgress | None:
        if book_id == "7001":
            return WeReadProgress(book_id=book_id, progress=0, is_started=False)
        raise AssertionError("unexpected progress lookup")


class ExactDouban:
    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        if subject_id != "1001":
            return None
        return Edition(
            title="三体",
            authors=["作者"],
            isbn="9780000001001",
            douban_id=subject_id,
        )

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        raise AssertionError("title search should not be called for Douban-to-WeRead scan")


class FailOnWeReadToDouban(ExactDouban):
    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        raise DoubanProviderError("second-direction provider failure")


class WeReadShelfScanCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.shelf = WeReadShelfIndex(self.path)
        self.history = ReadingHistoryIndex(self.path)
        self.checkpoints = ReconciliationCheckpointStore(self.path)
        self.evidence = ReconciliationEvidenceStore(self.path)
        self.shelf.replace_full(
            WeReadShelfSnapshot(books=(), album_count=0, has_mp=False),
            synced_at="shelf-v1",
        )
        self.history.replace_full(
            [HistoryEntry("1001", "三体", "do")],
            synced_at="history-v1",
        )

    def _run(self, weread_factory, stdout: io.StringIO, stderr: io.StringIO) -> int:
        return run(
            ["--direction", "douban-to-weread", "--max-items", "4", "--batch-size", "2"],
            weread_client_factory=weread_factory,
            douban_client_factory=ExactDouban,
            shelf_factory=lambda: self.shelf,
            history_factory=lambda: self.history,
            checkpoint_factory=lambda: self.checkpoints,
            evidence_factory=lambda: self.evidence,
            stdout=stdout,
            stderr=stderr,
        )

    def test_scan_prints_visible_progress_and_final_local_coverage(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = self._run(ExactWeRead, stdout, stderr)

        self.assertEqual(code, EXIT_OK)
        output = stdout.getvalue()
        self.assertIn("Read-only reconciliation evidence scan", output)
        self.assertIn("Requested time budget: 30s", output)
        self.assertIn("Initial local coverage", output)
        self.assertIn("Douban → WeRead: verified 0/1; pending 1", output)
        self.assertIn("Batch 1: Douban → WeRead | processed 1 | cumulative 1", output)
        self.assertIn("Processed this scan: 1", output)
        self.assertIn("Stop reason: complete", output)
        self.assertIn("Elapsed:", output)
        self.assertIn("Douban → WeRead: verified 1/1; pending 0", output)
        self.assertIn("No remote mutation is performed", output)
        self.assertEqual(stderr.getvalue(), "")

    def test_provider_failure_stops_without_persisting_failed_item(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = self._run(FailingWeRead, stdout, stderr)

        self.assertEqual(code, EXIT_PROVIDER_ERROR)
        self.assertIn("WeRead provider error: temporary provider failure", stderr.getvalue())
        output = stdout.getvalue()
        self.assertIn("Scan stopped after 0 item(s)", output)
        self.assertIn("Persisted local coverage after stop", output)
        self.assertIn("Re-run the same scan command to resume", output)
        rows = self.evidence.list_generation(
            "douban-to-weread",
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            policy_version=3,
        )
        self.assertEqual(rows, [])

    def test_failure_after_completed_batch_keeps_evidence_and_reports_resume_coverage(self) -> None:
        self.shelf.replace_full(
            WeReadShelfSnapshot(
                books=(WeReadShelfBook(book_id="7001", title="微信独有", author="作者"),),
                album_count=0,
                has_mp=False,
            ),
            synced_at="shelf-v1",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["--direction", "both", "--max-items", "2", "--batch-size", "1"],
            weread_client_factory=BothDirectionWeRead,
            douban_client_factory=FailOnWeReadToDouban,
            shelf_factory=lambda: self.shelf,
            history_factory=lambda: self.history,
            checkpoint_factory=lambda: self.checkpoints,
            evidence_factory=lambda: self.evidence,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_PROVIDER_ERROR)
        self.assertIn("Douban provider error: second-direction provider failure", stderr.getvalue())
        output = stdout.getvalue()
        self.assertIn("Batch 1: Douban → WeRead | processed 1 | cumulative 1", output)
        self.assertIn("Scan stopped after 1 item(s)", output)
        self.assertIn("Douban → WeRead: verified 1/1; pending 0", output)
        self.assertIn("WeRead → Douban: verified 0/1; pending 1", output)
        rows = self.evidence.list_generation(
            "douban-to-weread",
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            policy_version=3,
        )
        self.assertEqual({row.item_id for row in rows}, {"1001"})


if __name__ == "__main__":
    unittest.main()
