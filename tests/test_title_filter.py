from __future__ import annotations

import unittest

from douban_weread.core.models import Edition
from douban_weread.resolver import filter_title_candidates, is_same_work_title


class IsSameWorkTitleTests(unittest.TestCase):
    def test_exact_match(self) -> None:
        self.assertTrue(is_same_work_title("变量", "变量"))

    def test_unrelated_title_is_rejected(self) -> None:
        self.assertFalse(is_same_work_title("变量", "情绪"))

    def test_sequel_numbers_glued_to_prefix_are_rejected(self) -> None:
        self.assertFalse(is_same_work_title("变量", "变量2"))
        self.assertFalse(is_same_work_title("变量", "变量7"))
        self.assertFalse(is_same_work_title("变量", "变量8"))

    def test_sequel_number_separated_by_space_is_still_rejected(self) -> None:
        self.assertFalse(is_same_work_title("变量", "变量 2"))

    def test_genuine_subtitle_after_colon_is_accepted(self) -> None:
        self.assertTrue(is_same_work_title("变量", "变量：如何应对不确定的未来"))

    def test_genuine_annotation_in_brackets_is_accepted(self) -> None:
        self.assertTrue(is_same_work_title("变量", "变量（精装版）"))

    def test_unrelated_title_that_does_not_start_with_query_is_rejected(self) -> None:
        self.assertFalse(is_same_work_title("变量", "这不是变量"))

    def test_case_and_width_insensitive_exact_match(self) -> None:
        self.assertTrue(is_same_work_title("ABC", "ａｂｃ"))


class FilterTitleCandidatesTests(unittest.TestCase):
    def test_filters_out_unrelated_and_sequel_titles(self) -> None:
        candidates = [
            Edition(title="变量", authors=["何帆"], douban_id="1"),
            Edition(title="情绪", authors=["某作者"], douban_id="2"),
            Edition(title="变量2", authors=["何帆"], douban_id="3"),
            Edition(title="变量7", authors=["何帆"], douban_id="4"),
            Edition(title="变量8", authors=["何帆"], douban_id="5"),
            Edition(title="变量：橡树书屋沉思录", authors=["何帆"], douban_id="6"),
        ]
        result = filter_title_candidates("变量", candidates)
        titles = [edition.title for edition in result]
        self.assertEqual(titles, ["变量", "变量：橡树书屋沉思录"])

    def test_fails_closed_when_nothing_survives(self) -> None:
        candidates = [Edition(title="情绪", authors=["某作者"], douban_id="2")]
        self.assertEqual(filter_title_candidates("变量", candidates), [])


if __name__ == "__main__":
    unittest.main()
