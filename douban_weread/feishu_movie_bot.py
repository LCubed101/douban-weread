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
    """Adapt Channel SDK cardAction shapes to the app's stable snake_case shape.

    lark-channel-sdk exposes normalized card actions, but versions may surface
    event identity as snake_case or camelCase and action.value may arrive as an
    object or JSON string. Keep this compatibility adapter at the channel edge
    so both Movie Router and the existing Book handler receive one predictable
    shape.
    """

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
                    print(f"Feishu Movie Router message error: {type(exc).__name__}", file=sys.stderr)
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
                action_name = str(
                    (normalized.get("action") or {}).get("value", {}).get("action")
                    if isinstance(normalized.get("action"), Mapping)
                    else ""
                ).strip()
                print(
                    f"Feishu cardAction received: action={action_name or '<empty>'}",
                    file=sys.stderr,
                )
                try:
                    result = await self._router.handle_card_action(normalized)
                except Exception as exc:
                    print(f"Feishu Movie Router card error: {type(exc).__name__}", file=sys.stderr)
                    return {"toast": {"type": "error", "content": "影视想看操作没有执行，请稍后再试。"}}
                if result is not None:
                    return result
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
