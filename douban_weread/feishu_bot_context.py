from __future__ import annotations

import asyncio
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
    return {
        "toast": {"type": "info", "content": "已返回版本列表。"},
        "card": {
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
        },
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
    channel = channel_factory(app_id, app_secret)
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
                "card": base._processing_card(action),
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
