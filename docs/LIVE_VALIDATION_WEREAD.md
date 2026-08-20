# WeRead live validation

Date: 2026-08-20

Branch: `agent/weread-shelf-baseline`

## Local regression baseline

The single-book WeRead path passed 136 tests before shelf work. After `/shelf/sync`, local shelf storage, and the shelf CLI were added, the full local suite passed:

```text
Ran 150 tests in 0.078s
OK
```

The installed CLI smoke test also succeeded:

```text
usage: douban-weread weread shelf [-h] {sync,status,lookup} ...
```

## Live `/store/search`

A user-bound WeRead API key was supplied only through the local `WEREAD_API_KEY` environment variable. The key value was never printed, committed, or included in validation output, and was removed from the shell after each live request.

One low-volume read-only search was executed:

```bash
douban-weread weread search "白夜行" --limit 5
```

The first candidate was:

```text
1. 白夜行
   Author: 东野圭吾
   WeRead bookId: 230107
   Sold out: no
   Deep link: https://weread.qq.com/book-detail?type=1&v=65032c105382db65050e7aa
```

This validates the official `/store/search` path in the real runtime and confirms that the provider exposes title, author, `bookId`, `soldout`, and deep-link metadata correctly.

## Live `/book/info`

The first exact-title candidate was then resolved through the official read-only `/book/info` path:

```bash
douban-weread weread book --id 230107
```

Observed normalized metadata:

```text
白夜行
   Authors: 东野圭吾
   Translators: 刘姿君
   Publication: 南海出版公司 · 2017-07-21
   ISBN: 9787544291163
   WeRead bookId: 230107
   Deep link: https://weread.qq.com/book-detail?type=1&v=65032c105382db65050e7aa
```

The corresponding known Douban target Edition is subject `27112607`:

```text
白夜行
Authors: [日] 东野圭吾
Translators: 刘姿君
Publication: 南海出版公司 · 2017-07
ISBN: 9787544291163
```

The ISBNs are identical. Under the resolver contract, an exact normalized ISBN match is sufficient for exact Edition identity.

## Live Douban → WeRead resolver comparison

The comparison was executed through the project itself:

```bash
douban-weread weread compare --subject 27112607 --id 230107
```

Observed resolver evidence:

```text
Resolver result:
Match: exact_edition
Same Work: True
Exact Edition: True
Requires confirmation: False
Safe to auto align: True
Reasons: exact ISBN match
```

No state-changing operation was performed on either platform.

## Live Douban → WeRead `ReadingIntent` resolution

The full bounded search/alignment path was then executed:

```bash
douban-weread weread resolve --subject 27112607 --limit 5
```

Observed result:

```text
Cross-platform ReadingIntent:

Work: 白夜行
Douban subject: 27112607
WeRead status: available_exact
Resolution: exact_match
Examined WeRead Editions: 1

Selected WeRead Edition:
白夜行
   Authors: 东野圭吾
   Translators: 刘姿君
   Publication: 南海出版公司 · 2017-07-21
   ISBN: 9787544291163
   WeRead bookId: 230107
   Search sold out: no

Resolver evidence:
Match: exact_edition
Same Work: True
Exact Edition: True
Requires confirmation: False
Reasons: exact ISBN match
```

The project therefore completed the first real end-to-end catalog availability classification:

```text
exact Douban Edition
→ bounded official WeRead search
→ /book/info
→ resolver exact Edition evidence
→ ReadingIntent
→ AVAILABLE_EXACT
```

## Live `/shelf/sync` baseline

After the shelf CLI and local SQLite baseline passed 150 tests, one read-only official shelf sync was executed:

```bash
douban-weread weread shelf sync
```

Observed local baseline status:

```text
WeRead shelf baseline: complete
Visible shelf entries: 303
Electronic books: 302
Albums / audio books: 0
Article collection: yes
Last full sync: 2026-08-20T11:39:53.739860+00:00
Database: /Users/ludao/.local/share/douban-weread/history.sqlite3
```

This validates that `/shelf/sync` can establish a complete account-level WeRead baseline in one request and that the project preserves the official shelf accounting distinction between electronic books, albums/audio books, and the article-collection entry.

A subsequent local-only lookup returned:

```bash
douban-weread weread shelf lookup "白夜行"
```

```text
No local WeRead shelf candidates found for "白夜行".
```

This is an important semantic distinction: `白夜行` was proven `AVAILABLE_EXACT` in the WeRead catalog (`bookId=230107`), but it is not currently present in the user's synced shelf baseline. Therefore **catalog availability and shelf membership are separate states and must never be conflated**.

No state-changing operation was performed on either platform.

## Availability and shelf boundaries

- `AVAILABLE_EXACT` / `AVAILABLE_ALTERNATIVE` describe catalog-level availability after resolver verification.
- Shelf membership comes only from the user-bound `/shelf/sync` baseline.
- `soldout=0` does not imply “already on shelf.”
- “On shelf” does not automatically imply Douban `WISH`; reading progress/state must be considered separately.
- `albums[]` and the `mp` article-collection entry participate in shelf counts but do not enter Douban Book Work/Edition reconciliation.

## Next milestone: local two-sided reconciliation preview

The next step is deliberately local-only:

```text
complete Douban history baseline
+ complete WeRead shelf baseline
→ normalized-title cross-index
→ candidate overlap / one-sided presence / possible state conflicts
→ no writes
```

Title overlap is only a shortlist signal. It must not be promoted to same-Work or same-Edition evidence without lazy metadata verification through the existing resolver.
