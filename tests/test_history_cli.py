from __future__ import annotations

import io
import unittest
from pathlib import Path

from douban_weread.cli import EXIT_NO_RESULTS, EXIT_OK, EXIT_PROVIDER_ERROR, run
from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.providers.douban.interest import DoubanAuthError
from douban_weread.storage import HistoryIndexStatus, IndexedHistoryEntry


class FakeHistoryClient:
    def __init__(self) -> None:
        self.entries = [
            HistoryEntry("1", "想读书", "wish"),
            HistoryEntry("2", "在读书", "do"),
            HistoryEntry("3", "读过书", "collect"),
        ]
        self.error: Exception | None = None
        self.calls = 0

    def fetch_all(self) -> list[HistoryEntry]:
        self.calls += 1
        if self.error:
            raise self.error
        return self.entries


class FakeHistoryIndex:
    def __init__(self, *, complete: bool = True) -> None:
        self.replaced: list[HistoryEntry] | None = None
        self.complete = complete
        self.lookup_results: list[IndexedHistoryEntry] = []

    def replace_full(self, entries: list[HistoryEntry], *, synced_at: str | None = None) -> None:
        self.replaced = list(entries)
        self.complete = True

    def status(self) -> HistoryIndexStatus:
        if self.replaced is not None:
            counts = {"wish": 0, "do": 0, "collect": 0}
            for entry in self.replaced:
                counts[entry.state] += 1
            total = len(self.replaced)
        else:
            counts = {"wish": 0, "do": 0, "collect": 0}
            total = 0
        return HistoryIndexStatus(
            path=Path("/tmp/history.sqlite3"),
            initialized=self.complete,
            complete=self.complete,
            last_full_sync_at="2026-08-19T08:00:00+00:00" if self.complete else None,
            total=total,
            wish=counts["wish"],
            reading=counts["do"],
            read=counts["collect"],
        )

    def find_title_candidates(self, title: str, *, limit: int = 30, min_similarity: float = 0.72):
        return self.lookup_results[:limit]


class HistoryCliTests(unittest.TestCase):
    def test_full_sync_fetches_before_replacing_local_baseline(self) -> None:
        client = FakeHistoryClient()
        index = FakeHistoryIndex(complete=False)
        stdout = io.StringIO()

        code = run(
            ["history", "sync", "--full"],
            history_client_factory=lambda: client,
            history_index_factory=lambda: index,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(client.calls, 1)
        self.assertEqual(index.replaced, client.entries)
        self.assertIn("baseline synced successfully", stdout.getvalue())
        self.assertIn("Total: 3", stdout.getvalue())

    def test_failed_remote_sync_does_not_replace_existing_baseline(self) -> None:
        client = FakeHistoryClient()
        client.error = DoubanAuthError("expired")
        index = FakeHistoryIndex(complete=True)
        stderr = io.StringIO()

        code = run(
            ["history", "sync", "--full"],
            history_client_factory=lambda: client,
            history_index_factory=lambda: index,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_PROVIDER_ERROR)
        self.assertIsNone(index.replaced)
        self.assertIn("expired", stderr.getvalue())

    def test_history_status_is_local_only(self) -> None:
        index = FakeHistoryIndex(complete=True)
        stdout = io.StringIO()

        def network_factory():
            raise AssertionError("history status must not construct a network client")

        code = run(
            ["history", "status"],
            history_client_factory=network_factory,
            history_index_factory=lambda: index,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        self.assertIn("History baseline: complete", stdout.getvalue())

    def test_unsynced_history_status_returns_no_results(self) -> None:
        index = FakeHistoryIndex(complete=False)
        stdout = io.StringIO()

        code = run(
            ["history", "status"],
            history_index_factory=lambda: index,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_NO_RESULTS)
        self.assertIn("not synced", stdout.getvalue())

    def test_lookup_is_local_only_and_labels_read_state(self) -> None:
        index = FakeHistoryIndex(complete=True)
        index.lookup_results = [
            IndexedHistoryEntry(
                subject_id="25837854",
                title="荷马史诗·奥德赛",
                state="collect",
                title_key="荷马史诗奥德赛",
                last_seen_at="2026-08-19T08:00:00+00:00",
            )
        ]
        stdout = io.StringIO()

        def network_factory():
            raise AssertionError("history lookup must not construct a network client")

        code = run(
            ["history", "lookup", "荷马史诗：奥德赛"],
            history_client_factory=network_factory,
            history_index_factory=lambda: index,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        self.assertIn("READ | subject 25837854", stdout.getvalue())
        self.assertIn("candidates only", stdout.getvalue())

    def test_lookup_requires_complete_baseline(self) -> None:
        index = FakeHistoryIndex(complete=False)
        stderr = io.StringIO()

        code = run(
            ["history", "lookup", "奥德赛"],
            history_index_factory=lambda: index,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_NO_RESULTS)
        self.assertIn("history sync --full", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
