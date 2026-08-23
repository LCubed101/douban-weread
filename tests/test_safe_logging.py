from __future__ import annotations

import logging
import unittest

from douban_weread.safe_logging import install_log_redaction, redact_log_text


class SafeLoggingTests(unittest.TestCase):
    def test_redacts_feishu_websocket_query(self) -> None:
        value = (
            "connected to wss://msg-frontier.feishu.cn/ws/v2?fpid=1&"
            "access_key=secret&ticket=ticket-value [conn_id=123]"
        )
        redacted = redact_log_text(value)
        self.assertIn("wss://msg-frontier.feishu.cn/ws/v2?[REDACTED]", redacted)
        self.assertNotIn("secret", redacted)
        self.assertNotIn("ticket-value", redacted)

    def test_redacts_known_secret_query_pairs_outside_wss_url(self) -> None:
        redacted = redact_log_text("access_key=abc&ticket=def")
        self.assertEqual(redacted, "access_key=[REDACTED]&ticket=[REDACTED]")

    def test_install_redacts_formatted_log_arguments(self) -> None:
        install_log_redaction()
        record = logging.getLogger("safe-logging-test").makeRecord(
            "safe-logging-test",
            logging.INFO,
            __file__,
            1,
            "connected to %s",
            ("wss://msg-frontier.feishu.cn/ws/v2?access_key=abc&ticket=def",),
            None,
        )
        rendered = record.getMessage()
        self.assertIn("?[REDACTED]", rendered)
        self.assertNotIn("abc", rendered)
        self.assertNotIn("def", rendered)


if __name__ == "__main__":
    unittest.main()
