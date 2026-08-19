# Live Validation Log

This document records successful end-to-end validation runs against live provider data. It complements `TROUBLESHOOTING.md`, which focuses on failures, diagnosis, and fixes.

## 2026-08-19 — Douban Web Provider + CLI

### Environment

- macOS
- Python 3.10
- virtual environment: `.venv`
- pip upgraded from 21.2.3 to 26.2.1
- editable install: successful
- installed console command: successful

### Unit tests

Command:

```bash
python3 -m unittest discover -s tests -v
```

Initial provider/CLI result:

```text
Ran 29 tests in 0.003s
OK
```

After the live resolver validation exposed PIT-010 and the resolver regression tests were added:

```text
Ran 31 tests in 0.004s
OK
```

### Live title search

Command:

```bash
python3 -m douban_weread search "百年孤独"
```

Result: 10 candidate editions were returned.

Representative candidates:

| Douban subject | Translator(s) | Publisher | Published | ISBN |
| --- | --- | --- | --- | --- |
| 6082808 | 范晔 | 南海出版公司 | 2011-06 | 9787544253994 |
| 27107109 | 范晔 | 南海出版公司 | 2017-08 | 9787544291170 |
| 1786670 | 黄锦炎, 沈国正, 陈泉 | 上海译文出版社 | 1989-10 | 9787532706907 |
| 37144359 | 范晔 | 南海出版公司 | 2025-01 | 9787573510921 |
| 35060745 | 范晔 | 南海出版公司 | 2020-09 | 9787544299114 |
| 1937228 | 黄锦炎, 沈国正, 陈 泉 | 上海译文出版社 | 1984-08 | not exposed in parsed result |

The live result also exposed real metadata variation in author nationality prefixes, punctuation, spacing, and translator formatting. These are documented in `TROUBLESHOOTING.md`.

### External metadata spot-check

The following live CLI results were manually cross-checked against current Douban subject pages and matched on the critical Edition fields used by the resolver:

- subject `6082808`: title, author, translator 范晔, 南海出版公司, 2011-06, ISBN `9787544253994`
- subject `27107109`: title, author, translator 范晔, 南海出版公司, 2017-08, ISBN `9787544291170`
- subject `1786670`: title, author, translators 黄锦炎 / 沈国正 / 陈泉, 上海译文出版社, 1989-10, ISBN `9787532706907`

This validates not just HTTP reachability but the current HTML parsing path for the metadata fields that matter to edition identity.

### Exact ISBN search via module

Command:

```bash
python3 -m douban_weread search --isbn 9787544253994
```

Result:

```text
Exact ISBN result:

百年孤独
   Authors: [哥伦比亚] 加西亚·马尔克斯
   Translators: 范晔
   Publication: 南海出版公司 · 2011-06
   ISBN: 9787544253994
   Douban: https://book.douban.com/subject/6082808/
```

This confirms that ISBN search resolves and then verifies the exact subject ISBN instead of trusting search order alone.

### Editable install

Commands:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

Result:

```text
Successfully built douban-weread
Successfully installed douban-weread-0.1.0
```

### Installed console command

After editable installation, the package entry point was validated directly:

```bash
douban-weread search --isbn 9787544253994
```

It returned the same exact edition (subject `6082808`, 范晔, 南海出版公司, 2011-06, ISBN `9787544253994`). This closes the packaging/entry-point validation in addition to the `python3 -m ...` execution path.

## 2026-08-19 — Live Edition Resolver validation

### Source Edition

The live resolver run used the exact ISBN result as the Source Edition:

```text
subject: 6082808
Title: 百年孤独
Translator: 范晔
Publisher: 南海出版公司
Published: 2011-06
ISBN: 9787544253994
```

### Expected and observed resolver behavior after PIT-010 fix

The corrected resolver was run against all 10 live candidates.

| Subject | Edition outcome | Confirmation | Key differences |
| --- | --- | --- | --- |
| 6082808 | `exact_edition` | no | none; exact ISBN |
| 27107109 | `alternative_edition` | no | ISBN, publication year |
| 37144359 | `alternative_edition` | no | ISBN, publication year |
| 35060745 | `alternative_edition` | no | ISBN, publication year |
| 2008724 | `alternative_edition` | yes | ISBN, year; translator differs |
| 1786670 | `alternative_edition` | yes | ISBN, publisher, year; translator differs |
| 1059112 | `alternative_edition` | yes | ISBN, publisher, year; translator differs |
| 1762096 | `alternative_edition` | yes | ISBN, publisher, year; translator differs |
| 1937228 | `alternative_edition` | yes | publisher, year; translator differs; ISBN missing |
| 1794403 | `alternative_edition` | yes | publisher, year; translator differs; ISBN missing |

Only subject `6082808` was `safe_to_auto_apply=True`. All non-exact editions remained unsafe for silent state-changing actions.

This validates the intended distinction between:

```text
same Work
≠
same Edition
≠
materially equivalent reading experience
```

In particular, later 范晔 / 南海出版公司 records are now correctly treated as alternative editions despite high metadata similarity, because their known ISBNs and publication years differ.

Translator-different editions are correctly surfaced as material differences and require confirmation.

### Validation status

**Passed:**

```text
Douban public search
→ subject ID discovery
→ subject detail fetch
→ HTML metadata parsing
→ Edition normalization
→ CLI multi-edition display
→ exact ISBN verification
→ editable package install
→ installed console entry point
→ live resolver ranking
→ exact-vs-alternative Edition identity
→ material translator-difference confirmation policy
```

Not yet validated in this run:

- Douban authenticated write actions (`wish`)
- WeRead discovery and edition alignment

### Regression note

Do not assert a permanent candidate count or search ordering. Douban search results are live data and may change. Regression tests should assert parsing and safety semantics using fixtures, while this file records observed live behavior at a point in time.
