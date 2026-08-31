from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from douban_weread.feishu_mixed_router import MixedCaptureRouter, _BookOutcome
from douban_weread.inbox_weread import WeReadLookupKind
from douban_weread.movie_router import MovieResolveKind


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, to, message, opts=None):
        self.sent.append((to, message, opts))


class FakeMovieRouter:
    def __init__(self, *, movie_titles, book_titles):
        self.movie_titles = set(movie_titles)
        self.book_titles = set(book_titles)
        self.writes = []
        self.book_service = SimpleNamespace()

    async def _resolve(self, title):
        if title in self.movie_titles:
            return SimpleNamespace(
                kind=MovieResolveKind.EXACT,
                selected=SimpleNamespace(douban_id=f"movie-{title}", title=title),
                candidates=(),
            )
        return SimpleNamespace(kind=MovieResolveKind.NOT_FOUND, selected=None, candidates=())

    async def _book_candidates(self, title):
        if title in self.book_titles:
            return (SimpleNamespace(douban_id=f"book-{title}", title=title),)
        return ()

    async def _write(self, subject_id):
        self.writes.append(subject_id)


class MixedCaptureRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_book_and_one_movie_are_processed_together(self):
        movie_router = FakeMovieRouter(movie_titles={"机器人之梦"}, book_titles={"深度工作"})
        router = MixedCaptureRouter(
            movie_router=movie_router,
            book_flow=SimpleNamespace(),
            weread_lookup=SimpleNamespace(),
            watch_store=SimpleNamespace(),
        )
        channel = FakeChannel()
        message = SimpleNamespace(
            raw_content_type="image",
            chat_id="oc_chat",
            message_id="om_msg",
        )
        mentions = (
            SimpleNamespace(title="深度工作"),
            SimpleNamespace(title="机器人之梦"),
        )
        weread = SimpleNamespace(kind=WeReadLookupKind.EXACT, deep_link="https://weread.qq.com/x")

        with patch(
            "douban_weread.feishu_mixed_router.mentions_from_message",
            new=AsyncMock(return_value=mentions),
        ), patch.object(
            MixedCaptureRouter,
            "_sync_book",
            new=AsyncMock(return_value=_BookOutcome("深度工作", "written")),
        ), patch(
            "douban_weread.feishu_mixed_router.v11._lookup_mentions",
            new=AsyncMock(return_value=((mentions[0], weread, None),)),
        ), patch(
            "douban_weread.feishu_mixed_router.record_unavailable_watch",
        ):
            handled = await router.try_handle_message(channel, message, SimpleNamespace())

        self.assertTrue(handled)
        self.assertEqual(movie_router.writes, ["movie-机器人之梦"])
        self.assertEqual(len(channel.sent), 1)
        card = channel.sent[0][1]["card"]
        self.assertEqual(card["header"]["title"]["content"], "书和影视已分别处理")
        body = "\n".join(
            element.get("content", "")
            for element in card["elements"]
            if element.get("tag") == "markdown"
        )
        self.assertIn("深度工作", body)
        self.assertIn("机器人之梦", body)

    async def test_pure_movie_capture_is_left_to_existing_movie_router(self):
        movie_router = FakeMovieRouter(movie_titles={"机器人之梦", "完美的日子"}, book_titles=set())
        router = MixedCaptureRouter(
            movie_router=movie_router,
            book_flow=SimpleNamespace(),
            weread_lookup=SimpleNamespace(),
            watch_store=SimpleNamespace(),
        )
        channel = FakeChannel()
        message = SimpleNamespace(raw_content_type="image", chat_id="oc_chat", message_id="om_msg")
        mentions = (
            SimpleNamespace(title="机器人之梦"),
            SimpleNamespace(title="完美的日子"),
        )

        with patch(
            "douban_weread.feishu_mixed_router.mentions_from_message",
            new=AsyncMock(return_value=mentions),
        ):
            handled = await router.try_handle_message(channel, message, SimpleNamespace())

        self.assertFalse(handled)
        self.assertEqual(movie_router.writes, [])
        self.assertEqual(channel.sent, [])


if __name__ == "__main__":
    unittest.main()
