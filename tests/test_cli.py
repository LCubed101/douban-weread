from __future__ import annotations

import io
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from douban_weread.cli import (
    EXIT_CONFIRMATION_REQUIRED,
    EXIT_NO_RESULTS,
    EXIT_OK,
    EXIT_PROVIDER_ERROR,
    EXIT_RECONCILIATION_REQUIRED,
    EXIT_WRITE_VERIFICATION_ERROR,
    _default_interest_client,
    _diagnose_cookie_input,
    format_edition,
    run,
)
from douban_weread.core.models import Edition
from douban_weread.providers.douban import (
    DoubanProviderError,
    DoubanWriteVerificationError,
)


class FakeClient:
    def __init__(self) -> None:
        self.title_results: list[Edition] = []
        self.isbn_result: Edition | None = None
        self.subject_result: Edition | None = None
        self.subject_results: dict[str, Edition] = {}
        self.raise_error: Exception | None = None
        self.last_title: tuple[str, int] | None = None
        self.last_isbn: str | None = None
        self.last_subject: str | None = None

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        if self.raise_error:
            raise self.raise_error
        self.last_title = (title, count)
        return self.title_results[:count]

    def search_by_isbn(self, isbn: str) -> Edition | None:
        if self.raise_error:
            raise self.raise_error
        self.last_isbn = isbn
        return self.isbn_result

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        if self.raise_error:
            raise self.raise_error
        self.last_subject = subject_id
        if subject_id in self.subject_results:
            return self.subject_results[subject_id]
        return self.subject_result


class FakeInterestClient:
    def __init__(self) -> None:
        self.auth_status = SimpleNamespace(ok=True, reason="ok", message="Cookie accepted.", user_id="123456")
        self.statuses: dict[str, str | None] = {}
        self.current_status: str | None = None
        self.mark_error: Exception | None = None
        self.status_error: Exception | None = None
        self.last_probe: str | None = None
        self.last_status_subject: str | None = None
        self.last_mark: tuple[str, bool] | None = None

    def check_auth(self, *, probe_subject_id: str = "6082808"):
        self.last_probe = probe_subject_id
        return self.auth_status

    def get_interest_status(self, subject_id: str) -> str | None:
        self.last_status_subject = subject_id
        if self.status_error:
            raise self.status_error
        return self.statuses.get(subject_id, self.current_status)

    def mark_wish(self, subject_id: str, *, confirmed: bool = False):
        self.last_mark = (subject_id, confirmed)
        if self.mark_error:
            raise self.mark_error
        return SimpleNamespace(subject_id=subject_id, verified=True)


class FakeHistoryIndex:
    def __init__(self, *, complete: bool = True, candidates: list[SimpleNamespace] | None = None) -> None:
        self.complete = complete
        self.candidates = candidates or []
        self.last_lookup: tuple[str, int] | None = None
        self.last_set_state: tuple[str, str, str] | None = None

    def status(self):
        return SimpleNamespace(complete=self.complete)

    def find_title_candidates(
        self,
        title: str,
        *,
        limit: int = 30,
        min_similarity: float = 0.72,
    ):
        self.last_lookup = (title, limit)
        return self.candidates[:limit]

    def set_state(self, subject_id: str, title: str, state: str) -> None:
        self.last_set_state = (subject_id, title, state)


def sample_edition(**overrides: object) -> Edition:
    values: dict[str, object] = {
        "title": "百年孤独",
        "authors": ["加西亚·马尔克斯"],
        "translators": ["范晔"],
        "publisher": "南海出版公司",
        "publish_date": "2011-06",
        "isbn": "9787544253994",
        "douban_id": "6082808",
    }
    values.update(overrides)
    return Edition(**values)  # type: ignore[arg-type]


def older_same_work() -> Edition:
    return sample_edition(
        publish_date="2001-08",
        isbn="9787544218566",
        douban_id="2008724",
    )


class CliTests(unittest.TestCase):
    def test_format_edition_contains_version_fields(self) -> None:
        output = format_edition(sample_edition(), index=1)

        self.assertIn("1. 百年孤独", output)
        self.assertIn("Authors: 加西亚·马尔克斯", output)
        self.assertIn("Translators: 范晔", output)
        self.assertIn("南海出版公司 · 2011-06", output)
        self.assertIn("ISBN: 9787544253994", output)
        self.assertIn("https://book.douban.com/subject/6082808/", output)

    def test_title_search_prints_multiple_candidates_and_warning(self) -> None:
        client = FakeClient()
        client.title_results = [
            sample_edition(),
            sample_edition(
                translators=["另一译者"],
                publisher="另一出版社",
                publish_date="2024-01",
                isbn="9780000000000",
                douban_id="9999999",
            ),
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["search", "百年孤独", "--limit", "5"],
            client_factory=lambda: client,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(client.last_title, ("百年孤独", 5))
        self.assertIn("Found 2 candidate editions", stdout.getvalue())
        self.assertIn("Confirm translator, publisher, year, and ISBN", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_isbn_search_prints_exact_result(self) -> None:
        client = FakeClient()
        client.isbn_result = sample_edition()
        stdout = io.StringIO()

        code = run(
            ["search", "--isbn", "978-7-5442-5399-4"],
            client_factory=lambda: client,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(client.last_isbn, "978-7-5442-5399-4")
        self.assertIn("Exact ISBN result", stdout.getvalue())
        self.assertIn("百年孤独", stdout.getvalue())

    def test_no_results_returns_stable_exit_code(self) -> None:
        client = FakeClient()
        stdout = io.StringIO()

        code = run(
            ["search", "不存在的书"],
            client_factory=lambda: client,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_NO_RESULTS)
        self.assertIn("No Douban editions found", stdout.getvalue())

    def test_provider_error_is_sent_to_stderr(self) -> None:
        client = FakeClient()
        client.raise_error = DoubanProviderError("network unavailable")
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["search", "百年孤独"],
            client_factory=lambda: client,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_PROVIDER_ERROR)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("network unavailable", stderr.getvalue())

    def test_limit_is_clamped(self) -> None:
        client = FakeClient()

        code = run(
            ["search", "百年孤独", "--limit", "999"],
            client_factory=lambda: client,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_NO_RESULTS)
        self.assertEqual(client.last_title, ("百年孤独", 100))

    def test_default_interest_client_accepts_cookie_header_prefix(self) -> None:
        raw = 'Cookie: bid=test-bid; dbcl2="test-user:test-session"; ck=test-csrf'
        with patch.dict(os.environ, {"DOUBAN_COOKIE": raw}, clear=False):
            client = _default_interest_client()

        self.assertEqual(client.cookies.get("bid"), "test-bid")
        self.assertEqual(client.cookies.get("dbcl2"), "test-user:test-session")
        self.assertEqual(client.ck, "test-csrf")
        self.assertFalse(client.cookie_header.lower().startswith("cookie:"))

    def test_cookie_diagnose_reports_only_structure(self) -> None:
        raw = 'bid=test-bid; dbcl2="test-user:test-session"; ck=test-csrf'
        with patch.dict(os.environ, {"DOUBAN_COOKIE": raw}, clear=False):
            stdout = io.StringIO()
            code = run(["auth", "diagnose"], stdout=stdout, stderr=io.StringIO())

        output = stdout.getvalue()
        self.assertEqual(code, EXIT_OK)
        self.assertIn("Cookie input kind: cookie_header", output)
        self.assertIn("Has dbcl2: True", output)
        self.assertIn("Has ck: True", output)
        self.assertIn("Ready for auth check: True", output)
        self.assertNotIn("test-session", output)
        self.assertNotIn("test-csrf", output)

    def test_cookie_diagnose_classifies_json_export_without_values(self) -> None:
        raw = '[{"name":"dbcl2","value":"test-secret"}]'
        with patch.dict(os.environ, {"DOUBAN_COOKIE": raw}, clear=False):
            kind, names = _diagnose_cookie_input()
            stdout = io.StringIO()
            code = run(["auth", "diagnose"], stdout=stdout, stderr=io.StringIO())

        self.assertEqual(kind, "json_or_cookie_export")
        self.assertEqual(names, [])
        self.assertEqual(code, EXIT_PROVIDER_ERROR)
        self.assertIn("Cookie input kind: json_or_cookie_export", stdout.getvalue())
        self.assertNotIn("test-secret", stdout.getvalue())

    def test_auth_check_prints_success_without_cookie_value(self) -> None:
        interest = FakeInterestClient()
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = run(
            ["auth", "check", "--probe-subject", "6082808"],
            interest_client_factory=lambda: interest,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(interest.last_probe, "6082808")
        self.assertIn("Douban auth OK", stdout.getvalue())
        self.assertIn("user 123456", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_auth_check_failure_is_actionable(self) -> None:
        interest = FakeInterestClient()
        interest.auth_status = SimpleNamespace(
            ok=False,
            reason="missing_ck",
            message="DOUBAN_COOKIE does not contain ck.",
            user_id=None,
        )
        stderr = io.StringIO()

        code = run(
            ["auth", "check"],
            interest_client_factory=lambda: interest,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_PROVIDER_ERROR)
        self.assertIn("missing_ck", stderr.getvalue())

    def test_status_reads_current_interest_without_mutation(self) -> None:
        interest = FakeInterestClient()
        interest.current_status = "collect"
        stdout = io.StringIO()

        code = run(
            ["status", "--subject", "25837854"],
            interest_client_factory=lambda: interest,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(interest.last_status_subject, "25837854")
        self.assertIn("interest: collect", stdout.getvalue())
        self.assertIsNone(interest.last_mark)

    def test_status_prints_none_for_unmarked_subject(self) -> None:
        interest = FakeInterestClient()
        stdout = io.StringIO()

        code = run(
            ["status", "--subject", "25837854"],
            interest_client_factory=lambda: interest,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        self.assertIn("interest: none", stdout.getvalue())

    def test_inspect_reports_existing_read_other_edition_without_mutation(self) -> None:
        target = sample_edition()
        older = older_same_work()
        search = FakeClient()
        search.subject_result = target
        search.title_results = [target, older]
        interest = FakeInterestClient()
        interest.statuses = {"6082808": None, "2008724": "collect"}
        history = FakeHistoryIndex()
        stdout = io.StringIO()

        code = run(
            ["inspect", "--subject", "6082808"],
            client_factory=lambda: search,
            interest_client_factory=lambda: interest,
            history_index_factory=lambda: history,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        self.assertIn("Decision: ask_reread", stdout.getvalue())
        self.assertIn("READ | subject 2008724", stdout.getvalue())
        self.assertIn("Safe to write Want-to-Read: False", stdout.getvalue())
        self.assertIsNone(interest.last_mark)
        self.assertEqual(history.last_lookup, ("百年孤独", 30))

    def test_inspect_requires_complete_history_baseline(self) -> None:
        search = FakeClient()
        search.subject_result = sample_edition()
        interest = FakeInterestClient()
        history = FakeHistoryIndex(complete=False)
        stderr = io.StringIO()

        code = run(
            ["inspect", "--subject", "6082808"],
            client_factory=lambda: search,
            interest_client_factory=lambda: interest,
            history_index_factory=lambda: history,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_RECONCILIATION_REQUIRED)
        self.assertIn("history sync --full", stderr.getvalue())
        self.assertIsNone(interest.last_status_subject)

    def test_wish_without_confirm_returns_before_reconciliation(self) -> None:
        interest = FakeInterestClient()
        stderr = io.StringIO()

        code = run(
            ["wish", "--subject", "6082808"],
            interest_client_factory=lambda: interest,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_CONFIRMATION_REQUIRED)
        self.assertIsNone(interest.last_mark)
        self.assertIsNone(interest.last_status_subject)
        self.assertIn("--confirm", stderr.getvalue())

    def test_confirmed_wish_is_blocked_when_other_edition_was_read(self) -> None:
        target = sample_edition()
        older = older_same_work()
        search = FakeClient()
        search.subject_result = target
        search.title_results = [target, older]
        interest = FakeInterestClient()
        interest.statuses = {"6082808": None, "2008724": "collect"}
        history = FakeHistoryIndex()
        stderr = io.StringIO()

        code = run(
            ["wish", "--subject", "6082808", "--confirm"],
            client_factory=lambda: search,
            interest_client_factory=lambda: interest,
            history_index_factory=lambda: history,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_RECONCILIATION_REQUIRED)
        self.assertIsNone(interest.last_mark)
        self.assertIn("Decision: ask_reread", stderr.getvalue())
        self.assertIn("no write was performed", stderr.getvalue())

    def test_confirmed_wish_noops_when_target_is_already_wish(self) -> None:
        target = sample_edition()
        search = FakeClient()
        search.subject_result = target
        search.title_results = [target]
        interest = FakeInterestClient()
        interest.statuses = {"6082808": "wish"}
        history = FakeHistoryIndex()
        stdout = io.StringIO()

        code = run(
            ["wish", "--subject", "6082808", "--confirm"],
            client_factory=lambda: search,
            interest_client_factory=lambda: interest,
            history_index_factory=lambda: history,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        self.assertIsNone(interest.last_mark)
        self.assertIn("already marked Want-to-Read", stdout.getvalue())

    def test_confirmed_wish_writes_only_after_safe_reconciliation(self) -> None:
        target = sample_edition()
        search = FakeClient()
        search.subject_result = target
        search.title_results = [target]
        interest = FakeInterestClient()
        interest.statuses = {"6082808": None}
        history = FakeHistoryIndex()
        stdout = io.StringIO()

        code = run(
            ["wish", "--subject", "6082808", "--confirm"],
            client_factory=lambda: search,
            interest_client_factory=lambda: interest,
            history_index_factory=lambda: history,
            stdout=stdout,
            stderr=io.StringIO(),
        )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(interest.last_mark, ("6082808", True))
        self.assertEqual(history.last_set_state, ("6082808", "百年孤独", "wish"))
        self.assertIn("saved state was verified", stdout.getvalue())

    def test_wish_verification_failure_has_distinct_exit_code_after_safe_reconciliation(self) -> None:
        target = sample_edition()
        search = FakeClient()
        search.subject_result = target
        search.title_results = [target]
        interest = FakeInterestClient()
        interest.statuses = {"6082808": None}
        interest.mark_error = DoubanWriteVerificationError("expected wish, got do")
        history = FakeHistoryIndex()
        stderr = io.StringIO()

        code = run(
            ["wish", "--subject", "6082808", "--confirm"],
            client_factory=lambda: search,
            interest_client_factory=lambda: interest,
            history_index_factory=lambda: history,
            stdout=io.StringIO(),
            stderr=stderr,
        )

        self.assertEqual(code, EXIT_WRITE_VERIFICATION_ERROR)
        self.assertIsNone(history.last_set_state)
        self.assertIn("verification error", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
