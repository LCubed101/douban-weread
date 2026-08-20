from __future__ import annotations

import io
import unittest

from douban_weread.providers.weread import WeReadProgress, WeReadProviderError
from douban_weread.weread_cli import EXIT_OK, EXIT_PROVIDER_ERROR, run


class FakeProgressClient:
    def __init__(self, progress: WeReadProgress | None = None, error: Exception | None = None) -> None:
        self.progress = progress
        self.error = error
        self.calls: list[str] = []

    def get_progress(self, book_id: str) -> WeReadProgress | None:
        self.calls.append(book_id)
        if self.error:
            raise self.error
        return self.progress


class WeReadProgressCliTests(unittest.TestCase):
    def test_progress_prints_user_specific_read_only_evidence(self) -> None:
        client = FakeProgressClient(
            WeReadProgress(
                book_id="37724838",
                progress=0,
                is_started=False,
                update_time=123,
                reading_time_seconds=0,
            )
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["progress", "--id", "37724838"],
            client_factory=lambda: client,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(client.calls, ["37724838"])
        output = stdout.getvalue()
        self.assertIn("WeRead reading progress", output)
        self.assertIn("Progress: 0%", output)
        self.assertIn("Started: no", output)
        self.assertIn("Coarse state: unread", output)
        self.assertIn("not used to mutate Douban state", output)
        self.assertEqual(stderr.getvalue(), "")

    def test_progress_provider_error_fails_closed(self) -> None:
        client = FakeProgressClient(error=WeReadProviderError("progress unavailable"))
        stderr = io.StringIO()

        code = run(
            ["progress", "--id", "1"],
            client_factory=lambda: client,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_PROVIDER_ERROR)
        self.assertIn("WeRead provider error: progress unavailable", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
