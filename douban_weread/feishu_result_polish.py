from __future__ import annotations

from typing import Any

from douban_weread import feishu_bot_context as context

_PREPARED = False
_ORIGINAL_WEREAD_LINK_CARD = context._weread_link_card


def _douban_status_header(text: str) -> str | None:
    if "已加入豆瓣想读" in text:
        return "✅ 已加入豆瓣想读"
    if "豆瓣已经是想读" in text or "同一作品的想读版本" in text:
        return "✅ 豆瓣已有想读记录"
    return None


def _result_card(text: str, deep_link: str) -> dict[str, Any]:
    card = _ORIGINAL_WEREAD_LINK_CARD(text, deep_link)
    header = _douban_status_header(text)
    if header:
        card_header = card.get("header")
        if isinstance(card_header, dict):
            title = card_header.get("title")
            if isinstance(title, dict):
                title["content"] = header
    return card


def prepare_result_polish() -> None:
    """Make successful Douban capture the primary status in hybrid result cards."""

    global _PREPARED
    if _PREPARED:
        return
    context._weread_link_card = _result_card
    _PREPARED = True
