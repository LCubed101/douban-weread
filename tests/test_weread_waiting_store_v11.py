from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from douban_weread.core.models import Edition
from douban_weread.storage.weread_watch import WeReadAvailabilityWatchStore


class WeReadWaitingStoreV11Test(unittest.TestCase):
    def test_waiting_and_not_found_get_different_due_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WeReadAvailabilityWatchStore(Path(tmp) / "watch.sqlite3")
            waiting = store.add_or_refresh(
                chat_id="chat",
                source=Edition(title="如何改变世界"),
                weread=Edition(title="如何改变世界", weread_id="book-1"),
                deep_link="https://weread.qq.com/book-1",
                watch_kind="waiting",
            )
            missing = store.add_or_refresh(
                chat_id="chat",
                source=Edition(title="不存在的测试书"),
                weread=None,
                deep_link=None,
                watch_kind="not_found",
            )

            self.assertEqual(waiting.watch_kind, "waiting")
            self.assertEqual(missing.watch_kind, "not_found")
            self.assertIsNotNone(waiting.next_check_at)
            self.assertIsNotNone(missing.next_check_at)
            waiting_due = datetime.fromisoformat(waiting.next_check_at)
            missing_due = datetime.fromisoformat(missing.next_check_at)
            self.assertGreater((missing_due - waiting_due).days, 50)

    def test_new_rows_are_not_due_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WeReadAvailabilityWatchStore(Path(tmp) / "watch.sqlite3")
            store.add_or_refresh(
                chat_id="chat",
                source=Edition(title="如何改变世界"),
                weread=None,
                deep_link=None,
                watch_kind="not_found",
            )
            self.assertEqual(store.due_pending(now=datetime.now(timezone.utc)), [])


if __name__ == "__main__":
    unittest.main()
