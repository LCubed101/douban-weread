from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from typing import Protocol, TextIO

from douban_weread.core.models import Edition
from douban_weread.providers.douban import (
    DoubanAuthError,
    DoubanBookInterestClient,
    DoubanBookSearchClient,
    DoubanConfirmationRequired,
    DoubanProviderError,
    DoubanWriteVerificationError,
)


EXIT_OK = 0
EXIT_PROVIDER_ERROR = 1
EXIT_NO_RESULTS = 3
EXIT_CONFIRMATION_REQUIRED = 4
EXIT_WRITE_VERIFICATION_ERROR = 5


class BookSearchClient(Protocol):
    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]: ...

    def search_by_isbn(self, isbn: str) -> Edition | None: ...


class BookInterestClient(Protocol):
    def check_auth(self, *, probe_subject_id: str = "6082808"): ...

    def mark_wish(self, subject_id: str, *, confirmed: bool = False): ...


SearchClientFactory = Callable[[], BookSearchClient]
InterestClientFactory = Callable[[], BookInterestClient]


def _default_interest_client() -> DoubanBookInterestClient:
    """Build the auth client from the local environment.

    DevTools often displays the request header as ``Cookie: a=b; c=d`` while
    the provider itself expects only the header value. Accept that common
    one-line copy format, but do not try to parse multi-line request dumps or
    shell commands.
    """
    cookie = os.getenv("DOUBAN_COOKIE", "").strip()
    if "\n" not in cookie and cookie.lower().startswith("cookie:"):
        cookie = cookie.split(":", 1)[1].strip()
    return DoubanBookInterestClient(cookie=cookie)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="douban-weread",
        description="Search, inspect, and safely update Douban book editions.",
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

    auth = subparsers.add_parser(
        "auth",
        help="Check whether the locally configured Douban Cookie is usable.",
    )
    auth_subparsers = auth.add_subparsers(dest="auth_command", required=True)
    auth_check = auth_subparsers.add_parser("check", help="Validate DOUBAN_COOKIE without changing state.")
    auth_check.add_argument(
        "--probe-subject",
        default="6082808",
        help="Read-only Douban subject used for the authenticated endpoint probe.",
    )

    wish = subparsers.add_parser(
        "wish",
        help="Mark one explicitly selected Douban Book subject as Want-to-Read.",
        description=(
            "State-changing command. It requires --confirm and verifies the saved state after the write."
        ),
    )
    wish.add_argument("--subject", required=True, help="Exact Douban Book subject ID to update.")
    wish.add_argument(
        "--confirm",
        action="store_true",
        help="Explicitly confirm that the subject ID/edition has been selected and may be changed.",
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
    client_factory: SearchClientFactory = DoubanBookSearchClient,
    interest_client_factory: InterestClientFactory = _default_interest_client,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "search":
        client = client_factory()
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

    if args.command == "auth" and args.auth_command == "check":
        client = interest_client_factory()
        status = client.check_auth(probe_subject_id=args.probe_subject)
        if status.ok:
            suffix = f" (user {status.user_id})" if status.user_id else ""
            print(f"Douban auth OK{suffix}: {status.message}", file=stdout)
            return EXIT_OK
        print(f"Douban auth failed [{status.reason}]: {status.message}", file=stderr)
        return EXIT_PROVIDER_ERROR

    if args.command == "wish":
        client = interest_client_factory()
        try:
            result = client.mark_wish(args.subject, confirmed=args.confirm)
        except DoubanConfirmationRequired as exc:
            print(f"Confirmation required: {exc}", file=stderr)
            return EXIT_CONFIRMATION_REQUIRED
        except DoubanWriteVerificationError as exc:
            print(f"Douban write verification error: {exc}", file=stderr)
            return EXIT_WRITE_VERIFICATION_ERROR
        except (DoubanAuthError, DoubanProviderError, ValueError) as exc:
            print(f"Douban wish error: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR

        print(
            f"Douban subject {result.subject_id} is now marked Want-to-Read and the saved state was verified.",
            file=stdout,
        )
        return EXIT_OK

    parser.error(f"unsupported command: {args.command}")
    return 2


def main() -> None:
    raise SystemExit(run())
