from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_XIAOYUZHOU_API_BASE = "https://api.xiaoyuzhoufm.com"
DEFAULT_USER_AGENT = "douban-weread/0.1 (+https://github.com/LCubed101/douban-weread)"


class XiaoyuzhouProviderError(RuntimeError):
    pass


class XiaoyuzhouAuthError(XiaoyuzhouProviderError):
    pass


@dataclass(slots=True, frozen=True)
class XiaoyuzhouEpisodeCandidate:
    episode_id: str
    title: str
    podcast_title: str | None
    published_at: str | None
    duration_seconds: int | None
    episode_url: str


@dataclass(slots=True)
class _JsonResponse:
    status: int
    body: str


Transport = Callable[[str, str, Mapping[str, str], bytes | None], _JsonResponse]


class XiaoyuzhouSearchClient:
    """Read-only Xiaoyuzhou episode search adapter.

    Search uses Xiaoyuzhou's authenticated native search endpoint. The caller
    supplies a user-owned access token via ``XIAOYUZHOU_ACCESS_TOKEN`` or the
    constructor. This adapter never logs or persists the token.
    """

    def __init__(
        self,
        *,
        access_token: str | None = None,
        device_id: str | None = None,
        api_base: str = DEFAULT_XIAOYUZHOU_API_BASE,
        timeout: float = 10.0,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: Transport | None = None,
    ) -> None:
        self.access_token = (access_token if access_token is not None else os.getenv("XIAOYUZHOU_ACCESS_TOKEN", "")).strip()
        self.device_id = (device_id if device_id is not None else os.getenv("XIAOYUZHOU_DEVICE_ID", "")).strip()
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent
        self._transport = transport or self._default_transport

    def search_episodes(self, keyword: str, *, limit: int = 10) -> list[XiaoyuzhouEpisodeCandidate]:
        query = " ".join(keyword.split()).strip()
        if not query:
            return []
        if not self.access_token:
            raise XiaoyuzhouAuthError("XIAOYUZHOU_ACCESS_TOKEN is not set.")

        payload = {"keyword": query, "type": "EPISODE", "limit": max(1, min(limit, 20))}
        raw = self._request_json("POST", "/v1/search/create", payload)
        rows = self._extract_rows(raw)
        result: list[XiaoyuzhouEpisodeCandidate] = []
        seen: set[str] = set()
        for row in rows:
            item = self._parse_episode(row)
            if item is None or item.episode_id in seen:
                continue
            seen.add(item.episode_id)
            result.append(item)
            if len(result) >= payload["limit"]:
                break
        return result

    def _request_json(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> Any:
        body = json.dumps(dict(payload or {}), ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-jike-access-token": self.access_token,
        }
        if self.device_id:
            headers["x-jike-device-id"] = self.device_id
        response = self._transport(method, f"{self.api_base}{path}", headers, body)
        if response.status in {401, 403}:
            raise XiaoyuzhouAuthError(f"Xiaoyuzhou authentication failed with HTTP {response.status}.")
        if response.status < 200 or response.status >= 300:
            raise XiaoyuzhouProviderError(f"Xiaoyuzhou request failed with HTTP {response.status}.")
        try:
            return json.loads(response.body)
        except json.JSONDecodeError as exc:
            raise XiaoyuzhouProviderError("Xiaoyuzhou returned invalid JSON.") from exc

    def _default_transport(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> _JsonResponse:
        request = Request(url, headers=dict(headers), data=body, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - provider URL
                return _JsonResponse(
                    status=getattr(response, "status", 200),
                    body=response.read().decode("utf-8", errors="replace"),
                )
        except HTTPError as exc:
            return _JsonResponse(status=exc.code, body=exc.read().decode("utf-8", errors="replace"))
        except URLError as exc:
            raise XiaoyuzhouProviderError(f"Could not reach Xiaoyuzhou: {exc.reason}") from exc

    @staticmethod
    def _extract_rows(payload: Any) -> list[Mapping[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, Mapping)]
        if not isinstance(payload, Mapping):
            return []
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, Mapping)]
        if isinstance(data, Mapping):
            for key in ("data", "items", "list", "results"):
                rows = data.get(key)
                if isinstance(rows, list):
                    return [item for item in rows if isinstance(item, Mapping)]
        return []

    @classmethod
    def _parse_episode(cls, row: Mapping[str, Any]) -> XiaoyuzhouEpisodeCandidate | None:
        source: Mapping[str, Any] = row
        for key in ("episode", "target", "data"):
            nested = row.get(key)
            if isinstance(nested, Mapping) and (nested.get("eid") or nested.get("id") or nested.get("title")):
                source = nested
                break

        episode_id = str(source.get("eid") or source.get("id") or row.get("eid") or row.get("id") or "").strip()
        title = cls._clean(source.get("title") or row.get("title"))
        if not episode_id or not title:
            return None

        podcast = source.get("podcast") or row.get("podcast")
        podcast_title: str | None = None
        if isinstance(podcast, Mapping):
            podcast_title = cls._clean(podcast.get("title")) or None
        if not podcast_title:
            podcast_title = cls._clean(source.get("podcastTitle") or row.get("podcastTitle")) or None

        published = cls._clean(source.get("pubDate") or source.get("publishedAt") or row.get("pubDate")) or None
        duration = source.get("duration") or row.get("duration")
        try:
            duration_seconds = int(duration) if duration is not None else None
        except (TypeError, ValueError):
            duration_seconds = None

        return XiaoyuzhouEpisodeCandidate(
            episode_id=episode_id,
            title=title,
            podcast_title=podcast_title,
            published_at=published,
            duration_seconds=duration_seconds,
            episode_url=f"https://www.xiaoyuzhoufm.com/episode/{episode_id}",
        )

    @staticmethod
    def _clean(value: Any) -> str:
        return " ".join(str(value or "").split()).strip()
