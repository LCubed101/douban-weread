from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .reconciliation_checkpoint import default_reconciliation_db_path


_ALLOWED_STATUS = {
    "running",
    "partial",
    "paused_provider",
    "paused_generation",
    "complete",
}


@dataclass(slots=True, frozen=True)
class ReconciliationWorkerState:
    shelf_sync_at: str
    history_sync_at: str
    weread_to_douban_policy: int
    douban_to_weread_policy: int
    status: str
    tick_count: int
    processed_last_tick: int
    weread_to_douban_verified: int
    weread_to_douban_pending: int
    douban_to_weread_verified: int
    douban_to_weread_pending: int
    last_stop_reason: str | None = None
    last_error_kind: str | None = None
    started_at: str | None = None
    updated_at: str | None = None

    @property
    def verified_total(self) -> int:
        return self.weread_to_douban_verified + self.douban_to_weread_verified

    @property
    def pending_total(self) -> int:
        return self.weread_to_douban_pending + self.douban_to_weread_pending


class ReconciliationWorkerStateStore:
    """Persist orchestration state for one baseline/policy reconciliation generation.

    This table intentionally stores only normalized worker progress. It never
    stores provider payloads, credentials, Cookies, API keys, or mutation
    authorization.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else default_reconciliation_db_path()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS reconciliation_worker_state (
                    shelf_sync_at TEXT NOT NULL,
                    history_sync_at TEXT NOT NULL,
                    weread_to_douban_policy INTEGER NOT NULL,
                    douban_to_weread_policy INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    tick_count INTEGER NOT NULL,
                    processed_last_tick INTEGER NOT NULL,
                    weread_to_douban_verified INTEGER NOT NULL,
                    weread_to_douban_pending INTEGER NOT NULL,
                    douban_to_weread_verified INTEGER NOT NULL,
                    douban_to_weread_pending INTEGER NOT NULL,
                    last_stop_reason TEXT,
                    last_error_kind TEXT,
                    started_at TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(
                        shelf_sync_at,
                        history_sync_at,
                        weread_to_douban_policy,
                        douban_to_weread_policy
                    )
                );
                """
            )
            conn.commit()

    def get_generation(
        self,
        *,
        shelf_sync_at: str,
        history_sync_at: str,
        weread_to_douban_policy: int,
        douban_to_weread_policy: int,
    ) -> ReconciliationWorkerState | None:
        self._validate_generation(
            shelf_sync_at,
            history_sync_at,
            weread_to_douban_policy,
            douban_to_weread_policy,
        )
        if not self.path.exists():
            return None
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT shelf_sync_at, history_sync_at,
                       weread_to_douban_policy, douban_to_weread_policy,
                       status, tick_count, processed_last_tick,
                       weread_to_douban_verified, weread_to_douban_pending,
                       douban_to_weread_verified, douban_to_weread_pending,
                       last_stop_reason, last_error_kind, started_at, updated_at
                FROM reconciliation_worker_state
                WHERE shelf_sync_at=? AND history_sync_at=?
                  AND weread_to_douban_policy=? AND douban_to_weread_policy=?
                """,
                (
                    shelf_sync_at,
                    history_sync_at,
                    weread_to_douban_policy,
                    douban_to_weread_policy,
                ),
            ).fetchone()
        return _row_to_state(row) if row is not None else None

    def upsert(self, state: ReconciliationWorkerState) -> None:
        self._validate_state(state)
        updated_at = state.updated_at or datetime.now(timezone.utc).isoformat()
        self.initialize()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reconciliation_worker_state(
                    shelf_sync_at, history_sync_at,
                    weread_to_douban_policy, douban_to_weread_policy,
                    status, tick_count, processed_last_tick,
                    weread_to_douban_verified, weread_to_douban_pending,
                    douban_to_weread_verified, douban_to_weread_pending,
                    last_stop_reason, last_error_kind, started_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    shelf_sync_at, history_sync_at,
                    weread_to_douban_policy, douban_to_weread_policy
                ) DO UPDATE SET
                    status=excluded.status,
                    tick_count=excluded.tick_count,
                    processed_last_tick=excluded.processed_last_tick,
                    weread_to_douban_verified=excluded.weread_to_douban_verified,
                    weread_to_douban_pending=excluded.weread_to_douban_pending,
                    douban_to_weread_verified=excluded.douban_to_weread_verified,
                    douban_to_weread_pending=excluded.douban_to_weread_pending,
                    last_stop_reason=excluded.last_stop_reason,
                    last_error_kind=excluded.last_error_kind,
                    started_at=COALESCE(reconciliation_worker_state.started_at, excluded.started_at),
                    updated_at=excluded.updated_at
                """,
                (
                    state.shelf_sync_at,
                    state.history_sync_at,
                    state.weread_to_douban_policy,
                    state.douban_to_weread_policy,
                    state.status,
                    state.tick_count,
                    state.processed_last_tick,
                    state.weread_to_douban_verified,
                    state.weread_to_douban_pending,
                    state.douban_to_weread_verified,
                    state.douban_to_weread_pending,
                    state.last_stop_reason,
                    state.last_error_kind,
                    state.started_at,
                    updated_at,
                ),
            )
            conn.commit()

    @staticmethod
    def _validate_generation(
        shelf_sync_at: str,
        history_sync_at: str,
        weread_to_douban_policy: int,
        douban_to_weread_policy: int,
    ) -> None:
        if not shelf_sync_at.strip() or not history_sync_at.strip():
            raise ValueError("Complete baseline timestamps are required for worker state")
        if weread_to_douban_policy < 1 or douban_to_weread_policy < 1:
            raise ValueError("Worker policy versions must be >= 1")

    @classmethod
    def _validate_state(cls, state: ReconciliationWorkerState) -> None:
        cls._validate_generation(
            state.shelf_sync_at,
            state.history_sync_at,
            state.weread_to_douban_policy,
            state.douban_to_weread_policy,
        )
        if state.status not in _ALLOWED_STATUS:
            raise ValueError(f"Unsupported reconciliation worker status: {state.status}")
        numeric = (
            state.tick_count,
            state.processed_last_tick,
            state.weread_to_douban_verified,
            state.weread_to_douban_pending,
            state.douban_to_weread_verified,
            state.douban_to_weread_pending,
        )
        if any(value < 0 for value in numeric):
            raise ValueError("Worker counters must be non-negative")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def _row_to_state(row: tuple[object, ...]) -> ReconciliationWorkerState:
    return ReconciliationWorkerState(
        shelf_sync_at=str(row[0]),
        history_sync_at=str(row[1]),
        weread_to_douban_policy=int(row[2]),
        douban_to_weread_policy=int(row[3]),
        status=str(row[4]),
        tick_count=int(row[5]),
        processed_last_tick=int(row[6]),
        weread_to_douban_verified=int(row[7]),
        weread_to_douban_pending=int(row[8]),
        douban_to_weread_verified=int(row[9]),
        douban_to_weread_pending=int(row[10]),
        last_stop_reason=str(row[11]) if row[11] is not None else None,
        last_error_kind=str(row[12]) if row[12] is not None else None,
        started_at=str(row[13]) if row[13] is not None else None,
        updated_at=str(row[14]) if row[14] is not None else None,
    )
