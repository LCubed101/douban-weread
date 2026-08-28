from __future__ import annotations

import unittest
from types import SimpleNamespace

from douban_weread.core.models import Edition
from douban_weread.feishu_hybrid_batch import _pick_douban_candidate
from douban_weread.inbox import BookInboxResolutionKind


class HybridBatchSelectionTest(unittest.TestCase):
    def test_uses_exact_title_douban_even_without_weread(self) -> None:
        candidates = (
            Edition(title="深度工作", publisher="甲出版社", publish_date="2017-01", douban_id="1"),
            Edition(title="深度工作（新版）", publisher="乙出版社", publish_date="2024-01", douban_id="2"),
        )
        resolution = SimpleNamespace(
            kind=BookInboxResolutionKind.MULTIPLE_CANDIDATES,
            candidates=candidates,
        )
        picked = _pick_douban_candidate(resolution, "深度工作")
        self.assertEqual(picked.douban_id, "1")

    def test_weread_breaks_tie_between_exact_title_editions(self) -> None:
        candidates = (
            Edition(
                title="商业模式新生代",
                publisher="机械工业出版社",
                publish_date="2011-08",
                douban_id="1",
            ),
            Edition(
                title="商业模式新生代",
                publisher="机械工业出版社",
                publish_date="2016-10",
                douban_id="2",
            ),
        )
        resolution = SimpleNamespace(
            kind=BookInboxResolutionKind.MULTIPLE_CANDIDATES,
            candidates=candidates,
        )
        weread_result = SimpleNamespace(
            selected_edition=Edition(
                title="商业模式新生代",
                publisher="机械工业出版社",
                publish_date="2011-08-09",
            )
        )
        picked = _pick_douban_candidate(resolution, "商业模式新生代", weread_result)
        self.assertEqual(picked.douban_id, "1")

    def test_fuzzy_only_candidates_still_fail_closed(self) -> None:
        candidates = (
            Edition(title="测试书：新版", douban_id="1"),
            Edition(title="测试书方法论", douban_id="2"),
        )
        resolution = SimpleNamespace(
            kind=BookInboxResolutionKind.MULTIPLE_CANDIDATES,
            candidates=candidates,
        )
        self.assertIsNone(_pick_douban_candidate(resolution, "测试书"))


if __name__ == "__main__":
    unittest.main()
