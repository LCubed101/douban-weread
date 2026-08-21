# Reconciliation UI v1

This document defines the first user-facing reconciliation screens above the
local-only product models. It is a presentation contract, not a provider or
mutation API.

## Principles

- Pending/unverified items are never described as unavailable or not found.
- `no_user_action` is broader than `aligned`; keeping stronger Douban history is
  not the same thing as exact alignment.
- Edition/identity review must happen before any suggested cross-platform write.
- `OPEN_WEREAD` means open the resolved WeRead destination. It does not mean the
  application has an established official API for adding the book to shelf.
- No screen action implicitly authorizes a Douban or WeRead write.
- While reconciliation is partial, all classified counts are explicitly based
  only on verified evidence.

## Screen 1 — Home

### Purpose

Answer three questions quickly:

1. Is comparison still running?
2. How much has been verified?
3. Is there anything I need to handle?

### Current real-data example

```text
豆瓣 × 微信读书

正在比较你的阅读记录
14 / 1606 · <1%
[progress bar]

1592 本还在比较中

待你处理     10
已对齐        2
无需处理      4

[查看待处理 10]
```

### Copy rules

When `phase == reconciling`:

- Title: `正在比较你的阅读记录`
- Coverage: `{verified_total} / {candidate_total} · {progress_label}`
- Pending: `{pending_total} 本还在比较中`
- CTA: `查看待处理 {requires_user_action_total}` when action count > 0

When `phase == complete`:

- Title: `比较完成`
- Coverage: `{candidate_total} 本已完成比较`
- Do not show a pending message.

When a baseline is missing:

- Do not show `0 / 0`.
- Show the missing connection/baseline state instead.

### Home counters

- `待你处理` = verified items with `requires_user_action=True`
- `已对齐` = only `aligned`
- `无需处理` = verified items with no user action, including but not limited to
  `aligned`

The first two counters are intentionally not additive partitions of all verified
items; `已对齐` is a semantic subset of `无需处理`.

## Screen 2 — Action inbox

### Purpose

Show only verified items where the user has something meaningful to decide or
do. Pending items never appear here.

### Section order

1. `需要确认`
2. `可在微信读书打开`
3. `建议更新豆瓣状态`

These correspond to the stable product buckets:

- `review`
- `add_to_weread`
- `suggest_douban_state`

### Current real-data example

```text
待处理 10

需要确认 · 7

三体
豆瓣：三体
微信读书：三体1
版本不同，需要确认
[查看详情]

人的境况
豆瓣：人的境况
微信读书：人的境况
版本信息需要确认
[查看详情]

...

可在微信读书打开 · 3

上流法则
已找到相同版本，但还不在当前书架
[去微信读书]

伯南克论大萧条
已找到相同版本，但还不在当前书架
[去微信读书]

地粮·新粮
已找到相同版本，但还不在当前书架
[去微信读书]
```

### Review labels

`review_edition`
- Primary label: `版本不同，需要确认`
- Detail CTA: `查看版本`

`review_identity`
- Primary label: `需要确认是不是同一本书`
- Detail CTA: `查看详情`

`review_reread`
- Primary label: `可能正在重读`
- Detail CTA: `确认阅读状态`

`review_state`
- Primary label: `阅读状态需要确认`
- Detail CTA: `查看状态`

### WeRead action label

For `add_to_weread_shelf_exact` / `add_to_weread_shelf_alternative`:

- Button: `去微信读书`
- Action intent: `OPEN_WEREAD`
- Never label this button `自动加入书架` until an official, validated shelf-write
  capability exists.

## Screen 3 — Reconciliation detail

### Purpose

Explain exactly why one item needs review before the user acts.

### `三体` real-data example

```text
确认版本

豆瓣中的版本
三体
状态：在读

微信读书找到的版本
三体1
当前书架：未加入

为什么需要确认？
这是同一部作品，但不是已验证的同一版本。
在确认前，我们不会把它当成同一个版本自动处理。

匹配信息
同一作品：是
同一版本：否
匹配类型：alternative_edition
微信读书 bookId：178677

[在微信读书查看]
[暂不处理]
```

### Detail field contract

For edition review, render when available:

- `title` — source/Douban title
- `selected_edition_title` — concrete selected WeRead Edition
- `source_state`
- `douban_subject_id`
- `weread_book_id`
- `shelf_membership`
- `match_kind`
- `deep_link`

Do not expose resolver scores as the main user explanation. The stable semantic
reason (`review_edition`, `review_identity`, etc.) should drive the copy.

## Action semantics

### `REVIEW_EDITION`

User decides whether the resolved WeRead Edition is acceptable for this Work.
No write happens merely by opening this screen.

### `REVIEW_IDENTITY`

User decides whether the two records represent the same Work. This remains a
stronger safety gate than Edition review.

### `OPEN_WEREAD`

Open `deep_link` when present. This is navigation only.

### `UPDATE_DOUBAN_STATE`

This is a future explicit-confirmation flow. The UI may present the suggested
state, but must not perform a Douban mutation without the existing preflight and
explicit-confirmation safeguards.

## Non-action results

The first version does not need to put these in the inbox:

- `aligned`
- `keep_douban_history`
- `weread_not_found`
- `weread_unavailable`
- `weread_coming_soon`

They can later appear under a secondary `全部结果` or per-book history view.

`weread_not_found` copy must retain bounded-search semantics. Prefer:

`暂未在当前搜索范围内找到对应版本`

rather than the absolute claim:

`微信读书没有这本书`

## V1 implementation boundary

V1 UI should consume only:

- `ReconciliationHomeModel`
- `ReconciliationActionInboxModel`
- `ReconciliationDetailModel`

It should not read reconciliation evidence/checkpoint tables directly and should
not duplicate `UserPlanKind` mapping logic in the frontend.
