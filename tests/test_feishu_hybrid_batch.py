from __future__ import annotations

import unittest
from types import SimpleNamespace

from douban_weread.core.models import Edition
from douban_weread.feishu_hybrid_batch import _pick_douban_candidate
from douban_weread.inbox import BookInboxResolutionKind


class HybridBatchSelectionTest(unittest.TestCase):
    def test_picks_unique_douban_edition_matching_weread_metadata(self) -> None:
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
        picked = _pick_douban_candidate(resolution, weread_result)
        self.assertEqual(picked.douban_id, "1")

    def test_does_not_guess_when_candidates_are_equally_plausible(self) -> None:
        candidates = (
            Edition(title="测试书", publisher="同一出版社", publish_date="2024-01", douban_id="1"),
            Edition(title="测试书", publisher="同一出版社", publish_date="2024-01", douban_id="2"),
        )
        resolution = SimpleNamespace(
            kind=BookInboxResolutionKind.MULTIPLE_CANDIDATES,
            candidates=candidates,
        )
        weread_result = SimpleNamespace(
            selected_edition=Edition(title="测试书", publisher="同一出版社", publish_date="2024-01")
        )
        self.assertIsNone(_pick_douban_candidate(resolution, weread_result))


if __name__ == "__main__":
    unittest.main()
