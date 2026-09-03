from __future__ import annotations

import asyncio
from typing import Any, Iterable


class LocalOcrError(RuntimeError):
    """Raised when the local OCR engine cannot process an image."""


class LocalImageOcr:
    """Local OCR adapter backed by RapidOCR / ONNX Runtime.

    Normal recognition performs exactly one full-image OCR pass. A separate
    edition-detail method is available for the rare case where the book title is
    already known but multiple Douban editions remain and small publisher / ISBN
    text is needed for disambiguation.
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

    async def recognize_edition_detail(self, image_bytes: bytes) -> tuple[str, ...]:
        """OCR only likely book-cover metadata regions, on demand.

        This method is intentionally separate from ``recognize`` so ordinary
        screenshots remain fast and detail OCR cannot create extra book mentions.
        """

        if not image_bytes:
            return ()
        try:
            return await asyncio.to_thread(
                self._recognize_edition_detail_sync,
                bytes(image_bytes),
            )
        except Exception:
            # Edition detail is optional evidence. Falling back to the version
            # chooser is safer than failing the entire capture.
            return ()

    def _recognize_sync(self, image_bytes: bytes) -> tuple[str, ...]:
        return self._lines_from_ocr_output(self._ocr(image_bytes))

    def _recognize_edition_detail_sync(self, image_bytes: bytes) -> tuple[str, ...]:
        lines: list[str] = []
        for region in self._book_cover_bottom_regions(image_bytes):
            lines.extend(self._lines_from_ocr_output(self._ocr(region)))
        return _dedupe_lines(lines)

    @staticmethod
    def _lines_from_ocr_output(output: object) -> tuple[str, ...]:
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
    def _book_cover_bottom_regions(image_bytes: bytes) -> tuple[object, ...]:
        """Find up to two portrait rectangles and OCR only their bottom area.

        Publisher marks on Chinese book covers are commonly near the bottom.
        Detecting likely portrait cover rectangles keeps the second pass focused
        and avoids re-reading comments, captions and other social-screen text.
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

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        image_area = float(height * width)
        candidates: list[tuple[float, int, int, int, int]] = []

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w <= 0 or h <= 0 or h <= w:
                continue
            ratio = w / h
            area_ratio = (w * h) / image_area
            if not 0.45 <= ratio <= 0.9:
                continue
            if not 0.015 <= area_ratio <= 0.45:
                continue
            # Prefer larger, cover-like portrait rectangles.
            candidates.append((area_ratio, x, y, w, h))

        candidates.sort(reverse=True)
        selected: list[tuple[int, int, int, int]] = []
        for _area, x, y, w, h in candidates:
            # Suppress near-duplicate nested rectangles.
            if any(
                abs(x - sx) < max(12, int(w * 0.12))
                and abs(y - sy) < max(12, int(h * 0.12))
                and abs(w - sw) < max(12, int(w * 0.15))
                and abs(h - sh) < max(12, int(h * 0.15))
                for sx, sy, sw, sh in selected
            ):
                continue
            selected.append((x, y, w, h))
            if len(selected) >= 2:
                break

        regions: list[object] = []
        for x, y, w, h in selected:
            # OCR the lower 42% of the detected cover, where publisher / ISBN
            # evidence is most likely to appear.
            y0 = y + int(h * 0.58)
            crop = image[y0 : y + h, x : x + w]
            if crop.size == 0:
                continue
            enlarged = cv2.resize(
                crop,
                None,
                fx=3.0,
                fy=3.0,
                interpolation=cv2.INTER_CUBIC,
            )
            regions.append(enlarged)

        return tuple(regions)


def _dedupe_lines(values: Iterable[str]) -> tuple[str, ...]:
    """Keep first-seen OCR order while removing duplicate detections."""

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
