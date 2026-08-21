from __future__ import annotations

import unittest

from douban_weread.reconciliation.onboarding import FirstLoginReconciliationPhase
from douban_weread.reconciliation.product_screens import (
    ProductActionKind,
    build_reconciliation_action_inbox,
    build_reconciliation_home_model,
    get_reconciliation_detail,
)
from douban_weread.reconciliation.product_view import (
    ProductBucketCount,
    ProductReconciliationBucket,
    ProductReconciliationItem,
    ProductReconciliationView,
)
from douban_weread.reconciliation.user_plan import UserPlanKind


class ReconciliationProductScreenTests(unittest.TestCase):
    def _item(
        self,
        *,
        direction: str,
        item_id: str,
        title: str,
        bucket: ProductReconciliationBucket,
        plan: UserPlanKind,
        action: bool,
        selected_edition_title: str | None = None,
        weread_book_id: str | None = None,
        shelf_membership: str | None = None,
        match_kind: str | None = None,
        deep_link: str | None = None,
    ) -> ProductReconciliationItem:
        return ProductReconciliationItem(
            direction=direction,
            item_id=item_id,
            title=title,
            bucket=bucket,
            user_plan=plan,
            requires_user_action=action,
            summary=plan.value,
            source_state="do" if direction == "douban-to-weread" else None,
            douban_subject_id=item_id if direction == "douban-to-weread" else None,
            weread_book_id=weread_book_id,
            selected_edition_title=selected_edition_title,
            shelf_membership=shelf_membership,
            match_kind=match_kind,
            weread_reading_state=None,
            weread_progress=None,
            strongest_douban_state=None,
            suggested_douban_state=None,
            deep_link=deep_link,
        )

    def _view(self) -> ProductReconciliationView:
        items = (
            self._item(
                direction="douban-to-weread",
                item_id="2567698",
                title="三体",
                bucket=ProductReconciliationBucket.REVIEW,
                plan=UserPlanKind.REVIEW_EDITION,
                action=True,
                selected_edition_title="三体1",
                weread_book_id="178677",
                shelf_membership="no",
                match_kind="alternative_edition",
                deep_link="https://weread.qq.com/book-detail/example",
            ),
            self._item(
                direction="douban-to-weread",
                item_id="1002",
                title="上流法则",
                bucket=ProductReconciliationBucket.ADD_TO_WEREAD,
                plan=UserPlanKind.ADD_TO_WEREAD_SHELF_EXACT,
                action=True,
                selected_edition_title="上流法则",
                weread_book_id="926379",
                shelf_membership="no",
            ),
            self._item(
                direction="weread-to-douban",
                item_id="7001",
                title="一本微信书",
                bucket=ProductReconciliationBucket.SUGGEST_DOUBAN_STATE,
                plan=UserPlanKind.SUGGEST_DOUBAN_WISH,
                action=True,
                weread_book_id="7001",
                shelf_membership="yes",
            ),
            self._item(
                direction="douban-to-weread",
                item_id="1003",
                title="已对齐",
                bucket=ProductReconciliationBucket.ALIGNED,
                plan=UserPlanKind.ALIGNED,
                action=False,
                weread_book_id="9003",
                shelf_membership="yes",
            ),
        )
        return ProductReconciliationView(
            phase=FirstLoginReconciliationPhase.RECONCILING,
            ready_for_reconciliation=True,
            douban_baseline_complete=True,
            weread_baseline_complete=True,
            missing_baselines=(),
            last_error_kind=None,
            worker_status="partial",
            worker_ticks=1,
            candidate_total=1606,
            verified_total=14,
            pending_total=1592,
            requires_user_action_total=10,
            aligned_total=2,
            no_user_action_total=4,
            bucket_counts=(
                ProductBucketCount(ProductReconciliationBucket.ALIGNED, 2),
                ProductBucketCount(ProductReconciliationBucket.ADD_TO_WEREAD, 3),
                ProductBucketCount(ProductReconciliationBucket.REVIEW, 7),
                ProductBucketCount(ProductReconciliationBucket.WEREAD_NOT_FOUND, 2),
                ProductBucketCount(ProductReconciliationBucket.SUGGEST_DOUBAN_STATE, 1),
            ),
            items=items,
        )

    def test_home_model_exposes_real_progress_and_primary_counts(self) -> None:
        home = build_reconciliation_home_model(self._view())

        self.assertEqual(home.phase, "reconciling")
        self.assertEqual(home.progress_label, "<1%")
        self.assertEqual(home.verified_total, 14)
        self.assertEqual(home.candidate_total, 1606)
        self.assertEqual(home.pending_total, 1592)
        self.assertEqual(home.requires_user_action_total, 10)
        self.assertEqual(home.review_total, 7)
        self.assertEqual(home.add_to_weread_total, 3)
        self.assertEqual(home.suggest_douban_state_total, 1)

    def test_action_inbox_contains_only_actionable_items_in_product_order(self) -> None:
        inbox = build_reconciliation_action_inbox(self._view())

        self.assertEqual(inbox.total, 3)
        self.assertEqual(
            [section.bucket for section in inbox.sections],
            [
                ProductReconciliationBucket.REVIEW,
                ProductReconciliationBucket.ADD_TO_WEREAD,
                ProductReconciliationBucket.SUGGEST_DOUBAN_STATE,
            ],
        )
        self.assertEqual([section.count for section in inbox.sections], [1, 1, 1])
        self.assertTrue(all(item.action_kind is not ProductActionKind.NONE for section in inbox.sections for item in section.items))

    def test_review_edition_detail_preserves_three_body_identity(self) -> None:
        detail = get_reconciliation_detail(
            self._view(),
            direction="douban-to-weread",
            item_id="2567698",
        )

        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail.title, "三体")
        self.assertEqual(detail.selected_edition_title, "三体1")
        self.assertEqual(detail.weread_book_id, "178677")
        self.assertEqual(detail.match_kind, "alternative_edition")
        self.assertEqual(detail.shelf_membership, "no")
        self.assertEqual(detail.action_kind, ProductActionKind.REVIEW_EDITION)
        self.assertTrue(detail.requires_user_action)

    def test_add_to_weread_item_maps_to_open_weread_action(self) -> None:
        inbox = build_reconciliation_action_inbox(self._view())
        add_section = next(
            section
            for section in inbox.sections
            if section.bucket is ProductReconciliationBucket.ADD_TO_WEREAD
        )

        self.assertEqual(add_section.items[0].action_kind, ProductActionKind.OPEN_WEREAD)
        self.assertEqual(add_section.items[0].weread_book_id, "926379")

    def test_unverified_or_absent_item_has_no_detail(self) -> None:
        detail = get_reconciliation_detail(
            self._view(),
            direction="douban-to-weread",
            item_id="not-yet-verified",
        )
        self.assertIsNone(detail)

    def test_actionable_item_without_inbox_bucket_fails_closed(self) -> None:
        view = self._view()
        bad = self._item(
            direction="douban-to-weread",
            item_id="9999",
            title="bad",
            bucket=ProductReconciliationBucket.WEREAD_NOT_FOUND,
            plan=UserPlanKind.WEREAD_NOT_FOUND,
            action=True,
        )
        bad_view = ProductReconciliationView(
            phase=view.phase,
            ready_for_reconciliation=view.ready_for_reconciliation,
            douban_baseline_complete=view.douban_baseline_complete,
            weread_baseline_complete=view.weread_baseline_complete,
            missing_baselines=view.missing_baselines,
            last_error_kind=view.last_error_kind,
            worker_status=view.worker_status,
            worker_ticks=view.worker_ticks,
            candidate_total=view.candidate_total,
            verified_total=view.verified_total,
            pending_total=view.pending_total,
            requires_user_action_total=view.requires_user_action_total,
            aligned_total=view.aligned_total,
            no_user_action_total=view.no_user_action_total,
            bucket_counts=view.bucket_counts,
            items=view.items + (bad,),
        )

        with self.assertRaisesRegex(ValueError, "no inbox section"):
            build_reconciliation_action_inbox(bad_view)


if __name__ == "__main__":
    unittest.main()
