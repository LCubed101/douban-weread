from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from urllib.parse import parse_qs

from douban_weread.providers.douban.interest import (
    DoubanAuthError,
    DoubanBookInterestClient,
    DoubanConfirmationRequired,
    DoubanProviderError,
    DoubanWriteVerificationError,
)


# Synthetic test-only values; never use real cookies in repository fixtures.
COOKIE = 'bid=TEST; dbcl2="123456:TEST"; ck=TEST_CK'


class FakeTransport:
    def __init__(self, responses: list[tuple[int, str, str | None]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def __call__(self, method: str, url: str, headers, body: bytes | None):
        self.calls.append((method, url, dict(headers), body))
        if not self.responses:
            raise AssertionError("FakeTransport ran out of responses")
        status, response_body, response_url = self.responses.pop(0)
        return SimpleNamespace(status=status, body=response_body, url=response_url or url)


class DoubanBookInterestClientTests(unittest.TestCase):
    def test_missing_cookie_is_actionable(self) -> None:
        client = DoubanBookInterestClient(cookie="", transport=FakeTransport([]))
        status = client.check_auth()
        self.assertFalse(status.ok)
        self.assertEqual(status.reason, "missing_cookie")
        self.assertIn("DOUBAN_COOKIE", status.message)

    def test_missing_dbcl2_is_rejected_before_network(self) -> None:
        transport = FakeTransport([])
        client = DoubanBookInterestClient(cookie="bid=TEST; ck=TEST_CK", transport=transport)
        status = client.check_auth()
        self.assertFalse(status.ok)
        self.assertEqual(status.reason, "missing_dbcl2")
        self.assertEqual(transport.calls, [])

    def test_missing_ck_is_rejected_before_network(self) -> None:
        transport = FakeTransport([])
        client = DoubanBookInterestClient(cookie='dbcl2="123456:TEST"', transport=transport)
        status = client.check_auth()
        self.assertFalse(status.ok)
        self.assertEqual(status.reason, "missing_ck")
        self.assertEqual(status.user_id, "123456")
        self.assertEqual(transport.calls, [])

    def test_auth_probe_accepts_expected_json_and_never_exposes_cookie(self) -> None:
        transport = FakeTransport([(200, json.dumps({"html": "<div>ok</div>"}), None)])
        client = DoubanBookInterestClient(cookie=COOKIE, transport=transport)
        status = client.check_auth()
        self.assertTrue(status.ok)
        self.assertEqual(status.reason, "ok")
        self.assertEqual(status.user_id, "123456")
        self.assertNotIn("TEST_CK", status.message)
        method, _, headers, _ = transport.calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(headers["Cookie"], COOKIE)
        self.assertEqual(headers["X-Requested-With"], "XMLHttpRequest")

    def test_auth_probe_reports_403_without_leaking_cookie(self) -> None:
        transport = FakeTransport([(403, "forbidden", None)])
        client = DoubanBookInterestClient(cookie=COOKIE, transport=transport)
        status = client.check_auth()
        self.assertFalse(status.ok)
        self.assertEqual(status.reason, "cookie_expired_or_forbidden")
        self.assertNotIn("TEST_CK", status.message)

    def test_auth_probe_reports_captcha_or_block(self) -> None:
        transport = FakeTransport([(200, "<html>captcha</html>", None)])
        client = DoubanBookInterestClient(cookie=COOKIE, transport=transport)
        status = client.check_auth()
        self.assertFalse(status.ok)
        self.assertEqual(status.reason, "captcha_or_blocked")

    def test_get_interest_status_reads_direct_field(self) -> None:
        transport = FakeTransport([(200, json.dumps({"interest_status": "wish"}), None)])
        client = DoubanBookInterestClient(cookie=COOKIE, transport=transport)
        self.assertEqual(client.get_interest_status("6082808"), "wish")

    def test_get_interest_status_reads_checked_html_input(self) -> None:
        payload = json.dumps({"html": '<input type="radio" name="interest" value="do" checked>'})
        transport = FakeTransport([(200, payload, None)])
        client = DoubanBookInterestClient(cookie=COOKIE, transport=transport)
        self.assertEqual(client.get_interest_status("6082808"), "do")

    def test_get_interest_status_returns_none_when_no_state_is_selected(self) -> None:
        payload = json.dumps({"html": '<input type="radio" name="interest" value="wish">'} )
        transport = FakeTransport([(200, payload, None)])
        client = DoubanBookInterestClient(cookie=COOKIE, transport=transport)
        self.assertIsNone(client.get_interest_status("6082808"))

    def test_mark_wish_refuses_without_explicit_confirmation(self) -> None:
        client = DoubanBookInterestClient(cookie=COOKIE, transport=FakeTransport([]))
        with self.assertRaises(DoubanConfirmationRequired):
            client.mark_wish("6082808")

    def test_mark_wish_posts_confirmed_subject_and_verifies_saved_state(self) -> None:
        transport = FakeTransport([
            (200, json.dumps({"html": "<div>auth probe</div>"}), None),
            (200, json.dumps({"r": 0}), None),
            (200, json.dumps({"interest_status": "wish"}), None),
        ])
        client = DoubanBookInterestClient(cookie=COOKIE, transport=transport)
        result = client.mark_wish("6082808", confirmed=True)
        self.assertTrue(result.verified)
        self.assertEqual(result.requested_status, "wish")
        self.assertEqual(result.actual_status, "wish")
        self.assertEqual([call[0] for call in transport.calls], ["GET", "POST", "GET"])
        _, url, headers, body = transport.calls[1]
        self.assertEqual(url, "https://book.douban.com/j/subject/6082808/interest")
        self.assertEqual(headers["Origin"], "https://book.douban.com")
        self.assertEqual(headers["Referer"], "https://book.douban.com/subject/6082808/")
        self.assertIsNotNone(body)
        params = parse_qs(body.decode("utf-8"), keep_blank_values=True)
        self.assertEqual(params["interest"], ["wish"])
        self.assertEqual(params["ck"], ["TEST_CK"])
        self.assertEqual(params["rating"], [""])
        self.assertEqual(params["tags"], [""])
        self.assertEqual(params["comment"], [""])

    def test_boolean_false_is_not_mistaken_for_integer_success_code(self) -> None:
        transport = FakeTransport([
            (200, json.dumps({"html": "<div>auth probe</div>"}), None),
            (200, json.dumps({"r": False}), None),
        ])
        client = DoubanBookInterestClient(cookie=COOKIE, transport=transport)
        with self.assertRaises(DoubanProviderError):
            client.mark_wish("6082808", confirmed=True)

    def test_write_verification_failure_is_not_reported_as_success(self) -> None:
        transport = FakeTransport([
            (200, json.dumps({"html": "<div>auth probe</div>"}), None),
            (200, json.dumps({"r": 0}), None),
            (200, json.dumps({"interest_status": "do"}), None),
        ])
        client = DoubanBookInterestClient(cookie=COOKIE, transport=transport)
        with self.assertRaises(DoubanWriteVerificationError):
            client.mark_wish("6082808", confirmed=True)

    def test_login_redirect_is_auth_error(self) -> None:
        transport = FakeTransport([(200, "<html>登录豆瓣</html>", "https://accounts.douban.com/passport/login")])
        client = DoubanBookInterestClient(cookie=COOKIE, transport=transport)
        with self.assertRaises(DoubanAuthError):
            client.get_interest_status("6082808")

    def test_subject_id_must_be_digits_only(self) -> None:
        client = DoubanBookInterestClient(cookie=COOKIE, transport=FakeTransport([]))
        with self.assertRaises(ValueError):
            client.get_interest_status("../6082808")


if __name__ == "__main__":
    unittest.main()
