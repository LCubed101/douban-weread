from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from douban_weread.providers.weread import (
    WeReadShelfArchive,
    WeReadShelfBook,
    WeReadShelfSnapshot,
)
from douban_weread.storage import WeReadShelfIndex


class WeReadShelfStorageTests(unittest.TestCase):
    def test_replace_full_persists_complete_baseline_and_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.sqlite3"
            index = WeReadShelfIndex(path)
            snapshot = WeReadShelfSnapshot(
                books=(
                    WeReadShelfBook(
                        book_id="230107",
                        title="白夜行",
                        author="东野圭吾",
                        deep_link="https://weread.qq.com/book-detail?type=1&v=test",
                        category="小说",
                        read_update_time=1720000000,
                        finish_reading=True,
                        secret=False,
                    ),
                    WeReadShelfBook(book_id="2", title="恶意", author="东野圭吾"),
                ),
                album_count=2,
                has_mp=True,
                archives=(WeReadShelfArchive(name="小说", book_ids=("230107", "2")),),
            )

            index.replace_full(snapshot, synced_at="2026-08-20T12:00:00+00:00")
            status = index.status()

            self.assertTrue(status.complete)
            self.assertEqual(status.books, 2)
            self.assertEqual(status.albums, 2)
            self.assertTrue(status.has_mp)
            self.assertEqual(status.visible_entries, 5)
            self.assertEqual(status.last_full_sync_at, "2026-08-20T12:00:00+00:00")

            book = index.get("230107")
            self.assertIsNotNone(book)
            assert book is not None
            self.assertEqual(book.title, "白夜行")
            self.assertTrue(book.finish_reading)

    def test_lookup_is_local_title_shortlist_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = WeReadShelfIndex(Path(tmp) / "state.sqlite3")
            index.replace_full(
                WeReadShelfSnapshot(
                    books=(
                        WeReadShelfBook(book_id="1", title="白夜行", author="东野圭吾"),
                        WeReadShelfBook(book_id="2", title="白夜行（新版）", author="东野圭吾"),
                        WeReadShelfBook(book_id="3", title="恶意", author="东野圭吾"),
                    ),
                    album_count=0,
                    has_mp=False,
                )
            )

            results = index.find_title_candidates("白夜行", limit=10)
            self.assertEqual([item.book_id for item in results], ["1", "2"])

    def test_invalid_replacement_preserves_previous_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = WeReadShelfIndex(Path(tmp) / "state.sqlite3")
            index.replace_full(
                WeReadShelfSnapshot(
                    books=(WeReadShelfBook(book_id="1", title="原有书"),),
                    album_count=0,
                    has_mp=False,
                )
            )

            bad = WeReadShelfSnapshot(
                books=(
                    WeReadShelfBook(book_id="2", title=""),
                ),
                album_count=0,
                has_mp=False,
            )
            with self.assertRaisesRegex(ValueError, "missing a title"):
                index.replace_full(bad)

            self.assertIsNotNone(index.get("1"))
            self.assertTrue(index.status().complete)
            self.assertEqual(index.status().books, 1)

    def test_uninitialized_status_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = WeReadShelfIndex(Path(tmp) / "missing.sqlite3").status()
            self.assertFalse(status.initialized)
            self.assertFalse(status.complete)
            self.assertEqual(status.visible_entries, 0)


if __name__ == "__main__":
    unittest.main()
