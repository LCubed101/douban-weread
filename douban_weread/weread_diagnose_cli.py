from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from typing import Protocol, TextIO

from douban_weread.core.models import Edition
from douban_weread.providers.douban import DoubanBookSearchClient, DoubanProviderError
from douban_weread.providers.weread import WeReadClient, WeReadProviderError, WeReadSearchCandidate
from douban_weread.resolver import compare_editions


class WeReadDiagnosticProvider(Protocol):
    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]: ...

    def get_book(self, book_id: str) -> Edition | None: ...


class DoubanEditionProvider(Protocol):
    def get_by_subject_id(self, subject_id: str) -> Edition | None: ...

    def search_by_isbn(self, isbn: str) -> Edition | None: ...


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="douban-weread weread diagnose",
        description="Read-only diagnostic for Douban→WeRead Edition resolution.",
    )
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--subject", help="Exact Douban Book subject ID.")
    identity.add_argument("--isbn", help="Exact ISBN for the Douban Edition.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum WeRead search candidates to inspect.")
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    weread_provider: WeReadDiagnosticProvider | None = None,
    douban_provider: DoubanEditionProvider | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    weread = weread_provider or WeReadClient(api_key=os.getenv("WEREAD_API_KEY", ""))
    douban = douban_provider or DoubanBookSearchClient()

    try:
        source = (
            douban.get_by_subject_id(args.subject)
            if args.subject
            else douban.search_by_isbn(args.isbn)
        )
    except (DoubanProviderError, ValueError) as exc:
        print(f"Douban provider error: {exc}", file=stderr)
        return 1
    if source is None:
        identity = f"subject {args.subject}" if args.subject else f"ISBN {args.isbn}"
        print(f"No Douban Edition found for {identity}.", file=stdout)
        return 3

    limit = max(1, min(args.limit, 100))
    try:
        candidates = weread.search_books(source.title, count=limit)
    except (WeReadProviderError, ValueError) as exc:
        print(f"WeRead provider error: {exc}", file=stderr)
        return 1

    print("Douban source:", file=stdout)
    print(_edition_line(source), file=stdout)
    print(f"\nWeRead search returned {len(candidates)} candidate(s) for {source.title!r} (limit={limit}).", file=stdout)

    if not candidates:
        return 0

    for index, candidate in enumerate(candidates, start=1):
        print(f"\n[{index}] Search candidate", file=stdout)
        print(f"title={candidate.title}", file=stdout)
        print(f"bookId={candidate.book_id}", file=stdout)
        print(f"soldout={candidate.soldout}", file=stdout)
        print(f"author={candidate.author or '-'}", file=stdout)
        print(f"publisher={candidate.publisher or '-'}", file=stdout)
        print(f"deepLink={candidate.deep_link or '-'}", file=stdout)

        try:
            edition = weread.get_book(candidate.book_id)
        except (WeReadProviderError, ValueError) as exc:
            print(f"book_info_error={exc}", file=stdout)
            continue
        if edition is None:
            print("book_info=missing", file=stdout)
            continue

        print("book_info=" + _edition_line(edition), file=stdout)
        match = compare_editions(source, edition)
        print(f"resolver.kind={match.kind.value}", file=stdout)
        print(f"resolver.same_work={match.same_work}", file=stdout)
        print(f"resolver.exact_edition={match.exact_edition}", file=stdout)
        print(f"resolver.requires_confirmation={match.requires_confirmation}", file=stdout)
        print(f"resolver.safe_to_auto_apply={match.safe_to_auto_apply}", file=stdout)
        if match.reasons:
            print("resolver.reasons=" + "; ".join(match.reasons), file=stdout)
        if match.edition_differences:
            print("resolver.edition_differences=" + "; ".join(match.edition_differences), file=stdout)
        if match.material_differences:
            print("resolver.material_differences=" + "; ".join(match.material_differences), file=stdout)
    return 0


def _edition_line(edition: Edition) -> str:
    return " | ".join(
        [
            f"title={edition.title}",
            f"authors={'、'.join(edition.authors) if edition.authors else '-'}",
            f"publisher={edition.publisher or '-'}",
            f"publish_date={edition.publish_date or '-'}",
            f"isbn={edition.isbn or '-'}",
            f"douban_id={edition.douban_id or '-'}",
            f"weread_id={edition.weread_id or '-'}",
        ]
    )


def main() -> None:
    raise SystemExit(run())
