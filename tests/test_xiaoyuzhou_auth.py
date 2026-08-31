from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from douban_weread.xiaoyuzhou_auth import load_or_refresh_access_token, refresh_access_token


class FakeResponse:
    def __init__(self, headers):
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_refresh_reads_tokens_from_response_headers():
    response = FakeResponse({
        "x-jike-access-token": "new-access",
        "x-jike-refresh-token": "new-refresh",
    })
    with patch("douban_weread.xiaoyuzhou_auth.urlopen", return_value=response):
        tokens = refresh_access_token("old-refresh", device_id="device")
    assert tokens.access_token == "new-access"
    assert tokens.refresh_token == "new-refresh"


def test_refresh_token_file_is_rotated_privately():
    response = FakeResponse({
        "x-jike-access-token": "new-access",
        "x-jike-refresh-token": "new-refresh",
    })
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "token"
        path.write_text("old-refresh\n", encoding="utf-8")
        with patch.dict(os.environ, {"XIAOYUZHOU_ACCESS_TOKEN": ""}, clear=False):
            with patch("douban_weread.xiaoyuzhou_auth.urlopen", return_value=response):
                access = load_or_refresh_access_token(token_file=path)
        assert access == "new-access"
        assert path.read_text(encoding="utf-8").strip() == "new-refresh"
        assert path.stat().st_mode & 0o777 == 0o600


def test_existing_access_token_skips_refresh_file():
    with patch.dict(os.environ, {"XIAOYUZHOU_ACCESS_TOKEN": "existing-access"}, clear=False):
        assert load_or_refresh_access_token(token_file="/definitely/missing") == "existing-access"
