from __future__ import annotations

import asyncio
import re
import sys
from typing import Any

from douban_weread import feishu_bot as base
from douban_weread.adapters.feishu_ocr import FeishuOcrError, ImageTextRecognizer
from douban_weread.adapters.local_ocr import LocalImageOcr, LocalOcrError
from douban_weread.inbox import BookInboxService
from douban_weread.inbox_weread import WeReadEditionLookup
from douban_weread.inbox_weread_watch import WeReadWatchStoreLike, default_watch_store
from douban_weread.inbox_wish import DoubanWishFlow, WISH_FLOW_ERRORS
from douban_weread.providers.douban import DoubanBookSearchClient, DoubanProviderError


_WEREAD_LINK_RE = re.compile(r"^可读链接：(?P<url>\S+)\s*$", re.MULTILINE)


def _callback_card(raw_card: dict[str, Any]) -> dict[str, Any]:
    """Wrap a raw card in Feishu's card-action callback response schema."""

    return {"type": "raw", "data": raw_card}


def _weread_link_card(text: str, deep_link: str) -> dict[str, Any]:
    cleaned = _WEREAD_LINK_RE.sub("", text).strip()
    return {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {
            "title": {"tag": "plain_text", "content": "微信读书可读版本"},
            "template": "green",
        },
        "elements": [
            {"tag": "markdown", "content": cleaned},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "打开微信读书"},
                        "type": "primary",
                        "url": deep_link,
                    }
                ],
            },
        ],
    }


def _enhance_outbound_message(message: object) -> object:
    if not isinstance(message, dict):
        return message
    text = message.get("text")
    if not isinstance(text, str):
        return message
    match = _WEREAD_LINK_RE.search(text)
    if match is None:
        return message
    return {"card": _weread_link_card(text, match.group("url"))}


class _UiChannel:
    """Delegate channel behavior while upgrading user-visible WeRead links to cards."""

    def __init__(self, inner: base.ChannelLike) -> None:
        self._inner = inner

    def on(self, event: str, handler):
        return self._inner.on(event, handler)

    async def connect(self) -> None:
        await self._inner.connect()

    async def send(self, to: str, message: object, opts: object | None = None):
        return await self._inner.send(to, _enhance_outbound_message(message), opts)

    async def download_resource(
        self,
        file_key: str,
        resource_type: str = "image",
        message_id: str | None = None,
    ):
        return await self._inner.download_resource(
            file_key,
            resource_type=resource_type,
            message_id=message_id,
        )


def _end_search_card() -> dict[str, Any]:
    return {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {
            "title": {"tag": "plain_text", "content": "当前找书会话"},
            "template": "grey",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": "如果不想继续选择当前这些版本，可以直接结束，再发送新的书名。",
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "结束本次找书"},
                        "type": "danger",
                        "value": {"action": "end_search"},
                    }
                ],
            },
        ],
    }


async def _send_end_search_control(
    channel: base.ChannelLike,
    chat_id: str,
    *,
    reply_to: str | None = None,
) -> None:
    await channel.send(
        chat_id,
        {"card": _end_search_card()},
        {"reply_to": reply_to} if reply_to else None,
    )


async def _end_search(
    candidate_store: base.CandidateSelectionStore,
    event: object,
) -> dict[str, Any]:
    chat_id = base._card_event_text(event, "chat_id")
    if chat_id:
        candidate_store.clear(chat_id)
    raw_card = {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {
            "title": {"tag": "plain_text", "content": "本次找书已结束"},
            "template": "grey",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": "✅ 已清空当前版本选择。\n现在直接发送新的书名、ISBN 或豆瓣图书链接即可。",
            }
        ],
    }
    return {
        "toast": {"type": "success", "content": "本次找书已结束。"},
        "card": _callback_card(raw_card),
    }


async def _return_to_candidates(
    channel: base.ChannelLike,
    event: object,
    candidate_store: base.CandidateSelectionStore,
    *,
    weread_lookup: base.WeReadLookupLike | None,
) -> dict[str, Any]:
    chat_id = base._card_event_text(event, "chat_id")
    message_id = base._card_event_text(event, "message_id")
    candidates = candidate_store.get(chat_id) if chat_id else ()

    if not chat_id:
        return {"toast": {"type": "error", "content": "缺少会话信息，无法返回版本列表。"}}

    if not candidates:
        await channel.send(
            chat_id,
            {"text": "这个版本已取消，但之前的候选列表已经失效。请重新发送书名、ISBN 或豆瓣图书链接。"},
            {"reply_to": message_id} if message_id else None,
        )
        return {"toast": {"type": "info", "content": "已取消这个版本。"}}

    statuses = await base._lookup_candidate_statuses(candidates, weread_lookup)
    await channel.send(
        chat_id,
        {
            "text": base._candidate_list_text(
                candidates,
                heading="不是这本，回到刚才的豆瓣版本：",
                weread_statuses=statuses,
            )
        },
        {"reply_to": message_id} if message_id else None,
    )
    await _send_end_search_control(channel, chat_id, reply_to=message_id or None)
    raw_card = {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {
            "title": {"tag": "plain_text", "content": "已取消这个版本"},
            "template": "grey",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": "↩️ 已返回上一层候选版本，请继续回复数字选择。",
            }
        ],
    }
    return {
        "toast": {"type": "info", "content": "已返回版本列表。"},
        "card": _callback_card(raw_card),
    }


def build_bot(
    *,
    channel_factory: base.ChannelFactory = base._default_channel_factory,
    inbox_service: BookInboxService | None = None,
    image_recognizer: ImageTextRecognizer | None = None,
    wish_flow: base.WishFlowLike | None = None,
    weread_lookup: base.WeReadLookupLike | None = None,
    weread_watch_store: WeReadWatchStoreLike | None = None,
) -> base.ChannelLike:
    app_id, app_secret = base._credentials()
    raw_channel = channel_factory(app_id, app_secret)
    channel = _UiChannel(raw_channel)
    service = inbox_service or BookInboxService(DoubanBookSearchClient(), search_limit=5)
    recognizer = image_recognizer or LocalImageOcr()
    flow = wish_flow or DoubanWishFlow()
    lookup = weread_lookup or WeReadEditionLookup()
    watch_store = weread_watch_store or default_watch_store()
    candidate_store = base.CandidateSelectionStore()

    async def on_message(message: base.InboundMessageLike) -> None:
        try:
            await base._handle_message(
                channel,
                service,
                message,
                image_recognizer=recognizer,
                candidate_store=candidate_store,
                weread_lookup=lookup,
            )
            text = " ".join(message.content_text.split()).strip()
            if candidate_store.get(message.chat_id) and not text.isdigit():
                await _send_end_search_control(
                    channel,
                    message.chat_id,
                    reply_to=message.message_id,
                )
        except (DoubanProviderError, FeishuOcrError, LocalOcrError) as exc:
            await channel.send(
                message.chat_id,
                {"text": f"书籍识别暂时失败：{exc}"},
                {"reply_to": message.message_id},
            )
        except Exception as exc:
            print(f"Feishu message handling error: {type(exc).__name__}", file=sys.stderr)
            await channel.send(
                message.chat_id,
                {"text": "这条消息暂时无法安全处理，请稍后再试。"},
                {"reply_to": message.message_id},
            )

    async def on_card_action(event: object):
        value = base._card_action_value(event)
        action = str(value.get("action") or "").strip()
        chat_id = base._card_event_text(event, "chat_id")
        subject_id = str(value.get("douban_subject_id") or "").strip()

        if action == "end_search":
            return await _end_search(candidate_store, event)

        if action == "reject_book":
            return await _return_to_candidates(
                channel,
                event,
                candidate_store,
                weread_lookup=lookup,
            )

        if action in {"confirm_book", "confirm_wish"} and chat_id and subject_id:
            asyncio.create_task(
                base._run_card_action_after_ack(
                    channel,
                    flow,
                    event,
                    weread_lookup=lookup,
                    weread_watch_store=watch_store,
                )
            )
            return {
                "toast": {"type": "info", "content": "已收到，正在处理…"},
                "card": _callback_card(base._processing_card(action)),
            }

        try:
            return await base._handle_card_action(
                channel,
                flow,
                event,
                weread_lookup=lookup,
                weread_watch_store=watch_store,
            )
        except WISH_FLOW_ERRORS as exc:
            message_id = base._card_event_text(event, "message_id")
            if chat_id:
                await channel.send(
                    chat_id,
                    {"text": f"豆瓣想读操作未执行：{exc}"},
                    {"reply_to": message_id} if message_id else None,
                )
            return {"toast": {"type": "error", "content": "未修改豆瓣，请查看机器人回复。"}}
        except Exception as exc:
            print(f"Feishu card action error: {type(exc).__name__}", file=sys.stderr)
            return {"toast": {"type": "error", "content": "这次操作没有执行，请稍后再试。"}}

    async def on_error(error: object) -> None:
        print(f"Feishu channel error: {type(error).__name__}", file=sys.stderr)

    channel.on("message", on_message)
    channel.on("cardAction", on_card_action)
    channel.on("error", on_error)
    return channel
