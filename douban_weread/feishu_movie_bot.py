from __future__ import annotations

import json
import sys
from collections.abc import Mapping

from douban_weread import feishu_bot as base
from douban_weread.adapters.local_ocr import LocalImageOcr
from douban_weread.feishu_bot_v11 import build_bot as build_book_bot
from douban_weread.feishu_movie_router import FeishuMovieRouter


def _field(value: object, *names: str):
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value.get(name)
        return None
    for name in names:
        candidate = getattr(value, name, None)
        if candidate is not None:
            return candidate
    return None


def _normalize_action_value(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _normalize_card_action_event(event: object) -> dict[str, object]:
    """Adapt Channel SDK cardAction shapes to the app's stable snake_case shape."""

    action = _field(event, "action")
    raw_value = _field(action, "value") if action is not None else None
    value = _normalize_action_value(raw_value)

    return {
        "chat_id": str(_field(event, "chat_id", "chatId") or "").strip(),
        "message_id": str(_field(event, "message_id", "messageId") or "").strip(),
        "action": {
            "value": value,
            "tag": str(_field(action, "tag") or "").strip(),
        },
    }


def _callback_raw_card(result: object) -> dict[str, object] | None:
    """Extract the raw card body from the app's callback result envelope."""

    if not isinstance(result, Mapping):
        return None
    card = result.get("card")
    if not isinstance(card, Mapping):
        return None
    if card.get("type") == "raw" and isinstance(card.get("data"), Mapping):
        return dict(card["data"])
    if "elements" in card or "header" in card:
        return dict(card)
    return None


def _toast_only(result: object) -> dict[str, object]:
    if isinstance(result, Mapping) and isinstance(result.get("toast"), Mapping):
        return {"toast": dict(result["toast"])}
    return {"toast": {"type": "info", "content": "已处理。"}}


class _MovieAwareRawChannel:
    def __init__(self, inner, router: FeishuMovieRouter, recognizer) -> None:
        self._inner = inner
        self._router = router
        self._recognizer = recognizer

    def on(self, event: str, handler):
        if event == "message":
            async def wrapped_message(message):
                try:
                    if await self._router.try_handle_message(self, message, self._recognizer):
                        return None
                except Exception as exc:
                    print(f"Feishu Movie Router message error: {type(exc).__name__}: {exc}", file=sys.stderr)
                    await self.send(
                        message.chat_id,
                        {"text": "影视处理暂时失败，豆瓣状态没有继续修改。请稍后再试。"},
                        {"reply_to": message.message_id},
                    )
                    return None
                return await handler(message)

            return self._inner.on(event, wrapped_message)

        if event == "cardAction":
            async def wrapped_card_action(action_event):
                normalized = _normalize_card_action_event(action_event)
                action_value = (normalized.get("action") or {}).get("value", {})
                action_name = str(action_value.get("action") if isinstance(action_value, Mapping) else "").strip()
                print(
                    f"Feishu cardAction received: action={action_name or '<empty>'}",
                    file=sys.stderr,
                )
                try:
                    result = await self._router.handle_card_action(normalized)
                except Exception as exc:
                    print(f"Feishu Movie Router card error: {type(exc).__name__}: {exc}", file=sys.stderr)
                    return {"toast": {"type": "error", "content": "影视想看操作没有执行，请稍后再试。"}}

                if result is not None:
                    # Do not depend on Feishu's in-place callback-card replacement for
                    # Movie Router results. Live testing showed the click reaches us,
                    # but the callback replacement can fail with OutboundSendError.
                    # Send the next/final card as a normal bot message instead, then
                    # keep the callback response to a small toast only.
                    raw_card = _callback_raw_card(result)
                    chat_id = str(normalized.get("chat_id") or "").strip()
                    if raw_card is not None and chat_id:
                        try:
                            await self.send(chat_id, {"card": raw_card})
                        except Exception as exc:
                            print(
                                f"Feishu Movie Router result send error: {type(exc).__name__}: {exc}",
                                file=sys.stderr,
                            )
                            return {
                                "toast": {
                                    "type": "error",
                                    "content": "豆瓣操作已处理，但结果卡片发送失败，请查看机器人日志。",
                                }
                            }
                    return _toast_only(result)

                return await handler(normalized)

            return self._inner.on(event, wrapped_card_action)

        return self._inner.on(event, handler)

    async def connect(self) -> None:
        await self._inner.connect()

    async def send(self, to: str, message: object, opts: object | None = None):
        return await self._inner.send(to, message, opts)

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


def build_movie_aware_bot(
    *,
    channel_factory: base.ChannelFactory = base._default_channel_factory,
):
    router = FeishuMovieRouter.default()
    recognizer = LocalImageOcr()

    def wrapped_factory(app_id: str, app_secret: str):
        raw = channel_factory(app_id, app_secret)
        return _MovieAwareRawChannel(raw, router, recognizer)

    return build_book_bot(
        channel_factory=wrapped_factory,
        image_recognizer=recognizer,
    )
