from __future__ import annotations

import unittest

from douban_weread.inbox import BookInboxInputKind, request_from_image_key, request_from_text


class BookInboxTests(unittest.TestCase):
    def test_plain_title_becomes_text_search_request(self) -> None:
        request = request_from_text("  三体  ")
        self.assertEqual(request.input_kind, BookInboxInputKind.TEXT)
        self.assertEqual(request.search_query, "三体")

    def test_douban_subject_url_extracts_exact_subject_id(self) -> None:
        request = request_from_text("https://book.douban.com/subject/2567698/")
        self.assertEqual(request.input_kind, BookInboxInputKind.DOUBAN_URL)
        self.assertEqual(request.douban_subject_id, "2567698")
        self.assertIsNone(request.search_query)

    def test_weread_url_is_preserved_without_guessing_book_identity(self) -> None:
        url = "https://weread.qq.com/book-detail?type=1&v=16b327b052b9f516bffa427"
        request = request_from_text(url)
        self.assertEqual(request.input_kind, BookInboxInputKind.WEREAD_URL)
        self.assertEqual(request.source_url, url)
        self.assertIsNone(request.search_query)

    def test_image_key_is_pending_until_vision_is_connected(self) -> None:
        request = request_from_image_key("img_v3_abc")
        self.assertEqual(request.input_kind, BookInboxInputKind.IMAGE_PENDING)
        self.assertEqual(request.image_key, "img_v3_abc")


if __name__ == "__main__":
    unittest.main()
