from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from douban_weread.core.models import (
    Edition,
    EditionResolution,
    ReadingIntent,
    WeReadStatus,
    Work,
)
from douban_weread.providers.weread import WeReadSearchCandidate
from douban_weread.resolver import EditionMatchResult, compare_editions


class WeReadCatalogClient(Protocol):
    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]: ...

    def get_book(self, book_id: str) -> Edition | None: ...


@dataclass(slots=True)
class WeReadAlignmentResult:
    intent: ReadingIntent
    candidate: WeReadSearchCandidate | None = None
    match: EditionMatchResult | None = None
    examined_candidates: int = 0


def align_to_weread(
    source_edition: Edition,
    client: WeReadCatalogClient,
    *,
    limit: int = 5,
) -> WeReadAlignmentResult:
    """Resolve one Douban/source Edition against bounded official WeRead search.

    Search is deliberately bounded. `NOT_FOUND` therefore means no same-Work
    candidate was resolved within the configured search window, not proof that
    the entire WeRead catalog lacks the Work.

    A search candidate with ``soldout=1`` is preserved as `UNAVAILABLE` rather
    than being mislabeled `NOT_FOUND`. Positive availability requires both a
    same-Work resolver result and ``soldout=0`` search evidence.
    """

    bounded_limit = max(1, min(limit, 100))
    intent = ReadingIntent(
        work=Work(
            canonical_title=source_edition.title,
            authors=list(source_edition.authors),
            language=source_edition.language,
        ),
        source_edition=source_edition,
        source="weread_official",
    )

    candidates = client.search_books(source_edition.title, count=bounded_limit)
    examined = 0
    best_available: tuple[WeReadSearchCandidate, Edition, EditionMatchResult] | None = None
    best_unavailable: tuple[WeReadSearchCandidate, Edition, EditionMatchResult] | None = None

    for candidate in candidates:
        edition = client.get_book(candidate.book_id)
        if edition is None:
            continue
        examined += 1

        match = compare_editions(source_edition, edition)
        if not match.same_work:
            continue

        if candidate.soldout:
            if best_unavailable is None or _rank_key(match) > _rank_key(best_unavailable[2]):
                best_unavailable = (candidate, edition, match)
            continue

        if match.exact_edition:
            return _build_positive_result(
                intent,
                candidate,
                edition,
                match,
                examined_candidates=examined,
            )

        if best_available is None or _rank_key(match) > _rank_key(best_available[2]):
            best_available = (candidate, edition, match)

    if best_available is not None:
        candidate, edition, match = best_available
        return _build_positive_result(
            intent,
            candidate,
            edition,
            match,
            examined_candidates=examined,
        )

    if best_unavailable is not None:
        candidate, edition, match = best_unavailable
        resolution = (
            EditionResolution.EXACT_MATCH
            if match.exact_edition
            else EditionResolution.ALTERNATIVE_EDITION
        )
        intent.align_to(edition, resolution)
        intent.weread_status = WeReadStatus.UNAVAILABLE
        intent.source_url = _candidate_url(candidate, edition)
        intent.confidence = match.score
        intent.notes.append(
            "A same-Work WeRead Edition was found, but search reported soldout=1; it is not treated as readable."
        )
        return WeReadAlignmentResult(
            intent=intent,
            candidate=candidate,
            match=match,
            examined_candidates=examined,
        )

    intent.weread_status = WeReadStatus.NOT_FOUND
    intent.resolution = EditionResolution.NO_WEREAD_EDITION
    intent.notes.append(
        f"No same-Work WeRead Edition was resolved within the first {len(candidates)} search candidates; "
        "NOT_FOUND is bounded by the configured search policy."
    )
    return WeReadAlignmentResult(intent=intent, examined_candidates=examined)


def _build_positive_result(
    intent: ReadingIntent,
    candidate: WeReadSearchCandidate,
    edition: Edition,
    match: EditionMatchResult,
    *,
    examined_candidates: int,
) -> WeReadAlignmentResult:
    if match.exact_edition:
        intent.weread_status = WeReadStatus.AVAILABLE_EXACT
        resolution = EditionResolution.EXACT_MATCH
    else:
        intent.weread_status = WeReadStatus.AVAILABLE_ALTERNATIVE
        resolution = EditionResolution.ALTERNATIVE_EDITION

    intent.align_to(edition, resolution)
    intent.source_url = _candidate_url(candidate, edition)
    intent.confidence = match.score
    intent.notes.append(
        "Availability is based on official WeRead catalog search reporting soldout=0 plus resolver-confirmed Work identity; "
        "it does not assert account-specific entitlement."
    )
    if match.requires_confirmation:
        intent.notes.append("The selected alternative Edition has material differences and still requires user confirmation.")

    return WeReadAlignmentResult(
        intent=intent,
        candidate=candidate,
        match=match,
        examined_candidates=examined_candidates,
    )


def _rank_key(match: EditionMatchResult) -> tuple[bool, bool, float]:
    return (match.exact_edition, not match.requires_confirmation, match.score)


def _candidate_url(candidate: WeReadSearchCandidate, edition: Edition) -> str | None:
    if candidate.deep_link:
        return candidate.deep_link
    deep_link = edition.source_metadata.get("deep_link")
    if isinstance(deep_link, str) and deep_link.strip():
        return deep_link.strip()
    return None
