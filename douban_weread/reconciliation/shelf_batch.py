from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from douban_weread.alignment import WeReadAlignmentResult, align_to_weread
from douban_weread.core.models import Edition
from douban_weread.providers.weread import WeReadProgress, WeReadSearchCandidate
from douban_weread.reconciliation.shelf_preview import build_shelf_preview
from douban_weread.reconciliation.shelf_verify import (
    IncompleteShelfVerificationBaselineError,
    ShelfVerificationResult,
    verify_shelf_book,
)
from douban_weread.storage import (
    IndexedHistoryEntry,
    IndexedWeReadShelfBook,
    ReconciliationCheckpointStore,
    normalize_history_title,
)


WEREAD_TO_DOUBAN = "weread-to-douban"
DOUBAN_TO_WEREAD = "douban-to-weread"
_BATCH_DIRECTIONS = {WEREAD_TO_DOUBAN, DOUBAN_TO_WEREAD}
_MAX_BATCH_SIZE = 5


class BaselineStatus(Protocol):
    complete: bool
    last_full_sync_at: str | None


class ShelfProvider(Protocol):
    def status(self) -> BaselineStatus: ...

    def get(self, book_id: str) -> IndexedWeReadShelfBook | None: ...

    def all_books(self) -> list[IndexedWeReadShelfBook]: ...


class HistoryProvider(Protocol):
    def status(self) -> BaselineStatus: ...

    def get(self, subject_id: str) -> IndexedHistoryEntry | None: ...

    def all_entries(self) -> list[IndexedHistoryEntry]: ...

    def find_title_candidates(
        self,
        title: str,
        *,
        limit: int = 30,
        min_similarity: float = 0.72,
    ) -> list[IndexedHistoryEntry]: ...


class WeReadBatchProvider(Protocol):
    def get_book(self, book_id: str) -> Edition | None: ...

    def get_progress(self, book_id: str) -> WeReadProgress | None: ...

    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]: ...


class DoubanBatchProvider(Protocol):
    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]: ...

    def get_by_subject_id(self, subject_id: str) -> Edition | None: ...


class CheckpointProvider(Protocol):
    def completed_ids(
        self,
        direction: str,
        *,
        shelf_sync_at: str,
        history_sync_at: str,
    ) -> set[str]: ...

    def mark_completed(
        self,
        direction: str,
        item_id: str,
        *,
        shelf_sync_at: str,
        history_sync_at: str,
        outcome: str,
        recorded_at: str | None = None,
    ) -> None: ...


@dataclass(slots=True, frozen=True)
class BatchGeneration:
    shelf_sync_at: str
    history_sync_at: str


@dataclass(slots=True)
class BatchItemResult:
    direction: str
    item_id: str
    title: str
    outcome: str
    source_state: str | None = None
    shelf_verification: ShelfVerificationResult | None = None
    catalog_alignment: WeReadAlignmentResult | None = None
    selected_shelf_book: IndexedWeReadShelfBook | None = None


@dataclass(slots=True)
class ReconciliationBatchResult:
    direction: str
    generation: BatchGeneration
    candidate_total: int
    already_completed: int
    pending_before: int
    processed: tuple[BatchItemResult, ...]
    remaining_after: int
    requested_limit: int
    effective_limit: int


def run_reconciliation_batch(
    direction: str,
    *,
    limit: int,
    shelf_provider: ShelfProvider,
    history_provider: HistoryProvider,
    checkpoint_provider: CheckpointProvider,
    weread_provider: WeReadBatchProvider,
    douban_provider: DoubanBatchProvider,
    douban_search_limit: int = 3,
    history_candidate_limit: int = 5,
    weread_catalog_limit: int = 5,
) -> ReconciliationBatchResult:
    """Process a tiny read-only reconciliation batch and checkpoint successes.

    The runner intentionally caps one invocation at five items. Provider or
    parser failures propagate immediately instead of being converted to empty
    results; any earlier successful items remain checkpointed so a retry can
    resume from the next pending item.
    """

    if direction not in _BATCH_DIRECTIONS:
        raise ValueError(f"Unsupported reconciliation batch direction: {direction}")

    shelf_status = shelf_provider.status()
    history_status = history_provider.status()
    if not shelf_status.complete or not history_status.complete:
        raise IncompleteShelfVerificationBaselineError(
            "Complete WeRead shelf and Douban history baselines are required before batch reconciliation."
        )
    if not shelf_status.last_full_sync_at or not history_status.last_full_sync_at:
        raise IncompleteShelfVerificationBaselineError(
            "Complete baseline timestamps are required before batch reconciliation."
        )

    generation = BatchGeneration(
        shelf_sync_at=shelf_status.last_full_sync_at,
        history_sync_at=history_status.last_full_sync_at,
    )
    report = build_shelf_preview(
        history_provider.all_entries(),
        shelf_provider.all_books(),
    )
    requested_limit = limit
    effective_limit = max(1, min(limit, _MAX_BATCH_SIZE))
    completed = checkpoint_provider.completed_ids(
        direction,
        shelf_sync_at=generation.shelf_sync_at,
        history_sync_at=generation.history_sync_at,
    )

    if direction == WEREAD_TO_DOUBAN:
        candidates = sorted(
            report.weread_only_books,
            key=lambda book: (
                bool(book.secret),
                normalize_history_title(book.title),
                book.book_id,
            ),
        )
        pending = [book for book in candidates if book.book_id not in completed]
        selected = pending[:effective_limit]
        processed: list[BatchItemResult] = []
        for book in selected:
            verification = verify_shelf_book(
                book.book_id,
                shelf_provider=shelf_provider,
                history_provider=history_provider,
                weread_provider=weread_provider,
                douban_provider=douban_provider,
                douban_search_limit=max(1, min(douban_search_limit, 20)),
                history_candidate_limit=max(1, min(history_candidate_limit, 30)),
            )
            outcome = verification.decision.action.value
            checkpoint_provider.mark_completed(
                direction,
                book.book_id,
                shelf_sync_at=generation.shelf_sync_at,
                history_sync_at=generation.history_sync_at,
                outcome=outcome,
            )
            processed.append(
                BatchItemResult(
                    direction=direction,
                    item_id=book.book_id,
                    title=book.title,
                    outcome=outcome,
                    shelf_verification=verification,
                )
            )
    else:
        candidates = sorted(
            report.active_douban_only_entries,
            key=lambda entry: (normalize_history_title(entry.title), entry.subject_id),
        )
        pending = [entry for entry in candidates if entry.subject_id not in completed]
        selected = pending[:effective_limit]
        processed = []
        for entry in selected:
            source = douban_provider.get_by_subject_id(entry.subject_id)
            if source is None:
                raise ValueError(
                    f"Douban subject {entry.subject_id} could not be resolved to full Edition metadata."
                )
            alignment = align_to_weread(
                source,
                weread_provider,
                limit=max(1, min(weread_catalog_limit, 10)),
            )
            selected_shelf_book = None
            selected_edition = alignment.intent.selected_edition
            if selected_edition is not None and selected_edition.weread_id:
                selected_shelf_book = shelf_provider.get(selected_edition.weread_id)

            outcome = alignment.intent.weread_status.value
            checkpoint_provider.mark_completed(
                direction,
                entry.subject_id,
                shelf_sync_at=generation.shelf_sync_at,
                history_sync_at=generation.history_sync_at,
                outcome=outcome,
            )
            processed.append(
                BatchItemResult(
                    direction=direction,
                    item_id=entry.subject_id,
                    title=entry.title,
                    outcome=outcome,
                    source_state=entry.state,
                    catalog_alignment=alignment,
                    selected_shelf_book=selected_shelf_book,
                )
            )

    pending_before = len(pending)
    return ReconciliationBatchResult(
        direction=direction,
        generation=generation,
        candidate_total=len(candidates),
        already_completed=len(
            completed
            & {
                item.book_id if direction == WEREAD_TO_DOUBAN else item.subject_id
                for item in candidates
            }
        ),
        pending_before=pending_before,
        processed=tuple(processed),
        remaining_after=max(0, pending_before - len(processed)),
        requested_limit=requested_limit,
        effective_limit=effective_limit,
    )


def default_checkpoint_store() -> ReconciliationCheckpointStore:
    return ReconciliationCheckpointStore()
