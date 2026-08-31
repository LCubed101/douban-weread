from __future__ import annotations

import unittest
from types import SimpleNamespace

from douban_weread.movie_router import DoubanMovieResolver, MovieResolveKind
from douban_weread.providers.douban.movie import DoubanMovieCandidate, DoubanMovieSearchClient
from douban_weread.providers.douban.movie_interest import DoubanMovieInterestClient
from douban_weread.providers.douban.interest import DoubanConfirmationRequired


class FakeMovieSearch:
    def __init__(self, items):
        self.items = list(items)
        self.queries = []

    def search_by_title(self, title: str, *, count: int = 10):
        self.queries.append((title, count))
        return list(self.items)


def movie(movie_id: str, title: str, *, year: str = "2024", aliases=(), media_type="movie"):
    return DoubanMovieCandidate(
        douban_id=movie_id,
        title=title,
        year=year,
        media_type=media_type,
        directors=(),
        actors=(),
        genres=(),
        aliases=tuple(aliases),
        subject_url=f"https://movie.douban.com/subject/{movie_id}/",
    )


class DoubanMovieResolverTests(unittest.TestCase):
    def test_unique_exact_title_auto_selects(self):
        resolver = DoubanMovieResolver(FakeMovieSearch([movie("1", "机器人之梦")]))
        result = resolver.resolve("机器人之梦")
        self.assertEqual(result.kind, MovieResolveKind.EXACT)
        self.assertEqual(result.selected.douban_id, "1")

    def test_alias_can_match_exactly(self):
        resolver = DoubanMovieResolver(FakeMovieSearch([movie("1", "Robot Dreams", aliases=("机器人之梦",))]))
        result = resolver.resolve("机器人之梦")
        self.assertEqual(result.kind, MovieResolveKind.EXACT)

    def test_same_name_remakes_stay_ambiguous(self):
        resolver = DoubanMovieResolver(FakeMovieSearch([movie("1", "三体", year="2023"), movie("2", "三体", year="2024")]))
        result = resolver.resolve("三体")
        self.assertEqual(result.kind, MovieResolveKind.AMBIGUOUS)
        self.assertEqual(len(result.candidates), 2)

    def test_bare_tv_series_title_returns_seasons_as_ambiguous(self):
        resolver = DoubanMovieResolver(
            FakeMovieSearch(
                [
                    movie("1", "流人 第一季", year="2022", media_type="tv"),
                    movie("2", "流人 第二季", year="2022", media_type="tv"),
                    movie("3", "流人 第三季", year="2023", media_type="tv"),
                ]
            )
        )
        result = resolver.resolve("流人")
        self.assertEqual(result.kind, MovieResolveKind.AMBIGUOUS)
        self.assertIsNone(result.selected)
        self.assertEqual([item.title for item in result.candidates], ["流人 第一季", "流人 第二季", "流人 第三季"])

    def test_unrelated_prefix_result_still_fails_closed(self):
        resolver = DoubanMovieResolver(
            FakeMovieSearch([movie("1", "流人之歌", year="2024", media_type="movie")])
        )
        result = resolver.resolve("流人")
        self.assertEqual(result.kind, MovieResolveKind.NOT_FOUND)


class DoubanMovieSearchParsingTests(unittest.TestCase):
    def test_parses_movie_subject_page(self):
        html = """
        <span property="v:itemreviewed">机器人之梦</span><span class="year">(2023)</span>
        <div id="info">
        导演: 巴勃罗·贝格尔<br/>
        主演: 伊万·拉班达 / 阿尔伯特·特里佛·米拉纳<br/>
        类型: 剧情 / 动画<br/>
        制片国家/地区: 西班牙 / 法国<br/>
        上映日期: 2023-05-20<br/>
        又名: Robot Dreams<br/>
        </div>
        """
        item = DoubanMovieSearchClient._parse_subject_page(
            html,
            subject_id="35426925",
            subject_url="https://movie.douban.com/subject/35426925/",
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.title, "机器人之梦")
        self.assertEqual(item.year, "2023")
        self.assertEqual(item.media_type, "movie")
        self.assertIn("Robot Dreams", item.aliases)

    def test_subject_suggest_is_used_as_candidate_without_detail_refetch(self):
        calls = []

        def transport(url, headers):
            calls.append(url)
            if "/j/subject_suggest?" in url:
                return SimpleNamespace(
                    status=200,
                    body=(
                        '[{"id":"35426925","title":"机器人之梦","year":"2023",'
                        '"type":"movie","sub_title":"Robot Dreams",'
                        '"url":"https://movie.douban.com/subject/35426925/?suggest=机器人之梦"}]'
                    ),
                )
            raise AssertionError(f"detail page should not be fetched: {url}")

        client = DoubanMovieSearchClient(transport=transport)
        items = client.search_by_title("机器人之梦")

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.douban_id, "35426925")
        self.assertEqual(item.title, "机器人之梦")
        self.assertEqual(item.year, "2023")
        self.assertEqual(item.media_type, "movie")
        self.assertEqual(item.aliases, ("Robot Dreams",))
        self.assertEqual(item.subject_url, "https://movie.douban.com/subject/35426925/")
        self.assertEqual(len(calls), 1)

    def test_empty_suggest_falls_back_to_search_douban_movie_host(self):
        calls = []
        subject_html = """
        <span property="v:itemreviewed">机器人之梦</span><span class="year">(2023)</span>
        <div id="info">导演: 巴勃罗·贝格尔<br/>上映日期: 2023-05-20<br/></div>
        """

        def transport(url, headers):
            calls.append(url)
            if "/j/subject_suggest?" in url:
                return SimpleNamespace(status=200, body="[]")
            if "search.douban.com/movie/subject_search" in url:
                return SimpleNamespace(status=200, body='<a href="https://movie.douban.com/subject/35426925/">结果</a>')
            if "/subject/35426925/" in url:
                return SimpleNamespace(status=200, body=subject_html)
            raise AssertionError(f"unexpected URL: {url}")

        client = DoubanMovieSearchClient(transport=transport)
        items = client.search_by_title("机器人之梦")

        self.assertEqual([item.douban_id for item in items], ["35426925"])
        self.assertTrue(any("search.douban.com/movie/subject_search" in url for url in calls))


class DoubanMovieInterestTests(unittest.TestCase):
    def test_requires_explicit_confirmation(self):
        client = DoubanMovieInterestClient(cookie="dbcl2=1:abc; ck=test")
        with self.assertRaises(DoubanConfirmationRequired):
            client.mark_want_to_watch("1295644")

    def test_movie_host_and_verified_wish_write(self):
        calls = []

        def transport(method, url, headers, body):
            calls.append((method, url, body))
            if method == "POST":
                return SimpleNamespace(status=200, body='{"r":0}', url=url)
            return SimpleNamespace(
                status=200,
                body='{"interest_status":"wish"}',
                url=url,
            )

        client = DoubanMovieInterestClient(
            cookie="dbcl2=1:abc; ck=test",
            transport=transport,
        )
        result = client.mark_want_to_watch("1295644", confirmed=True)
        self.assertTrue(result.verified)
        self.assertEqual(result.actual_status, "wish")
        self.assertTrue(all("movie.douban.com" in url for _, url, _ in calls))
        self.assertTrue(any(method == "POST" for method, _, _ in calls))


if __name__ == "__main__":
    unittest.main()
