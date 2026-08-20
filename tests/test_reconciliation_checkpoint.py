from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from douban_weread.storage import (
    CURRENT_RECONCILIATION_POLICY_VERSION,
    ReconciliationCheckpointStore,
)


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
        self.assertEqual(rows[0].policy_version, CURRENT_RECONCILIATION_POLICY_VERSION)
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

    def test_policy_upgrade_does_not_reuse_old_checkpoint(self) -> None:
        kwargs = {
            "shelf_sync_at": "shelf",
            "history_sync_at": "history",
        }
        self.store.mark_completed(
            "douban-to-weread",
            "2567698",
            outcome="not_found",
            policy_version=1,
            **kwargs,
        )

        self.assertEqual(
            self.store.completed_ids(
                "douban-to-weread",
                policy_version=1,
                **kwargs,
            ),
            {"2567698"},
        )
        self.assertEqual(
            self.store.completed_ids(
                "douban-to-weread",
                policy_version=CURRENT_RECONCILIATION_POLICY_VERSION,
                **kwargs,
            ),
            set(),
        )

        self.store.mark_completed(
            "douban-to-weread",
            "2567698",
            outcome="available_exact",
            policy_version=CURRENT_RECONCILIATION_POLICY_VERSION,
            **kwargs,
        )
        self.assertEqual(
            self.store.completed_ids(
                "douban-to-weread",
                policy_version=1,
                **kwargs,
            ),
            set(),
        )
        self.assertEqual(
            self.store.completed_ids(
                "douban-to-weread",
                policy_version=CURRENT_RECONCILIATION_POLICY_VERSION,
                **kwargs,
            ),
            {"2567698"},
        )

    def test_legacy_table_is_migrated_and_defaults_existing_rows_to_policy_v1(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.executescript(
                """
                CREATE TABLE reconciliation_checkpoints (
                    direction TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    shelf_sync_at TEXT NOT NULL,
                    history_sync_at TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY(direction, item_id, shelf_sync_at, history_sync_at)
                );
                INSERT INTO reconciliation_checkpoints(
                    direction, item_id, shelf_sync_at, history_sync_at, outcome, recorded_at
                ) VALUES (
                    'douban-to-weread', '2567698', 'shelf', 'history', 'not_found', '2026-08-20T00:00:00+00:00'
                );
                """
            )

        self.store.initialize()

        self.assertEqual(
            self.store.completed_ids(
                "douban-to-weread",
                shelf_sync_at="shelf",
                history_sync_at="history",
                policy_version=1,
            ),
            {"2567698"},
        )
        self.assertEqual(
            self.store.completed_ids(
                "douban-to-weread",
                shelf_sync_at="shelf",
                history_sync_at="history",
                policy_version=CURRENT_RECONCILIATION_POLICY_VERSION,
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
        with self.assertRaisesRegex(ValueError, "policy_version"):
            self.store.completed_ids(
                "weread-to-douban",
                shelf_sync_at="shelf",
                history_sync_at="history",
                policy_version=0,
            )


if __name__ == "__main__":
    unittest.main()
