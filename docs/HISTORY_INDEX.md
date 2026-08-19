# Douban Reading History Index

Status: **implemented as a first baseline-sync layer; live validation required**.

## Goal

Avoid refetching a user's complete Douban reading history for every new book.

The intended flow is:

```text
first setup
→ full Douban WISH / READING / READ sync
→ local SQLite baseline

later captures
→ local lookup first
→ shortlist only relevant historical records
→ resolve full Edition metadata only when needed
→ Work/Edition reconciliation
```

The complete history is **not** sent to an LLM on each operation. The index is queried locally with normal Python/SQLite logic.

## Commands

### First full baseline

Requires a fresh user-owned `DOUBAN_COOKIE` in the current shell:

```bash
douban-weread history sync --full
```

The provider reads the user's three Douban Book lists:

- `wish` → Want-to-Read
- `do` → Reading
- `collect` → Read

The local database is replaced only after all three remote list fetches complete successfully. A failed/blocked/expired-session fetch must not destroy the previous good baseline.

### Local status

No network or Cookie required:

```bash
douban-weread history status
```

Example shape:

```text
History baseline: complete
Total: 1234
Want-to-Read: 456
Reading: 3
Read: 775
Last full sync: 2026-08-19T08:00:00+00:00
Database: ~/.local/share/douban-weread/history.sqlite3
```

### Local title shortlist

No network or Cookie required:

```bash
douban-weread history lookup "荷马史诗：奥德赛"
```

The result is only a **candidate shortlist**. Title similarity never authorizes a mutation and never proves same Work/Edition identity.

## Why the baseline is lightweight

A user may have hundreds or thousands of historical records. Fetching every subject detail page during the initial sync would multiply network requests and make setup unnecessarily slow.

Therefore the first baseline stores only what is needed to discover historical candidates cheaply:

```text
subject_id
title
state
normalized local title key
last_seen_at
```

When a future `inspect` sees a new target Edition, the intended next integration step is:

1. query the local history index;
2. shortlist a small number of similar historical titles;
3. fetch full Douban Edition metadata only for those subject IDs;
4. run the existing Work/Edition resolver;
5. combine verified historical states with the live target state;
6. reconcile before any mutation.

This keeps the expensive/network-sensitive work proportional to the number of relevant candidates rather than the user's entire library.

## Storage

Default database path:

```text
~/.local/share/douban-weread/history.sqlite3
```

Override with:

```bash
export DOUBAN_WEREAD_DB=/custom/path/history.sqlite3
```

The database is local and must not contain the Douban Cookie. Cookie/session data remains shell-local and is never persisted by this index.

## Sync policy

### Implemented now

```text
history sync --full
```

This establishes a trusted local baseline.

### Planned after live validation

Normal operation should be:

```text
project-owned verified mutation
→ update the affected local row directly

manual changes made in Douban app/web
→ periodic or user-requested refresh

ambiguous/stale high-risk case
→ targeted online verification
```

A full history refetch should not be required for every capture.

## Completeness semantics

A successful full sync means the three Douban list pages were traversed to their observed end and committed as one local snapshot.

It does **not** mean:

- Douban's unofficial web HTML is permanently stable;
- title-only local matching is a Work identity proof;
- WeRead state has been synchronized;
- a future manual Douban change is automatically known before the next refresh.

Those boundaries must stay explicit in UI/CLI output.

## Token and latency model

The history baseline itself uses no LLM token budget.

Typical later lookup:

```text
SQLite: thousands of local rows
→ Python title shortlist: tens of candidates at most
→ Edition resolver: only shortlisted candidates
→ AI: only if genuinely ambiguous metadata/recognition needs it
```

This is intentionally local-first and deterministic.

## Safety

- Read-only remote sync.
- No Cookie persisted to SQLite.
- No title-only write decisions.
- Previous good baseline survives a failed remote sync.
- Captcha/anti-abuse pages fail closed.
- No captcha bypass.
- `inspect`/`wish` are not connected to this new baseline until the provider has been live-validated.
