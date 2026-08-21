from __future__ import annotations

import unittest

from douban_weread.core.models import Edition
from douban_weread.inbox import (
    BookInboxResolutionKind,
    BookInboxService,
    request_from_image_key,
    request_from_text,
)


class FakeDouban:
    def __init__(self) -> None:
        self.search_calls: list[tuple[str, int]] = []
        self.isbn_calls: list[str] = []
        self.subject_calls: list[str] = []

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        self.search_calls.append((title, count))
        if title == "三体":
            return [Edition(title="三体", authors=["刘慈欣"], douban_id="2567698")]
        if title == "白夜行":
            return [
                Edition(title="白夜行", authors=["东野圭吾"], douban_id="3259440"),
                Edition(title="白夜行", authors=["东野圭吾"], douban_id="10554308"),
            ]
        return []

    def search_by_isbn(self, isbn: str) -> Edition | None:
        self.isbn_calls.append(isbn)
        if isbn == "9787536692930":
            return Edition(
                title="三体",
                authors=["刘慈欣"],
                isbn=isbn,
                douban_id="2567698",
            )
        return None

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        self.subject_calls.append(subject_id)
        if subject_id == "2567698":
            return Edition(title="三体", authors=["刘慈欣"], douban_id=subject_id)
        return None


class BookInboxServiceTests(unittest.TestCase):
    def test_single_title_candidate_becomes_confirmation(self) -> None:
        provider = FakeDouban()
        result = BookInboxService(provider).resolve(request_from_text("三体"))
        self.assertEqual(result.kind, BookInboxResolutionKind.CONFIRM)
        self.assertIsNotNone(result.confirmation)
        self.assertEqual(result.confirmation.candidate.douban_id, "2567698")

    def test_isbn_uses_exact_lookup_without_title_search(self) -> None:
        provider = FakeDouban()
        result = BookInboxService(provider).resolve(request_from_text("9787536692930"))
        self.assertEqual(result.kind, BookInboxResolutionKind.CONFIRM)
        self.assertEqual(provider.isbn_calls, ["9787536692930"])
        self.assertEqual(provider.search_calls, [])
        self.assertEqual(result.confirmation.candidate.douban_id, "2567698")

    def test_multiple_title_candidates_require_more_specific_input(self) -> None:
        result = BookInboxService(FakeDouban()).resolve(request_from_text("白夜行"))
        self.assertEqual(result.kind, BookInboxResolutionKind.MULTIPLE_CANDIDATES)
        self.assertEqual(len(result.candidates), 2)
        self.assertIsNone(result.confirmation)

    def test_douban_url_fetches_exact_subject(self) -> None:
        provider = FakeDouban()
        result = BookInboxService(provider).resolve(
            request_from_text("https://book.douban.com/subject/2567698/")
        )
        self.assertEqual(result.kind, BookInboxResolutionKind.CONFIRM)
        self.assertEqual(provider.subject_calls, ["2567698"])
        self.assertEqual(provider.search_calls, [])

    def test_image_stays_pending_without_provider_call(self) -> None:
        provider = FakeDouban()
        result = BookInboxService(provider).resolve(request_from_image_key("img_v3_x"))
        self.assertEqual(result.kind, BookInboxResolutionKind.PENDING_IMAGE)
        self.assertEqual(provider.search_calls, [])
        self.assertEqual(provider.isbn_calls, [])
        self.assertEqual(provider.subject_calls, [])


if __name__ == "__main__":
    unittest.main()
