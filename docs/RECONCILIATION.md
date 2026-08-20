# Work-Level Reading-State Reconciliation

Status: **history-aware reconciliation implemented, regression-tested, and live-validated for the forgotten-history safety path**.

## Why this layer exists

A correct edition match is not enough to authorize a state change.

The same Work may already exist in a user's reading history under a different Edition. A user may have forgotten that they already read it, may currently be reading another edition, or may have marked a different edition as Want-to-Read.

Therefore the safe mutation path is:

```text
Resolve exact target Edition
→ query complete local reading-history baseline
→ shortlist relevant historical subject IDs
→ lazily resolve full Edition metadata
→ verify same Work
→ combine historical + current provider state conservatively
→ reconcile state + edition differences
→ require confirmation
→ mutate
→ verify saved state
→ update local index
```

The complete Douban history is never sent to an LLM and is not refetched for every new book.

## Internal reading-state abstraction

Current Douban mapping:

| Douban raw state | Internal state |
| --- | --- |
| no state | `NONE` |
| `wish` | `WISH` |
| `do` | `READING` |
| `collect` | `READ` |
| unrecognized value | `UNKNOWN` |

State precedence prevents accidental downgrade:

```text
READ > READING > WISH > NONE
```

If the local snapshot and a current provider read disagree, reconciliation keeps the stronger known state. An unrecognized provider state remains `UNKNOWN` and fails closed.

This does **not** silently copy state between editions or infer that two editions are the same Work.

## History-aware discovery

The current inspector uses two discovery paths:

```text
A. live Douban title search (up to 20 candidates)
B. local Reading History Index title shortlist
```

For local history candidates, the lightweight SQLite row contains only `subject_id + title + state`. Before a candidate may affect reconciliation, the inspector fetches full Edition metadata for that subject and runs the normal resolver.

Therefore:

```text
local title similarity
≠
same Work
≠
same Edition
≠
write authorization
```

Only a candidate that survives full same-Work verification contributes a `WorkStateRecord`.

## Complete-baseline requirement

`inspect` and confirmed `wish` require a complete, current-schema local history baseline.

If the baseline is missing or invalidated, reconciliation fails closed with an instruction to run:

```bash
douban-weread history sync --full
```

This prevents the old bounded title-search path from being silently treated as exhaustive write safety.

## CLI

Read one exact subject state:

```bash
douban-weread status --subject 25837854
```

Inspect same-Work state history without writing:

```bash
douban-weread inspect --subject 25837854 --limit 20
```

The default live candidate limit is 20.

The state-changing path is:

```bash
douban-weread wish --subject 25837854 --confirm
```

Before a write, the command requires:

1. a complete local history baseline;
2. target Edition resolution;
3. local-history candidate discovery;
4. lazy full Edition resolution for shortlisted history subjects;
5. same-Work verification;
6. conservative state reconciliation;
7. explicit `--confirm`.

After a verified write succeeds, the local history index is updated immediately so project-owned mutations do not wait for the next full sync.

## Reconciliation outcomes

- target Edition already `READ` → no-op; never downgrade to `WISH`
- target Edition already `READING` → no-op; never downgrade to `WISH`
- target Edition already `WISH` → no duplicate write
- another Edition of the same Work is `READ` → `ASK_REREAD`
- another Edition is `READING` → block competing `WISH`
- another Edition is `WISH` → edition mismatch review
- any `UNKNOWN` state → fail closed
- no conflicting state → `SAFE_TO_WISH`, still requiring explicit confirmation

## Reading History Index validation — 2026-08-19

The prerequisite local history foundation was live-validated on the stacked base branch:

```text
Ran 98 tests in 0.066s
OK

History baseline: complete
Total: 1747
Want-to-Read: 1511
Reading: 40
Read: 196
```

After Cookie removal, local positive lookups returned:

```text
白夜行
- READ | subject 3259440 | 白夜行
- READ | subject 10554308 | 白夜行

素食者
- READ | subject 35534519 | 素食者
```

PIT-020 through PIT-022 document the parser and candidate-quality failures found during that validation.

## History-aware reconciliation validation — 2026-08-20

The full branch regression suite passed:

```text
Ran 103 tests in 0.240s
OK
```

After the temporary provider-access event recorded as PIT-023 recovered, the live validation used target subject `27112607` (`白夜行`, 刘姿君, 南海出版公司, 2017-07, ISBN `9787544291163`).

A direct resolver check confirmed historical subject `10554308` is the same Work but an alternative Edition:

```text
TARGET: 白夜行 ['刘姿君'] 南海出版公司 2017-07 9787544291163
HISTORY: 白夜行 ['刘姿君'] 南海出版公司 2013-01 9787544258609
same_work: True
kind: alternative_edition
requires_confirmation: False
differences: ['ISBN differs', 'publication year differs'] []
```

The read-only inspection intentionally constrained live title discovery to one candidate:

```bash
douban-weread inspect --subject 27112607 --limit 1
```

Observed records:

```text
NONE [target] | subject 27112607 | 刘姿君 · 南海出版公司 · 2017-07 · 9787544291163
READ | subject 10554308 | 刘姿君 · 南海出版公司 · 2013-01 · 9787544258609
READ | subject 3259440 | 刘姿君 · 南海出版公司 · 2008-09 · 9787544242516
```

Observed decision:

```text
Decision: ask_reread
Safe to write Want-to-Read: False
Requires user decision: True
```

This demonstrates the intended safety property: a currently unmarked target Edition is not considered safe to mark Want-to-Read when other same-Work Editions exist in the complete local history as `READ`. The historical subjects were supplied by the local index despite the deliberately tiny live-search bound, then resolved to full Edition metadata and verified as the same Work before affecting the decision.

No state-changing Douban write was performed in this validation.

## Known boundary

The local shortlist is still title-based candidate discovery. It greatly improves forgotten-history coverage but cannot prove that every alternate title for the same Work will be discovered. Full Work identity remains the resolver's responsibility after candidate discovery.

Future improvements may add more local discovery signals (author/title aliases or provider-verified Work links) without sending the full history to an LLM.

## Safety rules

- Never downgrade a known `READ` or `READING` state to `WISH` automatically.
- Never let title-only similarity authorize mutation.
- Require a complete local history baseline before a confirmed write.
- Resolve historical subject IDs to full Edition metadata before same-Work decisions.
- Fail closed when a shortlisted historical candidate cannot be resolved.
- Fail closed on unknown provider states.
- Preserve the stronger known state when local snapshot and current provider state disagree.
- A real write still requires explicit confirmation and post-write verification.
