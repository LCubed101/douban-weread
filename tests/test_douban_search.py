from __future__ import annotations

import unittest

from douban_weread.providers.douban.search import (
    DoubanBookSearchClient,
    DoubanProviderError,
    _TextResponse,
)


SEARCH_HTML = """
<html><body>
<a href="https://book.douban.com/subject/6082808/">百年孤独</a>
<a href="https://book.douban.com/subject/27107109/">百年孤独</a>
<a href="https://book.douban.com/subject/6082808/">duplicate</a>
</body></html>
"""

SUBJECT_6082808_HTML = """
<html><body>
<h1><span property="v:itemreviewed">百年孤独</span></h1>
<div id="mainpic"><img src="https://example.com/6082808.jpg"></div>
<div id="info">
<span class="pl">作者:</span> <a>[哥伦比亚] 加西亚·马尔克斯</a><br/>
<span class="pl">出版社:</span> 南海出版公司<br/>
<span class="pl">译者:</span> <a>范晔</a><br/>
<span class="pl">出版年:</span> 2011-6<br/>
<span class="pl">ISBN:</span> 9787544253994<br/>
</div>
</body></html>
"""

SUBJECT_27107109_HTML = """
<html><body>
<h1><span property="v:itemreviewed">百年孤独</span></h1>
<div id="info">
<span class="pl">作者:</span> 加西亚·马尔克斯<br/>
<span class="pl">出版社:</span> 南海出版公司<br/>
<span class="pl">译者:</span> 范晔<br/>
<span class="pl">出版年:</span> 2017-8<br/>
<span class="pl">ISBN:</span> 9787544291170<br/>
</div>
</body></html>
"""


class DoubanBookSearchClientTests(unittest.TestCase):
    def test_search_by_title_fetches_and_normalizes_subject_pages(self) -> None:
        requested: list[str] = []

        def transport(url: str, headers: dict[str, str]) -> _TextResponse:
            requested.append(url)
            self.assertIn("Mozilla/5.0", headers["User-Agent"])
            self.assertEqual(headers["Accept"], "text/html,application/xhtml+xml")
            if "/subject_search?" in url:
                self.assertIn("search_text=%E7%99%BE%E5%B9%B4%E5%AD%A4%E7%8B%AC", url)
                self.assertIn("cat=1001", url)
                return _TextResponse(status=200, body=SEARCH_HTML)
            if "/subject/6082808/" in url:
                return _TextResponse(status=200, body=SUBJECT_6082808_HTML)
            if "/subject/27107109/" in url:
                return _TextResponse(status=200, body=SUBJECT_27107109_HTML)
            raise AssertionError(f"unexpected URL: {url}")

        client = DoubanBookSearchClient(transport=transport)
        results = client.search_by_title("百年孤独", count=10)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].title, "百年孤独")
        self.assertEqual(results[0].douban_id, "6082808")
        self.assertEqual(results[0].authors, ["[哥伦比亚] 加西亚·马尔克斯"])
        self.assertEqual(results[0].translators, ["范晔"])
        self.assertEqual(results[0].publisher, "南海出版公司")
        self.assertEqual(results[0].publish_date, "2011-06")
        self.assertEqual(results[0].isbn, "9787544253994")
        self.assertEqual(results[0].cover_url, "https://example.com/6082808.jpg")
        self.assertEqual(results[0].source_metadata["provider"], "douban_web")
        self.assertEqual(results[1].publish_date, "2017-08")
        self.assertEqual(results[1].isbn, "9787544291170")
        self.assertEqual(len([url for url in requested if "/subject/6082808/" in url]), 1)

    def test_search_by_isbn_verifies_exact_subject_isbn(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> _TextResponse:
            if "/subject_search?" in url:
                self.assertIn("search_text=9787544253994", url)
                return _TextResponse(status=200, body=SEARCH_HTML)
            if "/subject/6082808/" in url:
                return _TextResponse(status=200, body=SUBJECT_6082808_HTML)
            if "/subject/27107109/" in url:
                return _TextResponse(status=200, body=SUBJECT_27107109_HTML)
            raise AssertionError(f"unexpected URL: {url}")

        client = DoubanBookSearchClient(transport=transport)
        result = client.search_by_isbn("978-7-5442-5399-4")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.douban_id, "6082808")
        self.assertEqual(result.isbn, "9787544253994")

    def test_unknown_isbn_returns_none(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> _TextResponse:
            return _TextResponse(status=200, body="<html><body>No matches</body></html>")

        client = DoubanBookSearchClient(transport=transport)
        self.assertIsNone(client.search_by_isbn("9780000000000"))

    def test_subject_without_title_is_skipped(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> _TextResponse:
            if "/subject_search?" in url:
                return _TextResponse(
                    status=200,
                    body='<a href="https://book.douban.com/subject/12345/">result</a>',
                )
            return _TextResponse(status=200, body="<html><div id='info'>ISBN: 9787544253994</div></html>")

        client = DoubanBookSearchClient(transport=transport)
        self.assertEqual(client.search_by_title("test"), [])

    def test_non_2xx_response_raises_provider_error(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> _TextResponse:
            return _TextResponse(status=418, body="blocked")

        client = DoubanBookSearchClient(transport=transport)
        with self.assertRaisesRegex(DoubanProviderError, "HTTP 418"):
            client.search_by_title("test")

    def test_blank_queries_do_not_call_transport(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> _TextResponse:
            raise AssertionError("transport should not be called")

        client = DoubanBookSearchClient(transport=transport)
        self.assertEqual(client.search_by_title("   "), [])
        self.assertIsNone(client.search_by_isbn("---"))

    def test_custom_user_agent_is_preserved(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> _TextResponse:
            self.assertEqual(headers["User-Agent"], "custom-agent")
            return _TextResponse(status=200, body="<html></html>")

        client = DoubanBookSearchClient(user_agent="custom-agent", transport=transport)
        self.assertEqual(client.search_by_title("test"), [])

    def test_multiple_people_are_split(self) -> None:
        html = """
        <h1><span property="v:itemreviewed">合作作品</span></h1>
        <div id="info">
        <span>作者:</span> 作者甲 / 作者乙<br/>
        <span>译者:</span> 译者甲、译者乙<br/>
        <span>ISBN:</span> 9787544253994<br/>
        </div>
        """
        edition = DoubanBookSearchClient._parse_subject_page(
            html,
            subject_id="1",
            subject_url="https://book.douban.com/subject/1/",
        )
        self.assertIsNotNone(edition)
        assert edition is not None
        self.assertEqual(edition.authors, ["作者甲", "作者乙"])
        self.assertEqual(edition.translators, ["译者甲", "译者乙"])


if __name__ == "__main__":
    unittest.main()
