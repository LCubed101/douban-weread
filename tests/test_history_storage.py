from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.storage import ReadingHistoryIndex


class ReadingHistoryIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "history.sqlite3"
        self.index = ReadingHistoryIndex(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_unsynced_status_does_not_create_database(self) -> None:
        status = self.index.status()
        self.assertFalse(status.initialized)
        self.assertFalse(status.complete)
        self.assertEqual(status.total, 0)
        self.assertFalse(self.path.exists())

    def test_full_replace_records_counts_and_sync_time(self) -> None:
        self.index.replace_full(
            [
                HistoryEntry("1", "书一", "wish"),
                HistoryEntry("2", "书二", "do"),
                HistoryEntry("3", "书三", "collect"),
                HistoryEntry("4", "书四", "collect"),
            ],
            synced_at="2026-08-19T08:00:00+00:00",
        )

        status = self.index.status()
        self.assertTrue(status.initialized)
        self.assertTrue(status.complete)
        self.assertEqual(status.total, 4)
        self.assertEqual(status.wish, 1)
        self.assertEqual(status.reading, 1)
        self.assertEqual(status.read, 2)
        self.assertEqual(status.last_full_sync_at, "2026-08-19T08:00:00+00:00")

    def test_pre_fix_complete_zero_baseline_is_invalidated(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.executescript(
                """
                CREATE TABLE history_entries (
                    subject_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    title_key TEXT NOT NULL,
                    state TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                CREATE TABLE history_sync_state (
                    source TEXT PRIMARY KEY,
                    complete INTEGER NOT NULL DEFAULT 0,
                    last_full_sync_at TEXT,
                    counts_json TEXT NOT NULL DEFAULT '{}'
                );
                INSERT INTO history_sync_state(source, complete, last_full_sync_at, counts_json)
                VALUES ('douban', 1, '2026-08-19T09:03:30+00:00', '{}');
                """
            )

        status = self.index.status()

        self.assertTrue(status.initialized)
        self.assertFalse(status.complete)
        self.assertEqual(status.total, 0)

    def test_v2_nonzero_baseline_with_corrupted_titles_is_invalidated(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.executescript(
                """
                CREATE TABLE history_entries (
                    subject_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    title_key TEXT NOT NULL,
                    state TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                CREATE TABLE history_sync_state (
                    source TEXT PRIMARY KEY,
                    complete INTEGER NOT NULL DEFAULT 0,
                    last_full_sync_at TEXT,
                    counts_json TEXT NOT NULL DEFAULT '{}',
                    baseline_version INTEGER NOT NULL DEFAULT 0
                );
                INSERT INTO history_entries(subject_id, title, title_key, state, last_seen_at)
                VALUES ('35307049', '纸质版 46.60元', '纸质版4660元', 'wish', '2026-08-19T09:40:22+00:00');
                INSERT INTO history_sync_state(
                    source, complete, last_full_sync_at, counts_json, baseline_version
                )
                VALUES ('douban', 1, '2026-08-19T09:40:22+00:00', '{"wish": 1}', 2);
                """
            )

        status = self.index.status()

        self.assertTrue(status.initialized)
        self.assertFalse(status.complete)
        self.assertEqual(status.total, 1)

    def test_full_replace_is_a_snapshot_not_an_append(self) -> None:
        self.index.replace_full(
            [HistoryEntry("1", "旧书", "wish"), HistoryEntry("2", "旧书二", "collect")]
        )
        self.index.replace_full([HistoryEntry("3", "新书", "do")])

        self.assertIsNone(self.index.get("1"))
        self.assertIsNone(self.index.get("2"))
        self.assertEqual(self.index.get("3").state, "do")  # type: ignore[union-attr]

    def test_title_shortlist_is_local_and_non_authoritative(self) -> None:
        self.index.replace_full(
            [
                HistoryEntry("25837854", "荷马史诗·奥德赛", "wish"),
                HistoryEntry("1062694", "荷马史诗：奥德赛", "collect"),
                HistoryEntry("999", "伊利亚特", "collect"),
            ]
        )

        candidates = self.index.find_title_candidates("荷马史诗·奥德赛")
        ids = {entry.subject_id for entry in candidates}
        self.assertIn("25837854", ids)
        self.assertIn("1062694", ids)
        self.assertNotIn("999", ids)

    def test_one_character_substring_does_not_pollute_title_shortlist(self) -> None:
        self.index.replace_full(
            [
                HistoryEntry("3259440", "白夜行", "collect"),
                HistoryEntry("10554308", "白夜行", "collect"),
                HistoryEntry("35965039", "白", "wish"),
            ]
        )

        candidates = self.index.find_title_candidates("白夜行")
        ids = {entry.subject_id for entry in candidates}

        self.assertEqual(ids, {"3259440", "10554308"})

    def test_set_state_updates_one_verified_project_owned_mutation(self) -> None:
        self.index.replace_full([HistoryEntry("1", "测试书", "wish")])
        self.index.set_state("1", "测试书", "collect")
        entry = self.index.get("1")
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.state, "collect")

    def test_invalid_state_is_rejected_before_snapshot_replace(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported history state"):
            self.index.replace_full([HistoryEntry("1", "测试书", "unknown")])
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
