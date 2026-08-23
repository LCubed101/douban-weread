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
    "书展",
    "首发",
    "出版社",
    "出版",
    "推荐",
    "作者",
    "著",
    "编著",
    "译",
)

# A single OCR line without ISBN / 《》 must clear this threshold before
# it is trusted enough to trigger a Douban title lookup.
_MIN_UNQUOTED_TITLE_SCORE = 24


@dataclass(slots=True, frozen=True)
class OcrBookHint:
    isbn: str | None = None
    title: str | None = None
    lines: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return bool(self.isbn or self.title)


def extract_book_hint(
    text_list: list[str] | tuple[str, ...],
) -> OcrBookHint:
    """Extract a conservative ISBN/title hint from OCR text.

    Evidence priority:

    1. ISBN
    2. Explicit title enclosed by 《》
    3. One high-confidence standalone title-like OCR line

    Ambiguous cover fragments are deliberately rejected instead of being
    sent to Douban as if they were a reliable title.
    """

    lines = tuple(
        normalized
        for line in text_list
        if (normalized := _normalize_line(line))
    )

    if not lines:
        return OcrBookHint(lines=())

    # ISBN is the strongest automatic identity signal.
    isbn = extract_isbn("\n".join(lines))
    if isbn:
        return OcrBookHint(isbn=isbn, lines=lines)

    # Explicit Chinese book-title quotes are strong title evidence.
    joined = "\n".join(lines)
    quoted = _BOOK_QUOTE_RE.search(joined)

    if quoted:
        title = _clean_title(quoted.group(1))

        if _plausible_title(title):
            return OcrBookHint(title=title, lines=lines)

    candidates = [
        _clean_title(line)
        for line in lines
        if _plausible_title(line)
    ]

    if not candidates:
        return OcrBookHint(lines=lines)

    scored = sorted(
        ((_title_score(candidate), candidate) for candidate in candidates),
        reverse=True,
    )

    best_score, best_title = scored[0]

    # Do not automatically search Douban from weak OCR fragments.
    if best_score < _MIN_UNQUOTED_TITLE_SCORE:
        return OcrBookHint(lines=lines)

    # If the two strongest candidates are close, OCR is ambiguous.
    # Failing closed is preferable to returning unrelated Douban editions.
    if len(scored) >= 2:
        second_score, _ = scored[1]

        if best_score - second_score < 4:
            return OcrBookHint(lines=lines)

    return OcrBookHint(
        title=best_title,
        lines=lines,
    )


def _normalize_line(value: str) -> str:
    return " ".join(str(value).split()).strip()


def _clean_title(value: str) -> str:
    return value.strip(
        " \t\n《》“”\"'：:，,。.!！?？—-·"
    )


def _plausible_title(value: str) -> bool:
    text = _clean_title(value)

    # Very short lines are frequently author names, labels, or fragments.
    if not 4 <= len(text) <= 24:
        return False

    lowered = text.casefold()

    if (
        "http://" in lowered
        or "https://" in lowered
        or "www." in lowered
    ):
        return False

    if any(fragment in text for fragment in _NOISY_FRAGMENTS):
        return False

    punctuation_count = sum(
        1
        for char in text
        if char in "，。！？；;,.!?：:"
    )

    if punctuation_count >= 2:
        return False

    han_count = len(_HAN_RE.findall(text))
    latin_count = sum(
        char.isalpha() and ord(char) < 128
        for char in text
    )

    if han_count < 4 and latin_count < 5:
        return False

    if text.isdigit():
        return False

    return True


def _title_score(value: str) -> int:
    text = _clean_title(value)

    han_count = len(_HAN_RE.findall(text))
    latin_count = sum(
        char.isalpha() and ord(char) < 128
        for char in text
    )

    punctuation_penalty = sum(
        1
        for char in text
        if not (
            char.isalnum()
            or _HAN_RE.match(char)
            or char in "·—-"
        )
    )

    length = len(text)

    # Book-cover titles are commonly compact.
    # Strongly prefer 4–12 characters and penalize prose-like long lines.
    if 4 <= length <= 12:
        length_adjustment = 30
    elif 13 <= length <= 18:
        length_adjustment = 5
    else:
        length_adjustment = -30

    return (
        han_count * 2
        + min(latin_count, 10)
        + length_adjustment
        - punctuation_penalty * 3
    )
