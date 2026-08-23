from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from douban_weread.core.models import Edition


def default_weread_watch_db_path() -> Path:
    override = os.getenv("DOUBAN_WEREAD_WATCH_DB", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "douban-weread" / "weread_watch.sqlite3"


@dataclass(slots=True, frozen=True)
class WeReadWatchEntry:
    id: int
    chat_id: str
    source_title: str
    source_authors: tuple[str, ...]
    source_publisher: str | None
    source_publish_date: str | None
    source_douban_id: str | None
    source_isbn: str | None
    weread_book_id: str | None
    weread_title: str | None
    deep_link: str | None
    status: str
    created_at: str
    updated_at: str
    notified_at: str | None = None

    def source_edition(self) -> Edition:
        return Edition(
            title=self.source_title,
            authors=list(self.source_authors),
            publisher=self.source_publisher,
            publish_date=self.source_publish_date,
            douban_id=self.source_douban_id,
            isbn=self.source_isbn,
        )


class WeReadAvailabilityWatchStore:
    """Persist WeRead availability watches without storing credentials or raw payloads."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else default_weread_watch_db_path()

    def add_or_refresh(
        self,
        *,
        chat_id: str,
        source: Edition,
        weread: Edition | None,
        deep_link: str | None,
    ) -> WeReadWatchEntry:
        chat = chat_id.strip()
        if not chat:
            raise ValueError("chat_id is required for a WeRead availability watch")
        if not source.title.strip():
            raise ValueError("source title is required for a WeRead availability watch")

        now = datetime.now(timezone.utc).isoformat()
        self.initialize()
        authors_json = json.dumps(source.authors, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO weread_availability_watch(
                    chat_id, source_title, source_authors_json, source_publisher,
                    source_publish_date, source_douban_id, source_isbn,
                    weread_book_id, weread_title, deep_link, status, created_at, updated_at, notified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, NULL)
                ON CONFLICT(chat_id, source_douban_id, source_title) DO UPDATE SET
                    source_authors_json=excluded.source_authors_json,
                    source_publisher=excluded.source_publisher,
                    source_publish_date=excluded.source_publish_date,
                    source_isbn=excluded.source_isbn,
                    weread_book_id=excluded.weread_book_id,
                    weread_title=excluded.weread_title,
                    deep_link=excluded.deep_link,
                    status='pending',
                    notified_at=NULL,
                    updated_at=excluded.updated_at
                """,
                (
                    chat,
                    source.title,
                    authors_json,
                    source.publisher,
                    source.publish_date,
                    source.douban_id,
                    source.isbn,
                    weread.weread_id if weread is not None else None,
                    weread.title if weread is not None else None,
                    deep_link,
                    now,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute(
                _SELECT_COLUMNS + " WHERE chat_id=? AND source_title=? AND source_douban_id IS ?",
                (chat, source.title, source.douban_id),
            ).fetchone()
        assert row is not None
        return _row_to_entry(row)

    def pending(self) -> list[WeReadWatchEntry]:
        if not self.path.exists():
            return []
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                _SELECT_COLUMNS + " WHERE status='pending' ORDER BY created_at ASC, id ASC"
            ).fetchall()
        return [_row_to_entry(row) for row in rows]

    def unnotified_available(self) -> list[WeReadWatchEntry]:
        if not self.path.exists():
            return []
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                _SELECT_COLUMNS
                + " WHERE status='available' AND notified_at IS NULL ORDER BY updated_at ASC, id ASC"
            ).fetchall()
        return [_row_to_entry(row) for row in rows]

    def mark_available(
        self,
        entry_id: int,
        *,
        weread: Edition,
        deep_link: str | None,
    ) -> WeReadWatchEntry:
        if entry_id < 1:
            raise ValueError("watch entry id must be >= 1")
        if not weread.weread_id:
            raise ValueError("available WeRead Edition must have a bookId")

        now = datetime.now(timezone.utc).isoformat()
        self.initialize()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE weread_availability_watch
                SET weread_book_id=?, weread_title=?, deep_link=?,
                    status='available', updated_at=?, notified_at=NULL
                WHERE id=? AND status='pending'
                """,
                (weread.weread_id, weread.title, deep_link, now, entry_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("pending WeRead watch entry was not found")
            conn.commit()
            row = conn.execute(_SELECT_COLUMNS + " WHERE id=?", (entry_id,)).fetchone()
        assert row is not None
        return _row_to_entry(row)

    def mark_notified(self, entry_id: int) -> WeReadWatchEntry:
        if entry_id < 1:
            raise ValueError("watch entry id must be >= 1")
        now = datetime.now(timezone.utc).isoformat()
        self.initialize()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE weread_availability_watch
                SET notified_at=?, updated_at=?
                WHERE id=? AND status='available' AND notified_at IS NULL
                """,
                (now, now, entry_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("unnotified available WeRead watch entry was not found")
            conn.commit()
            row = conn.execute(_SELECT_COLUMNS + " WHERE id=?", (entry_id,)).fetchone()
        assert row is not None
        return _row_to_entry(row)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS weread_availability_watch (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    source_title TEXT NOT NULL,
                    source_authors_json TEXT NOT NULL,
                    source_publisher TEXT,
                    source_publish_date TEXT,
                    source_douban_id TEXT,
                    source_isbn TEXT,
                    weread_book_id TEXT,
                    weread_title TEXT,
                    deep_link TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    notified_at TEXT,
                    UNIQUE(chat_id, source_douban_id, source_title)
                );
                """
            )
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(weread_availability_watch)")}
            if "notified_at" not in columns:
                conn.execute("ALTER TABLE weread_availability_watch ADD COLUMN notified_at TEXT")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)


_SELECT_COLUMNS = """
SELECT id, chat_id, source_title, source_authors_json, source_publisher,
       source_publish_date, source_douban_id, source_isbn,
       weread_book_id, weread_title, deep_link, status, created_at, updated_at, notified_at
FROM weread_availability_watch
"""


def _row_to_entry(row: tuple[object, ...]) -> WeReadWatchEntry:
    try:
        raw_authors = json.loads(str(row[3]))
    except json.JSONDecodeError:
        raw_authors = []
    authors = tuple(str(value) for value in raw_authors) if isinstance(raw_authors, list) else ()
    return WeReadWatchEntry(
        id=int(row[0]),
        chat_id=str(row[1]),
        source_title=str(row[2]),
        source_authors=authors,
        source_publisher=str(row[4]) if row[4] is not None else None,
        source_publish_date=str(row[5]) if row[5] is not None else None,
        source_douban_id=str(row[6]) if row[6] is not None else None,
        source_isbn=str(row[7]) if row[7] is not None else None,
        weread_book_id=str(row[8]) if row[8] is not None else None,
        weread_title=str(row[9]) if row[9] is not None else None,
        deep_link=str(row[10]) if row[10] is not None else None,
        status=str(row[11]),
        created_at=str(row[12]),
        updated_at=str(row[13]),
        notified_at=str(row[14]) if len(row) > 14 and row[14] is not None else None,
    )
