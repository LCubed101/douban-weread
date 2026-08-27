from __future__ import annotations

import asyncio
import os
import unittest
from dataclasses import dataclass
from unittest.mock import patch

from douban_weread.core.models import Edition
from douban_weread.feishu_bot_weread_only import _handle_weread_only_message
from douban_weread.feishu_runtime import router_mode
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
        self.sent = []

    async def send(self, to, message, opts=None):
        self.sent.append((to, message, opts))

    async def download_resource(self, file_key, resource_type="image", message_id=None):
        return b"image"


class FakeRecognizer:
    async def recognize(self, image_bytes):
        return ("推荐《专注》和《深度工作》",)


class FakeResult:
    def __init__(self, title: str, kind=WeReadLookupKind.EXACT):
        self.kind = kind
        self.selected_edition = Edition(title=title) if kind is not WeReadLookupKind.NOT_FOUND else None
        self.deep_link = f"https://weread.qq.com/{title}" if kind is WeReadLookupKind.EXACT else None
        self.message = "ok"


class FakeLookup:
    def __init__(self):
        self.titles = []

    def lookup_title(self, title):
        self.titles.append(title)
        return FakeResult(title)


class FakeWatchStore:
    def pending(self):
        return []

    def add_or_refresh(self, **kwargs):
        raise AssertionError("available result should not be watched")


class WeReadOnlyModeTest(unittest.TestCase):
    def test_router_mode_defaults_to_douban_weread(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(router_mode(), "douban_weread")

    def test_router_mode_accepts_weread_only(self):
        with patch.dict(os.environ, {"ROUTER_MODE": "weread_only"}, clear=True):
            self.assertEqual(router_mode(), "weread_only")

    def test_plain_single_title_goes_directly_to_weread(self):
        channel = FakeChannel()
        lookup = FakeLookup()
        asyncio.run(
            _handle_weread_only_message(
                channel,
                FakeMessage(content_text="专注"),
                FakeRecognizer(),
                lookup,
                FakeWatchStore(),
            )
        )
        self.assertEqual(lookup.titles, ["专注"])
        self.assertEqual(len(channel.sent), 1)
        rendered = str(channel.sent[0][1]["card"])
        self.assertIn("1 本", rendered)
        self.assertIn("打开《专注》", rendered)
        self.assertNotIn("豆瓣", rendered)

    def test_flomo_screenshot_routes_multiple_titles_without_douban(self):
        channel = FakeChannel()
        lookup = FakeLookup()
        asyncio.run(
            _handle_weread_only_message(
                channel,
                FakeMessage(raw_content_type="image", resources=(FakeResource(),)),
                FakeRecognizer(),
                lookup,
                FakeWatchStore(),
            )
        )
        self.assertEqual(lookup.titles, ["专注", "深度工作"])
        rendered = str(channel.sent[0][1]["card"])
        self.assertIn("2 本", rendered)
        self.assertIn("打开《专注》", rendered)
        self.assertIn("打开《深度工作》", rendered)


if __name__ == "__main__":
    unittest.main()
