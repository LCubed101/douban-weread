from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from douban_weread.core.models import Edition
from douban_weread.providers.weread import WeReadProgress, WeReadSearchCandidate, WeReadShelfBook, WeReadShelfSnapshot
from douban_weread.storage import ReadingHistoryIndex, ReconciliationCheckpointStore, WeReadShelfIndex
from douban_weread.weread_shelf_batch_cli import EXIT_OK, run


class FakeWeRead:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def get_book(self, book_id: str) -> Edition | None:
        self.calls.append(("book", book_id))
        return Edition(
            title="待同步书",
            authors=["作者"],
            isbn="9780000000001",
            weread_id=book_id,
        )

    def get_progress(self, book_id: str) -> WeReadProgress | None:
        self.calls.append(("progress", book_id))
        return WeReadProgress(book_id=book_id, progress=0, is_started=False)

    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        raise AssertionError("search should not be called")


class FakeDouban:
    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        return [
            Edition(
                title=title,
                authors=["作者"],
                isbn="9780000000001",
                douban_id="1001",
            )
        ]

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        raise AssertionError("subject lookup should not be called")


class WeReadShelfBatchCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.shelf = WeReadShelfIndex(self.path)
        self.history = ReadingHistoryIndex(self.path)
        self.checkpoints = ReconciliationCheckpointStore(self.path)
        self.shelf.replace_full(
            WeReadShelfSnapshot(
                books=(WeReadShelfBook(book_id="10", title="待同步书", author="作者"),),
                album_count=0,
                has_mp=False,
            ),
            synced_at="shelf-v1",
        )
        self.history.replace_full([], synced_at="history-v1")

    def test_weread_to_douban_batch_prints_suggestion_and_checkpoint(self) -> None:
        weread = FakeWeRead()
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["--direction", "weread-to-douban", "--limit", "1"],
            weread_client_factory=lambda: weread,
            douban_client_factory=FakeDouban,
            shelf_index_factory=lambda: self.shelf,
            history_index_factory=lambda: self.history,
            checkpoint_factory=lambda: self.checkpoints,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_OK)
        output = stdout.getvalue()
        self.assertIn("Read-only reconciliation batch", output)
        self.assertIn("Direction: weread-to-douban", output)
        self.assertIn("Outcome: suggest_wish", output)
        self.assertIn("Suggested Douban state: wish", output)
        self.assertIn("Checkpointed for this baseline: yes", output)
        self.assertIn("Remaining pending for this generation: 0", output)
        self.assertEqual(weread.calls, [("book", "10"), ("progress", "10")])
        self.assertEqual(stderr.getvalue(), "")

    def test_second_run_same_generation_skips_network(self) -> None:
        first_weread = FakeWeRead()
        first_code = run(
            ["--direction", "weread-to-douban", "--limit", "1"],
            weread_client_factory=lambda: first_weread,
            douban_client_factory=FakeDouban,
            shelf_index_factory=lambda: self.shelf,
            history_index_factory=lambda: self.history,
            checkpoint_factory=lambda: self.checkpoints,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        self.assertEqual(first_code, EXIT_OK)

        class NoNetworkWeRead(FakeWeRead):
            def get_book(self, book_id: str) -> Edition | None:
                raise AssertionError("checkpointed item should not be fetched again")

        stdout = io.StringIO()
        code = run(
            ["--direction", "weread-to-douban", "--limit", "1"],
            weread_client_factory=NoNetworkWeRead,
            douban_client_factory=FakeDouban,
            shelf_index_factory=lambda: self.shelf,
            history_index_factory=lambda: self.history,
            checkpoint_factory=lambda: self.checkpoints,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        output = stdout.getvalue()
        self.assertIn("Already checkpointed in this generation: 1", output)
        self.assertIn("No pending items were processed", output)


if __name__ == "__main__":
    unittest.main()
