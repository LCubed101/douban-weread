from __future__ import annotations

import io
import unittest

from douban_weread.core.models import Edition
from douban_weread.providers.weread import WeReadProviderError, WeReadSearchCandidate
from douban_weread.weread_cli import EXIT_NO_RESULTS, EXIT_OK, EXIT_PROVIDER_ERROR, run


class FakeWeReadClient:
    def __init__(
        self,
        results: list[WeReadSearchCandidate] | None = None,
        book: Edition | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = results or []
        self.book = book
        self.error = error
        self.search_calls: list[tuple[str, int]] = []
        self.book_calls: list[str] = []

    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        self.search_calls.append((keyword, count))
        if self.error:
            raise self.error
        return self.results

    def get_book(self, book_id: str) -> Edition | None:
        self.book_calls.append(book_id)
        if self.error:
            raise self.error
        return self.book


class WeReadCliTests(unittest.TestCase):
    def test_search_prints_catalog_candidates_without_claiming_readability(self) -> None:
        client = FakeWeReadClient(
            [
                WeReadSearchCandidate(
                    book_id="12345",
                    title="白夜行",
                    author="[日] 东野圭吾",
                    publisher="南海出版公司",
                    soldout=False,
                    deep_link="weread://reading?bId=12345",
                )
            ]
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["search", "白夜行", "--limit", "5"],
            client_factory=lambda: client,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(client.search_calls, [("白夜行", 5)])
        output = stdout.getvalue()
        self.assertIn('WeRead e-book candidates for "白夜行"', output)
        self.assertIn("1. 白夜行", output)
        self.assertIn("WeRead bookId: 12345", output)
        self.assertIn("Sold out: no", output)
        self.assertIn("catalog candidates only", output)
        self.assertNotIn("AVAILABLE_EXACT", output)
        self.assertEqual(stderr.getvalue(), "")

    def test_search_marks_soldout_candidate_without_dropping_it(self) -> None:
        client = FakeWeReadClient(
            [WeReadSearchCandidate(book_id="9", title="下架书", soldout=True)]
        )
        stdout = io.StringIO()

        code = run(
            ["search", "下架书"],
            client_factory=lambda: client,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        self.assertIn("Sold out: yes", stdout.getvalue())

    def test_no_results_is_distinct_from_provider_failure(self) -> None:
        client = FakeWeReadClient([])
        stdout = io.StringIO()

        code = run(
            ["search", "不存在的书"],
            client_factory=lambda: client,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_NO_RESULTS)
        self.assertIn("No WeRead e-book candidates found", stdout.getvalue())

    def test_provider_error_fails_closed(self) -> None:
        client = FakeWeReadClient(error=WeReadProviderError("gateway unavailable"))
        stderr = io.StringIO()

        code = run(
            ["search", "三体"],
            client_factory=lambda: client,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_PROVIDER_ERROR)
        self.assertIn("WeRead provider error: gateway unavailable", stderr.getvalue())

    def test_limit_is_clamped(self) -> None:
        client = FakeWeReadClient([])
        run(
            ["search", "三体", "--limit", "1000"],
            client_factory=lambda: client,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        self.assertEqual(client.search_calls, [("三体", 100)])

    def test_book_prints_normalized_edition_metadata(self) -> None:
        client = FakeWeReadClient(
            book=Edition(
                title="白夜行",
                authors=["东野圭吾"],
                translators=["刘姿君"],
                publisher="南海出版公司",
                publish_date="2013-01",
                isbn="9787544258609",
                weread_id="230107",
                source_metadata={"deep_link": "https://weread.qq.com/book-detail?type=1&v=test"},
            )
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["book", "--id", "230107"],
            client_factory=lambda: client,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(client.book_calls, ["230107"])
        output = stdout.getvalue()
        self.assertIn("WeRead book metadata", output)
        self.assertIn("白夜行", output)
        self.assertIn("Translators: 刘姿君", output)
        self.assertIn("Publication: 南海出版公司 · 2013-01", output)
        self.assertIn("ISBN: 9787544258609", output)
        self.assertIn("WeRead bookId: 230107", output)
        self.assertIn("availability classification still requires resolver evidence", output)
        self.assertEqual(stderr.getvalue(), "")

    def test_book_missing_metadata_returns_no_results(self) -> None:
        client = FakeWeReadClient(book=None)
        stdout = io.StringIO()

        code = run(
            ["book", "--id", "missing"],
            client_factory=lambda: client,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_NO_RESULTS)
        self.assertEqual(client.book_calls, ["missing"])
        self.assertIn("No WeRead book metadata found", stdout.getvalue())

    def test_book_provider_error_fails_closed(self) -> None:
        client = FakeWeReadClient(error=WeReadProviderError("book lookup failed"))
        stderr = io.StringIO()

        code = run(
            ["book", "--id", "230107"],
            client_factory=lambda: client,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_PROVIDER_ERROR)
        self.assertIn("WeRead provider error: book lookup failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
