from __future__ import annotations

import asyncio
from typing import Any


class LocalOcrError(RuntimeError):
    """Raised when the local OCR engine cannot process an image."""


class LocalImageOcr:
    """Local OCR adapter backed by RapidOCR / ONNX Runtime.

    Images stay on the local machine after they have been downloaded from
    Feishu. OCR work runs in a worker thread so the bot's asyncio event loop
    is not blocked by CPU-bound inference.
    """

    def __init__(self) -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise RuntimeError(
                "Local OCR requires rapidocr-onnxruntime. "
                "Run: pip install 'rapidocr-onnxruntime>=1.3,<2'"
            ) from exc

        self._ocr = RapidOCR()

    async def recognize(self, image_bytes: bytes) -> tuple[str, ...]:
        if not image_bytes:
            raise LocalOcrError("Downloaded Feishu image is empty")

        try:
            return await asyncio.to_thread(
                self._recognize_sync,
                bytes(image_bytes),
            )
        except LocalOcrError:
            raise
        except Exception as exc:
            raise LocalOcrError(
                f"Local OCR failed: {type(exc).__name__}: {exc}"
            ) from exc

    def _recognize_sync(self, image_bytes: bytes) -> tuple[str, ...]:
        output = self._ocr(image_bytes)

        # RapidOCR commonly returns:
        #
        #   (result, elapsed)
        #
        # result is a list whose entries look like:
        #
        #   [box, text, score]
        #
        # Keep this parsing slightly defensive so minor library return-format
        # differences do not break the bot.
        result: Any

        if (
            isinstance(output, tuple)
            and len(output) == 2
        ):
            result = output[0]
        else:
            result = output

        if not result:
            return ()

        lines: list[str] = []

        for item in result:
            if not isinstance(item, (list, tuple)):
                continue

            if len(item) < 2:
                continue

            text = str(item[1]).strip()

            if text:
                lines.append(text)

        return tuple(lines)
