from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.providers.weread import WeReadShelfBook, WeReadShelfSnapshot
from douban_weread.reconciliation.onboarding import FirstLoginReconciliationPhase
from douban_weread.reconciliation.product_view import (
    ProductReconciliationBucket,
    build_product_reconciliation_view,
)
from douban_weread.storage import (
    ReadingHistoryIndex,
    ReconciliationEvidence,
    ReconciliationEvidenceStore,
    ReconciliationWorkerStateStore,
    WeReadShelfIndex,
)


class ReconciliationProductViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "history.sqlite3"
        self.shelf = WeReadShelfIndex(self.path)
        self.history = ReadingHistoryIndex(self.path)
        self.evidence = ReconciliationEvidenceStore(self.path)
        self.worker = ReconciliationWorkerStateStore(self.path)

    def _view(self):
        return build_product_reconciliation_view(
            shelf_provider=self.shelf,
            history_provider=self.history,
            evidence_provider=self.evidence,
            state_provider=self.worker,
        )

    def _complete_baselines(self) -> None:
        self.shelf.replace_full(
            WeReadShelfSnapshot(
                books=(
                    WeReadShelfBook(book_id="7001", title="微信别名", author="作者"),
                ),
                album_count=0,
                has_mp=False,
            ),
            synced_at="shelf-v1",
        )
        self.history.replace_full(
            [
                HistoryEntry("1001", "三体", "do"),
                HistoryEntry("1002", "没找到", "wish"),
                HistoryEntry("1003", "待处理", "wish"),
            ],
            synced_at="history-v1",
        )

    def _upsert(
        self,
        *,
        direction: str,
        item_id: str,
        title: str,
        user_plan: str,
        requires_user_action: bool,
        policy_version: int,
        **kwargs,
    ) -> None:
        self.evidence.upsert(
            ReconciliationEvidence(
                direction=direction,
                item_id=item_id,
                shelf_sync_at="shelf-v1",
                history_sync_at="history-v1",
                policy_version=policy_version,
                title=title,
                outcome=kwargs.pop("outcome", user_plan),
                user_plan=user_plan,
                summary=kwargs.pop("summary", user_plan),
                requires_user_action=requires_user_action,
                **kwargs,
            )
        )

    def test_missing_baselines_have_unknown_coverage_not_zero(self) -> None:
        view = self._view()

        self.assertEqual(view.phase, FirstLoginReconciliationPhase.NEEDS_BASELINES)
        self.assertFalse(view.ready_for_reconciliation)
        self.assertEqual(view.missing_baselines, ("douban", "weread"))
        self.assertIsNone(view.candidate_total)
        self.assertIsNone(view.verified_total)
        self.assertIsNone(view.pending_total)
        self.assertIsNone(view.progress_percent)
        self.assertEqual(view.items, ())

    def test_partial_current_generation_aggregates_ui_counts_without_classifying_pending(self) -> None:
        self._complete_baselines()
        self._upsert(
            direction="weread-to-douban",
            item_id="7001",
            title="微信别名",
            user_plan="aligned",
            requires_user_action=False,
            policy_version=2,
            selected_weread_book_id="7001",
            shelf_membership="yes",
        )
        self._upsert(
            direction="douban-to-weread",
            item_id="1001",
            title="三体",
            user_plan="review_edition",
            requires_user_action=True,
            policy_version=3,
            selected_douban_subject="1001",
            selected_weread_book_id="178677",
            selected_edition_title="三体1",
            shelf_membership="no",
            match_kind="alternative_edition",
            deep_link="https://weread.qq.com/book-detail/example",
        )
        self._upsert(
            direction="douban-to-weread",
            item_id="1002",
            title="没找到",
            user_plan="weread_not_found",
            requires_user_action=False,
            policy_version=3,
            shelf_membership="unresolved",
        )

        view = self._view()

        self.assertEqual(view.phase, FirstLoginReconciliationPhase.RECONCILING)
        self.assertTrue(view.ready_for_reconciliation)
        self.assertEqual(view.candidate_total, 4)
        self.assertEqual(view.verified_total, 3)
        self.assertEqual(view.pending_total, 1)
        self.assertEqual(view.progress_percent, 75)
        self.assertEqual(view.requires_user_action_total, 1)
        self.assertEqual(view.aligned_total, 1)
        self.assertEqual(view.no_user_action_total, 2)
        counts = {item.bucket: item.count for item in view.bucket_counts}
        self.assertEqual(counts[ProductReconciliationBucket.ALIGNED], 1)
        self.assertEqual(counts[ProductReconciliationBucket.REVIEW], 1)
        self.assertEqual(counts[ProductReconciliationBucket.WEREAD_NOT_FOUND], 1)
        self.assertEqual(len(view.items), 3)

    def test_review_item_preserves_selected_edition_identity_for_detail_ui(self) -> None:
        self._complete_baselines()
        self._upsert(
            direction="douban-to-weread",
            item_id="1001",
            title="三体",
            user_plan="review_edition",
            requires_user_action=True,
            policy_version=3,
            selected_douban_subject="1001",
            selected_weread_book_id="178677",
            selected_edition_title="三体1",
            shelf_membership="no",
            match_kind="alternative_edition",
            deep_link="https://weread.qq.com/book-detail/example",
        )

        view = self._view()
        item = next(item for item in view.items if item.item_id == "1001")

        self.assertEqual(item.bucket, ProductReconciliationBucket.REVIEW)
        self.assertEqual(item.weread_book_id, "178677")
        self.assertEqual(item.selected_edition_title, "三体1")
        self.assertEqual(item.match_kind, "alternative_edition")
        self.assertEqual(item.shelf_membership, "no")
        self.assertEqual(item.deep_link, "https://weread.qq.com/book-detail/example")

    def test_keep_douban_history_is_no_action_but_not_counted_as_aligned(self) -> None:
        self._complete_baselines()
        self._upsert(
            direction="weread-to-douban",
            item_id="7001",
            title="微信别名",
            user_plan="keep_douban_history",
            requires_user_action=False,
            policy_version=2,
            selected_weread_book_id="7001",
            shelf_membership="yes",
            strongest_douban_state="read",
        )

        view = self._view()

        self.assertEqual(view.aligned_total, 0)
        self.assertEqual(view.no_user_action_total, 1)
        counts = {item.bucket: item.count for item in view.bucket_counts}
        self.assertEqual(counts[ProductReconciliationBucket.KEEP_DOUBAN_HISTORY], 1)

    def test_stale_policy_evidence_is_not_exposed_in_current_product_view(self) -> None:
        self._complete_baselines()
        self._upsert(
            direction="douban-to-weread",
            item_id="1001",
            title="三体",
            user_plan="weread_not_found",
            requires_user_action=False,
            policy_version=2,
        )

        view = self._view()

        self.assertEqual(view.candidate_total, 4)
        self.assertEqual(view.verified_total, 0)
        self.assertEqual(view.pending_total, 4)
        self.assertEqual(view.items, ())
        self.assertEqual(view.bucket_counts, ())

    def test_unknown_current_user_plan_fails_closed_instead_of_guessing_a_ui_bucket(self) -> None:
        self._complete_baselines()
        self._upsert(
            direction="douban-to-weread",
            item_id="1001",
            title="三体",
            user_plan="future_unknown_plan",
            requires_user_action=True,
            policy_version=3,
        )

        with self.assertRaisesRegex(ValueError, "Unknown persisted user plan"):
            self._view()


if __name__ == "__main__":
    unittest.main()
