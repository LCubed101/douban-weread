from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from douban_weread.core.models import Edition
from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.providers.weread import (
    WeReadProgress,
    WeReadSearchCandidate,
    WeReadShelfBook,
    WeReadShelfSnapshot,
)
from douban_weread.reconciliation import (
    DOUBAN_TO_WEREAD,
    WEREAD_TO_DOUBAN,
    run_reconciliation_batch,
)
from douban_weread.storage import (
    ReadingHistoryIndex,
    ReconciliationCheckpointStore,
    WeReadShelfIndex,
)


class WeReadToDoubanFakeWeRead:
    def __init__(self, books: dict[str, tuple[str, str]]) -> None:
        self.books = books
        self.book_calls: list[str] = []
        self.progress_calls: list[str] = []

    def get_book(self, book_id: str) -> Edition | None:
        self.book_calls.append(book_id)
        title, isbn = self.books[book_id]
        return Edition(title=title, authors=["作者"], isbn=isbn, weread_id=book_id)

    def get_progress(self, book_id: str) -> WeReadProgress | None:
        self.progress_calls.append(book_id)
        return WeReadProgress(book_id=book_id, progress=0, is_started=False)

    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        raise AssertionError("catalog search is not used in WeRead-to-Douban batch")


class ExactDoubanSearch:
    def __init__(self, by_title: dict[str, tuple[str, str]]) -> None:
        self.by_title = by_title
        self.search_calls: list[str] = []
        self.subject_calls: list[str] = []

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        self.search_calls.append(title)
        subject_id, isbn = self.by_title[title]
        return [Edition(title=title, authors=["作者"], isbn=isbn, douban_id=subject_id)]

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        self.subject_calls.append(subject_id)
        for title, (candidate_subject, isbn) in self.by_title.items():
            if candidate_subject == subject_id:
                return Edition(title=title, authors=["作者"], isbn=isbn, douban_id=subject_id)
        return None


class DoubanToWeReadFakeWeRead:
    def __init__(self, by_title: dict[str, tuple[str, str]]) -> None:
        self.by_title = by_title
        self.search_calls: list[str] = []
        self.book_calls: list[str] = []

    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        self.search_calls.append(keyword)
        book_id, _isbn = self.by_title[keyword]
        return [WeReadSearchCandidate(book_id=book_id, title=keyword, author="作者", soldout=False)]

    def get_book(self, book_id: str) -> Edition | None:
        self.book_calls.append(book_id)
        for title, (candidate_id, isbn) in self.by_title.items():
            if candidate_id == book_id:
                return Edition(title=title, authors=["作者"], isbn=isbn, weread_id=book_id)
        return None

    def get_progress(self, book_id: str) -> WeReadProgress | None:
        raise AssertionError("progress is not used in Douban-to-WeRead batch")


class ShelfBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.shelf = WeReadShelfIndex(self.path)
        self.history = ReadingHistoryIndex(self.path)
        self.checkpoints = ReconciliationCheckpointStore(self.path)

    def _sync_weread_only_books(self, count: int, *, include_private_first: bool = False) -> dict[str, tuple[str, str]]:
        books: list[WeReadShelfBook] = []
        metadata: dict[str, tuple[str, str]] = {}
        for index in range(count):
            title = f"书{index + 1}"
            book_id = str(100 + index)
            isbn = f"9780000000{index + 1:03d}"
            secret = include_private_first and index == 0
            books.append(WeReadShelfBook(book_id=book_id, title=title, author="作者", secret=secret))
            metadata[book_id] = (title, isbn)
        self.shelf.replace_full(
            WeReadShelfSnapshot(books=tuple(books), album_count=0, has_mp=False),
            synced_at="shelf-v1",
        )
        self.history.replace_full([], synced_at="history-v1")
        return metadata

    def test_same_generation_skips_already_checkpointed_items(self) -> None:
        metadata = self._sync_weread_only_books(3)
        douban_map = {
            title: (str(1000 + index), isbn)
            for index, (_book_id, (title, isbn)) in enumerate(metadata.items())
        }
        weread = WeReadToDoubanFakeWeRead(metadata)
        douban = ExactDoubanSearch(douban_map)

        first = run_reconciliation_batch(
            WEREAD_TO_DOUBAN,
            limit=2,
            shelf_provider=self.shelf,
            history_provider=self.history,
            checkpoint_provider=self.checkpoints,
            weread_provider=weread,
            douban_provider=douban,
        )
        second = run_reconciliation_batch(
            WEREAD_TO_DOUBAN,
            limit=2,
            shelf_provider=self.shelf,
            history_provider=self.history,
            checkpoint_provider=self.checkpoints,
            weread_provider=weread,
            douban_provider=douban,
        )

        self.assertEqual([item.item_id for item in first.processed], ["100", "101"])
        self.assertEqual([item.item_id for item in second.processed], ["102"])
        self.assertEqual(second.already_completed, 2)
        self.assertEqual(second.remaining_after, 0)

    def test_private_shelf_items_are_deprioritized_for_background_batch(self) -> None:
        metadata = self._sync_weread_only_books(2, include_private_first=True)
        douban_map = {
            title: (str(2000 + index), isbn)
            for index, (_book_id, (title, isbn)) in enumerate(metadata.items())
        }
        result = run_reconciliation_batch(
            WEREAD_TO_DOUBAN,
            limit=1,
            shelf_provider=self.shelf,
            history_provider=self.history,
            checkpoint_provider=self.checkpoints,
            weread_provider=WeReadToDoubanFakeWeRead(metadata),
            douban_provider=ExactDoubanSearch(douban_map),
        )
        self.assertEqual(result.processed[0].item_id, "101")

    def test_batch_size_is_hard_capped_at_five(self) -> None:
        metadata = self._sync_weread_only_books(7)
        douban_map = {
            title: (str(3000 + index), isbn)
            for index, (_book_id, (title, isbn)) in enumerate(metadata.items())
        }
        result = run_reconciliation_batch(
            WEREAD_TO_DOUBAN,
            limit=99,
            shelf_provider=self.shelf,
            history_provider=self.history,
            checkpoint_provider=self.checkpoints,
            weread_provider=WeReadToDoubanFakeWeRead(metadata),
            douban_provider=ExactDoubanSearch(douban_map),
        )
        self.assertEqual(result.effective_limit, 5)
        self.assertEqual(len(result.processed), 5)
        self.assertEqual(result.remaining_after, 2)

    def test_douban_to_weread_batch_checkpoints_catalog_outcome(self) -> None:
        self.shelf.replace_full(
            WeReadShelfSnapshot(books=(), album_count=0, has_mp=False),
            synced_at="shelf-v1",
        )
        self.history.replace_full(
            [HistoryEntry("5001", "待读书", "wish")],
            synced_at="history-v1",
        )
        isbn = "9780000005001"
        douban = ExactDoubanSearch({"待读书": ("5001", isbn)})
        weread = DoubanToWeReadFakeWeRead({"待读书": ("9001", isbn)})

        result = run_reconciliation_batch(
            DOUBAN_TO_WEREAD,
            limit=3,
            shelf_provider=self.shelf,
            history_provider=self.history,
            checkpoint_provider=self.checkpoints,
            weread_provider=weread,
            douban_provider=douban,
        )

        self.assertEqual(len(result.processed), 1)
        self.assertEqual(result.processed[0].outcome, "available_exact")
        self.assertEqual(result.processed[0].source_state, "wish")
        completed = self.checkpoints.completed_ids(
            DOUBAN_TO_WEREAD,
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
        )
        self.assertEqual(completed, {"5001"})

    def test_new_baseline_generation_makes_item_pending_again(self) -> None:
        metadata = self._sync_weread_only_books(1)
        title, isbn = metadata["100"]
        douban = ExactDoubanSearch({title: ("7001", isbn)})
        weread = WeReadToDoubanFakeWeRead(metadata)

        first = run_reconciliation_batch(
            WEREAD_TO_DOUBAN,
            limit=1,
            shelf_provider=self.shelf,
            history_provider=self.history,
            checkpoint_provider=self.checkpoints,
            weread_provider=weread,
            douban_provider=douban,
        )
        self.assertEqual(len(first.processed), 1)

        self.shelf.replace_full(
            WeReadShelfSnapshot(
                books=(WeReadShelfBook(book_id="100", title=title, author="作者"),),
                album_count=0,
                has_mp=False,
            ),
            synced_at="shelf-v2",
        )
        second = run_reconciliation_batch(
            WEREAD_TO_DOUBAN,
            limit=1,
            shelf_provider=self.shelf,
            history_provider=self.history,
            checkpoint_provider=self.checkpoints,
            weread_provider=weread,
            douban_provider=douban,
        )
        self.assertEqual(len(second.processed), 1)
        self.assertEqual(second.already_completed, 0)


if __name__ == "__main__":
    unittest.main()
