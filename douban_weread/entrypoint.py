from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "weread":
        from douban_weread.weread_cli import run as run_weread

        raise SystemExit(run_weread(sys.argv[2:]))

    from douban_weread.cli import main as run_douban

    run_douban()
