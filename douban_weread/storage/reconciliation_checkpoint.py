from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


_ALLOWED_DIRECTIONS = {"weread-to-douban", "douban-to-weread"}
CURRENT_RECONCILIATION_POLICY_VERSION = 3


@dataclass(slots=True, frozen=True)
class ReconciliationCheckpoint:
    direction: str
    item_id: str
    shelf_sync_at: str
    history_sync_at: str
    policy_version: int
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
    """Baseline- and policy-scoped local checkpoints for background reconciliation.

    A checkpoint never authorizes or records a remote mutation. It only prevents
    the same queue item from being re-verified repeatedly against the same pair
    of complete local baselines under the same reconciliation policy version.
    Refreshing either baseline or upgrading the policy makes the item eligible
    for verification again.
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
                    policy_version INTEGER NOT NULL DEFAULT 1,
                    outcome TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY(direction, item_id, shelf_sync_at, history_sync_at)
                );

                CREATE INDEX IF NOT EXISTS idx_reconciliation_checkpoint_generation
                    ON reconciliation_checkpoints(direction, shelf_sync_at, history_sync_at);
                """
            )
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(reconciliation_checkpoints)").fetchall()
            }
            if "policy_version" not in columns:
                conn.execute(
                    "ALTER TABLE reconciliation_checkpoints "
                    "ADD COLUMN policy_version INTEGER NOT NULL DEFAULT 1"
                )
            conn.commit()

    def completed_ids(
        self,
        direction: str,
        *,
        shelf_sync_at: str,
        history_sync_at: str,
        policy_version: int = CURRENT_RECONCILIATION_POLICY_VERSION,
    ) -> set[str]:
        self._validate_generation(direction, shelf_sync_at, history_sync_at, policy_version)
        if not self.path.exists():
            return set()
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT item_id
                FROM reconciliation_checkpoints
                WHERE direction=? AND shelf_sync_at=? AND history_sync_at=? AND policy_version=?
                """,
                (direction, shelf_sync_at, history_sync_at, policy_version),
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
        policy_version: int = CURRENT_RECONCILIATION_POLICY_VERSION,
        recorded_at: str | None = None,
    ) -> None:
        self._validate_generation(direction, shelf_sync_at, history_sync_at, policy_version)
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
                    direction, item_id, shelf_sync_at, history_sync_at,
                    policy_version, outcome, recorded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(direction, item_id, shelf_sync_at, history_sync_at) DO UPDATE SET
                    policy_version=excluded.policy_version,
                    outcome=excluded.outcome,
                    recorded_at=excluded.recorded_at
                """,
                (
                    direction,
                    normalized_id,
                    shelf_sync_at,
                    history_sync_at,
                    policy_version,
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
        policy_version: int = CURRENT_RECONCILIATION_POLICY_VERSION,
    ) -> list[ReconciliationCheckpoint]:
        self._validate_generation(direction, shelf_sync_at, history_sync_at, policy_version)
        if not self.path.exists():
            return []
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT direction, item_id, shelf_sync_at, history_sync_at,
                       policy_version, outcome, recorded_at
                FROM reconciliation_checkpoints
                WHERE direction=? AND shelf_sync_at=? AND history_sync_at=? AND policy_version=?
                ORDER BY recorded_at, item_id
                """,
                (direction, shelf_sync_at, history_sync_at, policy_version),
            ).fetchall()
        return [
            ReconciliationCheckpoint(
                direction=str(row[0]),
                item_id=str(row[1]),
                shelf_sync_at=str(row[2]),
                history_sync_at=str(row[3]),
                policy_version=int(row[4]),
                outcome=str(row[5]),
                recorded_at=str(row[6]),
            )
            for row in rows
        ]

    @staticmethod
    def _validate_generation(
        direction: str,
        shelf_sync_at: str,
        history_sync_at: str,
        policy_version: int,
    ) -> None:
        if direction not in _ALLOWED_DIRECTIONS:
            raise ValueError(f"Unsupported reconciliation direction: {direction}")
        if not shelf_sync_at.strip() or not history_sync_at.strip():
            raise ValueError("Complete baseline timestamps are required for reconciliation checkpoints")
        if policy_version < 1:
            raise ValueError("Reconciliation policy_version must be >= 1")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
