from __future__ import annotations

import unittest

from douban_weread.feishu_bot import _processing_card


class FeishuCardAckStateTest(unittest.TestCase):
    def test_confirm_book_processing_card_removes_buttons(self) -> None:
        card = _processing_card("confirm_book")

        self.assertEqual(card["header"]["template"], "grey")
        self.assertEqual(card["header"]["title"]["content"], "已收到操作")
        self.assertNotIn("action", {element.get("tag") for element in card["elements"]})
        self.assertIn("确认这本", card["elements"][0]["content"])

    def test_confirm_wish_processing_card_describes_write(self) -> None:
        card = _processing_card("confirm_wish")

        self.assertEqual(card["header"]["template"], "grey")
        self.assertIn("加入豆瓣想读", card["elements"][0]["content"])
        self.assertIn("写后验证", card["elements"][0]["content"])


if __name__ == "__main__":
    unittest.main()
