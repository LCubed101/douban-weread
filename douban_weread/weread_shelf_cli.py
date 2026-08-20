from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections.abc import Callable, Sequence
from typing import Protocol, TextIO

from douban_weread.core.models import Edition
from douban_weread.providers.douban import DoubanBookSearchClient, DoubanProviderError
from douban_weread.providers.weread import (
    WeReadClient,
    WeReadProgress,
    WeReadProviderError,
    WeReadShelfSnapshot,
)
from douban_weread.reconciliation.shelf_preview import build_shelf_preview
from douban_weread.reconciliation.shelf_verify import (
    IncompleteShelfVerificationBaselineError,
    verify_shelf_book,
)
from douban_weread.storage import (
    HistoryIndexStatus,
    IndexedHistoryEntry,
    IndexedWeReadShelfBook,
    ReadingHistoryIndex,
    WeReadShelfIndex,
    WeReadShelfIndexStatus,
)


EXIT_OK = 0
EXIT_PROVIDER_ERROR = 1
EXIT_NO_RESULTS = 3


class WeReadShelfClient(Protocol):
    def sync_shelf(self) -> WeReadShelfSnapshot: ...

    def get_book(self, book_id: str) -> Edition | None: ...

    def get_progress(self, book_id: str) -> WeReadProgress | None: ...


class DoubanVerificationClient(Protocol):
    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]: ...

    def get_by_subject_id(self, subject_id: str) -> Edition | None: ...


class ShelfIndex(Protocol):
    def replace_full(self, snapshot: WeReadShelfSnapshot, *, synced_at: str | None = None) -> None: ...

    def status(self) -> WeReadShelfIndexStatus: ...

    def get(self, book_id: str) -> IndexedWeReadShelfBook | None: ...

    def all_books(self) -> list[IndexedWeReadShelfBook]: ...

    def find_title_candidates(
        self,
        title: str,
        *,
        limit: int = 30,
        min_similarity: float = 0.72,
    ) -> list[IndexedWeReadShelfBook]: ...


class HistoryIndex(Protocol):
    def status(self) -> HistoryIndexStatus: ...

    def get(self, subject_id: str) -> IndexedHistoryEntry | None: ...

    def all_entries(self) -> list[IndexedHistoryEntry]: ...

    def find_title_candidates(
        self,
        title: str,
        *,
        limit: int = 30,
        min_similarity: float = 0.72,
    ) -> list[IndexedHistoryEntry]: ...


ShelfClientFactory = Callable[[], WeReadShelfClient]
DoubanVerificationFactory = Callable[[], DoubanVerificationClient]
ShelfIndexFactory = Callable[[], ShelfIndex]
HistoryIndexFactory = Callable[[], HistoryIndex]


def _default_client() -> WeReadClient:
    return WeReadClient(api_key=os.getenv("WEREAD_API_KEY", ""))


def _default_douban_verification_client() -> DoubanBookSearchClient:
    return DoubanBookSearchClient()


def _default_index() -> WeReadShelfIndex:
    return WeReadShelfIndex()


def _default_history_index() -> ReadingHistoryIndex:
    return ReadingHistoryIndex()


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

    preview = subparsers.add_parser(
        "preview",
        help="Compare local Douban active intent and WeRead shelf by exact normalized title.",
        description=(
            "Local-only two-sided reconciliation preview. Douban WISH/READING are current reading intent; "
            "READ remains historical evidence and is not expected to stay on the current WeRead shelf. "
            "Exact normalized title overlap is still only a shortlist signal."
        ),
    )
    preview.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum examples shown for each candidate/conflict section (default: 10).",
    )

    verify = subparsers.add_parser(
        "verify",
        help="Lazily verify one shelf book against bounded Douban Work/Edition and reading-state evidence.",
        description=(
            "Read-only single-book verification. Requires complete local shelf/history baselines, then fetches "
            "full WeRead metadata + progress and a small public Douban candidate set. Resolver-confirmed same-Work "
            "evidence may produce a suggested Douban state, but this command never mutates either platform."
        ),
    )
    verify.add_argument("--id", required=True, dest="book_id", help="Exact WeRead bookId already on the local shelf.")
    verify.add_argument(
        "--douban-limit",
        type=int,
        default=3,
        help="Maximum public Douban title-search candidates fetched for this one verification (default: 3).",
    )
    verify.add_argument(
        "--history-limit",
        type=int,
        default=5,
        help="Maximum local Douban history title candidates lazily resolved if missing from public search (default: 5).",
    )
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
    douban_verification_factory: DoubanVerificationFactory = _default_douban_verification_client,
    index_factory: ShelfIndexFactory = _default_index,
    history_index_factory: HistoryIndexFactory = _default_history_index,
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

    if args.shelf_command == "verify":
        shelf_index = index_factory()
        history_index = history_index_factory()
        weread_client = client_factory()
        douban_client = douban_verification_factory()
        try:
            result = verify_shelf_book(
                args.book_id,
                shelf_provider=shelf_index,
                history_provider=history_index,
                weread_provider=weread_client,
                douban_provider=douban_client,
                douban_search_limit=max(1, min(args.douban_limit, 20)),
                history_candidate_limit=max(1, min(args.history_limit, 30)),
            )
        except IncompleteShelfVerificationBaselineError as exc:
            print(f"Shelf verification unavailable: {exc}", file=stderr)
            return EXIT_NO_RESULTS
        except ValueError as exc:
            print(f"Shelf verification unavailable: {exc}", file=stderr)
            return EXIT_NO_RESULTS
        except (WeReadProviderError, DoubanProviderError, OSError, sqlite3.Error) as exc:
            print(f"Shelf verification provider error: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR

        print("Lazy shelf verification:", file=stdout)
        print("\nWeRead shelf item:", file=stdout)
        print(f"- {result.weread_edition.title}", file=stdout)
        if result.weread_edition.authors:
            print(f"  Authors: {', '.join(result.weread_edition.authors)}", file=stdout)
        if result.weread_edition.isbn:
            print(f"  ISBN: {result.weread_edition.isbn}", file=stdout)
        print(f"  WeRead bookId: {result.shelf_book.book_id}", file=stdout)
        print(f"  Progress: {result.progress.progress}%", file=stdout)
        print(f"  Started: {'yes' if result.progress.is_started else 'no'}", file=stdout)
        print(f"  Verified WeRead state: {result.weread_state.value}", file=stdout)

        print(
            f"\nResolver-confirmed same-Work Douban candidates: {len(result.verified_douban_candidates)}",
            file=stdout,
        )
        if result.best_match is not None:
            best = result.best_match
            print("Best verified Douban candidate:", file=stdout)
            print(f"- {best.edition.title}", file=stdout)
            print(f"  Douban subject: {best.edition.douban_id}", file=stdout)
            if best.edition.isbn:
                print(f"  ISBN: {best.edition.isbn}", file=stdout)
            print(f"  Match: {best.match.kind.value}", file=stdout)
            print(f"  Exact Edition: {best.match.exact_edition}", file=stdout)
            print(f"  Local history state: {best.history_state.value}", file=stdout)
            if best.match.reasons:
                print(f"  Reasons: {'; '.join(best.match.reasons)}", file=stdout)
        else:
            print(
                "No resolver-confirmed same-Work Douban candidate was found within this bounded verification window.",
                file=stdout,
            )

        print(
            f"Strongest verified Douban Work state in local baseline: {result.strongest_douban_state.value}",
            file=stdout,
        )
        print("\nRecommendation:", file=stdout)
        print(f"Action: {result.decision.action.value}", file=stdout)
        print(f"Suggested Douban state: {result.decision.suggested_douban_state.value}", file=stdout)
        print(f"Safe to auto apply: {result.decision.safe_to_auto_apply}", file=stdout)
        print(f"Requires user decision: {result.decision.requires_user_decision}", file=stdout)
        print(f"Reason: {result.decision.reason}", file=stdout)
        print(
            "\nBounded evidence: "
            f"public Douban search <= {result.douban_search_limit} candidates; "
            f"local history shortlist <= {result.history_candidate_limit}. "
            "This is not an exhaustive proof that no other Douban Edition exists.",
            file=stdout,
        )
        print("No mutation is performed by this command.", file=stdout)
        return EXIT_OK

    if args.shelf_command == "preview":
        shelf_index = index_factory()
        history_index = history_index_factory()
        try:
            shelf_status = shelf_index.status()
            history_status = history_index.status()
            if not shelf_status.complete or not history_status.complete:
                print(
                    "Both complete baselines are required. Sync Douban history and WeRead shelf first.",
                    file=stderr,
                )
                return EXIT_NO_RESULTS
            report = build_shelf_preview(
                history_index.all_entries(),
                shelf_index.all_books(),
            )
        except (OSError, sqlite3.Error, ValueError) as exc:
            print(f"Local reconciliation preview error: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR

        example_limit = max(1, min(args.limit, 100))
        active_total = report.douban_wish + report.douban_reading
        print("Local two-sided reconciliation preview:", file=stdout)
        print(f"Douban history entries: {report.douban_total}", file=stdout)
        print(f"  Active intents (wish + reading): {active_total}", file=stdout)
        print(f"    Want-to-Read: {report.douban_wish}", file=stdout)
        print(f"    Reading: {report.douban_reading}", file=stdout)
        print(f"  Read history (not expected on current shelf): {report.douban_read}", file=stdout)
        print(f"WeRead electronic shelf books: {report.weread_total}", file=stdout)
        print(f"  Shelf books marked finished: {report.weread_finished}", file=stdout)
        print(
            f"  Shelf books with nonzero readUpdateTime: {report.weread_with_read_activity}",
            file=stdout,
        )
        print("    (not treated as started-reading evidence; use /book/getprogress)", file=stdout)
        print(f"Shared exact normalized title keys (all Douban states): {report.shared_title_keys}", file=stdout)
        print(f"Shared title keys involving active Douban intent: {report.active_shared_title_keys}", file=stdout)
        print(
            f"Active Douban entries with exact-title shelf candidate: {report.active_douban_entries_with_exact_title}",
            file=stdout,
        )
        print(
            f"Active Douban-only by exact title: {len(report.active_douban_only_entries)}",
            file=stdout,
        )
        print(
            f"WeRead-only vs any Douban state by exact title: {len(report.weread_only_books)}",
            file=stdout,
        )
        print(
            f"WeRead shelf books overlapping Douban READ history by exact title: {len(report.read_history_overlap_books)}",
            file=stdout,
        )
        print(f"Ambiguous shared title keys: {report.ambiguous_shared_title_keys}", file=stdout)
        print(f"Possible finished/state conflicts: {len(report.possible_state_conflicts)}", file=stdout)

        if report.weread_only_books:
            print("\nWeRead shelf with no exact-title Douban history candidate:", file=stdout)
            for book in report.weread_only_books[:example_limit]:
                print(f"- {format_lookup_candidate(book)}", file=stdout)

        if report.active_douban_only_entries:
            print("\nActive Douban intent with no exact-title shelf candidate:", file=stdout)
            for entry in report.active_douban_only_entries[:example_limit]:
                print(
                    f"- subject {entry.subject_id} | {entry.title} | state: {entry.state}",
                    file=stdout,
                )

        if report.possible_state_conflicts:
            print("\nPossible state-conflict examples (singleton exact-title only):", file=stdout)
            for conflict in report.possible_state_conflicts[:example_limit]:
                print(
                    f"- {conflict.title} | Douban {conflict.douban_state} ({conflict.douban_subject_id}) "
                    f"| WeRead finished=yes ({conflict.weread_book_id})",
                    file=stdout,
                )

        print(
            "\nPreview only: exact title overlap is not Work/Edition verification. "
            "READ history missing from the current shelf is not treated as a sync gap. "
            "No mutation is authorized by this report.",
            file=stdout,
        )
        return EXIT_OK

    parser.error(f"unsupported WeRead shelf command: {args.shelf_command}")
    return 2


def main() -> None:
    raise SystemExit(run())
