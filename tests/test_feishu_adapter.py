from __future__ import annotations

import json
import unittest

from douban_weread.adapters.feishu import FeishuMessageKind, build_confirmation_card, parse_feishu_event
from douban_weread.core.models import Edition
from douban_weread.inbox import BookInboxConfirmation, BookInboxInputKind, request_from_text


def _event(*, message_type: str, content: dict[str, object]) -> dict[str, object]:
    return {
        "header": {
            "event_id": "evt_1",
            "event_type": "im.message.receive_v1",
        },
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_id": "om_1",
                "chat_id": "oc_1",
                "message_type": message_type,
                "content": json.dumps(content, ensure_ascii=False),
            },
        },
    }


class FeishuAdapterTests(unittest.TestCase):
    def test_text_message_becomes_book_inbox_request(self) -> None:
        inbound = parse_feishu_event(_event(message_type="text", content={"text": "三体"}))
        self.assertIsNotNone(inbound)
        assert inbound is not None
        self.assertEqual(inbound.message_kind, FeishuMessageKind.TEXT)
        self.assertEqual(inbound.inbox_request.input_kind, BookInboxInputKind.TEXT)
        self.assertEqual(inbound.inbox_request.search_query, "三体")
        self.assertEqual(inbound.sender_open_id, "ou_1")

    def test_image_message_preserves_image_key_as_pending(self) -> None:
        inbound = parse_feishu_event(_event(message_type="image", content={"image_key": "img_v3_abc"}))
        self.assertIsNotNone(inbound)
        assert inbound is not None
        self.assertEqual(inbound.message_kind, FeishuMessageKind.IMAGE)
        self.assertEqual(inbound.inbox_request.input_kind, BookInboxInputKind.IMAGE_PENDING)
        self.assertEqual(inbound.inbox_request.image_key, "img_v3_abc")

    def test_non_message_event_is_ignored(self) -> None:
        payload = {"header": {"event_type": "contact.user.created_v3"}, "event": {}}
        self.assertIsNone(parse_feishu_event(payload))

    def test_confirmation_card_has_explicit_confirm_and_reject_actions(self) -> None:
        confirmation = BookInboxConfirmation(
            request=request_from_text("三体"),
            candidate=Edition(
                title="三体",
                authors=["刘慈欣"],
                publisher="重庆出版社",
                publish_date="2008-01",
                isbn="9787536692930",
                douban_id="2567698",
            ),
        )
        card = build_confirmation_card(confirmation)
        actions = card["elements"][1]["actions"]
        self.assertEqual(actions[0]["value"]["action"], "confirm_book")
        self.assertEqual(actions[0]["value"]["douban_subject_id"], "2567698")
        self.assertEqual(actions[1]["value"]["action"], "reject_book")
        self.assertIn("刘慈欣", card["elements"][0]["content"])
        self.assertIn("9787536692930", card["elements"][0]["content"])


if __name__ == "__main__":
    unittest.main()
