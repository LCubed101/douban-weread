from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from douban_weread.providers.douban import DoubanProviderError, HistoryEntry
from douban_weread.providers.weread import WeReadProviderError, WeReadShelfSnapshot

from .shelf_batch import (
    CheckpointProvider,
    DoubanBatchProvider,
    EvidenceProvider,
    HistoryProvider,
    ShelfProvider,
    WeReadBatchProvider,
)
from .worker import (
    ReconciliationWorkerStatus,
    ReconciliationWorkerTickResult,
    ReconciliationWorkerView,
    WorkerStateProvider,
    get_reconciliation_worker_status,
    run_reconciliation_worker_tick,
)


class FirstLoginReconciliationPhase(str, Enum):
    NEEDS_BASELINES = "needs_baselines"
    RECONCILING = "reconciling"
    PAUSED_PROVIDER = "paused_provider"
    PAUSED_GENERATION = "paused_generation"
    COMPLETE = "complete"


class DoubanHistoryBaselineClient(Protocol):
    def fetch_all(self) -> list[HistoryEntry]: ...


class WeReadShelfBaselineClient(Protocol):
    def sync_shelf(self) -> WeReadShelfSnapshot: ...


class HistoryBaselineStore(HistoryProvider, Protocol):
    def replace_full(self, entries: list[HistoryEntry], *, synced_at: str | None = None) -> None: ...


class ShelfBaselineStore(ShelfProvider, Protocol):
    def replace_full(self, snapshot: WeReadShelfSnapshot, *, synced_at: str | None = None) -> None: ...


@dataclass(slots=True, frozen=True)
class FirstLoginReconciliationView:
    phase: FirstLoginReconciliationPhase
    douban_baseline_complete: bool
    weread_baseline_complete: bool
    douban_sync_at: str | None
    weread_sync_at: str | None
    missing_baselines: tuple[str, ...]
    worker: ReconciliationWorkerView | None
    last_error_kind: str | None = None

    @property
    def ready_for_reconciliation(self) -> bool:
        return self.douban_baseline_complete and self.weread_baseline_complete


@dataclass(slots=True, frozen=True)
class FirstLoginReconciliationTickResult:
    view: FirstLoginReconciliationView
    baselines_synced: tuple[str, ...]
    worker_tick: ReconciliationWorkerTickResult | None


def get_first_login_reconciliation_view(
    *,
    shelf_provider: ShelfBaselineStore,
    history_provider: HistoryBaselineStore,
    evidence_provider: EvidenceProvider,
    state_provider: WorkerStateProvider,
) -> FirstLoginReconciliationView:
    """Return a UI-ready local view without constructing or calling providers."""

    baseline_view = _baseline_view(
        shelf_provider=shelf_provider,
        history_provider=history_provider,
    )
    if baseline_view.missing_baselines:
        return baseline_view

    worker = get_reconciliation_worker_status(
        shelf_provider=shelf_provider,
        history_provider=history_provider,
        evidence_provider=evidence_provider,
        state_provider=state_provider,
    )
    return _view_from_worker(
        shelf_provider=shelf_provider,
        history_provider=history_provider,
        worker=worker,
    )


def run_first_login_reconciliation_tick(
    *,
    shelf_provider: ShelfBaselineStore,
    history_provider: HistoryBaselineStore,
    checkpoint_provider: CheckpointProvider,
    evidence_provider: EvidenceProvider,
    state_provider: WorkerStateProvider,
    weread_provider: WeReadBatchProvider,
    douban_provider: DoubanBatchProvider,
    weread_shelf_client: WeReadShelfBaselineClient | None = None,
    douban_history_client: DoubanHistoryBaselineClient | None = None,
    max_items: int = 4,
    batch_size: int = 2,
    max_seconds: float = 30.0,
    douban_search_limit: int = 3,
    history_candidate_limit: int = 5,
    weread_catalog_limit: int = 5,
) -> FirstLoginReconciliationTickResult:
    """Ensure missing first-login baselines, then run one bounded worker tick.

    Provider credentials are supplied through the caller-owned provider objects
    and are never persisted here. Complete existing baselines are reused. If one
    missing baseline sync succeeds and the other fails, the successful baseline
    remains available locally, but reconciliation does not start until both are
    complete. Platform writes are never performed by this controller.
    """

    synced: list[str] = []

    history_status = history_provider.status()
    if not history_status.complete:
        if douban_history_client is None:
            return FirstLoginReconciliationTickResult(
                view=_baseline_view(
                    shelf_provider=shelf_provider,
                    history_provider=history_provider,
                ),
                baselines_synced=(),
                worker_tick=None,
            )
        try:
            entries = douban_history_client.fetch_all()
            history_provider.replace_full(entries)
        except DoubanProviderError:
            return FirstLoginReconciliationTickResult(
                view=_baseline_view(
                    shelf_provider=shelf_provider,
                    history_provider=history_provider,
                    phase=FirstLoginReconciliationPhase.PAUSED_PROVIDER,
                    error_kind="douban_baseline",
                ),
                baselines_synced=tuple(synced),
                worker_tick=None,
            )
        synced.append("douban")

    shelf_status = shelf_provider.status()
    if not shelf_status.complete:
        if weread_shelf_client is None:
            return FirstLoginReconciliationTickResult(
                view=_baseline_view(
                    shelf_provider=shelf_provider,
                    history_provider=history_provider,
                ),
                baselines_synced=tuple(synced),
                worker_tick=None,
            )
        try:
            snapshot = weread_shelf_client.sync_shelf()
            shelf_provider.replace_full(snapshot)
        except WeReadProviderError:
            return FirstLoginReconciliationTickResult(
                view=_baseline_view(
                    shelf_provider=shelf_provider,
                    history_provider=history_provider,
                    phase=FirstLoginReconciliationPhase.PAUSED_PROVIDER,
                    error_kind="weread_baseline",
                ),
                baselines_synced=tuple(synced),
                worker_tick=None,
            )
        synced.append("weread")

    baseline_view = _baseline_view(
        shelf_provider=shelf_provider,
        history_provider=history_provider,
    )
    if baseline_view.missing_baselines:
        return FirstLoginReconciliationTickResult(
            view=baseline_view,
            baselines_synced=tuple(synced),
            worker_tick=None,
        )

    worker_tick = run_reconciliation_worker_tick(
        shelf_provider=shelf_provider,
        history_provider=history_provider,
        checkpoint_provider=checkpoint_provider,
        evidence_provider=evidence_provider,
        state_provider=state_provider,
        weread_provider=weread_provider,
        douban_provider=douban_provider,
        max_items=max_items,
        batch_size=batch_size,
        max_seconds=max_seconds,
        douban_search_limit=douban_search_limit,
        history_candidate_limit=history_candidate_limit,
        weread_catalog_limit=weread_catalog_limit,
    )
    view = _view_from_worker(
        shelf_provider=shelf_provider,
        history_provider=history_provider,
        worker=worker_tick.view,
    )
    return FirstLoginReconciliationTickResult(
        view=view,
        baselines_synced=tuple(synced),
        worker_tick=worker_tick,
    )


def _baseline_view(
    *,
    shelf_provider: ShelfBaselineStore,
    history_provider: HistoryBaselineStore,
    phase: FirstLoginReconciliationPhase | None = None,
    error_kind: str | None = None,
) -> FirstLoginReconciliationView:
    history = history_provider.status()
    shelf = shelf_provider.status()
    missing: list[str] = []
    if not history.complete:
        missing.append("douban")
    if not shelf.complete:
        missing.append("weread")
    return FirstLoginReconciliationView(
        phase=phase or FirstLoginReconciliationPhase.NEEDS_BASELINES,
        douban_baseline_complete=history.complete,
        weread_baseline_complete=shelf.complete,
        douban_sync_at=history.last_full_sync_at,
        weread_sync_at=shelf.last_full_sync_at,
        missing_baselines=tuple(missing),
        worker=None,
        last_error_kind=error_kind,
    )


def _view_from_worker(
    *,
    shelf_provider: ShelfBaselineStore,
    history_provider: HistoryBaselineStore,
    worker: ReconciliationWorkerView,
) -> FirstLoginReconciliationView:
    history = history_provider.status()
    shelf = shelf_provider.status()
    if worker.status == ReconciliationWorkerStatus.COMPLETE:
        phase = FirstLoginReconciliationPhase.COMPLETE
    elif worker.status == ReconciliationWorkerStatus.PAUSED_PROVIDER:
        phase = FirstLoginReconciliationPhase.PAUSED_PROVIDER
    elif worker.status == ReconciliationWorkerStatus.PAUSED_GENERATION:
        phase = FirstLoginReconciliationPhase.PAUSED_GENERATION
    else:
        phase = FirstLoginReconciliationPhase.RECONCILING
    return FirstLoginReconciliationView(
        phase=phase,
        douban_baseline_complete=history.complete,
        weread_baseline_complete=shelf.complete,
        douban_sync_at=history.last_full_sync_at,
        weread_sync_at=shelf.last_full_sync_at,
        missing_baselines=(),
        worker=worker,
        last_error_kind=worker.last_error_kind,
    )
