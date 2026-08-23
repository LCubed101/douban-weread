from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from douban_weread.core.models import Edition
from douban_weread.storage.weread_watch import WeReadAvailabilityWatchStore


class WeReadAvailabilityWatchStoreTests(unittest.TestCase):
    def test_adds_pending_watch_without_credentials_or_raw_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WeReadAvailabilityWatchStore(Path(tmp) / "watch.sqlite3")
            source = Edition(
                title="非普通读者",
                authors=["艾伦·贝内特"],
                publisher="译林出版社",
                publish_date="2010-10",
                isbn="9787544714204",
                douban_id="123456",
            )
            weread = Edition(
                title="非普通读者",
                authors=["艾伦·贝内特"],
                publisher="广西师范大学出版社",
                publish_date="2015-05",
                isbn="9787549564484",
                weread_id="wr-book",
            )
            entry = store.add_or_refresh(
                chat_id="oc_chat",
                source=source,
                weread=weread,
                deep_link="https://weread.qq.com/example",
            )
            self.assertEqual(entry.status, "pending")
            self.assertEqual(entry.weread_book_id, "wr-book")
            self.assertEqual(len(store.pending()), 1)

    def test_refresh_does_not_duplicate_same_chat_and_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WeReadAvailabilityWatchStore(Path(tmp) / "watch.sqlite3")
            source = Edition(title="非普通读者", douban_id="123456")
            first = store.add_or_refresh(
                chat_id="oc_chat",
                source=source,
                weread=Edition(title="非普通读者", weread_id="old"),
                deep_link=None,
            )
            second = store.add_or_refresh(
                chat_id="oc_chat",
                source=source,
                weread=Edition(title="非普通读者", weread_id="new"),
                deep_link="https://weread.qq.com/new",
            )
            pending = store.pending()
            self.assertEqual(first.id, second.id)
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0].weread_book_id, "new")

    def test_same_source_in_different_chats_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WeReadAvailabilityWatchStore(Path(tmp) / "watch.sqlite3")
            source = Edition(title="非普通读者", douban_id="123456")
            store.add_or_refresh(chat_id="chat_a", source=source, weread=None, deep_link=None)
            store.add_or_refresh(chat_id="chat_b", source=source, weread=None, deep_link=None)
            self.assertEqual([item.chat_id for item in store.pending()], ["chat_a", "chat_b"])


if __name__ == "__main__":
    unittest.main()
