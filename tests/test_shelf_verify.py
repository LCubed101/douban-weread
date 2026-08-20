from __future__ import annotations

import unittest

from douban_weread.core.models import Edition
from douban_weread.providers.weread import WeReadProgress
from douban_weread.reconciliation import CrossPlatformStateAction, ReadingState
from douban_weread.reconciliation.shelf_verify import (
    IncompleteShelfVerificationBaselineError,
    verify_shelf_book,
)
from douban_weread.storage import IndexedHistoryEntry, IndexedWeReadShelfBook


class Status:
    def __init__(self, complete: bool) -> None:
        self.complete = complete


class FakeShelf:
    def __init__(self, book: IndexedWeReadShelfBook | None, *, complete: bool = True) -> None:
        self.book = book
        self.complete = complete

    def status(self) -> Status:
        return Status(self.complete)

    def get(self, book_id: str) -> IndexedWeReadShelfBook | None:
        if self.book is not None and self.book.book_id == book_id:
            return self.book
        return None


class FakeHistory:
    def __init__(
        self,
        entries: list[IndexedHistoryEntry] | None = None,
        *,
        shortlist: list[IndexedHistoryEntry] | None = None,
        complete: bool = True,
    ) -> None:
        self.entries = {entry.subject_id: entry for entry in entries or []}
        self.shortlist = shortlist or []
        self.complete = complete

    def status(self) -> Status:
        return Status(self.complete)

    def get(self, subject_id: str) -> IndexedHistoryEntry | None:
        return self.entries.get(subject_id)

    def find_title_candidates(
        self,
        title: str,
        *,
        limit: int = 30,
        min_similarity: float = 0.72,
    ) -> list[IndexedHistoryEntry]:
        _ = title, min_similarity
        return self.shortlist[:limit]


class FakeWeRead:
    def __init__(self, edition: Edition, progress: WeReadProgress) -> None:
        self.edition = edition
        self.progress = progress

    def get_book(self, book_id: str) -> Edition | None:
        return self.edition if self.edition.weread_id == book_id else None

    def get_progress(self, book_id: str) -> WeReadProgress | None:
        return self.progress if self.progress.book_id == book_id else None


class FakeDouban:
    def __init__(
        self,
        search_results: list[Edition],
        *,
        by_subject: dict[str, Edition] | None = None,
    ) -> None:
        self.search_results = search_results
        self.by_subject = by_subject or {}
        self.search_counts: list[int] = []
        self.subject_fetches: list[str] = []

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        _ = title
        self.search_counts.append(count)
        return self.search_results[:count]

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        self.subject_fetches.append(subject_id)
        return self.by_subject.get(subject_id)


def shelf_book(book_id: str = "10", title: str = "同一本书") -> IndexedWeReadShelfBook:
    return IndexedWeReadShelfBook(
        book_id=book_id,
        title=title,
        author="作者",
        deep_link=None,
        category=None,
        finish_reading=False,
        read_update_time=123,
        secret=False,
        title_key="同一本书",
        last_seen_at="2026-08-20T00:00:00+00:00",
    )


def history(subject_id: str, title: str, state: str) -> IndexedHistoryEntry:
    return IndexedHistoryEntry(
        subject_id=subject_id,
        title=title,
        state=state,
        title_key=title,
        last_seen_at="2026-08-20T00:00:00+00:00",
    )


def weread_edition(*, isbn: str = "9780000000001") -> Edition:
    return Edition(
        title="同一本书",
        authors=["作者"],
        publisher="出版社A",
        publish_date="2025-01-01",
        isbn=isbn,
        weread_id="10",
    )


def douban_edition(
    subject_id: str = "100",
    *,
    isbn: str = "9780000000001",
    publisher: str = "出版社A",
) -> Edition:
    return Edition(
        title="同一本书",
        authors=["作者"],
        publisher=publisher,
        publish_date="2025-01-01",
        isbn=isbn,
        douban_id=subject_id,
    )


class ShelfVerificationTests(unittest.TestCase):
    def test_exact_unread_work_with_no_douban_history_suggests_wish(self) -> None:
        result = verify_shelf_book(
            "10",
            shelf_provider=FakeShelf(shelf_book()),
            history_provider=FakeHistory(),
            weread_provider=FakeWeRead(
                weread_edition(),
                WeReadProgress(book_id="10", progress=0, is_started=False),
            ),
            douban_provider=FakeDouban([douban_edition()]),
        )

        self.assertIsNotNone(result.best_match)
        assert result.best_match is not None
        self.assertTrue(result.best_match.match.exact_edition)
        self.assertEqual(result.strongest_douban_state, ReadingState.NONE)
        self.assertEqual(result.decision.action, CrossPlatformStateAction.SUGGEST_WISH)
        self.assertEqual(result.decision.suggested_douban_state, ReadingState.WISH)
        self.assertFalse(result.decision.safe_to_auto_apply)

    def test_exact_reading_work_with_douban_wish_suggests_reading(self) -> None:
        saved = history("100", "同一本书", "wish")
        result = verify_shelf_book(
            "10",
            shelf_provider=FakeShelf(shelf_book()),
            history_provider=FakeHistory([saved]),
            weread_provider=FakeWeRead(
                weread_edition(),
                WeReadProgress(book_id="10", progress=37, is_started=True),
            ),
            douban_provider=FakeDouban([douban_edition()]),
        )

        self.assertEqual(result.strongest_douban_state, ReadingState.WISH)
        self.assertEqual(result.decision.action, CrossPlatformStateAction.SUGGEST_READING)
        self.assertEqual(result.decision.suggested_douban_state, ReadingState.READING)

    def test_same_work_alternative_read_history_turns_active_reading_into_reread_review(self) -> None:
        saved = history("200", "同一本书", "collect")
        alternative = douban_edition("200", isbn="9780000000002", publisher="出版社B")
        result = verify_shelf_book(
            "10",
            shelf_provider=FakeShelf(shelf_book()),
            history_provider=FakeHistory([saved]),
            weread_provider=FakeWeRead(
                weread_edition(),
                WeReadProgress(book_id="10", progress=20, is_started=True),
            ),
            douban_provider=FakeDouban([alternative]),
        )

        self.assertIsNotNone(result.best_match)
        assert result.best_match is not None
        self.assertTrue(result.best_match.match.same_work)
        self.assertFalse(result.best_match.match.exact_edition)
        self.assertEqual(result.strongest_douban_state, ReadingState.READ)
        self.assertEqual(result.decision.action, CrossPlatformStateAction.ASK_REREAD)
        self.assertEqual(result.decision.suggested_douban_state, ReadingState.READ)

    def test_history_shortlist_can_restore_same_work_read_evidence_missing_from_live_search(self) -> None:
        saved = history("200", "同一本书", "collect")
        alternative = douban_edition("200", isbn="9780000000002", publisher="出版社B")
        douban = FakeDouban([], by_subject={"200": alternative})

        result = verify_shelf_book(
            "10",
            shelf_provider=FakeShelf(shelf_book()),
            history_provider=FakeHistory([saved], shortlist=[saved]),
            weread_provider=FakeWeRead(
                weread_edition(),
                WeReadProgress(book_id="10", progress=0, is_started=False),
            ),
            douban_provider=douban,
        )

        self.assertEqual(douban.subject_fetches, ["200"])
        self.assertEqual(result.strongest_douban_state, ReadingState.READ)
        self.assertEqual(result.decision.action, CrossPlatformStateAction.KEEP_HIGHER_DOUBAN_STATE)

    def test_no_verified_same_work_fails_closed_to_identity_review(self) -> None:
        different = Edition(
            title="同一本书",
            authors=["另一个作者"],
            douban_id="999",
        )
        result = verify_shelf_book(
            "10",
            shelf_provider=FakeShelf(shelf_book()),
            history_provider=FakeHistory(),
            weread_provider=FakeWeRead(
                weread_edition(),
                WeReadProgress(book_id="10", progress=0, is_started=False),
            ),
            douban_provider=FakeDouban([different]),
        )

        self.assertEqual(result.verified_douban_candidates, ())
        self.assertEqual(result.decision.action, CrossPlatformStateAction.REVIEW_IDENTITY)
        self.assertTrue(result.decision.requires_user_decision)

    def test_complete_both_baselines_are_required_before_network_verification(self) -> None:
        with self.assertRaises(IncompleteShelfVerificationBaselineError):
            verify_shelf_book(
                "10",
                shelf_provider=FakeShelf(shelf_book(), complete=False),
                history_provider=FakeHistory(),
                weread_provider=FakeWeRead(
                    weread_edition(),
                    WeReadProgress(book_id="10", progress=0, is_started=False),
                ),
                douban_provider=FakeDouban([]),
            )


if __name__ == "__main__":
    unittest.main()
