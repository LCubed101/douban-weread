from __future__ import annotations

import unittest

from douban_weread.providers.douban.history import (
    DoubanBookHistoryClient,
    _HistoryResponse,
)
from douban_weread.providers.douban.interest import DoubanAuthError
from douban_weread.providers.douban.search import DoubanProviderError


PAGE_1 = """
<html><body>
<div class="item">
  <div class="pic"><a href="https://book.douban.com/subject/25837854/"><img src="x"></a></div>
  <div class="info"><ul><li class="title"><a href="https://book.douban.com/subject/25837854/">荷马史诗·奥德赛</a></li></ul></div>
</div>
<div class="item">
  <div class="info"><a href="https://book.douban.com/subject/6082808/" title="百年孤独">百年孤独</a></div>
</div>
<span class="next"><a href="?start=15&sort=time&rating=all&filter=all&mode=grid">后页&gt;</a></span>
</body></html>
"""

PAGE_2 = """
<html><body>
<div class="item">
  <div class="info"><a href="https://book.douban.com/subject/1062694/">荷马史诗·奥德赛</a></div>
</div>
</body></html>
"""

CURRENT_SUBJECT_ITEM_PAGE = """
<html>
<head><title>测试用户想读的书(2)</title></head>
<body>
<ul class="interest-list">
  <li class="subject-item">
    <div class="pic"><a href="https://book.douban.com/subject/25837854/"><img src="x"></a></div>
    <div class="info">
      <h2><a href="https://book.douban.com/subject/25837854/" title="荷马史诗·奥德赛">荷马史诗·奥德赛</a></h2>
      <div class="ft"><a href="https://book.douban.com/subject/25837854/">纸质版 46.60元</a></div>
    </div>
  </li>
  <li class="subject-item">
    <div class="info">
      <h2><a href="https://book.douban.com/subject/6082808/" title="百年孤独">百年孤独</a></h2>
      <div class="ft"><a href="https://book.douban.com/subject/6082808/">纸质版 39.90元</a></div>
    </div>
  </li>
</ul>
</body>
</html>
"""


class DoubanBookHistoryClientTests(unittest.TestCase):
    def test_fetch_state_follows_pagination_and_deduplicates_subject_links(self) -> None:
        requested: list[str] = []

        def transport(url: str, headers: dict[str, str]) -> _HistoryResponse:
            requested.append(url)
            self.assertIn("Cookie", headers)
            if "start=0" in url:
                return _HistoryResponse(200, PAGE_1, url)
            if "start=15" in url:
                return _HistoryResponse(200, PAGE_2, url)
            raise AssertionError(f"unexpected URL: {url}")

        client = DoubanBookHistoryClient(
            'bid=test; dbcl2="123456:test-session"; ck=test-csrf',
            transport=transport,
        )
        entries = client.fetch_state("wish")

        self.assertEqual(
            [(entry.subject_id, entry.title, entry.state) for entry in entries],
            [
                ("25837854", "荷马史诗·奥德赛", "wish"),
                ("6082808", "百年孤独", "wish"),
                ("1062694", "荷马史诗·奥德赛", "wish"),
            ],
        )
        self.assertEqual(len(requested), 2)
        self.assertTrue(all("/people/123456/wish" in url for url in requested))

    def test_current_subject_item_markup_is_parsed(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> _HistoryResponse:
            return _HistoryResponse(200, CURRENT_SUBJECT_ITEM_PAGE, url)

        client = DoubanBookHistoryClient(
            'dbcl2="123456:test-session"; ck=test-csrf',
            transport=transport,
        )
        entries = client.fetch_state("wish")

        self.assertEqual(
            [(entry.subject_id, entry.title) for entry in entries],
            [("25837854", "荷马史诗·奥德赛"), ("6082808", "百年孤独")],
        )

    def test_price_link_to_same_subject_cannot_overwrite_title(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> _HistoryResponse:
            return _HistoryResponse(200, CURRENT_SUBJECT_ITEM_PAGE, url)

        client = DoubanBookHistoryClient(
            'dbcl2="123456:test-session"; ck=test-csrf',
            transport=transport,
        )
        entries = client.fetch_state("wish")

        self.assertEqual([entry.title for entry in entries], ["荷马史诗·奥德赛", "百年孤独"])
        self.assertFalse(any("纸质版" in entry.title for entry in entries))

    def test_declared_nonempty_list_with_zero_parsed_entries_fails_closed(self) -> None:
        body = "<html><head><title>测试用户想读的书(12)</title></head><body></body></html>"

        def transport(url: str, headers: dict[str, str]) -> _HistoryResponse:
            return _HistoryResponse(200, body, url)

        client = DoubanBookHistoryClient(
            'dbcl2="123456:test-session"; ck=test-csrf',
            transport=transport,
        )
        with self.assertRaisesRegex(DoubanProviderError, "declared 12 entries but parsed 0"):
            client.fetch_state("wish")

    def test_declared_total_must_match_all_parsed_pages(self) -> None:
        body = CURRENT_SUBJECT_ITEM_PAGE.replace("(2)", "(3)")

        def transport(url: str, headers: dict[str, str]) -> _HistoryResponse:
            return _HistoryResponse(200, body, url)

        client = DoubanBookHistoryClient(
            'dbcl2="123456:test-session"; ck=test-csrf',
            transport=transport,
        )
        with self.assertRaisesRegex(DoubanProviderError, "declared 3 entries but parsed 2"):
            client.fetch_state("wish")

    def test_declared_zero_allows_a_truly_empty_state(self) -> None:
        body = "<html><head><title>测试用户在读的书(0)</title></head><body></body></html>"

        def transport(url: str, headers: dict[str, str]) -> _HistoryResponse:
            return _HistoryResponse(200, body, url)

        client = DoubanBookHistoryClient(
            'dbcl2="123456:test-session"; ck=test-csrf',
            transport=transport,
        )
        self.assertEqual(client.fetch_state("do"), [])

    def test_fetch_all_reads_wish_do_collect(self) -> None:
        states_seen: list[str] = []

        def transport(url: str, headers: dict[str, str]) -> _HistoryResponse:
            for state in ("wish", "do", "collect"):
                if f"/{state}?" in url:
                    states_seen.append(state)
                    body = PAGE_2.replace("1062694", {"wish": "1", "do": "2", "collect": "3"}[state])
                    return _HistoryResponse(200, body, url)
            raise AssertionError(url)

        client = DoubanBookHistoryClient(
            'dbcl2="123456:test-session"; ck=test-csrf',
            transport=transport,
        )
        entries = client.fetch_all()

        self.assertEqual(states_seen, ["wish", "do", "collect"])
        self.assertEqual([entry.state for entry in entries], ["wish", "do", "collect"])

    def test_missing_cookie_fails_before_network(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> _HistoryResponse:
            raise AssertionError("network should not be called")

        client = DoubanBookHistoryClient("", transport=transport)
        with self.assertRaisesRegex(DoubanAuthError, "DOUBAN_COOKIE is not set"):
            client.fetch_all()

    def test_missing_user_id_fails_closed(self) -> None:
        client = DoubanBookHistoryClient("bid=test; ck=test-csrf")
        with self.assertRaisesRegex(DoubanAuthError, "user ID"):
            client.fetch_all()

    def test_login_page_is_rejected(self) -> None:
        def transport(url: str, headers: dict[str, str]) -> _HistoryResponse:
            return _HistoryResponse(
                200,
                '<html>登录豆瓣 <a href="https://accounts.douban.com/login">login</a></html>',
                "https://accounts.douban.com/passport/login",
            )

        client = DoubanBookHistoryClient(
            'dbcl2="123456:test-session"; ck=test-csrf',
            transport=transport,
        )
        with self.assertRaisesRegex(DoubanAuthError, "login page"):
            client.fetch_state("wish")

    def test_non_advancing_pagination_fails_closed(self) -> None:
        body = PAGE_1.replace("start=15", "start=0")

        def transport(url: str, headers: dict[str, str]) -> _HistoryResponse:
            return _HistoryResponse(200, body, url)

        client = DoubanBookHistoryClient(
            'dbcl2="123456:test-session"; ck=test-csrf',
            transport=transport,
        )
        with self.assertRaisesRegex(DoubanProviderError, "did not advance"):
            client.fetch_state("wish")


if __name__ == "__main__":
    unittest.main()
