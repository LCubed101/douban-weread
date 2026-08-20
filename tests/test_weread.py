from __future__ import annotations

import json
import unittest

from douban_weread.providers.weread.client import (
    WeReadAuthError,
    WeReadClient,
    WeReadProviderError,
    _JsonResponse,
)


class WeReadClientTests(unittest.TestCase):
    def test_missing_api_key_fails_before_network(self) -> None:
        def transport(url: str, headers: dict[str, str], body: bytes) -> _JsonResponse:
            raise AssertionError("transport should not be called")

        client = WeReadClient(api_key="", transport=transport)
        with self.assertRaisesRegex(WeReadAuthError, "required"):
            client.search_books("三体")

    def test_unexpected_api_key_format_fails_before_network(self) -> None:
        def transport(url: str, headers: dict[str, str], body: bytes) -> _JsonResponse:
            raise AssertionError("transport should not be called")

        client = WeReadClient(api_key="not-a-key", transport=transport)
        with self.assertRaisesRegex(WeReadAuthError, "unexpected format"):
            client.search_books("三体")

    def test_search_uses_official_gateway_scope_10_and_parses_scope_17_group(self) -> None:
        def transport(url: str, headers: dict[str, str], body: bytes) -> _JsonResponse:
            self.assertEqual(url, "https://i.weread.qq.com/api/agent/gateway")
            self.assertEqual(headers["Authorization"], "Bearer wrk-test")
            self.assertEqual(headers["Content-Type"], "application/json")
            payload = json.loads(body.decode("utf-8"))
            self.assertEqual(payload["api_name"], "/store/search")
            self.assertEqual(payload["skill_version"], "1.0.4")
            self.assertEqual(payload["keyword"], "白夜行")
            self.assertEqual(payload["scope"], 10)
            self.assertEqual(payload["count"], 5)
            response = {
                "errcode": 0,
                "sid": "abc",
                "hasMore": 0,
                "results": [
                    {
                        "title": "电子书",
                        "scope": 17,
                        "books": [
                            {
                                "searchIdx": 7,
                                "bookInfo": {
                                    "bookId": "12345",
                                    "title": "白夜行",
                                    "author": "[日] 东野圭吾",
                                    "publisher": "南海出版公司",
                                    "deepLink": "weread://reading?bId=12345",
                                    "soldout": 0,
                                },
                            }
                        ],
                    }
                ],
            }
            return _JsonResponse(status=200, body=json.dumps(response, ensure_ascii=False))

        client = WeReadClient(api_key="wrk-test", transport=transport)
        results = client.search_books("白夜行", count=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].book_id, "12345")
        self.assertEqual(results[0].title, "白夜行")
        self.assertEqual(results[0].author, "[日] 东野圭吾")
        self.assertEqual(results[0].publisher, "南海出版公司")
        self.assertFalse(results[0].soldout)
        self.assertEqual(results[0].search_idx, 7)
        self.assertEqual(results[0].source_metadata["group_scope"], 17)

    def test_search_keeps_soldout_as_unavailable_signal(self) -> None:
        response = {
            "errcode": 0,
            "results": [
                {
                    "title": "电子书",
                    "scope": 17,
                    "books": [
                        {
                            "bookInfo": {
                                "bookId": "9",
                                "title": "下架书",
                                "soldout": 1,
                            }
                        }
                    ],
                }
            ],
        }

        client = WeReadClient(
            api_key="wrk-test",
            transport=lambda *_: _JsonResponse(status=200, body=json.dumps(response, ensure_ascii=False)),
        )
        result = client.search_books("下架书")[0]
        self.assertTrue(result.soldout)

    def test_search_deduplicates_book_ids_across_groups(self) -> None:
        book = {"bookInfo": {"bookId": "1", "title": "重复书"}}
        response = {
            "errcode": 0,
            "results": [
                {"title": "电子书", "scope": 17, "books": [book]},
                {"title": "电子书", "scope": 17, "books": [book]},
            ],
        }
        client = WeReadClient(
            api_key="wrk-test",
            transport=lambda *_: _JsonResponse(status=200, body=json.dumps(response, ensure_ascii=False)),
        )
        self.assertEqual(len(client.search_books("重复书")), 1)

    def test_blank_search_skips_network(self) -> None:
        def transport(url: str, headers: dict[str, str], body: bytes) -> _JsonResponse:
            raise AssertionError("transport should not be called")

        client = WeReadClient(api_key="wrk-test", transport=transport)
        self.assertEqual(client.search_books("   "), [])

    def test_get_book_normalizes_to_existing_edition_model(self) -> None:
        response = {
            "errcode": 0,
            "bookId": "3300144307",
            "deepLink": "weread://reading?bId=3300144307",
            "title": "从零构建大模型",
            "author": "[美] 塞巴斯蒂安·拉施卡",
            "translator": "覃立波  冯骁骋  刘乾",
            "cover": "https://cdn.weread.qq.com/example.jpg",
            "publisher": "人民邮电出版社",
            "publishTime": "2025-04-01 00:00:00",
            "isbn": "978-7-115-00000-1",
        }

        def transport(url: str, headers: dict[str, str], body: bytes) -> _JsonResponse:
            payload = json.loads(body.decode("utf-8"))
            self.assertEqual(payload["api_name"], "/book/info")
            self.assertEqual(payload["bookId"], "3300144307")
            return _JsonResponse(status=200, body=json.dumps(response, ensure_ascii=False))

        edition = WeReadClient(api_key="wrk-test", transport=transport).get_book("3300144307")

        self.assertIsNotNone(edition)
        assert edition is not None
        self.assertEqual(edition.weread_id, "3300144307")
        self.assertEqual(edition.title, "从零构建大模型")
        self.assertEqual(edition.authors, ["[美] 塞巴斯蒂安·拉施卡"])
        self.assertEqual(edition.translators, ["覃立波  冯骁骋  刘乾"])
        self.assertEqual(edition.publisher, "人民邮电出版社")
        self.assertEqual(edition.publish_date, "2025-04-01")
        self.assertEqual(edition.isbn, "9787115000001")
        self.assertEqual(edition.cover_url, "https://cdn.weread.qq.com/example.jpg")
        self.assertEqual(edition.source_metadata["provider"], "weread_official")
        self.assertEqual(edition.source_metadata["raw_translator"], "覃立波  冯骁骋  刘乾")

    def test_book_without_title_returns_none(self) -> None:
        client = WeReadClient(
            api_key="wrk-test",
            transport=lambda *_: _JsonResponse(status=200, body='{"errcode":0,"bookId":"1"}'),
        )
        self.assertIsNone(client.get_book("1"))

    def test_nonzero_gateway_error_is_not_not_found(self) -> None:
        client = WeReadClient(
            api_key="wrk-test",
            transport=lambda *_: _JsonResponse(status=200, body='{"errcode":-2003,"errmsg":"参数格式错误"}'),
        )
        with self.assertRaisesRegex(WeReadProviderError, "-2003"):
            client.search_books("三体")

    def test_auth_gateway_error_is_typed(self) -> None:
        client = WeReadClient(
            api_key="wrk-test",
            transport=lambda *_: _JsonResponse(status=200, body='{"errCode":-2012,"errMsg":"登录超时"}'),
        )
        with self.assertRaisesRegex(WeReadAuthError, "authentication failed"):
            client.search_books("三体")

    def test_upgrade_info_fails_closed(self) -> None:
        response = {
            "errcode": 0,
            "upgrade_info": {"message": "please upgrade"},
        }
        client = WeReadClient(
            api_key="wrk-test",
            transport=lambda *_: _JsonResponse(status=200, body=json.dumps(response)),
        )
        with self.assertRaisesRegex(WeReadProviderError, "upgrade required"):
            client.search_books("三体")

    def test_invalid_json_fails_closed(self) -> None:
        client = WeReadClient(
            api_key="wrk-test",
            transport=lambda *_: _JsonResponse(status=200, body="not-json"),
        )
        with self.assertRaisesRegex(WeReadProviderError, "invalid JSON"):
            client.search_books("三体")

    def test_non_2xx_fails_closed(self) -> None:
        client = WeReadClient(
            api_key="wrk-test",
            transport=lambda *_: _JsonResponse(status=503, body="unavailable"),
        )
        with self.assertRaisesRegex(WeReadProviderError, "HTTP 503"):
            client.search_books("三体")


if __name__ == "__main__":
    unittest.main()
