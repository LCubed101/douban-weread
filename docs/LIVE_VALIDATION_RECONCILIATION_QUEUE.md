# Live reconciliation queue validation

Date: 2026-08-20

Branch: `agent/weread-shelf-baseline`

## Local regression before queue validation

```text
Ran 183 tests in 0.328s
OK
```

The installed shelf CLI exposed:

```text
douban-weread weread shelf {sync,status,lookup,preview,queue,verify}
```

## Live local-only queue counts

The complete local baselines produced two deterministic title-only work queues:

```text
WeRead → Douban candidates: 169
Douban → WeRead candidates: 1437
```

Definitions:

```text
WeRead → Douban
= current WeRead shelf entries with no exact normalized-title match in any local Douban history state

Douban → WeRead
= active Douban WISH / READING entries with no exact normalized-title match on the current WeRead shelf
```

These are work queues only. They are not proof that a Work is absent from the other platform and they do not authorize mutation.

Representative WeRead → Douban queue items included:

```text
CB_Bna2k22lC98M74M75J4ov42Y | Maurice Merleau-Ponty: The World of Perception | private
37724838 | 一个无政府主义者的意外死亡
32535536 | 一人份的热闹
35276968 | 一人企业：一个人也能赚钱的商业新模式
26797704 | 一间只属于自己的房间（果麦经典）
```

Representative Douban → WeRead queue items included:

```text
35791241 | 1000个铁粉 | wish
35224085 | 100天后会死的鳄鱼君 | wish
27019726 | 10人以下小团队管理手册 | wish
36414591 | 10种洞察 | wish
37497866 | 12种智慧 | wish
```

## First live queue-item verification

WeRead book `37724838` had already been verified through the bounded lazy-verification path:

```text
Title: 一个无政府主义者的意外死亡
WeRead progress: 0%
Started: no
Verified WeRead state: unread
```

The best resolver-confirmed Douban candidate was:

```text
Douban subject: 26649304
ISBN: 9787532770892
Match: exact_edition
Exact Edition: True
Local history state: none
```

The suggestion-only policy returned:

```text
Action: suggest_wish
Suggested Douban state: wish
Safe to auto apply: False
Requires user decision: True
```

This proves that queue membership can be upgraded from a title-only miss to verified Work/Edition identity plus a conservative reading-state recommendation.

## Background batch design

A read-only checkpointed batch runner has now landed and awaits local regression.

The batch design intentionally differs from simply taking the first N queue rows on every login:

1. One invocation processes at most 5 items; the default CLI batch size is 3.
2. Successful verification is checkpointed locally by:

```text
direction + item_id + WeRead shelf baseline timestamp + Douban history baseline timestamp
```

3. Re-running against the same pair of baselines skips checkpointed items.
4. A new complete Douban-history or WeRead-shelf sync naturally creates a new generation, so items can be reconsidered with fresh evidence.
5. Provider/parser failures fail closed and are not checkpointed as successful work.
6. Private WeRead shelf items are deprioritized behind normal shelf books for background processing.
7. Checkpoints record only item identity, baseline generation, outcome, and timestamp. They do not store API keys, Cookies, or full provider payloads.
8. Checkpoints never authorize a remote mutation.

The two batch directions remain semantically distinct:

```text
WeRead → Douban
→ shelf item
→ /book/info
→ /book/getprogress
→ bounded Douban discovery + local history shortlist
→ resolver
→ suggestion-only Douban state outcome

Douban → WeRead
→ exact Douban subject
→ bounded official WeRead catalog search
→ /book/info for candidates
→ resolver
→ AVAILABLE_EXACT / AVAILABLE_ALTERNATIVE / UNAVAILABLE / bounded NOT_FOUND
```

## Status

- Queue generation: live validated.
- Single-item WeRead → Douban verification: live validated.
- Batch checkpoint implementation: landed, local regression pending.
- Batch live run: not yet performed.
- No cross-platform mutation is authorized or performed by this milestone.
