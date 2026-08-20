# WeRead live validation

Date: 2026-08-20

Branch: `agent/weread-search-status`

## Local regression baseline

After the read-only WeRead search and `/book/info` CLI were added, the full local suite passed:

```text
Ran 126 tests in 0.068s
OK
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

The ISBNs are identical. Under the current resolver contract, an exact normalized ISBN match is sufficient to classify the records as `EXACT_EDITION`, `same_work=True`, `exact_edition=True`, `requires_confirmation=False`, and `safe_to_auto_apply=True`.

This is strong cross-platform Edition identity evidence, but the project should still execute the resolver through a repeatable CLI path before declaring the complete Douban → WeRead alignment workflow live-validated end to end.

## Availability boundary

The live search also returned `Sold out: no` for WeRead `bookId=230107`. That is useful catalog evidence, but the project does not yet treat `soldout=0` alone as proof that the book is readable in every user/account context.

The next step is therefore:

```text
Douban subject 27112607
+ WeRead bookId 230107
→ fetch both live Editions
→ compare_editions(...)
→ verify EXACT_EDITION in the real CLI path
```

Only after that should `AVAILABLE_EXACT` be wired into the cross-platform `ReadingIntent` flow.
