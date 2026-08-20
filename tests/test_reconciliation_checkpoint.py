from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from douban_weread.storage import ReconciliationCheckpointStore


class ReconciliationCheckpointStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.store = ReconciliationCheckpointStore(self.path)

    def test_marks_and_reads_one_generation(self) -> None:
        self.store.mark_completed(
            "weread-to-douban",
            "37724838",
            shelf_sync_at="2026-08-20T11:39:53+00:00",
            history_sync_at="2026-08-19T11:08:42+00:00",
            outcome="suggest_wish",
            recorded_at="2026-08-20T12:30:00+00:00",
        )

        completed = self.store.completed_ids(
            "weread-to-douban",
            shelf_sync_at="2026-08-20T11:39:53+00:00",
            history_sync_at="2026-08-19T11:08:42+00:00",
        )
        self.assertEqual(completed, {"37724838"})
        rows = self.store.list_generation(
            "weread-to-douban",
            shelf_sync_at="2026-08-20T11:39:53+00:00",
            history_sync_at="2026-08-19T11:08:42+00:00",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].outcome, "suggest_wish")

    def test_new_baseline_generation_does_not_reuse_old_checkpoint(self) -> None:
        self.store.mark_completed(
            "douban-to-weread",
            "35791241",
            shelf_sync_at="old-shelf",
            history_sync_at="old-history",
            outcome="available_exact",
        )

        self.assertEqual(
            self.store.completed_ids(
                "douban-to-weread",
                shelf_sync_at="new-shelf",
                history_sync_at="old-history",
            ),
            set(),
        )

    def test_upsert_replaces_outcome_in_same_generation(self) -> None:
        kwargs = {
            "shelf_sync_at": "shelf",
            "history_sync_at": "history",
        }
        self.store.mark_completed(
            "weread-to-douban",
            "1",
            outcome="review_identity",
            **kwargs,
        )
        self.store.mark_completed(
            "weread-to-douban",
            "1",
            outcome="suggest_wish",
            **kwargs,
        )
        rows = self.store.list_generation("weread-to-douban", **kwargs)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].outcome, "suggest_wish")

    def test_invalid_direction_and_blank_generation_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            self.store.completed_ids(
                "both",
                shelf_sync_at="shelf",
                history_sync_at="history",
            )
        with self.assertRaisesRegex(ValueError, "timestamps"):
            self.store.completed_ids(
                "weread-to-douban",
                shelf_sync_at="",
                history_sync_at="history",
            )


if __name__ == "__main__":
    unittest.main()
