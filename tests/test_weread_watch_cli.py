from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from douban_weread.core.models import Edition
from douban_weread.inbox_weread import WeReadLookupKind, WeReadLookupResult
from douban_weread.storage.weread_watch import WeReadAvailabilityWatchStore
from douban_weread.weread_watch_cli import run


class FakeLookup:
    def __init__(self, result: WeReadLookupResult) -> None:
        self.result = result
        self.calls: list[Edition] = []

    def lookup(self, source: Edition) -> WeReadLookupResult:
        self.calls.append(source)
        return self.result


class WeReadWatchCliTests(unittest.TestCase):
    def test_list_shows_pending_watch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WeReadAvailabilityWatchStore(Path(tmp) / "watch.sqlite3")
            store.add_or_refresh(
                chat_id="oc_chat",
                source=Edition(
                    title="非普通读者",
                    authors=["艾伦·贝内特"],
                    douban_id="123",
                    isbn="9780000000001",
                ),
                weread=Edition(title="非普通读者", weread_id="wr1"),
                deep_link="weread://example",
            )
            stdout = io.StringIO()
            code = run(["list"], store=store, stdout=stdout)

        self.assertEqual(code, 0)
        self.assertIn("Pending WeRead availability watches: 1", stdout.getvalue())
        self.assertIn("非普通读者", stdout.getvalue())
        self.assertIn("bookId wr1", stdout.getvalue())

    def test_check_marks_newly_readable_watch_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WeReadAvailabilityWatchStore(Path(tmp) / "watch.sqlite3")
            store.add_or_refresh(
                chat_id="oc_chat",
                source=Edition(
                    title="非普通读者",
                    authors=["艾伦·贝内特"],
                    publisher="出版社",
                    publish_date="2020-01",
                    douban_id="123",
                ),
                weread=Edition(title="非普通读者", weread_id="old"),
                deep_link=None,
            )
            available = Edition(
                title="非普通读者",
                authors=["艾伦·贝内特"],
                weread_id="new",
            )
            lookup = FakeLookup(
                WeReadLookupResult(
                    kind=WeReadLookupKind.ALTERNATIVE,
                    source_title="非普通读者",
                    selected_edition=available,
                    deep_link="weread://read",
                    message="available",
                )
            )
            stdout = io.StringIO()
            code = run(["check"], store=store, lookup=lookup, stdout=stdout)
            pending_after = store.pending()

        self.assertEqual(code, 0)
        self.assertEqual(len(lookup.calls), 1)
        self.assertEqual(lookup.calls[0].authors, ["艾伦·贝内特"])
        self.assertEqual(lookup.calls[0].publisher, "出版社")
        self.assertEqual(pending_after, [])
        self.assertIn("AVAILABLE (alternative Edition)", stdout.getvalue())
        self.assertIn("1 newly available, 0 still pending", stdout.getvalue())

    def test_check_keeps_unavailable_watch_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WeReadAvailabilityWatchStore(Path(tmp) / "watch.sqlite3")
            source = Edition(title="非普通读者", authors=["艾伦·贝内特"], douban_id="123")
            unavailable = Edition(title="非普通读者", weread_id="wr1")
            store.add_or_refresh(
                chat_id="oc_chat",
                source=source,
                weread=unavailable,
                deep_link=None,
            )
            lookup = FakeLookup(
                WeReadLookupResult(
                    kind=WeReadLookupKind.UNAVAILABLE,
                    source_title=source.title,
                    selected_edition=unavailable,
                    deep_link=None,
                    message="unavailable",
                )
            )
            stdout = io.StringIO()
            code = run(["check"], store=store, lookup=lookup, stdout=stdout)
            pending_after = store.pending()

        self.assertEqual(code, 0)
        self.assertEqual(len(pending_after), 1)
        self.assertIn("still unavailable", stdout.getvalue())
        self.assertIn("0 newly available, 1 still pending", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
