from __future__ import annotations

import unittest

from douban_weread.reconciliation.onboarding import FirstLoginReconciliationPhase
from douban_weread.reconciliation.product_view import ProductReconciliationView


class ProductProgressDisplayTests(unittest.TestCase):
    def _view(self, *, candidate_total, verified_total):
        pending_total = None
        if candidate_total is not None and verified_total is not None:
            pending_total = max(0, candidate_total - verified_total)
        return ProductReconciliationView(
            phase=FirstLoginReconciliationPhase.RECONCILING,
            ready_for_reconciliation=candidate_total is not None,
            douban_baseline_complete=candidate_total is not None,
            weread_baseline_complete=candidate_total is not None,
            missing_baselines=() if candidate_total is not None else ("douban", "weread"),
            last_error_kind=None,
            worker_status="partial" if candidate_total is not None else None,
            worker_ticks=1 if candidate_total is not None else None,
            candidate_total=candidate_total,
            verified_total=verified_total,
            pending_total=pending_total,
            requires_user_action_total=0 if candidate_total is not None else None,
            aligned_total=0 if candidate_total is not None else None,
            no_user_action_total=0 if candidate_total is not None else None,
            bucket_counts=(),
            items=(),
        )

    def test_missing_coverage_has_no_progress_display(self) -> None:
        view = self._view(candidate_total=None, verified_total=None)

        self.assertIsNone(view.progress_ratio)
        self.assertIsNone(view.progress_percent)
        self.assertIsNone(view.progress_label)

    def test_started_sub_one_percent_progress_is_not_displayed_as_zero(self) -> None:
        view = self._view(candidate_total=1606, verified_total=14)

        self.assertAlmostEqual(view.progress_ratio or 0, 14 / 1606)
        self.assertEqual(view.progress_percent, 0)
        self.assertEqual(view.progress_label, "<1%")

    def test_empty_candidate_set_is_complete(self) -> None:
        view = self._view(candidate_total=0, verified_total=0)

        self.assertEqual(view.progress_ratio, 1.0)
        self.assertEqual(view.progress_percent, 100)
        self.assertEqual(view.progress_label, "100%")


if __name__ == "__main__":
    unittest.main()
