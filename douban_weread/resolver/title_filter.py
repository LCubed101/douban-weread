from __future__ import annotations

import re
import unicodedata
from typing import Sequence

from douban_weread.core.models import Edition

# Characters that plausibly separate a work's main title from a genuine
# subtitle or edition annotation (colon, dash, bracket, whitespace, ...).
# A candidate title is only accepted as a *prefix* match when the query is
# immediately followed by one of these, never by a bare digit/letter — that
# distinguishes "变量：如何应对不确定的未来" (same work, annotated) from
# "变量2" / "变量7" / "变量8" (a different, sequel-numbered work).
_BOUNDARY_CHARS = set(" 　:：-—－·,，。.、()（）[]【】《》")

# After the boundary, a remainder made up entirely of numerals/counters is
# volume-numbering evidence, not a subtitle, even if separated by a space
# (e.g. "变量 2"). Reject those too.
_VOLUME_SUFFIX_RE = re.compile(
    r"^[\s:：\-—－·,，。.、()（）\[\]【】《》]*"
    r"[0-9一二三四五六七八九十ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+"
    r"[部卷季辑册]?"
    r"[\s:：\-—－·,，。.、()（）\[\]【】《》]*$"
)


def _normalize(value: str | None) -> str:
    return unicodedata.normalize("NFKC", value or "").casefold().strip()


def is_same_work_title(query: str, candidate_title: str) -> bool:
    """Strict, evidence-based check that ``candidate_title`` is the same work.

    This is intentionally narrower than substring/prefix matching. It accepts:

    - an exact match (after normalizing whitespace/full-width punctuation), or
    - the query as a leading segment of the candidate title, immediately
      followed by a subtitle/edition-marker boundary (colon, dash, bracket,
      space, ...) — e.g. query ``变量`` matching ``变量：橡树书屋沉思录``.

    It rejects:

    - candidates that do not start with the query at all (e.g. ``情绪``), and
    - a prefix match immediately followed by a digit/letter or by a
      boundary-then-bare-number (e.g. ``变量2``, ``变量7``, ``变量8``,
      ``变量 2``), since that is evidence of a distinct, sequel-numbered work
      rather than the same work.
    """
    q = _normalize(query)
    c = _normalize(candidate_title)
    if not q or not c:
        return False
    if q == c:
        return True
    if not c.startswith(q):
        return False

    remainder = c[len(q) :]
    if not remainder:
        return True
    if remainder[0] not in _BOUNDARY_CHARS:
        return False
    if _VOLUME_SUFFIX_RE.match(remainder):
        return False
    return True


def filter_title_candidates(query: str, candidates: Sequence[Edition]) -> list[Edition]:
    """Keep only candidates with clear title evidence of being the same work.

    Fails closed: candidates without strong title evidence are dropped rather
    than padded in to reach a target list size. Call sites must treat an
    empty result the same as "not found" instead of falling back to
    unfiltered candidates.
    """
    return [candidate for candidate in candidates if is_same_work_title(query, candidate.title)]
