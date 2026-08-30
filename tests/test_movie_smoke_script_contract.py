from __future__ import annotations

import unittest

from douban_weread.movie_router import DoubanMovieResolver, MovieResolveKind
from douban_weread.providers.douban.movie import DoubanMovieCandidate


class FakeSearch:
    def search_by_title(self, title: str, *, count: int = 10):
        return [
            DoubanMovieCandidate("1", "三体", "2023", "tv", (), (), (), (), "https://movie.douban.com/subject/1/"),
            DoubanMovieCandidate("2", "三体", "2024", "tv", (), (), (), (), "https://movie.douban.com/subject/2/"),
        ]


class MovieSmokeContractTests(unittest.TestCase):
    def test_ambiguous_titles_never_produce_selected_subject(self):
        result = DoubanMovieResolver(FakeSearch()).resolve("三体")
        self.assertEqual(result.kind, MovieResolveKind.AMBIGUOUS)
        self.assertIsNone(result.selected)


if __name__ == "__main__":
    unittest.main()
