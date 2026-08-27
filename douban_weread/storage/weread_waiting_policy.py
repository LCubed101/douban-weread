from __future__ import annotations

from datetime import datetime, timedelta, timezone

WAITING_RECHECK_DAYS = 30
NOT_FOUND_RECHECK_DAYS = 90


def next_check_at(*, watch_kind: str, now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    days = WAITING_RECHECK_DAYS if watch_kind == "waiting" else NOT_FOUND_RECHECK_DAYS
    return (current + timedelta(days=days)).isoformat()
