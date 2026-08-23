from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from douban_weread.feishu_watch_loop import run_watch_loop


class StopLoop(Exception):
    pass


class FakeChannel:
    def __init__(self, *, fail_send: bool = False) -> None:
        self.fail_send = fail_send
        self.sent: list[tuple[str, object, object | None]] = []

    async def send(self, to: str, message: object, opts: object | None = None):
        if self.fail_send:
            raise RuntimeError("send failed")
        self.sent.append((to, message, opts))
        return object()


class FakeWorker:
    def __init__(self) -> None:
        self.run_calls = 0
        self.acks: list[object] = []
        self.notice = SimpleNamespace(entry_id=1, chat_id="oc_chat", text="上架了")

    def run_once(self):
        self.run_calls += 1
        return [self.notice]

    def acknowledge(self, notice) -> None:
        self.acks.append(notice)


async def one_tick_sleep(_seconds: float) -> None:
    if one_tick_sleep.calls:
        raise StopLoop
    one_tick_sleep.calls += 1


one_tick_sleep.calls = 0


class FeishuWatchLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        one_tick_sleep.calls = 0

    def test_successful_send_is_acknowledged(self) -> None:
        channel = FakeChannel()
        worker = FakeWorker()

        with patch("douban_weread.feishu_watch_loop.asyncio.to_thread", side_effect=_inline_to_thread):
            with self.assertRaises(StopLoop):
                asyncio.run(run_watch_loop(channel, worker, interval_seconds=1, sleep=one_tick_sleep))

        self.assertEqual(worker.run_calls, 1)
        self.assertEqual(channel.sent, [("oc_chat", {"text": "上架了"}, None)])
        self.assertEqual(worker.acks, [worker.notice])

    def test_failed_send_is_not_acknowledged(self) -> None:
        channel = FakeChannel(fail_send=True)
        worker = FakeWorker()

        with patch("douban_weread.feishu_watch_loop.asyncio.to_thread", side_effect=_inline_to_thread):
            with self.assertRaises(StopLoop):
                asyncio.run(run_watch_loop(channel, worker, interval_seconds=1, sleep=one_tick_sleep))

        self.assertEqual(worker.run_calls, 1)
        self.assertEqual(worker.acks, [])


async def _inline_to_thread(func, *args):
    return func(*args)


if __name__ == "__main__":
    unittest.main()
