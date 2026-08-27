from __future__ import annotations

import asyncio
import sys

from douban_weread import feishu_bot as base
from douban_weread.adapters.feishu_ocr import FeishuOcrError, ImageTextRecognizer
from douban_weread.adapters.local_ocr import LocalImageOcr, LocalOcrError
from douban_weread.core.book_mentions import BookMention, extract_book_mentions
from douban_weread.core.models import Edition
from douban_weread.feishu_bot_context import _UiChannel
from douban_weread.feishu_bot_v11 import (
    _batch_summary_card,
    _lookup_mentions,
    _mentions_from_message,
    _waiting_list_text,
)
from douban_weread.inbox_weread import WEREAD_LOOKUP_ERRORS, WeReadEditionLookup, WeReadLookupKind
from douban_weread.inbox_weread_watch import (
    WeReadWatchStoreLike,
    default_watch_store,
    record_unavailable_watch,
)

_WAITING_LIST_COMMANDS = {"查看待上架", "等待上架", "查看等待上架", "查看等待列表", "waiting list"}


def _normalize_command(text: str) -> str:
    return " ".join(text.split()).strip("。！!？?").casefold()


def _plain_title_mentions(message: base.InboundMessageLike) -> tuple[BookMention, ...]:
    if message.raw_content_type not in {"text", "post", ""}:
        return ()
    text = " ".join(message.content_text.split()).strip()
    if not text or _normalize_command(text) in _WAITING_LIST_COMMANDS:
        return ()
    explicit = extract_book_mentions(text)
    if explicit:
        return explicit
    return (BookMention(text),)


async def _weread_only_mentions(
    channel: base.ChannelLike,
    message: base.InboundMessageLike,
    recognizer: ImageTextRecognizer,
) -> tuple[BookMention, ...]:
    if message.raw_content_type == "image":
        return await _mentions_from_message(channel, message, recognizer)
    return _plain_title_mentions(message)


async def _handle_weread_only_message(
    channel: base.ChannelLike,
    message: base.InboundMessageLike,
    recognizer: ImageTextRecognizer,
    lookup: base.WeReadLookupLike,
    watch_store: WeReadWatchStoreLike,
) -> None:
    if message.raw_content_type in {"text", "post", ""}:
        if _normalize_command(message.content_text) in _WAITING_LIST_COMMANDS:
            await channel.send(
                message.chat_id,
                {"text": _waiting_list_text(watch_store, chat_id=message.chat_id)},
                {"reply_to": message.message_id},
            )
            return

    mentions = await _weread_only_mentions(channel, message, recognizer)
    if not mentions:
        if message.raw_content_type == "image":
            await channel.send(
                message.chat_id,
                {
                    "text": (
                        "这张图里暂时没有识别到明确的《书名》。\n"
                        "可以换一张包含书名号的书单截图，或直接发送书名。"
                    )
                },
                {"reply_to": message.message_id},
            )
            return
        await channel.send(
            message.chat_id,
            {"text": "直接发送书名，或发送包含《书名》的书单截图即可。"},
            {"reply_to": message.message_id},
        )
        return

    outcomes = await _lookup_mentions(mentions, lookup)
    for mention, result, error in outcomes:
        if error is not None or result is None:
            continue
        kind = getattr(result, "kind", None)
        if kind in {WeReadLookupKind.UNAVAILABLE, WeReadLookupKind.NOT_FOUND}:
            record_unavailable_watch(
                chat_id=message.chat_id,
                source=Edition(title=mention.title),
                result=result,
                store=watch_store,
            )

    await channel.send(
        message.chat_id,
        {
            "card": _batch_summary_card(
                mentions=mentions,
                outcomes=outcomes,
                chat_id=message.chat_id,
                watch_store=watch_store,
            )
        },
        {"reply_to": message.message_id},
    )


def build_weread_only_bot(
    *,
    channel_factory: base.ChannelFactory = base._default_channel_factory,
    image_recognizer: ImageTextRecognizer | None = None,
    weread_lookup: base.WeReadLookupLike | None = None,
    weread_watch_store: WeReadWatchStoreLike | None = None,
) -> base.ChannelLike:
    app_id, app_secret = base._credentials()
    raw_channel = channel_factory(app_id, app_secret)
    channel = _UiChannel(raw_channel)
    recognizer = image_recognizer or LocalImageOcr()
    lookup = weread_lookup or WeReadEditionLookup()
    watch_store = weread_watch_store or default_watch_store()

    async def on_message(message: base.InboundMessageLike) -> None:
        try:
            await _handle_weread_only_message(channel, message, recognizer, lookup, watch_store)
        except (FeishuOcrError, LocalOcrError, *WEREAD_LOOKUP_ERRORS) as exc:
            print(f"WeRead-only message handling error: {type(exc).__name__}", file=sys.stderr)
            await channel.send(
                message.chat_id,
                {"text": "这条消息暂时无法查询微信读书，请稍后再试。"},
                {"reply_to": message.message_id},
            )
        except Exception as exc:
            print(f"WeRead-only message handling error: {type(exc).__name__}", file=sys.stderr)
            await channel.send(
                message.chat_id,
                {"text": "这条消息暂时无法安全处理，请稍后再试。"},
                {"reply_to": message.message_id},
            )

    async def on_card_action(event: object):
        value = base._card_action_value(event)
        action = str(value.get("action") or "").strip()
        chat_id = base._card_event_text(event, "chat_id")
        if action == "show_waiting_list":
            if chat_id:
                await channel.send(chat_id, {"text": _waiting_list_text(watch_store, chat_id=chat_id)})
                return {"toast": {"type": "success", "content": "已打开等待列表。"}}
            return {"toast": {"type": "error", "content": "缺少会话信息，无法查看等待列表。"}}
        return {"toast": {"type": "info", "content": "这个模式只处理微信读书查询。"}}

    async def on_error(error: object) -> None:
        print(f"Feishu channel error: {type(error).__name__}", file=sys.stderr)

    channel.on("message", on_message)
    channel.on("cardAction", on_card_action)
    channel.on("error", on_error)
    return channel
