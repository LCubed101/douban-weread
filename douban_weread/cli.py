from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from typing import Protocol, TextIO

from douban_weread.core.models import Edition
from douban_weread.providers.douban import DoubanBookSearchClient, DoubanProviderError


EXIT_OK = 0
EXIT_PROVIDER_ERROR = 1
EXIT_NO_RESULTS = 3


class BookSearchClient(Protocol):
    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]: ...

    def search_by_isbn(self, isbn: str) -> Edition | None: ...


ClientFactory = Callable[[], BookSearchClient]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="douban-weread",
        description="Search and inspect Douban book editions.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser(
        "search",
        help="Search Douban by title or ISBN.",
        description="Search Douban and print candidate editions for manual confirmation.",
    )
    group = search.add_mutually_exclusive_group(required=True)
    group.add_argument("query", nargs="?", help="Book title to search for.")
    group.add_argument("--isbn", help="ISBN-10 or ISBN-13 for exact edition lookup.")
    search.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum title-search candidates to display (default: 10).",
    )

    return parser


def format_edition(edition: Edition, *, index: int | None = None) -> str:
    heading = f"{index}. {edition.title}" if index is not None else edition.title
    lines = [heading]

    if edition.authors:
        lines.append(f"   Authors: {', '.join(edition.authors)}")
    if edition.translators:
        lines.append(f"   Translators: {', '.join(edition.translators)}")

    publication = " · ".join(
        value for value in (edition.publisher, edition.publish_date) if value
    )
    if publication:
        lines.append(f"   Publication: {publication}")
    if edition.isbn:
        lines.append(f"   ISBN: {edition.isbn}")
    if edition.douban_id:
        lines.append(f"   Douban: https://book.douban.com/subject/{edition.douban_id}/")

    return "\n".join(lines)


def _print_title_results(
    editions: Sequence[Edition],
    *,
    query: str,
    stdout: TextIO,
) -> int:
    if not editions:
        print(f'No Douban editions found for "{query}".', file=stdout)
        return EXIT_NO_RESULTS

    noun = "edition" if len(editions) == 1 else "editions"
    print(f'Found {len(editions)} candidate {noun} for "{query}":\n', file=stdout)
    for index, edition in enumerate(editions, start=1):
        print(format_edition(edition, index=index), file=stdout)
        if index != len(editions):
            print(file=stdout)

    if len(editions) > 1:
        print(
            "\nMultiple editions found. Confirm translator, publisher, year, and ISBN before changing reading state.",
            file=stdout,
        )
    return EXIT_OK


def _print_isbn_result(edition: Edition | None, *, isbn: str, stdout: TextIO) -> int:
    if edition is None:
        print(f"No Douban edition found for ISBN {isbn}.", file=stdout)
        return EXIT_NO_RESULTS

    print("Exact ISBN result:\n", file=stdout)
    print(format_edition(edition), file=stdout)
    return EXIT_OK


def run(
    argv: Sequence[str] | None = None,
    *,
    client_factory: ClientFactory = DoubanBookSearchClient,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    client = client_factory()

    if args.command == "search":
        try:
            if args.isbn:
                return _print_isbn_result(
                    client.search_by_isbn(args.isbn),
                    isbn=args.isbn,
                    stdout=stdout,
                )

            limit = max(1, min(args.limit, 100))
            editions = client.search_by_title(args.query, count=limit)
            return _print_title_results(editions, query=args.query, stdout=stdout)
        except DoubanProviderError as exc:
            print(f"Douban provider error: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR

    parser.error(f"unsupported command: {args.command}")
    return 2


def main() -> None:
    raise SystemExit(run())
