from __future__ import annotations

import unittest

from douban_weread import feishu_bot as base
from douban_weread.feishu_bot_context import (
    _callback_card,
    _enhance_outbound_message,
)


class FeishuUiEnhancementTest(unittest.TestCase):
    def test_processing_card_uses_callback_raw_wrapper(self) -> None:
        wrapped = _callback_card(base._processing_card("confirm_book"))
        self.assertEqual(wrapped["type"], "raw")
        card = wrapped["data"]
        self.assertEqual(card["header"]["template"], "grey")
        self.assertEqual(card["header"]["title"]["content"], "已收到操作")
        self.assertNotIn("actions", str(card))

    def test_weread_text_link_becomes_primary_button_card(self) -> None:
        message = {
            "text": (
                "豆瓣已经是想读。\n\n"
                "微信读书：找到同一版本。\n"
                "测试书 · 测试出版社\n"
                "可读链接：https://weread.qq.com/web/bookDetail/test123"
            )
        }
        enhanced = _enhance_outbound_message(message)
        card = enhanced["card"]
        self.assertEqual(card["header"]["template"], "green")
        button = card["elements"][1]["actions"][0]
        self.assertEqual(button["text"]["content"], "打开微信读书")
        self.assertEqual(button["type"], "primary")
        self.assertEqual(button["url"], "https://weread.qq.com/web/bookDetail/test123")
        self.assertNotIn("可读链接：", card["elements"][0]["content"])

    def test_non_weread_text_is_unchanged(self) -> None:
        message = {"text": "没有找到对应版本。"}
        self.assertIs(_enhance_outbound_message(message), message)


if __name__ == "__main__":
    unittest.main()
