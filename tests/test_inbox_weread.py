from __future__ import annotations

import unittest

from douban_weread.core.models import Edition
from douban_weread.inbox_weread import WeReadEditionLookup, WeReadLookupKind
from douban_weread.providers.weread import WeReadSearchCandidate


class FakeCatalog:
    def __init__(self, candidates, books) -> None:
        self.candidates = candidates
        self.books = books
        self.search_calls: list[tuple[str, int]] = []
        self.book_calls: list[str] = []

    def search_books(self, keyword: str, *, count: int = 10):
        self.search_calls.append((keyword, count))
        return self.candidates[:count]

    def get_book(self, book_id: str):
        self.book_calls.append(book_id)
        return self.books.get(book_id)


class KeywordCatalog(FakeCatalog):
    def __init__(self, by_keyword, books) -> None:
        super().__init__([], books)
        self.by_keyword = by_keyword

    def search_books(self, keyword: str, *, count: int = 10):
        self.search_calls.append((keyword, count))
        return self.by_keyword.get(keyword, [])[:count]


def source() -> Edition:
    return Edition(
        title="白夜行",
        authors=["[日] 东野圭吾"],
        translators=["刘姿君"],
        publisher="南海出版公司",
        publish_date="2017-07",
        isbn="9787544291163",
        douban_id="27112607",
    )


class WeReadEditionLookupTests(unittest.TestCase):
    def test_exact_readable_edition_is_reported(self) -> None:
        provider = FakeCatalog(
            [WeReadSearchCandidate(book_id="exact", title="白夜行", soldout=False, deep_link="https://weread.qq.com/exact")],
            {
                "exact": Edition(
                    title="白夜行",
                    authors=["东野圭吾"],
                    translators=["刘姿君"],
                    publisher="南海出版公司",
                    publish_date="2017-07-21",
                    isbn="9787544291163",
                    weread_id="exact",
                )
            },
        )

        result = WeReadEditionLookup(provider).lookup(source())

        self.assertEqual(result.kind, WeReadLookupKind.EXACT)
        self.assertEqual(result.selected_edition.weread_id, "exact")
        self.assertIn("找到同一版本", result.message)
        self.assertIn("https://weread.qq.com/exact", result.message)
        self.assertEqual(provider.search_calls, [("白夜行", 20)])

    def test_alternative_readable_edition_is_explicitly_not_exact(self) -> None:
        provider = FakeCatalog(
            [WeReadSearchCandidate(book_id="old", title="白夜行", soldout=False)],
            {
                "old": Edition(
                    title="白夜行",
                    authors=["东野圭吾"],
                    translators=["刘姿君"],
                    publisher="南海出版公司",
                    publish_date="2013-01",
                    isbn="9787544258609",
                    weread_id="old",
                )
            },
        )

        result = WeReadEditionLookup(provider).lookup(source())

        self.assertEqual(result.kind, WeReadLookupKind.ALTERNATIVE)
        self.assertEqual(result.selected_edition.weread_id, "old")
        self.assertIn("没有找到完全相同版本", result.message)
        self.assertIn("9787544291163", result.message)
        self.assertIn("9787544258609", result.message)
        self.assertEqual(provider.search_calls, [("白夜行", 20)])

    def test_title_miss_retries_exact_isbn_and_preserves_soldout_as_unavailable(self) -> None:
        provider = KeywordCatalog(
            {
                "白夜行": [WeReadSearchCandidate(book_id="other", title="恶意", soldout=False)],
                "9787544291163": [
                    WeReadSearchCandidate(
                        book_id="exact-soldout",
                        title="白夜行",
                        soldout=True,
                        deep_link="https://weread.qq.com/soldout",
                    )
                ],
            },
            {
                "other": Edition(title="恶意", authors=["东野圭吾"], weread_id="other"),
                "exact-soldout": Edition(
                    title="白夜行",
                    authors=["东野圭吾"],
                    translators=["刘姿君"],
                    publisher="南海出版公司",
                    publish_date="2017-07",
                    isbn="9787544291163",
                    weread_id="exact-soldout",
                ),
            },
        )

        result = WeReadEditionLookup(provider).lookup(source())

        self.assertEqual(result.kind, WeReadLookupKind.UNAVAILABLE)
        self.assertEqual(result.selected_edition.weread_id, "exact-soldout")
        self.assertEqual(
            provider.search_calls,
            [("白夜行", 20), ("9787544291163", 20)],
        )
        self.assertIn("当前目录状态显示不可读", result.message)

    def test_no_same_work_after_title_and_isbn_is_bounded_not_found(self) -> None:
        provider = KeywordCatalog(
            {
                "白夜行": [WeReadSearchCandidate(book_id="other", title="恶意", soldout=False)],
                "9787544291163": [],
            },
            {"other": Edition(title="恶意", authors=["东野圭吾"], weread_id="other")},
        )

        result = WeReadEditionLookup(provider, search_limit=3).lookup(source())

        self.assertEqual(result.kind, WeReadLookupKind.NOT_FOUND)
        self.assertIsNone(result.selected_edition)
        self.assertIn("标题或 ISBN", result.message)
        self.assertEqual(
            provider.search_calls,
            [("白夜行", 3), ("9787544291163", 3)],
        )


if __name__ == "__main__":
    unittest.main()
