from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from douban_weread.core.models import Edition
from douban_weread.feishu_bot import _handle_card_action
from douban_weread.inbox_weread import WeReadLookupKind, WeReadLookupResult
from douban_weread.inbox_wish import WishFlowKind


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, object | None]] = []

    async def send(self, to: str, message: object, opts: object | None = None):
        self.sent.append((to, message, opts))
        return object()


class FakeFlow:
    def __init__(self, source: Edition) -> None:
        self.source = source

    def preflight(self, subject_id: str):
        raise AssertionError("preflight should not be called for confirm_wish")

    def commit(self, subject_id: str):
        return SimpleNamespace(
            kind=WishFlowKind.WRITTEN,
            subject_id=subject_id,
            title=self.source.title,
            message=f"《{self.source.title}》已加入豆瓣想读，并完成写后验证。",
            decision=SimpleNamespace(target=self.source),
        )


class FakeLookup:
    def __init__(self, result: WeReadLookupResult) -> None:
        self.result = result

    def lookup(self, source: Edition) -> WeReadLookupResult:
        return self.result


class FakeWatchStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    def add_or_refresh(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise ValueError("disk unavailable")
        return object()


def event() -> dict[str, object]:
    return {
        "chat_id": "oc_chat",
        "message_id": "om_card",
        "action": {
            "value": {
                "action": "confirm_wish",
                "douban_subject_id": "123",
            }
        },
    }


class FeishuWeReadWatchTests(unittest.TestCase):
    def test_unavailable_lookup_is_queued_after_verified_douban_write(self) -> None:
        source = Edition(
            title="非普通读者",
            authors=["艾伦·贝内特"],
            douban_id="123",
            isbn="9780000000001",
        )
        weread = Edition(title="非普通读者", weread_id="wr1")
        lookup = FakeLookup(
            WeReadLookupResult(
                kind=WeReadLookupKind.UNAVAILABLE,
                source_title=source.title,
                selected_edition=weread,
                deep_link="weread://book",
                message="微信读书找到了同一作品，但当前不可读。",
            )
        )
        store = FakeWatchStore()
        channel = FakeChannel()

        response = asyncio.run(
            _handle_card_action(
                channel,
                FakeFlow(source),
                event(),
                weread_lookup=lookup,
                weread_watch_store=store,
            )
        )

        self.assertEqual(len(store.calls), 1)
        self.assertEqual(store.calls[0]["chat_id"], "oc_chat")
        self.assertIs(store.calls[0]["source"], source)
        self.assertIs(store.calls[0]["weread"], weread)
        text = channel.sent[0][1]["text"]
        self.assertIn("已加入豆瓣想读", text)
        self.assertIn("已加入「等待上架」列表", text)
        self.assertEqual(response["toast"]["type"], "success")

    def test_watch_persistence_failure_does_not_reclassify_douban_write(self) -> None:
        source = Edition(title="非普通读者", douban_id="123")
        weread = Edition(title="非普通读者", weread_id="wr1")
        lookup = FakeLookup(
            WeReadLookupResult(
                kind=WeReadLookupKind.UNAVAILABLE,
                source_title=source.title,
                selected_edition=weread,
                deep_link=None,
                message="微信读书当前不可读。",
            )
        )
        channel = FakeChannel()

        response = asyncio.run(
            _handle_card_action(
                channel,
                FakeFlow(source),
                event(),
                weread_lookup=lookup,
                weread_watch_store=FakeWatchStore(fail=True),
            )
        )

        text = channel.sent[0][1]["text"]
        self.assertIn("已加入豆瓣想读", text)
        self.assertIn("等待上架记录暂时保存失败", text)
        self.assertIn("豆瓣写入已经完成", text)
        self.assertEqual(response["toast"]["type"], "success")

    def test_readable_lookup_is_not_added_to_waiting_queue(self) -> None:
        source = Edition(title="非普通读者", douban_id="123")
        weread = Edition(title="非普通读者", weread_id="wr1")
        lookup = FakeLookup(
            WeReadLookupResult(
                kind=WeReadLookupKind.EXACT,
                source_title=source.title,
                selected_edition=weread,
                deep_link="weread://read",
                message="微信读书：找到同一版本。",
            )
        )
        store = FakeWatchStore()
        channel = FakeChannel()

        asyncio.run(
            _handle_card_action(
                channel,
                FakeFlow(source),
                event(),
                weread_lookup=lookup,
                weread_watch_store=store,
            )
        )

        self.assertEqual(store.calls, [])
        self.assertNotIn("等待上架", channel.sent[0][1]["text"])


if __name__ == "__main__":
    unittest.main()
