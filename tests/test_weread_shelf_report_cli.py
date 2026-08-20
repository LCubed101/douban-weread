from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.providers.weread import WeReadShelfBook, WeReadShelfSnapshot
from douban_weread.storage import (
    ReadingHistoryIndex,
    ReconciliationEvidence,
    ReconciliationEvidenceStore,
    WeReadShelfIndex,
)
from douban_weread.weread_shelf_report_cli import EXIT_NO_RESULTS, EXIT_OK, run


class WeReadShelfReportCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.shelf = WeReadShelfIndex(self.path)
        self.history = ReadingHistoryIndex(self.path)
        self.evidence = ReconciliationEvidenceStore(self.path)

    def test_report_prints_partial_coverage_and_plan_counts_locally(self) -> None:
        self.shelf.replace_full(
            WeReadShelfSnapshot(
                books=(WeReadShelfBook(book_id="w1", title="微信独有", author="作者甲"),),
                album_count=0,
                has_mp=False,
            ),
            synced_at="shelf-v1",
        )
        self.history.replace_full(
            [
                HistoryEntry("1001", "三体", "do"),
                HistoryEntry("1002", "另一想读", "wish"),
            ],
            synced_at="history-v1",
        )
        self.evidence.upsert(
            ReconciliationEvidence(
                direction="douban-to-weread",
                item_id="1001",
                shelf_sync_at="shelf-v1",
                history_sync_at="history-v1",
                policy_version=3,
                title="三体",
                source_state="do",
                outcome="available_alternative",
                user_plan="review_edition",
                summary="review edition",
                requires_user_action=True,
                selected_douban_subject="1001",
                selected_weread_book_id="178677",
                selected_edition_title="三体1",
                match_kind="alternative_edition",
                requires_confirmation=True,
                shelf_membership="no",
            )
        )

        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run(
            ["--direction", "both", "--limit", "3"],
            shelf_factory=lambda: self.shelf,
            history_factory=lambda: self.history,
            evidence_factory=lambda: self.evidence,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_OK)
        output = stdout.getvalue()
        self.assertIn("Local reconciliation evidence report", output)
        self.assertIn("Coverage: only persisted verified evidence is classified", output)
        self.assertIn("WeRead → Douban", output)
        self.assertIn("Candidate queue: 1", output)
        self.assertIn("Verified evidence: 0", output)
        self.assertIn("Douban → WeRead", output)
        self.assertIn("Reconciliation policy: v3", output)
        self.assertIn("Verified evidence: 1", output)
        self.assertIn("Pending verification: 1", output)
        self.assertIn("review_edition: 1", output)
        self.assertIn("WeRead bookId: 178677", output)
        self.assertIn("Local-only report: no provider API is called", output)
        self.assertEqual(stderr.getvalue(), "")

    def test_report_requires_complete_baselines(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run(
            [],
            shelf_factory=lambda: self.shelf,
            history_factory=lambda: self.history,
            evidence_factory=lambda: self.evidence,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_NO_RESULTS)
        self.assertIn("Both complete baselines are required", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
