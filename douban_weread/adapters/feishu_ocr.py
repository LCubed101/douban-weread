from __future__ import annotations

import base64
from typing import Protocol


class ImageTextRecognizer(Protocol):
    async def recognize(self, image_bytes: bytes) -> tuple[str, ...]: ...


class FeishuOcrError(RuntimeError):
    pass


class FeishuImageOcr:
    """Thin async adapter around Feishu Optical Character Recognition API."""

    def __init__(self, *, app_id: str, app_secret: str) -> None:
        import lark_oapi as lark

        self._client = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .build()
        )

    async def recognize(self, image_bytes: bytes) -> tuple[str, ...]:
        if not image_bytes:
            raise FeishuOcrError("Downloaded Feishu image is empty")

        from lark_oapi.api.optical_char_recognition.v1 import (
            BasicRecognizeImageRequest,
            BasicRecognizeImageRequestBody,
        )

        encoded = base64.b64encode(image_bytes).decode("ascii")
        request = (
            BasicRecognizeImageRequest.builder()
            .request_body(
                BasicRecognizeImageRequestBody.builder()
                .image(encoded)
                .build()
            )
            .build()
        )
        response = await self._client.optical_char_recognition.v1.image.abasic_recognize(request)
        if not response.success():
            raise FeishuOcrError(
                f"Feishu OCR failed with code {response.code}: {response.msg}"
            )
        data = response.data
        lines = getattr(data, "text_list", None) if data is not None else None
        return tuple(str(line).strip() for line in (lines or []) if str(line).strip())
