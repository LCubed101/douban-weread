# WeRead shelf baseline

Status: **official `/shelf/sync` provider and local SQLite baseline implemented on `agent/weread-shelf-baseline`; local regression pending.**

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

The implementation persists the WeRead baseline into the same configurable SQLite database used by the project (`DOUBAN_WEREAD_DB` when set, otherwise `~/.local/share/douban-weread/history.sqlite3`) using separate `weread_shelf_*` tables.

Electronic-book rows preserve lightweight shelf metadata:

```text
book_id
title/title_key
author
deep_link
category
read_update_time
finish_reading
update_time
is_top
secret
last_seen_at
```

Baseline metadata preserves:

```text
last_full_sync_at
book_count
album_count
has_mp
archive metadata
baseline_complete
schema/version
```

A full replacement is atomic. Provider/parser failure happens before replacement, and storage validation also happens before deleting the previous baseline.

## Implemented provider boundary

`WeReadClient.sync_shelf()` calls exactly:

```json
{
  "api_name": "/shelf/sync",
  "skill_version": "1.0.4"
}
```

It normalizes `books[]` into `WeReadShelfBook`, preserves archive membership, counts `albums[]`, and records whether `mp` is present. The computed visible shelf count follows the official contract:

```text
books.length + albums.length + (mp present ? 1 : 0)
```

Malformed book entries, duplicate `bookId`s, invalid arrays, and provider errors fail closed rather than producing a partial baseline.

## Implemented local index

`WeReadShelfIndex` now supports:

```text
replace_full(snapshot)
status()
get(book_id)
find_title_candidates(title)
```

Local title lookup is a shortlist only. Work/Edition identity still requires the existing resolver plus lazy `/book/info` requests for the small set of candidates that matter.

The implementation deliberately does **not** call `/book/info` once for every shelf item during full sync.

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

1. `/shelf/sync` provider support — implemented.
2. Local shelf SQLite baseline — implemented.
3. Status / local lookup CLI — next after regression passes.
4. Reconciliation report — after the baseline is live-validated.
5. No automatic writes.

Automatic application can be considered later only for separately defined safe cases and explicit user settings/confirmation.

## Regression coverage added

Eight tests were added for the first shelf slice:

- exact zero-parameter `/shelf/sync` request construction;
- `books[]` normalization;
- `albums[]` + `mp` accounting without converting them into books;
- invalid/missing book metadata fail-closed behavior;
- duplicate `bookId` fail-closed behavior;
- atomic local baseline persistence and status counts;
- local title shortlist behavior;
- preservation of the previous complete baseline when replacement validation fails;
- safe uninitialized status.

The full suite still needs to be run locally before adding the shelf CLI or making the first live full-shelf request.

## Next implementation slice

After the local suite is green, add:

```bash
douban-weread weread shelf sync
douban-weread weread shelf status
douban-weread weread shelf lookup "白夜行"
```

Only after those commands are covered by tests should the first real `/shelf/sync` be run with the user's local API key.
