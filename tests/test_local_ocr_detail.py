from __future__ import annotations

import unittest

from douban_weread.adapters.local_ocr import LocalImageOcr, _dedupe_lines


class LocalOcrDetailTests(unittest.TestCase):
    def test_parses_standard_rapidocr_output(self) -> None:
        output = (
            [
                [[[0, 0], [1, 0], [1, 1], [0, 1]], "精要主义", 0.98],
                [[[0, 2], [1, 2], [1, 3], [0, 3]], "浙江人民出版社", 0.92],
            ],
            0.12,
        )
        self.assertEqual(
            LocalImageOcr._lines_from_ocr_output(output),
            ("精要主义", "浙江人民出版社"),
        )

    def test_dedupe_keeps_full_image_order(self) -> None:
        self.assertEqual(
            _dedupe_lines(
                [
                    "精要主义",
                    "浙江人民出版社",
                    " 精要主义 ",
                    "浙江人民出版社",
                    "ISBN 9787213072291",
                ]
            ),
            ("精要主义", "浙江人民出版社", "ISBN 9787213072291"),
        )

    def test_empty_or_invalid_ocr_entries_are_ignored(self) -> None:
        output = ([None, [], [None, "  ", 0.1], [None, "出版社", 0.8]], 0.02)
        self.assertEqual(LocalImageOcr._lines_from_ocr_output(output), ("出版社",))


if __name__ == "__main__":
    unittest.main()
