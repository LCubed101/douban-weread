from types import SimpleNamespace

from douban_weread.feishu_tv_polish import _media_label, _polished_ambiguous_movie_card, _season_number


def item(title, year, movie_id, media_type="movie"):
    return SimpleNamespace(
        title=title,
        year=year,
        douban_id=movie_id,
        media_type=media_type,
        directors=(),
    )


def test_chinese_seasons_are_sorted_naturally_and_labeled_as_series():
    card = _polished_ambiguous_movie_card(
        "流人",
        [
            item("流人 第六季", "2026", "6"),
            item("流人 第一季", "2022", "1"),
            item("流人 第五季", "2025", "5"),
            item("流人 第二季", "2022", "2"),
        ],
    )

    assert card["header"]["title"]["content"] == "选择剧集季数"
    markdown = [element["content"] for element in card["elements"] if element["tag"] == "markdown"]
    assert markdown[1].startswith("1. 流人 第一季 · 2022 · 剧集")
    assert markdown[2].startswith("2. 流人 第二季 · 2022 · 剧集")
    assert markdown[3].startswith("3. 流人 第五季 · 2025 · 剧集")
    assert markdown[4].startswith("4. 流人 第六季 · 2026 · 剧集")


def test_season_helpers_are_conservative():
    assert _season_number("流人 第八季") == 8
    assert _season_number("Slow Horses Season 12") == 12
    assert _season_number("机器人之梦") is None
    assert _media_label(item("流人 第一季", "2022", "1", media_type="movie")) == "剧集"
