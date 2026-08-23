from __future__ import annotations

import unittest
from unittest.mock import patch

from douban_weread.adapters.local_ocr import (
    LocalImageOcr,
    LocalOcrError,
)


class FakeRapidOCR:
    def __call__(self, image_bytes):
        return (
            [
                [[[0, 0], [10, 0], [10, 10], [0, 10]], "我是", 0.99],
                [[[0, 20], [10, 20], [10, 30], [0, 30]], "个体心理学", 0.98],
                [[[0, 40], [10, 40], [10, 50], [0, 50]], "博士", 0.97],
                [
                    [[0, 60], [10, 60], [10, 70], [0, 70]],
                    "ISBN 978-7-5366-9293-0",
                    0.96,
                ],
            ],
            [0.1, 0.1, 0.1],
        )


class LocalImageOcrTests(unittest.IsolatedAsyncioTestCase):
    async def test_recognize_returns_text_lines(self) -> None:
        recognizer = object.__new__(LocalImageOcr)
        recognizer._ocr = FakeRapidOCR()

        lines = await recognizer.recognize(b"fake-image")

        self.assertEqual(
            lines,
            (
                "我是",
                "个体心理学",
                "博士",
                "ISBN 978-7-5366-9293-0",
            ),
        )

    async def test_empty_image_fails_closed(self) -> None:
        recognizer = object.__new__(LocalImageOcr)
        recognizer._ocr = FakeRapidOCR()

        with self.assertRaises(LocalOcrError):
            await recognizer.recognize(b"")


if __name__ == "__main__":
    unittest.main()
