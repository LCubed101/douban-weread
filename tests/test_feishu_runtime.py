from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from douban_weread.feishu_runtime import run_runtime, watch_interval_seconds


class FakeChannel:
    def __init__(self) -> None:
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def send(self, to: str, message: object, opts: object | None = None):
        return object()


class FakeWorker:
    def run_once(self):
        return []

    def acknowledge(self, notice) -> None:
        raise AssertionError("no notice should be acknowledged")


class FeishuRuntimeTests(unittest.TestCase):
    def test_default_interval_is_7_days(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(watch_interval_seconds(), 604800.0)

    def test_interval_can_be_overridden(self) -> None:
        with patch.dict(os.environ, {"DOUBAN_WEREAD_WATCH_INTERVAL_SECONDS": "3600"}, clear=True):
            self.assertEqual(watch_interval_seconds(), 3600.0)

    def test_invalid_interval_fails_closed(self) -> None:
        with patch.dict(os.environ, {"DOUBAN_WEREAD_WATCH_INTERVAL_SECONDS": "0"}, clear=True):
            with self.assertRaises(RuntimeError):
                watch_interval_seconds()

    def test_runtime_connects_channel_and_cancels_background_loop_on_exit(self) -> None:
        channel = FakeChannel()
        worker = FakeWorker()
        asyncio.run(run_runtime(channel, worker, interval_seconds=604800))
        self.assertTrue(channel.connected)


if __name__ == "__main__":
    unittest.main()
