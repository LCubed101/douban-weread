# WeRead checkpointed batch live validation

Date: 2026-08-20

Branch: `agent/weread-shelf-baseline`

## Local regression

The complete local suite passed after checkpointed batch support was added:

```text
Ran 198 tests in 0.543s
OK
```

The installed shelf CLI exposed:

```text
douban-weread weread shelf {sync,status,lookup,preview,queue,verify,batch}
```

The `batch` command is read-only and processes at most five pending items per invocation. Checkpoints are scoped to the pair of local baseline timestamps; no credential or provider response payload is persisted as checkpoint data.

## First live WeRead → Douban batch

The first live batch was run with:

```text
Direction: weread-to-douban
Douban baseline: 2026-08-19T11:08:42.065667+00:00
WeRead shelf baseline: 2026-08-20T11:39:53.739860+00:00
Candidate queue: 169
Already checkpointed in this generation: 0
Pending before batch: 169
Batch size: 2
```

The first processed item was:

```text
一个无政府主义者的意外死亡
WeRead bookId: 37724838
WeRead state: unread
Progress: 0%
Douban subject: 26649304
Match: exact_edition
Exact Edition: True
Existing Douban Work state: none
Outcome: suggest_wish
Suggested Douban state: wish
Requires user decision: True
Checkpointed for this baseline: yes
```

The second processed item was:

```text
一人份的热闹
WeRead bookId: 32535536
WeRead state: unread
Progress: 0%
Douban subject: 35041489
Match: exact_edition
Exact Edition: True
Existing Douban Work state: none
Outcome: suggest_wish
Suggested Douban state: wish
Requires user decision: True
Checkpointed for this baseline: yes
```

The batch completed with:

```text
Processed this batch: 2
Remaining pending for this generation: 167
```

No mutation was performed on either platform.

## Candidate ordering observation

The local queue previously listed a private/import-like item first:

```text
CB_Bna2k22lC98M74M75J4ov42Y | Maurice Merleau-Ponty: The World of Perception | private
```

The first live batch instead selected two ordinary electronic books before that item. This is evidence that the current batch ordering defers private/import-like shelf entries rather than prioritizing them.

## Live checkpoint resume validation

The exact same batch command was then run again without refreshing either local baseline. The second run reported:

```text
Candidate queue: 169
Already checkpointed in this generation: 2
Pending before batch: 167
Batch size: 2
```

The two previously processed book IDs (`37724838` and `32535536`) were not requested again. The batch resumed with new items instead.

The next processed item was:

```text
一人企业：一个人也能赚钱的商业新模式
WeRead bookId: 35276968
WeRead state: unread
Progress: 0%
Douban subject: 35293067
Match: exact_edition
Exact Edition: True
Existing Douban Work state: none
Outcome: suggest_wish
Suggested Douban state: wish
Requires user decision: True
Checkpointed for this baseline: yes
```

The following item exposed a useful reread case:

```text
一间只属于自己的房间（果麦经典）
WeRead bookId: 26797704
WeRead state: reading
Progress: 0%
Douban subject: 34835082
Match: exact_edition
Exact Edition: True
Existing Douban Work state: read
Outcome: ask_reread
Suggested Douban state: read
Requires user decision: True
Checkpointed for this baseline: yes
```

The second batch completed with:

```text
Processed this batch: 2
Remaining pending for this generation: 165
```

This live run proves that baseline-scoped checkpoints resume the queue instead of repeatedly verifying the same successful items.

## `progress=0` can still be Reading when start evidence exists

The reread case also confirms an important reading-state distinction. `Progress: 0%` is not sufficient by itself to classify a book as unread. The official progress payload also exposes start evidence (`isStartReading`), and the project intentionally maps:

```text
progress = 0 + not started
→ UNREAD

progress = 0 + started
→ READING
```

This is consistent with the earlier live case where `37724838` had `Progress: 0%`, `Started: no`, and was classified `unread`. In contrast, `26797704` had start evidence and was classified `reading` despite the displayed percentage remaining 0.

Because the verified Douban Work was already `READ`, the policy returned `ask_reread` and preserved the stronger historical state instead of downgrading it to `READING`.

## Safety boundary

- Batch processing is read-only.
- Batch size is capped at five items per invocation.
- Resolver-confirmed identity is required before cross-platform state recommendation.
- State-changing recommendations remain `safe_to_auto_apply=False`.
- A checkpoint only records that an item was processed for a specific pair of local baseline timestamps.
- Refreshing either complete baseline creates a new reconciliation generation naturally.
- Provider failures must not be checkpointed as completed work.
- A 0% displayed progress value is not treated as sufficient reading-state evidence without considering the official start flag.
