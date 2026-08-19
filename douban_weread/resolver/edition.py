from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Iterable

from douban_weread.core.models import Edition


class MatchKind(str, Enum):
    EXACT_EDITION = "exact_edition"
    LIKELY_SAME_EDITION = "likely_same_edition"
    ALTERNATIVE_EDITION = "alternative_edition"
    AMBIGUOUS = "ambiguous"
    DIFFERENT_WORK = "different_work"


@dataclass(slots=True)
class EditionMatchResult:
    candidate: Edition
    score: float
    kind: MatchKind
    same_work: bool
    exact_edition: bool
    requires_confirmation: bool
    safe_to_auto_apply: bool
    reasons: list[str] = field(default_factory=list)
    edition_differences: list[str] = field(default_factory=list)
    material_differences: list[str] = field(default_factory=list)


_BRACKET_PREFIX_RE = re.compile(r"^(?:\[[^\]]+\]|【[^】]+】|（[^）]+）|\([^\)]+\))\s*")
_NON_WORD_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)
_EDITION_MARKERS = {
    "abridged": ("节译", "缩写", "abridged"),
    "revised": ("修订版", "修订", "增订版", "增订", "revised", "updated edition"),
    "annotated": ("注释版", "评注版", "评注", "annotated"),
}


def _norm_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold().strip()
    return _NON_WORD_RE.sub("", text)


def _title_for_work(value: str) -> str:
    """Remove edition-only markers before comparing underlying works."""
    text = unicodedata.normalize("NFKC", value).casefold()
    aliases = sorted(
        {alias.casefold() for group in _EDITION_MARKERS.values() for alias in group},
        key=len,
        reverse=True,
    )
    for alias in aliases:
        text = text.replace(alias, " ")
    return _norm_text(text)


def _norm_person(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).strip()
    while True:
        stripped = _BRACKET_PREFIX_RE.sub("", text)
        if stripped == text:
            break
        text = stripped.strip()
    return _norm_text(text)


def _norm_people(values: Iterable[str]) -> set[str]:
    return {name for value in values if (name := _norm_person(value))}


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _title_similarity(left: str, right: str) -> float:
    a, b = _title_for_work(left), _title_for_work(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _publish_year(value: str | None) -> str | None:
    match = re.search(r"\b(\d{4})\b", value or "")
    return match.group(1) if match else None


def _edition_markers(title: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", title).casefold()
    return {
        marker
        for marker, aliases in _EDITION_MARKERS.items()
        if any(alias.casefold() in normalized for alias in aliases)
    }


def compare_editions(source: Edition, candidate: Edition) -> EditionMatchResult:
    """Compare two editions and return an explainable, conservative match result.

    Only an exact ISBN match is considered safe for automatic state-changing
    actions. Known differences in ISBN, publisher, or publication year identify
    a different Edition of the same Work, but do not by themselves require
    confirmation. Translator, language, and revision/content markers are
    material differences and do require confirmation.
    """

    reasons: list[str] = []
    edition_differences: list[str] = []
    material: list[str] = []

    source_isbn = _norm_text(source.isbn)
    candidate_isbn = _norm_text(candidate.isbn)
    if source_isbn and candidate_isbn and source_isbn == candidate_isbn:
        return EditionMatchResult(
            candidate=candidate,
            score=1.0,
            kind=MatchKind.EXACT_EDITION,
            same_work=True,
            exact_edition=True,
            requires_confirmation=False,
            safe_to_auto_apply=True,
            reasons=["exact ISBN match"],
        )
    if source_isbn and candidate_isbn and source_isbn != candidate_isbn:
        edition_differences.append("ISBN differs")
        reasons.append("ISBN differs")

    title_similarity = _title_similarity(source.title, candidate.title)
    source_authors = _norm_people(source.authors)
    candidate_authors = _norm_people(candidate.authors)
    author_overlap = _overlap(source_authors, candidate_authors)

    score = 0.35 * title_similarity + 0.30 * author_overlap
    reasons.append(f"work-title similarity {title_similarity:.2f}")
    if author_overlap:
        reasons.append(f"author overlap {author_overlap:.2f}")

    source_translators = _norm_people(source.translators)
    candidate_translators = _norm_people(candidate.translators)
    if source_translators and candidate_translators:
        translator_overlap = _overlap(source_translators, candidate_translators)
        if translator_overlap:
            score += 0.15 * translator_overlap
            reasons.append(f"translator overlap {translator_overlap:.2f}")
        else:
            material.append("translator differs")

    source_publisher = _norm_text(source.publisher)
    candidate_publisher = _norm_text(candidate.publisher)
    if source_publisher and candidate_publisher:
        if source_publisher == candidate_publisher:
            score += 0.08
            reasons.append("publisher matches")
        else:
            edition_differences.append("publisher differs")
            reasons.append("publisher differs")

    source_year = _publish_year(source.publish_date)
    candidate_year = _publish_year(candidate.publish_date)
    if source_year and candidate_year:
        if source_year == candidate_year:
            score += 0.07
            reasons.append("publication year matches")
        else:
            edition_differences.append("publication year differs")
            reasons.append("publication year differs")

    source_language = _norm_text(source.language)
    candidate_language = _norm_text(candidate.language)
    if source_language and candidate_language:
        if source_language == candidate_language:
            score += 0.05
            reasons.append("language matches")
        else:
            material.append("language differs")

    source_markers = _edition_markers(source.title)
    candidate_markers = _edition_markers(candidate.title)
    if source_markers != candidate_markers and (source_markers or candidate_markers):
        material.append("revision/abridgement/annotation markers differ")

    score = round(min(score, 0.99), 4)

    # A title match alone is never sufficient to conclude that two records are
    # the same work. We require meaningful author evidence as well.
    same_work = title_similarity >= 0.88 and author_overlap > 0

    if not same_work:
        kind = (
            MatchKind.DIFFERENT_WORK
            if title_similarity >= 0.88 and source_authors and candidate_authors
            else MatchKind.AMBIGUOUS
        )
        return EditionMatchResult(
            candidate=candidate,
            score=score,
            kind=kind,
            same_work=False,
            exact_edition=False,
            requires_confirmation=True,
            safe_to_auto_apply=False,
            reasons=reasons,
            edition_differences=edition_differences,
            material_differences=material,
        )

    if material:
        kind = MatchKind.ALTERNATIVE_EDITION
        requires_confirmation = True
    elif edition_differences:
        kind = MatchKind.ALTERNATIVE_EDITION
        requires_confirmation = False
    elif score >= 0.70:
        kind = MatchKind.LIKELY_SAME_EDITION
        requires_confirmation = False
    else:
        kind = MatchKind.ALTERNATIVE_EDITION
        requires_confirmation = False

    return EditionMatchResult(
        candidate=candidate,
        score=score,
        kind=kind,
        same_work=True,
        exact_edition=False,
        requires_confirmation=requires_confirmation,
        safe_to_auto_apply=False,
        reasons=reasons,
        edition_differences=edition_differences,
        material_differences=material,
    )


def rank_editions(source: Edition, candidates: Iterable[Edition]) -> list[EditionMatchResult]:
    """Rank candidates from safest/best match to weakest match."""
    results = [compare_editions(source, candidate) for candidate in candidates]
    return sorted(
        results,
        key=lambda item: (
            item.exact_edition,
            item.same_work,
            not item.requires_confirmation,
            item.score,
        ),
        reverse=True,
    )
