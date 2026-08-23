from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from douban_weread.inbox_weread import (
    WEREAD_LOOKUP_ERRORS,
    WeReadEditionLookup,
    WeReadLookupKind,
)
from douban_weread.storage.weread_watch import WeReadAvailabilityWatchStore


EXIT_OK = 0
EXIT_PROVIDER_ERROR = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="douban-weread weread watch",
        description="List or recheck local pending WeRead availability watches.",
    )
    subparsers = parser.add_subparsers(dest="watch_command", required=True)
    subparsers.add_parser("list", help="List books currently waiting for WeRead availability.")
    subparsers.add_parser(
        "check",
        help="Read-only recheck all pending watches and mark newly readable Editions available.",
    )
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    store: WeReadAvailabilityWatchStore | None = None,
    lookup: WeReadEditionLookup | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    watch_store = store or WeReadAvailabilityWatchStore()

    if args.watch_command == "list":
        entries = watch_store.pending()
        if not entries:
            print("No pending WeRead availability watches.", file=stdout)
            return EXIT_OK
        print(f"Pending WeRead availability watches: {len(entries)}", file=stdout)
        for entry in entries:
            details = [f"#{entry.id} {entry.source_title}"]
            if entry.source_douban_id:
                details.append(f"Douban subject {entry.source_douban_id}")
            if entry.weread_title:
                details.append(f"WeRead match {entry.weread_title}")
            if entry.weread_book_id:
                details.append(f"bookId {entry.weread_book_id}")
            print(" — ".join(details), file=stdout)
        return EXIT_OK

    checker = lookup or WeReadEditionLookup()
    entries = watch_store.pending()
    if not entries:
        print("No pending WeRead availability watches.", file=stdout)
        return EXIT_OK

    available = 0
    still_pending = 0
    for entry in entries:
        try:
            result = checker.lookup(entry.source_edition())
        except WEREAD_LOOKUP_ERRORS as exc:
            print(f"#{entry.id} {entry.source_title}: check failed: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR

        if result.kind in {WeReadLookupKind.EXACT, WeReadLookupKind.ALTERNATIVE}:
            selected = result.selected_edition
            if selected is None:
                print(f"#{entry.id} {entry.source_title}: readable result missing Edition metadata", file=stderr)
                return EXIT_PROVIDER_ERROR
            watch_store.mark_available(
                entry.id,
                weread=selected,
                deep_link=result.deep_link,
            )
            available += 1
            relation = "exact Edition" if result.kind is WeReadLookupKind.EXACT else "alternative Edition"
            line = f"#{entry.id} {entry.source_title}: AVAILABLE ({relation}) — {selected.title}"
            if result.deep_link:
                line += f" — {result.deep_link}"
            print(line, file=stdout)
            continue

        still_pending += 1
        if result.kind is WeReadLookupKind.UNAVAILABLE:
            print(f"#{entry.id} {entry.source_title}: still unavailable", file=stdout)
        else:
            print(f"#{entry.id} {entry.source_title}: no confirmed readable Work match yet", file=stdout)

    print(
        f"Watch check complete: {available} newly available, {still_pending} still pending.",
        file=stdout,
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(run())
