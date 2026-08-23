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
    """Persist only confirmed unavailable same-Work results.

    Returns a user-facing suffix. Persistence failure must never change the
    already-verified Douban write result into a failed write.
    """
    if result.kind is not WeReadLookupKind.UNAVAILABLE:
        return None
    try:
        store.add_or_refresh(
            chat_id=chat_id,
            source=source,
            weread=result.selected_edition,
            deep_link=result.deep_link,
        )
    except (ValueError, OSError, sqlite3.Error):
        return "等待上架记录暂时保存失败；豆瓣写入已经完成，不需要重复操作。"
    return "已加入「等待上架」列表。后续可用 `douban-weread weread watch check` 重新检查。"
