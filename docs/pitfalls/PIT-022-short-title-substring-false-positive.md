# PIT-022 — Short title substring creates false history candidate

## Symptom

A positive local lookup for `白夜行` correctly returned two `READ` records named `白夜行`, but also returned an unrelated `WISH` record whose entire title was only `白`.

```text
Local history candidates for "白夜行":
- READ | subject 3259440 | 白夜行
- READ | subject 10554308 | 白夜行
- WISH | subject 35965039 | 白
```

## Environment

- local-first Douban reading-history index
- SQLite baseline version 3
- `ReadingHistoryIndex.find_title_candidates()`
- observed during live validation on 2026-08-19

## Diagnosis

The shortlist logic awarded a fixed substring score whenever either normalized title contained the other:

```python
elif key in target_key or target_key in key:
    score = 0.92
```

That rule treated a one-character stored title such as `白` as a strong candidate for `白夜行` merely because it is a substring.

## Root cause

Substring containment was used as a coarse discovery heuristic without considering the amount of title coverage. Very short titles can therefore match many unrelated longer titles.

This did **not** authorize a mutation: local title matching is candidate discovery only, and Work/Edition verification is still required. However, it would create noisy candidate sets and unnecessary subject-detail requests once the history index is wired into reconciliation.

## Resolution

The substring heuristic is now directional and coverage-aware:

- exact normalized equality remains strongest;
- if the query is contained in a longer stored title, the query must contain at least two normalized characters;
- if a stored title is shorter than the query, it must contain at least two normalized characters and cover at least 60% of the query;
- otherwise similarity falls back to `SequenceMatcher` and the normal threshold.

A regression test reproduces the live `白夜行` / `白` case and requires only the two exact `白夜行` records to remain in the shortlist.

## Prevention / test

Do not treat arbitrary substring containment as strong evidence by itself, especially for one-character or very short titles.

Keep the architectural boundary explicit:

```text
local title match
→ candidate discovery only
→ full Edition metadata
→ same-Work verification
→ reconciliation
→ only then any write decision
```

The local shortlist must optimize recall without allowing obviously weak fragments to flood downstream resolution.
