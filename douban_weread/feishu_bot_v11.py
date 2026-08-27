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


def _watch_due_for_title(store: object, *, chat_id: str, title: str) -> str | None:
    pending_fn = getattr(store, "pending", None)
    if not callable(pending_fn):
        return None
    try:
        entries = pending_fn()
    except Exception:
        return None
    for entry in entries:
        if getattr(entry, "chat_id", None) != chat_id:
            continue
        if str(getattr(entry, "source_title", "") or "").strip() != title:
            continue
        due = str(getattr(entry, "next_check_at", "") or "")[:10]
        return due or None
    return None


def _waiting_list_text(store: object, *, chat_id: str) -> str:
    pending_fn = getattr(store, "pending", None)
    entries = pending_fn() if callable(pending_fn) else []
    entries = [entry for entry in entries if getattr(entry, "chat_id", None) == chat_id]
    if not entries:
        return "当前没有等待微信读书上架或重新搜索的书。"

    lines = [f"等待列表 · {len(entries)} 本"]
    for index, entry in enumerate(entries, start=1):
        kind = getattr(entry, "watch_kind", "not_found")
        label = "⏳ 待上架" if kind == "waiting" else "🔍 暂未找到"
        due = str(getattr(entry, "next_check_at", "") or "")[:10]
        suffix = f" · {due}" if due else ""
        lines.append(f"{index}. 《{entry.source_title}》 · {label}{suffix}")
    return "\n".join(lines)


def _selected_details(result: object) -> str | None:
    edition = getattr(result, "selected_edition", None)
    if edition is None:
        return None
    values = [
        str(getattr(edition, "title", "") or "").strip(),
        "、".join(getattr(edition, "authors", []) or []),
        str(getattr(edition, "publisher", "") or "").strip(),
        str(getattr(edition, "publish_date", "") or "").strip(),
    ]
    details = " · ".join(value for value in values if value)
    return details or None


def _batch_summary_card(
    *,
    mentions: tuple[BookMention, ...],
    outcomes: tuple[tuple[BookMention, object | None, str | None], ...],
    chat_id: str,
    watch_store: object | None,
) -> dict[str, object]:
    available: list[tuple[BookMention, object]] = []
    waiting: list[tuple[BookMention, object]] = []
    not_found: list[tuple[BookMention, object]] = []
    failed: list[tuple[BookMention, str | None]] = []

    for mention, result, error in outcomes:
        if error is not None or result is None:
            failed.append((mention, error))
            continue
        kind = getattr(result, "kind", None)
        if kind in {WeReadLookupKind.EXACT, WeReadLookupKind.ALTERNATIVE}:
            available.append((mention, result))
        elif kind is WeReadLookupKind.UNAVAILABLE:
            waiting.append((mention, result))
        elif kind is WeReadLookupKind.NOT_FOUND:
            not_found.append((mention, result))
        else:
            failed.append((mention, None))

    elements: list[dict[str, object]] = [
        {
            "tag": "markdown",
            "content": (
                f"📚 **{len(mentions)} 本** · ✅ 可读 {len(available)} · "
                f"⏳ 待上架 {len(waiting)} · 🔍 未找到 {len(not_found)}"
                + (f" · ⚠️ 失败 {len(failed)}" if failed else "")
            ),
        }
    ]

    if available:
        elements.append({"tag": "hr"})
        elements.append({"tag": "markdown", "content": "**✅ 微信读书可读**"})
        for mention, result in available:
            details = _selected_details(result)
            content = f"**《{mention.title}》**"
            if details and details != mention.title:
                content += f"\n{details}"
            elements.append({"tag": "markdown", "content": content})
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

    if waiting:
        elements.append({"tag": "hr"})
        lines = ["**⏳ 待上架**"]
        for mention, result in waiting:
            due = _watch_due_for_title(watch_store, chat_id=chat_id, title=mention.title) if watch_store else None
            suffix = f" · {due} 再查" if due else ""
            lines.append(f"《{mention.title}》{suffix}")
            deep_link = str(getattr(result, "deep_link", "") or "").strip()
            if deep_link:
                lines.append(f"[查看微信读书]({deep_link})")
        elements.append({"tag": "markdown", "content": "\n".join(lines)})

    if not_found:
        elements.append({"tag": "hr"})
        lines = [f"**🔍 已帮你记住 {len(not_found)} 本**"]
        for mention, _result in not_found:
            due = _watch_due_for_title(watch_store, chat_id=chat_id, title=mention.title) if watch_store else None
            suffix = f" · {due} 重搜" if due else ""
            lines.append(f"《{mention.title}》{suffix}")
        elements.append({"tag": "markdown", "content": "\n".join(lines)})

    if waiting or not_found:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看等待列表"},
                        "type": "default",
                        "value": {"action": "show_waiting_list"},
                    }
                ],
            }
        )

    if failed:
        elements.append({"tag": "hr"})
        lines = ["**⚠️ 本次查询失败**"]
        lines.extend(f"《{mention.title}》" for mention, _error in failed)
        lines.append("稍后重新发送即可重试。")
        elements.append({"tag": "markdown", "content": "\n".join(lines)})

    template = "green" if available else "blue"
    return {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {
            "title": {"tag": "plain_text", "content": "书单处理结果"},
            "template": template,
        },
        "elements": elements,
    }


async def _try_handle_waiting_list_command(
    channel: base.ChannelLike,
    message: base.InboundMessageLike,
    store: object,
) -> bool:
    if message.raw_content_type not in {"text", "post", ""}:
        return False
    if _normalize_command(message.content_text) not in _WAITING_LIST_COMMANDS:
        return False

    await channel.send(
        message.chat_id,
        {"text": _waiting_list_text(store, chat_id=message.chat_id)},
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
    """Handle explicit multi-book content as one summarized WeRead-first result."""

    if weread_lookup is None:
        return False

    mentions = await _mentions_from_message(channel, message, recognizer)
    if len(mentions) < 2:
        return False

    candidate_store.clear(message.chat_id)
    results = await _lookup_mentions(mentions, weread_lookup)

    for mention, result, error in results:
        if error is not None or result is None:
            continue
        kind = getattr(result, "kind", None)
        if (
            weread_watch_store is not None
            and kind in {WeReadLookupKind.UNAVAILABLE, WeReadLookupKind.NOT_FOUND}
        ):
            record_unavailable_watch(
                chat_id=message.chat_id,
                source=Edition(title=mention.title),
                result=result,
                store=weread_watch_store,
            )

    await channel.send(
        message.chat_id,
        {
            "card": _batch_summary_card(
                mentions=mentions,
                outcomes=results,
                chat_id=message.chat_id,
                watch_store=weread_watch_store,
            )
        },
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

        if action == "show_waiting_list":
            if chat_id:
                await channel.send(chat_id, {"text": _waiting_list_text(watch_store, chat_id=chat_id)})
                return {"toast": {"type": "success", "content": "已打开等待列表。"}}
            return {"toast": {"type": "error", "content": "缺少会话信息，无法查看等待列表。"}}

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