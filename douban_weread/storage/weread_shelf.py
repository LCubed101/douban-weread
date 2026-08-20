from __future__ import annotations

import json
import os
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from douban_weread.providers.weread import WeReadShelfBook, WeReadShelfSnapshot


_BASELINE_VERSION = 1


@dataclass(slots=True, frozen=True)
class WeReadShelfIndexStatus:
    path: Path
    initialized: bool
    complete: bool
    last_full_sync_at: str | None
    books: int
    albums: int
    has_mp: bool
    visible_entries: int


@dataclass(slots=True, frozen=True)
class IndexedWeReadShelfBook:
    book_id: str
    title: str
    author: str | None
    deep_link: str | None
    category: str | None
    finish_reading: bool
    read_update_time: int | None
    secret: bool
    title_key: str
    last_seen_at: str


def default_weread_shelf_db_path() -> Path:
    explicit = os.getenv("DOUBAN_WEREAD_DB", "").strip()
    if explicit:
        return Path(explicit).expanduser()

    data_home = os.getenv("XDG_DATA_HOME", "").strip()
    root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return root / "douban-weread" / "history.sqlite3"


def normalize_shelf_title(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold().strip()
    return "".join(ch for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


class WeReadShelfIndex:
    """Persistent local baseline for the user's official WeRead shelf snapshot."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else default_weread_shelf_db_path()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS weread_shelf_books (
                    book_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    title_key TEXT NOT NULL,
                    author TEXT,
                    deep_link TEXT,
                    category TEXT,
                    finish_reading INTEGER NOT NULL DEFAULT 0,
                    read_update_time INTEGER,
                    update_time INTEGER,
                    is_top INTEGER NOT NULL DEFAULT 0,
                    secret INTEGER NOT NULL DEFAULT 0,
                    last_seen_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_weread_shelf_title_key
                    ON weread_shelf_books(title_key);

                CREATE TABLE IF NOT EXISTS weread_shelf_sync_state (
                    source TEXT PRIMARY KEY,
                    complete INTEGER NOT NULL DEFAULT 0,
                    last_full_sync_at TEXT,
                    book_count INTEGER NOT NULL DEFAULT 0,
                    album_count INTEGER NOT NULL DEFAULT 0,
                    has_mp INTEGER NOT NULL DEFAULT 0,
                    archives_json TEXT NOT NULL DEFAULT '[]',
                    baseline_version INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    def replace_full(self, snapshot: WeReadShelfSnapshot, *, synced_at: str | None = None) -> None:
        timestamp = synced_at or datetime.now(timezone.utc).isoformat()
        rows: dict[str, WeReadShelfBook] = {}
        for book in snapshot.books:
            book_id = book.book_id.strip()
            title = book.title.strip()
            if not book_id:
                raise ValueError("WeRead shelf bookId must not be blank")
            if not title:
                raise ValueError(f"WeRead shelf book {book_id} is missing a title")
            if book_id in rows:
                raise ValueError(f"Duplicate WeRead shelf bookId: {book_id}")
            rows[book_id] = book

        archives_payload = [
            {"name": archive.name, "book_ids": list(archive.book_ids)}
            for archive in snapshot.archives
        ]

        self.initialize()
        with self._connect() as conn:
            conn.execute("BEGIN")
            conn.execute("DELETE FROM weread_shelf_books")
            conn.executemany(
                """
                INSERT INTO weread_shelf_books(
                    book_id, title, title_key, author, deep_link, category,
                    finish_reading, read_update_time, update_time, is_top,
                    secret, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        book.book_id,
                        book.title,
                        normalize_shelf_title(book.title),
                        book.author,
                        book.deep_link,
                        book.category,
                        int(book.finish_reading),
                        book.read_update_time,
                        book.update_time,
                        int(book.is_top),
                        int(book.secret),
                        timestamp,
                    )
                    for book in rows.values()
                ],
            )
            conn.execute(
                """
                INSERT INTO weread_shelf_sync_state(
                    source, complete, last_full_sync_at, book_count,
                    album_count, has_mp, archives_json, baseline_version
                )
                VALUES ('weread', 1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    complete=excluded.complete,
                    last_full_sync_at=excluded.last_full_sync_at,
                    book_count=excluded.book_count,
                    album_count=excluded.album_count,
                    has_mp=excluded.has_mp,
                    archives_json=excluded.archives_json,
                    baseline_version=excluded.baseline_version
                """,
                (
                    timestamp,
                    len(rows),
                    snapshot.album_count,
                    int(snapshot.has_mp),
                    json.dumps(archives_payload, ensure_ascii=False, sort_keys=True),
                    _BASELINE_VERSION,
                ),
            )
            conn.commit()

    def status(self) -> WeReadShelfIndexStatus:
        if not self.path.exists():
            return WeReadShelfIndexStatus(
                path=self.path,
                initialized=False,
                complete=False,
                last_full_sync_at=None,
                books=0,
                albums=0,
                has_mp=False,
                visible_entries=0,
            )

        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT complete, last_full_sync_at, book_count, album_count,
                       has_mp, baseline_version
                FROM weread_shelf_sync_state WHERE source='weread'
                """
            ).fetchone()
            actual_books = int(conn.execute("SELECT COUNT(*) FROM weread_shelf_books").fetchone()[0])

        if not row:
            return WeReadShelfIndexStatus(
                path=self.path,
                initialized=True,
                complete=False,
                last_full_sync_at=None,
                books=actual_books,
                albums=0,
                has_mp=False,
                visible_entries=actual_books,
            )

        books = actual_books
        albums = int(row[3])
        has_mp = bool(row[4])
        complete = bool(row[0]) and int(row[5]) == _BASELINE_VERSION and int(row[2]) == books
        return WeReadShelfIndexStatus(
            path=self.path,
            initialized=True,
            complete=complete,
            last_full_sync_at=row[1],
            books=books,
            albums=albums,
            has_mp=has_mp,
            visible_entries=books + albums + (1 if has_mp else 0),
        )

    def get(self, book_id: str) -> IndexedWeReadShelfBook | None:
        if not self.path.exists():
            return None
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT book_id, title, author, deep_link, category,
                       finish_reading, read_update_time, secret, title_key, last_seen_at
                FROM weread_shelf_books WHERE book_id=?
                """,
                (book_id,),
            ).fetchone()
        return self._row_to_book(row) if row else None

    def all_books(self) -> list[IndexedWeReadShelfBook]:
        """Return the complete local electronic-book shelf without network access."""
        if not self.path.exists():
            return []
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT book_id, title, author, deep_link, category,
                       finish_reading, read_update_time, secret, title_key, last_seen_at
                FROM weread_shelf_books
                ORDER BY title_key, book_id
                """
            ).fetchall()
        return [self._row_to_book(row) for row in rows]

    def find_title_candidates(self, title: str, *, limit: int = 30, min_similarity: float = 0.72) -> list[IndexedWeReadShelfBook]:
        if not self.path.exists():
            return []
        target = normalize_shelf_title(title)
        if not target:
            return []

        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT book_id, title, author, deep_link, category,
                       finish_reading, read_update_time, secret, title_key, last_seen_at
                FROM weread_shelf_books
                """
            ).fetchall()

        scored: list[tuple[float, IndexedWeReadShelfBook]] = []
        for row in rows:
            item = self._row_to_book(row)
            if item.title_key == target:
                score = 1.0
            elif target in item.title_key or item.title_key in target:
                shorter = min(len(target), len(item.title_key))
                longer = max(len(target), len(item.title_key))
                score = 0.92 if shorter >= 2 and shorter / longer >= 0.60 else 0.0
            else:
                score = SequenceMatcher(None, target, item.title_key).ratio()
            if score >= min_similarity:
                scored.append((score, item))

        scored.sort(key=lambda pair: (pair[0], pair[1].book_id), reverse=True)
        return [item for _, item in scored[: max(1, min(limit, 100))]]

    @staticmethod
    def _row_to_book(row: sqlite3.Row | tuple[object, ...]) -> IndexedWeReadShelfBook:
        return IndexedWeReadShelfBook(
            book_id=str(row[0]),
            title=str(row[1]),
            author=str(row[2]) if row[2] is not None else None,
            deep_link=str(row[3]) if row[3] is not None else None,
            category=str(row[4]) if row[4] is not None else None,
            finish_reading=bool(row[5]),
            read_update_time=int(row[6]) if row[6] is not None else None,
            secret=bool(row[7]),
            title_key=str(row[8]),
            last_seen_at=str(row[9]),
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
