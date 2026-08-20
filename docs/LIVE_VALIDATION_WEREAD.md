# WeRead live validation

Date: 2026-08-20

Branch: `agent/weread-search-status`

## Local regression baseline

After the read-only WeRead search, `/book/info`, and exact cross-platform compare CLI were added, the full local suite passed:

```text
Ran 129 tests in 0.108s
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

The ISBNs are identical. Under the resolver contract, an exact normalized ISBN match is sufficient for exact Edition identity.

## Live Douban → WeRead resolver comparison

The comparison was then executed through the project itself rather than by manual inspection:

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

The command fetched the exact Douban subject and exact WeRead `bookId`, normalized both records, and ran the existing provider-agnostic resolver. This validates the cross-platform Edition identity path end to end for the test pair:

```text
Douban subject 27112607
→ 白夜行 / ISBN 9787544291163

WeRead bookId 230107
→ 白夜行 / ISBN 9787544291163

compare_editions(...)
→ EXACT_EDITION
→ same_work=True
→ exact_edition=True
→ safe_to_auto_apply=True
```

No state-changing operation was performed on either platform.

## Availability boundary

The live search returned `Sold out: no` for WeRead `bookId=230107`. Combined with resolver-confirmed exact Edition identity, this is enough for the first catalog-level `AVAILABLE_EXACT` mapping used by the project.

The availability label is intentionally scoped: `soldout=0` is official WeRead catalog evidence that the candidate is not reported sold out, but it does not guarantee account-specific purchase/subscription entitlement in every user context.

A same-Work candidate reported as `soldout=1` must not be mislabeled `NOT_FOUND`; the alignment layer therefore preserves a separate `UNAVAILABLE` state. Likewise, `NOT_FOUND` remains bounded by the configured search window rather than claiming an exhaustive absence from the entire WeRead catalog.

## Next validation

The next project-level path is:

```text
exact Douban Edition
→ bounded official WeRead search
→ /book/info for candidates
→ resolver same-Work / exact-Edition evidence
→ ReadingIntent
→ AVAILABLE_EXACT / AVAILABLE_ALTERNATIVE / UNAVAILABLE / bounded NOT_FOUND
```

This path is implemented next and should be locally regression-tested before one low-volume live `weread resolve` validation is recorded.
