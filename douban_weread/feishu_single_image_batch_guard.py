from __future__ import annotations

import re

from douban_weread.feishu_multi_image import _image_resource_count

_PREPARED = False

# A real book title can be long, but OCR-corrupted social-screen prose captured
# between stray 《》 marks is usually much longer and sentence-like. Keep the
# single-image batch path conservative so one screenshot of one book does not
# become a fake two-book batch.
_MAX_SINGLE_IMAGE_BATCH_TITLE_LENGTH = 40
_SENTENCE_MARKS_RE = re.compile(r"[，。！？；;!?]")
_OCR_PROSE_FRAGMENTS = (
    "作者：",
    "作者:",
    "比如",
    "快来",
    "打造",
    "所有",
    "评论",
    "回复",
)


def _credible_single_image_batch_title(value: str) -> bool:
    title = " ".join(str(value or "").split()).strip()
    if not title:
        return False
    if len(title) > _MAX_SINGLE_IMAGE_BATCH_TITLE_LENGTH:
        return False
    if len(_SENTENCE_MARKS_RE.findall(title)) >= 2:
        return False
    if any(fragment in title for fragment in _OCR_PROSE_FRAGMENTS):
        return False
    return True


def prepare_single_image_batch_guard() -> None:
    """Filter obvious OCR prose before one image is treated as a book batch.

    Multi-image captures remain unchanged. For a single screenshot, only
    plausible compact book titles may contribute to the "2+ books" threshold.
    If filtering leaves fewer than two mentions, the batch handler returns
    False and the normal single-book OCR + edition-resolution path takes over.
    """

    global _PREPARED
    if _PREPARED:
        return

    from douban_weread import feishu_hybrid_batch as hybrid

    original = hybrid.mentions_from_message

    async def guarded_mentions(channel, message, recognizer):
        mentions = await original(channel, message, recognizer)
        if _image_resource_count(message) != 1 or len(mentions) < 2:
            return mentions
        return tuple(
            mention
            for mention in mentions
            if _credible_single_image_batch_title(getattr(mention, "title", ""))
        )

    hybrid.mentions_from_message = guarded_mentions
    _PREPARED = True
