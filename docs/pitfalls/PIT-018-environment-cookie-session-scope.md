## PIT-018 — `DOUBAN_COOKIE` exists only in the current shell environment

### Symptom

Unit tests pass, but a live authenticated command such as:

```bash
douban-weread inspect --subject 25837854 --limit 20
```

fails immediately with:

```text
Douban inspect error: DOUBAN_COOKIE is not set.
```

### Environment

- macOS
- zsh
- Python virtual environment
- `DOUBAN_COOKIE` intentionally supplied with `read -s` + `export`

### Diagnosis

The command fails before authenticated provider access because the current process environment does not contain `DOUBAN_COOKIE`.

A successful auth check in an earlier terminal/shell does not imply that a later shell still has the variable. Shell environment variables are process/session scoped unless the user deliberately configures persistence.

Git branch switching by itself is not evidence that the variable was cleared; the important check is whether the current shell still exports it.

### Root cause

`DOUBAN_COOKIE` is intentionally not persisted by the project. If the terminal/session changes, or the variable is unset, subsequent authenticated commands cannot access the browser session credential.

### Resolution

Re-inject the Cookie locally in the current shell without echoing it:

```bash
read -s "DOUBAN_COOKIE?Paste ONLY Cookie value: "; export DOUBAN_COOKIE; echo
```

Then verify structure without printing secret values:

```bash
douban-weread auth diagnose
```

Only continue when `Ready for auth check: True`.

### Prevention / test

- Keep secrets local and ephemeral by default.
- Do not store real Cookies in the repository, documentation, shell history, issues, PRs, or chat.
- When starting a new shell/session, treat authenticated commands as requiring credential re-injection.
- Prefer `auth diagnose` before a live authenticated workflow when shell continuity is uncertain.
- A missing environment variable should fail before any network mutation attempt.
