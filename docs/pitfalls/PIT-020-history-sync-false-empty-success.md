## PIT-020 — History sync can falsely succeed with an empty baseline after HTML drift

### Symptom

A live authenticated run of:

```bash
douban-weread history sync --full
```

reported success and stored a `complete` baseline, but every count was zero:

```text
History baseline: complete
Total: 0
Want-to-Read: 0
Reading: 0
Read: 0
```

The account was authenticated successfully immediately before the sync, so this was not an auth failure.

### Environment

- macOS
- Python 3.10
- `agent/douban-reading-history-index`
- live Douban Book user-history pages
- 2026-08-19

### Diagnosis

The first history parser fixture used an older/alternate `div.item` shape. Current Douban Book user-list pages use `li.subject-item` for book entries.

Because the parser found neither entries nor a pagination link, it interpreted the first page as a legitimately empty list and returned success. The SQLite layer then persisted the zero-row result as a complete baseline.

### Root cause

Two safety gaps combined:

1. the HTML parser did not support the current `li.subject-item` structure;
2. the sync path had no completeness invariant comparing parsed entries with the count declared by the page.

This is a classic parser-drift failure mode: an HTML integration can return HTTP 200 and still be semantically unusable.

### Resolution

- Support `li.subject-item` as the primary current Book-list container.
- Keep `div.item` only as a compatibility fallback.
- Parse the list's declared total from the page title/range when available.
- At the end of pagination, fail closed when parsed count differs from the declared total.
- If a page yields zero entries and exposes no verifiable zero total, fail closed instead of assuming the list is empty.
- Add a baseline format version. Baselines created before this parser/completeness fix are automatically treated as incomplete until a new full sync succeeds.

### Prevention / test

Regression coverage must include:

- current `li.subject-item > div.info > h2 > a` markup;
- a declared non-empty page that parses zero entries;
- a declared total that differs from the parsed total;
- a truly empty list with declared total zero;
- migration of the pre-fix `complete + 0 rows` baseline to an incomplete/untrusted state.

General rule:

> HTTP success is not history-sync success. A full baseline is complete only when page structure is recognized and the parsed record count is internally consistent with provider-visible pagination/count metadata.
