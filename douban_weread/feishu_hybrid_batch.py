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


def _main_title(value: str) -> str | None:
    """Return a conservative main-title fallback for `主标题：副标题` mentions."""

    title = str(value or "").strip()
    for separator in ("：", ":"):
        if separator not in title:
            continue
        main, subtitle = title.split(separator, 1)
        main = main.strip()
        subtitle = subtitle.strip()
        if len(main) >= 2 and subtitle:
            return main
    return None


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


def _pick_douban_candidate(
    resolution: object,
    mention_title: str,
    weread_result: object | None = None,
) -> Edition | None:
    """Pick a Douban edition without making WeRead a prerequisite."""

    kind = getattr(resolution, "kind", None)
    if kind is BookInboxResolutionKind.CONFIRM:
        confirmation = getattr(resolution, "confirmation", None)
        return getattr(confirmation, "candidate", None)
    if kind is not BookInboxResolutionKind.MULTIPLE_CANDIDATES:
        return None

    candidates = tuple(getattr(resolution, "candidates", ()) or ())
    if not candidates:
        return None

    exact = [candidate for candidate in candidates if _norm(candidate.title) == _norm(mention_title)]
    pool = exact or list(candidates)
    if len(pool) == 1:
        return pool[0]

    weread_edition = getattr(weread_result, "selected_edition", None)
    if weread_edition is not None:
        scored = [(candidate, _candidate_score(candidate, weread_edition)) for candidate in pool]
        best_score = max(score for _candidate, score in scored)
        best = [candidate for candidate, score in scored if score == best_score]
        if best_score >= 8 and len(best) == 1:
            return best[0]

    if exact:
        return exact[0]
    return None


def _compact_batch_card(
    *,
    mentions,
    douban_outcomes: list[_DoubanBatchOutcome],
    weread_results,
    watch_store: object | None,
) -> dict[str, object]:
    douban_ok = [o for o in douban_outcomes if o.status in {"written", "already"}]
    douban_attention = [o for o in douban_outcomes if o.status not in {"written", "already"}]

    available = []
    waiting = []
    not_found = []
    failed = []
    for mention, result, error in weread_results:
        if error is not None or result is None:
            failed.append((mention, result))
            continue
        kind = getattr(result, "kind", None)
        if kind in {WeReadLookupKind.EXACT, WeReadLookupKind.ALTERNATIVE}:
            available.append((mention, result))
        elif kind is WeReadLookupKind.UNAVAILABLE:
            waiting.append((mention, result))
        else:
            not_found.append((mention, result))

    unavailable = waiting + not_found + failed
    elements: list[dict[str, object]] = [
        {
            "tag": "markdown",
            "content": (
                f"📚 **{len(mentions)} 本**\n"
                f"豆瓣：✅ 想读 {len(douban_ok)}/{len(mentions)}\n"
                f"微信读书：✅ 可读 {len(available)} · 🔍 暂无 {len(unavailable)}"
            ),
        }
    ]

    if douban_attention:
        elements.append({"tag": "hr"})
        lines = ["**⚠️ 豆瓣未完成**"]
        for outcome in douban_attention:
            suffix = f" · {outcome.detail}" if outcome.detail else ""
            lines.append(f"《{outcome.title}》{suffix}")
        elements.append({"tag": "markdown", "content": "\n".join(lines)})

    if available:
        elements.append({"tag": "hr"})
        elements.append({"tag": "markdown", "content": "**✅ 微信读书可读**"})
        for mention, result in available:
            elements.append({"tag": "markdown", "content": f"《{mention.title}》"})
            deep_link = str(getattr(result, "deep_link", "") or "").strip()
            if deep_link:
                elements.append(
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": f"打开《{mention.title}》"},
                                "type": "primary",
                                "url": deep_link,
                            }
                        ],
                    }
                )

    if unavailable:
        elements.append({"tag": "hr"})
        titles = "、".join(f"《{mention.title}》" for mention, _result in unavailable)
        content = f"**🔍 微信读书暂时没有**\n{titles}"
        if watch_store is not None:
            content += "\n已帮你记住，之后会自动重搜。"
        elements.append({"tag": "markdown", "content": content})
        if watch_store is not None:
            elements.append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看等待列表"},
                            "type": "default",
                            "value": {"action": "show_waiting_list"},
                        }
                    ],
                }
            )

    return {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {
            "title": {"tag": "plain_text", "content": "书单已处理"},
            "template": "green" if douban_ok else "blue",
        },
        "elements": elements,
    }


def prepare_hybrid_batch_douban() -> None:
    """Use Douban as the primary destination for hybrid multi-book captures."""

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
                {"text": f"收到 {image_count} 张图片，但没有识别到明确的《书名》。可以换更清晰的截图。"},
                {"reply_to": message.message_id},
            )
            return True

        candidate_store.clear(message.chat_id)

        async def sync_douban(mention):
            try:
                resolution = await asyncio.to_thread(service.resolve, request_from_text(mention.title))
                candidate = _pick_douban_candidate(resolution, mention.title)

                # Some sources include a subtitle in the captured title while
                # Douban stores that subtitle separately. Only after the full
                # title fails do one conservative `主标题：副标题` fallback.
                if candidate is None:
                    main_title = _main_title(mention.title)
                    if main_title:
                        fallback_resolution = await asyncio.to_thread(
                            service.resolve,
                            request_from_text(main_title),
                        )
                        candidate = _pick_douban_candidate(fallback_resolution, main_title)

                if candidate is None:
                    return _DoubanBatchOutcome(mention.title, "unresolved", "没有安全匹配到豆瓣版本")
                subject_id = str(candidate.douban_id or "").strip()
                if not subject_id:
                    return _DoubanBatchOutcome(mention.title, "unresolved", "豆瓣条目缺少 ID")
                result = await asyncio.to_thread(flow.commit, subject_id)
                if result.kind is WishFlowKind.WRITTEN:
                    return _DoubanBatchOutcome(mention.title, "written")
                if result.kind is WishFlowKind.ALREADY_WISH or _is_same_work_existing_wish(result):
                    return _DoubanBatchOutcome(mention.title, "already")
                return _DoubanBatchOutcome(mention.title, "blocked", "已有阅读状态需要确认")
            except WISH_FLOW_ERRORS:
                return _DoubanBatchOutcome(mention.title, "failed", "豆瓣暂时无法写入")

        douban_outcomes = list(await asyncio.gather(*(sync_douban(mention) for mention in mentions)))

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

        await channel.send(
            message.chat_id,
            {
                "card": _compact_batch_card(
                    mentions=mentions,
                    douban_outcomes=douban_outcomes,
                    weread_results=weread_results,
                    watch_store=weread_watch_store,
                )
            },
            {"reply_to": message.message_id},
        )
        return True

    v11._try_handle_multi_book_message = hybrid_batch_handler
