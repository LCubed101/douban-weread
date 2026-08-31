from __future__ import annotations

import asyncio
from dataclasses import dataclass

from douban_weread import feishu_bot as base
from douban_weread import feishu_bot_v11 as v11
from douban_weread.core.models import Edition
from douban_weread.feishu_compact_douban import _is_same_work_existing_wish
from douban_weread.feishu_hybrid_batch import _main_title, _pick_douban_candidate
from douban_weread.feishu_movie_router import FeishuMovieRouter
from douban_weread.feishu_multi_image import mentions_from_message
from douban_weread.inbox import request_from_text
from douban_weread.inbox_weread import WeReadEditionLookup, WeReadLookupKind
from douban_weread.inbox_weread_watch import default_watch_store, record_unavailable_watch
from douban_weread.inbox_wish import DoubanWishFlow, WISH_FLOW_ERRORS, WishFlowKind
from douban_weread.movie_router import MovieResolveKind


@dataclass(slots=True)
class _BookOutcome:
    title: str
    status: str
    detail: str | None = None


@dataclass(slots=True)
class MixedCaptureRouter:
    """Route one capture containing both books and Film/TV.

    The mixed router only takes ownership when at least one mention is a safe
    book-only match and at least one mention is a safe movie-only match. Pure
    book or pure movie captures continue to the existing routers unchanged.
    Ambiguous same-title items are never guessed; they are surfaced as buttons.
    """

    movie_router: FeishuMovieRouter
    book_flow: object
    weread_lookup: object
    watch_store: object

    @classmethod
    def default(cls, movie_router: FeishuMovieRouter) -> "MixedCaptureRouter":
        return cls(
            movie_router=movie_router,
            book_flow=DoubanWishFlow(),
            weread_lookup=WeReadEditionLookup(),
            watch_store=default_watch_store(),
        )

    async def try_handle_message(self, channel: base.ChannelLike, message: base.InboundMessageLike, recognizer) -> bool:
        if message.raw_content_type not in {"image", "post"}:
            return False

        mentions = await mentions_from_message(channel, message, recognizer)
        if len(mentions) < 2:
            return False

        classified = []
        for mention in mentions:
            movie_result, book_candidates = await asyncio.gather(
                self.movie_router._resolve(mention.title),
                self.movie_router._book_candidates(mention.title),
            )
            classified.append((mention, movie_result, tuple(book_candidates)))

        movie_only = [
            (mention, movie_result)
            for mention, movie_result, book_candidates in classified
            if not book_candidates
            and movie_result.kind is MovieResolveKind.EXACT
            and movie_result.selected is not None
        ]
        book_only = [
            (mention, book_candidates)
            for mention, movie_result, book_candidates in classified
            if book_candidates and movie_result.kind is MovieResolveKind.NOT_FOUND
        ]
        ambiguous = [
            (mention, movie_result, book_candidates)
            for mention, movie_result, book_candidates in classified
            if book_candidates and movie_result.kind is not MovieResolveKind.NOT_FOUND
        ]
        unresolved = [
            mention
            for mention, movie_result, book_candidates in classified
            if not book_candidates
            and not (
                movie_result.kind is MovieResolveKind.EXACT
                and movie_result.selected is not None
            )
        ]

        # Do not steal pure-book or pure-movie captures from the existing paths.
        if not movie_only or not book_only:
            return False

        movie_titles: list[str] = []
        for _mention, movie_result in movie_only:
            selected = movie_result.selected
            assert selected is not None
            await self.movie_router._write(selected.douban_id)
            movie_titles.append(selected.title)

        book_mentions = tuple(mention for mention, _candidates in book_only)
        book_outcomes = list(
            await asyncio.gather(*(self._sync_book(mention) for mention in book_mentions))
        )
        weread_results = await v11._lookup_mentions(book_mentions, self.weread_lookup)

        for mention, result, error in weread_results:
            if error is not None or result is None:
                continue
            if getattr(result, "kind", None) in {
                WeReadLookupKind.UNAVAILABLE,
                WeReadLookupKind.NOT_FOUND,
            }:
                record_unavailable_watch(
                    chat_id=message.chat_id,
                    source=Edition(title=mention.title),
                    result=result,
                    store=self.watch_store,
                )

        card = _mixed_result_card(
            movie_titles=movie_titles,
            book_mentions=book_mentions,
            book_outcomes=book_outcomes,
            weread_results=weread_results,
            ambiguous=ambiguous,
            unresolved=unresolved,
        )
        await channel.send(
            message.chat_id,
            {"card": card},
            {"reply_to": message.message_id},
        )
        return True

    async def _sync_book(self, mention) -> _BookOutcome:
        try:
            resolution = await asyncio.to_thread(
                self.movie_router.book_service.resolve,
                request_from_text(mention.title),
            )
            candidate = _pick_douban_candidate(resolution, mention.title)
            if candidate is None:
                main_title = _main_title(mention.title)
                if main_title:
                    fallback = await asyncio.to_thread(
                        self.movie_router.book_service.resolve,
                        request_from_text(main_title),
                    )
                    candidate = _pick_douban_candidate(fallback, mention.title)
                    if candidate is None:
                        candidate = _pick_douban_candidate(fallback, main_title)

            if candidate is None:
                return _BookOutcome(mention.title, "unresolved", "没有安全匹配到豆瓣版本")
            subject_id = str(candidate.douban_id or "").strip()
            if not subject_id:
                return _BookOutcome(mention.title, "unresolved", "豆瓣条目缺少 ID")

            result = await asyncio.to_thread(self.book_flow.commit, subject_id)
            if result.kind is WishFlowKind.WRITTEN:
                return _BookOutcome(mention.title, "written")
            if result.kind is WishFlowKind.ALREADY_WISH or _is_same_work_existing_wish(result):
                return _BookOutcome(mention.title, "already")
            return _BookOutcome(mention.title, "blocked", "已有阅读状态需要确认")
        except WISH_FLOW_ERRORS:
            return _BookOutcome(mention.title, "failed", "豆瓣暂时无法写入")


def _movie_action(movie_result, title: str) -> dict[str, object]:
    if movie_result.kind is MovieResolveKind.EXACT and movie_result.selected is not None:
        return {
            "action": "confirm_movie",
            "movie_subject_id": movie_result.selected.douban_id,
            "movie_title": movie_result.selected.title,
        }
    return {"action": "choose_movie_editions", "movie_title": title}


def _book_action(book_candidates, title: str) -> dict[str, object]:
    if len(book_candidates) == 1:
        subject_id = str(getattr(book_candidates[0], "douban_id", "") or "").strip()
        if subject_id:
            return {"action": "confirm_wish", "douban_subject_id": subject_id}
    return {"action": "choose_book_editions", "book_title": title}


def _mixed_result_card(
    *,
    movie_titles: list[str],
    book_mentions,
    book_outcomes: list[_BookOutcome],
    weread_results,
    ambiguous,
    unresolved,
) -> dict[str, object]:
    book_ok = [outcome for outcome in book_outcomes if outcome.status in {"written", "already"}]
    book_attention = [outcome for outcome in book_outcomes if outcome.status not in {"written", "already"}]

    readable = []
    unavailable = []
    for mention, result, error in weread_results:
        if error is not None or result is None:
            unavailable.append((mention, None))
            continue
        kind = getattr(result, "kind", None)
        if kind in {WeReadLookupKind.EXACT, WeReadLookupKind.ALTERNATIVE}:
            readable.append((mention, result))
        else:
            unavailable.append((mention, result))

    elements: list[dict[str, object]] = [
        {
            "tag": "markdown",
            "content": (
                f"📚 **{len(book_mentions)} 本书** · 豆瓣 ✅ 想读 {len(book_ok)}/{len(book_mentions)} · "
                f"微信读书 ✅ 可读 {len(readable)}\n"
                f"🎬 **{len(movie_titles)} 部影视** · 豆瓣 ✅ 想看 {len(movie_titles)}/{len(movie_titles)}"
            ),
        }
    ]

    if movie_titles:
        elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "markdown",
                "content": "**🎬 已加入豆瓣想看**\n" + "\n".join(f"《{title}》" for title in movie_titles),
            }
        )

    if book_mentions:
        elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "markdown",
                "content": "**📚 图书**\n" + "\n".join(f"《{mention.title}》" for mention in book_mentions),
            }
        )

    if readable:
        elements.append({"tag": "markdown", "content": "**✅ 微信读书可读**"})
        for mention, result in readable:
            deep_link = str(getattr(result, "deep_link", "") or "").strip()
            if deep_link:
                elements.append(
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": f"打开《{mention.title}》"},
                                "type": "primary",
                                "url": deep_link,
                            }
                        ],
                    }
                )

    if unavailable:
        elements.append(
            {
                "tag": "markdown",
                "content": (
                    "**🔍 微信读书暂时没有**\n"
                    + "、".join(f"《{mention.title}》" for mention, _result in unavailable)
                    + "\n已帮你记住，之后会自动重搜。"
                ),
            }
        )

    if book_attention:
        elements.append({"tag": "hr"})
        lines = ["**⚠️ 豆瓣图书未完成**"]
        for outcome in book_attention:
            suffix = f" · {outcome.detail}" if outcome.detail else ""
            lines.append(f"《{outcome.title}》{suffix}")
        elements.append({"tag": "markdown", "content": "\n".join(lines)})

    if ambiguous:
        elements.append({"tag": "hr"})
        elements.append({"tag": "markdown", "content": "**需要你确认：图书还是影视？**"})
        for mention, movie_result, book_candidates in ambiguous:
            elements.append({"tag": "markdown", "content": f"《{mention.title}》"})
            elements.append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🎬 影视"},
                            "type": "primary",
                            "value": _movie_action(movie_result, mention.title),
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📚 图书"},
                            "type": "default",
                            "value": _book_action(book_candidates, mention.title),
                        },
                    ],
                }
            )

    if unresolved:
        elements.append({"tag": "hr"})
        elements.append(
            {
                "tag": "markdown",
                "content": "**⚠️ 暂未安全识别**\n" + "、".join(f"《{mention.title}》" for mention in unresolved),
            }
        )

    return {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {
            "title": {"tag": "plain_text", "content": "书和影视已分别处理"},
            "template": "green",
        },
        "elements": elements,
    }
