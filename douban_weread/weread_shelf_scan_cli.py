from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections.abc import Callable, Sequence
from typing import TextIO

from douban_weread.providers.douban import DoubanBookSearchClient, DoubanProviderError
from douban_weread.providers.weread import WeReadClient, WeReadProviderError
from douban_weread.reconciliation import (
    DOUBAN_TO_WEREAD,
    WEREAD_TO_DOUBAN,
    EvidenceScanGenerationChangedError,
    EvidenceScanStep,
    run_reconciliation_evidence_scan,
)
from douban_weread.reconciliation.evidence_report import build_reconciliation_evidence_report
from douban_weread.reconciliation.shelf_verify import IncompleteShelfVerificationBaselineError
from douban_weread.storage import (
    ReadingHistoryIndex,
    ReconciliationCheckpointStore,
    ReconciliationEvidenceStore,
    WeReadShelfIndex,
)


EXIT_OK = 0
EXIT_PROVIDER_ERROR = 1
EXIT_NO_RESULTS = 3

_DIRECTION_LABELS = {
    DOUBAN_TO_WEREAD: "Douban → WeRead",
    WEREAD_TO_DOUBAN: "WeRead → Douban",
}


def _default_weread_client() -> WeReadClient:
    return WeReadClient(api_key=os.getenv("WEREAD_API_KEY", ""))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="douban-weread weread shelf scan",
        description=(
            "Fill a bounded amount of normalized reconciliation evidence with checkpointed read-only verification. "
            "The scan never mutates Douban or WeRead and stops immediately on provider/parser failures."
        ),
    )
    parser.add_argument(
        "--direction",
        choices=("both", DOUBAN_TO_WEREAD, WEREAD_TO_DOUBAN),
        default="both",
        help="Which pending direction(s) to scan (default: both).",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=4,
        help="Maximum verified items this invocation; hard-capped at 20 (default: 4).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=2,
        help="Items per tiny underlying batch; hard-capped at 5 (default: 2).",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=30.0,
        help=(
            "Wall-clock budget checked between tiny batches; hard-capped at 120 seconds "
            "and never interrupts an in-flight request (default: 30)."
        ),
    )
    parser.add_argument(
        "--douban-limit",
        type=int,
        default=3,
        help="WeRead→Douban public Douban title-search window per item (default: 3).",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=5,
        help="WeRead→Douban local history shortlist per item (default: 5).",
    )
    parser.add_argument(
        "--catalog-limit",
        type=int,
        default=5,
        help="Douban→WeRead base catalog window; active Reading still uses up to 10 (default: 5).",
    )
    return parser


def _print_coverage(report, *, heading: str, stdout: TextIO) -> None:
    print(f"\n{heading}", file=stdout)
    for direction in (WEREAD_TO_DOUBAN, DOUBAN_TO_WEREAD):
        item = report.for_direction(direction)
        print(
            f"- {_DIRECTION_LABELS[direction]}: verified {item.verified_total}/{item.candidate_total}; "
            f"pending {item.pending_total}; user action {item.requires_user_action_total}",
            file=stdout,
        )


def run(
    argv: Sequence[str] | None = None,
    *,
    weread_client_factory: Callable[[], WeReadClient] = _default_weread_client,
    douban_client_factory: Callable[[], DoubanBookSearchClient] = DoubanBookSearchClient,
    shelf_factory: Callable[[], WeReadShelfIndex] = WeReadShelfIndex,
    history_factory: Callable[[], ReadingHistoryIndex] = ReadingHistoryIndex,
    checkpoint_factory: Callable[[], ReconciliationCheckpointStore] = ReconciliationCheckpointStore,
    evidence_factory: Callable[[], ReconciliationEvidenceStore] = ReconciliationEvidenceStore,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)

    shelf = shelf_factory()
    history = history_factory()
    checkpoint = checkpoint_factory()
    evidence = evidence_factory()

    try:
        initial_report = build_reconciliation_evidence_report(
            shelf_provider=shelf,
            history_provider=history,
            evidence_provider=evidence,
        )
    except IncompleteShelfVerificationBaselineError as exc:
        print(str(exc), file=stderr)
        return EXIT_NO_RESULTS
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Reconciliation scan error: {exc}", file=stderr)
        return EXIT_PROVIDER_ERROR

    print("Read-only reconciliation evidence scan:", file=stdout)
    print(f"Direction: {args.direction}", file=stdout)
    print(f"Requested max items: {args.max_items} (hard cap: 20)", file=stdout)
    print(f"Requested batch size: {args.batch_size} (hard cap: 5)", file=stdout)
    print(f"Requested time budget: {args.max_seconds:g}s (hard cap: 120s)", file=stdout)
    print("Successful items persist normalized evidence before checkpointing.", file=stdout)
    _print_coverage(initial_report, heading="Initial local coverage:", stdout=stdout)

    weread = weread_client_factory()
    douban = douban_client_factory()
    completed_steps: list[EvidenceScanStep] = []

    def on_step(step: EvidenceScanStep) -> None:
        completed_steps.append(step)
        print(
            f"Batch {step.batch_number}: {_DIRECTION_LABELS[step.direction]} | "
            f"processed {step.processed} | cumulative {step.cumulative_processed} | "
            f"remaining {step.remaining_after} | policy v{step.policy_version}",
            file=stdout,
        )

    try:
        result = run_reconciliation_evidence_scan(
            directions=args.direction,
            max_items=args.max_items,
            batch_size=args.batch_size,
            max_seconds=args.max_seconds,
            shelf_provider=shelf,
            history_provider=history,
            checkpoint_provider=checkpoint,
            evidence_provider=evidence,
            weread_provider=weread,
            douban_provider=douban,
            douban_search_limit=max(1, min(args.douban_limit, 20)),
            history_candidate_limit=max(1, min(args.history_limit, 30)),
            weread_catalog_limit=max(1, min(args.catalog_limit, 10)),
            on_step=on_step,
        )
        report = build_reconciliation_evidence_report(
            shelf_provider=shelf,
            history_provider=history,
            evidence_provider=evidence,
        )
    except IncompleteShelfVerificationBaselineError as exc:
        print(str(exc), file=stderr)
        return EXIT_NO_RESULTS
    except DoubanProviderError as exc:
        print(f"Douban provider error: {exc}", file=stderr)
        return _report_partial_stop(
            completed_steps,
            shelf=shelf,
            history=history,
            evidence=evidence,
            stdout=stdout,
        )
    except WeReadProviderError as exc:
        print(f"WeRead provider error: {exc}", file=stderr)
        return _report_partial_stop(
            completed_steps,
            shelf=shelf,
            history=history,
            evidence=evidence,
            stdout=stdout,
        )
    except EvidenceScanGenerationChangedError as exc:
        print(f"Reconciliation scan stopped: {exc}", file=stderr)
        return _report_partial_stop(
            completed_steps,
            shelf=shelf,
            history=history,
            evidence=evidence,
            stdout=stdout,
        )
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Reconciliation scan error: {exc}", file=stderr)
        return _report_partial_stop(
            completed_steps,
            shelf=shelf,
            history=history,
            evidence=evidence,
            stdout=stdout,
        )

    print("\nScan summary:", file=stdout)
    print(f"Processed this scan: {result.processed_total}", file=stdout)
    print(f"Stop reason: {result.stop_reason}", file=stdout)
    print(f"Elapsed: {result.elapsed_seconds:.1f}s", file=stdout)
    if result.requested_max_items != result.effective_max_items:
        print(f"Effective max items: {result.effective_max_items}", file=stdout)
    if result.requested_batch_size != result.effective_batch_size:
        print(f"Effective batch size: {result.effective_batch_size}", file=stdout)
    if result.requested_max_seconds != result.effective_max_seconds:
        print(f"Effective time budget: {result.effective_max_seconds:g}s", file=stdout)

    _print_coverage(report, heading="Current local coverage:", stdout=stdout)

    print(
        "\nNo remote mutation is performed. Re-run the scan to resume from persisted evidence/checkpoints, "
        "or use `douban-weread weread shelf report` for a local-only detailed summary.",
        file=stdout,
    )
    return EXIT_OK


def _report_partial_stop(
    completed_steps: list[EvidenceScanStep],
    *,
    shelf: WeReadShelfIndex,
    history: ReadingHistoryIndex,
    evidence: ReconciliationEvidenceStore,
    stdout: TextIO,
) -> int:
    persisted = sum(step.processed for step in completed_steps)
    print(
        f"\nScan stopped after {persisted} item(s) were successfully persisted in this invocation.",
        file=stdout,
    )
    try:
        report = build_reconciliation_evidence_report(
            shelf_provider=shelf,
            history_provider=history,
            evidence_provider=evidence,
        )
    except (IncompleteShelfVerificationBaselineError, ValueError, OSError, sqlite3.Error):
        print(
            "Persisted checkpoints/evidence remain resumable, but current coverage could not be reloaded.",
            file=stdout,
        )
    else:
        _print_coverage(report, heading="Persisted local coverage after stop:", stdout=stdout)
    print("Re-run the same scan command to resume; failed items are not checkpointed.", file=stdout)
    return EXIT_PROVIDER_ERROR


def main() -> None:
    raise SystemExit(run())
