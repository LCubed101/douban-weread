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

## Live provider status

The next planned validation was a read-only `白夜行` inspection using the complete local history baseline. Before any authenticated write, a public title search was attempted with `DOUBAN_COOKIE` unset and returned HTTP 403. A single exact subject-detail fetch from the same local runtime also returned HTTP 403 after a redirect.

Because both public search and exact subject detail were rejected, live history-aware reconciliation validation is currently **blocked by provider access**, not by a failing regression test.

The failure is documented as `docs/pitfalls/PIT-023-public-read-403-after-history-sync.md`.

Do not repeatedly retry or attempt to bypass provider anti-abuse controls. Resume later with one low-volume read-only probe. Until then, the already-synced local history baseline remains usable for local-only lookup, but a live `inspect` cannot complete because Edition metadata and current provider state reads still require Douban access.
