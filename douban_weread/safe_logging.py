from __future__ import annotations

import logging
import re
from typing import Any


_WSS_QUERY_RE = re.compile(r"(wss://msg-frontier\.feishu\.cn/ws/v2)\?[^\s]+")
_SECRET_QUERY_RE = re.compile(
    r"(?i)(access_key|ticket|app_secret|authorization|cookie)=([^&\s]+)"
)
_INSTALLED = False


def redact_log_text(value: str) -> str:
    """Remove connection credentials and known secret query values from logs."""
    text = _WSS_QUERY_RE.sub(r"\1?[REDACTED]", value)
    return _SECRET_QUERY_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_log_text(value)
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    return value


def install_log_redaction() -> None:
    """Install a process-wide LogRecord factory that redacts before handlers persist logs."""
    global _INSTALLED
    if _INSTALLED:
        return

    previous_factory = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = previous_factory(*args, **kwargs)
        record.msg = _redact_value(record.msg)
        record.args = _redact_value(record.args)
        return record

    logging.setLogRecordFactory(factory)
    _INSTALLED = True
