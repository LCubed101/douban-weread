# Feishu Book Inbox V1

> 第一次部署飞书机器人，请先看 [FEISHU_SETUP.md](FEISHU_SETUP.md)。

## Product role

Feishu Bot is the primary Book Inbox entry point. The local web UI remains a development/debug view over persisted reconciliation state.

## V1 flow

```text
Feishu text / URL / image
        ↓
Feishu event adapter
        ↓
BookInboxRequest
        ↓
book resolution
        ↓
BookInboxConfirmation
        ↓
Feishu interactive card
```

The confirmation card asks the user to confirm the candidate Edition before any state-changing action.

## Supported input boundary

- Plain text: normalized into a title-search request.
- Douban Book subject URL: exact `subject_id` is extracted.
- WeRead URL: preserved as a source URL; V1 does not guess a `bookId` from opaque URL parameters.
- Feishu image message: image resource is downloaded and passed to local OCR.
- Other Feishu message types: unsupported, fail closed.

## Feishu event boundary

The bot receives Feishu events through the SDK's WebSocket / long-connection transport. Message handling centers on `im.message.receive_v1` and supports text and image inputs.

## Card interaction boundary

The confirmation card emits explicit callback values:

```json
{"action": "confirm_book", "douban_subject_id": "..."}
{"action": "reject_book", "douban_subject_id": "..."}
```

When a WeRead identity is known, `weread_book_id` may also be included.

These values are UI intents. They do **not** authorize a mutation by themselves. The bot applies the write-safety flow before any Douban state change.

## Image flow

Current V1 image flow:

```text
Feishu image message
→ image resource download
→ local RapidOCR / ONNX Runtime
→ candidate title / ISBN evidence
→ existing resolver
→ confirmation card or conservative fallback
```

Do not use OCR as an identity source by itself. Extracted text is candidate evidence; Work/Edition verification still applies. If OCR evidence is ambiguous, V1 fails closed and asks the user for a clearer title, ISBN, Douban link, copyright page or barcode page instead of guessing an unrelated book.
