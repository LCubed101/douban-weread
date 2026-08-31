from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from douban_weread.feishu_movie_bot import _normalize_card_action_event


class FeishuMovieBotActionNormalizationTests(unittest.TestCase):
    def test_normalizes_snake_case_mapping_value(self):
        event = SimpleNamespace(
            chat_id="oc_chat",
            message_id="om_msg",
            action=SimpleNamespace(
                tag="button",
                value={"action": "confirm_movie", "movie_subject_id": "35426925"},
            ),
        )

        normalized = _normalize_card_action_event(event)

        self.assertEqual(normalized["chat_id"], "oc_chat")
        self.assertEqual(normalized["message_id"], "om_msg")
        self.assertEqual(normalized["action"]["value"]["action"], "confirm_movie")

    def test_normalizes_camel_case_and_json_string_value(self):
        payload = {"action": "confirm_wish", "douban_subject_id": "123"}
        event = SimpleNamespace(
            chatId="oc_chat",
            messageId="om_msg",
            action=SimpleNamespace(tag="button", value=json.dumps(payload)),
        )

        normalized = _normalize_card_action_event(event)

        self.assertEqual(normalized["chat_id"], "oc_chat")
        self.assertEqual(normalized["message_id"], "om_msg")
        self.assertEqual(normalized["action"]["value"], payload)

    def test_invalid_string_value_fails_closed(self):
        event = {
            "chatId": "oc_chat",
            "messageId": "om_msg",
            "action": {"tag": "button", "value": "not-json"},
        }

        normalized = _normalize_card_action_event(event)

        self.assertEqual(normalized["action"]["value"], {})


if __name__ == "__main__":
    unittest.main()
