from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.providers.weread import WeReadShelfBook, WeReadShelfSnapshot
from douban_weread.reconciliation.evidence_report import build_reconciliation_evidence_report
from douban_weread.reconciliation.shelf_batch import DOUBAN_TO_WEREAD, WEREAD_TO_DOUBAN
from douban_weread.storage import (
    ReadingHistoryIndex,
    ReconciliationEvidence,
    ReconciliationEvidenceStore,
    WeReadShelfIndex,
)


class ReconciliationEvidenceReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.shelf = WeReadShelfIndex(self.path)
        self.history = ReadingHistoryIndex(self.path)
        self.evidence = ReconciliationEvidenceStore(self.path)
        self.shelf.replace_full(
            WeReadShelfSnapshot(
                books=(
                    WeReadShelfBook(book_id="w1", title="微信独有", author="作者甲"),
                ),
                album_count=0,
                has_mp=False,
            ),
            synced_at="shelf-v1",
        )
        self.history.replace_full(
            [
                HistoryEntry("d1", "豆瓣在读", "do"),
                HistoryEntry("d2", "豆瓣想读", "wish"),
            ],
            synced_at="history-v1",
        )

    def test_report_counts_only_current_generation_verified_evidence(self) -> None:
        self.evidence.upsert(
            ReconciliationEvidence(
                direction=WEREAD_TO_DOUBAN,
                item_id="w1",
                shelf_sync_at="shelf-v1",
                history_sync_at="history-v1",
                policy_version=2,
                title="微信独有",
                outcome="suggest_wish",
                user_plan="suggest_douban_wish",
                summary="suggest wish",
                requires_user_action=True,
                selected_weread_book_id="w1",
                shelf_membership="yes",
            )
        )
        self.evidence.upsert(
            ReconciliationEvidence(
                direction=DOUBAN_TO_WEREAD,
                item_id="d1",
                shelf_sync_at="shelf-v1",
                history_sync_at="history-v1",
                policy_version=3,
                title="豆瓣在读",
                source_state="do",
                outcome="available_alternative",
                user_plan="review_edition",
                summary="review edition",
                requires_user_action=True,
                selected_douban_subject="d1",
                selected_weread_book_id="9001",
                shelf_membership="no",
            )
        )

        report = build_reconciliation_evidence_report(
            shelf_provider=self.shelf,
            history_provider=self.history,
            evidence_provider=self.evidence,
        )

        weread = report.for_direction(WEREAD_TO_DOUBAN)
        self.assertEqual(weread.candidate_total, 1)
        self.assertEqual(weread.verified_total, 1)
        self.assertEqual(weread.pending_total, 0)
        self.assertEqual(weread.requires_user_action_total, 1)
        self.assertEqual([(item.user_plan, item.count) for item in weread.plan_counts], [("suggest_douban_wish", 1)])

        douban = report.for_direction(DOUBAN_TO_WEREAD)
        self.assertEqual(douban.candidate_total, 2)
        self.assertEqual(douban.verified_total, 1)
        self.assertEqual(douban.pending_total, 1)
        self.assertEqual(douban.requires_user_action_total, 1)
        self.assertEqual([(item.user_plan, item.count) for item in douban.plan_counts], [("review_edition", 1)])

    def test_stale_policy_evidence_is_not_mixed_into_current_report(self) -> None:
        self.evidence.upsert(
            ReconciliationEvidence(
                direction=DOUBAN_TO_WEREAD,
                item_id="d1",
                shelf_sync_at="shelf-v1",
                history_sync_at="history-v1",
                policy_version=2,
                title="豆瓣在读",
                source_state="do",
                outcome="not_found",
                user_plan="weread_not_found",
                summary="old bounded result",
                requires_user_action=False,
            )
        )

        report = build_reconciliation_evidence_report(
            shelf_provider=self.shelf,
            history_provider=self.history,
            evidence_provider=self.evidence,
        )
        douban = report.for_direction(DOUBAN_TO_WEREAD)

        self.assertEqual(douban.policy_version, 3)
        self.assertEqual(douban.verified_total, 0)
        self.assertEqual(douban.pending_total, 2)
        self.assertEqual(douban.plan_counts, ())


if __name__ == "__main__":
    unittest.main()
