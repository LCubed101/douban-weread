# WeRead shelf baseline

Status: **design established from official `/shelf/sync`; implementation starts on `agent/weread-shelf-baseline`.**

Date: 2026-08-20

## Product goal

Treat WeRead shelf state as a second local baseline, parallel to the existing Douban reading-history index.

The first account-level flow is:

```text
Douban reading-history baseline
        ↕
Work / Edition reconciliation
        ↕
WeRead shelf baseline
```

The system should automatically fetch and compare both sides after account connection, but must not silently mutate either platform merely because a difference exists.

## Official `/shelf/sync` contract

The official WeChatReading shelf skill documents a zero-parameter `/shelf/sync` request. User identity is derived from the local API key.

The response has three distinct shelf content classes:

```text
books[]   electronic/imported/public-account book entries
albums[]  audio-book / album entries
mp        article-collection directory entry
```

For this project's Douban book reconciliation, only `books[]` enters Work/Edition matching.

`albums[]` and `mp` remain part of shelf accounting and user-visible baseline statistics, but they must not be converted into Douban book candidates.

Important `books[]` fields:

```text
bookId
deepLink
title
author
cover
category
readUpdateTime
finishReading
updateTime
isTop
secret
```

The shelf response also contains `archive[].name` / `archive[].bookIds` for shelf collections.

## Local-first model

The first full shelf sync should persist a local SQLite baseline rather than calling `/shelf/sync` for every operation.

Suggested row model for electronic books:

```text
book_id
name/title
author
deep_link
cover_url
category
read_update_time
finish_reading
update_time
is_top
secret
raw_snapshot_version
last_seen_at
```

Baseline metadata should also preserve:

```text
last_full_sync_at
book_count
album_count
has_mp
archive metadata or snapshot
baseline_complete
schema/version
```

A full replacement should be atomic: if provider fetching/parsing fails, keep the previous complete local baseline rather than replacing it with a partial shelf.

## Reconciliation semantics

The first reconciliation report should distinguish at least:

```text
ALIGNED
DOUBAN_ONLY
WEREAD_ONLY
ALTERNATIVE_EDITION
READING_STATE_CONFLICT
AMBIGUOUS
```

Examples:

- Douban WISH + same exact Edition in WeRead shelf → `ALIGNED`.
- Douban WISH + no same-Work shelf entry → `DOUBAN_ONLY`.
- WeRead shelf same Work + no Douban state → `WEREAD_ONLY`.
- Same Work but different Edition → `ALTERNATIVE_EDITION`.
- WeRead `finishReading=1` while Douban says WISH/READING → state conflict; do not silently downgrade or overwrite.
- Weak title-only evidence → `AMBIGUOUS`.

A WeRead shelf item is not automatically equivalent to Douban WISH. Shelf presence and reading progress are separate signals.

## Safety boundary

The first shelf milestone is read-only:

1. `/shelf/sync` provider support.
2. Local shelf SQLite baseline.
3. Status / local lookup CLI.
4. Reconciliation report.
5. No automatic writes.

Automatic application can be considered later only for separately defined safe cases and explicit user settings/confirmation.

## First implementation slice

1. Add `WeReadClient.sync_shelf()` with injectable transport coverage.
2. Normalize `books[]`, while preserving `albums[]`, `mp`, and archives as baseline metadata.
3. Add a `WeReadShelfIndex` SQLite store with atomic full replacement.
4. Add read-only CLI commands:

```bash
douban-weread weread shelf sync
douban-weread weread shelf status
douban-weread weread shelf lookup "白夜行"
```

5. Run local tests before the first live shelf sync.

Do not call `/book/info` once per entire shelf during baseline sync. `/shelf/sync` already provides the lightweight fields needed for local indexing; full Edition metadata should be fetched lazily only for reconciliation candidates that actually need identity verification.
