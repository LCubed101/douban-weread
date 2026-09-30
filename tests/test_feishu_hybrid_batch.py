from __future__ import annotations

import unittest
from types import SimpleNamespace

from douban_weread.core.models import Edition
from douban_weread.feishu_hybrid_batch import (
    _compact_batch_card,
    _main_title,
    _pick_douban_candidate,
    _same_work_edition_candidates,
)
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

    def test_multiple_exact_same_title_candidates_are_not_auto_picked(self) -> None:
        # Regression test for BUG 3: real Douban data for the title 甘南纪事
        # returns two entirely different books by different authors that
        # both happen to have the exact same title. Picking exact[0] here
        # would silently write the wrong book (or, best case, an arbitrary
        # one) to a user's Douban 想读 without ever asking. This must fail
        # closed to the batch flow's edition-selection path instead.
        candidates = (
            Edition(title="甘南纪事", authors=["杨显惠"], publisher="花城出版社", publish_date="2011-09", douban_id="6840152"),
            Edition(title="甘南纪事", authors=["郝洪涛"], publisher="甘肃人民出版社", publish_date="2009-01", douban_id="20500085"),
        )
        resolution = SimpleNamespace(
            kind=BookInboxResolutionKind.MULTIPLE_CANDIDATES,
            candidates=candidates,
        )

        self.assertIsNone(_pick_douban_candidate(resolution, "甘南纪事"))
        ambiguous = _same_work_edition_candidates(resolution)
        self.assertEqual(len(ambiguous), 2)
        self.assertEqual({c.douban_id for c in ambiguous}, {"6840152", "20500085"})

    def test_same_work_edition_candidates_is_empty_outside_multiple_candidates(self) -> None:
        confirm_resolution = SimpleNamespace(
            kind=BookInboxResolutionKind.CONFIRM,
            candidates=(Edition(title="独居荒野", douban_id="1"),),
        )
        not_found_resolution = SimpleNamespace(kind=BookInboxResolutionKind.NOT_FOUND, candidates=())
        self.assertEqual(_same_work_edition_candidates(confirm_resolution), ())
        self.assertEqual(_same_work_edition_candidates(not_found_resolution), ())

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


class Mention(SimpleNamespace):
    """Minimal stand-in for a BookMention (just needs .title)."""


class CompactBatchCardAmbiguousEditionTest(unittest.TestCase):
    """Regression coverage for BUG 3: a batch of unique + ambiguous books."""

    def test_unique_books_auto_process_ambiguous_book_gets_a_real_choice(self) -> None:
        from douban_weread.feishu_hybrid_batch import _DoubanBatchOutcome

        mentions = (Mention(title="独居荒野"), Mention(title="甘南纪事"), Mention(title="废墟是一座桥"))
        douban_outcomes = [
            _DoubanBatchOutcome("独居荒野", "written"),
            _DoubanBatchOutcome(
                "甘南纪事",
                "ambiguous",
                "存在多个豆瓣版本，需要你选择",
                candidates=(
                    Edition(title="甘南纪事", authors=["杨显惠"], publisher="花城出版社", publish_date="2011-09", douban_id="6840152"),
                    Edition(title="甘南纪事", authors=["郝洪涛"], publisher="甘肃人民出版社", publish_date="2009-01", douban_id="20500085"),
                ),
            ),
            _DoubanBatchOutcome("废墟是一座桥", "written"),
        ]
        weread_results = [(mention, None, "no lookup in this test") for mention in mentions]

        card = _compact_batch_card(
            mentions=mentions,
            douban_outcomes=douban_outcomes,
            weread_results=weread_results,
            watch_store=None,
        )

        # The two unresolved-ambiguity books did not block the two unique ones.
        self.assertIn("书单处理中", card["header"]["title"]["content"])
        summary_text = card["elements"][0]["content"]
        self.assertIn("想读 2/3", summary_text)
        self.assertIn("待确认版本 1", summary_text)

        # Every button offered for the ambiguous book uses the existing,
        # unmodified confirm_wish action/commit path — never an auto pick.
        buttons = [
            action["value"]
            for element in card["elements"]
            if element.get("tag") == "action"
            for action in element["actions"]
        ]
        self.assertEqual(len(buttons), 2)
        for value in buttons:
            self.assertEqual(value["action"], "confirm_wish")
        self.assertEqual(
            {value["douban_subject_id"] for value in buttons},
            {"6840152", "20500085"},
        )

    def test_no_ambiguous_books_keeps_the_original_processed_header(self) -> None:
        from douban_weread.feishu_hybrid_batch import _DoubanBatchOutcome

        mentions = (Mention(title="独居荒野"),)
        card = _compact_batch_card(
            mentions=mentions,
            douban_outcomes=[_DoubanBatchOutcome("独居荒野", "written")],
            weread_results=[(mentions[0], None, "no lookup in this test")],
            watch_store=None,
        )
        self.assertEqual(card["header"]["title"]["content"], "书单已处理")
        self.assertNotIn("待确认版本", card["elements"][0]["content"])


class HybridBatchDoubanSearchPollutionTest(unittest.TestCase):
    """Regression test for #74 + BUG 3 together: 变量/变量2/变量7/变量8 pollution
    must never turn into fake edition-ambiguity candidates for 变量."""

    def test_sequel_numbered_titles_never_become_edition_candidates(self) -> None:
        from douban_weread.inbox import BookInboxService, request_from_text

        class FakeDouban:
            def search_by_title(self, title: str, *, count: int = 20):
                if title == "变量":
                    return [
                        Edition(title="变量", authors=["何帆"], douban_id="1"),
                        Edition(title="情绪", authors=["某作者"], douban_id="2"),
                        Edition(title="变量2", authors=["何帆"], douban_id="3"),
                        Edition(title="变量7", authors=["何帆"], douban_id="4"),
                        Edition(title="变量8", authors=["何帆"], douban_id="5"),
                    ]
                return []

            def search_by_isbn(self, isbn: str):
                return None

            def get_by_subject_id(self, subject_id: str):
                return None

        service = BookInboxService(FakeDouban(), search_limit=5)
        resolution = service.resolve(request_from_text("变量"))

        # Exactly one real candidate survives #74's filter -> CONFIRM, not
        # MULTIPLE_CANDIDATES, so there is no edition-ambiguity to report at
        # all for this query.
        ambiguous = _same_work_edition_candidates(resolution)
        self.assertEqual(ambiguous, ())
        picked = _pick_douban_candidate(resolution, "变量")
        self.assertIsNotNone(picked)
        self.assertEqual(picked.douban_id, "1")


if __name__ == "__main__":
    unittest.main()
