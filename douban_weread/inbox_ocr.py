from __future__ import annotations

import re
from dataclasses import dataclass

from douban_weread.inbox import extract_isbn


_BOOK_QUOTE_RE = re.compile(r"《([^《》]{2,40})》")
_HAN_RE = re.compile(r"[\u4e00-\u9fff]")
_NOISY_FRAGMENTS = (
    "微信",
    "回复",
    "评论",
    "转发",
    "点赞",
    "收藏",
    "关注",
    "阅读",
    "展开",
    "全文",
    "扫码",
)


@dataclass(slots=True, frozen=True)
class OcrBookHint:
    isbn: str | None = None
    title: str | None = None
    lines: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return bool(self.isbn or self.title)


def extract_book_hint(text_list: list[str] | tuple[str, ...]) -> OcrBookHint:
    """Extract a conservative ISBN/title hint from OCR text.

    ISBN is always preferred. Title extraction intentionally avoids long prose,
    UI labels, URLs, and punctuation-heavy sentences. A hint is only for
    downstream candidate lookup; it never authorizes a state-changing action.
    """

    lines = tuple(_normalize_line(line) for line in text_list if _normalize_line(line))
    if not lines:
        return OcrBookHint(lines=())

    isbn = extract_isbn("\n".join(lines))
    if isbn:
        return OcrBookHint(isbn=isbn, lines=lines)

    joined = "\n".join(lines)
    quoted = _BOOK_QUOTE_RE.search(joined)
    if quoted:
        title = _clean_title(quoted.group(1))
        if _plausible_title(title):
            return OcrBookHint(title=title, lines=lines)

    candidates = [line for line in lines if _plausible_title(line)]
    if not candidates:
        return OcrBookHint(lines=lines)

    candidates.sort(key=_title_score, reverse=True)
    return OcrBookHint(title=_clean_title(candidates[0]), lines=lines)


def _normalize_line(value: str) -> str:
    return " ".join(str(value).split()).strip()


def _clean_title(value: str) -> str:
    return value.strip(" \t\n《》“”\"'：:，,。.!！?？—-·")


def _plausible_title(value: str) -> bool:
    text = _clean_title(value)
    if not 2 <= len(text) <= 30:
        return False
    lowered = text.casefold()
    if "http://" in lowered or "https://" in lowered or "www." in lowered:
        return False
    if any(fragment in text for fragment in _NOISY_FRAGMENTS):
        return False
    if sum(1 for char in text if char in "，。！？；;,.!?：:") >= 2:
        return False
    han_count = len(_HAN_RE.findall(text))
    latin_count = sum(char.isalpha() and ord(char) < 128 for char in text)
    if han_count < 2 and latin_count < 4:
        return False
    if text.isdigit():
        return False
    return True


def _title_score(value: str) -> tuple[int, int, int]:
    text = _clean_title(value)
    han_count = len(_HAN_RE.findall(text))
    # Prefer compact book-title-like lines. OCR cover titles are commonly short
    # and mostly Chinese; long prose should lose even when it has many Han chars.
    compact_bonus = 30 - min(len(text), 30)
    punctuation_penalty = sum(1 for char in text if not (char.isalnum() or _HAN_RE.match(char)))
    return (han_count + compact_bonus - punctuation_penalty * 2, -len(text), han_count)
