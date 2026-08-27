from __future__ import annotations

import asyncio
import sys

from douban_weread import feishu_bot as base
from douban_weread.adapters.feishu_ocr import FeishuOcrError, ImageTextRecognizer
from douban_weread.adapters.local_ocr import LocalImageOcr, LocalOcrError
from douban_weread.core.book_mentions import BookMention, extract_book_mentions
from douban_weread.core.models import Edition
from douban_weread.feishu_bot_context import (
    _UiChannel,
    _callback_card,
    _end_search,
    _return_to_candidates,
    _send_end_search_control,
)
from douban_weread.inbox import BookInboxService
from douban_weread.inbox_weread import WEREAD_LOOKUP_ERRORS, WeReadEditionLookup, WeReadLookupKind
from douban_weread.inbox_weread_watch import (
    WeReadWatchStoreLike,
    default_watch_store,
    record_unavailable_watch,
)
from douban_weread.inbox_wish import DoubanWishFlow, WISH_FLOW_ERRORS
from douban_weread.providers.douban import DoubanBookSearchClient, DoubanProviderError

_WAITING_LIST_COMMANDS = {"查看待上架", "等待上架", "查看等待上架", "waiting list"}


async def _mentions_from_message(
    channel: base.ChannelLike,
    message: base.InboundMessageLike,
    recognizer: ImageTextRecognizer,
) -> tuple[BookMention, ...]:
    if message.raw_content_type == "image":
        file_key = base._image_resource_key(message.resources)
        if not file_key:
            return ()
        image_bytes = await channel.download_resource(
            file_key,
            resource_type="image",
            message_id=message.message_id,
        )
        if not image_bytes:
            return ()
        lines = await recognizer.recognize(bytes(image_bytes))
        return extract_book_mentions("\n".join(lines))

    if message.raw_content_type in {"text", "post", ""}:
        return extract_book_mentions(message.content_text)

    return ()


def _lookup_one_mention(weread_lookup: base.WeReadLookupLike, mention: BookMention):
    title_lookup = getattr(weread_lookup, "lookup_title", None)
    if callable(title_lookup):
        return title_lookup(mention.title)
    return weread_lookup.lookup(Edition(title=mention.title))


async def _lookup_mentions(
    mentions: tuple[BookMention, ...],
    weread_lookup: base.WeReadLookupLike,
) -> tuple[tuple[BookMention, object | None, str | None], ...]:
    semaphore = asyncio.Semaphore(3)

    async def one(mention: BookMention) -> tuple[BookMention, object | None, str | None]:
        try:
            async with semaphore:
                result = await asyncio.to_thread(
                    _lookup_one_mention,
                    weread_lookup,
                    mention,
                )
        except WEREAD_LOOKUP_ERRORS as exc:
            return mention, None, str(exc)
        return mention, result, None

    return tuple(await asyncio.gather(*(one(mention) for mention in mentions)))


def _normalize_command(text: str) -> str:
    return " ".join(text.split()).strip("。！!？?").casefold()


async def _try_handle_waiting_list_command(
    channel: base.ChannelLike,
    message: base.InboundMessageLike,
    store: object,
) -> bool:
    if message.raw_content_type not in {"text", "post", ""}:
        return False
    if _normalize_command(message.content_text) not in _WAITING_LIST_COMMANDS:
        return False

    pending_fn = getattr(store, "pending", None)
    entries = pending_fn() if callable(pending_fn) else []
    entries = [entry for entry in entries if getattr(entry, "chat_id", None) == message.chat_id]
    if not entries:
        text = "当前没有等待微信读书上架/重新搜索的书。"
    else:
        lines = [f"当前等待列表共 {len(entries)} 本："]
        for index, entry in enumerate(entries, start=1):
            kind = getattr(entry, "watch_kind", "not_found")
            label = "⏳ 待上架" if kind == "waiting" else "🔍 暂未找到"
            due = str(getattr(entry, "next_check_at", "") or "")[:10]
            suffix = f" · 下次检查 {due}" if due else ""
            lines.append(f"{index}. 《{entry.source_title}》 · {label}{suffix}")
        text = "\n".join(lines)
    await channel.send(
        message.chat_id,
        {"text": text},
        {"reply_to": message.message_id},
    )
    return True


async def _try_handle_multi_book_message(
    channel: base.ChannelLike,
    message: base.InboundMessageLike,
    recognizer: ImageTextRecognizer,
    weread_lookup: base.WeReadLookupLike | None,
    candidate_store: base.CandidateSelectionStore,
    weread_watch_store: WeReadWatchStoreLike | None = None,
) -> bool:
    """Handle explicit multi-book content as a WeRead-first V1.1 route."""

    if weread_lookup is None:
        return False

    mentions = await _mentions_from_message(channel, message, recognizer)
    if len(mentions) < 2:
        return False

    candidate_store.clear(message.chat_id)
    await channel.send(
        message.chat_id,
        {
            "text": (
                f"从这段内容里识别到 {len(mentions)} 本书，正在逐本查微信读书：\n"
                + "\n".join(f"{index}. 《{mention.title}》" for index, mention in enumerate(mentions, start=1))
            )
        },
        {"reply_to": message.message_id},
    )

    results = await _lookup_mentions(mentions, weread_lookup)
    for mention, result, error in results:
        if error is not None:
            await channel.send(
                message.chat_id,
                {"text": f"《{mention.title}》\n微信读书查询暂时失败，请稍后再试。"},
                {"reply_to": message.message_id},
            )
            continue

        result_message = str(getattr(result, "message", "") or "").strip()
        if not result_message:
            result_message = "微信读书暂未返回可用结果。"

        watch_message = None
        kind = getattr(result, "kind", None)
        if (
            weread_watch_store is not None
            and kind in {WeReadLookupKind.UNAVAILABLE, WeReadLookupKind.NOT_FOUND}
        ):
            watch_message = record_unavailable_watch(
                chat_id=message.chat_id,
                source=Edition(title=mention.title),
                result=result,
                store=weread_watch_store,
            )

        text = f"《{mention.title}》\n{result_message}"
        if watch_message:
            text = f"{text}\n{watch_message}"
        await channel.send(
            message.chat_id,
            {"text": text},
            {"reply_to": message.message_id},
        )
    return True


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
            if await _try_handle_waiting_list_command(channel, message, watch_store):
                return
            if await _try_handle_multi_book_message(
                channel,
                message,
                recognizer,
                lookup,
                candidate_store,
                watch_store,
            ):
                return

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
