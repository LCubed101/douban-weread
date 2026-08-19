# Douban Authentication & Want-to-Read

Status: **implemented with mocked tests; live authenticated validation still required**.

This module uses a user-owned browser session to interact with an unofficial/internal Douban Book interest endpoint. Treat it as a fragile provider integration, not a stable public API.

## Security model

- Credentials stay local.
- `DOUBAN_COOKIE` must never be committed.
- Do not paste real Cookie values into GitHub issues, PR comments, chat messages, screenshots, or logs.
- The client never intentionally prints the Cookie value.
- State-changing actions require explicit confirmation.
- Every successful write is followed by a read-back verification.

## Cookie fields

The current implementation expects a complete Cookie header from a logged-in Douban browser session and validates at least:

- `dbcl2` — login/session identity signal
- `ck` — request token used by interest actions

Other Cookie fields should be preserved when exporting the full browser Cookie header.

## Local configuration

Example only — do **not** copy a real value into documentation:

```bash
export DOUBAN_COOKIE='bid=...; dbcl2="..."; ck=...; ...'
```

If using a local `.env` loader later, keep the file ignored by Git.

A browser may expose the same request header in either of these one-line forms:

```text
bid=...; dbcl2=...; ck=...
```

or:

```text
Cookie: bid=...; dbcl2=...; ck=...
```

The CLI accepts both forms. Do not paste a full multi-line request-header dump, a complete cURL command, or a JSON cookie export as `DOUBAN_COOKIE`.

To avoid putting the Cookie directly into shell history:

```bash
read -s "DOUBAN_COOKIE?Paste Douban Cookie locally: "
export DOUBAN_COOKIE
echo
```

The terminal intentionally does not echo the pasted secret.

## Local Cookie diagnosis

Before making any network request, inspect the locally configured input safely:

```bash
douban-weread auth diagnose
```

This command makes **no network request** and never prints Cookie values. It reports only:

- input format classification
- parsed cookie count
- whether `dbcl2` is present
- whether `ck` is present
- whether the input is ready for `auth check`

Example successful structural result:

```text
Cookie input kind: cookie_header
Parsed cookie count: 8
Has dbcl2: True
Has ck: True
Ready for auth check: True
```

Possible input classifications include `empty`, `multiline_input`, `curl_command`, `json_or_cookie_export`, `unparseable_cookie_header`, `not_cookie_header`, `empty_parse`, and `cookie_header`.

## Read-only authentication check

Run this only after `auth diagnose` reports `Ready for auth check: True`:

```bash
douban-weread auth check
```

The command performs two layers of validation:

1. local Cookie shape: required fields are present
2. a read-only request to the Douban Book interest endpoint

It may report:

- `missing_cookie`
- `cookie_format`
- `missing_dbcl2`
- `missing_ck`
- `cookie_expired_or_forbidden`
- `cookie_expired`
- `captcha_or_blocked`
- `unexpected_response`
- `network_or_provider`

Captcha / anti-abuse pages are surfaced as errors. The project should not automate captcha bypass.

## Want-to-Read action

The current state-changing command is intentionally narrow:

```bash
douban-weread wish --subject <DOUBAN_SUBJECT_ID> --confirm
```

Without `--confirm`, the client refuses to mutate state.

The command sends `interest=wish` for the exact subject ID and then reads the subject interest state back. It reports success only when the saved state is actually `wish`.

Do **not** use title-only similarity to choose the subject. The subject must already be explicitly selected/resolved by the caller.

## Current protocol assumption

Implementation research indicates the Book interest route follows the same family of internal endpoints used by other Douban media types:

```text
https://book.douban.com/j/subject/{subject_id}/interest
```

The request uses the browser session Cookie, `ck`, and state name `wish`. This is not an official public API contract and may change.

The implementation was independently written for this repository. Open-source projects used as protocol/behavior references are listed in `ACKNOWLEDGEMENTS.md`; no source code is currently copied directly into this repository.

## Mutation safety contract

A write is considered successful only when all of the following hold:

```text
explicit subject selected
→ explicit confirmation present
→ auth probe succeeds
→ POST receives an acceptable response
→ GET/read-back succeeds
→ actual state == wish
```

Any mismatch fails closed.

## Live validation sequence

Use a real account only after the unit tests pass.

1. Export Cookie locally; never send it to another person or service.
2. Run the full unit test suite.
3. Run `douban-weread auth diagnose`.
4. Only if it reports `Ready for auth check: True`, run `douban-weread auth check`.
5. Inspect the exact subject in a browser.
6. Choose a subject whose state you are comfortable changing.
7. Run the unconfirmed `wish` command first and verify that it refuses.
8. Only then run the same command with `--confirm`.
9. Verify both the CLI read-back and the Douban web UI.

Record any new failure mode in `docs/TROUBLESHOOTING.md` or `docs/pitfalls/`.

## Live validation status — 2026-08-19

- 52/52 tests passed on the user's macOS / Python 3.10 environment before adding the dedicated diagnostic command.
- The authenticated network probe has not yet succeeded because the current local Cookie input parsed to zero fields.
- A previous multi-line Python diagnostic was accidentally pasted into zsh one statement at a time; the project now provides `douban-weread auth diagnose` instead (PIT-015).
- No live `wish` write should be attempted until `douban-weread auth check` succeeds.

## Known uncertainty

The public Douban subject page can be verified without authentication, but the authenticated Book interest endpoint cannot be fully validated from this repository alone. A live user-owned Cookie test is therefore required before Issue #5 can be considered complete.
