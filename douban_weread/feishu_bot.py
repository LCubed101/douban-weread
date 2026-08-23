from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from douban_weread.adapters.feishu import (
    build_confirmation_card,
    build_wish_confirmation_card,
)
from douban_weread.adapters.feishu_ocr import FeishuImageOcr, FeishuOcrError, ImageTextRecognizer
from douban_weread.core.models import Edition
from douban_weread.inbox import (
    BookInboxConfirmation,
    BookInboxResolution,
    BookInboxResolutionKind,
    BookInboxService,
    request_from_text,
)
from douban_weread.inbox_ocr import extract_book_hint
from douban_weread.inbox_weread import (
    WEREAD_LOOKUP_ERRORS,
    WeReadEditionLookup,
)
from douban_weread.inbox_wish import (
    DoubanWishFlow,
    WISH_FLOW_ERRORS,
    WishFlowKind,
)
from douban_weread.providers.douban import DoubanBookSearchClient, DoubanProviderError


class ResourceLike(Protocol):
    type: str
    file_key: str


class ChannelLike(Protocol):
    def on(self, event: str, handler: Callable[..., Any]) -> None: ...

    async def connect(self) -> None: ...

    async def send(self, to: str, message: object, opts: object | None = None): ...

    async def download_resource(
        self,
        file_key: str,
        resource_type: str = "image",
        message_id: str | None = None,
    ): ...


class InboundMessageLike(Protocol):
    chat_id: str
    message_id: str
    content_text: str
    raw_content_type: str
    resources: Sequence[ResourceLike]


class WishFlowLike(Protocol):
    def preflight(self, subject_id: str): ...

    def commit(self, subject_id: str): ...


class WeReadLookupLike(Protocol):
    def lookup(self, source_edition: Edition): ...


class CandidateSelectionStore:
    """Small in-memory per-chat store for one pending multiple-edition choice."""

    def __init__(self) -> None:
        self._by_chat: dict[str, tuple[Edition, ...]] = {}

    def set(self, chat_id: str, candidates: Sequence[Edition]) -> None:
        values = tuple(candidates)
        if values:
            self._by_chat[chat_id] = values
        else:
            self._by_chat.pop(chat_id, None)

    def get(self, chat_id: str) -> tuple[Edition, ...]:
        return self._by_chat.get(chat_id, ())

    def clear(self, chat_id: str) -> None:
        self._by_chat.pop(chat_id, None)


ChannelFactory = Callable[[str, str], ChannelLike]


def _default_channel_factory(app_id: str, app_secret: str) -> ChannelLike:
    try:
        from lark_channel import FeishuChannel
    except ImportError as exc:  # pragma: no cover - packaging/runtime guard
        raise RuntimeError(
            "lark-channel-sdk is required for the Feishu bot; run pip install -e ."
        ) from exc
    return FeishuChannel(app_id=app_id, app_secret=app_secret)


def _credentials() -> tuple[str, str]:
    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError(
            "Set FEISHU_APP_ID and FEISHU_APP_SECRET in the current shell before starting the bot."
        )
    return app_id, app_secret


def build_bot(
    *,
    channel_factory: ChannelFactory = _default_channel_factory,
    inbox_service: BookInboxService | None = None,
    image_recognizer: ImageTextRecognizer | None = None,
    wish_flow: WishFlowLike | None = None,
    weread_lookup: WeReadLookupLike | None = None,
) -> ChannelLike:
    app_id, app_secret = _credentials()
    channel = channel_factory(app_id, app_secret)
    service = inbox_service or BookInboxService(DoubanBookSearchClient(), search_limit=5)
    recognizer = image_recognizer or FeishuImageOcr(app_id=app_id, app_secret=app_secret)
    flow = wish_flow or DoubanWishFlow()
    lookup = weread_lookup or WeReadEditionLookup()
    candidate_store = CandidateSelectionStore()

    async def on_message(message: InboundMessageLike) -> None:
        try:
            await _handle_message(
                channel,
                service,
                message,
                image_recognizer=recognizer,
                candidate_store=candidate_store,
            )
        except (DoubanProviderError, FeishuOcrError) as exc:
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
        try:
            return await _handle_card_action(
                channel,
                flow,
                event,
                weread_lookup=lookup,
            )
        except WISH_FLOW_ERRORS as exc:
            chat_id = _card_event_text(event, "chat_id")
            message_id = _card_event_text(event, "message_id")
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


async def _handle_card_action(
    channel: ChannelLike,
    flow: WishFlowLike,
    event: object,
    *,
    weread_lookup: WeReadLookupLike | None = None,
):
    chat_id = _card_event_text(event, "chat_id")
    message_id = _card_event_text(event, "message_id")
    value = _card_action_value(event)
    action = str(value.get("action") or "").strip()
    subject_id = str(value.get("douban_subject_id") or "").strip()

    if action in {"reject_book", "cancel_wish"}:
        return {"toast": {"type": "info", "content": "已取消，没有修改豆瓣。"}}

    if action not in {"confirm_book", "confirm_wish"}:
        return {"toast": {"type": "warning", "content": "无法识别这个操作，没有修改豆瓣。"}}

    if not chat_id or not subject_id:
        return {"toast": {"type": "error", "content": "缺少书籍或会话信息，没有修改豆瓣。"}}

    if action == "confirm_book":
        result = flow.preflight(subject_id)
        if result.kind is WishFlowKind.ALREADY_WISH:
            await channel.send(
                chat_id,
                {"text": result.message},
                {"reply_to": message_id} if message_id else None,
            )
            return {"toast": {"type": "success", "content": "豆瓣已经是想读。"}}
        if result.kind is not WishFlowKind.READY:
            await channel.send(
                chat_id,
                {"text": result.message},
                {"reply_to": message_id} if message_id else None,
            )
            return {"toast": {"type": "warning", "content": "需要先处理已有状态，没有修改豆瓣。"}}

        card = build_wish_confirmation_card(
            title=result.title or "这本书",
            subject_id=subject_id,
        )
        await channel.send(
            chat_id,
            {"card": card},
            {"reply_to": message_id} if message_id else None,
        )
        return {"toast": {"type": "info", "content": "检查通过，请再次确认是否加入想读。"}}

    result = flow.commit(subject_id)
    response_text = result.message
    lookup_failed = False

    if result.kind is WishFlowKind.WRITTEN and weread_lookup is not None:
        source_edition = result.decision.target if result.decision is not None else None
        if source_edition is not None:
            try:
                weread_result = weread_lookup.lookup(source_edition)
                response_text = f"{response_text}\n\n{weread_result.message}"
            except WEREAD_LOOKUP_ERRORS as exc:
                lookup_failed = True
                response_text = (
                    f"{response_text}\n\n"
                    f"微信读书查找暂时失败：{exc}\n"
                    "豆瓣写入已经完成并验证，不需要重复点击加入想读。"
                )

    await channel.send(
        chat_id,
        {"text": response_text},
        {"reply_to": message_id} if message_id else None,
    )
    if result.kind is WishFlowKind.WRITTEN:
        if lookup_failed:
            return {
                "toast": {
                    "type": "warning",
                    "content": "豆瓣已加入想读；微信读书查找暂时失败。",
                }
            }
        return {"toast": {"type": "success", "content": "已加入豆瓣想读。"}}
    if result.kind is WishFlowKind.ALREADY_WISH:
        return {"toast": {"type": "success", "content": "豆瓣已经是想读。"}}
    return {"toast": {"type": "warning", "content": "状态已变化，没有修改豆瓣。"}}


def _card_event_text(event: object, field: str) -> str:
    if isinstance(event, Mapping):
        value = event.get(field)
    else:
        value = getattr(event, field, None)
    return str(value or "").strip()


def _card_action_value(event: object) -> dict[str, object]:
    if isinstance(event, Mapping):
        action = event.get("action")
    else:
        action = getattr(event, "action", None)
    if isinstance(action, Mapping):
        value = action.get("value")
    else:
        value = getattr(action, "value", None)
    return dict(value) if isinstance(value, Mapping) else {}


async def _handle_message(
    channel: ChannelLike,
    service: BookInboxService,
    message: InboundMessageLike,
    *,
    image_recognizer: ImageTextRecognizer | None = None,
    candidate_store: CandidateSelectionStore | None = None,
) -> None:
    store = candidate_store or CandidateSelectionStore()

    if message.raw_content_type == "image":
        if image_recognizer is None:
            await channel.send(
                message.chat_id,
                {"text": "图片识别当前未配置，请先发送书名或豆瓣链接。"},
                {"reply_to": message.message_id},
            )
            return
        await _handle_image_message(
            channel,
            service,
            message,
            image_recognizer,
            candidate_store=store,
        )
        return

    if message.raw_content_type not in {"text", "post", ""}:
        await channel.send(
            message.chat_id,
            {"text": "目前支持书名、ISBN、豆瓣图书链接和书籍图片。"},
            {"reply_to": message.message_id},
        )
        return

    if await _maybe_handle_candidate_number(channel, message, store):
        return

    request = request_from_text(message.content_text)
    resolution = service.resolve(request)
    await _send_resolution(channel, message, resolution, candidate_store=store)


async def _maybe_handle_candidate_number(
    channel: ChannelLike,
    message: InboundMessageLike,
    store: CandidateSelectionStore,
) -> bool:
    text = " ".join(message.content_text.split()).strip()
    candidates = store.get(message.chat_id)
    if not candidates or not text.isdigit():
        return False

    choice = int(text)
    if choice < 1 or choice > len(candidates):
        await channel.send(
            message.chat_id,
            {"text": f"当前有 {len(candidates)} 个候选版本，请回复 1–{len(candidates)} 选择。"},
            {"reply_to": message.message_id},
        )
        return True

    edition = candidates[choice - 1]
    store.clear(message.chat_id)
    request = request_from_text(edition.isbn or edition.title)
    confirmation = BookInboxConfirmation(request=request, candidate=edition)
    card = build_confirmation_card(confirmation)
    await channel.send(
        message.chat_id,
        {"card": card},
        {"reply_to": message.message_id},
    )
    return True


async def _handle_image_message(
    channel: ChannelLike,
    service: BookInboxService,
    message: InboundMessageLike,
    recognizer: ImageTextRecognizer,
    *,
    candidate_store: CandidateSelectionStore | None = None,
) -> None:
    store = candidate_store or CandidateSelectionStore()
    file_key = _image_resource_key(message.resources)
    if not file_key:
        await channel.send(
            message.chat_id,
            {"text": "收到了图片，但没有拿到可下载的图片资源，请重新发送原图。"},
            {"reply_to": message.message_id},
        )
        return

    image_bytes = await channel.download_resource(
        file_key,
        resource_type="image",
        message_id=message.message_id,
    )
    if not image_bytes:
        await channel.send(
            message.chat_id,
            {"text": "图片下载失败，请重新发送原图或直接发送书名/ISBN。"},
            {"reply_to": message.message_id},
        )
        return

    lines = await recognizer.recognize(bytes(image_bytes))
    hint = extract_book_hint(lines)
    if not hint.usable:
        await channel.send(
            message.chat_id,
            {"text": "已经识别图片文字，但还不能稳定确定书名或 ISBN。请尽量拍清楚封面、版权页或条码。"},
            {"reply_to": message.message_id},
        )
        return

    if hint.isbn:
        request = request_from_text(hint.isbn)
    else:
        request = request_from_text(hint.title or "")

    resolution = service.resolve(request)
    await _send_resolution(channel, message, resolution, candidate_store=store)


async def _send_resolution(
    channel: ChannelLike,
    message: InboundMessageLike,
    resolution: BookInboxResolution,
    *,
    candidate_store: CandidateSelectionStore | None = None,
) -> None:
    store = candidate_store or CandidateSelectionStore()
    if resolution.kind is BookInboxResolutionKind.CONFIRM:
        store.clear(message.chat_id)
        confirmation = resolution.confirmation
        if confirmation is None:
            raise ValueError("Confirm resolution is missing confirmation data")
        card = build_confirmation_card(confirmation)
        await channel.send(
            message.chat_id,
            {"card": card},
            {"reply_to": message.message_id},
        )
        return

    if resolution.kind is BookInboxResolutionKind.MULTIPLE_CANDIDATES:
        store.set(message.chat_id, resolution.candidates)
        lines = [resolution.message or "找到多个版本："]
        for index, edition in enumerate(resolution.candidates, start=1):
            details = " · ".join(
                value
                for value in (
                    "、".join(edition.authors) if edition.authors else None,
                    edition.publisher,
                    edition.publish_date,
                    edition.isbn,
                )
                if value
            )
            lines.append(f"{index}. {edition.title}" + (f"｜{details}" if details else ""))
        lines.append(
            f"回复 1–{len(resolution.candidates)} 选择具体版本；也可以发送 ISBN 或豆瓣图书链接。"
        )
        await channel.send(
            message.chat_id,
            {"text": "\n".join(lines)},
            {"reply_to": message.message_id},
        )
        return

    store.clear(message.chat_id)
    await channel.send(
        message.chat_id,
        {"text": resolution.message or "暂时无法识别这本书。"},
        {"reply_to": message.message_id},
    )


def _image_resource_key(resources: Sequence[ResourceLike]) -> str | None:
    for resource in resources:
        if getattr(resource, "type", None) == "image":
            value = str(getattr(resource, "file_key", "") or "").strip()
            if value:
                return value
    return None


def main() -> None:
    try:
        channel = build_bot()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc

    print("Douban × WeRead Feishu Book Inbox starting via WebSocket...")
    print(
        "Image/OCR enabled. Douban Want-to-Read writes require two explicit card confirmations and read-back verification; "
        "verified writes are followed by a read-only WeRead Edition lookup."
    )
    try:
        asyncio.run(channel.connect())
    except KeyboardInterrupt:
        print("\nFeishu bot stopped.")


if __name__ == "__main__":
    main()
