from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from douban_weread.adapters.feishu import build_confirmation_card
from douban_weread.adapters.feishu_ocr import FeishuImageOcr, FeishuOcrError, ImageTextRecognizer
from douban_weread.inbox import (
    BookInboxRequest,
    BookInboxResolution,
    BookInboxResolutionKind,
    BookInboxService,
    request_from_text,
)
from douban_weread.inbox_ocr import extract_book_hint
from douban_weread.providers.douban import DoubanBookSearchClient, DoubanProviderError


class ResourceLike(Protocol):
    type: str
    file_key: str


class ChannelLike(Protocol):
    def on(self, event: str, handler: Callable[..., Any]) -> None: ...

    async def connect(self) -> None: ...

    async def send(self, to: str, message: object, opts: object | None = None): ...

    async def download_resource(self, file_key: str, *, resource_type: str): ...


class InboundMessageLike(Protocol):
    chat_id: str
    message_id: str
    content_text: str
    raw_content_type: str
    resources: Sequence[ResourceLike]


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
) -> ChannelLike:
    app_id, app_secret = _credentials()
    channel = channel_factory(app_id, app_secret)
    service = inbox_service or BookInboxService(DoubanBookSearchClient(), search_limit=5)
    recognizer = image_recognizer or FeishuImageOcr(app_id=app_id, app_secret=app_secret)

    async def on_message(message: InboundMessageLike) -> None:
        try:
            await _handle_message(channel, service, message, image_recognizer=recognizer)
        except (DoubanProviderError, FeishuOcrError) as exc:
            await channel.send(
                message.chat_id,
                {"text": f"书籍识别暂时失败：{exc}"},
                {"reply_to": message.message_id},
            )
        except Exception as exc:
            # Keep credentials and provider payloads out of user-visible/log output.
            print(f"Feishu message handling error: {type(exc).__name__}", file=sys.stderr)
            await channel.send(
                message.chat_id,
                {"text": "这条消息暂时无法安全处理，请稍后再试。"},
                {"reply_to": message.message_id},
            )

    async def on_card_action(event: object) -> None:
        # Deliberately no mutation in this milestone. Card callbacks are wired so
        # the next milestone can reconnect confirmation to the safe-write flow.
        print("Feishu card action received; mutation remains disabled in this milestone.")

    async def on_error(error: object) -> None:
        print(f"Feishu channel error: {type(error).__name__}", file=sys.stderr)

    channel.on("message", on_message)
    channel.on("cardAction", on_card_action)
    channel.on("error", on_error)
    return channel


async def _handle_message(
    channel: ChannelLike,
    service: BookInboxService,
    message: InboundMessageLike,
    *,
    image_recognizer: ImageTextRecognizer | None = None,
) -> None:
    if message.raw_content_type == "image":
        if image_recognizer is None:
            await channel.send(
                message.chat_id,
                {"text": "图片识别当前未配置，请先发送书名或豆瓣链接。"},
                {"reply_to": message.message_id},
            )
            return
        await _handle_image_message(channel, service, message, image_recognizer)
        return

    if message.raw_content_type not in {"text", "post", ""}:
        await channel.send(
            message.chat_id,
            {"text": "目前支持书名、ISBN、豆瓣图书链接和书籍图片。"},
            {"reply_to": message.message_id},
        )
        return

    request = request_from_text(message.content_text)
    resolution = service.resolve(request)
    await _send_resolution(channel, message, resolution)


async def _handle_image_message(
    channel: ChannelLike,
    service: BookInboxService,
    message: InboundMessageLike,
    recognizer: ImageTextRecognizer,
) -> None:
    file_key = _image_resource_key(message.resources)
    if not file_key:
        await channel.send(
            message.chat_id,
            {"text": "收到了图片，但没有拿到可下载的图片资源，请重新发送原图。"},
            {"reply_to": message.message_id},
        )
        return

    image_bytes = await channel.download_resource(file_key, resource_type="image")
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
    await _send_resolution(channel, message, resolution)


async def _send_resolution(
    channel: ChannelLike,
    message: InboundMessageLike,
    resolution: BookInboxResolution,
) -> None:
    if resolution.kind is BookInboxResolutionKind.CONFIRM:
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
        lines.append("请发送更具体的书名、ISBN，或直接发送豆瓣图书链接。")
        await channel.send(
            message.chat_id,
            {"text": "\n".join(lines)},
            {"reply_to": message.message_id},
        )
        return

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
    print("Image download + Feishu OCR enabled. No Douban or WeRead mutation is enabled.")
    try:
        asyncio.run(channel.connect())
    except KeyboardInterrupt:
        print("\nFeishu bot stopped.")


if __name__ == "__main__":
    main()
