from __future__ import annotations

import unittest
from types import SimpleNamespace

from douban_weread.alignment import WeReadAlignmentResult
from douban_weread.core.models import Edition, EditionResolution, ReadingIntent, WeReadStatus, Work
from douban_weread.reconciliation.policy import (
    CrossPlatformStateAction,
    CrossPlatformStateDecision,
    ReadingState,
    WeReadReadingState,
)
from douban_weread.reconciliation.shelf_batch import (
    DOUBAN_TO_WEREAD,
    WEREAD_TO_DOUBAN,
    BatchItemResult,
)
from douban_weread.reconciliation.user_plan import UserPlanKind, user_plan_for_batch_item
from douban_weread.resolver import EditionMatchResult, MatchKind


class UserPlanTests(unittest.TestCase):
    def _weread_to_douban_item(
        self,
        action: CrossPlatformStateAction,
        *,
        exact: bool = True,
    ) -> BatchItemResult:
        suggested = {
            CrossPlatformStateAction.SUGGEST_WISH: ReadingState.WISH,
            CrossPlatformStateAction.SUGGEST_READING: ReadingState.READING,
            CrossPlatformStateAction.SUGGEST_READ: ReadingState.READ,
            CrossPlatformStateAction.ASK_REREAD: ReadingState.READ,
        }.get(action, ReadingState.WISH)
        decision = CrossPlatformStateDecision(
            weread_state=WeReadReadingState.UNREAD,
            douban_state=ReadingState.NONE,
            suggested_douban_state=suggested,
            action=action,
            same_work_verified=action is not CrossPlatformStateAction.REVIEW_IDENTITY,
            exact_edition_verified=exact,
            safe_to_auto_apply=False,
            requires_user_decision=action
            not in {CrossPlatformStateAction.NOOP_ALIGNED, CrossPlatformStateAction.KEEP_HIGHER_DOUBAN_STATE},
            reason="test",
        )
        return BatchItemResult(
            direction=WEREAD_TO_DOUBAN,
            item_id="10",
            title="测试书",
            outcome=action.value,
            shelf_verification=SimpleNamespace(decision=decision),
        )

    def _douban_to_weread_item(
        self,
        status: WeReadStatus,
        *,
        on_shelf: bool = False,
        material_difference: bool = False,
    ) -> BatchItemResult:
        source = Edition(title="测试书", authors=["作者"], isbn="9780000000001", douban_id="100")
        selected = Edition(title="测试书", authors=["作者"], isbn="9780000000001", weread_id="900")
        intent = ReadingIntent(work=Work(canonical_title="测试书", authors=["作者"]), source_edition=source)
        match = None
        if status is WeReadStatus.AVAILABLE_EXACT:
            intent.selected_edition = selected
            intent.resolution = EditionResolution.EXACT_MATCH
            intent.source_url = "https://weread.example/book/900"
            match = EditionMatchResult(
                candidate=selected,
                score=1.0,
                kind=MatchKind.EXACT_EDITION,
                same_work=True,
                exact_edition=True,
                requires_confirmation=False,
                safe_to_auto_apply=True,
            )
        elif status is WeReadStatus.AVAILABLE_ALTERNATIVE:
            selected.isbn = "9780000000002"
            intent.selected_edition = selected
            intent.resolution = EditionResolution.ALTERNATIVE_EDITION
            intent.source_url = "https://weread.example/book/900"
            match = EditionMatchResult(
                candidate=selected,
                score=0.9,
                kind=MatchKind.ALTERNATIVE_EDITION,
                same_work=True,
                exact_edition=False,
                requires_confirmation=material_difference,
                safe_to_auto_apply=False,
            )
        elif status is WeReadStatus.UNAVAILABLE:
            intent.selected_edition = selected
            intent.resolution = EditionResolution.EXACT_MATCH
            intent.source_url = "https://weread.example/book/900"
        intent.weread_status = status
        alignment = WeReadAlignmentResult(intent=intent, match=match, examined_candidates=1)
        return BatchItemResult(
            direction=DOUBAN_TO_WEREAD,
            item_id="100",
            title="测试书",
            outcome=status.value,
            source_state="wish",
            catalog_alignment=alignment,
            selected_shelf_book=SimpleNamespace(book_id="900") if on_shelf else None,
        )

    def test_exact_catalog_match_not_on_shelf_becomes_add_exact(self) -> None:
        plan = user_plan_for_batch_item(self._douban_to_weread_item(WeReadStatus.AVAILABLE_EXACT))
        self.assertEqual(plan.kind, UserPlanKind.ADD_TO_WEREAD_SHELF_EXACT)
        self.assertTrue(plan.requires_user_action)
        self.assertEqual(plan.deep_link, "https://weread.example/book/900")

    def test_exact_catalog_match_already_on_shelf_is_aligned(self) -> None:
        plan = user_plan_for_batch_item(
            self._douban_to_weread_item(WeReadStatus.AVAILABLE_EXACT, on_shelf=True)
        )
        self.assertEqual(plan.kind, UserPlanKind.ALIGNED)
        self.assertFalse(plan.requires_user_action)

    def test_alternative_catalog_match_not_on_shelf_becomes_add_alternative(self) -> None:
        plan = user_plan_for_batch_item(self._douban_to_weread_item(WeReadStatus.AVAILABLE_ALTERNATIVE))
        self.assertEqual(plan.kind, UserPlanKind.ADD_TO_WEREAD_SHELF_ALTERNATIVE)

    def test_material_alternative_requires_edition_review(self) -> None:
        plan = user_plan_for_batch_item(
            self._douban_to_weread_item(
                WeReadStatus.AVAILABLE_ALTERNATIVE,
                material_difference=True,
            )
        )
        self.assertEqual(plan.kind, UserPlanKind.REVIEW_EDITION)
        self.assertTrue(plan.requires_user_action)

    def test_unavailable_catalog_is_not_an_add_action(self) -> None:
        plan = user_plan_for_batch_item(self._douban_to_weread_item(WeReadStatus.UNAVAILABLE))
        self.assertEqual(plan.kind, UserPlanKind.WEREAD_UNAVAILABLE)
        self.assertFalse(plan.requires_user_action)

    def test_bounded_not_found_is_preserved(self) -> None:
        plan = user_plan_for_batch_item(self._douban_to_weread_item(WeReadStatus.NOT_FOUND))
        self.assertEqual(plan.kind, UserPlanKind.WEREAD_NOT_FOUND)
        self.assertIn("bounded", plan.summary)

    def test_exact_unread_suggestion_becomes_suggest_douban_wish(self) -> None:
        plan = user_plan_for_batch_item(
            self._weread_to_douban_item(CrossPlatformStateAction.SUGGEST_WISH)
        )
        self.assertEqual(plan.kind, UserPlanKind.SUGGEST_DOUBAN_WISH)
        self.assertTrue(plan.requires_user_action)

    def test_non_exact_state_suggestion_becomes_edition_review(self) -> None:
        plan = user_plan_for_batch_item(
            self._weread_to_douban_item(CrossPlatformStateAction.SUGGEST_READING, exact=False)
        )
        self.assertEqual(plan.kind, UserPlanKind.REVIEW_EDITION)

    def test_reread_is_explicit_review(self) -> None:
        plan = user_plan_for_batch_item(
            self._weread_to_douban_item(CrossPlatformStateAction.ASK_REREAD)
        )
        self.assertEqual(plan.kind, UserPlanKind.REVIEW_REREAD)

    def test_higher_douban_history_is_kept_without_action(self) -> None:
        plan = user_plan_for_batch_item(
            self._weread_to_douban_item(CrossPlatformStateAction.KEEP_HIGHER_DOUBAN_STATE)
        )
        self.assertEqual(plan.kind, UserPlanKind.KEEP_DOUBAN_HISTORY)
        self.assertFalse(plan.requires_user_action)

    def test_noop_is_aligned(self) -> None:
        plan = user_plan_for_batch_item(
            self._weread_to_douban_item(CrossPlatformStateAction.NOOP_ALIGNED)
        )
        self.assertEqual(plan.kind, UserPlanKind.ALIGNED)

    def test_unverified_identity_is_review(self) -> None:
        plan = user_plan_for_batch_item(
            self._weread_to_douban_item(CrossPlatformStateAction.REVIEW_IDENTITY, exact=False)
        )
        self.assertEqual(plan.kind, UserPlanKind.REVIEW_IDENTITY)


if __name__ == "__main__":
    unittest.main()
