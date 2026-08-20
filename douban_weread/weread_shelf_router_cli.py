from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import TextIO


_HELP = """usage: douban-weread weread shelf [-h] {sync,status,lookup,preview,queue,verify,batch,report,scan} ...

Build, inspect, and gradually reconcile the local read-only WeRead shelf baseline.

positional arguments:
  {sync,status,lookup,preview,queue,verify,batch,report,scan}
    sync                 Fetch the official WeRead shelf and atomically replace the local baseline.
    status               Show the local WeRead shelf baseline without network access.
    lookup               Search the local WeRead electronic-book shelf by title without network access.
    preview              Compare local Douban active intent and WeRead shelf by exact normalized title.
    queue                List local candidates for later bounded verification without network requests.
    verify               Lazily verify one shelf book against bounded Douban Work/Edition and reading-state evidence.
    batch                Process up to five pending items with baseline-scoped checkpoints; read-only.
    report               Summarize current persisted reconciliation evidence locally; no network access.
    scan                 Fill a bounded amount of persisted reconciliation evidence with visible progress; read-only.

options:
  -h, --help             show this help message and exit
"""


def run(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args or args[0] in {"-h", "--help"}:
        print(_HELP.rstrip(), file=stdout)
        return 0

    if args[0] == "batch":
        from douban_weread.weread_shelf_batch_cli import run as run_batch

        return run_batch(args[1:])

    if args[0] == "report":
        from douban_weread.weread_shelf_report_cli import run as run_report

        return run_report(args[1:])

    if args[0] == "scan":
        from douban_weread.weread_shelf_scan_cli import run as run_scan

        return run_scan(args[1:])

    from douban_weread.weread_shelf_cli import run as run_shelf

    return run_shelf(args)


def main() -> None:
    raise SystemExit(run())
