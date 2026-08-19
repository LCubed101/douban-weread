from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from douban_weread.providers.douban.history import HistoryEntry


_HISTORY_STATES = {"wish", "do", "collect"}
_NON_WORD_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


@dataclass(slots=True, frozen=True)
class HistoryIndexStatus:
    path: Path
    initialized: bool
    complete: bool
    last_full_sync_at: str | None
    total: int
    wish: int
    reading: int
    read: int


@dataclass(slots=True, frozen=True)
class IndexedHistoryEntry:
    subject_id: str
    title: str
    state: str
    title_key: str
    last_seen_at: str


def default_history_db_path() -> Path:
    explicit = os.getenv("DOUBAN_WEREAD_DB", "").strip()
    if explicit:
        return Path(explicit).expanduser()

    data_home = os.getenv("XDG_DATA_HOME", "").strip()
    root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return root / "douban-weread" / "history.sqlite3"


def normalize_history_title(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold().strip()
    return _NON_WORD_RE.sub("", text)


class ReadingHistoryIndex:
    """Local-first SQLite index for platform reading history.

    The first implementation stores lightweight Douban list metadata only.
    Full Edition metadata remains lazy: reconciliation can fetch details later
    for a small shortlist instead of requesting every subject page during the
    baseline sync.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else default_history_db_path()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS history_entries (
                    subject_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    title_key TEXT NOT NULL,
                    state TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_history_title_key
                    ON history_entries(title_key);
                CREATE INDEX IF NOT EXISTS idx_history_state
                    ON history_entries(state);

                CREATE TABLE IF NOT EXISTS history_sync_state (
                    source TEXT PRIMARY KEY,
                    complete INTEGER NOT NULL DEFAULT 0,
                    last_full_sync_at TEXT,
                    counts_json TEXT NOT NULL DEFAULT '{}'
                );
                """
            )

    def replace_full(self, entries: list[HistoryEntry], *, synced_at: str | None = None) -> None:
        """Atomically replace the Douban baseline only after a full fetch succeeds."""
        timestamp = synced_at or datetime.now(timezone.utc).isoformat()
        rows: dict[str, HistoryEntry] = {}
        for entry in entries:
            if entry.state not in _HISTORY_STATES:
                raise ValueError(f"Unsupported history state: {entry.state}")
            if not entry.subject_id.isdigit():
                raise ValueError("History subject IDs must contain digits only.")
            title = entry.title.strip()
            if not title:
                raise ValueError(f"History subject {entry.subject_id} is missing a title.")
            rows[entry.subject_id] = HistoryEntry(entry.subject_id, title, entry.state)

        counts = {state: 0 for state in _HISTORY_STATES}
        for entry in rows.values():
            counts[entry.state] += 1

        self.initialize()
        with self._connect() as conn:
            conn.execute("BEGIN")
            conn.execute("DELETE FROM history_entries")
            conn.executemany(
                """
                INSERT INTO history_entries(subject_id, title, title_key, state, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        entry.subject_id,
                        entry.title,
                        normalize_history_title(entry.title),
                        entry.state,
                        timestamp,
                    )
                    for entry in rows.values()
                ],
            )
            conn.execute(
                """
                INSERT INTO history_sync_state(source, complete, last_full_sync_at, counts_json)
                VALUES ('douban', 1, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    complete=excluded.complete,
                    last_full_sync_at=excluded.last_full_sync_at,
                    counts_json=excluded.counts_json
                """,
                (timestamp, json.dumps(counts, sort_keys=True)),
            )
            conn.commit()

    def status(self) -> HistoryIndexStatus:
        if not self.path.exists():
            return HistoryIndexStatus(
                path=self.path,
                initialized=False,
                complete=False,
                last_full_sync_at=None,
                total=0,
                wish=0,
                reading=0,
                read=0,
            )

        self.initialize()
        with self._connect() as conn:
            sync = conn.execute(
                "SELECT complete, last_full_sync_at FROM history_sync_state WHERE source='douban'"
            ).fetchone()
            counts = dict(
                conn.execute(
                    "SELECT state, COUNT(*) AS count FROM history_entries GROUP BY state"
                ).fetchall()
            )

        wish = int(counts.get("wish", 0))
        reading = int(counts.get("do", 0))
        read = int(counts.get("collect", 0))
        return HistoryIndexStatus(
            path=self.path,
            initialized=True,
            complete=bool(sync[0]) if sync else False,
            last_full_sync_at=sync[1] if sync else None,
            total=wish + reading + read,
            wish=wish,
            reading=reading,
            read=read,
        )

    def get(self, subject_id: str) -> IndexedHistoryEntry | None:
        if not self.path.exists():
            return None
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT subject_id, title, state, title_key, last_seen_at
                FROM history_entries WHERE subject_id=?
                """,
                (subject_id,),
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def find_title_candidates(
        self,
        title: str,
        *,
        limit: int = 30,
        min_similarity: float = 0.72,
    ) -> list[IndexedHistoryEntry]:
        """Shortlist locally by title only; this never authorizes a mutation.

        Full Work/Edition verification remains the resolver's job. Scanning a
        few thousand lightweight local rows is cheap and avoids sending the
        entire history to an LLM or refetching it from Douban.
        """
        if not self.path.exists():
            return []
        target_key = normalize_history_title(title)
        if not target_key:
            return []

        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT subject_id, title, state, title_key, last_seen_at
                FROM history_entries
                """
            ).fetchall()

        scored: list[tuple[float, IndexedHistoryEntry]] = []
        for row in rows:
            entry = self._row_to_entry(row)
            key = entry.title_key
            if key == target_key:
                score = 1.0
            elif key in target_key or target_key in key:
                score = 0.92
            else:
                score = SequenceMatcher(None, target_key, key).ratio()
            if score >= min_similarity:
                scored.append((score, entry))

        scored.sort(key=lambda item: (item[0], item[1].subject_id), reverse=True)
        return [entry for _, entry in scored[: max(1, limit)]]

    def set_state(self, subject_id: str, title: str, state: str) -> None:
        """Update one local record after a verified project-owned mutation."""
        if state not in _HISTORY_STATES:
            raise ValueError(f"Unsupported history state: {state}")
        if not subject_id.isdigit():
            raise ValueError("History subject IDs must contain digits only.")
        timestamp = datetime.now(timezone.utc).isoformat()
        self.initialize()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO history_entries(subject_id, title, title_key, state, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(subject_id) DO UPDATE SET
                    title=excluded.title,
                    title_key=excluded.title_key,
                    state=excluded.state,
                    last_seen_at=excluded.last_seen_at
                """,
                (subject_id, title.strip(), normalize_history_title(title), state, timestamp),
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> IndexedHistoryEntry:
        return IndexedHistoryEntry(
            subject_id=str(row["subject_id"]),
            title=str(row["title"]),
            state=str(row["state"]),
            title_key=str(row["title_key"]),
            last_seen_at=str(row["last_seen_at"]),
        )
