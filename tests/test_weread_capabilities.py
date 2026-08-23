from __future__ import annotations

import unittest

from douban_weread.weread_capabilities import WeReadCapabilityDiscovery


class FakeClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def _call(self, api_name: str, **params: object) -> dict[str, object]:
        self.calls.append(api_name)
        return self.payload


class WeReadCapabilityDiscoveryTests(unittest.TestCase):
    def test_collects_nested_api_names_without_guessing(self) -> None:
        client = FakeClient(
            {
                "apis": [
                    {"api_name": "/store/search", "description": "search books"},
                    {"name": "/shelf/sync"},
                    {"apiName": "/book/info"},
                ]
            }
        )
        result = WeReadCapabilityDiscovery(client).list_capabilities()  # type: ignore[arg-type]
        self.assertEqual(client.calls, ["/_list"])
        self.assertEqual(
            [item.api_name for item in result],
            ["/book/info", "/shelf/sync", "/store/search"],
        )
        descriptions = {item.api_name: item.description for item in result}
        self.assertEqual(descriptions["/store/search"], "search books")

    def test_deduplicates_repeated_api_names(self) -> None:
        client = FakeClient(
            {"a": [{"api_name": "/shelf/sync"}], "b": ["/shelf/sync"]}
        )
        result = WeReadCapabilityDiscovery(client).list_capabilities()  # type: ignore[arg-type]
        self.assertEqual([item.api_name for item in result], ["/shelf/sync"])


if __name__ == "__main__":
    unittest.main()
