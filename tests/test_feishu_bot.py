from __future__ import annotations

import asyncio
import os
import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

from douban_weread.core.models import Edition
from douban_weread.feishu_bot import _handle_message, build_bot
from douban_weread.inbox import BookInboxService


class FakeDouban:
    def __init__(self) -> None:
        self.isbn_calls: list[str] = []
        self.title_calls: list[str] = []

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        self.title_calls.append(title)
        if title in {"三体", "听妈妈的话"}:
            return [Edition(title=title, authors=["作者"], douban_id="2567698")]
        return []

    def search_by_isbn(self, isbn: str) -> Edition | None:
        self.isbn_calls.append(isbn)
        if isbn == "9787536692930":
            return Edition(
                title="三体",
                authors=["刘慈欣"],
                isbn=isbn,
                douban_id="2567698",
            )
        return None

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        return None


@dataclass
class FakeResource:
    type: str = "image"
    file_key: str = "img_v3_abc"


class FakeChannel:
    def __init__(self, *, downloaded: bytes | None = b"image-bytes") -> None:
        self.handlers = {}
        self.sent: list[tuple[str, object, object | None]] = []
        self.downloaded = downloaded
        self.download_calls: list[tuple[str, str, str | None]] = []

    def on(self, event: str, handler) -> None:
        self.handlers[event] = handler

    async def connect(self) -> None:
        return None

    async def send(self, to: str, message: object, opts: object | None = None):
        self.sent.append((to, message, opts))
        return object()

    async def download_resource(
        self,
        file_key: str,
        resource_type: str = "image",
        message_id: str | None = None,
    ):
        self.download_calls.append((file_key, resource_type, message_id))
        return self.downloaded


@dataclass
class FakeMessage:
    chat_id: str = "oc_chat"
    message_id: str = "om_msg"
    content_text: str = "三体"
    raw_content_type: str = "text"
    resources: list[FakeResource] = field(default_factory=list)


class FakeRecognizer:
    def __init__(self, lines: tuple[str, ...]) -> None:
        self.lines = lines
        self.images: list[bytes] = []

    async def recognize(self, image_bytes: bytes) -> tuple[str, ...]:
        self.images.append(image_bytes)
        return self.lines


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
                image_recognizer=FakeRecognizer(("三体",)),
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

    def test_image_with_isbn_downloads_ocr_and_sends_exact_confirmation(self) -> None:
        channel = FakeChannel()
        provider = FakeDouban()
        service = BookInboxService(provider)
        recognizer = FakeRecognizer(("三体", "ISBN 978-7-5366-9293-0"))
        message = FakeMessage(
            content_text="",
            raw_content_type="image",
            resources=[FakeResource()],
        )

        asyncio.run(
            _handle_message(
                channel,
                service,
                message,
                image_recognizer=recognizer,
            )
        )

        self.assertEqual(
            channel.download_calls,
            [("img_v3_abc", "image", "om_msg")],
        )
        self.assertEqual(recognizer.images, [b"image-bytes"])
        self.assertEqual(provider.isbn_calls, ["9787536692930"])
        self.assertEqual(provider.title_calls, [])
        self.assertIn("card", channel.sent[0][1])

    def test_image_without_isbn_uses_conservative_title_hint(self) -> None:
        channel = FakeChannel()
        provider = FakeDouban()
        service = BookInboxService(provider)
        recognizer = FakeRecognizer(("听妈妈的话", "收藏 评论 转发"))
        message = FakeMessage(raw_content_type="image", resources=[FakeResource()])

        asyncio.run(
            _handle_message(channel, service, message, image_recognizer=recognizer)
        )

        self.assertEqual(
            channel.download_calls,
            [("img_v3_abc", "image", "om_msg")],
        )
        self.assertEqual(provider.title_calls, ["听妈妈的话"])
        self.assertIn("card", channel.sent[0][1])

    def test_image_without_downloadable_resource_does_not_guess(self) -> None:
        channel = FakeChannel()
        service = BookInboxService(FakeDouban())
        message = FakeMessage(raw_content_type="image", resources=[])
        asyncio.run(
            _handle_message(
                channel,
                service,
                message,
                image_recognizer=FakeRecognizer(("三体",)),
            )
        )
        self.assertIn("没有拿到可下载", channel.sent[0][1]["text"])
        self.assertEqual(channel.download_calls, [])

    def test_image_download_failure_does_not_call_ocr(self) -> None:
        channel = FakeChannel(downloaded=None)
        service = BookInboxService(FakeDouban())
        recognizer = FakeRecognizer(("三体",))
        message = FakeMessage(raw_content_type="image", resources=[FakeResource()])
        asyncio.run(
            _handle_message(channel, service, message, image_recognizer=recognizer)
        )
        self.assertEqual(
            channel.download_calls,
            [("img_v3_abc", "image", "om_msg")],
        )
        self.assertEqual(recognizer.images, [])
        self.assertIn("图片下载失败", channel.sent[0][1]["text"])

    def test_image_with_no_stable_hint_asks_for_clearer_image(self) -> None:
        channel = FakeChannel()
        service = BookInboxService(FakeDouban())
        recognizer = FakeRecognizer(("微信", "回复", "评论", "2026"))
        message = FakeMessage(raw_content_type="image", resources=[FakeResource()])
        asyncio.run(
            _handle_message(channel, service, message, image_recognizer=recognizer)
        )
        self.assertIn("还不能稳定确定", channel.sent[0][1]["text"])


if __name__ == "__main__":
    unittest.main()
