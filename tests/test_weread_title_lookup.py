from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass

from douban_weread.core.book_mentions import BookMention
from douban_weread.core.models import Edition
from douban_weread.feishu_bot_v11 import _lookup_mentions
from douban_weread.inbox_weread import WeReadEditionLookup, WeReadLookupKind


@dataclass
class Candidate:
    book_id: str
    title: str
    soldout: int = 0
    deep_link: str | None = None
    author: str | None = None
    publisher: str | None = None


class FakeProvider:
    def __init__(self, candidates, editions):
        self.candidates = candidates
        self.editions = editions
        self.searches = []

    def search_books(self, keyword: str, *, count: int = 10):
        self.searches.append((keyword, count))
        return list(self.candidates)

    def get_book(self, book_id: str):
        return self.editions.get(book_id)


class WeReadTitleLookupTest(unittest.TestCase):
    def test_exact_normalized_title_returns_readable_result(self) -> None:
        provider = FakeProvider(
            [Candidate("1", "深度工作", deep_link="https://weread.qq.com/web/bookDetail/1")],
            {"1": Edition(title="深度工作", authors=["卡尔·纽波特"])},
        )
        lookup = WeReadEditionLookup(provider=provider)

        result = lookup.lookup_title(" 深度工作 ")

        self.assertEqual(result.kind, WeReadLookupKind.EXACT)
        self.assertEqual(result.selected_edition.title, "深度工作")
        self.assertEqual(result.deep_link, "https://weread.qq.com/web/bookDetail/1")
        self.assertIn("可读链接：", result.message)

    def test_fuzzy_title_does_not_get_auto_selected(self) -> None:
        provider = FakeProvider(
            [Candidate("1", "深度工作：如何有效使用每一点脑力", deep_link="https://weread.qq.com/web/bookDetail/1")],
            {"1": Edition(title="深度工作：如何有效使用每一点脑力")},
        )
        lookup = WeReadEditionLookup(provider=provider)

        result = lookup.lookup_title("深度工作")

        self.assertEqual(result.kind, WeReadLookupKind.NOT_FOUND)
        self.assertIsNone(result.deep_link)

    def test_exact_title_soldout_is_unavailable(self) -> None:
        provider = FakeProvider(
            [Candidate("1", "专注", soldout=1, deep_link="https://weread.qq.com/web/bookDetail/1")],
            {"1": Edition(title="专注")},
        )
        lookup = WeReadEditionLookup(provider=provider)

        result = lookup.lookup_title("专注")

        self.assertEqual(result.kind, WeReadLookupKind.UNAVAILABLE)

    def test_search_only_soldout_candidate_is_still_waiting(self) -> None:
        provider = FakeProvider(
            [
                Candidate(
                    "87332a20811e1ad78g018d1e",
                    "如何改变世界",
                    soldout=1,
                    deep_link="https://weread.qq.com/book-detail?v=87332a20811e1ad78g018d1e",
                    author="埃里克·霍布斯鲍姆",
                )
            ],
            {},
        )
        lookup = WeReadEditionLookup(provider=provider)

        result = lookup.lookup_title("如何改变世界")

        self.assertEqual(result.kind, WeReadLookupKind.UNAVAILABLE)
        self.assertEqual(result.selected_edition.title, "如何改变世界")
        self.assertEqual(result.selected_edition.weread_id, "87332a20811e1ad78g018d1e")
        self.assertEqual(
            result.deep_link,
            "https://weread.qq.com/book-detail?v=87332a20811e1ad78g018d1e",
        )
        self.assertIn("待上架/不可读", result.message)

    def test_available_candidate_without_book_info_is_not_marked_readable(self) -> None:
        provider = FakeProvider(
            [Candidate("1", "深度工作", soldout=0, deep_link="https://weread.qq.com/web/bookDetail/1")],
            {},
        )
        lookup = WeReadEditionLookup(provider=provider)

        result = lookup.lookup_title("深度工作")

        self.assertEqual(result.kind, WeReadLookupKind.NOT_FOUND)

    def test_multi_book_lookup_uses_title_only_method(self) -> None:
        class Lookup:
            def __init__(self):
                self.titles = []

            def lookup_title(self, title):
                self.titles.append(title)
                return type("Result", (), {"message": "ok"})()

            def lookup(self, edition):
                raise AssertionError("edition lookup should not be used")

        lookup = Lookup()
        mentions = (BookMention("深度工作"), BookMention("专注"))

        results = asyncio.run(_lookup_mentions(mentions, lookup))

        self.assertEqual(lookup.titles, ["深度工作", "专注"])
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()
