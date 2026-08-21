from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from douban_weread.reconciliation import (
    FirstLoginReconciliationPhase,
    ProductReconciliationBucket,
    ProductReconciliationItem,
    ProductReconciliationView,
    UserPlanKind,
)
from douban_weread.web_ui import render_detail, render_home, render_inbox, run


class WebUiTests(unittest.TestCase):
    def _view(self) -> ProductReconciliationView:
        items = (
            ProductReconciliationItem(
                direction="douban-to-weread",
                item_id="2567698",
                title="三体",
                bucket=ProductReconciliationBucket.REVIEW,
                user_plan=UserPlanKind.REVIEW_EDITION,
                requires_user_action=True,
                summary="same work, alternative edition",
                source_state="do",
                douban_subject_id="2567698",
                weread_book_id="178677",
                selected_edition_title="三体1",
                shelf_membership="no",
                match_kind="alternative_edition",
                weread_reading_state=None,
                weread_progress=None,
                strongest_douban_state=None,
                suggested_douban_state=None,
                deep_link="https://weread.qq.com/book-detail?type=1&v=example",
            ),
            ProductReconciliationItem(
                direction="douban-to-weread",
                item_id="1002",
                title="上流法则",
                bucket=ProductReconciliationBucket.ADD_TO_WEREAD,
                user_plan=UserPlanKind.ADD_TO_WEREAD_SHELF_EXACT,
                requires_user_action=True,
                summary="available exact",
                source_state="wish",
                douban_subject_id="1002",
                weread_book_id="926379",
                selected_edition_title="上流法则",
                shelf_membership="no",
                match_kind="exact_edition",
                weread_reading_state=None,
                weread_progress=None,
                strongest_douban_state=None,
                suggested_douban_state=None,
                deep_link="https://weread.qq.com/book-detail?type=1&v=exact",
            ),
            ProductReconciliationItem(
                direction="weread-to-douban",
                item_id="7001",
                title="县中的孩子",
                bucket=ProductReconciliationBucket.ALIGNED,
                user_plan=UserPlanKind.ALIGNED,
                requires_user_action=False,
                summary="aligned",
                source_state=None,
                douban_subject_id="3001",
                weread_book_id="7001",
                selected_edition_title="县中的孩子：中国县域教育生态",
                shelf_membership="yes",
                match_kind="alternative_edition",
                weread_reading_state="unread",
                weread_progress=0,
                strongest_douban_state="wish",
                suggested_douban_state=None,
                deep_link=None,
            ),
            ProductReconciliationItem(
                direction="douban-to-weread",
                item_id="1004",
                title="Watching the English",
                bucket=ProductReconciliationBucket.WEREAD_NOT_FOUND,
                user_plan=UserPlanKind.WEREAD_NOT_FOUND,
                requires_user_action=False,
                summary="not found within bounded search",
                source_state="do",
                douban_subject_id="1004",
                weread_book_id=None,
                selected_edition_title=None,
                shelf_membership="unresolved",
                match_kind=None,
                weread_reading_state=None,
                weread_progress=None,
                strongest_douban_state=None,
                suggested_douban_state=None,
                deep_link=None,
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
            requires_user_action_total=2,
            aligned_total=1,
            no_user_action_total=2,
            bucket_counts=(),
            items=items,
        )

    def test_home_renders_real_progress_without_zero_percent(self) -> None:
        body = render_home(self._view())

        self.assertIn("14 / 1606", body)
        self.assertIn("&lt;1%", body)
        self.assertIn("1592 本还在比较中", body)
        self.assertIn("查看待处理 2", body)

    def test_inbox_only_renders_actionable_sections(self) -> None:
        body = render_inbox(self._view())

        self.assertIn("待处理 2", body)
        self.assertIn("需要确认", body)
        self.assertIn("可在微信读书打开", body)
        self.assertIn("三体1", body)
        self.assertIn("上流法则", body)
        self.assertNotIn("Watching the English", body)
        self.assertNotIn("县中的孩子", body)

    def test_three_body_detail_preserves_alternative_edition_safety_copy(self) -> None:
        status, body = render_detail(
            self._view(),
            direction="douban-to-weread",
            item_id="2567698",
        )

        self.assertEqual(status, 200)
        self.assertIn("确认版本", body)
        self.assertIn("三体1", body)
        self.assertIn("alternative_edition", body)
        self.assertIn("178677", body)
        self.assertIn("当前书架：未加入", body)
        self.assertIn("不会把它当成同一个版本自动处理", body)
        self.assertIn("在微信读书查看", body)

    def test_unverified_or_absent_detail_returns_404(self) -> None:
        status, body = render_detail(
            self._view(),
            direction="douban-to-weread",
            item_id="999999",
        )

        self.assertEqual(status, 404)
        self.assertIn("还没有可展示的验证结果", body)

    def test_user_controlled_titles_are_html_escaped(self) -> None:
        view = self._view()
        unsafe = ProductReconciliationItem(
            direction="douban-to-weread",
            item_id="1010",
            title='<script>alert("x")</script>',
            bucket=ProductReconciliationBucket.REVIEW,
            user_plan=UserPlanKind.REVIEW_IDENTITY,
            requires_user_action=True,
            summary="review",
            source_state="wish",
            douban_subject_id="1010",
            weread_book_id="9010",
            selected_edition_title="<b>edition</b>",
            shelf_membership="no",
            match_kind="ambiguous",
            weread_reading_state=None,
            weread_progress=None,
            strongest_douban_state=None,
            suggested_douban_state=None,
            deep_link=None,
        )
        view = ProductReconciliationView(
            phase=view.phase,
            ready_for_reconciliation=view.ready_for_reconciliation,
            douban_baseline_complete=True,
            weread_baseline_complete=True,
            missing_baselines=(),
            last_error_kind=None,
            worker_status="partial",
            worker_ticks=1,
            candidate_total=1607,
            verified_total=15,
            pending_total=1592,
            requires_user_action_total=3,
            aligned_total=1,
            no_user_action_total=2,
            bucket_counts=(),
            items=view.items + (unsafe,),
        )

        body = render_inbox(view)
        self.assertNotIn('<script>alert("x")</script>', body)
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", body)
        self.assertIn("&lt;b&gt;edition&lt;/b&gt;", body)

    def test_v1_refuses_non_loopback_bind(self) -> None:
        stdout = io.StringIO()
        with patch("douban_weread.web_ui.ThreadingHTTPServer") as server:
            code = run(["--host", "0.0.0.0", "--no-open"], stdout=stdout)

        self.assertEqual(code, 2)
        self.assertIn("Refusing to bind beyond 127.0.0.1", stdout.getvalue())
        server.assert_not_called()


if __name__ == "__main__":
    unittest.main()
