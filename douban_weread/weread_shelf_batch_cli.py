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
    run_reconciliation_batch,
)
from douban_weread.reconciliation.shelf_verify import IncompleteShelfVerificationBaselineError
from douban_weread.storage import (
    ReadingHistoryIndex,
    ReconciliationCheckpointStore,
    WeReadShelfIndex,
)


EXIT_OK = 0
EXIT_PROVIDER_ERROR = 1
EXIT_NO_RESULTS = 3


def _default_weread_client() -> WeReadClient:
    return WeReadClient(api_key=os.getenv("WEREAD_API_KEY", ""))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="douban-weread weread shelf batch",
        description=(
            "Process a tiny read-only reconciliation batch with local baseline-scoped checkpoints. "
            "One invocation handles at most five items and never mutates either platform."
        ),
    )
    parser.add_argument(
        "--direction",
        required=True,
        choices=(WEREAD_TO_DOUBAN, DOUBAN_TO_WEREAD),
        help="Which side supplies the pending reconciliation queue.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Requested items for this batch; hard-capped at 5 (default: 3).",
    )
    parser.add_argument(
        "--douban-limit",
        type=int,
        default=3,
        help="WeRead→Douban: maximum public Douban search candidates per item (default: 3).",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=5,
        help="WeRead→Douban: maximum local history candidates lazily resolved per item (default: 5).",
    )
    parser.add_argument(
        "--catalog-limit",
        type=int,
        default=5,
        help="Douban→WeRead: maximum official WeRead catalog candidates per item (default: 5).",
    )
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    weread_client_factory: Callable[[], WeReadClient] = _default_weread_client,
    douban_client_factory: Callable[[], DoubanBookSearchClient] = DoubanBookSearchClient,
    shelf_index_factory: Callable[[], WeReadShelfIndex] = WeReadShelfIndex,
    history_index_factory: Callable[[], ReadingHistoryIndex] = ReadingHistoryIndex,
    checkpoint_factory: Callable[[], ReconciliationCheckpointStore] = ReconciliationCheckpointStore,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)

    try:
        result = run_reconciliation_batch(
            args.direction,
            limit=args.limit,
            shelf_provider=shelf_index_factory(),
            history_provider=history_index_factory(),
            checkpoint_provider=checkpoint_factory(),
            weread_provider=weread_client_factory(),
            douban_provider=douban_client_factory(),
            douban_search_limit=max(1, min(args.douban_limit, 20)),
            history_candidate_limit=max(1, min(args.history_limit, 30)),
            weread_catalog_limit=max(1, min(args.catalog_limit, 10)),
        )
    except IncompleteShelfVerificationBaselineError as exc:
        print(str(exc), file=stderr)
        return EXIT_NO_RESULTS
    except DoubanProviderError as exc:
        print(f"Douban provider error: {exc}", file=stderr)
        return EXIT_PROVIDER_ERROR
    except WeReadProviderError as exc:
        print(f"WeRead provider error: {exc}", file=stderr)
        return EXIT_PROVIDER_ERROR
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Reconciliation batch error: {exc}", file=stderr)
        return EXIT_PROVIDER_ERROR

    print("Read-only reconciliation batch:", file=stdout)
    print(f"Direction: {result.direction}", file=stdout)
    print(f"Douban baseline: {result.generation.history_sync_at}", file=stdout)
    print(f"WeRead shelf baseline: {result.generation.shelf_sync_at}", file=stdout)
    print(f"Candidate queue: {result.candidate_total}", file=stdout)
    print(f"Already checkpointed in this generation: {result.already_completed}", file=stdout)
    print(f"Pending before batch: {result.pending_before}", file=stdout)
    if result.requested_limit != result.effective_limit:
        print(
            f"Requested batch size: {result.requested_limit}; effective batch size: {result.effective_limit} (hard cap: 5)",
            file=stdout,
        )
    else:
        print(f"Batch size: {result.effective_limit}", file=stdout)

    if not result.processed:
        print("\nNo pending items were processed for this baseline generation.", file=stdout)
    elif result.direction == WEREAD_TO_DOUBAN:
        for index, item in enumerate(result.processed, start=1):
            verification = item.shelf_verification
            assert verification is not None
            print(f"\n{index}. {item.title}", file=stdout)
            print(f"   WeRead bookId: {item.item_id}", file=stdout)
            print(f"   WeRead state: {verification.weread_state.value}", file=stdout)
            print(f"   Progress: {verification.progress.progress}%", file=stdout)
            if verification.best_match is not None:
                best = verification.best_match
                print(f"   Douban subject: {best.edition.douban_id}", file=stdout)
                print(f"   Match: {best.match.kind.value}", file=stdout)
                print(f"   Exact Edition: {best.match.exact_edition}", file=stdout)
                print(f"   Existing Douban Work state: {verification.strongest_douban_state.value}", file=stdout)
            else:
                print("   Douban Work identity: not verified in bounded evidence", file=stdout)
            print(f"   Outcome: {item.outcome}", file=stdout)
            print(
                f"   Suggested Douban state: {verification.decision.suggested_douban_state.value}",
                file=stdout,
            )
            print(f"   Requires user decision: {verification.decision.requires_user_decision}", file=stdout)
            print("   Checkpointed for this baseline: yes", file=stdout)
    else:
        for index, item in enumerate(result.processed, start=1):
            alignment = item.catalog_alignment
            assert alignment is not None
            intent = alignment.intent
            print(f"\n{index}. {item.title}", file=stdout)
            print(f"   Douban subject: {item.item_id}", file=stdout)
            if item.source_state:
                print(f"   Douban state: {item.source_state}", file=stdout)
            print(f"   WeRead catalog status: {intent.weread_status.value}", file=stdout)
            print(f"   Resolution: {intent.resolution.value}", file=stdout)
            if intent.selected_edition is not None:
                print(f"   Selected WeRead bookId: {intent.selected_edition.weread_id}", file=stdout)
                if intent.selected_edition.title:
                    print(f"   Selected Edition: {intent.selected_edition.title}", file=stdout)
            if intent.source_url:
                print(f"   Deep link: {intent.source_url}", file=stdout)
            print(f"   Outcome: {item.outcome}", file=stdout)
            print("   Checkpointed for this baseline: yes", file=stdout)

    print(f"\nProcessed this batch: {len(result.processed)}", file=stdout)
    print(f"Remaining pending for this generation: {result.remaining_after}", file=stdout)
    print(
        "No mutation is performed. Checkpoints only prevent repeated verification against the same pair of local baselines.",
        file=stdout,
    )
    return EXIT_OK


def main() -> None:
    raise SystemExit(run())
