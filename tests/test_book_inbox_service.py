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
        if title == "阿纳斯塔夏":
            # Regression fixture for BUG 1: a one-character typo (斯 vs 丝).
            # No exact/same-work title match at all -> should fall through
            # to the fuzzy "did you mean" suggestion layer.
            return [
                Edition(
                    title="阿纳丝塔夏",
                    authors=["[俄] 弗拉迪米尔·米格列"],
                    publisher="中国青年出版社",
                    publish_date="2016",
                    douban_id="20495701",
                )
            ]
        if title == "阿纳斯塔娅":
            # Two equally-close typo candidates (one substituted character
            # each, same ratio) -> ambiguous "did you mean", fail closed
            # rather than guessing between them.
            return [
                Edition(title="阿纳丝塔娅", douban_id="20495701"),
                Edition(title="阿纳斯培娅", douban_id="88888888"),
            ]
        if title == "变量":
            # Regression fixture for a real Douban search-relevance pollution
            # bug: querying "变量" mixed in an unrelated title ("情绪") and
            # other-numbered sequels ("变量2"/"变量7"/"变量8") alongside the
            # genuine work and one of its real subtitle editions.
            return [
                Edition(title="变量", authors=["何帆"], douban_id="30171723"),
                Edition(title="情绪", authors=["某作者"], douban_id="99999991"),
                Edition(title="变量2", authors=["何帆"], douban_id="99999992"),
                Edition(title="变量：如何应对不确定的未来", authors=["何帆"], douban_id="30469449"),
                Edition(title="变量7", authors=["何帆"], douban_id="99999997"),
                Edition(title="变量8", authors=["何帆"], douban_id="99999998"),
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

    def test_title_pollution_is_filtered_before_display(self) -> None:
        """Regression test for candidate pollution: querying 变量 must never
        surface 情绪 or the other-numbered sequels 变量2/变量7/变量8."""
        provider = FakeDouban()
        result = BookInboxService(provider).resolve(request_from_text("变量"))
        self.assertEqual(result.kind, BookInboxResolutionKind.MULTIPLE_CANDIDATES)
        titles = {edition.title for edition in result.candidates}
        self.assertNotIn("情绪", titles)
        self.assertNotIn("变量2", titles)
        self.assertNotIn("变量7", titles)
        self.assertNotIn("变量8", titles)
        self.assertEqual(titles, {"变量", "变量：如何应对不确定的未来"})

    def test_typo_query_gets_a_fuzzy_did_you_mean_suggestion(self) -> None:
        """Regression test for BUG 1: 阿纳斯塔夏 (typo) -> suggest 阿纳丝塔夏
        (real title), but never auto-confirm it."""
        provider = FakeDouban()
        result = BookInboxService(provider).resolve(request_from_text("阿纳斯塔夏"))
        self.assertEqual(result.kind, BookInboxResolutionKind.FUZZY_SUGGESTION)
        self.assertIsNotNone(result.confirmation)
        self.assertEqual(result.confirmation.candidate.title, "阿纳丝塔夏")
        self.assertEqual(result.confirmation.candidate.douban_id, "20495701")
        # Fuzzy suggestions never ship as a pre-filled candidate list either
        # (that would look like a same-work MULTIPLE_CANDIDATES set).
        self.assertEqual(result.candidates, (result.confirmation.candidate,))

    def test_ambiguous_typo_candidates_fail_closed_not_found(self) -> None:
        """Two equally-plausible typo fixes -> no single obvious answer, so
        this must behave like an ordinary not_found, never guess between them."""
        provider = FakeDouban()
        result = BookInboxService(provider).resolve(request_from_text("阿纳斯塔娅"))
        self.assertEqual(result.kind, BookInboxResolutionKind.NOT_FOUND)
        self.assertIsNone(result.confirmation)

    def test_sequel_numbered_titles_are_never_offered_as_fuzzy_suggestions(self) -> None:
        """变量 must not fuzzy-suggest 变量2/变量7/变量8 either — the #74
        prefix/volume-suffix exclusion applies to the fuzzy layer too."""
        provider = FakeDouban()
        result = BookInboxService(provider).resolve(request_from_text("变量"))
        # 变量 already has real #74-filtered candidates (MULTIPLE_CANDIDATES),
        # so the fuzzy layer never even runs here — but confirm directly that
        # the fuzzy matcher itself refuses these on the raw candidate pool.
        from douban_weread.resolver import suggest_fuzzy_title_match

        raw = provider.search_by_title("变量", count=5)
        self.assertIsNone(suggest_fuzzy_title_match("变量", raw))
        self.assertEqual(result.kind, BookInboxResolutionKind.MULTIPLE_CANDIDATES)

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
