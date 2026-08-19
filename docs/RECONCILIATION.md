# Work-Level Reading-State Reconciliation

Status: **implemented for Douban candidate scanning; live validation required**.

## Why this layer exists

A correct edition match is not enough to authorize a state change.

The same Work may already exist in a user's reading history under a different Edition. A user may have forgotten that they already read it, may currently be reading another edition, or may have marked a different edition as Want-to-Read.

Therefore the safe mutation path is:

```text
Resolve exact target Edition
→ inspect existing states for the same Work
→ reconcile state + edition differences
→ require confirmation
→ mutate
→ verify saved state
```

## Internal reading-state abstraction

Current Douban mapping:

| Douban raw state | Internal state |
| --- | --- |
| no state | `NONE` |
| `wish` | `WISH` |
| `do` | `READING` |
| `collect` | `READ` |

Future WeRead states will be mapped into the same provider-independent layer only after the actual WeRead capabilities are verified.

## Read is sticky

State precedence is used to prevent accidental downgrade:

```text
READ > READING > WISH > NONE
```

This does **not** mean states should be silently copied between platforms or editions.

Examples:

- target Edition already `READ` → no-op; never downgrade to `WISH`
- target Edition already `READING` → no-op; never downgrade to `WISH`
- target Edition already `WISH` → no duplicate write
- another Edition of the same Work is `READ` → ask whether this is a reread
- another Edition is `READING` → block a competing automatic `WISH`
- another Edition is `WISH` → treat as an edition mismatch requiring review
- no known state for the Work → eligible for an explicitly confirmed `WISH`

## CLI

Read one exact subject state:

```bash
douban-weread status --subject 25837854
```

Inspect same-Work state history without writing:

```bash
douban-weread inspect --subject 25837854
```

A representative result is:

```text
Decision: ask_reread
Safe to write Want-to-Read: False
Requires user decision: True
```

The `wish` command now performs the same reconciliation before mutation:

```bash
douban-weread wish --subject 25837854 --confirm
```

If reconciliation finds an existing `READ`, `READING`, or other-edition `WISH`, the command fails closed and performs no write.

## Current discovery strategy

The first implementation:

1. fetches the exact target subject;
2. searches Douban by the target title;
3. uses the Edition resolver to keep only candidates classified as the same Work;
4. reads authenticated interest state for those candidate subjects;
5. applies the reconciliation policy.

This is intentionally conservative but **not exhaustive**. Public title search may not surface every historical edition a user has ever marked.

Therefore `SAFE_TO_WISH` currently means:

> No conflicting state was found among the same-Work editions discovered by the current provider scan.

It does not yet mean that the user's complete Douban history has been exhaustively indexed.

## Next reliability layer: local reading-history index

To solve the "I may already have read this but forgot" case robustly, the next stage should ingest the user's own Douban reading lists and maintain a local history index keyed by Work and Edition.

Conceptually:

```text
Douban WISH list
Douban READING list
Douban READ list
        ↓
normalized Editions
        ↓
Work resolution
        ↓
local reading-history index
        ↓
new capture / WeRead candidate
        ↓
reconciliation before mutation
```

This history index should preserve the original platform state and Edition rather than collapsing all records into one title-level flag.

## Future cross-platform shape

```text
Work
├── Editions
├── Douban states
│   └── Edition → NONE / WISH / READING / READ
├── WeRead states
│   └── Edition → provider-verified state
└── Reconciliation
    ├── state mismatch
    ├── edition mismatch
    ├── already read / reread detection
    └── recommended action
```

WeRead state names must not be assumed until the provider is live-verified.

## Safety rules

- Never downgrade a known `READ` or `READING` state to `WISH` automatically.
- Never treat a same-title different Edition as a harmless duplicate.
- Never let title-only similarity authorize mutation.
- Fail closed when state discovery fails.
- Preserve all observed Edition identities and provider states for future reconciliation.
- A real write still requires explicit confirmation and post-write verification.
