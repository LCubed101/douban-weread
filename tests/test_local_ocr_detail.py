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

    def test_normal_recognition_is_one_ocr_pass(self) -> None:
        calls: list[object] = []
        adapter = LocalImageOcr.__new__(LocalImageOcr)

        def fake_ocr(value):
            calls.append(value)
            return ([ [None, "精要主义", 0.99] ], 0.01)

        adapter._ocr = fake_ocr
        self.assertEqual(adapter._recognize_sync(b"image"), ("精要主义",))
        self.assertEqual(len(calls), 1)

    def test_detail_recognition_uses_only_detail_regions(self) -> None:
        adapter = LocalImageOcr.__new__(LocalImageOcr)
        calls: list[object] = []
        adapter._ocr = lambda value: calls.append(value) or ([ [None, "浙江人民出版社", 0.9] ], 0.01)
        adapter._book_cover_bottom_regions = lambda _value: ("region-a", "region-b")

        self.assertEqual(
            adapter._recognize_edition_detail_sync(b"image"),
            ("浙江人民出版社",),
        )
        self.assertEqual(calls, ["region-a", "region-b"])

    def test_dedupe_keeps_first_seen_order(self) -> None:
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
