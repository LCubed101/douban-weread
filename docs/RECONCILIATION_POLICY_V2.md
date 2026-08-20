# Reconciliation policy v2

Date: 2026-08-20

Branch: `agent/weread-shelf-baseline`

## Why v2 exists

Live Douban → WeRead background verification surfaced active Douban `READING` entries whose first bounded catalog lookup returned:

```text
WeRead catalog status: not_found
Resolution: no_weread_edition
```

That result is not proof that the entire WeRead catalog lacks the Work. `NOT_FOUND` only means no resolver-confirmed same-Work Edition was found inside the configured search window.

Two product issues followed from this:

1. A currently-reading Work deserves a stronger verification attempt than a low-priority Want-to-Read backlog item.
2. A checkpoint created under an older reconciliation algorithm must not permanently suppress re-verification after the affected algorithm changes.

## Direction-scoped policy generations

The reconciliation generation is:

```text
Douban complete-baseline timestamp
+ WeRead complete-shelf timestamp
+ direction-specific reconciliation policy version
```

A checkpoint therefore prevents repeated work only when all three inputs are unchanged.

Policy versions are intentionally independent by direction:

```text
WeRead → Douban
policy v1

Douban → WeRead
policy v2
```

Only the Douban → WeRead catalog policy changed in this milestone. Existing successful WeRead → Douban v1 checkpoints remain reusable and are not invalidated merely because the opposite direction was upgraded.

## Douban → WeRead policy v2

Policy v2 uses the following catalog windows:

```text
Douban WISH
→ configured base window (default <= 5 candidates)

Douban READING
→ widened high-priority window (<= 10 candidates)
```

The wider Reading window is still bounded. A v2 `NOT_FOUND` remains an unresolved bounded result, not a catalog-wide absence claim.

## Migration

Existing checkpoint rows created before the policy-version column are migrated locally with:

```text
policy_version = 1
```

The migration does not delete the rows. Douban → WeRead policy v2 does not reuse its v1 rows as completed work. When an affected item is re-verified under v2, its row is updated to policy v2 and the latest outcome.

WeRead → Douban continues to use policy v1, so its existing v1 rows remain valid.

No API key, Cookie, provider response payload, or mutation authorization is stored in checkpoint rows.

## Ordering

Background priority remains product-oriented:

```text
Douban → WeRead
READING before WISH

WeRead → Douban
non-private finished shelf items before unfinished items
private/import-like items last
```

The goal is to surface reading-state conflicts and current-reading availability earlier without fanning out requests across the full account state.

## Safety boundary

- Policy v2 is read-only.
- One batch remains hard-capped at five queue items.
- `NOT_FOUND` is always described as bounded.
- Updating one direction's reconciliation logic can invalidate only that direction's old checkpoints without requiring a platform baseline refresh.
- Provider/parser failures are not checkpointed as successful completion.
- No WeRead or Douban state-changing action is performed by background reconciliation.
