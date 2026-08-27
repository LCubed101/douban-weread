from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass

from douban_weread.feishu_bot import CandidateSelectionStore
from douban_weread.feishu_bot_v11 import _try_handle_multi_book_message


@dataclass
class FakeResource:
    type: str = "image"
    file_key: str = "img-1"


@dataclass
class FakeMessage:
    chat_id: str = "chat-1"
    message_id: str = "message-1"
    content_text: str = ""
    raw_content_type: str = "text"
    resources: tuple[FakeResource, ...] = ()


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, object | None]] = []

    async def send(self, to: str, message: object, opts: object | None = None):
        self.sent.append((to, message, opts))

    async def download_resource(self, file_key: str, resource_type: str = "image", message_id: str | None = None):
        return b"fake-image"


class FakeRecognizer:
    async def recognize(self, image_bytes: bytes) -> tuple[str, ...]:
        return (
            "关于学习系统，推荐《巨人的工具》与《如何高效学习》。",
            "也可以看看《反脆弱》与《思考，快与慢》。",
        )


class FakeResult:
    def __init__(self, title: str) -> None:
        self.message = f"微信读书：找到《{title}》。\n可读链接：https://weread.qq.com/{title}"


class FakeLookup:
    def lookup(self, edition):
        return FakeResult(edition.title)


class FeishuMultiBookV11Test(unittest.TestCase):
    def test_long_text_routes_multiple_explicit_books_to_weread(self) -> None:
        channel = FakeChannel()
        message = FakeMessage(
            content_text="推荐《价值主张设计》《商业模式新生代》《价值主张设计》。",
            raw_content_type="text",
        )
        handled = asyncio.run(
            _try_handle_multi_book_message(
                channel,
                message,
                FakeRecognizer(),
                FakeLookup(),
                CandidateSelectionStore(),
            )
        )
        self.assertTrue(handled)
        self.assertIn("识别到 2 本书", channel.sent[0][1]["text"])
        self.assertEqual(len(channel.sent), 3)
        self.assertIn("价值主张设计", channel.sent[1][1]["text"])
        self.assertIn("商业模式新生代", channel.sent[2][1]["text"])

    def test_flomo_screenshot_uses_ocr_then_routes_books(self) -> None:
        channel = FakeChannel()
        message = FakeMessage(
            raw_content_type="image",
            resources=(FakeResource(),),
        )
        handled = asyncio.run(
            _try_handle_multi_book_message(
                channel,
                message,
                FakeRecognizer(),
                FakeLookup(),
                CandidateSelectionStore(),
            )
        )
        self.assertTrue(handled)
        self.assertIn("识别到 4 本书", channel.sent[0][1]["text"])
        self.assertEqual(len(channel.sent), 5)

    def test_single_plain_title_keeps_existing_flow(self) -> None:
        channel = FakeChannel()
        message = FakeMessage(content_text="白夜行", raw_content_type="text")
        handled = asyncio.run(
            _try_handle_multi_book_message(
                channel,
                message,
                FakeRecognizer(),
                FakeLookup(),
                CandidateSelectionStore(),
            )
        )
        self.assertFalse(handled)
        self.assertEqual(channel.sent, [])


if __name__ == "__main__":
    unittest.main()
