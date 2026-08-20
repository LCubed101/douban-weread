from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from typing import Protocol, TextIO

from douban_weread.core.models import Edition
from douban_weread.providers.douban import DoubanBookSearchClient, DoubanProviderError
from douban_weread.providers.weread import (
    WeReadClient,
    WeReadProviderError,
    WeReadSearchCandidate,
)
from douban_weread.resolver import compare_editions


EXIT_OK = 0
EXIT_PROVIDER_ERROR = 1
EXIT_NO_RESULTS = 3


class WeReadSearchClient(Protocol):
    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]: ...

    def get_book(self, book_id: str) -> Edition | None: ...


class DoubanEditionClient(Protocol):
    def get_by_subject_id(self, subject_id: str) -> Edition | None: ...


WeReadClientFactory = Callable[[], WeReadSearchClient]
DoubanClientFactory = Callable[[], DoubanEditionClient]


def _default_client() -> WeReadClient:
    return WeReadClient(api_key=os.getenv("WEREAD_API_KEY", ""))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="douban-weread weread",
        description="Read-only WeRead search, metadata lookup, and cross-platform Edition comparison.",
    )
    subparsers = parser.add_subparsers(dest="weread_command", required=True)

    search = subparsers.add_parser(
        "search",
        help="Search WeRead e-books by keyword.",
        description=(
            "Read-only official WeRead search. Results are catalog candidates only; "
            "Edition identity still requires /book/info plus the cross-platform resolver."
        ),
    )
    search.add_argument("query", help="Book title or keyword to search for.")
    search.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum search candidates requested from WeRead (default: 5).",
    )

    book = subparsers.add_parser(
        "book",
        help="Fetch normalized metadata for one exact WeRead bookId.",
        description=(
            "Read-only /book/info lookup. Prints normalized Edition metadata for resolver validation; "
            "it does not change WeRead state."
        ),
    )
    book.add_argument("--id", required=True, dest="book_id", help="Exact WeRead bookId to inspect.")

    compare = subparsers.add_parser(
        "compare",
        help="Compare one exact Douban subject with one exact WeRead bookId.",
        description=(
            "Read-only cross-platform Edition comparison. Fetches both exact records and runs the existing "
            "provider-agnostic resolver; it does not infer catalog availability or change either service."
        ),
    )
    compare.add_argument("--subject", required=True, help="Exact Douban Book subject ID.")
    compare.add_argument("--id", required=True, dest="book_id", help="Exact WeRead bookId.")
    return parser


def format_search_candidate(candidate: WeReadSearchCandidate, *, index: int) -> str:
    lines = [f"{index}. {candidate.title}"]
    if candidate.author:
        lines.append(f"   Author: {candidate.author}")
    if candidate.publisher:
        lines.append(f"   Publisher: {candidate.publisher}")
    lines.append(f"   WeRead bookId: {candidate.book_id}")
    lines.append(f"   Sold out: {'yes' if candidate.soldout else 'no'}")
    if candidate.deep_link:
        lines.append(f"   Deep link: {candidate.deep_link}")
    return "\n".join(lines)


def format_book(edition: Edition) -> str:
    lines = [edition.title]
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
        lines.append(f"   Douban subject: {edition.douban_id}")
    if edition.weread_id:
        lines.append(f"   WeRead bookId: {edition.weread_id}")
    deep_link = edition.source_metadata.get("deep_link")
    if isinstance(deep_link, str) and deep_link.strip():
        lines.append(f"   Deep link: {deep_link.strip()}")
    return "\n".join(lines)


def run(
    argv: Sequence[str] | None = None,
    *,
    client_factory: WeReadClientFactory = _default_client,
    douban_client_factory: DoubanClientFactory = DoubanBookSearchClient,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.weread_command == "search":
        client = client_factory()
        try:
            results = client.search_books(
                args.query,
                count=max(1, min(args.limit, 100)),
            )
        except (WeReadProviderError, ValueError) as exc:
            print(f"WeRead provider error: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR

        if not results:
            print(f'No WeRead e-book candidates found for "{args.query}".', file=stdout)
            return EXIT_NO_RESULTS

        print(f'WeRead e-book candidates for "{args.query}":\n', file=stdout)
        for index, candidate in enumerate(results, start=1):
            print(format_search_candidate(candidate, index=index), file=stdout)
            if index != len(results):
                print(file=stdout)
        print(
            "\nSearch hits are catalog candidates only. `Sold out: no` is not yet treated as proof of exact Edition identity or readability.",
            file=stdout,
        )
        return EXIT_OK

    if args.weread_command == "book":
        client = client_factory()
        try:
            edition = client.get_book(args.book_id)
        except (WeReadProviderError, ValueError) as exc:
            print(f"WeRead provider error: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR

        if edition is None:
            print(f"No WeRead book metadata found for bookId {args.book_id}.", file=stdout)
            return EXIT_NO_RESULTS

        print("WeRead book metadata:\n", file=stdout)
        print(format_book(edition), file=stdout)
        print(
            "\nMetadata is normalized for Edition comparison; availability classification still requires resolver evidence.",
            file=stdout,
        )
        return EXIT_OK

    if args.weread_command == "compare":
        weread_client = client_factory()
        douban_client = douban_client_factory()
        try:
            source = douban_client.get_by_subject_id(args.subject)
        except (DoubanProviderError, ValueError) as exc:
            print(f"Douban provider error: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR
        try:
            candidate = weread_client.get_book(args.book_id)
        except (WeReadProviderError, ValueError) as exc:
            print(f"WeRead provider error: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR

        if source is None:
            print(f"No Douban Edition found for subject {args.subject}.", file=stdout)
            return EXIT_NO_RESULTS
        if candidate is None:
            print(f"No WeRead book metadata found for bookId {args.book_id}.", file=stdout)
            return EXIT_NO_RESULTS

        result = compare_editions(source, candidate)
        print("Douban Edition:\n", file=stdout)
        print(format_book(source), file=stdout)
        print("\nWeRead Edition:\n", file=stdout)
        print(format_book(candidate), file=stdout)
        print("\nResolver result:", file=stdout)
        print(f"Match: {result.kind.value}", file=stdout)
        print(f"Same Work: {result.same_work}", file=stdout)
        print(f"Exact Edition: {result.exact_edition}", file=stdout)
        print(f"Requires confirmation: {result.requires_confirmation}", file=stdout)
        print(f"Safe to auto align: {result.safe_to_auto_apply}", file=stdout)
        if result.reasons:
            print(f"Reasons: {'; '.join(result.reasons)}", file=stdout)
        if result.edition_differences:
            print(f"Edition differences: {'; '.join(result.edition_differences)}", file=stdout)
        if result.material_differences:
            print(f"Material differences: {'; '.join(result.material_differences)}", file=stdout)
        print(
            "Availability: not assigned by this command; search `soldout` evidence is evaluated separately.",
            file=stdout,
        )
        return EXIT_OK

    parser.error(f"unsupported WeRead command: {args.weread_command}")
    return 2


def main() -> None:
    raise SystemExit(run())
