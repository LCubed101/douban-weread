from __future__ import annotations

import asyncio
import os
import unittest
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import patch

from douban_weread.core.models import Edition
from douban_weread.feishu_bot import (
    CandidateSelectionStore,
    _handle_card_action,
    _handle_message,
    build_bot,
)
from douban_weread.inbox import BookInboxService
from douban_weread.inbox_wish import WishFlowKind, WishFlowResult
from douban_weread.providers.weread import WeReadProviderError


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


class MultiCandidateDouban(FakeDouban):
    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        self.title_calls.append(title)
        if title == "听妈妈的话":
            return [
                Edition(
                    title="听妈妈的话",
                    authors=["李凡"],
                    publisher="上海译文出版社",
                    publish_date="2026-08",
                    isbn="9787580702531",
                    douban_id="38540433",
                ),
                Edition(
                    title="听妈妈的话",
                    publisher="新疆青少年出版社",
                    isbn="9787551524728",
                    douban_id="20000002",
                ),
            ]
        return []


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


@dataclass
class FakeAction:
    value: dict[str, str]


@dataclass
class FakeCardEvent:
    chat_id: str = "oc_chat"
    message_id: str = "om_card"
    action: FakeAction = field(
        default_factory=lambda: FakeAction(
            {"action": "confirm_book", "douban_subject_id": "2567698"}
        )
    )


class FakeRecognizer:
    def __init__(self, lines: tuple[str, ...]) -> None:
        self.lines = lines
        self.images: list[bytes] = []

    async def recognize(self, image_bytes: bytes) -> tuple[str, ...]:
        self.images.append(image_bytes)
        return self.lines


class FakeWishFlow:
    def __init__(self) -> None:
        self.preflight_calls: list[str] = []
        self.commit_calls: list[str] = []
        self.preflight_result = WishFlowResult(
            kind=WishFlowKind.READY,
            subject_id="2567698",
            title="三体",
            message="ready",
        )
        self.commit_result = WishFlowResult(
            kind=WishFlowKind.WRITTEN,
            subject_id="2567698",
            title="三体",
            message="《三体》已加入豆瓣想读，并完成写后验证。",
        )

    def preflight(self, subject_id: str) -> WishFlowResult:
        self.preflight_calls.append(subject_id)
        return self.preflight_result

    def commit(self, subject_id: str) -> WishFlowResult:
        self.commit_calls.append(subject_id)
        return self.commit_result


class FakeWeReadLookup:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[Edition] = []
        self.error = error

    def lookup(self, source_edition: Edition):
        self.calls.append(source_edition)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            message="微信读书：没有找到完全相同版本，但找到了同一作品的可读版本。\n三体1 · 刘慈欣"
        )


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
                wish_flow=FakeWishFlow(),
                weread_lookup=FakeWeReadLookup(),
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

    def test_numeric_reply_selects_first_pending_candidate(self) -> None:
        channel = FakeChannel()
        provider = MultiCandidateDouban()
        service = BookInboxService(provider)
        store = CandidateSelectionStore()

        asyncio.run(
            _handle_message(
                channel,
                service,
                FakeMessage(content_text="听妈妈的话"),
                candidate_store=store,
            )
        )
        self.assertIn("回复 1–2", channel.sent[-1][1]["text"])

        asyncio.run(
            _handle_message(
                channel,
                service,
                FakeMessage(content_text="1", message_id="om_choice"),
                candidate_store=store,
            )
        )
        self.assertEqual(provider.title_calls, ["听妈妈的话"])
        self.assertIn("card", channel.sent[-1][1])
        card = channel.sent[-1][1]["card"]
        self.assertIn("听妈妈的话", card["elements"][0]["content"])
        self.assertEqual(
            card["elements"][1]["actions"][0]["value"]["douban_subject_id"],
            "38540433",
        )

    def test_pending_candidates_are_isolated_by_chat(self) -> None:
        channel = FakeChannel()
        provider = MultiCandidateDouban()
        service = BookInboxService(provider)
        store = CandidateSelectionStore()

        asyncio.run(
            _handle_message(
                channel,
                service,
                FakeMessage(chat_id="chat_a", content_text="听妈妈的话"),
                candidate_store=store,
            )
        )
        asyncio.run(
            _handle_message(
                channel,
                service,
                FakeMessage(chat_id="chat_b", content_text="1"),
                candidate_store=store,
            )
        )
        self.assertEqual(provider.title_calls, ["听妈妈的话", "1"])
        self.assertNotIn("card", channel.sent[-1][1])
        self.assertEqual(len(store.get("chat_a")), 2)
        self.assertEqual(store.get("chat_b"), ())

    def test_out_of_range_numeric_reply_does_not_search(self) -> None:
        channel = FakeChannel()
        provider = MultiCandidateDouban()
        service = BookInboxService(provider)
        store = CandidateSelectionStore()

        asyncio.run(
            _handle_message(
                channel,
                service,
                FakeMessage(content_text="听妈妈的话"),
                candidate_store=store,
            )
        )
        asyncio.run(
            _handle_message(
                channel,
                service,
                FakeMessage(content_text="8", message_id="om_bad_choice"),
                candidate_store=store,
            )
        )
        self.assertEqual(provider.title_calls, ["听妈妈的话"])
        self.assertIn("请回复 1–2", channel.sent[-1][1]["text"])
        self.assertEqual(len(store.get("oc_chat")), 2)

    def test_candidate_selection_clears_pending_list(self) -> None:
        channel = FakeChannel()
        provider = MultiCandidateDouban()
        service = BookInboxService(provider)
        store = CandidateSelectionStore()

        asyncio.run(
            _handle_message(
                channel,
                service,
                FakeMessage(content_text="听妈妈的话"),
                candidate_store=store,
            )
        )
        self.assertEqual(len(store.get("oc_chat")), 2)
        asyncio.run(
            _handle_message(
                channel,
                service,
                FakeMessage(content_text="2", message_id="om_choice"),
                candidate_store=store,
            )
        )
        self.assertEqual(store.get("oc_chat"), ())

    def test_first_card_confirmation_only_preflights_and_sends_second_card(self) -> None:
        channel = FakeChannel()
        flow = FakeWishFlow()
        response = asyncio.run(_handle_card_action(channel, flow, FakeCardEvent()))

        self.assertEqual(flow.preflight_calls, ["2567698"])
        self.assertEqual(flow.commit_calls, [])
        self.assertEqual(len(channel.sent), 1)
        self.assertIn("card", channel.sent[0][1])
        actions = channel.sent[0][1]["card"]["elements"][1]["actions"]
        self.assertEqual(actions[0]["value"]["action"], "confirm_wish")
        self.assertEqual(response["toast"]["type"], "info")

    def test_second_card_confirmation_commits_wish(self) -> None:
        channel = FakeChannel()
        flow = FakeWishFlow()
        event = FakeCardEvent(
            action=FakeAction(
                {"action": "confirm_wish", "douban_subject_id": "2567698"}
            )
        )
        response = asyncio.run(_handle_card_action(channel, flow, event))

        self.assertEqual(flow.preflight_calls, [])
        self.assertEqual(flow.commit_calls, ["2567698"])
        self.assertIn("已加入豆瓣想读", channel.sent[0][1]["text"])
        self.assertEqual(response["toast"]["type"], "success")

    def test_verified_write_is_followed_by_read_only_weread_lookup(self) -> None:
        channel = FakeChannel()
        flow = FakeWishFlow()
        source = Edition(
            title="三体",
            authors=["刘慈欣"],
            isbn="9787536692930",
            douban_id="2567698",
        )
        flow.commit_result = WishFlowResult(
            kind=WishFlowKind.WRITTEN,
            subject_id="2567698",
            title="三体",
            message="《三体》已加入豆瓣想读，并完成写后验证。",
            decision=SimpleNamespace(target=source),
        )
        lookup = FakeWeReadLookup()
        event = FakeCardEvent(
            action=FakeAction(
                {"action": "confirm_wish", "douban_subject_id": "2567698"}
            )
        )

        response = asyncio.run(
            _handle_card_action(channel, flow, event, weread_lookup=lookup)
        )

        self.assertEqual(lookup.calls, [source])
        self.assertIn("已加入豆瓣想读", channel.sent[0][1]["text"])
        self.assertIn("微信读书", channel.sent[0][1]["text"])
        self.assertIn("可读版本", channel.sent[0][1]["text"])
        self.assertEqual(response["toast"]["type"], "success")

    def test_weread_lookup_failure_does_not_reclassify_verified_douban_write_as_failed(self) -> None:
        channel = FakeChannel()
        flow = FakeWishFlow()
        source = Edition(title="三体", authors=["刘慈欣"], douban_id="2567698")
        flow.commit_result = WishFlowResult(
            kind=WishFlowKind.WRITTEN,
            subject_id="2567698",
            title="三体",
            message="《三体》已加入豆瓣想读，并完成写后验证。",
            decision=SimpleNamespace(target=source),
        )
        lookup = FakeWeReadLookup(error=WeReadProviderError("temporary lookup failure"))
        event = FakeCardEvent(
            action=FakeAction(
                {"action": "confirm_wish", "douban_subject_id": "2567698"}
            )
        )

        response = asyncio.run(
            _handle_card_action(channel, flow, event, weread_lookup=lookup)
        )

        text = channel.sent[0][1]["text"]
        self.assertIn("已加入豆瓣想读", text)
        self.assertIn("微信读书查找暂时失败", text)
        self.assertIn("不需要重复点击", text)
        self.assertEqual(response["toast"]["type"], "warning")

    def test_cancel_card_action_never_calls_wish_flow(self) -> None:
        channel = FakeChannel()
        flow = FakeWishFlow()
        event = FakeCardEvent(
            action=FakeAction(
                {"action": "cancel_wish", "douban_subject_id": "2567698"}
            )
        )
        response = asyncio.run(_handle_card_action(channel, flow, event))
        self.assertEqual(flow.preflight_calls, [])
        self.assertEqual(flow.commit_calls, [])
        self.assertEqual(channel.sent, [])
        self.assertEqual(response["toast"]["type"], "info")

    def test_card_action_without_subject_fails_closed(self) -> None:
        channel = FakeChannel()
        flow = FakeWishFlow()
        event = FakeCardEvent(action=FakeAction({"action": "confirm_wish"}))
        response = asyncio.run(_handle_card_action(channel, flow, event))
        self.assertEqual(flow.commit_calls, [])
        self.assertEqual(response["toast"]["type"], "error")

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
        asyncio.run(_handle_message(channel, service, message, image_recognizer=recognizer))
        self.assertIn("还不能稳定确定", channel.sent[0][1]["text"])


if __name__ == "__main__":
    unittest.main()
