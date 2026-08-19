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

## 2026-08-19 — Live Douban authentication validation

The authenticated Book adapter was validated with a user-owned browser session while keeping the Cookie value local and out of logs/chat.

### Local Cookie diagnostics

After copying the actual `Cookie` request-header value from a logged-in `book.douban.com` request:

```text
Cookie input kind: cookie_header
Parsed cookie count: 16
Has dbcl2: True
Has ck: True
Ready for auth check: True
```

This confirms that the local parser recognized a real browser Cookie header and found the two fields required by the current authenticated Book adapter.

### Read-only authenticated probe

Command:

```bash
douban-weread auth check
```

Observed result:

```text
Douban auth OK (user 182590900): Douban Cookie was accepted by the Book interest endpoint.
```

This validates the current user-owned Cookie → authenticated Book interest-endpoint probe path on a real account.

### Safety status

**Passed:**

```text
local secret input without echo
→ Cookie structure diagnosis
→ dbcl2 / ck detection
→ authenticated Book interest endpoint probe
```

**Not yet performed:**

- a real state-changing `wish` request
- post-write read-back against a real changed subject

A real write remains intentionally deferred until Work-level reading-state reconciliation is live-validated, so an already-read / currently-reading / other-edition Want-to-Read record cannot be silently downgraded or duplicated.

## 2026-08-19 — Live Work-level reconciliation validation

### Unit-test baseline

The reconciliation branch was validated locally before the live read-only run:

```text
Ran 71 tests in 0.016s
OK
```

### Live target

The read-only Work inspection used Douban subject `25837854`:

```text
荷马史诗·奥德赛
Translator: 王焕生
Publisher: 人民文学出版社
Published: 2015-06
ISBN: 9787020102792
```

Command:

```bash
douban-weread inspect --subject 25837854 --limit 20
```

The live scan resolved the target and five additional same-Work editions from the current Douban title-search candidate set. All six returned no current Douban interest state:

| Subject | Translator | Publisher | Published | ISBN | State |
| --- | --- | --- | --- | --- | --- |
| 25837854 | 王焕生 | 人民文学出版社 | 2015-06 | 9787020102792 | `NONE` |
| 1062694 | 王焕生 | 人民文学出版社 | 1997-05 | 9787020038848 | `NONE` |
| 34894031 | 王焕生 | 人民文学出版社 | 2020-05 | 9787020158287 | `NONE` |
| 1777142 | 王焕生 | 人民文学出版社 | 1997-05 | 9787020024032 | `NONE` |
| 3247025 | 王焕生 | 人民文学出版社 | 2008-06 | 9787020071319 | `NONE` |
| 30282747 | 王焕生 | 人民文学出版社 | 2018-07 | 9787020130528 | `NONE` |

Observed decision:

```text
Decision: safe_to_wish
Safe to write Want-to-Read: True
Requires user decision: True
```

This validates the live read-only path:

```text
exact subject fetch
→ title candidate discovery
→ same-Work filtering
→ authenticated per-edition interest-state reads
→ Work-level reconciliation decision
```

### Important limitation

This result is **not proof that the user has never read or marked any edition of this Work**. The current inspector is bounded by the editions returned by the live title-search candidate scan. It does not yet index the user's complete historical `wish` / `do` / `collect` lists.

Therefore `safe_to_wish` currently means only:

> no conflicting state was found among the same-Work editions discovered by the current live scan.

The next reliability layer remains a local Douban reading-history index before relying on reconciliation as an exhaustive forgotten-history check.

### Write status

No state-changing `wish` request was performed in this validation. A real write remains deferred until the account/session secret has been replaced after accidental exposure and the intended completeness boundary for historical-state checking is accepted or improved.

## 2026-08-19 — History baseline parser-drift recovery

The first live history sync exposed PIT-020: authenticated HTTP requests succeeded, but the old list parser returned zero entries and incorrectly marked the baseline complete. After the parser and baseline-version fixes were added, the complete local regression suite passed:

```text
Ran 95 tests in 0.046s
OK
```

The previously written `complete + 0 rows` SQLite snapshot was then checked with:

```bash
douban-weread history status
```

Observed result:

```text
History baseline: not synced
Database: /Users/ludao/.local/share/douban-weread/history.sqlite3
```

This validates the migration/safety boundary: a baseline produced by the pre-fix parser is no longer trusted as complete after the parser schema version changes. No manual database deletion was required.

## 2026-08-19 — Live Douban reading-history baseline sync

After PIT-020 was fixed, the corrected history parser was run against the authenticated user's real Douban Book lists.

Authentication diagnostics succeeded without exposing credential values:

```text
Cookie input kind: cookie_header
Parsed cookie count: 15
Has dbcl2: True
Has ck: True
Ready for auth check: True
```

The authenticated read-only probe also succeeded:

```text
Douban auth OK (user 182590900): Douban Cookie was accepted by the Book interest endpoint.
```

Command:

```bash
douban-weread history sync --full
```

Observed result:

```text
Douban history baseline synced successfully.
History baseline: complete
Total: 1747
Want-to-Read: 1511
Reading: 40
Read: 196
Database: /Users/ludao/.local/share/douban-weread/history.sqlite3
```

This live-validates the corrected `li.subject-item` history ingestion path, pagination across the user's lists, state mapping for `wish` / `do` / `collect`, full-snapshot replacement, and the local SQLite persistence layer.

The full-history baseline is now available for local-first candidate discovery. The next integration step is to use this baseline to shortlist historical subject IDs, resolve full Edition metadata only for those candidates, and feed the verified same-Work records into reconciliation before any state-changing `wish` action.

No real state-changing Douban write was performed during this validation.

### Local-only lookup after Cookie removal

After the full sync, the temporary `DOUBAN_COOKIE` was removed and the local index was queried without provider access.

`history status` continued to report the persisted baseline counts:

```text
Want-to-Read: 1511
Reading: 40
Read: 196
Last full sync: 2026-08-19T09:40:22.610918+00:00
Database: /Users/ludao/.local/share/douban-weread/history.sqlite3
```

A local title lookup for the previously inspected target returned no candidates:

```bash
douban-weread history lookup "荷马史诗：奥德赛"
```

```text
No local history candidates found for "荷马史诗：奥德赛".
```

This validates the local-only negative lookup path. It is not considered a parser failure: the baseline remains complete, and the lookup result simply means no stored history title passed the local candidate threshold for this query. A positive lookup against a title known to exist in the user's history is still needed before the local lookup layer is considered fully live-validated.
