# PIT-014 — Cookie parsing can fail silently with an empty result

## Symptom

A real local auth check reported:

```text
Douban auth failed [cookie_format]: DOUBAN_COOKIE could not be parsed as a Cookie header.
```

A value-safe diagnostic then showed:

```text
Contains newline: False
Parsed cookie names: []
Has dbcl2: False
Has ck: False
```

No parser exception was raised.

## Diagnosis

Python's `http.cookies.SimpleCookie.load()` does not guarantee that unsupported input raises an exception. Some non-Cookie input can simply produce an empty cookie jar.

Therefore these are different states:

1. environment variable missing/empty;
2. Cookie parser raises;
3. Cookie parser returns an empty result;
4. Cookie parses, but required fields such as `dbcl2` or `ck` are missing.

The third case should not be mistaken for a network/authentication failure because no request has been made yet.

## Likely input classes

Without exposing any credential values, useful structural checks include whether the local value:

- contains `=` and `;` like an HTTP Cookie header value;
- starts with `Cookie:`;
- starts with `{` or `[` like a JSON cookie export;
- starts with `curl ` like a copied cURL command;
- contains newlines like a full request-header block.

Do not print the raw Cookie while debugging.

## Resolution

The supported input remains a normal HTTP Cookie request-header value:

```text
name=value; another=value; ...
```

A one-line `Cookie: ...` prefix may be normalized by the CLI. JSON exports, complete cURL commands, and multi-line request dumps should not be guessed or silently converted into credentials.

## Prevention / safety rule

When authentication setup fails before the first network request:

- diagnose only input shape and cookie names;
- never log or paste cookie values;
- distinguish local-format failures from expired-session, HTTP 403, captcha, or provider failures;
- fail closed rather than trying broad credential-format heuristics.

## General lesson

**No exception does not mean successful parsing.** For credential adapters, validate both parser execution and the resulting structured fields before making a request.
