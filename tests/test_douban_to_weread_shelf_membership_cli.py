from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from douban_weread.core.models import Edition
from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.providers.weread import WeReadSearchCandidate, WeReadShelfBook, WeReadShelfSnapshot
from douban_weread.storage import (
    ReadingHistoryIndex,
    ReconciliationCheckpointStore,
    ReconciliationEvidenceStore,
    WeReadShelfIndex,
)
from douban_weread.weread_shelf_batch_cli import EXIT_OK, run


class ExactDouban:
    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        return Edition(
            title="待读书",
            authors=["作者"],
            isbn="9780000005001",
            douban_id=subject_id,
        )

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        raise AssertionError("title search should not be called in Douban-to-WeRead batch")


class ExactWeRead:
    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        return [
            WeReadSearchCandidate(
                book_id="9001",
                title=keyword,
                author="作者",
                soldout=False,
            )
        ]

    def get_book(self, book_id: str) -> Edition | None:
        return Edition(
            title="待读书",
            authors=["作者"],
            isbn="9780000005001",
            weread_id=book_id,
        )

    def get_progress(self, book_id: str):
        raise AssertionError("progress should not be called in Douban-to-WeRead batch")


class DoubanToWeReadShelfMembershipCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.shelf = WeReadShelfIndex(self.path)
        self.history = ReadingHistoryIndex(self.path)
        self.checkpoints = ReconciliationCheckpointStore(self.path)
        self.history.replace_full(
            [HistoryEntry("5001", "待读书", "wish")],
            synced_at="history-v1",
        )

    def _run(self) -> str:
        stdout = io.StringIO()
        code = run(
            ["--direction", "douban-to-weread", "--limit", "1"],
            weread_client_factory=ExactWeRead,
            douban_client_factory=ExactDouban,
            shelf_index_factory=lambda: self.shelf,
            history_index_factory=lambda: self.history,
            checkpoint_factory=lambda: self.checkpoints,
            stdout=stdout,
            stderr=io.StringIO(),
        )
        self.assertEqual(code, EXIT_OK)
        return stdout.getvalue()

    def test_prints_no_when_resolved_catalog_book_is_not_on_current_shelf(self) -> None:
        self.shelf.replace_full(
            WeReadShelfSnapshot(books=(), album_count=0, has_mp=False),
            synced_at="shelf-v1",
        )
        output = self._run()
        self.assertIn("WeRead catalog status: available_exact", output)
        self.assertIn("Selected WeRead bookId: 9001", output)
        self.assertIn("Current shelf membership: no", output)
        self.assertIn("User plan: add_to_weread_shelf_exact", output)
        self.assertIn("User action required: yes", output)

        evidence = ReconciliationEvidenceStore(self.path).list_generation(
            "douban-to-weread",
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            policy_version=3,
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].item_id, "5001")
        self.assertEqual(evidence[0].user_plan, "add_to_weread_shelf_exact")
        self.assertEqual(evidence[0].selected_weread_book_id, "9001")
        self.assertEqual(evidence[0].shelf_membership, "no")
        self.assertTrue(evidence[0].exact_edition)

    def test_prints_yes_and_actual_shelf_title_when_book_id_is_already_present(self) -> None:
        self.shelf.replace_full(
            WeReadShelfSnapshot(
                books=(
                    WeReadShelfBook(
                        book_id="9001",
                        title="待读书（微信版标题）",
                        author="作者",
                    ),
                ),
                album_count=0,
                has_mp=False,
            ),
            synced_at="shelf-v1",
        )
        output = self._run()
        self.assertIn("WeRead catalog status: available_exact", output)
        self.assertIn("Selected WeRead bookId: 9001", output)
        self.assertIn("Current shelf membership: yes", output)
        self.assertIn("Current shelf title: 待读书（微信版标题）", output)
        self.assertIn("User plan: aligned", output)
        self.assertIn("User action required: no", output)

        evidence = ReconciliationEvidenceStore(self.path).list_generation(
            "douban-to-weread",
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            policy_version=3,
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].user_plan, "aligned")
        self.assertEqual(evidence[0].shelf_membership, "yes")

    def test_checkpoint_without_evidence_is_reverified_once(self) -> None:
        self.shelf.replace_full(
            WeReadShelfSnapshot(books=(), album_count=0, has_mp=False),
            synced_at="shelf-v1",
        )
        self.checkpoints.mark_completed(
            "douban-to-weread",
            "5001",
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            policy_version=3,
            outcome="available_exact",
        )

        output = self._run()

        self.assertIn("Already checkpointed in this generation: 0", output)
        self.assertIn("Processed this batch: 1", output)
        evidence = ReconciliationEvidenceStore(self.path).list_generation(
            "douban-to-weread",
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            policy_version=3,
        )
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].item_id, "5001")
        self.assertEqual(evidence[0].user_plan, "add_to_weread_shelf_exact")


if __name__ == "__main__":
    unittest.main()
