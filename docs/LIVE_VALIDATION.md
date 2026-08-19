# Live Validation Log

This document records successful end-to-end validation runs against live provider data. It complements `TROUBLESHOOTING.md`, which focuses on failures, diagnosis, and fixes.

## 2026-08-19 — Douban Web Provider + CLI

### Environment

- macOS
- Python 3.10
- virtual environment: `.venv`
- pip upgraded from 21.2.3 to 26.2.1
- editable install: successful

### Unit tests

Command:

```bash
python3 -m unittest discover -s tests -v
```

Result:

```text
Ran 29 tests in 0.003s
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

### Exact ISBN search

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
```

Not yet validated in this run:

- resolver ranking against a user-selected source edition in a live multi-edition case
- Douban authenticated write actions (`wish`)
- WeRead discovery and edition alignment

### Regression note

Do not assert a permanent candidate count or search ordering. Douban search results are live data and may change. Regression tests should assert parsing and safety semantics using fixtures, while this file records observed live behavior at a point in time.
