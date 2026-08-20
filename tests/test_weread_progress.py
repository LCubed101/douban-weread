from __future__ import annotations

import json
import unittest

from douban_weread.providers.weread.client import (
    WeReadClient,
    WeReadProviderError,
    _JsonResponse,
)


class WeReadProgressTests(unittest.TestCase):
    def test_get_progress_uses_official_endpoint_and_normalizes_fields(self) -> None:
        response = {
            "errcode": 0,
            "bookId": "37724838",
            "book": {
                "progress": 42,
                "isStartReading": 1,
                "updateTime": 1234567890,
                "recordReadingTime": 987,
            },
            "timestamp": 1234567899,
        }

        def transport(url: str, headers: dict[str, str], body: bytes) -> _JsonResponse:
            payload = json.loads(body.decode("utf-8"))
            self.assertEqual(payload["api_name"], "/book/getprogress")
            self.assertEqual(payload["skill_version"], "1.0.4")
            self.assertEqual(payload["bookId"], "37724838")
            return _JsonResponse(status=200, body=json.dumps(response))

        progress = WeReadClient(api_key="wrk-test", transport=transport).get_progress("37724838")

        self.assertIsNotNone(progress)
        assert progress is not None
        self.assertEqual(progress.book_id, "37724838")
        self.assertEqual(progress.progress, 42)
        self.assertTrue(progress.is_started)
        self.assertEqual(progress.reading_state, "reading")
        self.assertEqual(progress.reading_time_seconds, 987)

    def test_progress_zero_and_not_started_is_unread(self) -> None:
        response = {
            "errcode": 0,
            "bookId": "1",
            "book": {"progress": 0, "isStartReading": 0},
        }
        client = WeReadClient(
            api_key="wrk-test",
            transport=lambda *_: _JsonResponse(status=200, body=json.dumps(response)),
        )
        progress = client.get_progress("1")
        assert progress is not None
        self.assertEqual(progress.reading_state, "unread")

    def test_progress_100_without_finish_time_fails_closed_to_unknown_state(self) -> None:
        response = {
            "errcode": 0,
            "bookId": "1",
            "book": {"progress": 100, "isStartReading": 1},
        }
        client = WeReadClient(
            api_key="wrk-test",
            transport=lambda *_: _JsonResponse(status=200, body=json.dumps(response)),
        )
        progress = client.get_progress("1")
        assert progress is not None
        self.assertEqual(progress.reading_state, "unknown")

    def test_invalid_progress_fails_closed(self) -> None:
        response = {
            "errcode": 0,
            "bookId": "1",
            "book": {"progress": 101, "isStartReading": 1},
        }
        client = WeReadClient(
            api_key="wrk-test",
            transport=lambda *_: _JsonResponse(status=200, body=json.dumps(response)),
        )
        with self.assertRaisesRegex(WeReadProviderError, "invalid progress"):
            client.get_progress("1")


if __name__ == "__main__":
    unittest.main()
