from __future__ import annotations

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from douban_weread.core.models import Edition
from douban_weread.feishu_bot import (
    CandidateSelectionStore,
    _handle_card_action,
    _maybe_handle_candidate_number,
)
from douban_weread.inbox_wish import WishFlowKind, WishFlowResult


class Channel:
    def __init__(self):
        self.sent = []

    async def send(self, to, message, opts=None):
        self.sent.append((to, message, opts))
        return SimpleNamespace(message_id=f"om_{len(self.sent)}")


class Flow:
    def __init__(self):
        self.commits = []

    def commit(self, subject_id):
        self.commits.append(subject_id)
        raise AssertionError("Dry run must never commit")


class ChoiceIsolationTests(unittest.TestCase):
    def test_reply_selects_matching_list(self):
        store = CandidateSelectionStore()
        first = Edition(title="First", douban_id="111")
        second = Edition(title="Second", douban_id="222")
        store.set("chat", [first], "om_first")
        store.set("chat", [second], "om_second")
        channel = Channel()
        message = SimpleNamespace(
            chat_id="chat", message_id="om_user", content_text="1",
            reply_to_message_id="om_first",
        )
        self.assertTrue(asyncio.run(_maybe_handle_candidate_number(channel, message, store)))
        self.assertEqual(channel.sent[-1][1]["card"]["elements"][1]["actions"][0]["value"]["douban_subject_id"], "111")
        self.assertEqual(store.get("chat", "om_second"), (second,))

    def test_ambiguous_number_fails_closed(self):
        store = CandidateSelectionStore()
        store.set("chat", [Edition(title="First", douban_id="111")], "om_first")
        store.set("chat", [Edition(title="Second", douban_id="222")], "om_second")
        channel = Channel()
        message = SimpleNamespace(chat_id="chat", message_id="om_user", content_text="1")
        self.assertTrue(asyncio.run(_maybe_handle_candidate_number(channel, message, store)))
        self.assertIn("引用", channel.sent[-1][1]["text"])
        self.assertEqual(store.count("chat"), 2)

    def test_dry_run_blocks_card_write(self):
        channel = Channel()
        flow = Flow()
        event = {"chat_id": "chat", "message_id": "om_card",
                 "action": {"value": {"action": "confirm_wish", "douban_subject_id": "111"}}}
        with patch.dict(os.environ, {"DOUBAN_DRY_RUN": "1"}):
            result = asyncio.run(_handle_card_action(channel, flow, event))
        self.assertEqual(flow.commits, [])
        self.assertIn("DRY RUN", channel.sent[-1][1]["text"])
        self.assertEqual(result["toast"]["type"], "info")


if __name__ == "__main__":
    unittest.main()
