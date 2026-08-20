from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from douban_weread.storage import IndexedHistoryEntry, IndexedWeReadShelfBook, normalize_history_title


@dataclass(slots=True, frozen=True)
class PossibleStateConflict:
    title: str
    douban_subject_id: str
    douban_state: str
    weread_book_id: str
    weread_finished: bool


@dataclass(slots=True, frozen=True)
class ShelfReconciliationPreview:
    douban_total: int
    weread_total: int
    shared_title_keys: int
    douban_entries_with_exact_title: int
    weread_books_with_exact_title: int
    douban_only_entries: tuple[IndexedHistoryEntry, ...]
    weread_only_books: tuple[IndexedWeReadShelfBook, ...]
    ambiguous_shared_title_keys: int
    possible_state_conflicts: tuple[PossibleStateConflict, ...]


def build_shelf_preview(
    douban_entries: list[IndexedHistoryEntry],
    weread_books: list[IndexedWeReadShelfBook],
) -> ShelfReconciliationPreview:
    """Build a local-only exact-title reconciliation preview.

    Exact normalized title overlap is only a shortlist signal. This function
    intentionally does not claim same Work or same Edition identity and never
    authorizes a mutation.
    """

    douban_by_key: dict[str, list[IndexedHistoryEntry]] = defaultdict(list)
    weread_by_key: dict[str, list[IndexedWeReadShelfBook]] = defaultdict(list)

    for entry in douban_entries:
        key = normalize_history_title(entry.title)
        if key:
            douban_by_key[key].append(entry)

    for book in weread_books:
        key = normalize_history_title(book.title)
        if key:
            weread_by_key[key].append(book)

    shared_keys = set(douban_by_key) & set(weread_by_key)

    douban_matched = {
        entry.subject_id
        for key in shared_keys
        for entry in douban_by_key[key]
    }
    weread_matched = {
        book.book_id
        for key in shared_keys
        for book in weread_by_key[key]
    }

    douban_only = tuple(
        entry for entry in douban_entries if entry.subject_id not in douban_matched
    )
    weread_only = tuple(
        book for book in weread_books if book.book_id not in weread_matched
    )

    ambiguous_keys = sum(
        1
        for key in shared_keys
        if len(douban_by_key[key]) != 1 or len(weread_by_key[key]) != 1
    )

    conflicts: list[PossibleStateConflict] = []
    for key in shared_keys:
        left = douban_by_key[key]
        right = weread_by_key[key]
        if len(left) != 1 or len(right) != 1:
            continue
        douban = left[0]
        weread = right[0]
        if weread.finish_reading and douban.state in {"wish", "do"}:
            conflicts.append(
                PossibleStateConflict(
                    title=douban.title,
                    douban_subject_id=douban.subject_id,
                    douban_state=douban.state,
                    weread_book_id=weread.book_id,
                    weread_finished=True,
                )
            )

    conflicts.sort(key=lambda item: (normalize_history_title(item.title), item.douban_subject_id))

    return ShelfReconciliationPreview(
        douban_total=len(douban_entries),
        weread_total=len(weread_books),
        shared_title_keys=len(shared_keys),
        douban_entries_with_exact_title=len(douban_matched),
        weread_books_with_exact_title=len(weread_matched),
        douban_only_entries=douban_only,
        weread_only_books=weread_only,
        ambiguous_shared_title_keys=ambiguous_keys,
        possible_state_conflicts=tuple(conflicts),
    )
