from __future__ import annotations

import unittest

from douban_weread.feishu_result_polish import _douban_status_header


class FeishuResultPolishTests(unittest.TestCase):
    def test_written_wish_is_prominent(self) -> None:
        self.assertEqual(
            _douban_status_header("✅《甘南纪事》已加入豆瓣想读。\n微信读书：找到同一版本。"),
            "✅ 已加入豆瓣想读",
        )

    def test_existing_wish_is_prominent(self) -> None:
        self.assertEqual(
            _douban_status_header("✅《甘南纪事》豆瓣已经是想读。"),
            "✅ 豆瓣已有想读记录",
        )

    def test_plain_weread_result_keeps_existing_header(self) -> None:
        self.assertIsNone(_douban_status_header("微信读书：找到同一版本。"))


if __name__ == "__main__":
    unittest.main()
