from __future__ import annotations

import re

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_SEASON_CN_RE = re.compile(r"第(?P<num>[零一二两三四五六七八九十百\d]+)季")
_SEASON_EN_RE = re.compile(r"season\s*(?P<num>\d+)", re.IGNORECASE)


def _cn_number(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if value == "百":
        return 100
    if "百" in value:
        left, right = value.split("百", 1)
        hundreds = _CN_DIGITS.get(left, 1) * 100
        tail = _cn_number(right) if right else 0
        return hundreds + (tail or 0)
    if "十" in value:
        left, right = value.split("十", 1)
        tens = _CN_DIGITS.get(left, 1) * 10
        ones = _CN_DIGITS.get(right, 0) if right else 0
        return tens + ones
    if len(value) == 1:
        return _CN_DIGITS.get(value)
    return None


def _season_number(title: str) -> int | None:
    match = _SEASON_CN_RE.search(str(title or ""))
    if match:
        return _cn_number(match.group("num"))
    match = _SEASON_EN_RE.search(str(title or ""))
    if match:
        return int(match.group("num"))
    return None


def _is_season_candidate(item: object) -> bool:
    return _season_number(str(getattr(item, "title", "") or "")) is not None


def _media_label(item: object) -> str:
    if _is_season_candidate(item):
        return "剧集"
    raw = str(getattr(item, "media_type", "") or "").strip().casefold()
    if raw in {"tv", "television", "series", "tv_series"}:
        return "剧集"
    if raw in {"documentary", "doc"}:
        return "纪录片"
    if raw == "movie":
        return "电影"
    return "影视"


def _candidate_sort_key(item: object):
    season = _season_number(str(getattr(item, "title", "") or ""))
    if season is not None:
        return (0, season, str(getattr(item, "year", "") or ""), str(getattr(item, "title", "") or ""))
    return (1, 10**6, str(getattr(item, "year", "") or ""), str(getattr(item, "title", "") or ""))


def _polished_ambiguous_movie_card(query: str, candidates) -> dict[str, object]:
    ordered = tuple(sorted(tuple(candidates), key=_candidate_sort_key))
    season_family = bool(ordered) and all(_is_season_candidate(item) for item in ordered)

    if season_family:
        intro = f"《{query}》找到多个季度，请选择要加入豆瓣想看的那一季："
        header = "选择剧集季数"
    else:
        intro = f"《{query}》有多个豆瓣影视条目，请选一个："
        header = "确认影视条目"

    elements: list[dict[str, object]] = [{"tag": "markdown", "content": intro}]
    for index, item in enumerate(ordered, start=1):
        details = " · ".join(
            value
            for value in (
                str(getattr(item, "year", "") or "").strip(),
                _media_label(item),
                " / ".join(getattr(item, "directors", ()) or ()),
            )
            if value
        )
        title = str(getattr(item, "title", query) or query)
        label = f"{index}. {title}" + (f" · {details}" if details else "")
        elements.append({"tag": "markdown", "content": label})
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": f"选择 {index}"},
                        "type": "primary",
                        "value": {
                            "action": "confirm_movie",
                            "movie_subject_id": str(getattr(item, "douban_id", "") or ""),
                            "movie_title": title,
                        },
                    }
                ],
            }
        )

    return {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {"title": {"tag": "plain_text", "content": header}, "template": "blue"},
        "elements": elements,
    }


def prepare_tv_card_polish() -> None:
    """Make TV season choices human-readable and naturally ordered."""

    from douban_weread import feishu_movie_router as movie_router

    movie_router._ambiguous_movie_card = _polished_ambiguous_movie_card
