# V1.3 Podcast Episode Router

Goal: route a recommended podcast episode to the exact Xiaoyuzhou episode page without creating a second listening library.

## Product path

```text
Podcast episode title / screenshot / recommendation text
→ identify episode + podcast
→ resolve exact Xiaoyuzhou episode
→ return `https://www.xiaoyuzhoufm.com/episode/<eid>`
```

V1.3 is read-only. It does not subscribe, favorite, or modify Xiaoyuzhou state.

## Why Xiaoyuzhou first

The current primary listening destination is Xiaoyuzhou. Public episode pages use stable-looking URLs of the form:

```text
https://www.xiaoyuzhoufm.com/episode/<eid>
```

Xiaoyuzhou's native search surface is authenticated. The smoke adapter therefore reads a user-owned access token from the local environment only:

```text
XIAOYUZHOU_ACCESS_TOKEN
XIAOYUZHOU_DEVICE_ID   # optional; include when available from the same session
```

Never commit or paste these values into issues, chat, screenshots, docs, or Git history.

## Resolver policy

Fail closed:

- one exact episode-title match → `EXACT`
- multiple exact matches → `AMBIGUOUS`
- fuzzy/keyword-only results → never auto-select
- optional exact podcast title can narrow same-name episodes

The first smoke test intentionally validates title → episode URL before any Feishu runtime integration.

## Local smoke

After pulling the branch/baseline and activating `.venv`:

```bash
python scripts/podcast_smoke.py "触屏时代的触觉饥渴" --podcast "随机波动StochasticVolatility"
```

Expected successful shape:

```text
EXACT · <episode title> · <podcast> · <published time>
https://www.xiaoyuzhoufm.com/episode/<eid>
Read-only resolve completed. No Xiaoyuzhou state was modified.
```

If no token is loaded:

```text
AUTH_REQUIRED · XIAOYUZHOU_ACCESS_TOKEN is not set.
```

Do not wire this into Feishu until a real local search successfully resolves at least one known episode to the same Xiaoyuzhou episode page visible in the app/web share flow.
