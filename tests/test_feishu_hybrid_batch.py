from __future__ import annotations

import unittest
from types import SimpleNamespace

from douban_weread.core.models import Edition
from douban_weread.feishu_hybrid_batch import _main_title, _pick_douban_candidate
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

    def test_extracts_main_title_from_chinese_subtitle_separator(self) -> None:
        self.assertEqual(
            _main_title("如何改变世界：社会企业家与新思想的威力"),
            "如何改变世界",
        )

    def test_extracts_main_title_from_ascii_subtitle_separator(self) -> None:
        self.assertEqual(_main_title("主标题: 副标题"), "主标题")

    def test_does_not_fallback_without_real_subtitle(self) -> None:
        self.assertIsNone(_main_title("如何改变世界"))
        self.assertIsNone(_main_title("标题："))

    def test_main_title_search_can_still_match_original_full_title(self) -> None:
        resolution = SimpleNamespace(
            kind=BookInboxResolutionKind.MULTIPLE_CANDIDATES,
            candidates=(
                Edition(
                    title="如何改变世界 : 社会企业家与新思想的威力",
                    publisher="新星出版社",
                    publish_date="2006-04",
                    douban_id="123",
                ),
                Edition(title="如何改变世界经济", douban_id="456"),
            ),
        )
        picked = _pick_douban_candidate(
            resolution,
            "如何改变世界：社会企业家与新思想的威力",
        )
        self.assertEqual(picked.douban_id, "123")


if __name__ == "__main__":
    unittest.main()
