from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass

from douban_weread.feishu_capture_buffer import BufferedImageChannel


@dataclass
class Resource:
    type: str
    file_key: str


@dataclass
class Message:
    chat_id: str
    message_id: str
    raw_content_type: str
    content_text: str = ""
    resources: tuple[Resource, ...] = ()


class InnerChannel:
    def __init__(self) -> None:
        self.handlers = {}
        self.download_calls = []

    def on(self, event, handler):
        self.handlers[event] = handler

    async def connect(self):
        return None

    async def send(self, to, message, opts=None):
        return None

    async def download_resource(self, file_key, resource_type="image", message_id=None):
        self.download_calls.append((file_key, message_id))
        return b"img"


class CaptureBufferTest(unittest.IsolatedAsyncioTestCase):
    async def test_two_separate_image_events_become_one_post(self) -> None:
        inner = InnerChannel()
        channel = BufferedImageChannel(inner, quiet_seconds=0.2)
        received = []

        async def handler(message):
            received.append(message)

        channel.on("message", handler)
        await inner.handlers["message"](
            Message("chat-1", "m1", "image", resources=(Resource("image", "k1"),))
        )
        await inner.handlers["message"](
            Message("chat-1", "m2", "image", resources=(Resource("image", "k2"),))
        )
        await asyncio.sleep(0.3)

        self.assertEqual(len(received), 1)
        merged = received[0]
        self.assertEqual(merged.raw_content_type, "post")
        self.assertEqual([r.file_key for r in merged.resources], ["k1", "k2"])

    async def test_download_uses_each_original_message_id(self) -> None:
        inner = InnerChannel()
        channel = BufferedImageChannel(inner, quiet_seconds=0.2)
        received = []

        async def handler(message):
            received.append(message)

        channel.on("message", handler)
        await inner.handlers["message"](
            Message("chat-1", "m1", "image", resources=(Resource("image", "k1"),))
        )
        await inner.handlers["message"](
            Message("chat-1", "m2", "image", resources=(Resource("image", "k2"),))
        )
        await asyncio.sleep(0.3)
        merged = received[0]

        await channel.download_resource("k1", message_id=merged.message_id)
        await channel.download_resource("k2", message_id=merged.message_id)
        self.assertEqual(inner.download_calls, [("k1", "m1"), ("k2", "m2")])


if __name__ == "__main__":
    unittest.main()
