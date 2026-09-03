from __future__ import annotations

import asyncio
import re
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
        """Try precise cover-bottom OCR first, then a bounded media fallback.

        The contour detector is fast when the embedded cover has a visible edge,
        but social/video screenshots often flatten the cover into the background.
        If the detected regions do not yield publisher/ISBN-like evidence, scan
        at most two upper-media regions. This keeps the fallback bounded and is
        still isolated from book-title extraction.
        """

        lines: list[str] = []
        for region in self._book_cover_bottom_regions(image_bytes):
            lines.extend(self._lines_from_ocr_output(self._ocr(region)))

        deduped = _dedupe_lines(lines)
        if _has_edition_metadata(deduped):
            return deduped

        fallback_lines: list[str] = list(deduped)
        for region in self._upper_media_fallback_regions(image_bytes):
            fallback_lines.extend(self._lines_from_ocr_output(self._ocr(region)))
            current = _dedupe_lines(fallback_lines)
            if _has_edition_metadata(current):
                return current

        return _dedupe_lines(fallback_lines)

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
    def _decode_image(image_bytes: bytes):
        try:
            import cv2
            import numpy as np
        except ImportError:
            return None

        encoded = np.frombuffer(image_bytes, dtype=np.uint8)
        return cv2.imdecode(encoded, cv2.IMREAD_COLOR)

    @classmethod
    def _book_cover_bottom_regions(cls, image_bytes: bytes) -> tuple[object, ...]:
        """Find up to two portrait rectangles and OCR only their bottom area."""

        try:
            import cv2
        except ImportError:
            return ()

        image = cls._decode_image(image_bytes)
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
            # Slightly prefer larger rectangles in the upper 70% of the image,
            # where social/video posts usually place the media content.
            top_bonus = 0.01 if y < height * 0.7 else 0.0
            candidates.append((area_ratio + top_bonus, x, y, w, h))

        candidates.sort(reverse=True)
        selected: list[tuple[int, int, int, int]] = []
        for _score, x, y, w, h in candidates:
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
            # Chinese publisher marks are commonly close to the lower center of
            # the front cover. Keep a little more than the bottom third so a logo
            # or small imprint just above the edge is not clipped.
            y0 = y + int(h * 0.52)
            crop = image[y0 : y + h, x : x + w]
            if crop.size == 0:
                continue
            regions.append(
                cv2.resize(
                    crop,
                    None,
                    fx=3.0,
                    fy=3.0,
                    interpolation=cv2.INTER_CUBIC,
                )
            )

        return tuple(regions)

    @classmethod
    def _upper_media_fallback_regions(cls, image_bytes: bytes) -> tuple[object, ...]:
        """Return at most two bounded fallback crops for embedded book covers.

        Many Bilibili/Xiaohongshu-style screenshots place the media in the upper
        half, while the cover itself may have no detectable outer contour. We
        therefore scan only the upper-left and upper-center/right media halves,
        never the comments below. The fallback runs only after a multiple-edition
        ambiguity and only when precise cover-bottom OCR found no metadata.
        """

        try:
            import cv2
        except ImportError:
            return ()

        image = cls._decode_image(image_bytes)
        if image is None:
            return ()

        height, width = image.shape[:2]
        if height < 240 or width < 240:
            return ()

        media_h = max(1, int(height * 0.52))
        overlap = int(width * 0.06)
        split = width // 2
        crops = (
            image[0:media_h, 0 : min(width, split + overlap)],
            image[0:media_h, max(0, split - overlap) : width],
        )

        regions: list[object] = []
        for crop in crops:
            if crop.size == 0:
                continue
            regions.append(
                cv2.resize(
                    crop,
                    None,
                    fx=1.8,
                    fy=1.8,
                    interpolation=cv2.INTER_CUBIC,
                )
            )
        return tuple(regions)


def _has_edition_metadata(lines: Iterable[str]) -> bool:
    """Return True when OCR found likely edition-level evidence."""

    for value in lines:
        text = "".join(str(value).split())
        if not text:
            continue
        folded = text.casefold()
        if "出版" in text or "isbn" in folded:
            return True
        digits = re.sub(r"\D", "", text)
        if len(digits) in {10, 13}:
            return True
    return False


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
