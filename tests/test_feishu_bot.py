from __future__ import annotations

import asyncio
import os
import unittest
from dataclasses import dataclass
from unittest.mock import patch

from douban_weread.core.models import Edition
from douban_weread.feishu_bot import _handle_message, build_bot
from douban_weread.inbox import BookInboxService


class FakeDouban:
    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        if title == "三体":
            return [Edition(title="三体", authors=["刘慈欣"], douban_id="2567698")]
        return []

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        return None


class FakeChannel:
    def __init__(self) -> None:
        self.handlers = {}
        self.sent: list[tuple[str, object, object | None]] = []

    def on(self, event: str, handler) -> None:
        self.handlers[event] = handler

    async def connect(self) -> None:
        return None

    async def send(self, to: str, message: object, opts: object | None = None):
        self.sent.append((to, message, opts))
        return object()


@dataclass
class FakeMessage:
    chat_id: str = "oc_chat"
    message_id: str = "om_msg"
    content_text: str = "三体"
    raw_content_type: str = "text"


class FeishuBotTests(unittest.TestCase):
    def test_build_bot_requires_local_credentials(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "FEISHU_APP_ID"):
                build_bot(channel_factory=lambda app_id, secret: FakeChannel())

    def test_build_bot_registers_message_card_and_error_handlers(self) -> None:
        channel = FakeChannel()
        with patch.dict(
            os.environ,
            {"FEISHU_APP_ID": "cli_test", "FEISHU_APP_SECRET": "secret"},
            clear=True,
        ):
            result = build_bot(
                channel_factory=lambda app_id, secret: channel,
                inbox_service=BookInboxService(FakeDouban()),
            )
        self.assertIs(result, channel)
        self.assertEqual(set(channel.handlers), {"message", "cardAction", "error"})

    def test_text_message_sends_confirmation_card_as_reply(self) -> None:
        channel = FakeChannel()
        service = BookInboxService(FakeDouban())
        asyncio.run(_handle_message(channel, service, FakeMessage()))
        self.assertEqual(len(channel.sent), 1)
        chat_id, payload, opts = channel.sent[0]
        self.assertEqual(chat_id, "oc_chat")
        self.assertIn("card", payload)
        self.assertEqual(opts, {"reply_to": "om_msg"})

    def test_image_message_is_acknowledged_without_guessing_identity(self) -> None:
        channel = FakeChannel()
        service = BookInboxService(FakeDouban())
        message = FakeMessage(content_text="", raw_content_type="image")
        asyncio.run(_handle_message(channel, service, message))
        self.assertEqual(len(channel.sent), 1)
        payload = channel.sent[0][1]
        self.assertIn("图片已经收到", payload["text"])


if __name__ == "__main__":
    unittest.main()
