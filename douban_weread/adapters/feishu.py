from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from douban_weread.inbox import (
    BookInboxConfirmation,
    BookInboxInputKind,
    BookInboxRequest,
    request_from_image_key,
    request_from_text,
)


class FeishuMessageKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    UNSUPPORTED = "unsupported"


@dataclass(slots=True, frozen=True)
class FeishuInboundMessage:
    event_id: str
    message_id: str
    chat_id: str
    sender_open_id: str | None
    message_kind: FeishuMessageKind
    inbox_request: BookInboxRequest


def parse_feishu_event(payload: Mapping[str, Any]) -> FeishuInboundMessage | None:
    """Parse one unencrypted Feishu event subscription payload conservatively.

    Returns None for non-message events. The adapter intentionally supports only
    text and image message bodies in V1. Image messages are represented as
    IMAGE_PENDING until attachment download + vision is added.
    """

    header = payload.get("header")
    event = payload.get("event")
    if not isinstance(header, Mapping) or not isinstance(event, Mapping):
        return None
    if header.get("event_type") != "im.message.receive_v1":
        return None

    message = event.get("message")
    sender = event.get("sender")
    if not isinstance(message, Mapping):
        return None

    event_id = str(header.get("event_id") or "").strip()
    message_id = str(message.get("message_id") or "").strip()
    chat_id = str(message.get("chat_id") or "").strip()
    message_type = str(message.get("message_type") or "").strip()
    if not event_id or not message_id or not chat_id:
        raise ValueError("Feishu message event is missing stable event/message/chat identity")

    sender_open_id: str | None = None
    if isinstance(sender, Mapping):
        sender_id = sender.get("sender_id")
        if isinstance(sender_id, Mapping):
            value = str(sender_id.get("open_id") or "").strip()
            sender_open_id = value or None

    content = _parse_content(message.get("content"))
    if message_type == "text":
        text = str(content.get("text") or "")
        request = request_from_text(text)
        return FeishuInboundMessage(
            event_id=event_id,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            message_kind=FeishuMessageKind.TEXT,
            inbox_request=request,
        )

    if message_type == "image":
        image_key = str(content.get("image_key") or "").strip()
        request = request_from_image_key(image_key)
        return FeishuInboundMessage(
            event_id=event_id,
            message_id=message_id,
            chat_id=chat_id,
            sender_open_id=sender_open_id,
            message_kind=FeishuMessageKind.IMAGE,
            inbox_request=request,
        )

    return FeishuInboundMessage(
        event_id=event_id,
        message_id=message_id,
        chat_id=chat_id,
        sender_open_id=sender_open_id,
        message_kind=FeishuMessageKind.UNSUPPORTED,
        inbox_request=BookInboxRequest(input_kind=BookInboxInputKind.UNSUPPORTED),
    )


def build_confirmation_card(confirmation: BookInboxConfirmation) -> dict[str, Any]:
    """Build the first identity-confirmation card without performing mutation."""

    edition = confirmation.candidate
    details: list[str] = []
    if edition.authors:
        details.append("作者：" + "、".join(edition.authors))
    if edition.publisher:
        details.append("出版社：" + edition.publisher)
    if edition.publish_date:
        details.append("出版：" + edition.publish_date)
    if edition.isbn:
        details.append("ISBN：" + edition.isbn)

    identity: dict[str, str] = {}
    if edition.douban_id:
        identity["douban_subject_id"] = edition.douban_id
    if edition.weread_id:
        identity["weread_book_id"] = edition.weread_id

    confirm_value = {
        "action": "confirm_book",
        **identity,
    }
    reject_value = {
        "action": "reject_book",
        **identity,
    }

    elements: list[dict[str, Any]] = [
        {
            "tag": "markdown",
            "content": f"**{edition.title}**\n" + ("\n".join(details) if details else "请确认书名与版本信息。"),
        },
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "确认这本"},
                    "type": "primary",
                    "value": confirm_value,
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "不是这本"},
                    "type": "danger",
                    "value": reject_value,
                },
            ],
        },
    ]

    return {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {
            "title": {"tag": "plain_text", "content": confirmation.prompt},
            "template": "blue",
        },
        "elements": elements,
    }


def build_wish_confirmation_card(*, title: str, subject_id: str) -> dict[str, Any]:
    """Build the second, state-changing confirmation card.

    Rendering this card never authorizes a write by itself. The callback value
    explicitly carries a distinct `confirm_wish` action so the bot can require a
    second user click after a fresh read-only reconciliation preflight.
    """

    return {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {
            "title": {"tag": "plain_text", "content": "确认加入豆瓣想读？"},
            "template": "orange",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    f"**{title}**\n"
                    "已通过版本与豆瓣历史状态检查。\n"
                    "只有点击下面的确认按钮后，才会真正修改豆瓣。"
                ),
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "加入豆瓣想读"},
                        "type": "primary",
                        "value": {
                            "action": "confirm_wish",
                            "douban_subject_id": subject_id,
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "取消"},
                        "type": "danger",
                        "value": {
                            "action": "cancel_wish",
                            "douban_subject_id": subject_id,
                        },
                    },
                ],
            },
        ],
    }


def _parse_content(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("Feishu message content is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Feishu message content JSON must be an object")
    return parsed
