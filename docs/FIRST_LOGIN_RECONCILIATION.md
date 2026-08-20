# First-login reconciliation flow

Date: 2026-08-20

Branch: `agent/weread-shelf-baseline`

## Product goal

A newly connected user should not have to understand `preview`, `queue`, `batch`, `scan`, checkpoints, or policy generations.

The application should progressively establish a complete local picture and expose only user-facing progress and review items:

```text
connect providers
→ establish complete Douban history baseline if missing
→ establish complete WeRead shelf baseline if missing
→ run bounded reconciliation worker ticks
→ persist normalized evidence
→ show coverage + user-plan report
```

This flow remains read-only with respect to both remote platforms. It does not authorize or perform a bidirectional write merely because a first-login reconciliation is running.

## Controller phases

The first-login controller exposes stable product phases:

```text
needs_baselines
reconciling
paused_provider
paused_generation
complete
```

`needs_baselines` also identifies the missing side(s): `douban`, `weread`, or both.

When both baselines are complete, the controller delegates to the persisted reconciliation worker state. Worker implementation details such as `running`, `partial`, checkpoint generation, and bounded scan batches do not need to leak into the primary onboarding UI.

## Baseline behavior

Complete existing baselines are reused. The controller only fetches a side whose current baseline is incomplete.

For a first-time user with neither baseline:

```text
Douban history fetch_all
→ atomic ReadingHistoryIndex.replace_full
→ WeRead official shelf sync
→ atomic WeReadShelfIndex.replace_full
→ reconciliation worker tick
```

If the first baseline succeeds and the second provider fails, the successful baseline stays local and complete. Reconciliation does not start until both are complete. A later retry fetches only the still-missing side.

Provider/parser failures must never be converted into an empty complete baseline.

## Credential boundary

Provider credentials are caller-owned, in-memory inputs to the controller. The controller and worker-state tables do not store:

```text
Douban Cookie
WeRead API key
bearer token
raw provider payload
write authorization
```

The local database stores complete normalized baselines, reconciliation evidence, checkpoints, and coarse worker progress only.

## UI-ready view

The controller view includes:

```text
phase
Douban baseline complete + sync timestamp
WeRead baseline complete + sync timestamp
missing baseline sides
worker coverage when both baselines are complete
last coarse error kind
```

When a worker exists, UI progress should be derived from persisted evidence coverage rather than an in-memory request counter. This means progress survives app restarts.

## Failure / resume examples

### WeRead baseline failure after Douban succeeds

```text
phase: paused_provider
Douban baseline: complete
WeRead baseline: incomplete
missing: weread
error: weread_baseline
```

Retry behavior: reuse Douban baseline, fetch WeRead only, then begin reconciliation.

### Reconciliation provider failure

```text
phase: paused_provider
both baselines: complete
worker state: paused_provider
error: weread_provider or douban_provider
```

Previously verified evidence remains persisted. The next worker tick resumes from evidence + checkpoint state; the failed item was not checkpointed.

### Baseline / policy generation changes

A new complete baseline timestamp or reconciliation policy version identifies a new reconciliation generation. Old evidence/state can remain for audit, but it must not be reported as current progress.

## First-login UI recommendation

The initial UI should focus on only three user concepts:

```text
1. Connecting / reading your two libraries
2. Comparing editions and reading states (progress x / total)
3. Review needed (count of user-action plans)
```

Detailed technical categories remain available in the report layer but should not dominate onboarding.
