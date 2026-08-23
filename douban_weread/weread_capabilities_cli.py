from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from typing import TextIO

from douban_weread.providers.weread import WeReadClient, WeReadProviderError
from douban_weread.weread_capabilities import WeReadCapabilityDiscovery


def run(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    args = list(argv or [])
    if args:
        print("Usage: douban-weread weread capabilities", file=stderr)
        return 2

    client = WeReadClient(api_key=os.getenv("WEREAD_API_KEY", ""))
    try:
        capabilities = WeReadCapabilityDiscovery(client).list_capabilities()
    except (WeReadProviderError, ValueError) as exc:
        print(f"WeRead capability discovery error: {exc}", file=stderr)
        return 1

    if not capabilities:
        print("WeRead /_list returned no recognizable API names.", file=stdout)
        return 3

    print("WeRead APIs available to this account:", file=stdout)
    for capability in capabilities:
        suffix = f" — {capability.description}" if capability.description else ""
        print(f"- {capability.api_name}{suffix}", file=stdout)

    names = {item.api_name.casefold() for item in capabilities}
    write_hints = sorted(
        name for name in names
        if any(token in name for token in ("subscribe", "notify", "shelf/add", "bookshelf/add", "addbook"))
    )
    print("", file=stdout)
    if write_hints:
        print("Potential subscription/shelf-write APIs detected:", file=stdout)
        for name in write_hints:
            print(f"- {name}", file=stdout)
        print("Do not call these until their official parameter documentation is reviewed.", file=stdout)
    else:
        print("No obvious subscription or shelf-write API name was detected.", file=stdout)
    return 0


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))
