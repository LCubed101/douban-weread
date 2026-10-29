from __future__ import annotations

import unittest

from douban_weread.core.models import Edition
from douban_weread.inbox import BookInboxResolutionKind, BookInboxService, request_from_text
from douban_weread.inbox_weread import WeReadEditionLookup, WeReadLookupKind
from douban_weread.providers.weread import WeReadSearchCandidate
from douban_weread.resolver import filter_title_candidates, is_exact_title_match, is_same_work_title


class _DoubanCatalog:
    def search_by_title(self, title: str, *, count: int = 20):
        return [
            Edition(title="梦游书", authors=["简媜"], douban_id="6047925"),
            Edition(title="梦游书", authors=["简媜"], douban_id="37408713"),
            Edition(title="梦游书", authors=["简媜"], douban_id="25884913"),
            Edition(title="夢遊書", authors=["簡媜"], douban_id="2216915"),
            Edition(title="夢遊書", authors=["簡媜"], douban_id="3902430"),
        ][:count]

    def search_by_isbn(self, isbn: str):
        return None

    def get_by_subject_id(self, subject_id: str):
        return None


class _WeReadCatalog:
    def search_books(self, keyword: str, *, count: int = 10):
        return [WeReadSearchCandidate(
            book_id="jiang",
            title="酱园弄凶案：变动时代的女性、司法与社会",
            author="彭晗",
            deep_link="https://weread.qq.com/book-detail?v=test",
            soldout=False,
        )]

    def get_book(self, book_id: str):
        raise AssertionError("Related hint must not fetch a book")


class SmallSearchFixTests(unittest.TestCase):
    def test_traditional_title_matches_exact_but_not_unrelated_work(self):
        self.assertTrue(is_exact_title_match("梦游书", "夢遊書"))
        self.assertTrue(is_same_work_title("夢遊書", "梦游书"))
        self.assertFalse(is_same_work_title("梦游书", "梦游惊魂"))
        self.assertFalse(is_same_work_title("变量", "变量 2"))

    def test_all_five_douban_editions_remain_selectable(self):
        editions = _DoubanCatalog().search_by_title("梦游书")
        self.assertEqual(len(filter_title_candidates("梦游书", editions)), 5)
        result = BookInboxService(_DoubanCatalog()).resolve(request_from_text("梦游书"))
        self.assertEqual(result.kind, BookInboxResolutionKind.MULTIPLE_CANDIDATES)
        self.assertEqual(len(result.candidates), 5)

    def test_weread_related_hints_have_real_newlines_and_no_selection(self):
        result = WeReadEditionLookup(_WeReadCatalog()).lookup_title("酱园弄")
        self.assertEqual(result.kind, WeReadLookupKind.NOT_FOUND)
        self.assertIsNone(result.selected_edition)
        self.assertIn("\n搜索还返回以下相关书籍", result.message)
        self.assertNotIn("\\n", result.message)


if __name__ == "__main__":
    unittest.main()
