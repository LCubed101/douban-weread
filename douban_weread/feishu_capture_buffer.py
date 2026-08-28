from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable

from douban_weread import feishu_bot as base


@dataclass(slots=True)
class _BufferedResource:
    type: str
    file_key: str
    message_id: str
    original: object


class BufferedImageChannel:
    """Coalesce consecutive image events from one chat into one synthetic post.

    Feishu mobile can visually send several selected images together while the
    bot SDK still delivers them as separate `image` message events. The old
    multi-image code only merged resources that were already present in one
    event, so the first image was processed before its siblings arrived.

    This wrapper waits for a short quiet window, merges all image events from
    the same chat, and invokes the bot's normal message handler once. It also
    remembers the original message id for each file key so attachment download
    keeps working after the synthetic merge.
    """

    def __init__(self, inner: base.ChannelLike, *, quiet_seconds: float = 0.9) -> None:
        self._inner = inner
        self._quiet_seconds = max(0.2, quiet_seconds)
        self._message_handler: Callable[[object], Any] | None = None
        self._pending: dict[str, list[object]] = {}
        self._generation: dict[str, int] = {}
        self._resource_message_ids: dict[str, str] = {}

    def on(self, event: str, handler):
        if event != "message":
            return self._inner.on(event, handler)
        self._message_handler = handler
        return self._inner.on("message", self._receive_message)

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
        origin_message_id = self._resource_message_ids.get(file_key) or message_id
        return await self._inner.download_resource(
            file_key,
            resource_type=resource_type,
            message_id=origin_message_id,
        )

    async def _receive_message(self, message: object) -> None:
        handler = self._message_handler
        if handler is None:
            return

        chat_id = str(getattr(message, "chat_id", "") or "").strip()
        resources = tuple(getattr(message, "resources", ()) or ())
        image_resources = [r for r in resources if self._is_image_resource(r)]
        raw_type = str(getattr(message, "raw_content_type", "") or "").strip().casefold()

        if not image_resources and raw_type != "image":
            if chat_id and chat_id in self._pending:
                await self._flush(chat_id)
            await handler(message)
            return

        if not chat_id:
            await handler(message)
            return

        message_id = str(getattr(message, "message_id", "") or "").strip()
        for resource in image_resources:
            key = str(getattr(resource, "file_key", "") or "").strip()
            if key and message_id:
                self._resource_message_ids[key] = message_id

        self._pending.setdefault(chat_id, []).append(message)
        generation = self._generation.get(chat_id, 0) + 1
        self._generation[chat_id] = generation
        asyncio.create_task(self._flush_after(chat_id, generation))

    async def _flush_after(self, chat_id: str, generation: int) -> None:
        await asyncio.sleep(self._quiet_seconds)
        if self._generation.get(chat_id) != generation:
            return
        await self._flush(chat_id)

    async def _flush(self, chat_id: str) -> None:
        messages = self._pending.pop(chat_id, [])
        self._generation.pop(chat_id, None)
        handler = self._message_handler
        if not messages or handler is None:
            return
        if len(messages) == 1:
            await handler(messages[0])
            return
        await handler(self._combine(messages))

    def _combine(self, messages: list[object]) -> object:
        first = messages[0]
        all_resources: list[object] = []
        seen_keys: set[str] = set()
        text_parts: list[str] = []

        for message in messages:
            message_id = str(getattr(message, "message_id", "") or "").strip()
            text = str(getattr(message, "content_text", "") or "").strip()
            if text:
                text_parts.append(text)
            for resource in tuple(getattr(message, "resources", ()) or ()):
                key = str(getattr(resource, "file_key", "") or "").strip()
                resource_type = str(getattr(resource, "type", "") or "image").strip() or "image"
                if key and key in seen_keys:
                    continue
                if key:
                    seen_keys.add(key)
                    if message_id:
                        self._resource_message_ids[key] = message_id
                all_resources.append(
                    _BufferedResource(
                        type=resource_type,
                        file_key=key,
                        message_id=message_id,
                        original=resource,
                    )
                )

        return SimpleNamespace(
            chat_id=getattr(first, "chat_id", ""),
            message_id=getattr(first, "message_id", ""),
            content_text="\n".join(text_parts),
            raw_content_type="post",
            resources=tuple(all_resources),
        )

    @staticmethod
    def _is_image_resource(resource: object) -> bool:
        resource_type = str(getattr(resource, "type", "") or "").strip().casefold()
        key = str(getattr(resource, "file_key", "") or "").strip()
        return bool(key and (resource_type == "image" or not resource_type))


def buffered_channel_factory(
    *,
    quiet_seconds: float = 0.9,
    inner_factory: base.ChannelFactory = base._default_channel_factory,
) -> base.ChannelFactory:
    def factory(app_id: str, app_secret: str) -> base.ChannelLike:
        return BufferedImageChannel(
            inner_factory(app_id, app_secret),
            quiet_seconds=quiet_seconds,
        )

    return factory
