# Local reconciliation evidence

Date: 2026-08-20

Branch: `agent/weread-shelf-baseline`

## Purpose

Checkpoint-only background reconciliation is not sufficient for a final user report. A checkpoint can answer "was this item already verified for this generation?" but cannot reconstruct why the item was classified as aligned, missing, alternative Edition, reread conflict, or bounded not-found.

The project therefore persists a normalized evidence row for every successfully verified batch item.

## Generation key

Evidence is scoped by:

```text
direction
+ item_id
+ complete WeRead shelf baseline timestamp
+ complete Douban history baseline timestamp
+ direction-specific reconciliation policy version
```

Unlike the earlier checkpoint table, the evidence primary key includes `policy_version`, so evidence from older algorithms can coexist with a newer generation for comparison and audit.

## Stored normalized fields

The evidence table stores only report-relevant normalized facts:

```text
direction / item_id / title
source state
provider-level outcome
user plan / summary / requires-user-action
selected Douban subject
selected WeRead bookId / Edition title
resolver match kind
exact-Edition flag
requires-confirmation flag
WeRead catalog status / resolution
current shelf membership
WeRead coarse reading state / progress
strongest Douban Work state
suggested Douban state
deep link
bounded catalog search limit
recorded timestamp
```

Not every field applies to both directions; non-applicable fields remain null.

## Write ordering

For one successfully verified item the batch order is:

```text
provider verification
→ normalized BatchItemResult
→ user-facing plan
→ persist normalized evidence
→ persist checkpoint
```

Evidence is deliberately written before the checkpoint. If evidence persistence fails, the item must not become a checkpoint-only success that would later be skipped despite having no reportable evidence. A retry can safely overwrite the same evidence key before checkpointing.

## Privacy and security boundary

The evidence table must not contain:

```text
raw provider response payloads
full shelf payloads
Douban Cookie values
WeRead API keys
credentials or bearer tokens
mutation authorization
```

It contains normalized reconciliation facts only. The existing local-first SQLite database remains the storage boundary.

## Reporting goal

Once enough background items are verified, the evidence store is intended to support a report without re-running provider calls. The product-level aggregation should be expressed in stable user-plan categories such as:

```text
aligned
add_to_weread_shelf_exact
add_to_weread_shelf_alternative
suggest_douban_wish
suggest_douban_reading
suggest_douban_read
keep_douban_history
review_reread
review_edition
review_identity
review_state
weread_unavailable
weread_not_found
```

This report layer is the next milestone after evidence persistence is regression-validated.
