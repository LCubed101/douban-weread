# Reconciliation product view

Date: 2026-08-20

Branch: `agent/weread-shelf-baseline`

## Purpose

The reconciliation engine exposes many provider, resolver, policy, checkpoint, and evidence details. Product UI should not parse CLI output or reproduce those rules. `build_product_reconciliation_view()` converts the current local onboarding/worker/evidence state into one stable UI-ready payload without making provider requests or performing platform mutations.

## Coverage is explicit

Before both baselines are complete, candidate coverage is unknown rather than zero:

```text
candidate_total = null
verified_total = null
pending_total = null
```

After both baselines are complete:

```text
candidate_total = current two-sided candidate queue
verified_total = current-generation persisted evidence
pending_total = candidate_total - verified_total
```

A pending item is unclassified. It must never be presented as `weread_not_found`, unavailable, aligned, or needing user action until verified evidence exists.

## Home-level counters

The product view exposes:

```text
phase
candidate_total
verified_total
pending_total
progress_percent
requires_user_action_total
aligned_total
no_user_action_total
worker_status
worker_ticks
```

`no_user_action_total` is intentionally broader than `aligned_total`. For example, `keep_douban_history`, `weread_not_found`, and `weread_unavailable` may require no immediate user action but are not equivalent to cross-platform alignment.

## Stable product buckets

Individual `UserPlanKind` values are grouped into these UI buckets:

```text
aligned
add_to_weread
suggest_douban_state
review
keep_douban_history
weread_not_found
weread_unavailable
weread_coming_soon
```

Mapping:

```text
aligned
  aligned

add_to_weread
  add_to_weread_shelf_exact
  add_to_weread_shelf_alternative

suggest_douban_state
  suggest_douban_wish
  suggest_douban_reading
  suggest_douban_read

review
  review_reread
  review_edition
  review_identity
  review_state

keep_douban_history
  keep_douban_history

weread_not_found
  weread_not_found

weread_unavailable
  weread_unavailable

weread_coming_soon
  weread_coming_soon
```

Unknown persisted plans fail closed instead of being guessed into a UI bucket.

## Important product semantics

Three distinctions must remain visible in future UI work:

1. **Pending is not not-found.** A book still awaiting verification has no provider conclusion yet.
2. **No user action is not aligned.** Keeping stronger Douban history or finding no WeRead Edition can both require no immediate action without meaning the platforms agree.
3. **Alternative Edition requiring confirmation is review, not add.** For example, the validated Douban `三体` → WeRead `三体1` case remains `review_edition`; the selected Edition identity is preserved for a detail screen.

## Detail rows

Each verified detail row keeps normalized UI-safe evidence such as:

```text
title / direction / item id
product bucket / exact user plan
summary / requires-user-action
Douban subject id
selected WeRead bookId and Edition title
shelf membership
match kind
WeRead coarse reading state/progress
strongest Douban state / suggested Douban state
deep link
```

Raw provider payloads, API keys, Cookies, and mutation authorization are not exposed through this layer.

## Intended UI flow

A future UI can render:

```text
Connecting / building baselines
        ↓
Comparing 14 / 1606
        ↓
Needs your action: N
Aligned: N
Version / identity review: N
Can add to WeRead: N
Suggest Douban state: N
WeRead not found: N
        ↓
Detail list backed by normalized current-generation evidence
```

The exact copy and visual design may evolve, but the semantic boundaries above should stay stable.
