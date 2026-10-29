from __future__ import annotations

import unittest

from douban_weread.inbox import BookInboxService, request_from_text
from douban_weread.core.models import Edition


class _Catalog:
    def __init__(self) -> None:
        self.counts: list[int] = []

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        self.counts.append(count)
        return [
            Edition(title=f"无关书名{i}", authors=("其他作者",))
            for i in range(9)
        ] + [Edition(title=title, authors=("目标作者",))]

    def search_by_isbn(self, isbn: str) -> Edition | None:
        return None

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        return None


class DoubanRecallTests(unittest.TestCase):
    def test_default_search_limit_includes_tenth_candidate(self) -> None:
        provider = _Catalog()
        resolution = BookInboxService(provider).resolve(request_from_text("酱园弄"))
        self.assertEqual(provider.counts, [10])
        self.assertEqual([e.title for e in resolution.candidates], ["酱园弄"])

    def test_search_limit_allows_twenty_but_caps_higher_values(self) -> None:
        provider = _Catalog()
        self.assertEqual(BookInboxService(provider, search_limit=20).search_limit, 20)
        self.assertEqual(BookInboxService(provider, search_limit=100).search_limit, 20)


if __name__ == "__main__":
    unittest.main()
