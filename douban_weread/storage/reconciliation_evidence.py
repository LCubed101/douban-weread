from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


_ALLOWED_DIRECTIONS = {"weread-to-douban", "douban-to-weread"}
_ALLOWED_SHELF_MEMBERSHIP = {None, "yes", "no", "unresolved"}


@dataclass(slots=True, frozen=True)
class ReconciliationEvidence:
    direction: str
    item_id: str
    shelf_sync_at: str
    history_sync_at: str
    policy_version: int
    title: str
    outcome: str
    user_plan: str
    summary: str
    requires_user_action: bool
    recorded_at: str | None = None
    source_state: str | None = None
    selected_douban_subject: str | None = None
    selected_weread_book_id: str | None = None
    selected_edition_title: str | None = None
    match_kind: str | None = None
    exact_edition: bool | None = None
    requires_confirmation: bool | None = None
    weread_catalog_status: str | None = None
    weread_resolution: str | None = None
    shelf_membership: str | None = None
    weread_reading_state: str | None = None
    weread_progress: int | None = None
    strongest_douban_state: str | None = None
    suggested_douban_state: str | None = None
    deep_link: str | None = None
    catalog_search_limit: int | None = None


def default_reconciliation_evidence_db_path() -> Path:
    explicit = os.getenv("DOUBAN_WEREAD_DB", "").strip()
    if explicit:
        return Path(explicit).expanduser()

    data_home = os.getenv("XDG_DATA_HOME", "").strip()
    root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return root / "douban-weread" / "history.sqlite3"


class ReconciliationEvidenceStore:
    """Local normalized evidence for reproducible reconciliation reports.

    The store intentionally persists only normalized reconciliation facts. It
    does not persist provider response payloads, credentials, Cookies, API keys,
    or mutation authorization.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else default_reconciliation_evidence_db_path()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS reconciliation_evidence (
                    direction TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    shelf_sync_at TEXT NOT NULL,
                    history_sync_at TEXT NOT NULL,
                    policy_version INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    source_state TEXT,
                    outcome TEXT NOT NULL,
                    user_plan TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    requires_user_action INTEGER NOT NULL,
                    selected_douban_subject TEXT,
                    selected_weread_book_id TEXT,
                    selected_edition_title TEXT,
                    match_kind TEXT,
                    exact_edition INTEGER,
                    requires_confirmation INTEGER,
                    weread_catalog_status TEXT,
                    weread_resolution TEXT,
                    shelf_membership TEXT,
                    weread_reading_state TEXT,
                    weread_progress INTEGER,
                    strongest_douban_state TEXT,
                    suggested_douban_state TEXT,
                    deep_link TEXT,
                    catalog_search_limit INTEGER,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY(direction, item_id, shelf_sync_at, history_sync_at, policy_version)
                );

                CREATE INDEX IF NOT EXISTS idx_reconciliation_evidence_generation
                    ON reconciliation_evidence(
                        direction, shelf_sync_at, history_sync_at, policy_version
                    );

                CREATE INDEX IF NOT EXISTS idx_reconciliation_evidence_plan
                    ON reconciliation_evidence(user_plan);
                """
            )
            conn.commit()

    def upsert(self, evidence: ReconciliationEvidence) -> None:
        self._validate(evidence)
        timestamp = evidence.recorded_at or datetime.now(timezone.utc).isoformat()
        self.initialize()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reconciliation_evidence(
                    direction, item_id, shelf_sync_at, history_sync_at, policy_version,
                    title, source_state, outcome, user_plan, summary,
                    requires_user_action, selected_douban_subject, selected_weread_book_id,
                    selected_edition_title, match_kind, exact_edition,
                    requires_confirmation, weread_catalog_status, weread_resolution,
                    shelf_membership, weread_reading_state, weread_progress,
                    strongest_douban_state, suggested_douban_state, deep_link,
                    catalog_search_limit, recorded_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(direction, item_id, shelf_sync_at, history_sync_at, policy_version)
                DO UPDATE SET
                    title=excluded.title,
                    source_state=excluded.source_state,
                    outcome=excluded.outcome,
                    user_plan=excluded.user_plan,
                    summary=excluded.summary,
                    requires_user_action=excluded.requires_user_action,
                    selected_douban_subject=excluded.selected_douban_subject,
                    selected_weread_book_id=excluded.selected_weread_book_id,
                    selected_edition_title=excluded.selected_edition_title,
                    match_kind=excluded.match_kind,
                    exact_edition=excluded.exact_edition,
                    requires_confirmation=excluded.requires_confirmation,
                    weread_catalog_status=excluded.weread_catalog_status,
                    weread_resolution=excluded.weread_resolution,
                    shelf_membership=excluded.shelf_membership,
                    weread_reading_state=excluded.weread_reading_state,
                    weread_progress=excluded.weread_progress,
                    strongest_douban_state=excluded.strongest_douban_state,
                    suggested_douban_state=excluded.suggested_douban_state,
                    deep_link=excluded.deep_link,
                    catalog_search_limit=excluded.catalog_search_limit,
                    recorded_at=excluded.recorded_at
                """,
                (
                    evidence.direction,
                    evidence.item_id.strip(),
                    evidence.shelf_sync_at,
                    evidence.history_sync_at,
                    evidence.policy_version,
                    evidence.title.strip(),
                    evidence.source_state,
                    evidence.outcome.strip(),
                    evidence.user_plan.strip(),
                    evidence.summary.strip(),
                    int(evidence.requires_user_action),
                    evidence.selected_douban_subject,
                    evidence.selected_weread_book_id,
                    evidence.selected_edition_title,
                    evidence.match_kind,
                    _bool_to_db(evidence.exact_edition),
                    _bool_to_db(evidence.requires_confirmation),
                    evidence.weread_catalog_status,
                    evidence.weread_resolution,
                    evidence.shelf_membership,
                    evidence.weread_reading_state,
                    evidence.weread_progress,
                    evidence.strongest_douban_state,
                    evidence.suggested_douban_state,
                    evidence.deep_link,
                    evidence.catalog_search_limit,
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
        policy_version: int,
    ) -> list[ReconciliationEvidence]:
        self._validate_generation(direction, shelf_sync_at, history_sync_at, policy_version)
        if not self.path.exists():
            return []
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT direction, item_id, shelf_sync_at, history_sync_at, policy_version,
                       title, source_state, outcome, user_plan, summary,
                       requires_user_action, selected_douban_subject, selected_weread_book_id,
                       selected_edition_title, match_kind, exact_edition,
                       requires_confirmation, weread_catalog_status, weread_resolution,
                       shelf_membership, weread_reading_state, weread_progress,
                       strongest_douban_state, suggested_douban_state, deep_link,
                       catalog_search_limit, recorded_at
                FROM reconciliation_evidence
                WHERE direction=? AND shelf_sync_at=? AND history_sync_at=? AND policy_version=?
                ORDER BY recorded_at, item_id
                """,
                (direction, shelf_sync_at, history_sync_at, policy_version),
            ).fetchall()
        return [_row_to_evidence(row) for row in rows]

    @staticmethod
    def _validate(evidence: ReconciliationEvidence) -> None:
        ReconciliationEvidenceStore._validate_generation(
            evidence.direction,
            evidence.shelf_sync_at,
            evidence.history_sync_at,
            evidence.policy_version,
        )
        if not evidence.item_id.strip():
            raise ValueError("Reconciliation evidence item_id must not be blank")
        if not evidence.title.strip():
            raise ValueError("Reconciliation evidence title must not be blank")
        if not evidence.outcome.strip() or not evidence.user_plan.strip() or not evidence.summary.strip():
            raise ValueError("Reconciliation evidence outcome, user_plan, and summary are required")
        if evidence.shelf_membership not in _ALLOWED_SHELF_MEMBERSHIP:
            raise ValueError("Reconciliation evidence shelf_membership is invalid")
        if evidence.weread_progress is not None and not 0 <= evidence.weread_progress <= 100:
            raise ValueError("Reconciliation evidence weread_progress must be between 0 and 100")
        if evidence.catalog_search_limit is not None and evidence.catalog_search_limit < 1:
            raise ValueError("Reconciliation evidence catalog_search_limit must be >= 1")

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
            raise ValueError("Complete baseline timestamps are required for reconciliation evidence")
        if policy_version < 1:
            raise ValueError("Reconciliation evidence policy_version must be >= 1")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def _bool_to_db(value: bool | None) -> int | None:
    return None if value is None else int(value)


def _db_to_bool(value: object) -> bool | None:
    return None if value is None else bool(int(value))


def _row_to_evidence(row: tuple[object, ...]) -> ReconciliationEvidence:
    return ReconciliationEvidence(
        direction=str(row[0]),
        item_id=str(row[1]),
        shelf_sync_at=str(row[2]),
        history_sync_at=str(row[3]),
        policy_version=int(row[4]),
        title=str(row[5]),
        source_state=str(row[6]) if row[6] is not None else None,
        outcome=str(row[7]),
        user_plan=str(row[8]),
        summary=str(row[9]),
        requires_user_action=bool(int(row[10])),
        selected_douban_subject=str(row[11]) if row[11] is not None else None,
        selected_weread_book_id=str(row[12]) if row[12] is not None else None,
        selected_edition_title=str(row[13]) if row[13] is not None else None,
        match_kind=str(row[14]) if row[14] is not None else None,
        exact_edition=_db_to_bool(row[15]),
        requires_confirmation=_db_to_bool(row[16]),
        weread_catalog_status=str(row[17]) if row[17] is not None else None,
        weread_resolution=str(row[18]) if row[18] is not None else None,
        shelf_membership=str(row[19]) if row[19] is not None else None,
        weread_reading_state=str(row[20]) if row[20] is not None else None,
        weread_progress=int(row[21]) if row[21] is not None else None,
        strongest_douban_state=str(row[22]) if row[22] is not None else None,
        suggested_douban_state=str(row[23]) if row[23] is not None else None,
        deep_link=str(row[24]) if row[24] is not None else None,
        catalog_search_limit=int(row[25]) if row[25] is not None else None,
        recorded_at=str(row[26]),
    )
