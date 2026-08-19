# Edition Matching Policy

This document describes how `douban-weread` distinguishes the same **Work** from the same **Edition** and how it decides whether an alternative WeRead-readable edition can be recommended.

## Safety principle

A visually similar title is never enough for a state-changing action.

Only an **exact ISBN match** is currently considered safe for automatic mutation. Other matches can be ranked and recommended, but remain explainable and conservative.

## Match kinds

- `EXACT_EDITION` — ISBN is identical after normalization.
- `LIKELY_SAME_EDITION` — strong same-work evidence and no material content/translation difference; publisher/year may differ.
- `ALTERNATIVE_EDITION` — same work, but an edition-level difference exists or confidence is lower.
- `AMBIGUOUS` — insufficient evidence to establish the same work.
- `DIFFERENT_WORK` — title may match, but author evidence contradicts the match.

## Signals

The first scoring implementation uses:

- title similarity
- author overlap
- translator overlap
- publisher equality
- publication-year equality
- language equality
- exact ISBN as a hard identity signal

The score is not intended to be a universal bibliographic truth. It is an explainable ranking aid for the user workflow.

## Material differences

The following differences require confirmation before substitution:

- different translator
- different language
- revision / abridgement / annotation markers

Publisher or publication-year differences alone are treated as non-material for recommendation purposes, but they do **not** make a candidate safe for silent state-changing actions.

## Examples

### Exact ISBN

Source and candidate share the same normalized ISBN.

Result: `EXACT_EDITION`, no confirmation required, safe for automatic alignment.

### Same work, same translator, different publisher/year

Result: usually `LIKELY_SAME_EDITION`. The alternative can be recommended without a warning dialog, but the current resolver still marks it unsafe for silent account mutation.

### Same work, different translator

Result: `ALTERNATIVE_EDITION`, confirmation required.

This matters because translation can materially change the reading experience.

### Same title, different author

Result: `DIFFERENT_WORK`. Never auto-select.

### Title only, no author evidence

Result: `AMBIGUOUS`. Never auto-select or mutate account state.

## Explainability contract

Each result exposes:

- `score`
- `kind`
- `same_work`
- `exact_edition`
- `requires_confirmation`
- `safe_to_auto_apply`
- `reasons`
- `material_differences`

Interfaces such as Feishu, Web UI, or CLI should use these fields rather than reproducing matching logic themselves.
