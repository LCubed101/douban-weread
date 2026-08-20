from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from douban_weread.providers.douban import DoubanProviderError
from douban_weread.providers.weread import WeReadProviderError
from douban_weread.storage import (
    ReconciliationWorkerState,
    ReconciliationWorkerStateStore,
)

from .evidence_report import (
    ReconciliationEvidenceReport,
    build_reconciliation_evidence_report,
)
from .evidence_scan import (
    EvidenceScanGenerationChangedError,
    EvidenceScanResult,
    EvidenceScanStep,
    run_reconciliation_evidence_scan,
)
from .shelf_batch import (
    DOUBAN_TO_WEREAD,
    WEREAD_TO_DOUBAN,
    CheckpointProvider,
    DoubanBatchProvider,
    EvidenceProvider,
    HistoryProvider,
    ShelfProvider,
    WeReadBatchProvider,
)


class ReconciliationWorkerStatus(str, Enum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    PARTIAL = "partial"
    PAUSED_PROVIDER = "paused_provider"
    PAUSED_GENERATION = "paused_generation"
    COMPLETE = "complete"


@dataclass(slots=True, frozen=True)
class ReconciliationWorkerCoverage:
    weread_to_douban_verified: int
    weread_to_douban_pending: int
    douban_to_weread_verified: int
    douban_to_weread_pending: int

    @property
    def verified_total(self) -> int:
        return self.weread_to_douban_verified + self.douban_to_weread_verified

    @property
    def pending_total(self) -> int:
        return self.weread_to_douban_pending + self.douban_to_weread_pending


@dataclass(slots=True, frozen=True)
class ReconciliationWorkerView:
    status: ReconciliationWorkerStatus
    shelf_sync_at: str
    history_sync_at: str
    weread_to_douban_policy: int
    douban_to_weread_policy: int
    coverage: ReconciliationWorkerCoverage
    tick_count: int
    processed_last_tick: int
    last_stop_reason: str | None
    last_error_kind: str | None
    started_at: str | None
    updated_at: str | None


@dataclass(slots=True, frozen=True)
class ReconciliationWorkerTickResult:
    view: ReconciliationWorkerView
    processed_this_tick: int
    scan_result: EvidenceScanResult | None
    error_kind: str | None


class WorkerStateProvider:
    def get_generation(
        self,
        *,
        shelf_sync_at: str,
        history_sync_at: str,
        weread_to_douban_policy: int,
        douban_to_weread_policy: int,
    ) -> ReconciliationWorkerState | None: ...

    def upsert(self, state: ReconciliationWorkerState) -> None: ...


def get_reconciliation_worker_status(
    *,
    shelf_provider: ShelfProvider,
    history_provider: HistoryProvider,
    evidence_provider: EvidenceProvider,
    state_provider: WorkerStateProvider,
) -> ReconciliationWorkerView:
    report = build_reconciliation_evidence_report(
        shelf_provider=shelf_provider,
        history_provider=history_provider,
        evidence_provider=evidence_provider,
    )
    return _view_from_report(report, state_provider)


def run_reconciliation_worker_tick(
    *,
    shelf_provider: ShelfProvider,
    history_provider: HistoryProvider,
    checkpoint_provider: CheckpointProvider,
    evidence_provider: EvidenceProvider,
    state_provider: WorkerStateProvider,
    weread_provider: WeReadBatchProvider,
    douban_provider: DoubanBatchProvider,
    max_items: int = 4,
    batch_size: int = 2,
    max_seconds: float = 30.0,
    douban_search_limit: int = 3,
    history_candidate_limit: int = 5,
    weread_catalog_limit: int = 5,
) -> ReconciliationWorkerTickResult:
    """Run one bounded, resumable first-login reconciliation worker tick.

    The worker never mutates Douban or WeRead. It delegates remote reads to the
    bounded evidence scanner, which persists normalized evidence before
    checkpoints. Provider failures become a persisted paused state instead of
    losing already-completed work.
    """

    initial_report = build_reconciliation_evidence_report(
        shelf_provider=shelf_provider,
        history_provider=history_provider,
        evidence_provider=evidence_provider,
    )
    generation = _generation(initial_report)
    existing = state_provider.get_generation(**generation)
    coverage = _coverage(initial_report)
    tick_count = existing.tick_count if existing is not None else 0
    started_at = existing.started_at if existing is not None else None

    if coverage.pending_total == 0:
        state = _state_from_report(
            initial_report,
            status=ReconciliationWorkerStatus.COMPLETE,
            tick_count=tick_count,
            processed_last_tick=0,
            last_stop_reason="complete",
            last_error_kind=None,
            started_at=started_at,
        )
        state_provider.upsert(state)
        return ReconciliationWorkerTickResult(
            view=_view(initial_report, state),
            processed_this_tick=0,
            scan_result=None,
            error_kind=None,
        )

    now = datetime.now(timezone.utc).isoformat()
    running_state = _state_from_report(
        initial_report,
        status=ReconciliationWorkerStatus.RUNNING,
        tick_count=tick_count + 1,
        processed_last_tick=0,
        last_stop_reason=None,
        last_error_kind=None,
        started_at=started_at or now,
        updated_at=now,
    )
    state_provider.upsert(running_state)

    steps: list[EvidenceScanStep] = []

    def on_step(step: EvidenceScanStep) -> None:
        steps.append(step)

    try:
        scan_result = run_reconciliation_evidence_scan(
            directions="both",
            max_items=max_items,
            batch_size=batch_size,
            max_seconds=max_seconds,
            shelf_provider=shelf_provider,
            history_provider=history_provider,
            checkpoint_provider=checkpoint_provider,
            evidence_provider=evidence_provider,
            weread_provider=weread_provider,
            douban_provider=douban_provider,
            douban_search_limit=douban_search_limit,
            history_candidate_limit=history_candidate_limit,
            weread_catalog_limit=weread_catalog_limit,
            on_step=on_step,
        )
    except DoubanProviderError:
        return _pause_after_failure(
            status=ReconciliationWorkerStatus.PAUSED_PROVIDER,
            error_kind="douban_provider",
            steps=steps,
            shelf_provider=shelf_provider,
            history_provider=history_provider,
            evidence_provider=evidence_provider,
            state_provider=state_provider,
            tick_count=tick_count + 1,
            started_at=running_state.started_at,
        )
    except WeReadProviderError:
        return _pause_after_failure(
            status=ReconciliationWorkerStatus.PAUSED_PROVIDER,
            error_kind="weread_provider",
            steps=steps,
            shelf_provider=shelf_provider,
            history_provider=history_provider,
            evidence_provider=evidence_provider,
            state_provider=state_provider,
            tick_count=tick_count + 1,
            started_at=running_state.started_at,
        )
    except EvidenceScanGenerationChangedError:
        return _pause_after_failure(
            status=ReconciliationWorkerStatus.PAUSED_GENERATION,
            error_kind="generation_changed",
            steps=steps,
            shelf_provider=shelf_provider,
            history_provider=history_provider,
            evidence_provider=evidence_provider,
            state_provider=state_provider,
            tick_count=tick_count + 1,
            started_at=running_state.started_at,
        )

    final_report = build_reconciliation_evidence_report(
        shelf_provider=shelf_provider,
        history_provider=history_provider,
        evidence_provider=evidence_provider,
    )
    final_coverage = _coverage(final_report)
    final_status = (
        ReconciliationWorkerStatus.COMPLETE
        if final_coverage.pending_total == 0
        else ReconciliationWorkerStatus.PARTIAL
    )
    final_state = _state_from_report(
        final_report,
        status=final_status,
        tick_count=tick_count + 1,
        processed_last_tick=scan_result.processed_total,
        last_stop_reason=scan_result.stop_reason,
        last_error_kind=None,
        started_at=running_state.started_at,
    )
    state_provider.upsert(final_state)
    return ReconciliationWorkerTickResult(
        view=_view(final_report, final_state),
        processed_this_tick=scan_result.processed_total,
        scan_result=scan_result,
        error_kind=None,
    )


def _pause_after_failure(
    *,
    status: ReconciliationWorkerStatus,
    error_kind: str,
    steps: list[EvidenceScanStep],
    shelf_provider: ShelfProvider,
    history_provider: HistoryProvider,
    evidence_provider: EvidenceProvider,
    state_provider: WorkerStateProvider,
    tick_count: int,
    started_at: str | None,
) -> ReconciliationWorkerTickResult:
    report = build_reconciliation_evidence_report(
        shelf_provider=shelf_provider,
        history_provider=history_provider,
        evidence_provider=evidence_provider,
    )
    processed = sum(step.processed for step in steps)
    state = _state_from_report(
        report,
        status=status,
        tick_count=tick_count,
        processed_last_tick=processed,
        last_stop_reason="provider_failure" if status == ReconciliationWorkerStatus.PAUSED_PROVIDER else "generation_changed",
        last_error_kind=error_kind,
        started_at=started_at,
    )
    state_provider.upsert(state)
    return ReconciliationWorkerTickResult(
        view=_view(report, state),
        processed_this_tick=processed,
        scan_result=None,
        error_kind=error_kind,
    )


def _generation(report: ReconciliationEvidenceReport) -> dict[str, object]:
    return {
        "shelf_sync_at": report.shelf_sync_at,
        "history_sync_at": report.history_sync_at,
        "weread_to_douban_policy": report.for_direction(WEREAD_TO_DOUBAN).policy_version,
        "douban_to_weread_policy": report.for_direction(DOUBAN_TO_WEREAD).policy_version,
    }


def _coverage(report: ReconciliationEvidenceReport) -> ReconciliationWorkerCoverage:
    w2d = report.for_direction(WEREAD_TO_DOUBAN)
    d2w = report.for_direction(DOUBAN_TO_WEREAD)
    return ReconciliationWorkerCoverage(
        weread_to_douban_verified=w2d.verified_total,
        weread_to_douban_pending=w2d.pending_total,
        douban_to_weread_verified=d2w.verified_total,
        douban_to_weread_pending=d2w.pending_total,
    )


def _view_from_report(
    report: ReconciliationEvidenceReport,
    state_provider: WorkerStateProvider,
) -> ReconciliationWorkerView:
    generation = _generation(report)
    state = state_provider.get_generation(**generation)
    coverage = _coverage(report)
    if state is None:
        if coverage.pending_total == 0:
            status = ReconciliationWorkerStatus.COMPLETE
        elif coverage.verified_total > 0:
            status = ReconciliationWorkerStatus.PARTIAL
        else:
            status = ReconciliationWorkerStatus.NOT_STARTED
        return ReconciliationWorkerView(
            status=status,
            shelf_sync_at=report.shelf_sync_at,
            history_sync_at=report.history_sync_at,
            weread_to_douban_policy=int(generation["weread_to_douban_policy"]),
            douban_to_weread_policy=int(generation["douban_to_weread_policy"]),
            coverage=coverage,
            tick_count=0,
            processed_last_tick=0,
            last_stop_reason=None,
            last_error_kind=None,
            started_at=None,
            updated_at=None,
        )
    return _view(report, state)


def _view(
    report: ReconciliationEvidenceReport,
    state: ReconciliationWorkerState,
) -> ReconciliationWorkerView:
    coverage = _coverage(report)
    status = ReconciliationWorkerStatus(state.status)
    if status == ReconciliationWorkerStatus.COMPLETE and coverage.pending_total > 0:
        status = ReconciliationWorkerStatus.PARTIAL
    return ReconciliationWorkerView(
        status=status,
        shelf_sync_at=report.shelf_sync_at,
        history_sync_at=report.history_sync_at,
        weread_to_douban_policy=state.weread_to_douban_policy,
        douban_to_weread_policy=state.douban_to_weread_policy,
        coverage=coverage,
        tick_count=state.tick_count,
        processed_last_tick=state.processed_last_tick,
        last_stop_reason=state.last_stop_reason,
        last_error_kind=state.last_error_kind,
        started_at=state.started_at,
        updated_at=state.updated_at,
    )


def _state_from_report(
    report: ReconciliationEvidenceReport,
    *,
    status: ReconciliationWorkerStatus,
    tick_count: int,
    processed_last_tick: int,
    last_stop_reason: str | None,
    last_error_kind: str | None,
    started_at: str | None,
    updated_at: str | None = None,
) -> ReconciliationWorkerState:
    generation = _generation(report)
    coverage = _coverage(report)
    return ReconciliationWorkerState(
        shelf_sync_at=report.shelf_sync_at,
        history_sync_at=report.history_sync_at,
        weread_to_douban_policy=int(generation["weread_to_douban_policy"]),
        douban_to_weread_policy=int(generation["douban_to_weread_policy"]),
        status=status.value,
        tick_count=tick_count,
        processed_last_tick=processed_last_tick,
        weread_to_douban_verified=coverage.weread_to_douban_verified,
        weread_to_douban_pending=coverage.weread_to_douban_pending,
        douban_to_weread_verified=coverage.douban_to_weread_verified,
        douban_to_weread_pending=coverage.douban_to_weread_pending,
        last_stop_reason=last_stop_reason,
        last_error_kind=last_error_kind,
        started_at=started_at,
        updated_at=updated_at,
    )


def default_worker_state_store() -> ReconciliationWorkerStateStore:
    return ReconciliationWorkerStateStore()
