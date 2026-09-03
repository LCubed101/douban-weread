from __future__ import annotations

import unittest

from douban_weread.core.models import Edition
from douban_weread.feishu_ocr_edition_resolution import resolve_ocr_edition


class OcrEditionResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.zhejiang = Edition(
            title="精要主义",
            authors=["格雷戈·麦吉沃恩"],
            publisher="浙江人民出版社",
            publish_date="2016-04",
            isbn="9787213072291",
            douban_id="1",
        )
        self.china_youth = Edition(
            title="精要主义",
            authors=["格雷戈·麦吉沃恩"],
            publisher="中国青年出版社",
            publish_date="2023-09",
            isbn="9787515342733",
            douban_id="2",
        )

    def test_publisher_on_cover_selects_unique_edition(self) -> None:
        selected, evidence = resolve_ocr_edition(
            (self.zhejiang, self.china_youth),
            (
                "《精要主义》",
                "作者：[英] 格雷戈·麦吉沃恩",
                "浙江人民出版社",
            ),
        )
        self.assertIs(selected, self.zhejiang)
        self.assertIn("出版社", evidence)

    def test_publisher_core_matches_when_ocr_drops_suffix(self) -> None:
        selected, evidence = resolve_ocr_edition(
            (self.zhejiang, self.china_youth),
            ("精要主义", "格雷戈麦吉沃恩", "浙江人民"),
        )
        self.assertIs(selected, self.zhejiang)
        self.assertIn("出版社", evidence)

    def test_isbn_is_strongest_evidence(self) -> None:
        selected, evidence = resolve_ocr_edition(
            (self.zhejiang, self.china_youth),
            ("精要主义", "ISBN 978-7-5153-4273-3"),
        )
        self.assertIs(selected, self.china_youth)
        self.assertIn("ISBN", evidence)

    def test_author_only_does_not_guess_edition(self) -> None:
        selected, evidence = resolve_ocr_edition(
            (self.zhejiang, self.china_youth),
            ("精要主义", "作者 格雷戈·麦吉沃恩"),
        )
        self.assertIsNone(selected)
        self.assertEqual(evidence, ())

    def test_year_only_does_not_guess_edition(self) -> None:
        selected, evidence = resolve_ocr_edition(
            (self.zhejiang, self.china_youth),
            ("精要主义", "2023"),
        )
        self.assertIsNone(selected)
        self.assertEqual(evidence, ())

    def test_same_publisher_tie_fails_closed(self) -> None:
        other = Edition(
            title="精要主义",
            publisher="浙江人民出版社",
            publish_date="2018-01",
            douban_id="3",
        )
        selected, evidence = resolve_ocr_edition(
            (self.zhejiang, other),
            ("《精要主义》", "浙江人民出版社"),
        )
        self.assertIsNone(selected)
        self.assertEqual(evidence, ())


if __name__ == "__main__":
    unittest.main()
