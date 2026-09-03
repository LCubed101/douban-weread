from __future__ import annotations

import re
from collections.abc import Sequence

from douban_weread import feishu_bot as base
from douban_weread.core.models import Edition
from douban_weread.inbox import (
    BookInboxConfirmation,
    BookInboxResolution,
    BookInboxResolutionKind,
    request_from_text,
)
from douban_weread.inbox_ocr import OcrBookHint, extract_book_hint

_PREPARED = False
_ORIGINAL_IMAGE_HANDLER = base._handle_image_message


def _compact(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", value).casefold()


def _publisher_core(value: str | None) -> str:
    text = _compact(value)
    for suffix in ("出版传媒集团", "出版集团", "出版社", "出版公司", "出版"):
        text = text.replace(suffix, "")
    return text


def _ocr_blob(lines: Sequence[str]) -> str:
    return _compact("\n".join(lines))


def _candidate_evidence(candidate: Edition, lines: Sequence[str]) -> tuple[int, tuple[str, ...]]:
    """Score only edition-level OCR evidence."""

    blob = _ocr_blob(lines)
    score = 0
    evidence: list[str] = []

    isbn = _compact(candidate.isbn)
    if isbn and isbn in blob:
        score += 100
        evidence.append("ISBN")

    publisher = _compact(candidate.publisher)
    publisher_core = _publisher_core(candidate.publisher)
    if publisher and publisher in blob:
        score += 12
        evidence.append("出版社")
    elif len(publisher_core) >= 3 and publisher_core in blob:
        score += 8
        evidence.append("出版社")

    publish_date = str(candidate.publish_date or "")
    year_match = re.search(r"(?:19|20)\d{2}", publish_date)
    if year_match and year_match.group(0) in blob:
        score += 3
        evidence.append("出版年份")

    return score, tuple(evidence)


def resolve_ocr_edition(
    candidates: Sequence[Edition],
    lines: Sequence[str],
) -> tuple[Edition | None, tuple[str, ...]]:
    """Return one edition only when OCR contains strong, uniquely winning evidence."""

    if not candidates:
        return None, ()

    scored = [
        (*_candidate_evidence(candidate, lines), candidate)
        for candidate in candidates
    ]
    scored.sort(key=lambda item: item[0], reverse=True)

    best_score, best_evidence, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else -1

    if best_score < 8:
        return None, ()
    if best_score - second_score < 4:
        return None, ()
    return best, best_evidence


def _auto_confirmation(
    request,
    candidate: Edition,
    evidence: Sequence[str],
) -> BookInboxResolution:
    label = " + ".join(evidence)
    prompt = f"已根据图片中的{label}锁定这个版本。" if label else "已根据图片信息锁定这个版本。"
    confirmation = BookInboxConfirmation(
        request=request,
        candidate=candidate,
        prompt=prompt,
    )
    return BookInboxResolution(
        kind=BookInboxResolutionKind.CONFIRM,
        request=request,
        confirmation=confirmation,
        candidates=(candidate,),
        message=prompt,
    )


async def _detail_lines_if_supported(recognizer, image_bytes: bytes) -> tuple[str, ...]:
    method = getattr(recognizer, "recognize_edition_detail", None)
    if not callable(method):
        return ()
    try:
        result = await method(image_bytes)
    except Exception:
        return ()
    return tuple(str(line) for line in result if str(line).strip())


async def _metadata_aware_image_handler(
    channel: base.ChannelLike,
    service,
    message: base.InboundMessageLike,
    recognizer,
    *,
    candidate_store: base.CandidateSelectionStore | None = None,
    weread_lookup: base.WeReadLookupLike | None = None,
) -> None:
    store = candidate_store or base.CandidateSelectionStore()
    file_key = base._image_resource_key(message.resources)
    if not file_key:
        return await _ORIGINAL_IMAGE_HANDLER(
            channel,
            service,
            message,
            recognizer,
            candidate_store=store,
            weread_lookup=weread_lookup,
        )

    image_bytes = await channel.download_resource(
        file_key,
        resource_type="image",
        message_id=message.message_id,
    )
    if not image_bytes:
        await channel.send(
            message.chat_id,
            {"text": "图片下载失败，请重新发送原图或直接发送书名/ISBN。"},
            {"reply_to": message.message_id},
        )
        return

    # Stage 1: exactly one normal full-image OCR pass. These lines are used to
    # identify the book itself and must not be polluted by zoomed detail OCR.
    lines = tuple(await recognizer.recognize(bytes(image_bytes)))
    hint: OcrBookHint = extract_book_hint(lines)
    if not hint.usable:
        await channel.send(
            message.chat_id,
            {"text": "已识别到图片文字，但暂时没认准是哪本书。\n你可以直接发送：\n• 书名\n• ISBN\n• 豆瓣图书链接\n• 或再拍一张版权页 / 条码页"},
            {"reply_to": message.message_id},
        )
        return

    request = request_from_text(hint.isbn or hint.title or "")
    resolution = service.resolve(request)

    if (
        hint.isbn is None
        and resolution.kind is BookInboxResolutionKind.MULTIPLE_CANDIDATES
    ):
        # First use any edition evidence already visible in the normal OCR.
        selected, evidence = resolve_ocr_edition(resolution.candidates, hint.lines or lines)

        # Stage 2: only if the title is known, multiple editions remain, and the
        # first pass could not decide, run one focused cover-bottom detail pass.
        # These lines are edition evidence only; they never return to the book
        # mention extractor, so they cannot create fake extra books.
        if selected is None:
            detail_lines = await _detail_lines_if_supported(recognizer, bytes(image_bytes))
            if detail_lines:
                selected, evidence = resolve_ocr_edition(
                    resolution.candidates,
                    (*lines, *detail_lines),
                )

        if selected is not None:
            resolution = _auto_confirmation(request, selected, evidence)

    await base._send_resolution(
        channel,
        message,
        resolution,
        candidate_store=store,
        weread_lookup=weread_lookup,
    )


def prepare_ocr_edition_resolution() -> None:
    """Use OCR edition evidence before asking the user to choose a version."""

    global _PREPARED
    if _PREPARED:
        return
    base._handle_image_message = _metadata_aware_image_handler
    _PREPARED = True
