# Resolver v3 live validation — first-volume title relation

Date: 2026-08-20

Branch: `agent/weread-shelf-baseline`

## Live problem

A Douban active-reading entry for subject `2567698` (`三体`) initially resolved to bounded WeRead `NOT_FOUND` even though official WeRead search returned `三体1` as the second catalog candidate.

A direct read-only Edition comparison established the original failure mode:

```text
Douban Edition: 三体
Author: 刘慈欣
Publisher: 重庆出版社
Publication: 2008-01
ISBN: 9787536692930

WeRead Edition: 三体1
Author: 刘慈欣
Publisher: 重庆出版社
Publication: 2022-04-01
ISBN: 9787229166922
WeRead bookId: 178677

old resolver:
Match: ambiguous
Same Work: False
work-title similarity: 0.80
author overlap: 1.00
```

The global same-Work title threshold remains `0.88`; it was not lowered.

## Narrow resolver change

Resolver v3 adds a confirmation-only base-title ↔ first-volume relation for titles that are exactly the other title plus one of these suffixes:

```text
1
第一部
第1部
```

Author overlap is still required. The relation never creates an exact Edition and never becomes safe for automatic state-changing application.

Negative regression cases explicitly keep these separate:

```text
三体 ↔ 三体2·黑暗森林
三体 ↔ 三体全集（全三册）
```

## Direct live result after v3

The same read-only comparison then returned:

```text
Match: alternative_edition
Same Work: True
Exact Edition: False
Requires confirmation: True
Safe to auto align: False

Reasons:
ISBN differs
work-title similarity 0.80
first-volume title variant
author overlap 1.00
publisher matches
publication year differs

Edition differences:
ISBN differs
publication year differs
```

This is the intended Work/Edition distinction: `三体1` is accepted as a same-Work candidate while remaining a different concrete Edition that requires review.

## End-to-end live batch result

After the full local suite passed with:

```text
Ran 225 tests in 0.471s
OK
```

Douban → WeRead policy v3 was run against the unchanged complete local baselines. The `三体` item changed from bounded `not_found` under the previous resolver to:

```text
Douban subject: 2567698
Douban state: do
Catalog search window: <= 10
WeRead catalog status: available_alternative
Resolution: alternative_edition
Selected WeRead bookId: 178677
Selected Edition: 三体1
Current shelf membership: no
Outcome: available_alternative
User plan: review_edition
User action required: yes
```

No platform mutation was performed.

## Safety conclusion

This live case validates the full path:

```text
official WeRead search
→ full /book/info Edition metadata
→ resolver same-Work / alternative-Edition decision
→ current shelf membership lookup by bookId
→ user-facing review_edition plan
→ baseline + policy scoped checkpoint
```

The first-volume relation is deliberately confirmation-only and does not relax the global title threshold for unrelated books.
