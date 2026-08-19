## PIT-021 — History title overwritten by purchase/price link

### Symptom

A live full history sync reported plausible non-zero counts and persisted 1747 records, but local title lookups for known books returned no candidates.

Direct SQLite inspection showed many rows like:

```text
wish  35307049  纸质版 46.60元
wish  26603828  纸质版 17.71元
wish  36636224  纸质版 22.90元
```

The Douban subject IDs and states were present, but the stored `title` was often a purchase-link label instead of the book title.

### Environment

- macOS
- Python 3.10
- `agent/douban-reading-history-index`
- authenticated read-only Douban Book history pages
- SQLite baseline version 2

### Diagnosis

Current Douban Book history list items use `li.subject-item`. One item can contain multiple anchors related to the same book, including:

- the canonical book title under `div.info > h2 > a`;
- later purchase / paper-book price links such as `纸质版 46.60元`.

The parser previously treated any `/subject/<id>/` anchor inside the list item as a possible title. A later price link could therefore overwrite the title already captured for the same subject ID.

A plausible total row count was not enough to detect this semantic corruption: pagination and subject discovery were correct while one field inside each row was wrong.

### Root cause

The parser used subject-link identity as a proxy for title-anchor identity.

That assumption is invalid because a single Douban list item can expose multiple subject-related links with different display text.

### Resolution

The parser now:

1. treats `li.subject-item > div.info > h2 > a` as the authoritative current Book title anchor;
2. keeps a conservative legacy `div.item` fallback;
3. never overwrites a captured title with a later subject-related anchor;
4. ignores purchase/price links for title extraction;
5. increments the SQLite baseline schema/version from 2 to 3 so the live baseline created with corrupted titles is automatically considered incomplete and must be rebuilt.

### Prevention / test

Regression coverage must include a realistic list item where both the title link and a later price link point to the same subject ID:

```html
<li class="subject-item">
  <div class="info">
    <h2><a href="/subject/123/">白夜行</a></h2>
    <a href="/subject/123/">纸质版 46.60元</a>
  </div>
</li>
```

Expected parsed title: `白夜行`.

Never validate a history ingestion layer from row counts alone. Live validation must include at least one semantic spot-check of stored titles and at least one positive local lookup for a book known to exist in the source history.
