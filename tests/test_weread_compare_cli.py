from __future__ import annotations

import io
import unittest

from douban_weread.core.models import Edition
from douban_weread.providers.douban import DoubanProviderError
from douban_weread.providers.weread import WeReadProviderError
from douban_weread.weread_cli import EXIT_OK, EXIT_PROVIDER_ERROR, run


class FakeDoubanClient:
    def __init__(self, edition: Edition | None = None, error: Exception | None = None) -> None:
        self.edition = edition
        self.error = error
        self.calls: list[str] = []

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        self.calls.append(subject_id)
        if self.error:
            raise self.error
        return self.edition


class FakeWeReadClient:
    def __init__(self, edition: Edition | None = None, error: Exception | None = None) -> None:
        self.edition = edition
        self.error = error
        self.calls: list[str] = []

    def get_book(self, book_id: str) -> Edition | None:
        self.calls.append(book_id)
        if self.error:
            raise self.error
        return self.edition

    def search_books(self, keyword: str, *, count: int = 10):
        raise AssertionError("search should not be called")


class WeReadCompareCliTests(unittest.TestCase):
    def test_exact_isbn_comparison_reports_exact_edition(self) -> None:
        douban = FakeDoubanClient(
            Edition(
                title="白夜行",
                authors=["[日] 东野圭吾"],
                translators=["刘姿君"],
                publisher="南海出版公司",
                publish_date="2017-07",
                isbn="9787544291163",
                douban_id="27112607",
            )
        )
        weread = FakeWeReadClient(
            Edition(
                title="白夜行",
                authors=["东野圭吾"],
                translators=["刘姿君"],
                publisher="南海出版公司",
                publish_date="2017-07-21",
                isbn="9787544291163",
                weread_id="230107",
            )
        )
        stdout = io.StringIO()

        code = run(
            ["compare", "--subject", "27112607", "--id", "230107"],
            client_factory=lambda: weread,
            douban_client_factory=lambda: douban,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(douban.calls, ["27112607"])
        self.assertEqual(weread.calls, ["230107"])
        output = stdout.getvalue()
        self.assertIn("Match: exact_edition", output)
        self.assertIn("Same Work: True", output)
        self.assertIn("Exact Edition: True", output)
        self.assertIn("Requires confirmation: False", output)
        self.assertIn("Safe to auto align: True", output)
        self.assertIn("Reasons: exact ISBN match", output)
        self.assertIn("Availability: not assigned", output)

    def test_different_isbn_same_work_reports_alternative_edition(self) -> None:
        douban = FakeDoubanClient(
            Edition(
                title="白夜行",
                authors=["东野圭吾"],
                translators=["刘姿君"],
                publisher="南海出版公司",
                publish_date="2013-01",
                isbn="9787544258609",
                douban_id="10554308",
            )
        )
        weread = FakeWeReadClient(
            Edition(
                title="白夜行",
                authors=["东野圭吾"],
                translators=["刘姿君"],
                publisher="南海出版公司",
                publish_date="2017-07-21",
                isbn="9787544291163",
                weread_id="230107",
            )
        )
        stdout = io.StringIO()

        code = run(
            ["compare", "--subject", "10554308", "--id", "230107"],
            client_factory=lambda: weread,
            douban_client_factory=lambda: douban,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        output = stdout.getvalue()
        self.assertIn("Match: alternative_edition", output)
        self.assertIn("Same Work: True", output)
        self.assertIn("Exact Edition: False", output)
        self.assertIn("Safe to auto align: False", output)
        self.assertIn("Edition differences: ISBN differs; publication year differs", output)

    def test_provider_failures_remain_distinct_and_fail_closed(self) -> None:
        douban_error = io.StringIO()
        code = run(
            ["compare", "--subject", "27112607", "--id", "230107"],
            client_factory=lambda: FakeWeReadClient(Edition(title="白夜行")),
            douban_client_factory=lambda: FakeDoubanClient(error=DoubanProviderError("blocked")),
            stdout=io.StringIO(),
            stderr=douban_error,
        )
        self.assertEqual(code, EXIT_PROVIDER_ERROR)
        self.assertIn("Douban provider error: blocked", douban_error.getvalue())

        weread_error = io.StringIO()
        code = run(
            ["compare", "--subject", "27112607", "--id", "230107"],
            client_factory=lambda: FakeWeReadClient(error=WeReadProviderError("gateway failed")),
            douban_client_factory=lambda: FakeDoubanClient(Edition(title="白夜行")),
            stdout=io.StringIO(),
            stderr=weread_error,
        )
        self.assertEqual(code, EXIT_PROVIDER_ERROR)
        self.assertIn("WeRead provider error: gateway failed", weread_error.getvalue())


if __name__ == "__main__":
    unittest.main()
