from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from typing import Protocol, TextIO

from douban_weread.alignment import align_to_weread
from douban_weread.core.models import Edition
from douban_weread.providers.douban import DoubanBookSearchClient, DoubanProviderError
from douban_weread.providers.weread import (
    WeReadClient,
    WeReadProgress,
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

    def get_progress(self, book_id: str) -> WeReadProgress | None: ...


class DoubanEditionClient(Protocol):
    def get_by_subject_id(self, subject_id: str) -> Edition | None: ...


WeReadClientFactory = Callable[[], WeReadSearchClient]
DoubanClientFactory = Callable[[], DoubanEditionClient]


def _default_client() -> WeReadClient:
    return WeReadClient(api_key=os.getenv("WEREAD_API_KEY", ""))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="douban-weread weread",
        description="Read-only WeRead search, metadata lookup, progress, Edition comparison, and alignment.",
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

    progress = subparsers.add_parser(
        "progress",
        help="Fetch official reading progress for one exact WeRead bookId.",
        description=(
            "Read-only /book/getprogress lookup. The coarse state is intentionally conservative: "
            "progress=100 is treated as read only when finishTime is also present."
        ),
    )
    progress.add_argument("--id", required=True, dest="book_id", help="Exact WeRead bookId to inspect.")

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

    resolve = subparsers.add_parser(
        "resolve",
        help="Resolve one Douban Edition to an available WeRead Edition.",
        description=(
            "Read-only bounded alignment. Fetches the exact Douban subject, searches official WeRead, resolves "
            "candidate metadata, and maps resolver evidence into ReadingIntent availability."
        ),
    )
    resolve.add_argument("--subject", required=True, help="Exact Douban Book subject ID to align.")
    resolve.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum WeRead search candidates considered (default: 5).",
    )
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


def format_progress(progress: WeReadProgress) -> str:
    lines = [
        f"WeRead bookId: {progress.book_id}",
        f"Progress: {progress.progress}%",
        f"Started: {'yes' if progress.is_started else 'no'}",
        f"Coarse state: {progress.reading_state}",
    ]
    if progress.update_time is not None:
        lines.append(f"Last reading update: {progress.update_time}")
    if progress.reading_time_seconds is not None:
        lines.append(f"Recorded reading time: {progress.reading_time_seconds} seconds")
    if progress.finish_time is not None:
        lines.append(f"Finish time: {progress.finish_time}")
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

    if args.weread_command == "progress":
        client = client_factory()
        try:
            progress = client.get_progress(args.book_id)
        except (WeReadProviderError, ValueError) as exc:
            print(f"WeRead provider error: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR

        if progress is None:
            print(f"No WeRead progress found for bookId {args.book_id}.", file=stdout)
            return EXIT_NO_RESULTS

        print("WeRead reading progress:\n", file=stdout)
        print(format_progress(progress), file=stdout)
        print(
            "\nProgress is user-specific read-only evidence. It is not used to mutate Douban state by this command.",
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

    if args.weread_command == "resolve":
        weread_client = client_factory()
        douban_client = douban_client_factory()
        try:
            source = douban_client.get_by_subject_id(args.subject)
        except (DoubanProviderError, ValueError) as exc:
            print(f"Douban provider error: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR

        if source is None:
            print(f"No Douban Edition found for subject {args.subject}.", file=stdout)
            return EXIT_NO_RESULTS

        try:
            aligned = align_to_weread(
                source,
                weread_client,
                limit=max(1, min(args.limit, 100)),
            )
        except (WeReadProviderError, ValueError) as exc:
            print(f"WeRead provider error: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR

        intent = aligned.intent
        print("Cross-platform ReadingIntent:\n", file=stdout)
        print(f"Work: {intent.work.canonical_title}", file=stdout)
        print(f"Douban subject: {source.douban_id or args.subject}", file=stdout)
        print(f"WeRead status: {intent.weread_status.value}", file=stdout)
        print(f"Resolution: {intent.resolution.value}", file=stdout)
        print(f"Examined WeRead Editions: {aligned.examined_candidates}", file=stdout)

        if intent.selected_edition is not None:
            print("\nSelected WeRead Edition:\n", file=stdout)
            print(format_book(intent.selected_edition), file=stdout)
        if aligned.candidate is not None:
            print(f"   Search sold out: {'yes' if aligned.candidate.soldout else 'no'}", file=stdout)
        if aligned.match is not None:
            print("\nResolver evidence:", file=stdout)
            print(f"Match: {aligned.match.kind.value}", file=stdout)
            print(f"Same Work: {aligned.match.same_work}", file=stdout)
            print(f"Exact Edition: {aligned.match.exact_edition}", file=stdout)
            print(f"Requires confirmation: {aligned.match.requires_confirmation}", file=stdout)
            if aligned.match.reasons:
                print(f"Reasons: {'; '.join(aligned.match.reasons)}", file=stdout)
        if intent.notes:
            print("\nNotes:", file=stdout)
            for note in intent.notes:
                print(f"- {note}", file=stdout)
        return EXIT_OK

    parser.error(f"unsupported WeRead command: {args.weread_command}")
    return 2


def main() -> None:
    raise SystemExit(run())
