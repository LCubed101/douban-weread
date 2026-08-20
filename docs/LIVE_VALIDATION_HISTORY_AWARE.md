# History-aware reconciliation validation

## 2026-08-19 — local regression suite

Branch: `agent/history-aware-reconciliation`

The complete suite passed locally before live provider validation:

```text
Ran 103 tests in 0.240s
OK
```

The run includes coverage for:

- historical same-Work editions missing from live title search;
- incomplete history baseline fail-closed behavior;
- historical `READ` surviving a weaker live `NONE`;
- newer live `READ` overriding an older local `WISH`;
- CLI `inspect` refusing an incomplete baseline;
- verified project-owned `wish` updating the local index only after remote write verification.

No state-changing Douban write was performed.

## 2026-08-19 — temporary provider 403 during planned live validation

The first planned read-only `白夜行` validation was interrupted by provider access failures. With `DOUBAN_COOKIE` unset, both public title search and a single exact subject-detail fetch returned HTTP 403 from the same local runtime.

Because exact subject detail was also rejected, this was broader than a `subject_search`-only failure. The event is documented as `docs/pitfalls/PIT-023-public-read-403-after-history-sync.md`.

The validation was stopped rather than retried in a loop. No bypass or anti-bot evasion was attempted.

## 2026-08-20 — provider recovery and live history-aware reconciliation

After waiting overnight, one low-volume exact-subject probe was run with `DOUBAN_COOKIE` unset and no provider-code change:

```text
白夜行 南海出版公司 2017-07 27112607
```

This confirmed that exact public subject access had recovered. PIT-023 therefore remains classified as a temporary provider-access event with an unconfirmed trigger rather than a permanent parser or endpoint failure.

A second low-volume read-only comparison then resolved the target Edition and one historical Edition:

```text
TARGET: 白夜行 ['刘姿君'] 南海出版公司 2017-07 9787544291163
HISTORY: 白夜行 ['刘姿君'] 南海出版公司 2013-01 9787544258609
same_work: True
kind: alternative_edition
requires_confirmation: False
differences: ['ISBN differs', 'publication year differs'] []
```

This validates that subject `27112607` and historical subject `10554308` are the same Work but different Editions.

The authenticated live reconciliation test then used a deliberately tiny live-search bound:

```bash
douban-weread inspect --subject 27112607 --limit 1
```

Observed same-Work states:

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
Reason: Another edition of the same Work is already marked read. Treat the new target as a possible reread and ask before changing state.
```

The target itself was currently unmarked, while two older same-Work Editions were present in the complete local history baseline as `READ`. With the live title-search limit intentionally reduced to `1`, those historical records were still discovered from SQLite, lazily resolved to full Edition metadata, verified as the same Work, and included in reconciliation.

This live run validates the intended forgotten-history safety path:

```text
exact target Edition
→ bounded live discovery
+ complete local history shortlist
→ lazy historical Edition resolution
→ same-Work verification
→ historical READ detection
→ ASK_REREAD
→ write blocked
```

The Cookie was removed from the shell after the read-only test. No state-changing Douban write was performed.

## Status

History-aware reconciliation is now live-validated for the core case it was designed to solve: a currently unmarked target Edition must not be considered safe to mark Want-to-Read when another Edition of the same Work already exists in the user's historical `READ` state.

The next separate validation, if performed, should be a deliberately selected first real `wish` on a target that history-aware reconciliation classifies as safe. That mutation still requires explicit user confirmation and post-write read-back verification.
