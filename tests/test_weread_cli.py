from __future__ import annotations

import io
import unittest

from douban_weread.providers.weread import WeReadProviderError, WeReadSearchCandidate
from douban_weread.weread_cli import EXIT_NO_RESULTS, EXIT_OK, EXIT_PROVIDER_ERROR, run


class FakeWeReadClient:
    def __init__(self, results: list[WeReadSearchCandidate] | None = None, error: Exception | None = None) -> None:
        self.results = results or []
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        self.calls.append((keyword, count))
        if self.error:
            raise self.error
        return self.results


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
        self.assertEqual(client.calls, [("白夜行", 5)])
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
        self.assertEqual(client.calls, [("三体", 100)])


if __name__ == "__main__":
    unittest.main()
