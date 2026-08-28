from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass

from douban_weread.core.models import Edition
from douban_weread.feishu_bot import CandidateSelectionStore
from douban_weread.feishu_multi_image import mentions_from_message, try_handle_book_batch_message
from douban_weread.inbox_weread import WeReadLookupKind


@dataclass
class FakeResource:
    type: str
    file_key: str


@dataclass
class FakeMessage:
    chat_id: str = "chat-1"
    message_id: str = "message-1"
    content_text: str = ""
    raw_content_type: str = "post"
    resources: tuple[FakeResource, ...] = ()


class FakeChannel:
    def __init__(self, missing: set[str] | None = None) -> None:
        self.missing = missing or set()
        self.downloaded: list[str] = []
        self.sent: list[tuple[str, object, object | None]] = []

    async def download_resource(self, file_key: str, resource_type: str = "image", message_id: str | None = None):
        self.downloaded.append(file_key)
        if file_key in self.missing:
            return None
        return file_key.encode("utf-8")

    async def send(self, to: str, message: object, opts: object | None = None):
        self.sent.append((to, message, opts))


class FakeRecognizer:
    async def recognize(self, image_bytes: bytes):
        key = image_bytes.decode("utf-8")
        if key == "img-1":
            return ("推荐《深度工作》和《专注》。",)
        if key == "img-2":
            return ("继续推荐《资本主义的未来》和《如何改变世界》。",)
        return ()


class FakeResult:
    def __init__(self, title: str) -> None:
        self.kind = WeReadLookupKind.EXACT
        self.message = f"找到《{title}》"
        self.deep_link = f"https://weread.qq.com/{title}"
        self.selected_edition = Edition(title=title)


class FakeLookup:
    def lookup_title(self, title: str):
        return FakeResult(title)

    def lookup(self, edition: Edition):
        return FakeResult(edition.title)


class FeishuMultiImageTest(unittest.TestCase):
    def test_post_with_two_images_merges_ocr_before_extraction(self) -> None:
        message = FakeMessage(
            content_text="flomo 书单",
            resources=(
                FakeResource("image", "img-1"),
                FakeResource("image", "img-2"),
            ),
        )
        channel = FakeChannel()

        mentions = asyncio.run(mentions_from_message(channel, message, FakeRecognizer()))

        self.assertEqual(channel.downloaded, ["img-1", "img-2"])
        self.assertEqual(
            [mention.title for mention in mentions],
            ["深度工作", "专注", "资本主义的未来", "如何改变世界"],
        )

    def test_multi_image_batch_sends_one_summary_card(self) -> None:
        message = FakeMessage(
            resources=(
                FakeResource("image", "img-1"),
                FakeResource("image", "img-2"),
            ),
        )
        channel = FakeChannel()

        handled = asyncio.run(
            try_handle_book_batch_message(
                channel,
                message,
                FakeRecognizer(),
                FakeLookup(),
                CandidateSelectionStore(),
            )
        )

        self.assertTrue(handled)
        self.assertEqual(len(channel.sent), 1)
        rendered = str(channel.sent[0][1]["card"])
        self.assertIn("4 本", rendered)
        self.assertIn("深度工作", rendered)
        self.assertIn("如何改变世界", rendered)

    def test_one_failed_download_keeps_other_image_ocr(self) -> None:
        message = FakeMessage(
            resources=(
                FakeResource("image", "img-1"),
                FakeResource("image", "img-2"),
            ),
        )
        channel = FakeChannel(missing={"img-2"})

        mentions = asyncio.run(mentions_from_message(channel, message, FakeRecognizer()))

        self.assertEqual([mention.title for mention in mentions], ["深度工作", "专注"])

    def test_multi_image_without_books_is_consumed_instead_of_legacy_fallback(self) -> None:
        class EmptyRecognizer:
            async def recognize(self, image_bytes: bytes):
                return ("没有明确书名",)

        message = FakeMessage(
            resources=(
                FakeResource("image", "img-1"),
                FakeResource("image", "img-2"),
            ),
        )
        channel = FakeChannel()

        handled = asyncio.run(
            try_handle_book_batch_message(
                channel,
                message,
                EmptyRecognizer(),
                FakeLookup(),
                CandidateSelectionStore(),
            )
        )

        self.assertTrue(handled)
        self.assertEqual(len(channel.sent), 1)
        self.assertIn("收到 2 张图片", channel.sent[0][1]["text"])


if __name__ == "__main__":
    unittest.main()
