# PIT-013 — Browser Cookie copy format may not be a raw Cookie header value

## Symptom

After the full suite passed, the first live read-only auth check returned:

```text
Douban auth failed [cookie_format]: DOUBAN_COOKIE could not be parsed as a Cookie header.
```

No Cookie value was printed or shared.

## Diagnosis

This failure happens before the network auth probe. It means the locally supplied `DOUBAN_COOKIE` could not be parsed into cookie key/value pairs.

The exact pasted representation was not inspected for privacy. Common browser-copy variants include:

```text
Cookie: a=b; c=d
```

versus the raw value expected by many parsers:

```text
a=b; c=d
```

A full multi-line request-header dump or a copied shell/cURL command is intentionally not treated as a Cookie value.

## Resolution

The CLI now accepts the common single-line `Cookie: ...` prefix and strips it before constructing `DoubanBookInterestClient`.

It does **not** attempt to parse arbitrary multi-line header dumps or commands. This keeps credential handling narrow and predictable.

## Privacy-safe troubleshooting rule

Never ask a contributor to paste their Cookie into an issue, PR, chat, or log.

If parsing still fails, inspect only metadata locally, such as whether expected **cookie names** are present (`dbcl2`, `ck`), without printing their values.

## Prevention / test

A regression test now constructs an obviously synthetic Cookie header with the `Cookie:` prefix and verifies that:

- the prefix is removed;
- synthetic `dbcl2` and `ck` fields are parsed;
- no real credential material is required.

## General lesson

Authentication setup has two distinct layers:

```text
local representation / parsing
→ authenticated network probe
```

Do not debug server-side auth until local credential representation has been validated.