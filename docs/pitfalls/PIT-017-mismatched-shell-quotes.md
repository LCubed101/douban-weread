# PIT-017 — Smart quotes can leave zsh waiting at `dquote>`

## Symptom

A command such as:

```text
douban-weread search "荷马史诗：奥德赛“
```

caused zsh to show:

```text
dquote>
```

instead of running the command.

## Root cause

The opening quote was the ASCII shell delimiter `"`, while the closing character was a typographic Chinese/curly quote `“`. zsh therefore considered the ASCII double-quoted string unfinished and waited for a matching `"`.

## Resolution

Abort the unfinished command with `Ctrl+C`, then rerun using matching ASCII quotes:

```bash
douban-weread search "荷马史诗：奥德赛"
```

Single ASCII quotes are also safe:

```bash
douban-weread search '荷马史诗：奥德赛'
```

## Prevention

- Terminal examples should use plain ASCII `'` or `"` only.
- Avoid copying shell commands through rich-text editors that auto-convert quotes to smart quotes.
- When zsh shows `dquote>`, `quote>`, or a similar continuation prompt, inspect delimiters before assuming the application hung.
