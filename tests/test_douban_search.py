from __future__ import annotations

import unittest

from douban_weread.providers.douban.search import (
    DoubanBookSearchClient,
    DoubanProviderError,
    _JsonResponse,
)


class DoubanBookSearchClientTests(unittest.TestCase):
    def test_search_by_title_returns_candidates(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> _JsonResponse:
            self.assertIn("q=%E7%99%BE%E5%B9%B4%E5%AD%A4%E7%8B%AC", url)
            self.assertEqual(headers["Accept"], "application/json")
            return _JsonResponse(
                status=200,
                payload={
                    "books": [
                        {
                            "id": "6082808",
                            "title": "百年孤独",
                            "author": ["[哥伦比亚] 加西亚·马尔克斯"],
                            "translator": ["范晔"],
                            "publisher": "南海出版公司",
                            "pubdate": "2011-6",
                            "isbn13": "9787544253994",
                            "images": {"large": "https://example.com/cover.jpg"},
                        },
                        {
                            "id": "9999999",
                            "title": "百年孤独",
                            "author": ["加西亚·马尔克斯"],
                            "publisher": "另一出版社",
                            "pubdate": "2024",
                            "isbn13": "9780000000000",
                        },
                    ]
                },
            )

        client = DoubanBookSearchClient(api_key="test-key", transport=transport)
        results = client.search_by_title("百年孤独")

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].douban_id, "6082808")
        self.assertEqual(results[0].translator, "范晔")
        self.assertEqual(results[0].isbn, "9787544253994")

    def test_search_by_isbn_returns_exact_edition(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> _JsonResponse:
            self.assertIn("/isbn/9787544253994", url)
            return _JsonResponse(
                status=200,
                payload={
                    "id": "6082808",
                    "title": "百年孤独",
                    "author": ["加西亚·马尔克斯"],
                    "translator": ["范晔"],
                    "publisher": "南海出版公司",
                    "pubdate": "2011-6",
                    "isbn13": "978-7-5442-5399-4",
                },
            )

        client = DoubanBookSearchClient(transport=transport)
        result = client.search_by_isbn("978-7-5442-5399-4")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.isbn, "9787544253994")
        self.assertEqual(result.douban_id, "6082808")

    def test_unknown_isbn_returns_none_on_404(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> _JsonResponse:
            return _JsonResponse(status=404, payload={})

        client = DoubanBookSearchClient(transport=transport)
        self.assertIsNone(client.search_by_isbn("9780000000000"))

    def test_invalid_search_payload_raises_provider_error(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> _JsonResponse:
            return _JsonResponse(status=200, payload={"books": "invalid"})

        client = DoubanBookSearchClient(transport=transport)
        with self.assertRaises(DoubanProviderError):
            client.search_by_title("test")

    def test_blank_queries_do_not_call_transport(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> _JsonResponse:
            raise AssertionError("transport should not be called")

        client = DoubanBookSearchClient(transport=transport)
        self.assertEqual(client.search_by_title("   "), [])
        self.assertIsNone(client.search_by_isbn("---"))


if __name__ == "__main__":
    unittest.main()
