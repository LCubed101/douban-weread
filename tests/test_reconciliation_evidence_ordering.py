from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from douban_weread.core.models import Edition
from douban_weread.providers.douban.history import HistoryEntry
from douban_weread.providers.weread import WeReadProgress, WeReadSearchCandidate, WeReadShelfSnapshot
from douban_weread.reconciliation import DOUBAN_TO_WEREAD, run_reconciliation_batch
from douban_weread.storage import (
    ReadingHistoryIndex,
    ReconciliationCheckpointStore,
    WeReadShelfIndex,
)


class ExactDouban:
    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        return Edition(
            title="测试书",
            authors=["作者"],
            isbn="9780000005001",
            douban_id=subject_id,
        )

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        raise AssertionError("title search is not used")


class ExactWeRead:
    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]:
        return [
            WeReadSearchCandidate(
                book_id="9001",
                title="测试书",
                author="作者",
                soldout=False,
            )
        ]

    def get_book(self, book_id: str) -> Edition | None:
        return Edition(
            title="测试书",
            authors=["作者"],
            isbn="9780000005001",
            weread_id=book_id,
        )

    def get_progress(self, book_id: str) -> WeReadProgress | None:
        raise AssertionError("progress is not used")


class FailingEvidenceStore:
    def list_generation(self, direction: str, **kwargs):
        return []

    def upsert(self, evidence) -> None:
        raise RuntimeError("simulated evidence write failure")


class ReconciliationEvidenceOrderingTests(unittest.TestCase):
    def test_evidence_failure_happens_before_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "history.sqlite3"
            shelf = WeReadShelfIndex(path)
            history = ReadingHistoryIndex(path)
            checkpoints = ReconciliationCheckpointStore(path)
            shelf.replace_full(
                WeReadShelfSnapshot(books=(), album_count=0, has_mp=False),
                synced_at="shelf-v1",
            )
            history.replace_full(
                [HistoryEntry("5001", "测试书", "wish")],
                synced_at="history-v1",
            )

            with self.assertRaisesRegex(RuntimeError, "evidence write failure"):
                run_reconciliation_batch(
                    DOUBAN_TO_WEREAD,
                    limit=1,
                    shelf_provider=shelf,
                    history_provider=history,
                    checkpoint_provider=checkpoints,
                    evidence_provider=FailingEvidenceStore(),
                    weread_provider=ExactWeRead(),
                    douban_provider=ExactDouban(),
                )

            self.assertEqual(
                checkpoints.completed_ids(
                    DOUBAN_TO_WEREAD,
                    shelf_sync_at="shelf-v1",
                    history_sync_at="history-v1",
                    policy_version=3,
                ),
                set(),
            )


if __name__ == "__main__":
    unittest.main()
