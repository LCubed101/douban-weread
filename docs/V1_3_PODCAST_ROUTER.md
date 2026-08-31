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

## Xiaoyuzhou search surface

The direct Xiaoyuzhou API adapter keeps using:

```text
POST https://api.xiaoyuzhoufm.com/v1/search/create
{"keyword": "...", "type": "EPISODE", "limit": 10}
```

A separate open-source `xyz` proxy exposes its own local `POST /search` wrapper. That wrapper path must not be confused with Xiaoyuzhou's direct API path. Recent Xiaoyuzhou tooling also uses `/v1/search/create` directly, so V1.3 keeps that endpoint until a live smoke test proves otherwise.

Public episode destinations remain:

```text
https://www.xiaoyuzhoufm.com/episode/<eid>
```

## Authentication

Search is authenticated. Prefer a long-lived refresh token stored only in a local private file rather than repeatedly copying a short-lived access token.

Default refresh-token file:

```text
~/.config/douban-weread/xiaoyuzhou_refresh_token
```

Or set:

```text
XIAOYUZHOU_REFRESH_TOKEN_FILE=/your/private/path
XIAOYUZHOU_DEVICE_ID=...   # optional; use the value from the same browser session
```

`podcast_smoke.py` will exchange the refresh token for a short-lived access token in memory. If Xiaoyuzhou rotates the refresh token, the new value is written back atomically with file mode `0600`.

`XIAOYUZHOU_ACCESS_TOKEN` is still supported and takes precedence when already present.

Never commit or paste access tokens, refresh tokens, or device IDs into issues, chat, screenshots, docs, or Git history.

## Resolver policy

Fail closed:

- one exact episode-title match → `EXACT`
- multiple exact matches → `AMBIGUOUS`
- fuzzy/keyword-only results → never auto-select
- optional exact podcast title can narrow same-name episodes

The first smoke test intentionally validates title → episode URL before any Feishu runtime integration.

## Local smoke

After pulling the baseline and activating `.venv`:

```bash
python scripts/podcast_smoke.py "触屏时代的触觉饥渴" --podcast "随机波动StochasticVolatility"
```

Or point to a one-off private refresh-token file:

```bash
python scripts/podcast_smoke.py \
  "触屏时代的触觉饥渴" \
  --podcast "随机波动StochasticVolatility" \
  --refresh-token-file ~/.config/douban-weread/xiaoyuzhou_refresh_token
```

Expected successful shape:

```text
EXACT · <episode title> · <podcast> · <published time>
https://www.xiaoyuzhoufm.com/episode/<eid>
Read-only resolve completed. No Xiaoyuzhou state was modified.
```

Do not wire this into Feishu until a real local search successfully resolves at least one known episode to the same Xiaoyuzhou episode page visible in the app/web share flow.
