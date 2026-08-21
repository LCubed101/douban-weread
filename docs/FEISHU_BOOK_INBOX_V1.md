# Feishu Book Inbox V1

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
book resolution (next step)
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
- Feishu image message: `image_key` is preserved as `IMAGE_PENDING`. Attachment download and vision recognition are deliberately a separate step.
- Other Feishu message types: unsupported, fail closed.

## Feishu event boundary

V1 parses the unencrypted Feishu event-subscription shape for `im.message.receive_v1` and requires stable `event_id`, `message_id`, and `chat_id` values.

Network authentication, webhook verification/encryption, idempotency storage, Feishu API token acquisition, and message sending are not implemented by this adapter primitive yet. Those belong to the transport layer and are the next integration step.

## Card interaction boundary

The confirmation card emits explicit callback values:

```json
{"action": "confirm_book", "douban_subject_id": "..."}
{"action": "reject_book", "douban_subject_id": "..."}
```

When a WeRead identity is known, `weread_book_id` may also be included.

These values are only UI intents. They do **not** authorize or perform a Douban/WeRead mutation. A later callback handler must re-load/reconcile the candidate and apply the existing write-safety policy before any mutation.

## Image plan

The intended image flow is:

```text
Feishu image message
→ image_key
→ authenticated Feishu attachment download
→ vision extracts title/author/ISBN candidates
→ BookInboxRequest
→ existing resolver
→ confirmation card
```

Do not use OCR as an identity source by itself. Extracted text is candidate evidence; Work/Edition verification still applies.
