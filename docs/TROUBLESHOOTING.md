# Troubleshooting & Development Notes

This document records real failures encountered while developing and validating `douban-weread`, together with their diagnosis and resolution.

The goal is not only to list fixes, but to preserve **how we distinguished environment problems, provider problems, parsing problems, and matching problems** so future contributors do not have to rediscover the same path.

Successful end-to-end snapshots are recorded separately in [LIVE_VALIDATION.md](LIVE_VALIDATION.md).

Last live validation: **2026-08-19**.

## Known-good baseline

The following setup was validated successfully on macOS:

- Python 3.10
- virtual environment created with `python3 -m venv .venv`
- modern pip after `python3 -m pip install --upgrade pip`
- editable install with `python3 -m pip install -e .`
- 29/29 unit tests passing
- live title search for `百年孤独` returning 10 Douban editions
- live ISBN search for `9787544253994` resolving to Douban subject `6082808`

Useful verification commands:

```bash
python3 -m unittest discover -s tests -v
python3 -m douban_weread search "百年孤独"
python3 -m douban_weread search --isbn 9787544253994
```

---

## PIT-001 — `python` command not found on macOS

### Symptom

```text
zsh: command not found: python
```

### Cause

The machine exposed Python as `python3`, not `python`.

### Resolution

Use:

```bash
python3 --version
python3 -m douban_weread ...
```

### Developer note

Documentation and examples should prefer `python3` unless the environment is explicitly controlled.

---

## PIT-002 — Editable install fails with old pip

### Symptom

```text
ERROR: File "setup.py" or "setup.cfg" not found.
Directory cannot be installed in editable mode
```

A `pyproject.toml` existed, but the environment had pip 21.2.3.

### Cause

The installed pip was too old for the project's modern `pyproject.toml` editable-install flow.

### Resolution

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

Validated result:

```text
Successfully built douban-weread
Successfully installed douban-weread-0.1.0
```

### Project change

The Quick Start now upgrades pip before editable installation.

The package minimum was also changed from Python 3.11 to **Python 3.10**, because the complete test suite and live CLI flow were validated successfully under Python 3.10 and no 3.11-only feature was required.

---

## PIT-003 — Python HTTPS fails while `curl` works

### Symptom

```text
[SSL: CERTIFICATE_VERIFY_FAILED]
certificate verify failed: self signed certificate in certificate chain
```

At the same time:

```bash
curl -I https://book.douban.com/
```

returned HTTP 200.

### Diagnosis

This distinction was important:

- `curl` succeeds → system network and Douban are reachable.
- Python `urllib` fails → investigate Python's certificate trust store before changing provider code.

The affected installation was the python.org macOS framework installation under:

```text
/Library/Frameworks/Python.framework/Versions/3.10
```

and `/Applications/Python 3.10` contained the certificate installer.

### Resolution

Run:

```bash
open "/Applications/Python 3.10/Install Certificates.command"
```

The installer upgraded `certifi` and linked Python's certificate bundle.

### Important safety rule

**Do not solve this by disabling TLS verification.**

Do not add `verify=False`, an unverified SSL context, or equivalent workarounds. Repair the local trust chain instead.

---

## PIT-004 — Douban returns HTTP 418 for Python's obvious bot User-Agent

### Symptom

After TLS was fixed, a plain `urllib.request.urlopen()` request reached Douban but returned:

```text
HTTP Error 418
```

### Diagnostic experiment

The same request with a browser-like User-Agent returned:

```text
status: 200
```

### Cause

Douban may reject obvious library/bot User-Agents even when the page is publicly reachable.

### Resolution

The Douban provider now uses a browser-like default User-Agent while keeping it configurable for tests and deployments.

### Developer note

A provider error should be classified before changing parsing logic:

```text
TLS error  -> environment / certificate layer
HTTP 418   -> request fingerprint / anti-bot layer
HTTP 4xx   -> endpoint / request contract layer
parse error -> HTML / metadata layer
match error -> resolver layer
```

---

## PIT-005 — Legacy `api.douban.com/v2/book` returned HTTP 400

### Symptom

After fixing both TLS and User-Agent handling:

```bash
python3 -m douban_weread search "百年孤独"
```

still failed with:

```text
Douban provider error: Douban request failed with HTTP 400
```

### Conclusion

The problem was no longer the user's machine or the User-Agent. The legacy Book API was not a reliable foundation for the project.

### Resolution / architecture change

The read-only Douban provider was switched from the legacy JSON API to public Douban Book web pages:

```text
book.douban.com/subject_search
        ↓
extract candidate subject IDs
        ↓
book.douban.com/subject/{id}/
        ↓
parse edition metadata
        ↓
normalize into provider-independent Edition
```

The public search route was manually validated with `百年孤独` and returned real subject IDs including:

```text
6082808
27107109
1786670
37144359
35060745
1059112
1937228
1762096
2008724
1794403
```

### Design lesson

Keep provider boundaries narrow. Because `DoubanBookSearchClient` still returns the same provider-independent `Edition` objects, the CLI and resolver did not need to know that the underlying transport changed from JSON API to HTML pages.

---

## PIT-006 — ISBN search must verify the subject page, not trust search ranking

### Risk

A web search for an ISBN can still return fuzzy or neighboring results.

### Resolution

`search_by_isbn()` treats search results only as candidates and verifies the normalized ISBN parsed from the subject page before returning an exact edition.

Validated case:

```text
ISBN: 9787544253994
Douban subject: 6082808
Title: 百年孤独
Translator: 范晔
Publisher: 南海出版公司
Published: 2011-06
```

### Safety implication

Exact ISBN verification is the strongest signal currently allowed for automatic edition identity. Search rank alone must never authorize a future state-changing action.

---

## PIT-007 — Real Douban metadata is inconsistent across editions

Live `百年孤独` results exposed several normalization edge cases:

### Author nationality prefixes vary

Examples:

```text
[哥伦比亚] 加西亚·马尔克斯
[哥伦比亚]加西亚·马尔克斯
（哥伦比亚）加西亚·马尔克斯
```

### Name punctuation varies

Examples include different middle-dot characters and spacing:

```text
加西亚·马尔克斯
加西亚・马尔克斯
加西亚 马尔克斯
```

### Translator formatting varies

Examples:

```text
黄锦炎, 沈国正, 陈泉
黄锦炎, 沈国正, 陈 泉
```

### ISBN may be missing

One real candidate (`subject/1937228`) did not expose an ISBN in the parsed result.

### Design consequence

Do not use raw display strings as identity keys.

The resolver should continue to:

- normalize Unicode and punctuation for comparison
- strip nationality-like prefixes for person matching
- treat missing metadata as unknown, not automatically different
- preserve raw/source metadata for debugging
- never perform a state-changing action from title-only similarity

Display values should remain close to the source; comparison values may be normalized separately.

---

## PIT-008 — Passing unit tests is not the same as a live provider validation

Before live testing, mocked unit tests passed while the actual provider still failed successively at:

1. local Python certificate validation
2. HTTP 418 anti-bot handling
3. legacy API HTTP 400

Only after those layers were tested independently did the real search succeed.

### Recommended validation sequence

For any provider change:

```text
1. Unit tests with fixtures/mocks
2. Basic network reachability
3. TLS validation
4. HTTP status / request fingerprint
5. Search endpoint returns real IDs
6. Detail endpoint exposes expected metadata
7. Normalization output inspection
8. Resolver behavior inspection
9. Only then consider write actions
```

### Why this matters

A failing live test should not immediately trigger changes to the resolver or data model. First identify the layer that failed.

---

## Current live-validation sample: `百年孤独`

On 2026-08-19 the CLI returned 10 candidate editions spanning:

- different translators
- different publishers
- publication years from the 1980s through 2025
- editions with and without ISBNs

This is a useful regression case because it exercises exactly why the project separates **Work** from **Edition**.

Recommended recurring smoke tests:

```bash
python3 -m douban_weread search "百年孤独"
python3 -m douban_weread search --isbn 9787544253994
```

Do not assert that the ordering or total candidate count will remain permanently stable; Douban search results can change.

---

## How to add a new pitfall

When a new issue is discovered, append a section using this template:

```markdown
## PIT-XXX — Short name

### Symptom
What the developer/user saw.

### Environment
Only details relevant to reproducing it.

### Diagnosis
How the failing layer was isolated.

### Root cause
What actually caused it, once known.

### Resolution
The safe fix or workaround.

### Prevention / test
What test, documentation, or architectural rule should prevent regression.
```

Prefer evidence from a reproducible command or test. If the root cause is still uncertain, label it as a hypothesis rather than presenting it as fact.

## Provider caveat

The Douban Web Provider is an unofficial integration over public web pages. Page structure, anti-bot behavior, and availability can change. Keep parsing isolated inside the provider, fail conservatively, avoid excessive requests, and never commit user cookies or secrets.
