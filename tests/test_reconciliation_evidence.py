from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from douban_weread.storage import ReconciliationEvidence, ReconciliationEvidenceStore


class ReconciliationEvidenceStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.store = ReconciliationEvidenceStore(self.path)

    def test_round_trip_preserves_normalized_report_fields(self) -> None:
        self.store.upsert(
            ReconciliationEvidence(
                direction="douban-to-weread",
                item_id="2567698",
                shelf_sync_at="shelf-v1",
                history_sync_at="history-v1",
                policy_version=3,
                title="三体",
                source_state="do",
                outcome="available_alternative",
                user_plan="review_edition",
                summary="A same-Work WeRead Edition is available, but material Edition differences require review.",
                requires_user_action=True,
                selected_douban_subject="2567698",
                selected_weread_book_id="178677",
                selected_edition_title="三体1",
                match_kind="alternative_edition",
                exact_edition=False,
                requires_confirmation=True,
                weread_catalog_status="available_alternative",
                weread_resolution="alternative_edition",
                shelf_membership="no",
                deep_link="https://weread.qq.com/book-detail?example",
                catalog_search_limit=10,
                recorded_at="2026-08-20T14:00:00+00:00",
            )
        )

        rows = self.store.list_generation(
            "douban-to-weread",
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            policy_version=3,
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.item_id, "2567698")
        self.assertEqual(row.user_plan, "review_edition")
        self.assertEqual(row.selected_weread_book_id, "178677")
        self.assertEqual(row.selected_edition_title, "三体1")
        self.assertEqual(row.match_kind, "alternative_edition")
        self.assertFalse(row.exact_edition)
        self.assertTrue(row.requires_confirmation)
        self.assertEqual(row.shelf_membership, "no")
        self.assertEqual(row.catalog_search_limit, 10)

    def test_policy_generations_are_kept_separate(self) -> None:
        base = dict(
            direction="douban-to-weread",
            item_id="2567698",
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            title="三体",
            source_state="do",
            summary="bounded result",
            requires_user_action=False,
        )
        self.store.upsert(
            ReconciliationEvidence(
                **base,
                policy_version=2,
                outcome="not_found",
                user_plan="weread_not_found",
            )
        )
        self.store.upsert(
            ReconciliationEvidence(
                **base,
                policy_version=3,
                outcome="available_alternative",
                user_plan="review_edition",
                requires_user_action=True,
            )
        )

        v2 = self.store.list_generation(
            "douban-to-weread",
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            policy_version=2,
        )
        v3 = self.store.list_generation(
            "douban-to-weread",
            shelf_sync_at="shelf-v1",
            history_sync_at="history-v1",
            policy_version=3,
        )
        self.assertEqual([row.user_plan for row in v2], ["weread_not_found"])
        self.assertEqual([row.user_plan for row in v3], ["review_edition"])

    def test_schema_has_no_raw_provider_or_credential_payload_columns(self) -> None:
        self.store.initialize()
        with sqlite3.connect(self.path) as conn:
            columns = {
                str(row[1]).lower()
                for row in conn.execute("PRAGMA table_info(reconciliation_evidence)").fetchall()
            }

        forbidden_fragments = ("raw", "payload", "cookie", "api_key", "credential", "token")
        for column in columns:
            self.assertFalse(
                any(fragment in column for fragment in forbidden_fragments),
                f"unexpected sensitive/raw evidence column: {column}",
            )


if __name__ == "__main__":
    unittest.main()
