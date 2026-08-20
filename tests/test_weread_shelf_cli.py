from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from douban_weread.providers.weread import (
    WeReadProviderError,
    WeReadShelfBook,
    WeReadShelfSnapshot,
)
from douban_weread.storage import WeReadShelfIndex
from douban_weread.weread_shelf_cli import EXIT_NO_RESULTS, EXIT_OK, EXIT_PROVIDER_ERROR, run


class FakeShelfClient:
    def __init__(self, snapshot: WeReadShelfSnapshot | None = None, error: Exception | None = None) -> None:
        self.snapshot = snapshot
        self.error = error
        self.calls = 0

    def sync_shelf(self) -> WeReadShelfSnapshot:
        self.calls += 1
        if self.error:
            raise self.error
        assert self.snapshot is not None
        return self.snapshot


class WeReadShelfCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.index = WeReadShelfIndex(self.path)
        self.snapshot = WeReadShelfSnapshot(
            books=(
                WeReadShelfBook(
                    book_id="230107",
                    title="白夜行",
                    author="东野圭吾",
                    deep_link="https://weread.qq.com/book-detail?test=1",
                    finish_reading=False,
                ),
                WeReadShelfBook(
                    book_id="2",
                    title="已读完的书",
                    author="作者",
                    finish_reading=True,
                    secret=True,
                ),
            ),
            album_count=2,
            has_mp=True,
        )

    def test_sync_replaces_local_baseline_and_prints_counts(self) -> None:
        client = FakeShelfClient(self.snapshot)
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["sync"],
            client_factory=lambda: client,
            index_factory=lambda: self.index,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(client.calls, 1)
        status = self.index.status()
        self.assertTrue(status.complete)
        self.assertEqual(status.books, 2)
        self.assertEqual(status.albums, 2)
        self.assertTrue(status.has_mp)
        self.assertEqual(status.visible_entries, 5)
        output = stdout.getvalue()
        self.assertIn("WeRead shelf baseline synced successfully.", output)
        self.assertIn("Visible shelf entries: 5", output)
        self.assertIn("Electronic books: 2", output)
        self.assertIn("Albums / audio books: 2", output)
        self.assertIn("Article collection: yes", output)
        self.assertEqual(stderr.getvalue(), "")

    def test_status_reads_local_baseline_without_client(self) -> None:
        self.index.replace_full(self.snapshot, synced_at="2026-08-20T12:00:00+00:00")
        stdout = io.StringIO()

        code = run(
            ["status"],
            client_factory=lambda: (_ for _ in ()).throw(AssertionError("client should not be created")),
            index_factory=lambda: self.index,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        self.assertIn("WeRead shelf baseline: complete", stdout.getvalue())
        self.assertIn("Last full sync: 2026-08-20T12:00:00+00:00", stdout.getvalue())

    def test_lookup_reads_local_candidates_only(self) -> None:
        self.index.replace_full(self.snapshot)
        stdout = io.StringIO()

        code = run(
            ["lookup", "白夜行"],
            client_factory=lambda: (_ for _ in ()).throw(AssertionError("client should not be created")),
            index_factory=lambda: self.index,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        output = stdout.getvalue()
        self.assertIn('Local WeRead shelf candidates for "白夜行"', output)
        self.assertIn("bookId 230107 | 白夜行 | 东野圭吾 | finished: no", output)
        self.assertIn("Work/Edition verification is still required", output)

    def test_lookup_requires_complete_baseline(self) -> None:
        stderr = io.StringIO()

        code = run(
            ["lookup", "白夜行"],
            index_factory=lambda: self.index,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_NO_RESULTS)
        self.assertIn("shelf baseline is not complete", stderr.getvalue())

    def test_sync_provider_failure_does_not_become_empty_baseline(self) -> None:
        client = FakeShelfClient(error=WeReadProviderError("gateway unavailable"))
        stderr = io.StringIO()

        code = run(
            ["sync"],
            client_factory=lambda: client,
            index_factory=lambda: self.index,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_PROVIDER_ERROR)
        self.assertFalse(self.index.status().complete)
        self.assertIn("WeRead shelf sync error: gateway unavailable", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
