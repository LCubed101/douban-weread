from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from douban_weread import feishu_bot as base
from douban_weread.feishu_multi_image import mentions_from_message
from douban_weread.inbox import BookInboxResolutionKind, BookInboxService, request_from_text
from douban_weread.movie_router import DoubanMovieResolver, MovieResolveKind
from douban_weread.providers.douban import DoubanBookSearchClient
from douban_weread.providers.douban.movie_interest import DoubanMovieInterestClient

_MOVIE_PREFIX_RE = re.compile(r"^(?:电影|影视|剧集|纪录片|想看)\s*[:：]?\s*(.+)$", re.IGNORECASE)
_BARE_MOVIE_WORDS = {"电影", "影视", "剧集", "纪录片", "想看"}


def _norm(value: str | None) -> str:
    return re.sub(r"[\W_]+", "", str(value or "")).casefold()


def _exact_book_candidates(service: BookInboxService, title: str) -> tuple[object, ...]:
    resolution = service.resolve(request_from_text(title))
    if resolution.kind is BookInboxResolutionKind.CONFIRM:
        candidate = getattr(getattr(resolution, "confirmation", None), "candidate", None)
        if candidate is not None and _norm(getattr(candidate, "title", None)) == _norm(title):
            return (candidate,)
        return ()
    if resolution.kind is BookInboxResolutionKind.MULTIPLE_CANDIDATES:
        return tuple(
            candidate
            for candidate in resolution.candidates
            if _norm(getattr(candidate, "title", None)) == _norm(title)
        )
    return ()


def _movie_result_card(title: str, *, count: int = 1) -> dict[str, object]:
    content = f"🎬 **{count} 部影视**\n豆瓣：✅ 想看 {count}/{count}"
    if count == 1:
        content += f"\n\n《{title}》"
    return {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {
            "title": {"tag": "plain_text", "content": "✅ 已加入豆瓣想看"},
            "template": "green",
        },
        "elements": [{"tag": "markdown", "content": content}],
    }


def _movie_batch_card(titles: list[str]) -> dict[str, object]:
    lines = [f"🎬 **{len(titles)} 部影视**", f"豆瓣：✅ 想看 {len(titles)}/{len(titles)}", ""]
    lines.extend(f"《{title}》" for title in titles)
    return {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {
            "title": {"tag": "plain_text", "content": "影视已处理"},
            "template": "green",
        },
        "elements": [{"tag": "markdown", "content": "\n".join(lines)}],
    }


def _ambiguous_movie_card(query: str, candidates) -> dict[str, object]:
    elements: list[dict[str, object]] = [
        {"tag": "markdown", "content": f"《{query}》有多个豆瓣影视条目，请选一个："}
    ]
    for index, item in enumerate(candidates, start=1):
        details = " · ".join(x for x in (item.year, item.media_type, " / ".join(item.directors)) if x)
        label = f"{index}. {item.title}" + (f" · {details}" if details else "")
        elements.append({"tag": "markdown", "content": label})
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": f"选择 {index}"},
                        "type": "primary",
                        "value": {
                            "action": "confirm_movie",
                            "movie_subject_id": item.douban_id,
                            "movie_title": item.title,
                        },
                    }
                ],
            }
        )
    return {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {"title": {"tag": "plain_text", "content": "确认影视条目"}, "template": "blue"},
        "elements": elements,
    }


def _book_edition_card(query: str, candidates) -> dict[str, object]:
    elements: list[dict[str, object]] = [
        {"tag": "markdown", "content": f"📚 《{query}》有多个豆瓣图书版本，请选一个。选择后直接加入想读："}
    ]
    for index, item in enumerate(candidates, start=1):
        details = " · ".join(
            value
            for value in (
                "、".join(getattr(item, "authors", ()) or ()),
                str(getattr(item, "publisher", "") or "").strip(),
                str(getattr(item, "publish_date", "") or "").strip(),
                str(getattr(item, "isbn", "") or "").strip(),
            )
            if value
        )
        elements.append(
            {
                "tag": "markdown",
                "content": f"{index}. {getattr(item, 'title', query)}" + (f" · {details}" if details else ""),
            }
        )
        subject_id = str(getattr(item, "douban_id", "") or "").strip()
        if subject_id:
            elements.append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": f"选择 {index}"},
                            "type": "primary",
                            "value": {"action": "confirm_wish", "douban_subject_id": subject_id},
                        }
                    ],
                }
            )
    return {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {"title": {"tag": "plain_text", "content": "选择豆瓣图书版本"}, "template": "blue"},
        "elements": elements,
    }


def _media_or_book_card(query: str, movie_result, book_candidates) -> dict[str, object]:
    movie_action: dict[str, object]
    if movie_result.kind is MovieResolveKind.EXACT and movie_result.selected is not None:
        item = movie_result.selected
        movie_action = {
            "action": "confirm_movie",
            "movie_subject_id": item.douban_id,
            "movie_title": item.title,
        }
    else:
        movie_action = {"action": "choose_movie_editions", "movie_title": query}

    book_actions: dict[str, object]
    if len(book_candidates) == 1:
        subject_id = str(getattr(book_candidates[0], "douban_id", "") or "").strip()
        book_actions = (
            {"action": "confirm_wish", "douban_subject_id": subject_id}
            if subject_id
            else {"action": "choose_book_editions", "book_title": query}
        )
    else:
        book_actions = {"action": "choose_book_editions", "book_title": query}

    movie_label = "🎬 影视"
    if movie_result.kind is MovieResolveKind.EXACT and movie_result.selected is not None:
        year = str(movie_result.selected.year or "").strip()
        if year:
            movie_label += f" · {year}"

    return {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {
            "title": {"tag": "plain_text", "content": "这是图书还是影视？"},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": f"《{query}》同时匹配到豆瓣图书和影视。**不用重新输入，直接选一个：**",
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": movie_label},
                        "type": "primary",
                        "value": movie_action,
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📚 图书"},
                        "type": "default",
                        "value": book_actions,
                    },
                ],
            },
        ],
    }


@dataclass(slots=True)
class FeishuMovieRouter:
    resolver: DoubanMovieResolver
    interest: DoubanMovieInterestClient
    book_service: BookInboxService

    @classmethod
    def default(cls) -> "FeishuMovieRouter":
        return cls(
            resolver=DoubanMovieResolver(),
            interest=DoubanMovieInterestClient(),
            book_service=BookInboxService(DoubanBookSearchClient(), search_limit=5),
        )

    async def _resolve(self, title: str):
        return await asyncio.to_thread(self.resolver.resolve, title)

    async def _book_candidates(self, title: str) -> tuple[object, ...]:
        return await asyncio.to_thread(_exact_book_candidates, self.book_service, title)

    async def _write(self, subject_id: str):
        return await asyncio.to_thread(self.interest.mark_want_to_watch, subject_id, confirmed=True)

    async def try_handle_message(self, channel: base.ChannelLike, message: base.InboundMessageLike, recognizer) -> bool:
        if message.raw_content_type in {"text", ""}:
            raw = " ".join(message.content_text.split()).strip()
            if not raw:
                return False
            if raw in _BARE_MOVIE_WORDS:
                await channel.send(
                    message.chat_id,
                    {"text": "直接发片名即可；如果同时匹配到图书和影视，我会给你两个按钮选择，不用再输入“影视”。"},
                    {"reply_to": message.message_id},
                )
                return True

            prefix_match = _MOVIE_PREFIX_RE.match(raw)
            forced_movie = prefix_match is not None
            query = prefix_match.group(1).strip() if prefix_match else raw
            if not query:
                return False

            movie = await self._resolve(query)
            if movie.kind is MovieResolveKind.NOT_FOUND:
                return False if not forced_movie else await self._send_not_found(channel, message, query)

            book_candidates = () if forced_movie else await self._book_candidates(query)
            if book_candidates:
                await channel.send(
                    message.chat_id,
                    {"card": _media_or_book_card(query, movie, book_candidates)},
                    {"reply_to": message.message_id},
                )
                return True

            if movie.kind is MovieResolveKind.AMBIGUOUS:
                await channel.send(
                    message.chat_id,
                    {"card": _ambiguous_movie_card(query, movie.candidates)},
                    {"reply_to": message.message_id},
                )
                return True

            item = movie.selected
            if item is None:
                return False
            await self._write(item.douban_id)
            await channel.send(
                message.chat_id,
                {"card": _movie_result_card(item.title)},
                {"reply_to": message.message_id},
            )
            return True

        if message.raw_content_type in {"image", "post"}:
            mentions = await mentions_from_message(channel, message, recognizer)
            if not mentions:
                return False

            classifications = []
            for mention in mentions:
                movie = await self._resolve(mention.title)
                book_candidates = await self._book_candidates(mention.title)
                classifications.append((mention, movie, bool(book_candidates)))

            movie_only = [
                (mention, movie)
                for mention, movie, book_exact in classifications
                if not book_exact and movie.kind is MovieResolveKind.EXACT and movie.selected is not None
            ]
            non_movie = [item for item in classifications if item[2] or item[1].kind is not MovieResolveKind.EXACT]

            if not movie_only:
                return False
            if non_movie:
                await channel.send(
                    message.chat_id,
                    {"text": "这张截图里同时有书和影视/存在同名歧义。V1.2 暂不自动混合写入，请把影视单独发一张，避免写错豆瓣状态。"},
                    {"reply_to": message.message_id},
                )
                return True

            titles: list[str] = []
            for _mention, movie in movie_only:
                item = movie.selected
                assert item is not None
                await self._write(item.douban_id)
                titles.append(item.title)

            await channel.send(
                message.chat_id,
                {"card": _movie_batch_card(titles)},
                {"reply_to": message.message_id},
            )
            return True

        return False

    async def _send_not_found(self, channel, message, query: str) -> bool:
        await channel.send(
            message.chat_id,
            {"text": f"没有安全匹配到《{query}》的豆瓣影视条目，未修改豆瓣。"},
            {"reply_to": message.message_id},
        )
        return True

    async def handle_card_action(self, event: object):
        value = base._card_action_value(event)
        action = str(value.get("action") or "").strip()

        if action == "choose_movie_editions":
            title = str(value.get("movie_title") or "").strip()
            if not title:
                return {"toast": {"type": "error", "content": "缺少影视标题，未执行。"}}
            result = await self._resolve(title)
            if result.kind is MovieResolveKind.EXACT and result.selected is not None:
                await self._write(result.selected.douban_id)
                return {
                    "toast": {"type": "success", "content": "已加入豆瓣想看。"},
                    "card": _movie_result_card(result.selected.title),
                }
            if result.kind is MovieResolveKind.AMBIGUOUS:
                return {
                    "toast": {"type": "info", "content": "请选择具体影视版本。"},
                    "card": _ambiguous_movie_card(title, result.candidates),
                }
            return {"toast": {"type": "warning", "content": "没有安全匹配到影视条目，未修改豆瓣。"}}

        if action == "choose_book_editions":
            title = str(value.get("book_title") or "").strip()
            if not title:
                return {"toast": {"type": "error", "content": "缺少图书标题，未执行。"}}
            candidates = await self._book_candidates(title)
            if not candidates:
                return {"toast": {"type": "warning", "content": "没有安全匹配到豆瓣图书版本，未修改豆瓣。"}}
            return {
                "toast": {"type": "info", "content": "请选择具体图书版本。"},
                "card": _book_edition_card(title, candidates),
            }

        if action != "confirm_movie":
            return None

        subject_id = str(value.get("movie_subject_id") or "").strip()
        title = str(value.get("movie_title") or "").strip()
        if not subject_id:
            return {"toast": {"type": "error", "content": "缺少豆瓣影视条目 ID，未执行。"}}
        await self._write(subject_id)
        return {
            "toast": {"type": "success", "content": "已加入豆瓣想看。"},
            "card": _movie_result_card(title or "这部影视"),
        }
