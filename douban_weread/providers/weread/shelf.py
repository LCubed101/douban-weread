from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class WeReadShelfBook:
    book_id: str
    title: str
    author: str | None = None
    deep_link: str | None = None
    cover_url: str | None = None
    category: str | None = None
    read_update_time: int | None = None
    finish_reading: bool = False
    update_time: int | None = None
    is_top: bool = False
    secret: bool = False
    source_metadata: dict[str, object] = field(default_factory=dict, repr=False, compare=False)


@dataclass(slots=True, frozen=True)
class WeReadShelfArchive:
    name: str
    book_ids: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class WeReadShelfSnapshot:
    books: tuple[WeReadShelfBook, ...]
    album_count: int
    has_mp: bool
    archives: tuple[WeReadShelfArchive, ...] = ()

    @property
    def book_count(self) -> int:
        return len(self.books)

    @property
    def visible_entry_count(self) -> int:
        return self.book_count + self.album_count + (1 if self.has_mp else 0)


def parse_shelf_payload(payload: dict[str, object]) -> WeReadShelfSnapshot:
    raw_books = payload.get("books", [])
    if not isinstance(raw_books, list):
        raise ValueError("WeRead shelf response has invalid books[]")

    books: list[WeReadShelfBook] = []
    seen: set[str] = set()
    for raw in raw_books:
        if not isinstance(raw, dict):
            raise ValueError("WeRead shelf response contains an invalid book entry")
        book_id = _required_text(raw.get("bookId"), field="bookId")
        title = _required_text(raw.get("title"), field="title")
        if book_id in seen:
            raise ValueError(f"WeRead shelf response contains duplicate bookId {book_id}")
        seen.add(book_id)
        books.append(
            WeReadShelfBook(
                book_id=book_id,
                title=title,
                author=_optional_text(raw.get("author")),
                deep_link=_optional_text(raw.get("deepLink")),
                cover_url=_optional_text(raw.get("cover")),
                category=_optional_text(raw.get("category")),
                read_update_time=_optional_int(raw.get("readUpdateTime")),
                finish_reading=_as_bool_flag(raw.get("finishReading")),
                update_time=_optional_int(raw.get("updateTime")),
                is_top=_as_bool_flag(raw.get("isTop")),
                secret=_as_bool_flag(raw.get("secret")),
                source_metadata={"raw": dict(raw)},
            )
        )

    raw_albums = payload.get("albums", [])
    if not isinstance(raw_albums, list):
        raise ValueError("WeRead shelf response has invalid albums[]")

    raw_archives = payload.get("archive", [])
    if raw_archives is None:
        raw_archives = []
    if not isinstance(raw_archives, list):
        raise ValueError("WeRead shelf response has invalid archive[]")

    archives: list[WeReadShelfArchive] = []
    for raw in raw_archives:
        if not isinstance(raw, dict):
            raise ValueError("WeRead shelf response contains an invalid archive entry")
        name = _optional_text(raw.get("name")) or ""
        raw_ids = raw.get("bookIds", [])
        if not isinstance(raw_ids, list):
            raise ValueError("WeRead shelf archive has invalid bookIds[]")
        book_ids = tuple(str(item).strip() for item in raw_ids if str(item).strip())
        archives.append(WeReadShelfArchive(name=name, book_ids=book_ids))

    return WeReadShelfSnapshot(
        books=tuple(books),
        album_count=len(raw_albums),
        has_mp=payload.get("mp") not in (None, {}, [], ""),
        archives=tuple(archives),
    )


def _required_text(value: object, *, field: str) -> str:
    text = _optional_text(value)
    if not text:
        raise ValueError(f"WeRead shelf book is missing {field}")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_bool_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none"}
    return bool(value)
