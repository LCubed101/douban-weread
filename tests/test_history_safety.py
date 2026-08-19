from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.storage import ReadingHistoryIndex


class ReadingHistorySafetyTests(unittest.TestCase):
    def test_conflicting_remote_states_do_not_replace_good_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = ReadingHistoryIndex(Path(tmp) / "history.sqlite3")
            index.replace_full([HistoryEntry("1", "原有记录", "collect")])

            with self.assertRaisesRegex(ValueError, "conflicting history states"):
                index.replace_full(
                    [
                        HistoryEntry("2", "冲突记录", "wish"),
                        HistoryEntry("2", "冲突记录", "collect"),
                    ]
                )

            original = index.get("1")
            self.assertIsNotNone(original)
            assert original is not None
            self.assertEqual(original.state, "collect")
            self.assertIsNone(index.get("2"))


if __name__ == "__main__":
    unittest.main()
