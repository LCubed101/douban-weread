from __future__ import annotations

import unittest
from types import SimpleNamespace

from douban_weread.feishu_movie_router import FeishuMovieRouter
from douban_weread.movie_router import MovieResolveKind, MovieResolveResult
from douban_weread.providers.douban.movie import DoubanMovieCandidate


def movie(movie_id="35426925", title="机器人之梦", year="2023"):
    return DoubanMovieCandidate(
        douban_id=movie_id,
        title=title,
        year=year,
        media_type="movie",
        directors=(),
        actors=(),
        genres=(),
        aliases=(),
        subject_url=f"https://movie.douban.com/subject/{movie_id}/",
    )


class FakeResolver:
    def __init__(self, result):
        self.result = result

    def resolve(self, title):
        return self.result


class FakeInterest:
    def __init__(self):
        self.writes = []

    def mark_want_to_watch(self, subject_id, *, confirmed=False):
        self.writes.append((subject_id, confirmed))
        return SimpleNamespace(verified=True, actual_status="wish")


class FakeBookService:
    def __init__(self, exact=False):
        self.exact = exact

    def resolve(self, request):
        if not self.exact:
            return SimpleNamespace(kind=SimpleNamespace(), confirmation=None, candidates=())
        candidate = SimpleNamespace(title=request.search_query)
        return SimpleNamespace(
            kind=__import__("douban_weread.inbox", fromlist=["BookInboxResolutionKind"]).BookInboxResolutionKind.CONFIRM,
            confirmation=SimpleNamespace(candidate=candidate),
            candidates=(candidate,),
        )


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, to, message, opts=None):
        self.sent.append((to, message, opts))


class FeishuMovieRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_unique_movie_text_writes_want_to_watch(self):
        item = movie()
        resolver = FakeResolver(MovieResolveResult(MovieResolveKind.EXACT, item.title, item, (item,)))
        interest = FakeInterest()
        router = FeishuMovieRouter(resolver, interest, FakeBookService(False))
        channel = FakeChannel()
        message = SimpleNamespace(raw_content_type="text", content_text="机器人之梦", chat_id="c1", message_id="m1")

        handled = await router.try_handle_message(channel, message, recognizer=None)

        self.assertTrue(handled)
        self.assertEqual(interest.writes, [("35426925", True)])
        self.assertEqual(channel.sent[0][1]["card"]["header"]["title"]["content"], "✅ 已加入豆瓣想看")

    async def test_same_name_book_and_movie_fails_closed(self):
        item = movie()
        resolver = FakeResolver(MovieResolveResult(MovieResolveKind.EXACT, item.title, item, (item,)))
        interest = FakeInterest()
        router = FeishuMovieRouter(resolver, interest, FakeBookService(True))
        channel = FakeChannel()
        message = SimpleNamespace(raw_content_type="text", content_text="机器人之梦", chat_id="c1", message_id="m1")

        handled = await router.try_handle_message(channel, message, recognizer=None)

        self.assertTrue(handled)
        self.assertEqual(interest.writes, [])
        self.assertIn("影视：机器人之梦", channel.sent[0][1]["text"])

    async def test_explicit_movie_prefix_bypasses_book_collision(self):
        item = movie()
        resolver = FakeResolver(MovieResolveResult(MovieResolveKind.EXACT, item.title, item, (item,)))
        interest = FakeInterest()
        router = FeishuMovieRouter(resolver, interest, FakeBookService(True))
        channel = FakeChannel()
        message = SimpleNamespace(raw_content_type="text", content_text="影视：机器人之梦", chat_id="c1", message_id="m1")

        handled = await router.try_handle_message(channel, message, recognizer=None)

        self.assertTrue(handled)
        self.assertEqual(interest.writes, [("35426925", True)])

    async def test_ambiguous_movie_requires_selection(self):
        one = movie("1", "三体", "2023")
        two = movie("2", "三体", "2024")
        resolver = FakeResolver(MovieResolveResult(MovieResolveKind.AMBIGUOUS, "三体", None, (one, two)))
        interest = FakeInterest()
        router = FeishuMovieRouter(resolver, interest, FakeBookService(False))
        channel = FakeChannel()
        message = SimpleNamespace(raw_content_type="text", content_text="三体", chat_id="c1", message_id="m1")

        handled = await router.try_handle_message(channel, message, recognizer=None)

        self.assertTrue(handled)
        self.assertEqual(interest.writes, [])
        card = channel.sent[0][1]["card"]
        actions = [element for element in card["elements"] if element.get("tag") == "action"]
        self.assertEqual(len(actions), 2)

    async def test_movie_card_selection_is_single_confirmation(self):
        item = movie()
        resolver = FakeResolver(MovieResolveResult(MovieResolveKind.NOT_FOUND, "", None, ()))
        interest = FakeInterest()
        router = FeishuMovieRouter(resolver, interest, FakeBookService(False))
        event = SimpleNamespace(
            action=SimpleNamespace(value={"action": "confirm_movie", "movie_subject_id": item.douban_id, "movie_title": item.title})
        )

        # Use the same event accessor shape the base adapter accepts in production.
        from douban_weread import feishu_bot as base
        original = base._card_action_value
        base._card_action_value = lambda _event: event.action.value
        try:
            result = await router.handle_card_action(event)
        finally:
            base._card_action_value = original

        self.assertEqual(interest.writes, [("35426925", True)])
        self.assertEqual(result["toast"]["type"], "success")


if __name__ == "__main__":
    unittest.main()
