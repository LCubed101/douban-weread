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

## Revised active-intent preview

After the preview semantics were corrected, the full local suite passed:

```text
Ran 157 tests in 0.090s
OK
```

Observed revised preview:

```text
Douban history entries: 1748
  Active intents (wish + reading): 1552
    Want-to-Read: 1512
    Reading: 40
  Read history (not expected on current shelf): 196

WeRead electronic shelf books: 302
  Shelf books marked finished: 15
  Shelf books with nonzero readUpdateTime: 302

Shared exact normalized title keys (all Douban states): 133
Shared title keys involving active Douban intent: 111
Active Douban entries with exact-title shelf candidate: 115
Active Douban-only by exact title: 1437
WeRead-only vs any Douban state by exact title: 169
WeRead shelf books overlapping Douban READ history by exact title: 22
Ambiguous shared title keys: 4
Possible finished/state conflicts: 0
```

This establishes the correct first-pass business scope:

```text
Douban WISH / READING
→ current reading intent; relevant to current shelf alignment

Douban READ
→ historical evidence; absence from the current shelf is normal

WeRead shelf presence
→ not equivalent to Douban WISH
```

The `1437` active Douban entries without an exact-title shelf candidate are not automatically sync failures. They still contain several unresolved classes: different title, different Edition, no WeRead shelf membership, or no WeRead catalog availability.

Likewise, the `169` WeRead-only exact-title misses are high-priority reconciliation candidates, not proof that Douban lacks the Work.

## Live `/book/getprogress`: `readUpdateTime` is not reading-state evidence

After official `/book/getprogress` support was added, the full local suite passed:

```text
Ran 163 tests in 0.092s
OK
```

A live read-only progress lookup was executed for a WeRead shelf-only title candidate:

```text
bookId: 37724838
Title: 一个无政府主义者的意外死亡
```

Observed official progress evidence:

```text
WeRead bookId: 37724838
Progress: 0%
Started: no
Coarse state: unread
Last reading update: 1633955344
Recorded reading time: 0 seconds
```

This is decisive evidence that `readUpdateTime` from the shelf/progress payload must not be interpreted as "the user has started reading". The book has a nonzero update timestamp while official progress is 0%, `isStartReading` is false, and recorded reading time is zero.

The project therefore uses `/book/getprogress` as the reading-state authority for lazy verification:

```text
progress = 0 and isStartReading = false
→ UNREAD

progress = 1..99, or started evidence
→ READING

progress = 100 and finishTime present
→ READ

inconsistent / unsupported combination
→ UNKNOWN / fail closed
```

`readUpdateTime` remains metadata only and is not a state-transition signal.

## State synchronization policy boundary

Cross-platform state recommendation is now separated from identity resolution:

```text
Work/Edition resolver
        ↓
verified Work identity
        ↓
/book/getprogress
        ↓
UNREAD / READING / READ / UNKNOWN
        ↓
conservative Douban state recommendation
```

The first policy is intentionally suggestion-only:

- WeRead UNREAD + Douban NONE → suggest WISH, but do not auto-apply.
- WeRead READING + Douban NONE/WISH → suggest READING, but do not auto-apply.
- WeRead READ + Douban NONE/WISH/READING → suggest READ, but do not auto-apply.
- Douban READ + WeRead READING → possible reread; ask rather than downgrade READ.
- Unknown identity or state → fail closed.
- Same Work but non-exact Edition can support a Work-level suggestion, but Edition choice must be reviewed before a concrete Edition write.

No cross-platform state-changing action is auto-applied in v0.2.

## First live lazy shelf verification

After the single-book lazy verification path was added, the full local suite passed:

```text
Ran 180 tests in 0.273s
OK
```

The installed shelf CLI exposed:

```text
douban-weread weread shelf {sync,status,lookup,preview,verify}
```

The same WeRead shelf book used for progress validation was then verified end-to-end:

```text
WeRead bookId: 37724838
Title: 一个无政府主义者的意外死亡
Progress: 0%
Started: no
Verified WeRead state: unread
```

Bounded Douban verification found two resolver-confirmed same-Work candidates. The best candidate was:

```text
Douban subject: 26649304
ISBN: 9787532770892
Match: exact_edition
Exact Edition: True
Local history state: none
Reason: exact ISBN match
```

The strongest verified Douban Work state in the complete local history baseline was `none`, so the suggestion-only policy returned:

```text
Action: suggest_wish
Suggested Douban state: wish
Safe to auto apply: False
Requires user decision: True
```

This is the first live proof of the full WeRead-shelf-to-Douban recommendation chain:

```text
personal WeRead shelf membership
→ full WeRead Edition metadata
→ user-specific /book/getprogress
→ bounded Douban discovery + local complete history shortlist
→ Work/Edition resolver
→ conservative cross-platform state recommendation
```

The live command was accidentally repeated once with the same inputs and returned the same result. Both runs were read-only and produced no mutation.

The bounded verifier explicitly does not claim that public Douban search is exhaustive. Local history candidates are added before state reconciliation so an older same-Work Edition can still prevent an unsafe downgrade or duplicate suggestion.

## Safety boundary

- No WeRead mutation was performed.
- No Douban mutation was performed in this shelf milestone.
- Exact normalized title overlap is shortlist evidence only.
- Full `/book/info` and `/book/getprogress` are fetched lazily only for candidates that require Work/Edition or reading-state verification.
- Single-book verification is bounded by default to at most 3 public Douban search candidates and 5 local history shortlist candidates.
- Do not fan out detail requests across the full 302-book shelf merely to build a baseline.
- Cross-platform state changes remain suggestion-only in v0.2.
