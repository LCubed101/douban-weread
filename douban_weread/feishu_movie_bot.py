from __future__ import annotations

from douban_weread import feishu_bot as base
from douban_weread.adapters.local_ocr import LocalImageOcr
from douban_weread.feishu_bot_v11 import build_bot as build_book_bot
from douban_weread.feishu_movie_router import FeishuMovieRouter


class _MovieAwareRawChannel:
    def __init__(self, inner, router: FeishuMovieRouter, recognizer) -> None:
        self._inner = inner
        self._router = router
        self._recognizer = recognizer

    def on(self, event: str, handler):
        if event == "message":
            async def wrapped_message(message):
                if await self._router.try_handle_message(self, message, self._recognizer):
                    return None
                return await handler(message)

            return self._inner.on(event, wrapped_message)

        if event == "cardAction":
            async def wrapped_card_action(action_event):
                result = await self._router.handle_card_action(action_event)
                if result is not None:
                    return result
                return await handler(action_event)

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
