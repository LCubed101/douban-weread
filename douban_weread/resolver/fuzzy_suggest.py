from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher
from typing import Sequence

from douban_weread.core.models import Edition

from .title_filter import is_same_work_title

# A candidate this close in character-edit distance to the query is treated
# as a plausible single-character-class typo (e.g. 斯 <-> 丝), not a
# different title. Calibrated against real cases: "阿纳斯塔夏" vs the real
# title "阿纳丝塔夏" scores 0.800; unrelated titles score far lower.
_MIN_RATIO = 0.78

# The top suggestion must clear the runner-up by this much, or there is no
# single obvious "did you mean" and the right answer is fail closed, not a
# best-effort guess between two similar-looking titles.
_MIN_MARGIN = 0.08

# Below this length, edit-distance ratios are too noisy to trust (a couple
# of shared characters in a 2-3 character title inflate the ratio a lot).
_MIN_TITLE_LENGTH = 3


def _normalize(value: str | None) -> str:
    return unicodedata.normalize("NFKC", value or "").casefold().strip()


def _is_prefix_relation(query: str, candidate_title: str) -> bool:
    """True when one normalized title is a leading prefix of the other.

    Prefix relations (变量 / 变量：副标题 / 变量2) are #74's title_filter's
    territory — either accepted there as same-work evidence, or explicitly
    rejected as a different, sequel-numbered work. This fuzzy layer must
    never re-litigate that decision by a different route: a candidate like
    变量2 must stay excluded here even though its raw string-similarity
    ratio to 变量 happens to be just as high as a genuine typo's.
    """
    q, c = _normalize(query), _normalize(candidate_title)
    if not q or not c:
        return False
    return q.startswith(c) or c.startswith(q)


def suggest_fuzzy_title_match(
    query: str, candidates: Sequence[Edition]
) -> Edition | None:
    """Return one high-confidence "did you mean" candidate, or None.

    This is a suggestion layer, not a relaxed resolver — the result must
    never be auto-committed by a caller. It only runs on candidates that
    #74's exact/same-work title filter (`is_same_work_title`) already
    rejected, and only ever returns a candidate when:

    - it is not in a prefix relation with the query (that's #74's job, not
      this layer's — see `_is_prefix_relation`);
    - its normalized-title similarity to the query is >= `_MIN_RATIO`;
    - it clearly beats every other candidate by >= `_MIN_MARGIN` (no close
      runner-up to be ambiguous about);
    - both titles are long enough (`_MIN_TITLE_LENGTH`) for the ratio to be
      meaningful.

    Any of those failing means fail closed: return None, exactly like an
    unmatched search today — never a best-effort guess.
    """

    query_norm = _normalize(query)
    if len(query_norm) < _MIN_TITLE_LENGTH:
        return None

    scored: list[tuple[Edition, float]] = []
    for candidate in candidates:
        title = candidate.title or ""
        if is_same_work_title(query, title):
            # Already exact/same-work evidence — not this layer's concern,
            # and conflating the two would blur "confirmed" with "guessed".
            continue
        if _is_prefix_relation(query, title):
            continue
        candidate_norm = _normalize(title)
        if len(candidate_norm) < _MIN_TITLE_LENGTH:
            continue
        ratio = SequenceMatcher(None, query_norm, candidate_norm).ratio()
        if ratio >= _MIN_RATIO:
            scored.append((candidate, ratio))

    if not scored:
        return None

    scored.sort(key=lambda item: item[1], reverse=True)
    best_candidate, best_ratio = scored[0]
    if len(scored) > 1:
        _runner_up, runner_up_ratio = scored[1]
        if best_ratio - runner_up_ratio < _MIN_MARGIN:
            # Two (or more) similarly-plausible typos — ambiguous, not a
            # single obvious "did you mean". Fail closed rather than pick.
            return None

    return best_candidate
