from __future__ import annotations

import asyncio
import os
import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

from douban_weread.adapters.feishu_ocr import (
    FEISHU_OCR_RATE_LIMIT_CODE,
    FEISHU_OCR_RATE_LIMIT_MESSAGE,
    FeishuOcrError,
)
from douban_weread.feishu_bot import build_bot


@dataclass
class FakeResource:
    type: str = "image"
    file_key: str = "img_rate_limited"


@dataclass
class FakeMessage:
    chat_id: str = "oc_chat"
    message_id: str = "om_image"
    content_text: str = ""
    raw_content_type: str = "image"
    resources: list[FakeResource] = field(default_factory=lambda: [FakeResource()])


class FakeChannel:
    def __init__(self) -> None:
        self.handlers = {}
        self.sent = []

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
        return b"image-bytes"


class RateLimitedRecognizer:
    def __init__(self) -> None:
        self.calls = 0

    async def recognize(self, image_bytes: bytes):
        self.calls += 1
        raise FeishuOcrError(
            FEISHU_OCR_RATE_LIMIT_MESSAGE,
            code=FEISHU_OCR_RATE_LIMIT_CODE,
        )


class FeishuOcrRateLimitTests(unittest.TestCase):
    def test_rate_limit_error_is_typed(self) -> None:
        error = FeishuOcrError(
            FEISHU_OCR_RATE_LIMIT_MESSAGE,
            code=FEISHU_OCR_RATE_LIMIT_CODE,
        )
        self.assertTrue(error.is_rate_limited)
        self.assertEqual(str(error), FEISHU_OCR_RATE_LIMIT_MESSAGE)

    def test_bot_returns_stable_fallback_without_retrying_ocr(self) -> None:
        channel = FakeChannel()
        recognizer = RateLimitedRecognizer()
        with patch.dict(
            os.environ,
            {"FEISHU_APP_ID": "cli_test", "FEISHU_APP_SECRET": "secret"},
            clear=True,
        ):
            build_bot(
                channel_factory=lambda app_id, secret: channel,
                inbox_service=object(),
                image_recognizer=recognizer,
                wish_flow=object(),
                weread_lookup=object(),
                weread_watch_store=object(),
            )

        asyncio.run(channel.handlers["message"](FakeMessage()))

        self.assertEqual(recognizer.calls, 1)
        self.assertEqual(len(channel.sent), 1)
        self.assertIn(FEISHU_OCR_RATE_LIMIT_MESSAGE, channel.sent[0][1]["text"])
        self.assertEqual(channel.sent[0][2], {"reply_to": "om_image"})


if __name__ == "__main__":
    unittest.main()
