from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class WeReadStatus(str, Enum):
    AVAILABLE_EXACT = "available_exact"
    AVAILABLE_ALTERNATIVE = "available_alternative"
    UNAVAILABLE = "unavailable"
    COMING_SOON = "coming_soon"
    NOT_FOUND = "not_found"


class EditionResolution(str, Enum):
    EXACT_MATCH = "exact_match"
    ALTERNATIVE_EDITION = "alternative_edition"
    USER_SELECTED = "user_selected"
    NO_WEREAD_EDITION = "no_weread_edition"


@dataclass(slots=True)
class Work:
    canonical_title: str
    authors: list[str] = field(default_factory=list)
    original_title: Optional[str] = None
    language: Optional[str] = None


@dataclass(slots=True)
class Edition:
    title: str
    authors: list[str] = field(default_factory=list)
    translators: list[str] = field(default_factory=list)
    publisher: Optional[str] = None
    publish_date: Optional[str] = None
    isbn: Optional[str] = None
    language: Optional[str] = None
    cover_url: Optional[str] = None
    douban_id: Optional[str] = None
    weread_id: Optional[str] = None
    source_metadata: dict[str, object] = field(default_factory=dict, repr=False)


@dataclass(slots=True)
class ReadingIntent:
    work: Work
    source_edition: Edition
    selected_edition: Optional[Edition] = None
    weread_status: WeReadStatus = WeReadStatus.NOT_FOUND
    resolution: EditionResolution = EditionResolution.NO_WEREAD_EDITION
    source: Optional[str] = None
    source_url: Optional[str] = None
    confidence: Optional[float] = None
    notes: list[str] = field(default_factory=list)

    def align_to(self, edition: Edition, resolution: EditionResolution) -> None:
        self.selected_edition = edition
        self.resolution = resolution
