# Reconciliation policy v3

Date: 2026-08-20

Branch: `agent/weread-shelf-baseline`

## Live evidence that triggered v3

A Douban active-reading entry for `三体` (subject `2567698`) was searched against the official WeRead catalog. The first ten lightweight search candidates already contained:

```text
三体全集（全三册）
三体1
三体2·黑暗森林
三体3·死神永生
...
```

Therefore pagination was not the cause of the bounded `NOT_FOUND` result.

An exact cross-platform comparison of Douban `三体` and WeRead `三体1` produced:

```text
Douban title: 三体
Douban author: 刘慈欣
Douban publisher: 重庆出版社
Douban year: 2008
Douban ISBN: 9787536692930

WeRead title: 三体1
WeRead author: 刘慈欣
WeRead publisher: 重庆出版社
WeRead year: 2022
WeRead ISBN: 9787229166922

old resolver:
work-title similarity: 0.80
author overlap: 1.00
Same Work: false
Match: ambiguous
```

The global resolver required title similarity >= 0.88 plus author overlap, so the trailing first-volume marker caused a false negative even though the catalog candidate was already ranked second.

## Resolver v3 rule

The global title threshold remains unchanged.

A narrow additional relation is recognized when one normalized title is exactly the other normalized title plus a first-volume suffix:

```text
1
第一部
第1部
```

The relation is symmetric for cross-platform comparison, but it still requires non-zero author overlap.

Examples:

```text
三体 ↔ 三体1
same Work candidate: yes
exact Edition: no
requires confirmation: yes
safe to auto apply: no

三体 ↔ 三体2·黑暗森林
same Work through this rule: no

三体 ↔ 三体全集（全三册）
same Work through this rule: no
```

The rule does not strip arbitrary numbers, sequel markers, subtitles, boxed-set markers, or volume labels globally. It does not lower the normal 0.88 title threshold.

## Edition semantics

The live `三体` / `三体1` pair has different ISBN and publication year. Therefore even after Work identity is recognized it remains an `ALTERNATIVE_EDITION`, not an exact Edition.

Because the Work relation depends on the narrow first-volume title rule, the result always sets:

```text
requires_confirmation = true
safe_to_auto_apply = false
```

For Douban → WeRead, the expected user-facing plan is therefore `review_edition`, not automatic shelf addition.

## Checkpoint generation

The resolver is shared by both reconciliation directions, so v3 changes matching semantics on both sides.

Direction-specific checkpoint policy versions advance to:

```text
WeRead → Douban: v2
Douban → WeRead: v3
```

Old rows remain local but do not suppress verification under the new policy version. No platform baseline refresh is required to re-run an item after this algorithm change.

## Pagination

Official WeRead search pagination remains a valid future improvement because `/store/search` exposes `hasMore` and `searchIdx`/`maxIdx`. It is not required to fix this particular live false negative because the relevant `三体1` candidate was already present in the first ten results.

## Safety boundary

- Resolver v3 is read-only.
- Exact ISBN remains the only resolver evidence considered safe for automatic Edition identity.
- The first-volume title relation never produces `EXACT_EDITION` by itself.
- The relation never makes a state-changing action safe to auto-apply.
- Boxed sets and later sequel volumes are explicitly covered by negative regression tests.
