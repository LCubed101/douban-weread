from __future__ import annotations

import unittest

from douban_weread.core.models import Edition
from douban_weread.resolver.edition import MatchKind, compare_editions, rank_editions


def edition(
    *,
    title: str = "百年孤独",
    authors: list[str] | None = None,
    translators: list[str] | None = None,
    publisher: str | None = None,
    publish_date: str | None = None,
    isbn: str | None = None,
    language: str | None = None,
) -> Edition:
    return Edition(
        title=title,
        authors=authors if authors is not None else ["加西亚·马尔克斯"],
        translators=translators if translators is not None else [],
        publisher=publisher,
        publish_date=publish_date,
        isbn=isbn,
        language=language,
    )


class EditionMatchingTests(unittest.TestCase):
    def test_exact_isbn_is_exact_and_safe(self) -> None:
        source = edition(isbn="9787544253994", translators=["范晔"])
        candidate = edition(isbn="978-7-5442-5399-4", translators=["范晔"])

        result = compare_editions(source, candidate)

        self.assertEqual(result.kind, MatchKind.EXACT_EDITION)
        self.assertEqual(result.score, 1.0)
        self.assertTrue(result.same_work)
        self.assertTrue(result.exact_edition)
        self.assertFalse(result.requires_confirmation)
        self.assertTrue(result.safe_to_auto_apply)
        self.assertEqual(result.edition_differences, [])

    def test_different_isbn_is_alternative_even_with_matching_metadata(self) -> None:
        source = edition(
            isbn="9787544253994",
            translators=["范晔"],
            publisher="南海出版公司",
            publish_date="2011-06",
        )
        candidate = edition(
            isbn="9787544291170",
            translators=["范晔"],
            publisher="南海出版公司",
            publish_date="2017-08",
        )

        result = compare_editions(source, candidate)

        self.assertTrue(result.same_work)
        self.assertEqual(result.kind, MatchKind.ALTERNATIVE_EDITION)
        self.assertFalse(result.requires_confirmation)
        self.assertFalse(result.safe_to_auto_apply)
        self.assertIn("ISBN differs", result.edition_differences)
        self.assertIn("publication year differs", result.edition_differences)
        self.assertEqual(result.material_differences, [])

    def test_same_work_same_translator_different_publisher_is_alternative(self) -> None:
        source = edition(
            authors=["[哥伦比亚] 加西亚·马尔克斯"],
            translators=["范晔"],
            publisher="南海出版公司",
            publish_date="2011-06",
        )
        candidate = edition(
            authors=["加西亚·马尔克斯"],
            translators=["范晔"],
            publisher="另一出版社",
            publish_date="2011-10",
        )

        result = compare_editions(source, candidate)

        self.assertTrue(result.same_work)
        self.assertEqual(result.kind, MatchKind.ALTERNATIVE_EDITION)
        self.assertFalse(result.requires_confirmation)
        self.assertFalse(result.safe_to_auto_apply)
        self.assertIn("publisher differs", result.edition_differences)
        self.assertEqual(result.material_differences, [])

    def test_different_publication_year_is_alternative(self) -> None:
        source = edition(
            translators=["范晔"],
            publisher="南海出版公司",
            publish_date="2011-06",
        )
        candidate = edition(
            translators=["范晔"],
            publisher="南海出版公司",
            publish_date="2020-09",
        )

        result = compare_editions(source, candidate)

        self.assertEqual(result.kind, MatchKind.ALTERNATIVE_EDITION)
        self.assertFalse(result.requires_confirmation)
        self.assertIn("publication year differs", result.edition_differences)

    def test_different_translator_requires_confirmation(self) -> None:
        source = edition(translators=["范晔"])
        candidate = edition(translators=["另一译者"])

        result = compare_editions(source, candidate)

        self.assertTrue(result.same_work)
        self.assertEqual(result.kind, MatchKind.ALTERNATIVE_EDITION)
        self.assertTrue(result.requires_confirmation)
        self.assertIn("translator differs", result.material_differences)
        self.assertFalse(result.safe_to_auto_apply)

    def test_different_language_requires_confirmation(self) -> None:
        source = edition(language="zh-CN")
        candidate = edition(language="en")

        result = compare_editions(source, candidate)

        self.assertTrue(result.same_work)
        self.assertTrue(result.requires_confirmation)
        self.assertIn("language differs", result.material_differences)

    def test_same_title_different_author_is_not_same_work(self) -> None:
        source = edition(authors=["作者甲"])
        candidate = edition(authors=["作者乙"])

        result = compare_editions(source, candidate)

        self.assertFalse(result.same_work)
        self.assertEqual(result.kind, MatchKind.DIFFERENT_WORK)
        self.assertTrue(result.requires_confirmation)
        self.assertFalse(result.safe_to_auto_apply)

    def test_title_only_similarity_never_auto_applies(self) -> None:
        source = edition(authors=[])
        candidate = edition(authors=[])

        result = compare_editions(source, candidate)

        self.assertFalse(result.same_work)
        self.assertEqual(result.kind, MatchKind.AMBIGUOUS)
        self.assertTrue(result.requires_confirmation)
        self.assertFalse(result.safe_to_auto_apply)

    def test_revision_marker_is_same_work_but_material_edition_difference(self) -> None:
        source = edition(title="漫长的告别", authors=["雷蒙德·钱德勒"])
        candidate = edition(title="漫长的告别 修订版", authors=["雷蒙德·钱德勒"])

        result = compare_editions(source, candidate)

        self.assertTrue(result.same_work)
        self.assertEqual(result.kind, MatchKind.ALTERNATIVE_EDITION)
        self.assertIn("revision/abridgement/annotation markers differ", result.material_differences)
        self.assertTrue(result.requires_confirmation)

    def test_rank_editions_places_exact_isbn_first(self) -> None:
        source = edition(isbn="9787544253994", translators=["范晔"])
        alternative = edition(isbn="9780000000000", translators=["范晔"])
        exact = edition(isbn="9787544253994", translators=["另一译者"])
        different_work = edition(title="百年孤独", authors=["另一个作者"])

        ranked = rank_editions(source, [alternative, different_work, exact])

        self.assertEqual(ranked[0].kind, MatchKind.EXACT_EDITION)
        self.assertIs(ranked[0].candidate, exact)
        self.assertTrue(ranked[1].same_work)
        self.assertEqual(ranked[1].kind, MatchKind.ALTERNATIVE_EDITION)
        self.assertFalse(ranked[-1].same_work)


if __name__ == "__main__":
    unittest.main()
