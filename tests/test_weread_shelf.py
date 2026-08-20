from __future__ import annotations

import json
import unittest

from douban_weread.providers.weread import WeReadClient, WeReadProviderError
from douban_weread.providers.weread.client import _JsonResponse


class WeReadShelfProviderTests(unittest.TestCase):
    def test_sync_shelf_uses_official_zero_parameter_endpoint(self) -> None:
        def transport(url: str, headers: dict[str, str], body: bytes) -> _JsonResponse:
            payload = json.loads(body.decode("utf-8"))
            self.assertEqual(payload, {"api_name": "/shelf/sync", "skill_version": "1.0.4"})
            response = {
                "errcode": 0,
                "books": [
                    {
                        "bookId": "230107",
                        "title": "白夜行",
                        "author": "东野圭吾",
                        "deepLink": "https://weread.qq.com/book-detail?type=1&v=test",
                        "category": "小说",
                        "readUpdateTime": 1720000000,
                        "finishReading": 1,
                        "updateTime": 1720000100,
                        "isTop": 0,
                        "secret": 1,
                    }
                ],
                "albums": [{"albumInfo": {"albumId": "a1", "name": "有声书"}}],
                "mp": {"name": "文章收藏"},
                "archive": [{"name": "小说", "bookIds": ["230107"]}],
                "bookCount": 1,
            }
            return _JsonResponse(status=200, body=json.dumps(response, ensure_ascii=False))

        snapshot = WeReadClient(api_key="wrk-test", transport=transport).sync_shelf()

        self.assertEqual(snapshot.book_count, 1)
        self.assertEqual(snapshot.album_count, 1)
        self.assertTrue(snapshot.has_mp)
        self.assertEqual(snapshot.visible_entry_count, 3)
        book = snapshot.books[0]
        self.assertEqual(book.book_id, "230107")
        self.assertEqual(book.title, "白夜行")
        self.assertEqual(book.author, "东野圭吾")
        self.assertTrue(book.finish_reading)
        self.assertTrue(book.secret)
        self.assertEqual(snapshot.archives[0].book_ids, ("230107",))

    def test_albums_and_mp_are_counted_but_not_converted_to_books(self) -> None:
        response = {
            "errcode": 0,
            "books": [],
            "albums": [{"albumInfo": {"albumId": "a1"}}, {"albumInfo": {"albumId": "a2"}}],
            "mp": {"name": "文章收藏"},
        }
        client = WeReadClient(
            api_key="wrk-test",
            transport=lambda *_: _JsonResponse(status=200, body=json.dumps(response, ensure_ascii=False)),
        )
        snapshot = client.sync_shelf()
        self.assertEqual(snapshot.books, ())
        self.assertEqual(snapshot.album_count, 2)
        self.assertEqual(snapshot.visible_entry_count, 3)

    def test_invalid_book_shape_fails_closed(self) -> None:
        response = {"errcode": 0, "books": [{"bookId": "1"}], "albums": []}
        client = WeReadClient(
            api_key="wrk-test",
            transport=lambda *_: _JsonResponse(status=200, body=json.dumps(response)),
        )
        with self.assertRaisesRegex(WeReadProviderError, "missing title"):
            client.sync_shelf()

    def test_duplicate_book_ids_fail_closed(self) -> None:
        response = {
            "errcode": 0,
            "books": [
                {"bookId": "1", "title": "甲"},
                {"bookId": "1", "title": "乙"},
            ],
            "albums": [],
        }
        client = WeReadClient(
            api_key="wrk-test",
            transport=lambda *_: _JsonResponse(status=200, body=json.dumps(response, ensure_ascii=False)),
        )
        with self.assertRaisesRegex(WeReadProviderError, "duplicate bookId 1"):
            client.sync_shelf()


if __name__ == "__main__":
    unittest.main()
