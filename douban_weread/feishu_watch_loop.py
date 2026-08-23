from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

from douban_weread.weread_watch_worker import WeReadWatchNotification, WeReadWatchWorker


DEFAULT_WATCH_INTERVAL_SECONDS = 24 * 60 * 60


class NotificationChannel(Protocol):
    async def send(self, to: str, message: object, opts: object | None = None): ...


Sleep = Callable[[float], Awaitable[None]]


async def run_watch_loop(
    channel: NotificationChannel,
    worker: WeReadWatchWorker,
    *,
    interval_seconds: float = DEFAULT_WATCH_INTERVAL_SECONDS,
    sleep: Sleep = asyncio.sleep,
) -> None:
    """Periodically run the read-only watch worker and deliver durable notices.

    The first check happens after one interval so bot startup stays lightweight.
    A notification is acknowledged only after Feishu send succeeds. If checking
    or delivery fails, the loop survives and the durable state is retried on a
    later interval.
    """
    interval = max(1.0, float(interval_seconds))
    while True:
        await sleep(interval)
        try:
            notices = await asyncio.to_thread(worker.run_once)
        except Exception as exc:  # provider/storage failure must not stop the bot
            print(f"WeRead watch check failed: {type(exc).__name__}")
            continue

        for notice in notices:
            try:
                await channel.send(notice.chat_id, {"text": notice.text})
            except Exception as exc:  # keep unacknowledged for the next retry
                print(f"WeRead watch notification failed: {type(exc).__name__}")
                continue
            try:
                await asyncio.to_thread(worker.acknowledge, notice)
            except Exception as exc:
                # Sending succeeded, but failure to persist the ack intentionally
                # favors a possible duplicate over silently losing notification state.
                print(f"WeRead watch acknowledge failed: {type(exc).__name__}")


def notification_payload(notification: WeReadWatchNotification) -> dict[str, str]:
    return {"text": notification.text}
