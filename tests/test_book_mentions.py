from __future__ import annotations

import unittest

from douban_weread.core.book_mentions import extract_book_mentions


class BookMentionExtractorTest(unittest.TestCase):
    def test_extracts_explicit_book_titles_and_deduplicates(self) -> None:
        text = (
            "推荐《价值主张设计》和《商业模式新生代》。"
            "后面又提到《价值主张设计》，以及《U型理论》。"
        )
        mentions = extract_book_mentions(text)
        self.assertEqual(
            [mention.title for mention in mentions],
            ["价值主张设计", "商业模式新生代", "U型理论"],
        )

    def test_recovers_ocr_line_break_inside_book_marks(self) -> None:
        text = "推荐《价值主张设计》，以及《商业模式\n新生代》。"
        mentions = extract_book_mentions(text)
        self.assertEqual(
            [mention.title for mention in mentions],
            ["价值主张设计", "商业模式 新生代"],
        )

    def test_accepts_ocr_angle_book_marks(self) -> None:
        text = "OCR 结果：〈价值主张设计〉和《商业模式新生代》。"
        mentions = extract_book_mentions(text)
        self.assertEqual(
            [mention.title for mention in mentions],
            ["价值主张设计", "商业模式新生代"],
        )

    def test_ignores_generic_corner_quotes_from_flomo_prose(self) -> None:
        text = "你正在建立「暂停」机制与「系统」，同时推荐《深度工作》。"
        mentions = extract_book_mentions(text)
        self.assertEqual([mention.title for mention in mentions], ["深度工作"])

    def test_ambiguous_plain_prose_fails_closed(self) -> None:
        self.assertEqual(extract_book_mentions("我最近想读深度工作和专注"), ())


if __name__ == "__main__":
    unittest.main()
