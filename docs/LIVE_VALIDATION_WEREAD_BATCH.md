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

## Checkpoint validation still pending

A second invocation against the exact same pair of local baselines is required to prove the checkpoint resume behavior live. The expected behavior is:

```text
Already checkpointed in this generation: 2
Pending before batch: 167
```

and the two previously processed book IDs must not be requested again.

Only after this repeat-run proof should the checkpointed resume behavior be considered live-validated.

## Safety boundary

- Batch processing is read-only.
- Batch size is capped at five items per invocation.
- Resolver-confirmed identity is required before cross-platform state recommendation.
- State-changing recommendations remain `safe_to_auto_apply=False`.
- A checkpoint only records that an item was processed for a specific pair of local baseline timestamps.
- Refreshing either complete baseline creates a new reconciliation generation naturally.
- Provider failures must not be checkpointed as completed work.
