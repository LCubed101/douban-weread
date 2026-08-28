from __future__ import annotations

import asyncio
from typing import Any

from douban_weread import feishu_bot as base
from douban_weread.inbox_weread import WeReadEditionLookup
from douban_weread.inbox_weread_watch import default_watch_store
from douban_weread.inbox_wish import DoubanWishFlow, WISH_FLOW_ERRORS, WishFlowKind

_ORIGINAL_CANDIDATE_HANDLER = base._maybe_handle_candidate_number
_ORIGINAL_CARD_HANDLER = base._handle_card_action
_PREPARED = False


def _is_same_work_existing_wish(result: object) -> bool:
    decision = getattr(result, "decision", None)
    reason = str(getattr(decision, "reason", "") or "").casefold()
    return "same work" in reason and "already marked want-to-read" in reason


def _selected_edition_from_result(result: object):
    decision = getattr(result, "decision", None)
    return getattr(decision, "target", None)


def _compact_base_text(result: object) -> str:
    title = str(getattr(result, "title", "") or "这本书")
    kind = getattr(result, "kind", None)
    if kind is WishFlowKind.WRITTEN:
        return f"✅《{title}》已加入豆瓣想读。"
    if kind is WishFlowKind.ALREADY_WISH:
        return f"✅《{title}》豆瓣已经是想读。"
    if _is_same_work_existing_wish(result):
        return f"✅ 豆瓣里已经有《{title}》同一作品的想读版本，不重复添加。"
    return str(getattr(result, "message", "") or "这次没有修改豆瓣。")


async def _send_commit_result(
    channel: base.ChannelLike,
    *,
    chat_id: str,
    message_id: str | None,
    result: object,
    selected_edition: object | None,
    weread_lookup: object | None,
    weread_watch_store: object | None,
) -> None:
    base_text = _compact_base_text(result)
    kind = getattr(result, "kind", None)
    should_lookup = kind in {WishFlowKind.WRITTEN, WishFlowKind.ALREADY_WISH} or _is_same_work_existing_wish(result)

    if should_lookup and selected_edition is not None and weread_lookup is not None:
        response_text, _lookup_failed = await asyncio.to_thread(
            base._with_weread_followup,
            base_text=base_text,
            chat_id=chat_id,
            source_edition=selected_edition,
            weread_lookup=weread_lookup,
            weread_watch_store=weread_watch_store,
            douban_write_completed=kind is WishFlowKind.WRITTEN,
        )
    else:
        response_text = base_text

    await channel.send(
        chat_id,
        {"text": response_text},
        {"reply_to": message_id} if message_id else None,
    )


def prepare_compact_douban_flow() -> None:
    """Make an explicit edition selection the final confirmation for Douban wish.

    The user already expressed intent by selecting a numbered Douban edition or
    pressing the first `确认这本` button. We therefore keep the safety preflight
    inside `DoubanWishFlow.commit()` but remove the redundant second confirmation
    card. This patch is installed only for the hybrid Douban+WeRead router.
    """

    global _PREPARED
    if _PREPARED:
        return

    numeric_flow = DoubanWishFlow()
    numeric_lookup = WeReadEditionLookup()
    numeric_watch_store = default_watch_store()

    async def compact_candidate_number(
        channel: base.ChannelLike,
        message: base.InboundMessageLike,
        store: base.CandidateSelectionStore,
    ) -> bool:
        text = " ".join(message.content_text.split()).strip()
        candidates = store.get(message.chat_id)
        if not candidates or not text.isdigit():
            return False

        choice = int(text)
        if choice < 1 or choice > len(candidates):
            await channel.send(
                message.chat_id,
                {"text": f"当前有 {len(candidates)} 个版本，请回复 1–{len(candidates)}。"},
                {"reply_to": message.message_id},
            )
            return True

        edition = candidates[choice - 1]
        subject_id = str(getattr(edition, "douban_id", "") or "").strip()
        if not subject_id:
            return await _ORIGINAL_CANDIDATE_HANDLER(channel, message, store)

        try:
            result = await asyncio.to_thread(numeric_flow.commit, subject_id)
            await _send_commit_result(
                channel,
                chat_id=message.chat_id,
                message_id=message.message_id,
                result=result,
                selected_edition=edition,
                weread_lookup=numeric_lookup,
                weread_watch_store=numeric_watch_store,
            )
        except WISH_FLOW_ERRORS as exc:
            await channel.send(
                message.chat_id,
                {"text": f"豆瓣想读暂时没有写入：{exc}"},
                {"reply_to": message.message_id},
            )
        return True

    async def compact_card_action(
        channel: base.ChannelLike,
        flow: base.WishFlowLike,
        event: object,
        *,
        weread_lookup: base.WeReadLookupLike | None = None,
        weread_watch_store: object | None = None,
    ) -> Any:
        value = base._card_action_value(event)
        action = str(value.get("action") or "").strip()
        subject_id = str(value.get("douban_subject_id") or "").strip()
        chat_id = base._card_event_text(event, "chat_id")
        message_id = base._card_event_text(event, "message_id")

        if action != "confirm_book" or not chat_id or not subject_id:
            return await _ORIGINAL_CARD_HANDLER(
                channel,
                flow,
                event,
                weread_lookup=weread_lookup,
                weread_watch_store=weread_watch_store,
            )

        try:
            result = await asyncio.to_thread(flow.commit, subject_id)
            selected = _selected_edition_from_result(result)
            await _send_commit_result(
                channel,
                chat_id=chat_id,
                message_id=message_id or None,
                result=result,
                selected_edition=selected,
                weread_lookup=weread_lookup,
                weread_watch_store=weread_watch_store,
            )
        except WISH_FLOW_ERRORS as exc:
            await channel.send(
                chat_id,
                {"text": f"豆瓣想读暂时没有写入：{exc}"},
                {"reply_to": message_id} if message_id else None,
            )
            return {"toast": {"type": "error", "content": "豆瓣想读暂时没有写入。"}}

        kind = getattr(result, "kind", None)
        if kind is WishFlowKind.WRITTEN:
            return {"toast": {"type": "success", "content": "已加入豆瓣想读。"}}
        if kind is WishFlowKind.ALREADY_WISH or _is_same_work_existing_wish(result):
            return {"toast": {"type": "success", "content": "豆瓣已有想读记录。"}}
        return {"toast": {"type": "warning", "content": "这次没有修改豆瓣。"}}

    base._maybe_handle_candidate_number = compact_candidate_number
    base._handle_card_action = compact_card_action
    _PREPARED = True
