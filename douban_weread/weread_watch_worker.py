from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from douban_weread.inbox_weread import WeReadEditionLookup, WeReadLookupKind
from douban_weread.providers.weread import WeReadClient
from douban_weread.storage.weread_watch import WeReadAvailabilityWatchStore


class ShelfProvider(Protocol):
    def sync_shelf(self): ...


@dataclass(slots=True, frozen=True)
class WeReadWatchNotification:
    entry_id: int
    chat_id: str
    text: str


class WeReadWatchWorker:
    """Read-only availability checker that emits durable notification intents."""

    def __init__(
        self,
        *,
        store: WeReadAvailabilityWatchStore | None = None,
        lookup: WeReadEditionLookup | None = None,
        shelf_provider: ShelfProvider | None = None,
    ) -> None:
        self.store = store or WeReadAvailabilityWatchStore()
        self.lookup = lookup or WeReadEditionLookup()
        self.shelf_provider = shelf_provider or getattr(self.lookup, "provider", None)

    def run_once(self) -> list[WeReadWatchNotification]:
        for entry in self.store.pending():
            result = self.lookup.lookup(entry.source_edition())
            if result.kind not in {WeReadLookupKind.EXACT, WeReadLookupKind.ALTERNATIVE}:
                continue
            selected = result.selected_edition
            if selected is None or not selected.weread_id:
                continue
            self.store.mark_available(
                entry.id,
                weread=selected,
                deep_link=result.deep_link,
            )

        available_entries = self.store.unnotified_available()
        if not available_entries:
            return []

        shelf_ids: set[str] | None = None
        if self.shelf_provider is not None:
            snapshot = self.shelf_provider.sync_shelf()
            shelf_ids = {book.book_id for book in snapshot.books}

        notifications: list[WeReadWatchNotification] = []
        for entry in available_entries:
            on_shelf = (
                entry.weread_book_id in shelf_ids
                if shelf_ids is not None and entry.weread_book_id is not None
                else None
            )
            notifications.append(
                WeReadWatchNotification(
                    entry_id=entry.id,
                    chat_id=entry.chat_id,
                    text=_notification_text(entry, on_shelf=on_shelf),
                )
            )
        return notifications

    def acknowledge(self, notification: WeReadWatchNotification) -> None:
        self.store.mark_notified(notification.entry_id)


def _notification_text(entry, *, on_shelf: bool | None) -> str:
    title = entry.weread_title or entry.source_title
    lines = [f"《{entry.source_title}》在微信读书已经可以读了 🎉"]
    if title != entry.source_title:
        lines.append(f"可读版本：{title}")
    if on_shelf is True:
        lines.append("已检测到这个版本在你的微信读书书架中。")
    elif on_shelf is False:
        lines.append("暂未检测到这个版本在你的微信读书书架中。")
    else:
        lines.append("暂时无法确认它是否已经在你的微信读书书架中。")
    if entry.deep_link:
        lines.append(f"打开微信读书：{entry.deep_link}")
    return "\n".join(lines)
