from __future__ import annotations

import io
import unittest

from douban_weread.cli import EXIT_NO_RESULTS, EXIT_OK, EXIT_PROVIDER_ERROR, format_edition, run
from douban_weread.core.models import Edition
from douban_weread.providers.douban import DoubanProviderError


class FakeClient:
    def __init__(self) -> None:
        self.title_results: list[Edition] = []
        self.isbn_result: Edition | None = None
        self.raise_error: Exception | None = None
        self.last_title: tuple[str, int] | None = None
        self.last_isbn: str | None = None

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        if self.raise_error:
            raise self.raise_error
        self.last_title = (title, count)
        return self.title_results

    def search_by_isbn(self, isbn: str) -> Edition | None:
        if self.raise_error:
            raise self.raise_error
        self.last_isbn = isbn
        return self.isbn_result


def sample_edition(**overrides: object) -> Edition:
    values: dict[str, object] = {
        "title": "百年孤独",
        "authors": ["加西亚·马尔克斯"],
        "translators": ["范晔"],
        "publisher": "南海出版公司",
        "publish_date": "2011-06",
        "isbn": "9787544253994",
        "douban_id": "6082808",
    }
    values.update(overrides)
    return Edition(**values)  # type: ignore[arg-type]


class CliTests(unittest.TestCase):
    def test_format_edition_contains_version_fields(self) -> None:
        output = format_edition(sample_edition(), index=1)

        self.assertIn("1. 百年孤独", output)
        self.assertIn("Authors: 加西亚·马尔克斯", output)
        self.assertIn("Translators: 范晔", output)
        self.assertIn("南海出版公司 · 2011-06", output)
        self.assertIn("ISBN: 9787544253994", output)
        self.assertIn("https://book.douban.com/subject/6082808/", output)

    def test_title_search_prints_multiple_candidates_and_warning(self) -> None:
        client = FakeClient()
        client.title_results = [
            sample_edition(),
            sample_edition(
                translators=["另一译者"],
                publisher="另一出版社",
                publish_date="2024-01",
                isbn="9780000000000",
                douban_id="9999999",
            ),
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["search", "百年孤独", "--limit", "5"],
            client_factory=lambda: client,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(client.last_title, ("百年孤独", 5))
        self.assertIn("Found 2 candidate editions", stdout.getvalue())
        self.assertIn("Confirm translator, publisher, year, and ISBN", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_isbn_search_prints_exact_result(self) -> None:
        client = FakeClient()
        client.isbn_result = sample_edition()
        stdout = io.StringIO()

        code = run(
            ["search", "--isbn", "978-7-5442-5399-4"],
            client_factory=lambda: client,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(client.last_isbn, "978-7-5442-5399-4")
        self.assertIn("Exact ISBN result", stdout.getvalue())
        self.assertIn("百年孤独", stdout.getvalue())

    def test_no_results_returns_stable_exit_code(self) -> None:
        client = FakeClient()
        stdout = io.StringIO()

        code = run(
            ["search", "不存在的书"],
            client_factory=lambda: client,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_NO_RESULTS)
        self.assertIn("No Douban editions found", stdout.getvalue())

    def test_provider_error_is_sent_to_stderr(self) -> None:
        client = FakeClient()
        client.raise_error = DoubanProviderError("network unavailable")
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["search", "百年孤独"],
            client_factory=lambda: client,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_PROVIDER_ERROR)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("network unavailable", stderr.getvalue())

    def test_limit_is_clamped(self) -> None:
        client = FakeClient()

        code = run(
            ["search", "百年孤独", "--limit", "999"],
            client_factory=lambda: client,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_NO_RESULTS)
        self.assertEqual(client.last_title, ("百年孤独", 100))


if __name__ == "__main__":
    unittest.main()
