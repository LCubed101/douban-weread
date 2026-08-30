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
        self.queries = []

    def resolve(self, title):
        self.queries.append(title)
        return self.result


class FakeInterest:
    def __init__(self):
        self.writes = []

    def mark_want_to_watch(self, subject_id, *, confirmed=False):
        self.writes.append((subject_id, confirmed))
        return SimpleNamespace(verified=True, actual_status="wish")


class FakeBookService:
    def __init__(self, exact=False, candidates=None):
        self.exact = exact
        self._candidates = list(candidates or [])

    def resolve(self, request):
        from douban_weread.inbox import BookInboxResolutionKind

        if self._candidates:
            if len(self._candidates) == 1:
                candidate = self._candidates[0]
                return SimpleNamespace(
                    kind=BookInboxResolutionKind.CONFIRM,
                    confirmation=SimpleNamespace(candidate=candidate),
                    candidates=(candidate,),
                )
            return SimpleNamespace(
                kind=BookInboxResolutionKind.MULTIPLE_CANDIDATES,
                confirmation=None,
                candidates=tuple(self._candidates),
            )
        if not self.exact:
            return SimpleNamespace(kind=SimpleNamespace(), confirmation=None, candidates=())
        candidate = SimpleNamespace(
            title=request.search_query,
            douban_id="book-1",
            authors=(),
            publisher=None,
            publish_date=None,
            isbn=None,
        )
        return SimpleNamespace(
            kind=BookInboxResolutionKind.CONFIRM,
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

    async def test_same_name_book_and_movie_shows_two_choice_buttons(self):
        item = movie()
        resolver = FakeResolver(MovieResolveResult(MovieResolveKind.EXACT, item.title, item, (item,)))
        interest = FakeInterest()
        router = FeishuMovieRouter(resolver, interest, FakeBookService(True))
        channel = FakeChannel()
        message = SimpleNamespace(raw_content_type="text", content_text="机器人之梦", chat_id="c1", message_id="m1")

        handled = await router.try_handle_message(channel, message, recognizer=None)

        self.assertTrue(handled)
        self.assertEqual(interest.writes, [])
        card = channel.sent[0][1]["card"]
        self.assertEqual(card["header"]["title"]["content"], "这是图书还是影视？")
        actions = card["elements"][1]["actions"]
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0]["value"]["action"], "confirm_movie")
        self.assertEqual(actions[1]["value"]["action"], "confirm_wish")
        self.assertIn("影视", actions[0]["text"]["content"])
        self.assertIn("图书", actions[1]["text"]["content"])

    async def test_bare_movie_word_is_not_sent_to_book_search(self):
        item = movie()
        resolver = FakeResolver(MovieResolveResult(MovieResolveKind.EXACT, item.title, item, (item,)))
        router = FeishuMovieRouter(resolver, FakeInterest(), FakeBookService(False))
        channel = FakeChannel()
        message = SimpleNamespace(raw_content_type="text", content_text="影视", chat_id="c1", message_id="m1")

        handled = await router.try_handle_message(channel, message, recognizer=None)

        self.assertTrue(handled)
        self.assertEqual(resolver.queries, [])
        self.assertIn("两个按钮", channel.sent[0][1]["text"])

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

    async def test_multiple_exact_book_editions_use_one_book_button_then_version_buttons(self):
        item = movie()
        books = [
            SimpleNamespace(title="机器人之梦", douban_id="b1", authors=("A",), publisher="P1", publish_date="2024", isbn=None),
            SimpleNamespace(title="机器人之梦", douban_id="b2", authors=("B",), publisher="P2", publish_date="2025", isbn=None),
        ]
        router = FeishuMovieRouter(
            FakeResolver(MovieResolveResult(MovieResolveKind.EXACT, item.title, item, (item,))),
            FakeInterest(),
            FakeBookService(candidates=books),
        )
        channel = FakeChannel()
        message = SimpleNamespace(raw_content_type="text", content_text="机器人之梦", chat_id="c1", message_id="m1")

        await router.try_handle_message(channel, message, recognizer=None)
        book_button = channel.sent[0][1]["card"]["elements"][1]["actions"][1]
        self.assertEqual(book_button["value"]["action"], "choose_book_editions")

        from douban_weread import feishu_bot as base
        event = SimpleNamespace(action=SimpleNamespace(value=book_button["value"]))
        original = base._card_action_value
        base._card_action_value = lambda _event: event.action.value
        try:
            result = await router.handle_card_action(event)
        finally:
            base._card_action_value = original

        self.assertEqual(result["card"]["header"]["title"]["content"], "选择豆瓣图书版本")
        version_actions = [e for e in result["card"]["elements"] if e.get("tag") == "action"]
        self.assertEqual(len(version_actions), 2)
        self.assertTrue(all(e["actions"][0]["value"]["action"] == "confirm_wish" for e in version_actions))

    async def test_movie_card_selection_is_single_confirmation(self):
        item = movie()
        resolver = FakeResolver(MovieResolveResult(MovieResolveKind.NOT_FOUND, "", None, ()))
        interest = FakeInterest()
        router = FeishuMovieRouter(resolver, interest, FakeBookService(False))
        event = SimpleNamespace(
            action=SimpleNamespace(value={"action": "confirm_movie", "movie_subject_id": item.douban_id, "movie_title": item.title})
        )

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
