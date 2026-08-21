# Product reconciliation screens

This document defines the first UI contract above `ProductReconciliationView`.
The screen models are local-only projections. They do not call providers and do
not perform Douban or WeRead mutations.

## 1. Home

`build_reconciliation_home_model(view)` provides the progress card and primary
verified-result counts.

For the current live sample, the intended presentation is conceptually:

```text
正在比较 14 / 1606 · <1%
待你处理 10
已对齐 2
无需处理 4
```

Important semantics:

- `pending_total` is unverified work. It is not `weread_not_found`.
- `aligned_total` is narrower than `no_user_action_total`.
- A verified item such as `keep_douban_history` can require no action without
  being fully aligned.
- Progress remains partial until every current-generation candidate has verified
  evidence.

## 2. Action inbox

`build_reconciliation_action_inbox(view)` includes only verified rows with
`requires_user_action=True`.

Sections are ordered by user risk/attention:

1. `review` — identity, Edition, reread, or state needs confirmation.
2. `add_to_weread` — a concrete WeRead Edition is available but not on shelf.
3. `suggest_douban_state` — exact verified evidence supports a Douban state
   suggestion.

Non-action rows such as `aligned`, `keep_douban_history`, `weread_not_found`,
`weread_unavailable`, and `weread_coming_soon` are not placed in this inbox.

If a future actionable plan has no inbox/action mapping, product projection fails
closed instead of silently putting it into a misleading section.

## 3. Detail

`get_reconciliation_detail(view, direction=..., item_id=...)` resolves only a
current-generation verified row. Pending/unverified candidates return `None`.

The detail payload preserves the normalized evidence needed by UI, including:

- Douban subject id
- selected WeRead book id
- selected Edition title
- Work/Edition match kind
- current shelf membership
- WeRead reading state/progress when available
- strongest Douban state / suggested state when available
- safe deep link when available

The live `三体` example should therefore be representable as:

```text
source: 三体 (Douban subject 2567698)
selected WeRead Edition: 三体1
WeRead bookId: 178677
match: alternative_edition
shelf: no
action: review_edition
```

`review_edition` is intentionally not converted to `open_weread`: material
Edition differences require confirmation first.

## 4. Action intents are not mutation authorization

`ProductActionKind` is a UI intent layer only:

- `review_edition`
- `review_identity`
- `review_reread`
- `review_state`
- `open_weread`
- `update_douban_state`
- `none`

`open_weread` means the product may offer the verified WeRead deep link. There is
still no established official shelf-write endpoint in this project.

`update_douban_state` means the product may later offer an explicitly confirmed
Douban mutation. It does not authorize automatic state changes.

The existing read-back verification and explicit confirmation requirements stay
in force for any future state-changing flow.
