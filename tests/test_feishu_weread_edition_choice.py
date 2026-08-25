from __future__ import annotations

import unittest
from types import SimpleNamespace

from douban_weread.core.models import Edition
from douban_weread.feishu_bot import (
    _candidate_list_text,
    _format_weread_candidate_status,
    _is_reselect_edition_command,
)
from douban_weread.inbox_weread import WeReadLookupKind


class WeReadAwareEditionChoiceTest(unittest.TestCase):
    def test_exact_match_is_highlighted_before_douban_choice(self) -> None:
        result = SimpleNamespace(kind=WeReadLookupKind.EXACT, selected_edition=None)
        self.assertEqual(
            _format_weread_candidate_status(result),
            "✅ 微信读书：有同版可读",
        )

    def test_alternative_match_names_the_weread_edition(self) -> None:
        selected = Edition(
            title="你的夏天还好吗？",
            publisher="人民文学出版社",
            publish_date="2016",
        )
        result = SimpleNamespace(
            kind=WeReadLookupKind.ALTERNATIVE,
            selected_edition=selected,
        )
        status = _format_weread_candidate_status(result)
        self.assertIn("🟡 微信读书：有同一作品的其他版本", status)
        self.assertIn("人民文学出版社", status)
        self.assertIn("2016", status)

    def test_candidate_list_shows_weread_status_next_to_each_douban_edition(self) -> None:
        candidates = (
            Edition(title="书名", publisher="甲出版社", publish_date="2016", isbn="111"),
            Edition(title="书名", publisher="乙出版社", publish_date="2022", isbn="222"),
        )
        text = _candidate_list_text(
            candidates,
            weread_statuses=(
                "✅ 微信读书：有同版可读",
                "🟡 微信读书：有同一作品的其他版本",
            ),
        )
        self.assertIn("1. 书名｜甲出版社 · 2016 · 111", text)
        self.assertIn("✅ 微信读书：有同版可读", text)
        self.assertIn("2. 书名｜乙出版社 · 2022 · 222", text)
        self.assertIn("🟡 微信读书：有同一作品的其他版本", text)
        self.assertIn("重新选择豆瓣版本", text)

    def test_reselect_commands_are_not_treated_as_book_titles(self) -> None:
        for text in (
            "重新选择",
            "重新选择版本",
            "重新选择豆瓣版本",
            " 换一个豆瓣版本！ ",
        ):
            with self.subTest(text=text):
                self.assertTrue(_is_reselect_edition_command(text))

        self.assertFalse(_is_reselect_edition_command("白夜行"))


if __name__ == "__main__":
    unittest.main()
