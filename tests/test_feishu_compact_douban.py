from __future__ import annotations

import asyncio
import unittest

from douban_weread.core.models import Edition
from douban_weread.feishu_compact_douban import _compact_base_text, _is_same_work_existing_wish
from douban_weread.inbox_wish import WishFlowKind


class FakeDecision:
    def __init__(self, reason: str = "", target: Edition | None = None) -> None:
        self.reason = reason
        self.target = target


class FakeResult:
    def __init__(self, kind, title: str, reason: str = "") -> None:
        self.kind = kind
        self.title = title
        self.message = "verbose provider message"
        self.decision = FakeDecision(reason, Edition(title=title, douban_id="123"))


class CompactDoubanFlowTest(unittest.TestCase):
    def test_written_result_uses_short_copy(self) -> None:
        result = FakeResult(WishFlowKind.WRITTEN, "商业模式新生代")
        self.assertEqual(_compact_base_text(result), "✅《商业模式新生代》已加入豆瓣想读。")

    def test_already_wish_result_uses_short_copy(self) -> None:
        result = FakeResult(WishFlowKind.ALREADY_WISH, "价值主张设计")
        self.assertEqual(_compact_base_text(result), "✅《价值主张设计》豆瓣已经是想读。")

    def test_same_work_existing_wish_is_not_reported_as_raw_english_error(self) -> None:
        result = FakeResult(
            WishFlowKind.BLOCKED,
            "商业模式新生代",
            "Another edition of the same Work is already marked Want-to-Read. This is an edition mismatch.",
        )
        self.assertTrue(_is_same_work_existing_wish(result))
        self.assertEqual(
            _compact_base_text(result),
            "✅ 豆瓣里已经有《商业模式新生代》同一作品的想读版本，不重复添加。",
        )


if __name__ == "__main__":
    unittest.main()
