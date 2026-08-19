from __future__ import annotations

import unittest

from douban_weread.providers.douban.normalize import (
    normalize_douban_edition,
    normalize_isbn,
    normalize_people,
    normalize_publish_date,
)


class DoubanNormalizationTests(unittest.TestCase):
    def test_multiple_authors_and_translators_are_preserved_as_lists(self) -> None:
        edition = normalize_douban_edition(
            {
                "id": "123",
                "title": "Example Book",
                "author": [" Author A ", "Author B", "Author A"],
                "translator": ["Translator A", " Translator B "],
                "publisher": " Example Press ",
                "pubdate": "2023-9",
                "isbn13": "978-1-4028-9462-6",
            }
        )

        self.assertIsNotNone(edition)
        assert edition is not None
        self.assertEqual(edition.authors, ["Author A", "Author B"])
        self.assertEqual(edition.translators, ["Translator A", "Translator B"])
        self.assertEqual(edition.publisher, "Example Press")
        self.assertEqual(edition.publish_date, "2023-09")
        self.assertEqual(edition.isbn, "9781402894626")

    def test_missing_optional_fields_do_not_crash(self) -> None:
        edition = normalize_douban_edition({"id": "123", "title": "Minimal Book"})

        self.assertIsNotNone(edition)
        assert edition is not None
        self.assertEqual(edition.authors, [])
        self.assertEqual(edition.translators, [])
        self.assertIsNone(edition.publisher)
        self.assertIsNone(edition.publish_date)
        self.assertIsNone(edition.isbn)

    def test_invalid_payload_without_identity_is_skipped(self) -> None:
        self.assertIsNone(normalize_douban_edition({"title": "Missing ID"}))
        self.assertIsNone(normalize_douban_edition({"id": "123"}))
        self.assertIsNone(normalize_douban_edition("not a mapping"))

    def test_unknown_date_format_is_preserved(self) -> None:
        self.assertEqual(normalize_publish_date("Spring 2020 edition"), "2020")
        self.assertEqual(normalize_publish_date("未知日期"), "未知日期")

    def test_isbn_requires_valid_length(self) -> None:
        self.assertEqual(normalize_isbn("978-7-5442-5399-4"), "9787544253994")
        self.assertEqual(normalize_isbn("0-306-40615-2"), "0306406152")
        self.assertIsNone(normalize_isbn("1234"))

    def test_people_accept_scalar_and_remove_duplicates(self) -> None:
        self.assertEqual(normalize_people(" Single Author "), ["Single Author"])
        self.assertEqual(normalize_people(["A", "A", " B ", None]), ["A", "B"])

    def test_raw_provider_metadata_is_preserved_for_debugging(self) -> None:
        raw = {"id": "123", "title": "Book", "custom_field": {"nested": True}}
        edition = normalize_douban_edition(raw)

        self.assertIsNotNone(edition)
        assert edition is not None
        self.assertEqual(edition.source_metadata["custom_field"], {"nested": True})


if __name__ == "__main__":
    unittest.main()
