# History-aware reconciliation validation

This file records validation for the stacked history-aware reconciliation layer on top of the already live-validated Reading History Index foundation.

## 2026-08-19 — Local regression validation

Branch:

```text
agent/history-aware-reconciliation
```

The complete test suite passed locally:

```text
Ran 103 tests in 0.240s
OK
```

The run includes regression coverage for:

- a historical same-Work Edition absent from live title search;
- incomplete history baseline failing closed;
- a historical `READ` surviving a weaker live `NONE`;
- a newer live `READ` overriding an older local `WISH`;
- CLI `inspect` refusing an incomplete history baseline;
- a verified project-owned `wish` updating the local history index only after successful remote write verification.

This validates the code path only. A real read-only provider run is still required to prove that the local 1747-row baseline contributes a same-Work historical record to live `inspect` behavior.

## Next live validation

Use a target Edition whose same Work is already present in the local history baseline, preferably under a different Douban subject ID. Run `inspect` only; do not perform a real `wish` write.

Expected path:

```text
target Edition
→ complete local history shortlist
→ lazy metadata fetch for shortlisted subject IDs
→ resolver confirms same Work
→ historical READ / READING / WISH enters reconciliation
→ write-safety decision fails closed or asks for review as appropriate
```

No real state-changing Douban write has been performed in this layer.
