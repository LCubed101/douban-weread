from __future__ import annotations

import unittest

from douban_weread.adapters.feishu import (
    build_confirmation_card,
    build_wish_confirmation_card,
)
from douban_weread.core.models import Edition
from douban_weread.inbox import BookInboxConfirmation, request_from_text


class FeishuButtonContrastTest(unittest.TestCase):
    def test_not_this_book_uses_colored_danger_button(self) -> None:
        confirmation = BookInboxConfirmation(
            request=request_from_text("听妈妈的话"),
            candidate=Edition(title="听妈妈的话", douban_id="123"),
        )
        card = build_confirmation_card(confirmation)
        actions = card["elements"][1]["actions"]
        self.assertEqual(actions[0]["type"], "primary")
        self.assertEqual(actions[1]["type"], "danger")
        self.assertEqual(actions[1]["text"]["content"], "不是这本")

    def test_cancel_wish_uses_colored_danger_button(self) -> None:
        card = build_wish_confirmation_card(title="听妈妈的话", subject_id="123")
        actions = card["elements"][1]["actions"]
        self.assertEqual(actions[0]["type"], "primary")
        self.assertEqual(actions[1]["type"], "danger")
        self.assertEqual(actions[1]["text"]["content"], "取消")


if __name__ == "__main__":
    unittest.main()
