from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from douban_weread.core.models import Edition
from douban_weread.feishu_compact_douban import (
    _compact_base_text,
    _is_same_work_existing_wish,
    _preserved_higher_state,
    _send_commit_result,
)
from douban_weread.inbox_wish import WishFlowKind
from douban_weread.reconciliation import ReconciliationAction


class FakeDecision:
    def __init__(
        self,
        reason: str = "",
        target: Edition | None = None,
        action: ReconciliationAction | None = None,
    ) -> None:
        self.reason = reason
        self.target = target
        self.action = action


class FakeResult:
    def __init__(
        self,
        kind,
        title: str,
        reason: str = "",
        action: ReconciliationAction | None = None,
    ) -> None:
        self.kind = kind
        self.title = title
        self.message = "verbose provider message"
        self.decision = FakeDecision(
            reason,
            Edition(title=title, douban_id="123"),
            action,
        )


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, object | None]] = []

    async def send(self, to: str, message: object, opts: object | None = None):
        self.sent.append((to, message, opts))
        return object()


class FakeLookup:
    def __init__(self) -> None:
        self.calls: list[Edition] = []

    def lookup(self, source_edition: Edition):
        self.calls.append(source_edition)
        return SimpleNamespace(message="✅ 微信读书：有同版可读")


class CompactDoubanFlowTest(unittest.TestCase):
    def test_written_result_uses_short_copy(self) -> None:
        result = FakeResult(WishFlowKind.WRITTEN, "商业模式新生代")
        self.assertEqual(_compact_base_text(result), "✅《商业模式新生代》已加入豆瓣想读。")

    def test_already_wish_result_uses_short_copy(self) -> None:
        result = FakeResult(WishFlowKind.ALREADY_WISH, "价值主张设计")
        self.assertEqual(_compact_base_text(result), "✅《价值主张设计》豆瓣已经是想读。")

    def test_same_work_existing_wish_is_not_reported_as_raw_english_error(self) -> None:
        result = FakeResult(
            WishFlowKind.BLOCKED,
            "商业模式新生代",
            "Another edition of the same Work is already marked Want-to-Read. This is an edition mismatch.",
        )
        self.assertTrue(_is_same_work_existing_wish(result))
        self.assertEqual(
            _compact_base_text(result),
            "✅ 豆瓣里已经有《商业模式新生代》同一作品的想读版本，不重复添加。",
        )

    def test_already_reading_uses_friendly_copy(self) -> None:
        result = FakeResult(
            WishFlowKind.BLOCKED,
            "精要主义",
            "The selected edition is already marked reading; do not downgrade it to Want-to-Read.",
            ReconciliationAction.NOOP_ALREADY_READING,
        )
        text = _compact_base_text(result)
        self.assertEqual(_preserved_higher_state(result), "在读")
        self.assertEqual(
            text,
            "📖《精要主义》已经在豆瓣「在读」，已保留当前状态，不会改成「想读」。",
        )
        self.assertNotIn("do not downgrade", text)

    def test_already_read_uses_friendly_copy(self) -> None:
        result = FakeResult(
            WishFlowKind.BLOCKED,
            "精要主义",
            "The selected edition is already marked read; do not downgrade it to Want-to-Read.",
            ReconciliationAction.NOOP_ALREADY_READ,
        )
        self.assertEqual(_preserved_higher_state(result), "读过")
        self.assertEqual(
            _compact_base_text(result),
            "📖《精要主义》已经在豆瓣「读过」，已保留当前状态，不会改成「想读」。",
        )

    def test_preserved_reading_state_still_checks_weread(self) -> None:
        result = FakeResult(
            WishFlowKind.BLOCKED,
            "精要主义",
            "The selected edition is already marked reading; do not downgrade it to Want-to-Read.",
            ReconciliationAction.NOOP_ALREADY_READING,
        )
        channel = FakeChannel()
        lookup = FakeLookup()
        selected = result.decision.target

        asyncio.run(
            _send_commit_result(
                channel,
                chat_id="oc_chat",
                message_id="om_msg",
                result=result,
                selected_edition=selected,
                weread_lookup=lookup,
                weread_watch_store=None,
            )
        )

        self.assertEqual(lookup.calls, [selected])
        text = channel.sent[0][1]["text"]
        self.assertIn("豆瓣「在读」", text)
        self.assertIn("微信读书", text)
        self.assertNotIn("do not downgrade", text)


if __name__ == "__main__":
    unittest.main()
