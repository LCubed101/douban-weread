from __future__ import annotations

import sqlite3
from typing import Protocol

from douban_weread.core.models import Edition
from douban_weread.inbox_weread import WeReadLookupKind, WeReadLookupResult
from douban_weread.storage.weread_watch import WeReadAvailabilityWatchStore


class WeReadWatchStoreLike(Protocol):
    def add_or_refresh(
        self,
        *,
        chat_id: str,
        source: Edition,
        weread: Edition | None,
        deep_link: str | None,
        watch_kind: str | None = None,
    ): ...


def default_watch_store() -> WeReadAvailabilityWatchStore:
    return WeReadAvailabilityWatchStore()


def record_unavailable_watch(
    *,
    chat_id: str,
    source: Edition,
    result: WeReadLookupResult,
    store: WeReadWatchStoreLike,
) -> str | None:
    """Persist unavailable/not-found WeRead items with a durable recheck cadence."""
    if result.kind not in {WeReadLookupKind.UNAVAILABLE, WeReadLookupKind.NOT_FOUND}:
        return None

    waiting = result.kind is WeReadLookupKind.UNAVAILABLE
    weread = result.selected_edition if waiting else None
    deep_link = result.deep_link if waiting else None
    watch_kind = "waiting" if waiting else "not_found"
    try:
        entry = store.add_or_refresh(
            chat_id=chat_id,
            source=source,
            weread=weread,
            deep_link=deep_link,
            watch_kind=watch_kind,
        )
    except (ValueError, OSError, sqlite3.Error):
        return "等待上架记录暂时保存失败；当前查询结果不受影响。"

    due = getattr(entry, "next_check_at", None)
    due_text = f"下次计划检查：{str(due)[:10]}。" if due else ""
    if waiting:
        return f"已加入「等待上架」列表；预计 30 天后重新检查。{due_text}"
    return f"已加入「等待上架」列表（当前未找到）；预计 90 天后重新搜索。{due_text}"
