from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookies import SimpleCookie
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .search import DEFAULT_USER_AGENT, DoubanProviderError


DEFAULT_BASE_URL = "https://book.douban.com"
_INTERESTS = {"wish", "do", "collect"}
_SUBJECT_ID_RE = re.compile(r"^\d+$")
_LOGIN_URL_MARKERS = ("accounts.douban.com", "passport.douban", "/login", "/signup")
_BLOCK_MARKERS = ("captcha", "sec.douban.com", "验证码")


class DoubanAuthError(DoubanProviderError):
    """Raised when a user-owned Douban session cannot be used safely."""


class DoubanConfirmationRequired(DoubanProviderError):
    """Raised when a state-changing action was not explicitly confirmed."""


class DoubanWriteVerificationError(DoubanProviderError):
    """Raised when Douban did not persist the requested state."""


@dataclass(slots=True, frozen=True)
class AuthStatus:
    ok: bool
    reason: str
    message: str
    user_id: str | None = None


@dataclass(slots=True, frozen=True)
class InterestMutationResult:
    subject_id: str
    requested_status: str
    actual_status: str | None
    verified: bool


@dataclass(slots=True)
class _HttpResponse:
    status: int
    body: str
    url: str


Transport = Callable[[str, str, Mapping[str, str], bytes | None], _HttpResponse]


class _InterestHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.checked_interest: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "input":
            return
        attrs_map = {key: value for key, value in attrs}
        if attrs_map.get("name") != "interest" or "checked" not in attrs_map:
            return
        value = attrs_map.get("value")
        if value in _INTERESTS:
            self.checked_interest = value


def _parse_cookie_fields(cookie_header: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    jar = SimpleCookie()
    try:
        jar.load(cookie_header)
    except Exception:
        return parsed
    for key, morsel in jar.items():
        parsed[key] = morsel.value
    return parsed


def _extract_user_id(dbcl2: str | None) -> str | None:
    if not dbcl2:
        return None
    value = dbcl2.strip().strip('"')
    user_id, sep, _ = value.partition(":")
    return user_id if sep and user_id else None


class DoubanBookInterestClient:
    """Authenticated adapter for a user's Douban Book reading state.

    This client uses an unofficial/internal Douban web interface. It therefore
    fails conservatively, never logs the Cookie value, requires explicit
    confirmation before mutation, and verifies the state after every write.
    """

    def __init__(
        self,
        cookie: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: Transport | None = None,
    ) -> None:
        self.cookie_header = (cookie if cookie is not None else os.getenv("DOUBAN_COOKIE", "")).strip()
        self.cookies = _parse_cookie_fields(self.cookie_header)
        self.ck = self.cookies.get("ck", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent
        self._transport = transport or self._default_transport

    def check_auth(self, *, probe_subject_id: str = "6082808") -> AuthStatus:
        """Validate local Cookie fields and probe the authenticated interest endpoint."""
        local = self._validate_local_cookie()
        if not local.ok:
            return local

        try:
            self._validate_subject_id(probe_subject_id)
            response = self._request("GET", self._interest_url(probe_subject_id))
        except DoubanAuthError as exc:
            return AuthStatus(False, "auth_failed", str(exc), user_id=local.user_id)
        except DoubanProviderError as exc:
            return AuthStatus(False, "network_or_provider", str(exc), user_id=local.user_id)

        if response.status in {401, 403}:
            return AuthStatus(
                False,
                "cookie_expired_or_forbidden",
                f"Douban rejected the authenticated probe with HTTP {response.status}.",
                user_id=local.user_id,
            )
        if response.status < 200 or response.status >= 300:
            return AuthStatus(
                False,
                "provider_error",
                f"Douban auth probe returned HTTP {response.status}.",
                user_id=local.user_id,
            )
        if self._looks_like_login(response.url, response.body):
            return AuthStatus(
                False,
                "cookie_expired",
                "Douban redirected or returned a login page; export a fresh Cookie from your browser.",
                user_id=local.user_id,
            )
        if self._looks_blocked(response.body):
            return AuthStatus(
                False,
                "captcha_or_blocked",
                "Douban returned a captcha or anti-abuse page; do not bypass it programmatically.",
                user_id=local.user_id,
            )
        try:
            json.loads(response.body)
        except json.JSONDecodeError:
            return AuthStatus(
                False,
                "unexpected_response",
                "Douban auth probe did not return the expected JSON response.",
                user_id=local.user_id,
            )

        return AuthStatus(True, "ok", "Douban Cookie was accepted by the Book interest endpoint.", user_id=local.user_id)

    def get_interest_status(self, subject_id: str) -> str | None:
        """Return wish/do/collect, or None if the subject has no reading state."""
        self._validate_subject_id(subject_id)
        local = self._validate_local_cookie()
        if not local.ok:
            raise DoubanAuthError(local.message)

        response = self._request("GET", self._interest_url(subject_id))
        self._raise_for_auth_or_block(response)
        if response.status < 200 or response.status >= 300:
            raise DoubanProviderError(f"Douban interest lookup failed with HTTP {response.status}")

        payload = self._parse_json(response.body, context="interest lookup")
        direct = payload.get("interest_status")
        if isinstance(direct, str) and direct in _INTERESTS:
            return direct

        html = payload.get("html")
        if isinstance(html, str) and html:
            parser = _InterestHtmlParser()
            parser.feed(html)
            return parser.checked_interest
        return None

    def mark_wish(self, subject_id: str, *, confirmed: bool = False) -> InterestMutationResult:
        """Mark one explicitly selected Douban Book subject as Want-to-Read."""
        self._validate_subject_id(subject_id)
        if not confirmed:
            raise DoubanConfirmationRequired(
                "Refusing to change Douban state without explicit confirmation. "
                "Pass confirmed=True only after the exact subject/edition has been selected."
            )

        auth = self.check_auth(probe_subject_id=subject_id)
        if not auth.ok:
            raise DoubanAuthError(auth.message)

        body = urlencode(
            {
                "ck": self.ck,
                "interest": "wish",
                "rating": "",
                "foldcollect": "F",
                "tags": "",
                "comment": "",
            }
        ).encode("utf-8")
        response = self._request("POST", self._interest_url(subject_id), body=body)
        self._raise_for_auth_or_block(response)
        if response.status < 200 or response.status >= 300:
            raise DoubanProviderError(f"Douban wish action failed with HTTP {response.status}")

        payload = self._parse_json(response.body, context="wish action")
        if self._response_has_explicit_error(payload):
            raise DoubanProviderError("Douban rejected the Want-to-Read action.")

        actual = self.get_interest_status(subject_id)
        if actual != "wish":
            raise DoubanWriteVerificationError(
                f"Douban write verification failed for subject {subject_id}: expected wish, got {actual or 'no state'}."
            )

        return InterestMutationResult(
            subject_id=subject_id,
            requested_status="wish",
            actual_status=actual,
            verified=True,
        )

    def _validate_local_cookie(self) -> AuthStatus:
        if not self.cookie_header:
            return AuthStatus(False, "missing_cookie", "DOUBAN_COOKIE is not set.")
        if not self.cookies:
            return AuthStatus(False, "cookie_format", "DOUBAN_COOKIE could not be parsed as a Cookie header.")
        user_id = _extract_user_id(self.cookies.get("dbcl2"))
        if not self.cookies.get("dbcl2"):
            return AuthStatus(
                False,
                "missing_dbcl2",
                "DOUBAN_COOKIE does not contain dbcl2; confirm that the browser is logged in to Douban.",
            )
        if not self.ck:
            return AuthStatus(
                False,
                "missing_ck",
                "DOUBAN_COOKIE does not contain ck; export a fresh complete Cookie before write actions.",
                user_id=user_id,
            )
        return AuthStatus(True, "local_fields_ok", "Required Douban Cookie fields are present.", user_id=user_id)

    def _request(self, method: str, url: str, *, body: bytes | None = None) -> _HttpResponse:
        headers = self._headers(url, method=method)
        return self._transport(method, url, headers, body)

    def _headers(self, url: str, *, method: str) -> dict[str, str]:
        subject_match = re.search(r"/subject/(\d+)/interest", url)
        subject_id = subject_match.group(1) if subject_match else ""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cookie": self.cookie_header,
            "Referer": f"{self.base_url}/subject/{subject_id}/" if subject_id else f"{self.base_url}/",
            "X-Requested-With": "XMLHttpRequest",
        }
        if method == "POST":
            headers["Origin"] = self.base_url
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        return headers

    def _default_transport(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> _HttpResponse:
        request = Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - expected provider URL
                text = response.read().decode("utf-8", errors="replace")
                return _HttpResponse(
                    status=getattr(response, "status", 200),
                    body=text,
                    url=response.geturl(),
                )
        except HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return _HttpResponse(status=exc.code, body=text, url=exc.geturl())
        except URLError as exc:
            raise DoubanProviderError(f"Could not reach Douban: {exc.reason}") from exc

    def _raise_for_auth_or_block(self, response: _HttpResponse) -> None:
        if response.status in {401, 403}:
            raise DoubanAuthError(
                f"Douban rejected the authenticated request with HTTP {response.status}; the Cookie may be expired or blocked."
            )
        if self._looks_like_login(response.url, response.body):
            raise DoubanAuthError("Douban returned a login page; export a fresh Cookie from your browser.")
        if self._looks_blocked(response.body):
            raise DoubanAuthError("Douban returned a captcha or anti-abuse page; do not bypass it programmatically.")

    @staticmethod
    def _parse_json(body: str, *, context: str) -> dict[str, object]:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise DoubanProviderError(f"Douban {context} response was not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise DoubanProviderError(f"Douban {context} response had an unexpected JSON shape.")
        return payload

    @staticmethod
    def _response_has_explicit_error(payload: Mapping[str, object]) -> bool:
        # Known successful responses use integer r=0. Do not treat boolean
        # False as integer zero: bool is a subclass of int in Python.
        if "r" in payload:
            value = payload.get("r")
            return not (type(value) is int and value == 0)
        if payload.get("error") or payload.get("msg") == "error":
            return True
        return False

    @staticmethod
    def _looks_like_login(url: str, body: str) -> bool:
        lowered_url = url.lower()
        lowered_body = body.lower()
        return any(marker in lowered_url for marker in _LOGIN_URL_MARKERS) or (
            "登录豆瓣" in body and "accounts.douban.com" in lowered_body
        )

    @staticmethod
    def _looks_blocked(body: str) -> bool:
        lowered = body.lower()
        return any(marker in lowered for marker in _BLOCK_MARKERS)

    def _interest_url(self, subject_id: str) -> str:
        return f"{self.base_url}/j/subject/{subject_id}/interest"

    @staticmethod
    def _validate_subject_id(subject_id: str) -> None:
        if not _SUBJECT_ID_RE.fullmatch(subject_id):
            raise ValueError("Douban subject_id must contain digits only.")
