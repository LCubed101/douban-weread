from __future__ import annotations

from collections.abc import Sequence

from douban_weread import feishu_bot as base
from douban_weread.adapters.feishu_ocr import ImageTextRecognizer
from douban_weread.core.book_mentions import BookMention, extract_book_mentions
from douban_weread.core.models import Edition
from douban_weread.inbox_weread import WeReadLookupKind
from douban_weread.inbox_weread_watch import WeReadWatchStoreLike, record_unavailable_watch


def _image_resource_keys(message: base.InboundMessageLike) -> tuple[str, ...]:
    keys: list[str] = []
    seen: set[str] = set()
    resources: Sequence[object] = getattr(message, "resources", ()) or ()

    for resource in resources:
        resource_type = str(getattr(resource, "type", "") or "").strip().casefold()
        file_key = str(getattr(resource, "file_key", "") or "").strip()
        if resource_type == "image" and file_key and file_key not in seen:
            seen.add(file_key)
            keys.append(file_key)

    # Some single-image payloads do not expose a normalized resource type.
    # Preserve the existing fallback for those messages.
    if not keys and getattr(message, "raw_content_type", "") == "image":
        fallback = base._image_resource_key(resources)
        if fallback:
            keys.append(fallback)

    return tuple(keys)


def _image_resource_count(message: base.InboundMessageLike) -> int:
    return len(_image_resource_keys(message))


async def mentions_from_message(
    channel: base.ChannelLike,
    message: base.InboundMessageLike,
    recognizer: ImageTextRecognizer,
) -> tuple[BookMention, ...]:
    """Merge text + OCR from every image resource, then extract books once."""

    text_parts: list[str] = []
    if getattr(message, "raw_content_type", "") in {"text", "post", ""}:
        text = str(getattr(message, "content_text", "") or "").strip()
        if text:
            text_parts.append(text)

    for file_key in _image_resource_keys(message):
        image_bytes = await channel.download_resource(
            file_key,
            resource_type="image",
            message_id=message.message_id,
        )
        if not image_bytes:
            # Partial failure should not throw away OCR from the other images.
            continue
        lines = await recognizer.recognize(bytes(image_bytes))
        text_parts.extend(str(line) for line in lines if str(line).strip())

    if not text_parts:
        return ()
    return extract_book_mentions("\n".join(text_parts))


async def try_handle_book_batch_message(
    channel: base.ChannelLike,
    message: base.InboundMessageLike,
    recognizer: ImageTextRecognizer,
    weread_lookup: base.WeReadLookupLike | None,
    candidate_store: base.CandidateSelectionStore,
    weread_watch_store: WeReadWatchStoreLike | None = None,
) -> bool:
    """Handle multi-book text/images, including one Feishu post with several images."""

    if weread_lookup is None:
        return False

    from douban_weread import feishu_bot_v11 as v11

    image_count = _image_resource_count(message)
    mentions = await mentions_from_message(channel, message, recognizer)

    # Keep ordinary single-book text / single-image behavior unchanged.
    # A message carrying 2+ images is explicitly a batch capture, so do not
    # fall back into the legacy single-image Douban path.
    if len(mentions) < 2 and image_count < 2:
        return False

    if not mentions:
        await channel.send(
            message.chat_id,
            {
                "text": (
                    f"收到 {image_count} 张图片，但暂时没有识别到明确的《书名》。\n"
                    "可以换更清晰的截图，或直接发送书名。"
                )
            },
            {"reply_to": message.message_id},
        )
        return True

    candidate_store.clear(message.chat_id)
    results = await v11._lookup_mentions(mentions, weread_lookup)

    for mention, result, error in results:
        if error is not None or result is None:
            continue
        kind = getattr(result, "kind", None)
        if (
            weread_watch_store is not None
            and kind in {WeReadLookupKind.UNAVAILABLE, WeReadLookupKind.NOT_FOUND}
        ):
            record_unavailable_watch(
                chat_id=message.chat_id,
                source=Edition(title=mention.title),
                result=result,
                store=weread_watch_store,
            )

    await channel.send(
        message.chat_id,
        {
            "card": v11._batch_summary_card(
                mentions=mentions,
                outcomes=results,
                chat_id=message.chat_id,
                watch_store=weread_watch_store,
            )
        },
        {"reply_to": message.message_id},
    )
    return True


def prepare_multi_image_support() -> None:
    """Install the shared multi-image capture path into both router modes."""

    from douban_weread import feishu_bot_v11 as v11
    from douban_weread import feishu_bot_weread_only as weread_only

    v11._mentions_from_message = mentions_from_message
    v11._try_handle_multi_book_message = try_handle_book_batch_message
    weread_only._mentions_from_message = mentions_from_message
