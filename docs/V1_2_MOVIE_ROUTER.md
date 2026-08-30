# V1.2 Movie Router

V1.2 extends the existing recommendation router from books to Film / TV while preserving a narrow product boundary.

## Goal

```text
Screenshot / text
→ identify Film / TV title
→ resolve the exact Douban Movie subject
→ mark it Want-to-Watch (想看)
```

Books remain unchanged:

```text
Book → Douban Want-to-Read → WeRead availability
Film / TV → Douban Want-to-Watch
```

## First engineering slice

This slice intentionally does **not** connect Film / TV to the Feishu bot yet. It establishes and tests the provider boundary first:

- `DoubanMovieSearchClient`: read-only `movie.douban.com` search + subject parsing.
- `DoubanMovieResolver`: fail-closed exact title / alias resolution.
- `DoubanMovieInterestClient`: authenticated `想看` write on `movie.douban.com`, with explicit confirmation and post-write verification.

## Safety rules

- Never route movie writes through `book.douban.com`.
- Auto-select only one exact title or exact alias match.
- Same-name remakes / adaptations remain ambiguous.
- A write requires `confirmed=True` after the exact movie subject has been selected.
- After writing `wish`, read the Movie interest endpoint again and verify the persisted state.
- Captcha, login redirects, auth failures, and unexpected responses fail closed.

## Next slice

After a real local read/write validation with the user's own Douban Cookie succeeds:

1. Add Film / TV mention extraction to the Feishu input layer.
2. Add a compact ambiguous-title selection card (year / type / director).
3. Selecting a candidate becomes the single confirmation and directly writes `想看`.
4. Support mixed screenshots containing both books and Film / TV entities.
