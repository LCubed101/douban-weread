# WeRead shelf baseline

Status: **official `/shelf/sync`, local SQLite baseline, shelf CLI, and local two-sided reconciliation preview implemented on `agent/weread-shelf-baseline`; preview regression pending.**

Date: 2026-08-20

## Product goal

Treat WeRead shelf state as a second local baseline, parallel to the existing Douban reading-history index.

The account-level flow is:

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

## Implemented local index and CLI

`WeReadShelfIndex` supports:

```text
replace_full(snapshot)
status()
get(book_id)
all_books()
find_title_candidates(title)
```

`ReadingHistoryIndex` also exposes `all_entries()` so the two complete local baselines can be compared without network traffic.

The shelf CLI is live-validated:

```bash
douban-weread weread shelf sync
douban-weread weread shelf status
douban-weread weread shelf lookup "白夜行"
```

The first real shelf sync produced:

```text
Visible shelf entries: 303
Electronic books: 302
Albums / audio books: 0
Article collection: yes
```

A local lookup for `白夜行` returned no shelf candidate even though the catalog-level flow had already proven an exact available WeRead Edition. This establishes that **catalog availability and shelf membership are separate states**.

The implementation deliberately does **not** call `/book/info` once for every shelf item during full sync.

## Local two-sided reconciliation preview

The first local reconciliation command is:

```bash
douban-weread weread shelf preview --limit 10
```

It uses the complete local Douban history and WeRead electronic-book shelf only; it makes no provider request and performs no mutation.

The preview compares exact normalized title keys and reports:

```text
Douban history total
WeRead electronic shelf total
shared exact normalized title keys
Douban entries with an exact-title shelf candidate
WeRead books with an exact-title Douban candidate
Douban-only by exact title
WeRead-only by exact title
ambiguous shared title keys
possible finished/state conflicts
```

Possible state conflicts are deliberately restricted to singleton exact-title groups where WeRead reports `finishReading=1` while Douban is `wish` or `do`.

**Important:** exact normalized title overlap is only shortlist evidence. It is not same-Work or same-Edition evidence and never authorizes a write. Duplicate-title groups remain ambiguous. Final reconciliation requires lazy metadata verification through the existing resolver.

## Target reconciliation semantics

The eventual verified reconciliation report should distinguish at least:

```text
ALIGNED
DOUBAN_ONLY
WEREAD_ONLY
ALTERNATIVE_EDITION
READING_STATE_CONFLICT
AMBIGUOUS
```

Examples:

- Douban WISH + resolver-confirmed same exact Edition in WeRead shelf → `ALIGNED`.
- Douban WISH + no verified same-Work shelf entry → `DOUBAN_ONLY`.
- WeRead shelf same Work + no verified Douban state → `WEREAD_ONLY`.
- Same Work but different Edition → `ALTERNATIVE_EDITION`.
- WeRead `finishReading=1` while Douban says WISH/READING → state conflict; do not silently downgrade or overwrite.
- Weak/title-only evidence → `AMBIGUOUS` until verified.

A WeRead shelf item is not automatically equivalent to Douban WISH. Shelf presence and reading progress are separate signals.

## Safety boundary

The shelf milestone remains read-only:

1. `/shelf/sync` provider support — implemented and live-validated.
2. Local shelf SQLite baseline — implemented and live-validated.
3. Status / local lookup CLI — implemented and live-validated.
4. Local exact-title reconciliation preview — implemented; regression pending.
5. Lazy Work/Edition verification for preview shortlists — next.
6. No automatic writes.

Automatic application can be considered later only for separately defined safe cases and explicit user settings/confirmation.

## Regression history

The provider/storage plus shelf CLI baseline reached:

```text
Ran 150 tests in 0.078s
OK
```

Five additional tests now cover the local two-sided preview:

- normalized exact-title overlap and one-sided counts;
- singleton finished/state conflict detection;
- duplicate-title ambiguity fail-closed behavior;
- preview CLI over two complete local baselines without network access;
- refusal to preview when either baseline is incomplete.

The expected full local suite after this slice is 155 tests.

## Next validation

Run the local suite, then execute the local-only preview against the real synchronized baselines:

```bash
douban-weread weread shelf preview --limit 10
```

The preview output should be treated as a triage map, not a final synchronization decision. The next engineering slice will lazily verify selected shared/one-sided candidates with full Douban and WeRead Edition metadata before assigning `ALIGNED`, `DOUBAN_ONLY`, `WEREAD_ONLY`, `ALTERNATIVE_EDITION`, or a state conflict.
