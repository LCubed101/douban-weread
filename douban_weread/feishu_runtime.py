from __future__ import annotations

import asyncio
import contextlib
import os
import sys

from douban_weread.feishu_bot import ChannelLike
from douban_weread.feishu_bot_v11 import build_bot
from douban_weread.feishu_bot_weread_only import build_weread_only_bot
from douban_weread.feishu_capture_buffer import buffered_channel_factory
from douban_weread.feishu_compact_douban import prepare_compact_douban_flow
from douban_weread.feishu_hybrid_batch import prepare_hybrid_batch_douban
from douban_weread.feishu_multi_image import prepare_multi_image_support
from douban_weread.feishu_result_polish import prepare_result_polish
from douban_weread.feishu_watch_loop import DEFAULT_WATCH_INTERVAL_SECONDS, run_watch_loop
from douban_weread.safe_logging import install_log_redaction
from douban_weread.weread_watch_worker import WeReadWatchWorker


def router_mode() -> str:
    value = os.getenv("ROUTER_MODE", "douban_weread").strip().casefold() or "douban_weread"
    aliases = {
        "default": "douban_weread",
        "douban": "douban_weread",
        "douban_weread": "douban_weread",
        "weread": "weread_only",
        "weread_only": "weread_only",
    }
    resolved = aliases.get(value)
    if resolved is None:
        raise RuntimeError("ROUTER_MODE must be 'douban_weread' or 'weread_only'")
    return resolved


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


def image_burst_quiet_seconds() -> float:
    raw = os.getenv("DOUBAN_WEREAD_IMAGE_BURST_SECONDS", "0.9").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError("DOUBAN_WEREAD_IMAGE_BURST_SECONDS must be a number") from exc
    if value < 0.2 or value > 5:
        raise RuntimeError("DOUBAN_WEREAD_IMAGE_BURST_SECONDS must be between 0.2 and 5 seconds")
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
        prepare_multi_image_support()
        mode = router_mode()
        if mode == "douban_weread":
            prepare_compact_douban_flow()
            prepare_hybrid_batch_douban()
            prepare_result_polish()
        quiet_seconds = image_burst_quiet_seconds()
        channel_factory = buffered_channel_factory(quiet_seconds=quiet_seconds)
        channel = (
            build_weread_only_bot(channel_factory=channel_factory)
            if mode == "weread_only"
            else build_bot(channel_factory=channel_factory)
        )
        interval = watch_interval_seconds()
        worker = WeReadWatchWorker()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc

    print("Douban × WeRead Feishu Reading Inbox starting via WebSocket...")
    print(f"Router mode: {mode}")
    print(
        f"Image burst capture enabled: consecutive image events are merged after {quiet_seconds:g}s of quiet time."
    )
    if mode == "weread_only":
        print(
            "WeRead-only mode enabled. Text titles and screenshots are routed directly to read-only WeRead lookup; "
            "Douban credentials are not required."
        )
    else:
        print(
            "Hybrid mode enabled. Multi-book captures query WeRead and conservatively sync Douban Want-to-Read when "
            "one Douban edition can be resolved safely; ambiguous editions stay pending instead of being guessed."
        )
    print(f"WeRead availability watch enabled: checking every {interval:g} seconds (default: 604800 / 7d).")
    try:
        asyncio.run(run_runtime(channel, worker, interval_seconds=interval))
    except KeyboardInterrupt:
        print("\nFeishu bot stopped.")


if __name__ == "__main__":
    main()
