from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass

from douban_weread.core.models import Edition
from douban_weread.feishu_bot import CandidateSelectionStore
from douban_weread.feishu_bot_v11 import _try_handle_multi_book_message
from douban_weread.inbox_weread import WeReadLookupKind


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
    def __init__(self, title: str, *, kind=WeReadLookupKind.EXACT) -> None:
        self.kind = kind
        self.message = f"微信读书：找到《{title}》。"
        self.deep_link = f"https://weread.qq.com/{title}" if kind is WeReadLookupKind.EXACT else None
        self.selected_edition = Edition(title=title) if kind is not WeReadLookupKind.NOT_FOUND else None


class FakeLookup:
    def lookup(self, edition):
        return FakeResult(edition.title)


class MixedLookup:
    def lookup(self, edition):
        if edition.title == "价值主张设计":
            return FakeResult(edition.title, kind=WeReadLookupKind.NOT_FOUND)
        return FakeResult(edition.title)


class FakeWatchEntry:
    def __init__(self, title: str) -> None:
        self.chat_id = "chat-1"
        self.source_title = title
        self.watch_kind = "not_found"
        self.next_check_at = "2026-11-25T00:00:00+00:00"


class FakeWatchStore:
    def __init__(self) -> None:
        self.entries = [FakeWatchEntry("价值主张设计")]

    def pending(self):
        return list(self.entries)

    def add_or_refresh(self, **kwargs):
        return self.entries[0]


class FeishuMultiBookV11Test(unittest.TestCase):
    def test_long_text_returns_one_summary_card(self) -> None:
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
        self.assertEqual(len(channel.sent), 1)
        card = channel.sent[0][1]["card"]
        self.assertEqual(card["header"]["title"]["content"], "书单处理结果")
        rendered = str(card)
        self.assertIn("2 本", rendered)
        self.assertIn("价值主张设计", rendered)
        self.assertIn("商业模式新生代", rendered)
        self.assertIn("打开《价值主张设计》", rendered)
        self.assertNotIn("###", rendered)

    def test_flomo_screenshot_uses_ocr_then_returns_one_summary(self) -> None:
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
        self.assertEqual(len(channel.sent), 1)
        rendered = str(channel.sent[0][1]["card"])
        self.assertIn("4 本", rendered)
        self.assertIn("巨人的工具", rendered)
        self.assertIn("思考，快与慢", rendered)

    def test_waiting_results_get_button_and_short_copy(self) -> None:
        channel = FakeChannel()
        message = FakeMessage(
            content_text="推荐《价值主张设计》《商业模式新生代》。",
            raw_content_type="text",
        )
        handled = asyncio.run(
            _try_handle_multi_book_message(
                channel,
                message,
                FakeRecognizer(),
                MixedLookup(),
                CandidateSelectionStore(),
                FakeWatchStore(),
            )
        )
        self.assertTrue(handled)
        rendered = str(channel.sent[0][1]["card"])
        self.assertIn("已帮你记住 1 本", rendered)
        self.assertIn("2026-11-25 重搜", rendered)
        self.assertIn("查看等待列表", rendered)
        self.assertIn("show_waiting_list", rendered)
        self.assertNotIn("发送 **查看待上架**", rendered)
        self.assertNotIn("###", rendered)

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
