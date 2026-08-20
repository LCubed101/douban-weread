from __future__ import annotations

import io
import unittest

from douban_weread.core.models import Edition
from douban_weread.providers.weread import WeReadSearchCandidate
from douban_weread.weread_cli import EXIT_OK, run


class FakeDoubanClient:
    def __init__(self, edition: Edition | None) -> None:
        self.edition = edition
        self.calls: list[str] = []

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        self.calls.append(subject_id)
        return self.edition


class FakeWeReadClient:
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


class WeReadResolveCliTests(unittest.TestCase):
    def test_resolve_prints_available_exact_reading_intent(self) -> None:
        source = Edition(
            title="白夜行",
            authors=["[日] 东野圭吾"],
            translators=["刘姿君"],
            publisher="南海出版公司",
            publish_date="2017-07",
            isbn="9787544291163",
            douban_id="27112607",
        )
        weread = Edition(
            title="白夜行",
            authors=["东野圭吾"],
            translators=["刘姿君"],
            publisher="南海出版公司",
            publish_date="2017-07-21",
            isbn="9787544291163",
            weread_id="230107",
        )
        weread_client = FakeWeReadClient(
            [
                WeReadSearchCandidate(
                    book_id="230107",
                    title="白夜行",
                    soldout=False,
                    deep_link="https://weread.qq.com/book-detail?exact",
                )
            ],
            {"230107": weread},
        )
        douban_client = FakeDoubanClient(source)
        stdout = io.StringIO()

        code = run(
            ["resolve", "--subject", "27112607", "--limit", "5"],
            client_factory=lambda: weread_client,
            douban_client_factory=lambda: douban_client,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        output = stdout.getvalue()
        self.assertIn("Cross-platform ReadingIntent", output)
        self.assertIn("WeRead status: available_exact", output)
        self.assertIn("Resolution: exact_match", output)
        self.assertIn("WeRead bookId: 230107", output)
        self.assertIn("Search sold out: no", output)
        self.assertIn("Match: exact_edition", output)
        self.assertIn("Reasons: exact ISBN match", output)
        self.assertEqual(douban_client.calls, ["27112607"])
        self.assertEqual(weread_client.search_calls, [("白夜行", 5)])
        self.assertEqual(weread_client.book_calls, ["230107"])

    def test_resolve_preserves_bounded_not_found_semantics(self) -> None:
        source = Edition(
            title="白夜行",
            authors=["东野圭吾"],
            isbn="9787544291163",
            douban_id="27112607",
        )
        weread_client = FakeWeReadClient(
            [WeReadSearchCandidate(book_id="other", title="恶意", soldout=False)],
            {"other": Edition(title="恶意", authors=["东野圭吾"], weread_id="other")},
        )
        stdout = io.StringIO()

        code = run(
            ["resolve", "--subject", "27112607", "--limit", "1"],
            client_factory=lambda: weread_client,
            douban_client_factory=lambda: FakeDoubanClient(source),
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        output = stdout.getvalue()
        self.assertIn("WeRead status: not_found", output)
        self.assertIn("Resolution: no_weread_edition", output)
        self.assertIn("bounded by the configured search policy", output)


if __name__ == "__main__":
    unittest.main()
