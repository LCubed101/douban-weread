# User-facing reconciliation plan live validation

Date: 2026-08-20

Branch: `agent/weread-shelf-baseline`

## Regression baseline

After the user-facing reconciliation plan layer was added, the complete local suite passed:

```text
Ran 213 tests in 2.886s
OK
```

The plan layer is presentation semantics over already verified reconciliation evidence. It does not perform provider requests, database writes beyond existing checkpoints, or platform mutations.

## Live Douban → WeRead plan cases

A live read-only batch resumed the same baseline generation:

```text
Direction: douban-to-weread
Candidate queue: 1437
Already checkpointed in this generation: 2
Pending before batch: 1435
Batch size: 2
```

### 10人以下小团队管理手册

Observed evidence:

```text
Douban subject: 27019726
Douban state: wish
WeRead catalog status: available_exact
Resolution: exact_match
Selected WeRead bookId: 926226
Selected Edition: 10人以下小团队管理手册
Current shelf membership: no
```

User-facing plan:

```text
User plan: add_to_weread_shelf_exact
Summary: An exact WeRead Edition is available but is not on the current shelf.
User action required: yes
```

### 10种洞察

Observed evidence:

```text
Douban subject: 36414591
Douban state: wish
WeRead catalog status: available_exact
Resolution: exact_match
Selected WeRead bookId: 3300060935
Selected Edition: 10种洞察：探索理所当然之外的世界
Current shelf membership: no
```

User-facing plan:

```text
User plan: add_to_weread_shelf_exact
Summary: An exact WeRead Edition is available but is not on the current shelf.
User action required: yes
```

The second case is another title-difference example: the WeRead title includes a subtitle, while full Edition resolution still establishes an exact Edition. User-facing semantics therefore depend on verified Edition identity plus current shelf membership, not exact title equality.

## Product ordering refinement

Sequential alphabetical processing repeatedly surfaced low-urgency WISH items with the same `add_to_weread_shelf_exact` plan. The background ordering was therefore refined after this live run:

```text
Douban → WeRead
READING / do first
then WISH

WeRead → Douban
non-private finishReading=true first
then non-private unfinished
then private/import-like items
```

This ordering is intended to surface current reading-state conflicts and completed-reading evidence earlier. It does not change identity rules, safety policy, checkpoint generation, or the five-item hard batch cap.

Regression and live validation of the refined ordering are still pending.

## Safety boundary

- All recorded runs are read-only.
- No WeRead shelf mutation was performed.
- No Douban state mutation was performed.
- User-facing plan values are derived from resolver-confirmed evidence and do not authorize writes.
- Exact-title overlap remains shortlist evidence only.
- `available_exact` remains separate from current shelf membership.
