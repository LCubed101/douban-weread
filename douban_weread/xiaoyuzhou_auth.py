from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_BASE = "https://api.xiaoyuzhoufm.com"
REFRESH_PATH = "/app_auth_tokens.refresh"
APP_USER_AGENT = "Xiaoyuzhou/2.7.0 (build:1234; iOS 17.0.0)"
DEFAULT_DEVICE_ID = "00000000-0000-0000-0000-000000000000"
DEFAULT_REFRESH_TOKEN_FILE = Path.home() / ".config" / "douban-weread" / "xiaoyuzhou_refresh_token"


class XiaoyuzhouRefreshError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class XiaoyuzhouTokens:
    access_token: str
    refresh_token: str


def refresh_access_token(
    refresh_token: str,
    *,
    device_id: str | None = None,
    timeout: float = 15.0,
) -> XiaoyuzhouTokens:
    token = refresh_token.strip()
    if not token:
        raise XiaoyuzhouRefreshError("Xiaoyuzhou refresh token is empty.")

    headers: dict[str, str] = {
        "User-Agent": APP_USER_AGENT,
        "Content-Type": "application/json",
        "x-jike-app-version": "2.7.0",
        "x-jike-device-id": (device_id or DEFAULT_DEVICE_ID).strip(),
        "x-jike-refresh-token": token,
    }

    request = Request(f"{API_BASE}{REFRESH_PATH}", data=b"", headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed provider URL
            access = str(response.headers.get("x-jike-access-token") or "").strip()
            rotated = str(response.headers.get("x-jike-refresh-token") or token).strip()
    except HTTPError as exc:
        raise XiaoyuzhouRefreshError(f"Xiaoyuzhou token refresh failed with HTTP {exc.code}.") from exc
    except URLError as exc:
        raise XiaoyuzhouRefreshError(f"Could not reach Xiaoyuzhou token refresh endpoint: {exc.reason}") from exc

    if not access:
        raise XiaoyuzhouRefreshError("Xiaoyuzhou token refresh returned no access token.")
    return XiaoyuzhouTokens(access_token=access, refresh_token=rotated or token)


def _atomic_private_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".xiaoyuzhou-token-", dir=str(path.parent), text=True)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def load_or_refresh_access_token(
    *,
    token_file: str | Path | None = None,
    device_id: str | None = None,
) -> str:
    """Return an access token, refreshing from a local rotating refresh-token file when needed.

    Existing XIAOYUZHOU_ACCESS_TOKEN wins and requires no file access. Otherwise
    the refresh token is read from XIAOYUZHOU_REFRESH_TOKEN_FILE or the default
    private config path, exchanged once, and any rotated refresh token is written
    back atomically with mode 0600.
    """

    existing = os.getenv("XIAOYUZHOU_ACCESS_TOKEN", "").strip()
    if existing:
        return existing

    configured = token_file or os.getenv("XIAOYUZHOU_REFRESH_TOKEN_FILE", "").strip() or DEFAULT_REFRESH_TOKEN_FILE
    path = Path(configured).expanduser()
    if not path.exists():
        raise XiaoyuzhouRefreshError(f"Xiaoyuzhou refresh-token file not found: {path}")

    refresh = path.read_text(encoding="utf-8").strip()
    tokens = refresh_access_token(
        refresh,
        device_id=device_id or os.getenv("XIAOYUZHOU_DEVICE_ID", "").strip() or None,
    )
    if tokens.refresh_token != refresh:
        _atomic_private_write(path, tokens.refresh_token + "\n")
    return tokens.access_token
