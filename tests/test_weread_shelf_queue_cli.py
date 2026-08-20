from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.providers.weread import WeReadShelfBook, WeReadShelfSnapshot
from douban_weread.storage import ReadingHistoryIndex, WeReadShelfIndex
from douban_weread.weread_shelf_cli import EXIT_NO_RESULTS, EXIT_OK, run


class WeReadShelfQueueCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.shelf = WeReadShelfIndex(self.path)
        self.history = ReadingHistoryIndex(self.path)
        self.shelf.replace_full(
            WeReadShelfSnapshot(
                books=(
                    WeReadShelfBook(book_id="10", title="微信独有", author="作者甲"),
                    WeReadShelfBook(book_id="20", title="共有书", author="作者乙"),
                ),
                album_count=0,
                has_mp=False,
            )
        )
        self.history.replace_full(
            [
                HistoryEntry("100", "共有书", "wish"),
                HistoryEntry("200", "豆瓣独有", "wish"),
                HistoryEntry("300", "过去已读", "collect"),
            ]
        )

    @staticmethod
    def _no_network():
        raise AssertionError("queue must not create a network client")

    def test_queue_lists_both_directions_with_next_commands_without_network(self) -> None:
        stdout = io.StringIO()
        code = run(
            ["queue", "--limit", "5"],
            client_factory=self._no_network,
            douban_verification_factory=self._no_network,
            index_factory=lambda: self.shelf,
            history_index_factory=lambda: self.history,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        output = stdout.getvalue()
        self.assertIn("Local reconciliation verification queue", output)
        self.assertIn("WeRead → Douban candidates: 1", output)
        self.assertIn("bookId 10 | 微信独有 | 作者甲", output)
        self.assertIn("douban-weread weread shelf verify --id 10", output)
        self.assertIn("Douban → WeRead candidates: 1", output)
        self.assertIn("subject 200 | 豆瓣独有 | state: wish", output)
        self.assertIn("douban-weread weread resolve --subject 200 --limit 5", output)
        self.assertNotIn("subject 300", output)
        self.assertIn("makes no network requests", output)
        self.assertIn("No mutation is authorized", output)

    def test_queue_direction_filter_only_prints_requested_side(self) -> None:
        stdout = io.StringIO()
        code = run(
            ["queue", "--direction", "weread-to-douban", "--limit", "1"],
            client_factory=self._no_network,
            douban_verification_factory=self._no_network,
            index_factory=lambda: self.shelf,
            history_index_factory=lambda: self.history,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        output = stdout.getvalue()
        self.assertIn("WeRead → Douban candidates: 1", output)
        self.assertNotIn("Douban → WeRead candidates", output)

    def test_queue_requires_both_complete_local_baselines(self) -> None:
        empty_history_path = Path(self.tempdir.name) / "other.sqlite3"
        incomplete_history = ReadingHistoryIndex(empty_history_path)
        stderr = io.StringIO()

        code = run(
            ["queue"],
            client_factory=self._no_network,
            douban_verification_factory=self._no_network,
            index_factory=lambda: self.shelf,
            history_index_factory=lambda: incomplete_history,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_NO_RESULTS)
        self.assertIn("Both complete baselines are required", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
