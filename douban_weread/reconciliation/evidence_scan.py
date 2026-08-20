from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from .shelf_batch import (
    DOUBAN_TO_WEREAD,
    WEREAD_TO_DOUBAN,
    CheckpointProvider,
    DoubanBatchProvider,
    EvidenceProvider,
    HistoryProvider,
    ShelfProvider,
    WeReadBatchProvider,
    run_reconciliation_batch,
)


_SCAN_DIRECTIONS = (DOUBAN_TO_WEREAD, WEREAD_TO_DOUBAN)
_MAX_SCAN_ITEMS = 20
_MAX_BATCH_SIZE = 5


class EvidenceScanGenerationChangedError(RuntimeError):
    """Raised if complete baseline timestamps change during one scan run."""


@dataclass(slots=True, frozen=True)
class EvidenceScanStep:
    batch_number: int
    direction: str
    processed: int
    cumulative_processed: int
    candidate_total: int
    remaining_after: int
    policy_version: int


@dataclass(slots=True, frozen=True)
class EvidenceScanResult:
    directions: tuple[str, ...]
    requested_max_items: int
    effective_max_items: int
    requested_batch_size: int
    effective_batch_size: int
    processed_total: int
    steps: tuple[EvidenceScanStep, ...]
    stop_reason: str
    shelf_sync_at: str | None
    history_sync_at: str | None


def normalize_scan_directions(value: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        if value == "both":
            return _SCAN_DIRECTIONS
        values = (value,)
    else:
        values = tuple(value)

    if not values:
        raise ValueError("At least one reconciliation scan direction is required")
    normalized: list[str] = []
    for direction in values:
        if direction not in _SCAN_DIRECTIONS:
            raise ValueError(f"Unsupported reconciliation scan direction: {direction}")
        if direction not in normalized:
            normalized.append(direction)
    return tuple(normalized)


def run_reconciliation_evidence_scan(
    *,
    directions: str | Sequence[str],
    max_items: int,
    batch_size: int,
    shelf_provider: ShelfProvider,
    history_provider: HistoryProvider,
    checkpoint_provider: CheckpointProvider,
    evidence_provider: EvidenceProvider,
    weread_provider: WeReadBatchProvider,
    douban_provider: DoubanBatchProvider,
    douban_search_limit: int = 3,
    history_candidate_limit: int = 5,
    weread_catalog_limit: int = 5,
    on_step: Callable[[EvidenceScanStep], None] | None = None,
) -> EvidenceScanResult:
    """Fill a bounded amount of reconciliation evidence with visible progress.

    This runner remains read-only with respect to Douban and WeRead. It delegates
    all remote verification to the existing tiny batch runner, which persists
    normalized evidence before checkpoints. Multiple directions are processed in
    round-robin order so one large queue cannot starve the other.

    Provider/parser failures propagate immediately. Previously completed steps
    remain safely persisted and a later invocation resumes from their evidence +
    checkpoints. The scan also fails closed if either complete baseline timestamp
    changes while the process is running.
    """

    normalized_directions = normalize_scan_directions(directions)
    requested_max_items = max_items
    requested_batch_size = batch_size
    effective_max_items = max(1, min(max_items, _MAX_SCAN_ITEMS))
    effective_batch_size = max(1, min(batch_size, _MAX_BATCH_SIZE))

    active = set(normalized_directions)
    steps: list[EvidenceScanStep] = []
    processed_total = 0
    expected_baselines: tuple[str, str] | None = None
    stop_reason = "complete"

    while active and processed_total < effective_max_items:
        made_progress = False
        for direction in normalized_directions:
            if direction not in active or processed_total >= effective_max_items:
                continue

            remaining_budget = effective_max_items - processed_total
            limit = min(effective_batch_size, remaining_budget)
            result = run_reconciliation_batch(
                direction,
                limit=limit,
                shelf_provider=shelf_provider,
                history_provider=history_provider,
                checkpoint_provider=checkpoint_provider,
                evidence_provider=evidence_provider,
                weread_provider=weread_provider,
                douban_provider=douban_provider,
                douban_search_limit=douban_search_limit,
                history_candidate_limit=history_candidate_limit,
                weread_catalog_limit=weread_catalog_limit,
            )

            current_baselines = (
                result.generation.shelf_sync_at,
                result.generation.history_sync_at,
            )
            if expected_baselines is None:
                expected_baselines = current_baselines
            elif current_baselines != expected_baselines:
                raise EvidenceScanGenerationChangedError(
                    "Complete reconciliation baselines changed during this scan; stop and restart against one generation."
                )

            processed = len(result.processed)
            if processed == 0:
                active.discard(direction)
                continue

            processed_total += processed
            made_progress = True
            step = EvidenceScanStep(
                batch_number=len(steps) + 1,
                direction=direction,
                processed=processed,
                cumulative_processed=processed_total,
                candidate_total=result.candidate_total,
                remaining_after=result.remaining_after,
                policy_version=result.generation.policy_version,
            )
            steps.append(step)
            if on_step is not None:
                on_step(step)

            if result.remaining_after == 0:
                active.discard(direction)

        if not made_progress:
            stop_reason = "no_progress" if active else "complete"
            break
    else:
        if processed_total >= effective_max_items and active:
            stop_reason = "max_items"
        elif not active:
            stop_reason = "complete"

    if processed_total >= effective_max_items and active:
        stop_reason = "max_items"

    shelf_sync_at = expected_baselines[0] if expected_baselines is not None else None
    history_sync_at = expected_baselines[1] if expected_baselines is not None else None
    return EvidenceScanResult(
        directions=normalized_directions,
        requested_max_items=requested_max_items,
        effective_max_items=effective_max_items,
        requested_batch_size=requested_batch_size,
        effective_batch_size=effective_batch_size,
        processed_total=processed_total,
        steps=tuple(steps),
        stop_reason=stop_reason,
        shelf_sync_at=shelf_sync_at,
        history_sync_at=history_sync_at,
    )
