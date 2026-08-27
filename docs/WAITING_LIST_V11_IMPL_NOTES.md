Implementation target:

- Persist unavailable/not-found multi-book results.
- `waiting` exact known unavailable: recheck in 30 days.
- `not_found`: recheck in 90 days.
- Do not query every background-loop wake; query only due rows.
- Preserve existing notification behavior when a book becomes readable.
