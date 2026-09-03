from __future__ import annotations

import asyncio
from typing import Any, Iterable


class LocalOcrError(RuntimeError):
    """Raised when the local OCR engine cannot process an image."""


class LocalImageOcr:
    """Local OCR adapter backed by RapidOCR / ONNX Runtime.

    Images stay on the local machine after they have been downloaded from
    Feishu. OCR work runs in a worker thread so the bot's asyncio event loop
    is not blocked by CPU-bound inference.

    A normal full-image OCR pass is followed by overlapping, upscaled detail
    tiles when OpenCV is available. This second pass is intentionally aimed at
    small book-cover metadata such as publisher names, which often appear near
    the bottom of a cover and can be missed in a full social-media screenshot.
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
        lines: list[str] = []

        # First pass: preserve the existing full-image behavior. It is still
        # best for large title/author text and gives stable reading order.
        lines.extend(self._lines_from_ocr_output(self._ocr(image_bytes)))

        # Second pass: zoom into overlapping tiles. Social screenshots often
        # make the book cover occupy only a small fraction of the image, and
        # publisher text at the bottom of the cover can otherwise be only a few
        # pixels high. RapidOCR already depends on OpenCV in normal installs;
        # if OpenCV is unavailable we simply keep the full-image result.
        for region in self._detail_regions(image_bytes):
            lines.extend(self._lines_from_ocr_output(self._ocr(region)))

        return _dedupe_lines(lines)

    @staticmethod
    def _lines_from_ocr_output(output: object) -> tuple[str, ...]:
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

        if isinstance(output, tuple) and len(output) == 2:
            result = output[0]
        else:
            result = output

        if not result:
            return ()

        lines: list[str] = []
        for item in result:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            text = str(item[1]).strip()
            if text:
                lines.append(text)
        return tuple(lines)

    @staticmethod
    def _detail_regions(image_bytes: bytes) -> tuple[object, ...]:
        """Return upscaled overlapping tiles for small-text OCR.

        Two columns × three rows keeps the extra OCR cost bounded while making
        small cover metadata substantially larger. Tiles overlap so text near a
        boundary is not lost. The layout is generic: it also works when a book
        cover is embedded in the upper-left, center, or lower part of a social
        screenshot instead of assuming the whole screenshot is the cover.
        """

        try:
            import cv2
            import numpy as np
        except ImportError:
            return ()

        encoded = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            return ()

        height, width = image.shape[:2]
        if height < 240 or width < 240:
            return ()

        cols = 2
        rows = 3
        overlap = 0.12
        regions: list[object] = []

        cell_w = width / cols
        cell_h = height / rows
        pad_x = int(cell_w * overlap)
        pad_y = int(cell_h * overlap)

        for row in range(rows):
            for col in range(cols):
                x0 = max(0, int(col * cell_w) - pad_x)
                y0 = max(0, int(row * cell_h) - pad_y)
                x1 = min(width, int((col + 1) * cell_w) + pad_x)
                y1 = min(height, int((row + 1) * cell_h) + pad_y)
                crop = image[y0:y1, x0:x1]
                if crop.size == 0:
                    continue

                # 2× enlargement is enough to help tiny publisher/ISBN text
                # without turning each tile into an excessively large OCR job.
                enlarged = cv2.resize(
                    crop,
                    None,
                    fx=2.0,
                    fy=2.0,
                    interpolation=cv2.INTER_CUBIC,
                )
                regions.append(enlarged)

        return tuple(regions)


def _dedupe_lines(values: Iterable[str]) -> tuple[str, ...]:
    """Keep first-seen OCR order while removing duplicate tile detections."""

    seen: set[str] = set()
    lines: list[str] = []
    for value in values:
        text = " ".join(str(value).split()).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(text)
    return tuple(lines)
