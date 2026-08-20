from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from douban_weread.core.models import Edition
from douban_weread.providers.weread import WeReadProgress, WeReadShelfBook, WeReadShelfSnapshot
from douban_weread.storage import ReadingHistoryIndex, WeReadShelfIndex
from douban_weread.weread_shelf_cli import EXIT_NO_RESULTS, EXIT_OK, run


class FakeWeRead:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def get_book(self, book_id: str) -> Edition | None:
        self.calls.append(("book", book_id))
        return Edition(
            title="同一本书",
            authors=["作者"],
            isbn="9780000000001",
            weread_id=book_id,
        )

    def get_progress(self, book_id: str) -> WeReadProgress | None:
        self.calls.append(("progress", book_id))
        return WeReadProgress(book_id=book_id, progress=0, is_started=False)

    def sync_shelf(self) -> WeReadShelfSnapshot:
        raise AssertionError("sync should not be called")


class FakeDouban:
    def __init__(self) -> None:
        self.calls = 0

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        self.calls += 1
        return [
            Edition(
                title=title,
                authors=["作者"],
                isbn="9780000000001",
                douban_id="100",
            )
        ]

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        raise AssertionError(f"unexpected history fetch: {subject_id}")


class WeReadShelfVerifyCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.shelf = WeReadShelfIndex(self.path)
        self.history = ReadingHistoryIndex(self.path)
        self.history.replace_full([])

    def test_verify_prints_bounded_exact_match_and_state_suggestion(self) -> None:
        self.shelf.replace_full(
            WeReadShelfSnapshot(
                books=(WeReadShelfBook(book_id="10", title="同一本书", author="作者"),),
            )
        )
        weread = FakeWeRead()
        douban = FakeDouban()
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["verify", "--id", "10"],
            client_factory=lambda: weread,
            douban_verification_factory=lambda: douban,
            index_factory=lambda: self.shelf,
            history_index_factory=lambda: self.history,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_OK)
        output = stdout.getvalue()
        self.assertIn("Lazy shelf verification", output)
        self.assertIn("Progress: 0%", output)
        self.assertIn("Verified WeRead state: unread", output)
        self.assertIn("Match: exact_edition", output)
        self.assertIn("Action: suggest_wish", output)
        self.assertIn("Suggested Douban state: wish", output)
        self.assertIn("Safe to auto apply: False", output)
        self.assertIn("No mutation is performed", output)
        self.assertEqual(weread.calls, [("book", "10"), ("progress", "10")])
        self.assertEqual(douban.calls, 1)
        self.assertEqual(stderr.getvalue(), "")

    def test_verify_missing_local_shelf_book_stops_before_network(self) -> None:
        self.shelf.replace_full(WeReadShelfSnapshot(books=()))

        class NoNetworkWeRead(FakeWeRead):
            def get_book(self, book_id: str) -> Edition | None:
                raise AssertionError("network should not be called")

        class NoNetworkDouban(FakeDouban):
            def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
                raise AssertionError("network should not be called")

        stderr = io.StringIO()
        code = run(
            ["verify", "--id", "10"],
            client_factory=NoNetworkWeRead,
            douban_verification_factory=NoNetworkDouban,
            index_factory=lambda: self.shelf,
            history_index_factory=lambda: self.history,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_NO_RESULTS)
        self.assertIn("is not present in the complete local shelf baseline", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
