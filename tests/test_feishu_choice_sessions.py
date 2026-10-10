from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from douban_weread.core.models import Edition
from douban_weread import feishu_bot as base
from douban_weread.feishu_bot import CandidateSelectionStore, _handle_message
from douban_weread import feishu_compact_douban as compact
from douban_weread.feishu_bot_v11 import build_bot
from douban_weread.feishu_movie_bot import _MovieAwareRawChannel
from douban_weread.inbox import BookInboxService
from tests.test_feishu_bot import FakeChannel, FakeMessage, FakeRecognizer, FakeWishFlow, FakeWeReadLookup


class TwoBooksDouban:
    def __init__(self) -> None:
        self.title_calls: list[str] = []

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        self.title_calls.append(title)
        if title not in {"君幸食", "球形的荒野"}:
            return []
        return [
            Edition(title=title, authors=["作者甲"], douban_id="1001"),
            Edition(title=title, authors=["作者乙"], douban_id="1002"),
        ]

    def search_by_isbn(self, isbn: str) -> Edition | None:
        return None

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        return None


class FeishuChoiceSessionTests(unittest.TestCase):
    def test_quoted_choice_resolves_correct_book_with_two_pending(self) -> None:
        store = CandidateSelectionStore()
        first = [Edition(title="君幸食", douban_id="1001")]
        second = [Edition(title="球形的荒野", douban_id="2001")]
        store.set("chat", first, title="君幸食")
        store.bind_message("chat", "om_first", "君幸食", first)
        store.set("chat", second, title="球形的荒野")
        store.bind_message("chat", "om_second", "球形的荒野", second)
        self.assertEqual(store.get_for_reply("chat", "om_first"), tuple(first))
        self.assertEqual(store.get_for_reply("chat", "om_second"), tuple(second))
        self.assertEqual(store.get_for_reply("other", "om_first"), ())
        self.assertEqual(store.get("chat"), ())

    def test_replaced_candidate_list_invalidates_old_reply(self) -> None:
        store = CandidateSelectionStore()
        first = [Edition(title="君幸食", douban_id="1001")]
        replacement = [Edition(title="君幸食", douban_id="1002")]
        store.set("chat", first, title="君幸食")
        store.bind_message("chat", "om_old", "君幸食", first)
        store.set("chat", replacement, title="君幸食")
        self.assertEqual(store.get_for_reply("chat", "om_old"), ())
        store.clear("chat")
        self.assertEqual(store.get_for_reply("chat", "om_old"), ())

    def test_two_pending_books_never_guess_bare_number(self) -> None:
        channel, provider, store = FakeChannel(), TwoBooksDouban(), CandidateSelectionStore()
        service = BookInboxService(provider)
        for title in ("君幸食", "球形的荒野"):
            asyncio.run(_handle_message(
                channel, service, FakeMessage(content_text=title), candidate_store=store,
            ))
        self.assertEqual(set(store.titles("oc_chat")), {"君幸食", "球形的荒野"})
        asyncio.run(_handle_message(
            channel, service, FakeMessage(content_text="1", message_id="choice"), candidate_store=store,
        ))
        self.assertEqual(provider.title_calls, ["君幸食", "球形的荒野"])
        self.assertNotIn("card", channel.sent[-1][1])
        self.assertIn("《书名》 1", channel.sent[-1][1]["text"])
        self.assertEqual(channel.sent[-1][2], {"reply_to": "choice"})

    def test_explicit_title_number_selects_correct_book(self) -> None:
        channel, provider, store = FakeChannel(), TwoBooksDouban(), CandidateSelectionStore()
        service = BookInboxService(provider)
        for title in ("君幸食", "球形的荒野"):
            asyncio.run(_handle_message(
                channel, service, FakeMessage(content_text=title), candidate_store=store,
            ))
        asyncio.run(_handle_message(
            channel, service,
            FakeMessage(content_text="《君幸食》 2", message_id="choice"),
            candidate_store=store,
        ))
        card = channel.sent[-1][1]["card"]
        self.assertEqual(next(action["value"]["douban_subject_id"] for element in card["elements"] for action in element.get("actions", []) if "douban_subject_id" in action.get("value", {})), "1002")
        self.assertEqual(provider.title_calls, ["君幸食", "球形的荒野"])

    def test_orphan_number_never_calls_douban(self) -> None:
        channel, provider = FakeChannel(), TwoBooksDouban()
        asyncio.run(_handle_message(
            channel, BookInboxService(provider),
            FakeMessage(content_text="1", message_id="orphan"),
            candidate_store=CandidateSelectionStore(),
        ))
        self.assertEqual(provider.title_calls, [])
        self.assertIn("没有待选版本", channel.sent[-1][1]["text"])

    def test_orphan_qualified_number_never_searches_douban(self) -> None:
        channel, provider = FakeChannel(), TwoBooksDouban()
        asyncio.run(_handle_message(
            channel, BookInboxService(provider),
            FakeMessage(content_text="《君幸食》 2", message_id="orphan-qualified"),
            candidate_store=CandidateSelectionStore(),
        ))
        self.assertEqual(provider.title_calls, [])
        self.assertIn("没有待选版本", channel.sent[-1][1]["text"])
        self.assertEqual(channel.sent[-1][2], {"reply_to": "orphan-qualified"})

    def test_new_not_found_does_not_erase_other_pending_book(self) -> None:
        channel, provider, store = FakeChannel(), TwoBooksDouban(), CandidateSelectionStore()
        service = BookInboxService(provider)
        for title in ("君幸食", "不存在的书"):
            asyncio.run(_handle_message(
                channel, service, FakeMessage(content_text=title), candidate_store=store,
            ))
        self.assertEqual(store.titles("oc_chat"), ("君幸食",))
        asyncio.run(_handle_message(
            channel, service, FakeMessage(content_text="1"), candidate_store=store,
        ))
        self.assertIn("card", channel.sent[-1][1])

    def test_actual_compact_flow_never_writes_ambiguous_number(self) -> None:
        channel, provider, store = FakeChannel(), TwoBooksDouban(), CandidateSelectionStore()
        service = BookInboxService(provider)
        for title in ("君幸食", "球形的荒野"):
            asyncio.run(_handle_message(
                channel, service, FakeMessage(content_text=title), candidate_store=store,
            ))
        flow = FakeWishFlow()
        original_handler = base._maybe_handle_candidate_number
        original_prepared = compact._PREPARED
        try:
            compact._PREPARED = False
            with (
                patch.object(compact, "DoubanWishFlow", return_value=flow),
                patch.object(compact, "WeReadEditionLookup", return_value=FakeWeReadLookup()),
                patch.object(compact, "default_watch_store", return_value=object()),
                patch.object(compact, "_send_commit_result", new_callable=AsyncMock),
            ):
                compact.prepare_compact_douban_flow()
                asyncio.run(base._maybe_handle_candidate_number(
                    channel, FakeMessage(content_text="1"), store,
                ))
                self.assertEqual(flow.commit_calls, [])
                self.assertIn("《书名》 1", channel.sent[-1][1]["text"])
        finally:
            base._maybe_handle_candidate_number = original_handler
            compact._PREPARED = original_prepared

    def test_movie_aware_router_serializes_full_message_pipeline(self) -> None:
        channel = FakeChannel()
        events: list[str] = []
        active = 0
        peak = 0

        class Router:
            async def try_handle_message(self, _channel, message, _recognizer):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                if message.content_text == "君幸食":
                    await asyncio.sleep(0.02)
                events.append(message.content_text)
                active -= 1
                return True

        class MixedRouter:
            async def try_handle_message(self, _channel, _message, _recognizer):
                return False

        wrapper = _MovieAwareRawChannel(channel, Router(), MixedRouter(), object())
        wrapper.on("message", AsyncMock())

        async def run() -> None:
            await asyncio.gather(
                channel.handlers["message"](FakeMessage(content_text="君幸食")),
                channel.handlers["message"](FakeMessage(content_text="球形的荒野")),
            )

        asyncio.run(run())
        self.assertEqual(peak, 1)
        self.assertEqual(events, ["君幸食", "球形的荒野"])

    def test_v11_serializes_messages_in_same_chat(self) -> None:
        channel = FakeChannel()
        active = 0
        peak = 0
        observed: list[str] = []

        async def fake_handle(*args, **kwargs):
            nonlocal active, peak
            message = args[2]
            active += 1
            peak = max(peak, active)
            if message.content_text == "君幸食":
                await asyncio.sleep(0.02)
            observed.append(message.content_text)
            active -= 1

        with (
            patch("douban_weread.feishu_bot_v11.base._credentials", return_value=("id", "secret")),
            patch("douban_weread.feishu_bot_v11._try_handle_waiting_list_command", new_callable=AsyncMock, return_value=False),
            patch("douban_weread.feishu_bot_v11._try_handle_multi_book_message", new_callable=AsyncMock, return_value=False),
            patch("douban_weread.feishu_bot_v11.base._handle_message", side_effect=fake_handle),
        ):
            build_bot(
                channel_factory=lambda _id, _secret: channel,
                inbox_service=BookInboxService(TwoBooksDouban()),
                image_recognizer=FakeRecognizer(()),
                wish_flow=FakeWishFlow(),
                weread_lookup=FakeWeReadLookup(),
                weread_watch_store=object(),
            )

            async def run() -> None:
                await asyncio.gather(
                    channel.handlers["message"](FakeMessage(content_text="君幸食")),
                    channel.handlers["message"](FakeMessage(content_text="球形的荒野")),
                )

            asyncio.run(run())
        self.assertEqual(peak, 1)
        self.assertEqual(observed, ["君幸食", "球形的荒野"])


if __name__ == "__main__":
    unittest.main()
