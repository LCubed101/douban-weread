from __future__ import annotations

import unittest

from douban_weread.alignment import align_to_weread
from douban_weread.core.models import Edition, EditionResolution, WeReadStatus
from douban_weread.providers.weread import WeReadSearchCandidate


class FakeCatalogClient:
    def __init__(
        self,
        candidates: list[WeReadSearchCandidate],
        books: dict[str, Edition | None],
    ) -> None:
        self.candidates = candidates
        self.books = books
        self.search_calls: list[tuple[str, int]] = []
        self.book_calls: list[str] = []

    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        self.search_calls.append((keyword, count))
        return self.candidates[:count]

    def get_book(self, book_id: str) -> Edition | None:
        self.book_calls.append(book_id)
        return self.books.get(book_id)


def source_2017() -> Edition:
    return Edition(
        title="白夜行",
        authors=["[日] 东野圭吾"],
        translators=["刘姿君"],
        publisher="南海出版公司",
        publish_date="2017-07",
        isbn="9787544291163",
        douban_id="27112607",
    )


class WeReadAlignmentTests(unittest.TestCase):
    def test_exact_available_maps_to_reading_intent(self) -> None:
        client = FakeCatalogClient(
            [
                WeReadSearchCandidate(
                    book_id="230107",
                    title="白夜行",
                    soldout=False,
                    deep_link="https://weread.qq.com/book-detail?exact",
                )
            ],
            {
                "230107": Edition(
                    title="白夜行",
                    authors=["东野圭吾"],
                    translators=["刘姿君"],
                    publisher="南海出版公司",
                    publish_date="2017-07-21",
                    isbn="9787544291163",
                    weread_id="230107",
                )
            },
        )

        result = align_to_weread(source_2017(), client, limit=5)

        self.assertEqual(result.intent.weread_status, WeReadStatus.AVAILABLE_EXACT)
        self.assertEqual(result.intent.resolution, EditionResolution.EXACT_MATCH)
        self.assertEqual(result.intent.selected_edition.weread_id, "230107")
        self.assertTrue(result.match.exact_edition)
        self.assertEqual(result.intent.source_url, "https://weread.qq.com/book-detail?exact")
        self.assertIn("soldout=0", result.intent.notes[0])

    def test_available_alternative_maps_without_claiming_exact(self) -> None:
        client = FakeCatalogClient(
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

        result = align_to_weread(source_2017(), client)

        self.assertEqual(result.intent.weread_status, WeReadStatus.AVAILABLE_ALTERNATIVE)
        self.assertEqual(result.intent.resolution, EditionResolution.ALTERNATIVE_EDITION)
        self.assertTrue(result.match.same_work)
        self.assertFalse(result.match.exact_edition)
        self.assertEqual(result.intent.selected_edition.weread_id, "old")

    def test_first_volume_variant_is_available_alternative_and_requires_confirmation(self) -> None:
        source = Edition(
            title="三体",
            authors=["刘慈欣"],
            publisher="重庆出版社",
            publish_date="2008-01",
            isbn="9787536692930",
            douban_id="2567698",
        )
        client = FakeCatalogClient(
            [
                WeReadSearchCandidate(book_id="set", title="三体全集（全三册）", soldout=False),
                WeReadSearchCandidate(book_id="178677", title="三体1", soldout=False),
            ],
            {
                "set": Edition(
                    title="三体全集（全三册）",
                    authors=["刘慈欣"],
                    weread_id="set",
                ),
                "178677": Edition(
                    title="三体1",
                    authors=["刘慈欣"],
                    publisher="重庆出版社",
                    publish_date="2022-04-01",
                    isbn="9787229166922",
                    weread_id="178677",
                ),
            },
        )

        result = align_to_weread(source, client, limit=10)

        self.assertEqual(result.intent.weread_status, WeReadStatus.AVAILABLE_ALTERNATIVE)
        self.assertEqual(result.intent.resolution, EditionResolution.ALTERNATIVE_EDITION)
        self.assertEqual(result.intent.selected_edition.weread_id, "178677")
        self.assertIsNotNone(result.match)
        assert result.match is not None
        self.assertTrue(result.match.same_work)
        self.assertTrue(result.match.requires_confirmation)
        self.assertIn("first-volume title variant", result.match.reasons)
        self.assertEqual(client.book_calls, ["set", "178677"])

    def test_soldout_same_work_is_unavailable_not_not_found(self) -> None:
        client = FakeCatalogClient(
            [WeReadSearchCandidate(book_id="230107", title="白夜行", soldout=True)],
            {
                "230107": Edition(
                    title="白夜行",
                    authors=["东野圭吾"],
                    isbn="9787544291163",
                    weread_id="230107",
                )
            },
        )

        result = align_to_weread(source_2017(), client)

        self.assertEqual(result.intent.weread_status, WeReadStatus.UNAVAILABLE)
        self.assertEqual(result.intent.resolution, EditionResolution.EXACT_MATCH)
        self.assertEqual(result.intent.selected_edition.weread_id, "230107")
        self.assertIn("soldout=1", result.intent.notes[0])

    def test_no_same_work_is_bounded_not_found(self) -> None:
        client = FakeCatalogClient(
            [WeReadSearchCandidate(book_id="other", title="恶意", soldout=False)],
            {
                "other": Edition(
                    title="恶意",
                    authors=["东野圭吾"],
                    weread_id="other",
                )
            },
        )

        result = align_to_weread(source_2017(), client, limit=3)

        self.assertEqual(result.intent.weread_status, WeReadStatus.NOT_FOUND)
        self.assertEqual(result.intent.resolution, EditionResolution.NO_WEREAD_EDITION)
        self.assertIsNone(result.intent.selected_edition)
        self.assertIn("bounded", result.intent.notes[0])

    def test_later_exact_available_beats_earlier_alternative(self) -> None:
        client = FakeCatalogClient(
            [
                WeReadSearchCandidate(book_id="old", title="白夜行", soldout=False),
                WeReadSearchCandidate(book_id="exact", title="白夜行", soldout=False),
            ],
            {
                "old": Edition(
                    title="白夜行",
                    authors=["东野圭吾"],
                    translators=["刘姿君"],
                    publisher="南海出版公司",
                    publish_date="2013-01",
                    isbn="9787544258609",
                    weread_id="old",
                ),
                "exact": Edition(
                    title="白夜行",
                    authors=["东野圭吾"],
                    translators=["刘姿君"],
                    publisher="南海出版公司",
                    publish_date="2017-07-21",
                    isbn="9787544291163",
                    weread_id="exact",
                ),
            },
        )

        result = align_to_weread(source_2017(), client)

        self.assertEqual(result.intent.weread_status, WeReadStatus.AVAILABLE_EXACT)
        self.assertEqual(result.intent.selected_edition.weread_id, "exact")
        self.assertEqual(client.book_calls, ["old", "exact"])


if __name__ == "__main__":
    unittest.main()
