from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Callable, Sequence
from typing import TextIO

from douban_weread.reconciliation.evidence_report import (
    DirectionEvidenceReport,
    build_reconciliation_evidence_report,
)
from douban_weread.reconciliation.shelf_batch import DOUBAN_TO_WEREAD, WEREAD_TO_DOUBAN
from douban_weread.reconciliation.shelf_verify import IncompleteShelfVerificationBaselineError
from douban_weread.storage import ReadingHistoryIndex, ReconciliationEvidenceStore, WeReadShelfIndex


EXIT_OK = 0
EXIT_PROVIDER_ERROR = 1
EXIT_NO_RESULTS = 3


_DIRECTION_LABELS = {
    WEREAD_TO_DOUBAN: "WeRead → Douban",
    DOUBAN_TO_WEREAD: "Douban → WeRead",
}


ShelfFactory = Callable[[], WeReadShelfIndex]
HistoryFactory = Callable[[], ReadingHistoryIndex]
EvidenceFactory = Callable[[], ReconciliationEvidenceStore]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="douban-weread weread shelf report",
        description=(
            "Summarize locally persisted reconciliation evidence for the current complete baselines. "
            "This command makes no network requests and never mutates either platform."
        ),
    )
    parser.add_argument(
        "--direction",
        choices=("both", WEREAD_TO_DOUBAN, DOUBAN_TO_WEREAD),
        default="both",
        help="Which evidence direction to show (default: both).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum verified evidence examples shown per direction (default: 5).",
    )
    return parser


def _format_identity(row) -> str:
    details = [row.title, f"plan: {row.user_plan}"]
    if row.direction == DOUBAN_TO_WEREAD:
        details.append(f"Douban subject: {row.item_id}")
        if row.selected_weread_book_id:
            details.append(f"WeRead bookId: {row.selected_weread_book_id}")
        if row.shelf_membership:
            details.append(f"shelf: {row.shelf_membership}")
    else:
        details.append(f"WeRead bookId: {row.item_id}")
        if row.selected_douban_subject:
            details.append(f"Douban subject: {row.selected_douban_subject}")
        if row.weread_reading_state:
            details.append(f"WeRead state: {row.weread_reading_state}")
    return " | ".join(details)


def _print_direction(
    report: DirectionEvidenceReport,
    *,
    item_limit: int,
    stdout: TextIO,
) -> None:
    print(f"\n{_DIRECTION_LABELS[report.direction]}:", file=stdout)
    print(f"  Reconciliation policy: v{report.policy_version}", file=stdout)
    print(f"  Candidate queue: {report.candidate_total}", file=stdout)
    print(f"  Verified evidence: {report.verified_total}", file=stdout)
    print(f"  Pending verification: {report.pending_total}", file=stdout)
    print(f"  Verified items requiring user action: {report.requires_user_action_total}", file=stdout)

    if report.plan_counts:
        print("  Verified user plans:", file=stdout)
        for item in report.plan_counts:
            print(f"    {item.user_plan}: {item.count}", file=stdout)
    else:
        print("  Verified user plans: none yet", file=stdout)

    if report.orphaned_evidence_total:
        print(
            f"  Warning: {report.orphaned_evidence_total} evidence row(s) are outside the current candidate queue.",
            file=stdout,
        )

    if report.evidence:
        print("  Verified examples:", file=stdout)
        for row in report.evidence[:item_limit]:
            print(f"    - {_format_identity(row)}", file=stdout)


def run(
    argv: Sequence[str] | None = None,
    *,
    shelf_factory: ShelfFactory = WeReadShelfIndex,
    history_factory: HistoryFactory = ReadingHistoryIndex,
    evidence_factory: EvidenceFactory = ReconciliationEvidenceStore,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)

    try:
        report = build_reconciliation_evidence_report(
            shelf_provider=shelf_factory(),
            history_provider=history_factory(),
            evidence_provider=evidence_factory(),
        )
    except IncompleteShelfVerificationBaselineError as exc:
        print(str(exc), file=stderr)
        return EXIT_NO_RESULTS
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Local reconciliation report error: {exc}", file=stderr)
        return EXIT_PROVIDER_ERROR

    print("Local reconciliation evidence report:", file=stdout)
    print(f"Douban baseline: {report.history_sync_at}", file=stdout)
    print(f"WeRead shelf baseline: {report.shelf_sync_at}", file=stdout)
    print(
        "Coverage: only persisted verified evidence is classified; pending candidates remain unclassified.",
        file=stdout,
    )

    directions = (
        (WEREAD_TO_DOUBAN, DOUBAN_TO_WEREAD)
        if args.direction == "both"
        else (args.direction,)
    )
    item_limit = max(1, min(args.limit, 100))
    for direction in directions:
        _print_direction(
            report.for_direction(direction),
            item_limit=item_limit,
            stdout=stdout,
        )

    print(
        "\nLocal-only report: no provider API is called and no mutation is performed.",
        file=stdout,
    )
    return EXIT_OK


def main() -> None:
    raise SystemExit(run())
