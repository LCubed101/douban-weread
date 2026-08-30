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


def _norm(value: str | None) -> str:
    return re.sub(r"[\W_]+", "", str(value or "")).casefold()


def _exact_book_exists(service: BookInboxService, title: str) -> bool:
    resolution = service.resolve(request_from_text(title))
    if resolution.kind is BookInboxResolutionKind.CONFIRM:
        candidate = getattr(getattr(resolution, "confirmation", None), "candidate", None)
        return candidate is not None and _norm(candidate.title) == _norm(title)
    if resolution.kind is BookInboxResolutionKind.MULTIPLE_CANDIDATES:
        return any(_norm(candidate.title) == _norm(title) for candidate in resolution.candidates)
    return False


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

    async def _book_exact(self, title: str) -> bool:
        return await asyncio.to_thread(_exact_book_exists, self.book_service, title)

    async def _write(self, subject_id: str):
        return await asyncio.to_thread(self.interest.mark_want_to_watch, subject_id, confirmed=True)

    async def try_handle_message(self, channel: base.ChannelLike, message: base.InboundMessageLike, recognizer) -> bool:
        if message.raw_content_type in {"text", ""}:
            raw = " ".join(message.content_text.split()).strip()
            if not raw:
                return False
            prefix_match = _MOVIE_PREFIX_RE.match(raw)
            forced_movie = prefix_match is not None
            query = prefix_match.group(1).strip() if prefix_match else raw
            if not query:
                return False

            movie = await self._resolve(query)
            if movie.kind is MovieResolveKind.NOT_FOUND:
                return False if not forced_movie else await self._send_not_found(channel, message, query)

            book_exact = False if forced_movie else await self._book_exact(query)
            if book_exact:
                await channel.send(
                    message.chat_id,
                    {"text": f"《{query}》同时存在同名图书和影视。请发送“影视：{query}”走豆瓣想看；直接发书名仍走图书流程。"},
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
                book_exact = await self._book_exact(mention.title)
                classifications.append((mention, movie, book_exact))

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
        if str(value.get("action") or "").strip() != "confirm_movie":
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
