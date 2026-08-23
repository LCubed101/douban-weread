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
    """Persist unavailable or not-yet-exposed WeRead availability watches.

    ``UNAVAILABLE`` means an official same-Work WeRead Edition was found but is
    currently unreadable. ``NOT_FOUND`` is stored as a weaker watch: no WeRead
    bookId is asserted, and later checks must rediscover the Work by the normal
    bounded title + ISBN lookup. Readable results are never queued.

    Returns a user-facing suffix. Persistence failure must never change an
    already-verified Douban write result into a failed write.
    """
    if result.kind not in {WeReadLookupKind.UNAVAILABLE, WeReadLookupKind.NOT_FOUND}:
        return None

    weread = result.selected_edition if result.kind is WeReadLookupKind.UNAVAILABLE else None
    deep_link = result.deep_link if result.kind is WeReadLookupKind.UNAVAILABLE else None
    try:
        store.add_or_refresh(
            chat_id=chat_id,
            source=source,
            weread=weread,
            deep_link=deep_link,
        )
    except (ValueError, OSError, sqlite3.Error):
        return "等待上架记录暂时保存失败；豆瓣状态已经确认，不需要重复操作。"

    if result.kind is WeReadLookupKind.NOT_FOUND:
        return (
            "已加入「等待上架」列表（弱匹配）。当前官方微信读书接口还没有暴露可确认的同 Work 版本；"
            "后续会继续按标题 + ISBN 重新检查。"
        )
    return "已加入「等待上架」列表。后续可用 `douban-weread weread watch check` 重新检查。"
