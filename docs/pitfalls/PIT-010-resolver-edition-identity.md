# PIT-010 — High match score does not mean same Edition

## Symptom

Live resolver validation used Douban subject `6082808` as the Source Edition:

```text
百年孤独
范晔
南海出版公司
2011-06
ISBN 9787544253994
```

The resolver correctly ranked the exact ISBN match first, but it classified later editions such as:

- subject `27107109` — 范晔 / 南海出版公司 / 2017-08 / ISBN `9787544291170`
- subject `35060745` — 范晔 / 南海出版公司 / 2020-09 / ISBN `9787544299114`
- subject `37144359` — 范晔 / 南海出版公司 / 2025-01 / ISBN `9787573510921`

as:

```text
Kind: likely_same_edition
Score: 0.88
Same work: True
Exact edition: False
Confirmation required: False
```

## Why this was wrong

These records have different ISBNs and publication years. They can be strong matches for the same **Work**, but they are known to be different **Editions**.

A high similarity score based on title, author, translator, and publisher must not override explicit edition-identity evidence.

The bug came from the scoring implementation only rewarding matching fields. It did not treat known differences in ISBN, publisher, or publication year as evidence that two records are distinct editions.

## Design rule

Keep two concepts separate:

1. **Edition identity difference** — tells us that this is a different Edition of the same Work.
2. **Material reading difference** — tells us that user confirmation is needed because the reading experience may change.

Current policy:

| Difference | Same Work? | Alternative Edition? | Requires confirmation? |
| --- | --- | --- | --- |
| Different ISBN | usually yes | yes | no, by itself |
| Different publisher | usually yes | yes | no, by itself |
| Different publication year | usually yes | yes | no, by itself |
| Different translator | usually yes | yes | yes |
| Different language | usually yes | yes | yes |
| Revision / abridgement / annotation marker | usually yes | yes | yes |

Exact normalized ISBN remains the only edition identity signal currently considered safe for automatic state-changing actions.

## Resolution

`EditionMatchResult` now exposes two separate lists:

```text
edition_differences
material_differences
```

Known ISBN / publisher / year differences force `MatchKind.ALTERNATIVE_EDITION` but do not automatically require confirmation.

Translator / language / revision-content differences remain `material_differences` and require confirmation.

Regression tests were added for:

- different ISBN with otherwise matching metadata
- different publisher with same translator
- different publication year with same translator/publisher
- exact ISBN remaining exact and safe

## Live-validation expectation after the fix

Using `6082808` as Source Edition:

```text
6082808 (2011 / 范晔)
→ exact_edition
→ safe_to_auto_apply = True

27107109 (2017 / 范晔)
35060745 (2020 / 范晔)
37144359 (2025 / 范晔)
→ alternative_edition
→ confirmation required = False
→ edition_differences includes ISBN/year differences

1786670 / 1059112 / 1762096 / 1937228 / 2008724 / 1794403
→ alternative_edition
→ translator differs where applicable
→ confirmation required = True
```

## General lesson

**Similarity answers “how close are these records?”; identity evidence answers “are these the same Edition?”**

Identity constraints must take precedence over aggregate similarity scores.