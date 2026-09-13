from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from douban_weread.core.models import Edition
from douban_weread.feishu_bot import CandidateSelectionStore, _handle_message
from douban_weread.inbox import BookInboxService
from douban_weread.inbox_wish import WishFlowKind, WishFlowResult


class FakeDouban:
    """Search provider returning a fixed, pre-arranged candidate list per title."""

    def __init__(self, by_title: dict[str, list[Edition]]) -> None:
        self._by_title = by_title
        self.title_calls: list[str] = []

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        self.title_calls.append(title)
        return list(self._by_title.get(title, []))

    def search_by_isbn(self, isbn: str) -> Edition | None:
        return None

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        return None


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, object | None]] = []

    async def send(self, to: str, message: object, opts: object | None = None):
        self.sent.append((to, message, opts))
        return object()

    async def download_resource(self, *args, **kwargs):  # pragma: no cover - unused here
        return None


class FakeWishFlow:
    def __init__(self, commit_result: WishFlowResult) -> None:
        self.commit_result = commit_result
        self.commit_calls: list[str] = []
        self.preflight_calls: list[str] = []

    def preflight(self, subject_id: str) -> WishFlowResult:  # pragma: no cover - fast path uses commit()
        self.preflight_calls.append(subject_id)
        return self.commit_result

    def commit(self, subject_id: str) -> WishFlowResult:
        self.commit_calls.append(subject_id)
        return self.commit_result


class FakeWeReadLookup:
    def __init__(self) -> None:
        self.calls: list[Edition] = []

    def lookup(self, source_edition: Edition):
        self.calls.append(source_edition)
        return SimpleNamespace(message="✅ 微信读书：有同版可读")


def _run(channel, service, message, *, wish_flow=None, weread_lookup=None, store=None) -> None:
    asyncio.run(
        _handle_message(
            channel,
            service,
            message,
            candidate_store=store or CandidateSelectionStore(),
            weread_lookup=weread_lookup,
            wish_flow=wish_flow,
        )
    )


def _message(text: str, *, chat_id: str = "oc_chat", message_id: str = "om_msg") -> SimpleNamespace:
    return SimpleNamespace(
        chat_id=chat_id,
        message_id=message_id,
        content_text=text,
        raw_content_type="text",
        resources=(),
    )


class ExplicitTextFastPathTests(unittest.TestCase):
    def test_unique_exact_candidate_skips_confirmation_and_runs_wish_flow(self) -> None:
        edition = Edition(title="变量", authors=["何帆"], douban_id="30171723")
        provider = FakeDouban({"变量": [edition]})
        service = BookInboxService(provider)
        wish_flow = FakeWishFlow(
            WishFlowResult(
                kind=WishFlowKind.WRITTEN,
                subject_id="30171723",
                title="变量",
                message="《变量》已加入豆瓣想读，并完成写后验证。",
                decision=SimpleNamespace(target=edition),
            )
        )
        lookup = FakeWeReadLookup()
        channel = FakeChannel()

        _run(channel, service, _message("变量"), wish_flow=wish_flow, weread_lookup=lookup)

        # Exactly one outgoing message: no "你想加入的是这本吗？" confirmation card.
        self.assertEqual(len(channel.sent), 1)
        _, payload, _opts = channel.sent[0]
        self.assertNotIn("card", payload)
        self.assertIn("已加入豆瓣想读", payload["text"])
        self.assertIn("微信读书", payload["text"])

        # The existing DoubanWishFlow write path was reused as-is, once.
        self.assertEqual(wish_flow.commit_calls, ["30171723"])
        self.assertEqual(wish_flow.preflight_calls, [])
        # And the existing WeRead lookup ran on the resolved candidate.
        self.assertEqual(lookup.calls, [edition])

    def test_already_wish_returns_existing_state_and_weread_in_one_message(self) -> None:
        edition = Edition(title="变量", authors=["何帆"], douban_id="30171723")
        provider = FakeDouban({"变量": [edition]})
        service = BookInboxService(provider)
        wish_flow = FakeWishFlow(
            WishFlowResult(
                kind=WishFlowKind.ALREADY_WISH,
                subject_id="30171723",
                title="变量",
                message="《变量》已经在豆瓣标记为想读，不需要重复添加。",
                decision=SimpleNamespace(target=edition),
            )
        )
        lookup = FakeWeReadLookup()
        channel = FakeChannel()

        _run(channel, service, _message("变量"), wish_flow=wish_flow, weread_lookup=lookup)

        self.assertEqual(len(channel.sent), 1)
        text = channel.sent[0][1]["text"]
        self.assertIn("已经在豆瓣标记为想读", text)
        self.assertIn("微信读书", text)
        self.assertEqual(lookup.calls, [edition])

    def test_already_reading_or_read_is_not_downgraded(self) -> None:
        edition = Edition(title="变量", authors=["何帆"], douban_id="30171723")
        provider = FakeDouban({"变量": [edition]})
        service = BookInboxService(provider)
        wish_flow = FakeWishFlow(
            WishFlowResult(
                kind=WishFlowKind.BLOCKED,
                subject_id="30171723",
                title="变量",
                message=(
                    "《变量》暂时不能安全加入豆瓣想读。"
                    "需要先处理已有阅读状态或版本关系："
                    "The selected edition is already marked reading; do not downgrade it to Want-to-Read."
                ),
                decision=SimpleNamespace(target=edition),
            )
        )
        lookup = FakeWeReadLookup()
        channel = FakeChannel()

        _run(channel, service, _message("变量"), wish_flow=wish_flow, weread_lookup=lookup)

        # A single reply, the existing write path called exactly once, and no
        # second write attempt of any kind (commit() itself never downgrades
        # an existing 在读/读过 state — see DoubanWishFlow.preflight()).
        self.assertEqual(len(channel.sent), 1)
        self.assertEqual(wish_flow.commit_calls, ["30171723"])
        self.assertIn("已有阅读状态", channel.sent[0][1]["text"])

    def test_subtitle_candidate_is_not_an_exact_match_and_keeps_confirmation(self) -> None:
        edition = Edition(title="变量：如何应对不确定的未来", authors=["何帆"], douban_id="30469449")
        provider = FakeDouban({"变量": [edition]})
        service = BookInboxService(provider)
        wish_flow = FakeWishFlow(
            WishFlowResult(kind=WishFlowKind.WRITTEN, subject_id="30469449", title=edition.title, message="written")
        )
        channel = FakeChannel()

        _run(channel, service, _message("变量"), wish_flow=wish_flow)

        self.assertEqual(len(channel.sent), 1)
        self.assertIn("card", channel.sent[0][1])
        self.assertEqual(wish_flow.commit_calls, [])

    def test_multiple_candidates_do_not_enter_fast_path(self) -> None:
        editions = [
            Edition(title="变量", authors=["何帆"], publisher="中信出版社", douban_id="30171723"),
            Edition(title="变量", authors=["何帆"], publisher="中信出版集团", douban_id="30469999"),
        ]
        provider = FakeDouban({"变量": editions})
        service = BookInboxService(provider)
        wish_flow = FakeWishFlow(
            WishFlowResult(kind=WishFlowKind.WRITTEN, subject_id="30171723", title="变量", message="written")
        )
        channel = FakeChannel()

        _run(channel, service, _message("变量"), wish_flow=wish_flow)

        self.assertEqual(len(channel.sent), 1)
        self.assertIn("回复 1", channel.sent[0][1]["text"])
        self.assertEqual(wish_flow.commit_calls, [])

    def test_isbn_input_never_enters_the_text_fast_path(self) -> None:
        # request_from_text classifies a bare ISBN-looking string as ISBN,
        # not TEXT, so even a single exact CONFIRM result must not fast-path.
        edition = Edition(title="变量", authors=["何帆"], douban_id="30171723", isbn="9787508698175")
        provider = FakeDouban({"变量": [edition]})

        class IsbnDouban(FakeDouban):
            def search_by_isbn(self, isbn: str) -> Edition | None:
                return edition if isbn == "9787508698175" else None

        service = BookInboxService(IsbnDouban({"变量": [edition]}))
        wish_flow = FakeWishFlow(
            WishFlowResult(kind=WishFlowKind.WRITTEN, subject_id="30171723", title="变量", message="written")
        )
        channel = FakeChannel()

        _run(channel, service, _message("9787508698175"), wish_flow=wish_flow)

        self.assertEqual(len(channel.sent), 1)
        self.assertIn("card", channel.sent[0][1])
        self.assertEqual(wish_flow.commit_calls, [])

    def test_without_wish_flow_falls_back_to_confirmation_card(self) -> None:
        edition = Edition(title="变量", authors=["何帆"], douban_id="30171723")
        provider = FakeDouban({"变量": [edition]})
        service = BookInboxService(provider)
        channel = FakeChannel()

        _run(channel, service, _message("变量"), wish_flow=None)

        self.assertEqual(len(channel.sent), 1)
        self.assertIn("card", channel.sent[0][1])


if __name__ == "__main__":
    unittest.main()
