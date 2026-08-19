# PIT-016 — DevTools copy may not be the Cookie request-header value

## Symptom

`douban-weread auth diagnose` reports:

```text
Cookie input kind: not_cookie_header
Parsed cookie count: 0
Has dbcl2: False
Has ck: False
Ready for auth check: False
```

## Diagnosis

The CLI has already ruled out an empty value and common one-line `Cookie: ...` normalization. The remaining input does not structurally look like an HTTP Cookie request-header value (`name=value; name2=value2`).

No authenticated network request should be attempted from this state.

## Common cause

When copying from browser DevTools, it is easy to copy the wrong artifact, for example:

- a request URL or label;
- a response header;
- a cookie table row rather than the request Cookie header;
- a complete cURL command;
- a JSON cookie export;
- explanatory text instead of the header value.

## Resolution

In Chrome DevTools:

1. Keep the user logged in to Douban.
2. Open a `book.douban.com` page and DevTools → Network.
3. Reload the page so a real request is captured.
4. Select a request whose host is `book.douban.com`.
5. In Headers → Request Headers, locate `cookie`.
6. Copy only the request-header value after `cookie:`. The desired shape is one line like `name=value; name2=value2; ...`.
7. Re-enter that value locally and run `douban-weread auth diagnose` before `auth check`.

## Safety rule

Never print, share, commit, screenshot, or paste the actual Cookie value into chat, GitHub issues, or PR comments. Diagnostics should expose only structural information such as cookie count and whether required names (`dbcl2`, `ck`) are present.

## Prevention

Prefer the built-in `douban-weread auth diagnose` command over ad-hoc shell or Python snippets. A live auth probe should only run after diagnostics report:

```text
Has dbcl2: True
Has ck: True
Ready for auth check: True
```
