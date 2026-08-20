from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections.abc import Callable, Sequence
from typing import TextIO

from douban_weread.providers.douban import DoubanBookSearchClient
from douban_weread.providers.weread import WeReadClient
from douban_weread.reconciliation import (
    ReconciliationWorkerTickResult,
    ReconciliationWorkerView,
    get_reconciliation_worker_status,
    run_reconciliation_worker_tick,
)
from douban_weread.reconciliation.shelf_verify import IncompleteShelfVerificationBaselineError
from douban_weread.storage import (
    ReadingHistoryIndex,
    ReconciliationCheckpointStore,
    ReconciliationEvidenceStore,
    ReconciliationWorkerStateStore,
    WeReadShelfIndex,
)


EXIT_OK = 0
EXIT_PROVIDER_ERROR = 1
EXIT_NO_RESULTS = 3


def _default_weread_client() -> WeReadClient:
    return WeReadClient(api_key=os.getenv("WEREAD_API_KEY", ""))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="douban-weread weread shelf worker",
        description=(
            "Inspect or advance the persistent local first-login reconciliation worker. "
            "Status is local-only; tick performs bounded read-only provider verification and never mutates either platform."
        ),
    )
    subparsers = parser.add_subparsers(dest="worker_command", required=True)
    subparsers.add_parser(
        "status",
        help="Show current worker state and coverage locally; no provider API calls.",
    )
    tick = subparsers.add_parser(
        "tick",
        help="Advance the worker by one bounded read-only reconciliation tick.",
    )
    tick.add_argument("--max-items", type=int, default=4, help="Maximum items this tick; scan hard cap remains 20.")
    tick.add_argument("--batch-size", type=int, default=2, help="Underlying tiny batch size; hard cap remains 5.")
    tick.add_argument("--max-seconds", type=float, default=30.0, help="Time budget checked between batches; hard cap remains 120s.")
    tick.add_argument("--douban-limit", type=int, default=3, help="WeRead→Douban public search window per item.")
    tick.add_argument("--history-limit", type=int, default=5, help="WeRead→Douban local history shortlist per item.")
    tick.add_argument("--catalog-limit", type=int, default=5, help="Douban→WeRead base catalog window per item.")
    return parser


def _print_view(view: ReconciliationWorkerView, *, heading: str, stdout: TextIO) -> None:
    print(heading, file=stdout)
    print(f"State: {view.status.value}", file=stdout)
    print(f"Douban baseline: {view.history_sync_at}", file=stdout)
    print(f"WeRead shelf baseline: {view.shelf_sync_at}", file=stdout)
    print(
        f"Policies: WeRead→Douban v{view.weread_to_douban_policy}; "
        f"Douban→WeRead v{view.douban_to_weread_policy}",
        file=stdout,
    )
    print(
        f"WeRead → Douban: verified {view.coverage.weread_to_douban_verified}; "
        f"pending {view.coverage.weread_to_douban_pending}",
        file=stdout,
    )
    print(
        f"Douban → WeRead: verified {view.coverage.douban_to_weread_verified}; "
        f"pending {view.coverage.douban_to_weread_pending}",
        file=stdout,
    )
    print(f"Total verified: {view.coverage.verified_total}", file=stdout)
    print(f"Total pending: {view.coverage.pending_total}", file=stdout)
    print(f"Worker ticks: {view.tick_count}", file=stdout)
    if view.processed_last_tick:
        print(f"Processed last tick: {view.processed_last_tick}", file=stdout)
    if view.last_stop_reason:
        print(f"Last stop reason: {view.last_stop_reason}", file=stdout)
    if view.last_error_kind:
        print(f"Last error kind: {view.last_error_kind}", file=stdout)


def run(
    argv: Sequence[str] | None = None,
    *,
    weread_client_factory: Callable[[], WeReadClient] = _default_weread_client,
    douban_client_factory: Callable[[], DoubanBookSearchClient] = DoubanBookSearchClient,
    shelf_factory: Callable[[], WeReadShelfIndex] = WeReadShelfIndex,
    history_factory: Callable[[], ReadingHistoryIndex] = ReadingHistoryIndex,
    checkpoint_factory: Callable[[], ReconciliationCheckpointStore] = ReconciliationCheckpointStore,
    evidence_factory: Callable[[], ReconciliationEvidenceStore] = ReconciliationEvidenceStore,
    state_factory: Callable[[], ReconciliationWorkerStateStore] = ReconciliationWorkerStateStore,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    shelf = shelf_factory()
    history = history_factory()
    evidence = evidence_factory()
    state = state_factory()

    if args.worker_command == "status":
        try:
            view = get_reconciliation_worker_status(
                shelf_provider=shelf,
                history_provider=history,
                evidence_provider=evidence,
                state_provider=state,
            )
        except IncompleteShelfVerificationBaselineError as exc:
            print(str(exc), file=stderr)
            return EXIT_NO_RESULTS
        except (ValueError, OSError, sqlite3.Error) as exc:
            print(f"Reconciliation worker status error: {exc}", file=stderr)
            return EXIT_PROVIDER_ERROR

        _print_view(view, heading="Local reconciliation worker status:", stdout=stdout)
        print("Local-only status: no provider API is called and no mutation is performed.", file=stdout)
        return EXIT_OK

    try:
        result = run_reconciliation_worker_tick(
            shelf_provider=shelf,
            history_provider=history,
            checkpoint_provider=checkpoint_factory(),
            evidence_provider=evidence,
            state_provider=state,
            weread_provider=weread_client_factory(),
            douban_provider=douban_client_factory(),
            max_items=args.max_items,
            batch_size=args.batch_size,
            max_seconds=args.max_seconds,
            douban_search_limit=max(1, min(args.douban_limit, 20)),
            history_candidate_limit=max(1, min(args.history_limit, 30)),
            weread_catalog_limit=max(1, min(args.catalog_limit, 10)),
        )
    except IncompleteShelfVerificationBaselineError as exc:
        print(str(exc), file=stderr)
        return EXIT_NO_RESULTS
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Reconciliation worker tick error: {exc}", file=stderr)
        return EXIT_PROVIDER_ERROR

    _print_tick_result(result, stdout=stdout)
    if result.error_kind is not None:
        print(
            f"Worker paused safely after {result.processed_this_tick} persisted item(s); error kind: {result.error_kind}.",
            file=stderr,
        )
        print("Re-run `worker tick` to resume; the failed item was not checkpointed.", file=stderr)
        return EXIT_PROVIDER_ERROR
    return EXIT_OK


def _print_tick_result(result: ReconciliationWorkerTickResult, *, stdout: TextIO) -> None:
    print("Reconciliation worker tick:", file=stdout)
    print(f"Processed this tick: {result.processed_this_tick}", file=stdout)
    if result.scan_result is not None:
        print(f"Scan stop reason: {result.scan_result.stop_reason}", file=stdout)
        print(f"Elapsed: {result.scan_result.elapsed_seconds:.1f}s", file=stdout)
    _print_view(result.view, heading="Current worker state:", stdout=stdout)
    print("No remote mutation is performed by the worker.", file=stdout)


def main() -> None:
    raise SystemExit(run())
