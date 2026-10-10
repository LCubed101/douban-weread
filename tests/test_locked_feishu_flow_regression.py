from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from douban_weread.core.models import Edition
from douban_weread.feishu_bot import CandidateSelectionStore
from douban_weread.feishu_multi_image import mentions_from_message


class _Channel:
    async def download_resource(self, *args, **kwargs):
        raise AssertionError("Plain-text book lists must not download images")


class LockedFlowRegressionTests(unittest.TestCase):
    def test_plain_number_chooses_newest_pending_book(self):
        store = CandidateSelectionStore()
        first = Edition(title="君幸食", douban_id="1")
        latest = Edition(title="梦游书", douban_id="2")
        store.set("chat", [first], title="君幸食")
        store.set("chat", [latest], title="梦游书")
        self.assertEqual(store.get("chat"), (latest,))
        store.clear("chat", title="梦游书")
        self.assertEqual(store.get("chat"), (first,))

    def test_quoted_message_preserves_older_book_choice(self):
        store = CandidateSelectionStore()
        first = Edition(title="君幸食", douban_id="1")
        latest = Edition(title="梦游书", douban_id="2")
        store.set("chat", [first], title="君幸食")
        store.bind_message("chat", "bot-first", "君幸食", [first])
        store.set("chat", [latest], title="梦游书")
        self.assertEqual(store.get_for_reply("chat", "bot-first"), (first,))
        self.assertEqual(store.get("chat"), (latest,))

    def test_douban_punctuation_retry_recovers_verified_title(self):
        from douban_weread.inbox import BookInboxService, BookInboxResolutionKind, request_from_text

        class Catalog:
            def __init__(self):
                self.queries = []

            def search_by_title(self, title, *, count=5):
                self.queries.append(title)
                if title == "重启人生就从今日晚餐开始！":
                    return [Edition(
                        title=title, authors=["角田光代"],
                        isbn="9787549645091", douban_id="37325638",
                    )]
                return []

        provider = Catalog()
        result = BookInboxService(provider).resolve(
            request_from_text("重启人生就从今日晚餐开始")
        )
        self.assertEqual(result.kind, BookInboxResolutionKind.CONFIRM)
        self.assertEqual(result.confirmation.candidate.douban_id, "37325638")
        self.assertEqual(provider.queries, [
            "重启人生就从今日晚餐开始",
            "重启人生就从今日晚餐开始！",
        ])

    def test_unquoted_multiline_books_are_independent(self):
        titles = [
            "落在我身上的雨",
            "路上观察学入门",
            "球形的荒野",
            "君幸食",
            "重启人生就从今日晚餐开始",
            "梦游书",
            "热水用完了",
            "问题还没想明白",
        ]
        message = SimpleNamespace(
            raw_content_type="text",
            content_text="\n".join(titles),
            resources=(),
            message_id="msg-1",
        )
        result = asyncio.run(mentions_from_message(_Channel(), message, None))
        self.assertEqual([item.title for item in result], titles)


if __name__ == "__main__":
    unittest.main()
