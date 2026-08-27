from __future__ import annotations

import unittest
from datetime import datetime, timezone

from douban_weread.storage.weread_waiting_policy import next_check_at


class WeReadWaitingPolicyTest(unittest.TestCase):
    def test_waiting_rechecks_after_30_days(self) -> None:
        now = datetime(2026, 8, 27, tzinfo=timezone.utc)
        self.assertTrue(next_check_at(watch_kind="waiting", now=now).startswith("2026-09-26"))

    def test_not_found_rechecks_after_90_days(self) -> None:
        now = datetime(2026, 8, 27, tzinfo=timezone.utc)
        self.assertTrue(next_check_at(watch_kind="not_found", now=now).startswith("2026-11-25"))


if __name__ == "__main__":
    unittest.main()
