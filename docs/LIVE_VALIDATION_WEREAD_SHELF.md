# WeRead shelf live validation

Date: 2026-08-20

Branch: `agent/weread-shelf-baseline`

## Local regression before live shelf sync

```text
Ran 150 tests in 0.078s
OK
```

The installed CLI exposed:

```text
douban-weread weread shelf {sync,status,lookup}
```

## First live `/shelf/sync`

A user-bound `WEREAD_API_KEY` was supplied only through the local shell environment and removed immediately after the request. No key value was printed or committed.

The first read-only account shelf sync completed successfully:

```text
WeRead shelf baseline: complete
Visible shelf entries: 303
Electronic books: 302
Albums / audio books: 0
Article collection: yes
Last full sync: 2026-08-20T11:39:53.739860+00:00
Database: /Users/ludao/.local/share/douban-weread/history.sqlite3
```

The visible count matches the official shelf accounting rule:

```text
302 electronic books + 0 albums + 1 article-collection entry = 303 visible entries
```

The local `status` command reproduced the same result without network access.

## Catalog availability is separate from shelf membership

The exact WeRead Edition of `白夜行` had already been live-validated through catalog search and `/book/info`:

```text
bookId: 230107
ISBN: 9787544291163
resolver: EXACT_EDITION
catalog status: AVAILABLE_EXACT
```

But the local shelf lookup returned:

```text
No local WeRead shelf candidates found for "白夜行".
```

Therefore the project must model two independent facts:

```text
catalog availability != personal shelf membership
```

An Edition may be available in WeRead without already being on the user's shelf.

## First local two-sided preview

After the first local-only cross-baseline preview was added:

```text
Ran 155 tests in 0.108s
OK
```

Observed local preview:

```text
Douban history entries: 1748
WeRead electronic shelf books: 302
Shared exact normalized title keys: 133
Douban entries with exact-title shelf candidate: 137
WeRead books with exact-title Douban candidate: 133
Douban-only by exact title: 1611
WeRead-only by exact title: 169
Ambiguous shared title keys: 4
Possible finished/state conflicts: 0
```

This preview is title-only and does not establish Work or Edition identity.

The result also exposed an important semantic bug in the first report: `Douban-only` included historical `collect` / READ records. A book that was read in the past is not expected to remain on the current WeRead shelf, so such an absence is not a synchronization gap.

The preview semantics were therefore revised before any automatic synchronization logic was added:

```text
Douban WISH / READING
→ current reading intent; relevant to current shelf alignment

Douban READ
→ historical evidence; absence from the current shelf is normal

WeRead shelf presence
→ not equivalent to Douban WISH

WeRead finishReading / later /book/getprogress
→ reading-state evidence
```

The revised active-intent preview is implemented and awaits the next local regression + real local preview run.

## Safety boundary

- No WeRead mutation was performed.
- No Douban mutation was performed.
- Exact normalized title overlap is shortlist evidence only.
- Full `/book/info` and `/book/getprogress` should be fetched lazily only for candidates that require Work/Edition or reading-state verification.
- Do not fan out detail requests across the full 302-book shelf merely to build a baseline.
