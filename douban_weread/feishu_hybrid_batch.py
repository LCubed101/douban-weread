from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from douban_weread import feishu_bot as base
from douban_weread.core.models import Edition
from douban_weread.feishu_compact_douban import _is_same_work_existing_wish
from douban_weread.feishu_multi_image import _image_resource_count, mentions_from_message
from douban_weread.inbox import BookInboxResolutionKind, BookInboxService, request_from_text
from douban_weread.inbox_weread import WeReadLookupKind
from douban_weread.inbox_weread_watch import WeReadWatchStoreLike, record_unavailable_watch
from douban_weread.inbox_wish import DoubanWishFlow, WISH_FLOW_ERRORS, WishFlowKind
from douban_weread.providers.douban import DoubanBookSearchClient


@dataclass(slots=True)
class _DoubanBatchOutcome:
    title: str
    status: str
    detail: str | None = None


def _norm(value: str | None) -> str:
    return re.sub(r"[\W_]+", "", str(value or "")).casefold()


def _ym(value: str | None) -> str:
    text = str(value or "")
    match = re.search(r"(\d{4})[-/.年]?(\d{1,2})?", text)
    if not match:
        return ""
    month = match.group(2)
    return match.group(1) + (f"-{int(month):02d}" if month else "")


def _candidate_score(candidate: Edition, weread_edition: Edition | None) -> int:
    if weread_edition is None:
        return 0
    score = 0
    if candidate.isbn and weread_edition.isbn and _norm(candidate.isbn) == _norm(weread_edition.isbn):
        score += 100
    if _norm(candidate.title) == _norm(weread_edition.title):
        score += 2
    if candidate.publisher and weread_edition.publisher and _norm(candidate.publisher) == _norm(weread_edition.publisher):
        score += 8
    c_date, w_date = _ym(candidate.publish_date), _ym(weread_edition.publish_date)
    if c_date and w_date:
        if c_date == w_date:
            score += 8
        elif c_date[:4] == w_date[:4]:
            score += 3
    c_authors = {_norm(a) for a in candidate.authors if _norm(a)}
    w_authors = {_norm(a) for a in weread_edition.authors if _norm(a)}
    if c_authors and w_authors and c_authors.intersection(w_authors):
        score += 3
    return score


def _pick_douban_candidate(resolution: object, weread_result: object | None) -> Edition | None:
    kind = getattr(resolution, "kind", None)
    if kind is BookInboxResolutionKind.CONFIRM:
        confirmation = getattr(resolution, "confirmation", None)
        return getattr(confirmation, "candidate", None)
    if kind is not BookInboxResolutionKind.MULTIPLE_CANDIDATES:
        return None

    candidates = tuple(getattr(resolution, "candidates", ()) or ())
    if not candidates:
        return None
    weread_edition = getattr(weread_result, "selected_edition", None)
    scored = [(candidate, _candidate_score(candidate, weread_edition)) for candidate in candidates]
    best_score = max(score for _candidate, score in scored)
    best = [candidate for candidate, score in scored if score == best_score]
    # Only auto-select when WeRead metadata gives a unique, strong edition match.
    if best_score >= 8 and len(best) == 1:
        return best[0]
    return None


def _augment_card(card: dict[str, object], outcomes: list[_DoubanBatchOutcome]) -> dict[str, object]:
    synced = [o for o in outcomes if o.status in {"written", "already"}]
    unresolved = [o for o in outcomes if o.status == "unresolved"]
    blocked = [o for o in outcomes if o.status == "blocked"]
    failed = [o for o in outcomes if o.status == "failed"]

    elements = card.get("elements")
    if not isinstance(elements, list):
        return card

    summary = (
        f"豆瓣：✅ 已想读 {len(synced)} · 🟡 待确认 {len(unresolved)}"
        + (f" · ⚠️ 未同步 {len(blocked) + len(failed)}" if blocked or failed else "")
    )
    elements.insert(1, {"tag": "markdown", "content": summary})

    details: list[str] = []
    if synced:
        details.append("**✅ 豆瓣想读**")
        details.extend(f"《{o.title}》" for o in synced)
    if unresolved:
        if details:
            details.append("")
        details.append("**🟡 豆瓣版本待确认**")
        details.extend(f"《{o.title}》" for o in unresolved)
        details.append("单独发送书名即可选择版本。")
    if blocked or failed:
        if details:
            details.append("")
        details.append("**⚠️ 豆瓣未同步**")
        for outcome in blocked + failed:
            suffix = f" · {outcome.detail}" if outcome.detail else ""
            details.append(f"《{outcome.title}》{suffix}")

    if details:
        elements.append({"tag": "hr"})
        elements.append({"tag": "markdown", "content": "\n".join(details)})
    return card


def prepare_hybrid_batch_douban() -> None:
    """Add conservative Douban Want-to-Read sync to hybrid multi-book captures."""

    from douban_weread import feishu_bot_v11 as v11

    service = BookInboxService(DoubanBookSearchClient(), search_limit=5)
    flow = DoubanWishFlow()

    async def hybrid_batch_handler(
        channel: base.ChannelLike,
        message: base.InboundMessageLike,
        recognizer,
        weread_lookup: base.WeReadLookupLike | None,
        candidate_store: base.CandidateSelectionStore,
        weread_watch_store: WeReadWatchStoreLike | None = None,
    ) -> bool:
        if weread_lookup is None:
            return False

        image_count = _image_resource_count(message)
        mentions = await mentions_from_message(channel, message, recognizer)
        if len(mentions) < 2 and image_count < 2:
            return False
        if not mentions:
            await channel.send(
                message.chat_id,
                {"text": f"收到 {image_count} 张图片，但暂时没有识别到明确的《书名》。可以换更清晰的截图，或直接发送书名。"},
                {"reply_to": message.message_id},
            )
            return True

        candidate_store.clear(message.chat_id)
        weread_results = await v11._lookup_mentions(mentions, weread_lookup)

        for mention, result, error in weread_results:
            if error is not None or result is None:
                continue
            if (
                weread_watch_store is not None
                and getattr(result, "kind", None) in {WeReadLookupKind.UNAVAILABLE, WeReadLookupKind.NOT_FOUND}
            ):
                record_unavailable_watch(
                    chat_id=message.chat_id,
                    source=Edition(title=mention.title),
                    result=result,
                    store=weread_watch_store,
                )

        async def sync_one(item):
            mention, weread_result, _error = item
            try:
                resolution = await asyncio.to_thread(service.resolve, request_from_text(mention.title))
                candidate = _pick_douban_candidate(resolution, weread_result)
                if candidate is None:
                    return _DoubanBatchOutcome(mention.title, "unresolved")
                subject_id = str(candidate.douban_id or "").strip()
                if not subject_id:
                    return _DoubanBatchOutcome(mention.title, "unresolved")
                result = await asyncio.to_thread(flow.commit, subject_id)
                if result.kind is WishFlowKind.WRITTEN:
                    return _DoubanBatchOutcome(mention.title, "written")
                if result.kind is WishFlowKind.ALREADY_WISH or _is_same_work_existing_wish(result):
                    return _DoubanBatchOutcome(mention.title, "already")
                return _DoubanBatchOutcome(mention.title, "blocked", "已有阅读状态或版本关系需要人工确认")
            except WISH_FLOW_ERRORS:
                return _DoubanBatchOutcome(mention.title, "failed", "豆瓣暂时无法写入")

        douban_outcomes = list(await asyncio.gather(*(sync_one(item) for item in weread_results)))
        card = v11._batch_summary_card(
            mentions=mentions,
            outcomes=weread_results,
            chat_id=message.chat_id,
            watch_store=weread_watch_store,
        )
        _augment_card(card, douban_outcomes)
        await channel.send(
            message.chat_id,
            {"card": card},
            {"reply_to": message.message_id},
        )
        return True

    v11._try_handle_multi_book_message = hybrid_batch_handler
