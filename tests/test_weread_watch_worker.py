from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from douban_weread.core.models import Edition
from douban_weread.inbox_weread import WeReadLookupKind, WeReadLookupResult
from douban_weread.providers.weread.shelf import WeReadShelfBook, WeReadShelfSnapshot
from douban_weread.storage.weread_watch import WeReadAvailabilityWatchStore
from douban_weread.weread_watch_worker import WeReadWatchWorker


class FakeLookup:
    def __init__(self, result: WeReadLookupResult) -> None:
        self.result = result
        self.calls: list[Edition] = []

    def lookup(self, source: Edition) -> WeReadLookupResult:
        self.calls.append(source)
        return self.result


class FakeShelf:
    def __init__(self, ids: list[str]) -> None:
        self.ids = ids
        self.calls = 0

    def sync_shelf(self) -> WeReadShelfSnapshot:
        self.calls += 1
        return WeReadShelfSnapshot(
            books=tuple(WeReadShelfBook(book_id=value, title=value) for value in self.ids),
            album_count=0,
            has_mp=False,
        )


class WeReadWatchWorkerTests(unittest.TestCase):
    def test_available_transition_emits_notification_and_waits_for_ack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WeReadAvailabilityWatchStore(Path(tmp) / "watch.sqlite3")
            source = Edition(title="非普通读者", douban_id="4934784", isbn="9787544714204")
            store.add_or_refresh(chat_id="oc_chat", source=source, weread=None, deep_link=None)
            readable = Edition(title="非普通读者", weread_id="wr1")
            worker = WeReadWatchWorker(
                store=store,
                lookup=FakeLookup(
                    WeReadLookupResult(
                        kind=WeReadLookupKind.ALTERNATIVE,
                        source_title=source.title,
                        selected_edition=readable,
                        deep_link="https://weread.qq.com/wr1",
                        message="readable",
                    )
                ),
                shelf_provider=FakeShelf([]),
            )

            notices = worker.run_once()

            self.assertEqual(len(notices), 1)
            self.assertIn("已经可以读了", notices[0].text)
            self.assertIn("暂未检测到", notices[0].text)
            self.assertEqual(len(store.pending()), 0)
            self.assertEqual(len(store.unnotified_available()), 1)

            worker.acknowledge(notices[0])
            self.assertEqual(store.unnotified_available(), [])

    def test_existing_unnotified_available_is_retried_without_relookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WeReadAvailabilityWatchStore(Path(tmp) / "watch.sqlite3")
            source = Edition(title="书", douban_id="1")
            entry = store.add_or_refresh(chat_id="oc_chat", source=source, weread=None, deep_link=None)
            readable = Edition(title="书", weread_id="wr1")
            store.mark_available(entry.id, weread=readable, deep_link=None)
            lookup = FakeLookup(
                WeReadLookupResult(
                    kind=WeReadLookupKind.NOT_FOUND,
                    source_title="书",
                    selected_edition=None,
                    deep_link=None,
                    message="not found",
                )
            )
            worker = WeReadWatchWorker(store=store, lookup=lookup, shelf_provider=FakeShelf(["wr1"]))

            notices = worker.run_once()

            self.assertEqual(lookup.calls, [])
            self.assertEqual(len(notices), 1)
            self.assertIn("已经在你的微信读书书架", notices[0].text)

    def test_still_pending_emits_no_notification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WeReadAvailabilityWatchStore(Path(tmp) / "watch.sqlite3")
            source = Edition(title="非普通读者", douban_id="4934784")
            store.add_or_refresh(chat_id="oc_chat", source=source, weread=None, deep_link=None)
            worker = WeReadWatchWorker(
                store=store,
                lookup=FakeLookup(
                    WeReadLookupResult(
                        kind=WeReadLookupKind.NOT_FOUND,
                        source_title=source.title,
                        selected_edition=None,
                        deep_link=None,
                        message="not found",
                    )
                ),
                shelf_provider=FakeShelf([]),
            )

            self.assertEqual(worker.run_once(), [])
            self.assertEqual(len(store.pending()), 1)


if __name__ == "__main__":
    unittest.main()
