from __future__ import annotations

import asyncio
import contextlib
import os
import sys

from douban_weread.feishu_bot import ChannelLike
from douban_weread.feishu_bot_v11 import build_bot
from douban_weread.feishu_watch_loop import DEFAULT_WATCH_INTERVAL_SECONDS, run_watch_loop
from douban_weread.safe_logging import install_log_redaction
from douban_weread.weread_watch_worker import WeReadWatchWorker


def watch_interval_seconds() -> float:
    raw = os.getenv("DOUBAN_WEREAD_WATCH_INTERVAL_SECONDS", "").strip()
    if not raw:
        return float(DEFAULT_WATCH_INTERVAL_SECONDS)
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError("DOUBAN_WEREAD_WATCH_INTERVAL_SECONDS must be a number") from exc
    if value < 1:
        raise RuntimeError("DOUBAN_WEREAD_WATCH_INTERVAL_SECONDS must be >= 1")
    return value


async def run_runtime(
    channel: ChannelLike,
    worker: WeReadWatchWorker,
    *,
    interval_seconds: float,
) -> None:
    watch_task = asyncio.create_task(
        run_watch_loop(channel, worker, interval_seconds=interval_seconds),
        name="weread-watch-loop",
    )
    try:
        await channel.connect()
    finally:
        watch_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watch_task


def main() -> None:
    install_log_redaction()
    try:
        channel = build_bot()
        interval = watch_interval_seconds()
        worker = WeReadWatchWorker()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc

    print("Douban × WeRead Feishu Reading Inbox starting via WebSocket...")
    print(
        "Image/OCR enabled. Multi-book inputs with explicit 《...》 titles are routed to read-only WeRead lookup; "
        "single-book inputs keep the existing Douban confirmation flow."
    )
    print(f"WeRead availability watch enabled: checking every {interval:g} seconds (default: 604800 / 7d).")
    try:
        asyncio.run(run_runtime(channel, worker, interval_seconds=interval))
    except KeyboardInterrupt:
        print("\nFeishu bot stopped.")


if __name__ == "__main__":
    main()
