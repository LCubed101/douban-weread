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

## Checkpoint-only migration

After evidence persistence was introduced, an item is considered completed only when both of these exist for the same baseline/policy generation:

```text
checkpoint
AND
normalized evidence row
```

This means checkpoint-only rows produced by an older build are automatically re-verified once, so they can acquire reportable evidence rather than being skipped forever.

## Live persistence validation

The complete regression suite passed before the first live evidence migration run:

```text
Ran 230 tests in 0.473s
OK
```

Using the unchanged complete baseline pair and Douban → WeRead policy v3, two pre-existing checkpoint-only items were intentionally treated as not completed because they had no evidence rows yet. The live batch reported:

```text
Candidate queue: 1437
Already checkpointed in this generation: 0
Pending before batch: 1437
Batch size: 2
```

The first result remained a bounded unresolved catalog result:

```text
Watching the English
Douban state: do
Catalog search window: <= 10
WeRead catalog status: not_found
Resolution: no_weread_edition
User plan: weread_not_found
User action required: no
```

The second result preserved the resolver-v3 alternative-Edition finding:

```text
三体
Douban state: do
Catalog search window: <= 10
WeRead catalog status: available_alternative
Resolution: alternative_edition
Selected WeRead bookId: 178677
Selected Edition: 三体1
Current shelf membership: no
User plan: review_edition
User action required: yes
```

The batch completed with the explicit local persistence boundary:

```text
No mutation is performed. Verified normalized evidence is persisted locally before each checkpoint.
```

This live run validates the checkpoint-only migration path and confirms that normalized evidence persistence does not change the provider/resolver/user-plan semantics already established for the same inputs.

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

The evidence store supports a local report without re-running provider calls. Product-level aggregation is expressed in stable user-plan categories such as:

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

The report must always expose verified coverage separately from the pending queue so a partially processed baseline is never presented as a full-library conclusion.
