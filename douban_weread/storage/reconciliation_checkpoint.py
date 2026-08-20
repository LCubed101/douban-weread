from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


_ALLOWED_DIRECTIONS = {"weread-to-douban", "douban-to-weread"}


@dataclass(slots=True, frozen=True)
class ReconciliationCheckpoint:
    direction: str
    item_id: str
    shelf_sync_at: str
    history_sync_at: str
    outcome: str
    recorded_at: str


def default_reconciliation_db_path() -> Path:
    explicit = os.getenv("DOUBAN_WEREAD_DB", "").strip()
    if explicit:
        return Path(explicit).expanduser()

    data_home = os.getenv("XDG_DATA_HOME", "").strip()
    root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return root / "douban-weread" / "history.sqlite3"


class ReconciliationCheckpointStore:
    """Baseline-scoped local checkpoints for bounded background reconciliation.

    A checkpoint never authorizes or records a remote mutation. It only prevents
    the same queue item from being re-verified repeatedly against the same pair
    of complete local baselines. A new Douban-history or WeRead-shelf sync has a
    new generation and therefore naturally becomes eligible for verification.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else default_reconciliation_db_path()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS reconciliation_checkpoints (
                    direction TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    shelf_sync_at TEXT NOT NULL,
                    history_sync_at TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY(direction, item_id, shelf_sync_at, history_sync_at)
                );

                CREATE INDEX IF NOT EXISTS idx_reconciliation_checkpoint_generation
                    ON reconciliation_checkpoints(direction, shelf_sync_at, history_sync_at);
                """
            )

    def completed_ids(
        self,
        direction: str,
        *,
        shelf_sync_at: str,
        history_sync_at: str,
    ) -> set[str]:
        self._validate_generation(direction, shelf_sync_at, history_sync_at)
        if not self.path.exists():
            return set()
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT item_id
                FROM reconciliation_checkpoints
                WHERE direction=? AND shelf_sync_at=? AND history_sync_at=?
                """,
                (direction, shelf_sync_at, history_sync_at),
            ).fetchall()
        return {str(row[0]) for row in rows}

    def mark_completed(
        self,
        direction: str,
        item_id: str,
        *,
        shelf_sync_at: str,
        history_sync_at: str,
        outcome: str,
        recorded_at: str | None = None,
    ) -> None:
        self._validate_generation(direction, shelf_sync_at, history_sync_at)
        normalized_id = item_id.strip()
        normalized_outcome = outcome.strip()
        if not normalized_id:
            raise ValueError("Reconciliation checkpoint item_id must not be blank")
        if not normalized_outcome:
            raise ValueError("Reconciliation checkpoint outcome must not be blank")

        timestamp = recorded_at or datetime.now(timezone.utc).isoformat()
        self.initialize()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reconciliation_checkpoints(
                    direction, item_id, shelf_sync_at, history_sync_at, outcome, recorded_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(direction, item_id, shelf_sync_at, history_sync_at) DO UPDATE SET
                    outcome=excluded.outcome,
                    recorded_at=excluded.recorded_at
                """,
                (
                    direction,
                    normalized_id,
                    shelf_sync_at,
                    history_sync_at,
                    normalized_outcome,
                    timestamp,
                ),
            )
            conn.commit()

    def list_generation(
        self,
        direction: str,
        *,
        shelf_sync_at: str,
        history_sync_at: str,
    ) -> list[ReconciliationCheckpoint]:
        self._validate_generation(direction, shelf_sync_at, history_sync_at)
        if not self.path.exists():
            return []
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT direction, item_id, shelf_sync_at, history_sync_at, outcome, recorded_at
                FROM reconciliation_checkpoints
                WHERE direction=? AND shelf_sync_at=? AND history_sync_at=?
                ORDER BY recorded_at, item_id
                """,
                (direction, shelf_sync_at, history_sync_at),
            ).fetchall()
        return [ReconciliationCheckpoint(*map(str, row)) for row in rows]

    @staticmethod
    def _validate_generation(direction: str, shelf_sync_at: str, history_sync_at: str) -> None:
        if direction not in _ALLOWED_DIRECTIONS:
            raise ValueError(f"Unsupported reconciliation direction: {direction}")
        if not shelf_sync_at.strip() or not history_sync_at.strip():
            raise ValueError("Complete baseline timestamps are required for reconciliation checkpoints")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
