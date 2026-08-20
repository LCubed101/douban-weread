from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from douban_weread.storage import IndexedHistoryEntry, IndexedWeReadShelfBook, normalize_history_title


_ACTIVE_DOUBAN_STATES = {"wish", "do"}


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
    douban_wish: int
    douban_reading: int
    douban_read: int
    weread_total: int
    weread_finished: int
    weread_with_read_activity: int
    shared_title_keys: int
    active_shared_title_keys: int
    douban_entries_with_exact_title: int
    active_douban_entries_with_exact_title: int
    weread_books_with_exact_title: int
    douban_only_entries: tuple[IndexedHistoryEntry, ...]
    active_douban_only_entries: tuple[IndexedHistoryEntry, ...]
    weread_only_books: tuple[IndexedWeReadShelfBook, ...]
    read_history_overlap_books: tuple[IndexedWeReadShelfBook, ...]
    ambiguous_shared_title_keys: int
    possible_state_conflicts: tuple[PossibleStateConflict, ...]


def build_shelf_preview(
    douban_entries: list[IndexedHistoryEntry],
    weread_books: list[IndexedWeReadShelfBook],
) -> ShelfReconciliationPreview:
    """Build a local-only exact-title reconciliation preview.

    The preview distinguishes current Douban reading intent (WISH / READING)
    from historical READ evidence. A historical READ entry that is absent from
    the current WeRead shelf is not treated as a synchronization gap.

    Exact normalized title overlap remains only a shortlist signal. This
    function intentionally does not claim same Work or same Edition identity
    and never authorizes a mutation.
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
    active_shared_keys = {
        key
        for key in shared_keys
        if any(entry.state in _ACTIVE_DOUBAN_STATES for entry in douban_by_key[key])
    }

    douban_matched = {
        entry.subject_id
        for key in shared_keys
        for entry in douban_by_key[key]
    }
    active_douban_matched = {
        entry.subject_id
        for key in active_shared_keys
        for entry in douban_by_key[key]
        if entry.state in _ACTIVE_DOUBAN_STATES
    }
    weread_matched = {
        book.book_id
        for key in shared_keys
        for book in weread_by_key[key]
    }

    douban_only = tuple(
        entry for entry in douban_entries if entry.subject_id not in douban_matched
    )
    active_douban_only = tuple(
        entry
        for entry in douban_entries
        if entry.state in _ACTIVE_DOUBAN_STATES and entry.subject_id not in active_douban_matched
    )
    weread_only = tuple(
        book for book in weread_books if book.book_id not in weread_matched
    )

    read_history_book_ids = {
        book.book_id
        for key in shared_keys
        if any(entry.state == "collect" for entry in douban_by_key[key])
        for book in weread_by_key[key]
    }
    read_history_overlap = tuple(
        book for book in weread_books if book.book_id in read_history_book_ids
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
        if weread.finish_reading and douban.state in _ACTIVE_DOUBAN_STATES:
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
        douban_wish=sum(entry.state == "wish" for entry in douban_entries),
        douban_reading=sum(entry.state == "do" for entry in douban_entries),
        douban_read=sum(entry.state == "collect" for entry in douban_entries),
        weread_total=len(weread_books),
        weread_finished=sum(book.finish_reading for book in weread_books),
        weread_with_read_activity=sum(
            book.read_update_time is not None and book.read_update_time > 0
            for book in weread_books
        ),
        shared_title_keys=len(shared_keys),
        active_shared_title_keys=len(active_shared_keys),
        douban_entries_with_exact_title=len(douban_matched),
        active_douban_entries_with_exact_title=len(active_douban_matched),
        weread_books_with_exact_title=len(weread_matched),
        douban_only_entries=douban_only,
        active_douban_only_entries=active_douban_only,
        weread_only_books=weread_only,
        read_history_overlap_books=read_history_overlap,
        ambiguous_shared_title_keys=ambiguous_keys,
        possible_state_conflicts=tuple(conflicts),
    )
