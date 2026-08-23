from __future__ import annotations

import unittest

from douban_weread.inbox_ocr import extract_book_hint


class InboxOcrTests(unittest.TestCase):
    def test_isbn_is_preferred_over_title_text(self) -> None:
        hint = extract_book_hint([
            "三体",
            "重庆出版社",
            "ISBN：978-7-5366-9293-0",
        ])

        self.assertEqual(hint.isbn, "9787536692930")
        self.assertIsNone(hint.title)

    def test_book_title_quotes_are_preferred(self) -> None:
        hint = extract_book_hint([
            "今天读完《听妈妈的话》",
            "这是一些普通文章文字",
        ])

        self.assertEqual(hint.title, "听妈妈的话")

    def test_short_cover_title_beats_long_prose(self) -> None:
        hint = extract_book_hint([
            "这是一本关于女性经验与家庭关系的长篇文章内容",
            "听妈妈的话",
            "收藏 评论 转发",
        ])

        self.assertEqual(hint.title, "听妈妈的话")

    def test_ui_only_text_has_no_book_hint(self) -> None:
        hint = extract_book_hint([
            "微信",
            "回复",
            "点赞",
            "评论",
            "2026",
        ])

        self.assertFalse(hint.usable)

    def test_fragmented_cover_text_does_not_guess_title(self) -> None:
        hint = extract_book_hint(
            (
                "辅是",
                "有女孩都值得",
                "家！",
                "热爱是一种能力带",
                "我们去往住何地",
                "吴海云",
                "方！",
                "书展首发",
                "博",
                "人",
            )
        )

        self.assertIsNone(hint.isbn)
        self.assertIsNone(hint.title)
        self.assertFalse(hint.usable)


if __name__ == "__main__":
    unittest.main()
