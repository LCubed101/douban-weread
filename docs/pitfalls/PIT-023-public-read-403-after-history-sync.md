## PIT-023 — Public Douban reads return HTTP 403 after a large history sync

### Symptom

After a successful full authenticated reading-history sync, later read-only public requests from the same local environment failed with HTTP 403.

Observed failures included both:

```text
douban-weread search "白夜行" --limit 20
→ Douban provider error: Douban request failed with HTTP 403
```

and an exact subject-detail fetch:

```text
DoubanBookSearchClient().get_by_subject_id("27112607")
→ DoubanProviderError: Douban request failed with HTTP 403
```

The exact-subject traceback showed a redirect before the final 403 response.

### Environment

- macOS
- Python 3.10
- `agent/history-aware-reconciliation`
- local regression suite: `Ran 103 tests in 0.240s / OK`
- a real full Douban history sync of 1747 rows had completed earlier in the same session/window
- `DOUBAN_COOKIE` was unset before the public-read probes

### Diagnosis

This is broader than a `subject_search`-only failure because the exact subject page also returned 403 from the same local runtime.

The evidence is consistent with a temporary provider-side anti-abuse / access restriction affecting the current request environment, but the exact trigger is not proven. Do not claim a specific rate limit, IP ban, or account restriction without additional evidence.

The provider currently surfaces only the final HTTP status, so it cannot distinguish a generic forbidden response from a temporary challenge or other provider-side policy response.

### Recovery observation — 2026-08-20

After stopping further live Douban requests and waiting until the next day, one low-volume exact-subject probe was retried with `DOUBAN_COOKIE` still unset:

```text
DoubanBookSearchClient().get_by_subject_id("27112607")
→ 白夜行 南海出版公司 2017-07 27112607
```

The same local code and machine therefore recovered without a code change, credential change, or bypass attempt. This strengthens the interpretation that the earlier 403 was temporary provider-side access control rather than a permanent parser or endpoint failure. It still does not prove the exact trigger or scope of the restriction.

### Root cause

Not confirmed.

Likely category: temporary provider-side access control / anti-abuse behavior after a comparatively large number of requests. The current evidence does not establish whether the restriction is keyed by IP, request pattern, redirect target, session state, elapsed time, or another signal.

### Resolution

- Stop repeated live requests once the broad 403 is confirmed.
- Do not retry in a tight loop.
- Do not bypass captcha, anti-bot, or other provider protections.
- Keep using the already-synced local history baseline while waiting for provider access to recover.
- Resume live validation later with one low-volume exact-subject probe before any broader scan.
- If that probe succeeds, continue with targeted low-volume validation rather than immediately returning to a 20-candidate public search.

No code path should convert this failure into a successful reconciliation decision.

### Prevention / test

- Preserve the local-first architecture so most history checks require no network request.
- Keep full-history sync explicit rather than automatic per lookup.
- Prefer targeted subject fetches from the local history shortlist over broad public searches when validating history-aware reconciliation.
- Add conservative retry/backoff or clearer 403 diagnostics before any future automated refresh loop.
- Regression tests should continue to assert that provider errors fail closed and do not authorize a write.
- A future provider diagnostic may safely report status/redirect classification without exposing cookies or response secrets.
