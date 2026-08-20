from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections.abc import Callable, Sequence
from typing import Protocol, TextIO

from douban_weread.providers.weread import (
    WeReadClient,
    WeReadProviderError,
    WeReadShelfSnapshot,
)
from douban_weread.storage import (
    IndexedWeReadShelfBook,
    WeReadShelfIndex,
    WeReadShelfIndexStatus,
)


EXIT_OK = 0
EXIT_PROVIDER_ERROR = 1
EXIT_NO_RESULTS = 3


class WeReadShelfClient(Protocol):
    def sync_shelf(self) -> WeReadShelfSnapshot: ...


class ShelfIndex(Protocol):
    def replace_full(self, snapshot: WeReadShelfSnapshot, *, synced_at: str | None = None) -> None: ...

    def status(self) -> WeReadShelfIndexStatus: ...

    def find_title_candidates(
        self,
        title: str,
        *,
        limit: int = 30,
        min_similarity: float = 0.72,
    ) -> list[IndexedWeReadShelfBook]: ...


ShelfClientFactory = Callable[[], WeReadShelfClient]
ShelfIndexFactory = Callable[[], ShelfIndex]


def _default_client() -> WeReadClient:
    return WeReadClient(api_key=os.getenv("WEREAD_API_KEY", ""))


def _default_index() -> WeReadShelfIndex:
    return WeReadShelfIndex()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="douban-weread weread shelf",
        description="Build and inspect the local read-only WeRead shelf baseline.",
    )
    subparsers = parser.add_subparsers(dest="shelf_command", required=True)

    subparsers.add_parser(
        "sync",
        help="Fetch the official WeRead shelf and atomically replace the local baseline.",
        description=(
            "Read-only official /shelf/sync. Electronic books are indexed for later Work/Edition reconciliation; "
            "albums/audio books and the article-collection entry are preserved only as baseline counts."
        ),
    )

    subparsers.add_parser(
        "status",
        help="Show the local WeRead shelf baseline without network access.",
    )

    lookup = subparsers.add_parser(
        "lookup",
        help="Search the local WeRead electronic-book shelf by title without network access.",
    )
    lookup.add_argument("query", help="Book title or approximate title to search locally.")
    lookup.add_argument("--limit", type=int, default=20, help="Maximum local candidates to show.")
    return parser


def format_shelf_status(status: WeReadShelfIndexStatus) -> str:
    if not status.initialized or not status.complete:
        return f"WeRead shelf baseline: not synced\nDatabase: {status.path}"

    return "\n".join(
        [
            "WeRead shelf baseline: complete",
            f"Visible shelf entries: {status.visible_entries}",
            f"Electronic books: {status.books}",
            f"Albums / audio books: {status.albums}",
            f"Article collection: {'yes' if status.has_mp else 'no'}",
            f"Last full sync: {status.last_full_sync_at}",
            f"Database: {status.path}",
        ]
    )


def format_lookup_candidate(item: IndexedWeReadShelfBook) -> str:
    details = [f"bookId {item.book_id}", item.title]
    if item.author:
        details.append(item.author)
    details.append(f"finished: {'yes' if item.finish_reading else 'no'}")
    if item.secret:
        details.append("private")
    return " | ".join(details)


def run(
    argv: Sequence[str] | None = None,
    *,
    client_factory: ShelfClientFactory = _default_client,
    index_factory: ShelfIndexFactory = _default_index,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.shelf_command == "sync":
        client = client_factory()
        index = index_factory()
        try:
            snapshot = client.sync_shelf()
            index.replace_full(snapshot)
            status = index.status()
        except (WeReadProviderError, ValueError, OSError, sqlite3.Error) as exc:
            print(f"WeRead shelf sync error: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR

        print("WeRead shelf baseline synced successfully.", file=stdout)
        print(format_shelf_status(status), file=stdout)
        return EXIT_OK

    if args.shelf_command == "status":
        index = index_factory()
        try:
            status = index.status()
        except (OSError, sqlite3.Error) as exc:
            print(f"WeRead shelf database error: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR

        print(format_shelf_status(status), file=stdout)
        return EXIT_OK if status.complete else EXIT_NO_RESULTS

    if args.shelf_command == "lookup":
        index = index_factory()
        try:
            status = index.status()
            candidates = index.find_title_candidates(
                args.query,
                limit=max(1, min(args.limit, 100)),
            )
        except (OSError, sqlite3.Error, ValueError) as exc:
            print(f"WeRead shelf database error: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR

        if not status.complete:
            print(
                "WeRead shelf baseline is not complete. Run `douban-weread weread shelf sync` first.",
                file=stderr,
            )
            return EXIT_NO_RESULTS

        if not candidates:
            print(f'No local WeRead shelf candidates found for "{args.query}".', file=stdout)
            return EXIT_NO_RESULTS

        print(f'Local WeRead shelf candidates for "{args.query}":', file=stdout)
        for item in candidates:
            print(f"- {format_lookup_candidate(item)}", file=stdout)
        print(
            "Local shelf title matches are candidates only; Work/Edition verification is still required.",
            file=stdout,
        )
        return EXIT_OK

    parser.error(f"unsupported WeRead shelf command: {args.shelf_command}")
    return 2


def main() -> None:
    raise SystemExit(run())
