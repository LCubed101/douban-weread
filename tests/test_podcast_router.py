from types import SimpleNamespace

from douban_weread.podcast_router import PodcastResolveKind, XiaoyuzhouEpisodeResolver
from douban_weread.providers.xiaoyuzhou import XiaoyuzhouEpisodeCandidate, XiaoyuzhouSearchClient


def episode(eid: str, title: str, podcast: str = "随机波动"):
    return XiaoyuzhouEpisodeCandidate(
        episode_id=eid,
        title=title,
        podcast_title=podcast,
        published_at="2026-08-01T00:00:00Z",
        duration_seconds=3600,
        episode_url=f"https://www.xiaoyuzhoufm.com/episode/{eid}",
    )


class FakeSearch:
    def __init__(self, items):
        self.items = list(items)

    def search_episodes(self, keyword: str, *, limit: int = 10):
        return list(self.items)


def test_exact_episode_title_auto_selects():
    resolver = XiaoyuzhouEpisodeResolver(FakeSearch([episode("1", "触屏时代的触觉饥渴")]))
    result = resolver.resolve("触屏时代的触觉饥渴")
    assert result.kind is PodcastResolveKind.EXACT
    assert result.selected is not None
    assert result.selected.episode_id == "1"


def test_exact_podcast_constraint_filters_same_episode_title():
    resolver = XiaoyuzhouEpisodeResolver(
        FakeSearch([
            episode("1", "AI 与人的关系", "随机波动"),
            episode("2", "AI 与人的关系", "别去明知山"),
        ])
    )
    result = resolver.resolve("AI 与人的关系", podcast="随机波动")
    assert result.kind is PodcastResolveKind.EXACT
    assert result.selected is not None
    assert result.selected.episode_id == "1"


def test_fuzzy_results_never_auto_select():
    resolver = XiaoyuzhouEpisodeResolver(
        FakeSearch([
            episode("1", "我们如何和 AI 相处"),
            episode("2", "AI 时代的人类关系"),
        ])
    )
    result = resolver.resolve("AI 和人")
    assert result.kind is PodcastResolveKind.AMBIGUOUS
    assert result.selected is None


def test_search_response_parser_handles_nested_episode_shape():
    client = XiaoyuzhouSearchClient(access_token="token", transport=lambda *args: None)
    item = client._parse_episode(
        {
            "episode": {
                "eid": "abc123",
                "title": "一期节目",
                "podcast": {"title": "某播客"},
                "pubDate": "2026-08-30T00:00:00Z",
                "duration": 1800,
            }
        }
    )
    assert item is not None
    assert item.episode_id == "abc123"
    assert item.podcast_title == "某播客"
    assert item.episode_url == "https://www.xiaoyuzhoufm.com/episode/abc123"


def test_search_client_sends_episode_search_request_without_printing_token():
    calls = []

    def transport(method, url, headers, body):
        calls.append((method, url, headers, body))
        return SimpleNamespace(
            status=200,
            body='{"data":[{"eid":"abc","title":"测试单集","podcast":{"title":"测试播客"}}]}',
        )

    client = XiaoyuzhouSearchClient(access_token="secret-token", device_id="device", transport=transport)
    items = client.search_episodes("测试单集")
    assert len(items) == 1
    assert items[0].episode_id == "abc"
    method, url, headers, body = calls[0]
    assert method == "POST"
    assert url.endswith("/v1/search/create")
    assert headers["x-jike-access-token"] == "secret-token"
    assert headers["x-jike-device-id"] == "device"
    assert b'"type": "EPISODE"' in body
