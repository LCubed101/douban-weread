from __future__ import annotations

import unittest

from douban_weread.feishu_bot import _is_weread_shelf_command


class WeReadShelfCommandTest(unittest.TestCase):
    def test_common_shelf_commands_are_not_book_titles(self) -> None:
        for text in (
            "加入书架",
            "微信读书加入书架",
            "加入微信读书书架",
            "添加到书架",
            "打开微信读书",
            " 微信读书加入书架！ ",
        ):
            with self.subTest(text=text):
                self.assertTrue(_is_weread_shelf_command(text))

    def test_real_book_title_is_not_intercepted(self) -> None:
        self.assertFalse(_is_weread_shelf_command("你的夏天还好吗？"))
        self.assertFalse(_is_weread_shelf_command("白夜行"))


if __name__ == "__main__":
    unittest.main()
