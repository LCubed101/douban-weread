from __future__ import annotations

import asyncio
import unittest

from douban_weread.core.models import Edition
from douban_weread.feishu_bot import CandidateSelectionStore
from douban_weread.feishu_bot_context import (
    _end_search,
    _end_search_card,
    _return_to_candidates,
)


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, object | None]] = []

    async def send(self, to: str, message: object, opts: object | None = None):
        self.sent.append((to, message, opts))


class RejectBookContextTest(unittest.TestCase):
    def test_reject_book_returns_to_previous_candidates_and_shows_end_button(self) -> None:
        channel = FakeChannel()
        store = CandidateSelectionStore()
        store.set(
            "chat-1",
            (
                Edition(title="褚时健传", publisher="中信出版社", publish_date="2015-12", isbn="9787508656359"),
                Edition(title="褚时健传（修订版）", publisher="中信出版社", publish_date="2022-03", isbn="9787521737615"),
            ),
        )
        event = {
            "chat_id": "chat-1",
            "message_id": "message-1",
            "action": {"value": {"action": "reject_book", "douban_subject_id": "123"}},
        }

        result = asyncio.run(
            _return_to_candidates(
                channel,
                event,
                store,
                weread_lookup=None,
            )
        )

        self.assertEqual(result["toast"]["content"], "已返回版本列表。")
        self.assertEqual(len(channel.sent), 2)
        message = channel.sent[0][1]
        self.assertIn("不是这本，回到刚才的豆瓣版本", message["text"])
        self.assertIn("1. 褚时健传", message["text"])
        self.assertIn("2. 褚时健传（修订版）", message["text"])
        control = channel.sent[1][1]["card"]
        self.assertEqual(control["elements"][1]["actions"][0]["type"], "danger")
        self.assertEqual(control["elements"][1]["actions"][0]["value"]["action"], "end_search")
        self.assertEqual(len(store.get("chat-1")), 2)

    def test_end_search_clears_candidate_context(self) -> None:
        store = CandidateSelectionStore()
        store.set("chat-1", (Edition(title="听妈妈的话"),))
        event = {
            "chat_id": "chat-1",
            "message_id": "message-1",
            "action": {"value": {"action": "end_search"}},
        }

        result = asyncio.run(_end_search(store, event))

        self.assertEqual(store.get("chat-1"), ())
        self.assertEqual(result["toast"]["content"], "本次找书已结束。")
        self.assertEqual(result["card"]["header"]["template"], "grey")
        self.assertIn("发送新的书名", result["card"]["elements"][0]["content"])

    def test_end_search_button_has_colored_contrast(self) -> None:
        card = _end_search_card()
        button = card["elements"][1]["actions"][0]
        self.assertEqual(button["type"], "danger")
        self.assertEqual(button["text"]["content"], "结束本次找书")


if __name__ == "__main__":
    unittest.main()
