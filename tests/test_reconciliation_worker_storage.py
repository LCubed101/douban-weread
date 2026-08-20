from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from douban_weread.storage import ReconciliationWorkerState, ReconciliationWorkerStateStore


class ReconciliationWorkerStateStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.store = ReconciliationWorkerStateStore(self.path)

    def test_round_trip_preserves_generation_and_progress(self) -> None:
        self.store.upsert(
            ReconciliationWorkerState(
                shelf_sync_at="shelf-v1",
                history_sync_at="history-v1",
                weread_to_douban_policy=2,
                douban_to_weread_policy=3,
                status="partial",
                tick_count=2,
                processed_last_tick=4,
                weread_to_douban_verified=4,
                weread_to_douban_pending=165,
                douban_to_weread_verified=6,
                douban_to_weread_pending=1431,
                last_stop_reason="max_items",
                started_at="2026-08-20T14:00:00+00:00",
            )
        )

        row = self.store.get_generation(
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            weread_to_douban_policy=2,
            douban_to_weread_policy=3,
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.status, "partial")
        self.assertEqual(row.tick_count, 2)
        self.assertEqual(row.processed_last_tick, 4)
        self.assertEqual(row.verified_total, 10)
        self.assertEqual(row.pending_total, 1596)
        self.assertEqual(row.last_stop_reason, "max_items")
        self.assertIsNotNone(row.updated_at)

    def test_policy_generation_is_part_of_worker_identity(self) -> None:
        base = dict(
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            status="partial",
            tick_count=1,
            processed_last_tick=1,
            weread_to_douban_verified=0,
            weread_to_douban_pending=1,
            douban_to_weread_verified=1,
            douban_to_weread_pending=1,
        )
        self.store.upsert(
            ReconciliationWorkerState(
                **base,
                weread_to_douban_policy=1,
                douban_to_weread_policy=2,
            )
        )

        current = self.store.get_generation(
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            weread_to_douban_policy=2,
            douban_to_weread_policy=3,
        )
        self.assertIsNone(current)

    def test_schema_has_no_raw_payload_or_credential_columns(self) -> None:
        self.store.initialize()
        with sqlite3.connect(self.path) as conn:
            columns = {
                str(row[1]).lower()
                for row in conn.execute("PRAGMA table_info(reconciliation_worker_state)").fetchall()
            }

        forbidden = ("raw", "payload", "cookie", "api_key", "credential", "token")
        for column in columns:
            self.assertFalse(any(fragment in column for fragment in forbidden), column)


if __name__ == "__main__":
    unittest.main()
