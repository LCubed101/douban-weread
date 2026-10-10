from __future__ import annotations

import unittest

from douban_weread.core.models import Edition
from douban_weread.inbox import BookInboxResolutionKind, BookInboxService, request_from_text
from douban_weread.inbox_weread import WeReadEditionLookup, WeReadLookupKind
from douban_weread.providers.weread import WeReadSearchCandidate


class _DoubanCatalog:
    def search_by_title(self, title: str, *, count: int = 20):
        return [
            Edition(
                title="酱园弄凶案：变动时代的女性、司法与社会",
                authors=["彭晗"],
                douban_id="123",
                source_metadata={"subject_url": "https://book.douban.com/subject/123/"},
            ),
            Edition(title="完全无关", authors=["某作者"]),
        ][:count]

    def search_by_isbn(self, isbn: str):
        return None

    def get_by_subject_id(self, subject_id: str):
        return None


class _WeReadCatalog:
    def search_books(self, keyword: str, *, count: int = 10):
        return [
            WeReadSearchCandidate(
                book_id="3300228157",
                title="酱园弄凶案：变动时代的女性、司法与社会",
                author="彭晗",
                soldout=False,
                deep_link="https://weread.qq.com/book-detail?v=example",
            ),
            WeReadSearchCandidate(book_id="other", title="春阿氏谋夫案", author="王冷佛"),
        ][:count]

    def get_book(self, book_id: str):
        raise AssertionError("Related-only candidates must not be resolved as exact books")


class RelatedHintsTests(unittest.TestCase):
    def test_douban_related_book_is_not_actionable(self):
        result = BookInboxService(_DoubanCatalog()).resolve(request_from_text("酱园弄"))
        self.assertEqual(result.kind, BookInboxResolutionKind.NOT_FOUND)
        self.assertEqual(result.candidates, ())
        self.assertIsNone(result.confirmation)
        self.assertIn("酱园弄凶案", result.message)
        self.assertIn("彭晗", result.message)
        self.assertNotIn("完全无关", result.message)

    def test_weread_related_book_is_not_exact_or_readability_claim(self):
        result = WeReadEditionLookup(_WeReadCatalog()).lookup_title("酱园弄")
        self.assertEqual(result.kind, WeReadLookupKind.NOT_FOUND)
        self.assertIsNone(result.selected_edition)
        self.assertIn("酱园弄凶案", result.message)
        self.assertIn("未确认是同一作品或版本", result.message)
        self.assertNotIn("春阿氏谋夫案", result.message)

    def test_unrelated_mengyoushu_results_remain_not_found(self):
        class OtherCatalog(_WeReadCatalog):
            def search_books(self, keyword: str, *, count: int = 10):
                return [WeReadSearchCandidate(book_id="a", title="梦游惊魂", author="雷姆琼儿")]

        result = WeReadEditionLookup(OtherCatalog()).lookup_title("梦游书")
        self.assertEqual(result.kind, WeReadLookupKind.NOT_FOUND)
        self.assertNotIn("梦游惊魂", result.message)


if __name__ == "__main__":
    unittest.main()
