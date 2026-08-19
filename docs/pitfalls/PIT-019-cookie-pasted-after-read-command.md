## PIT-019 — Cookie pasted after `read -s` completed

### Symptom

After running:

```bash
read -s "DOUBAN_COOKIE?Paste ONLY Cookie value: "; export DOUBAN_COOKIE; echo
```

the shell returned to the normal prompt, and the Cookie text was then pasted again. zsh interpreted each semicolon-separated Cookie segment as a command, producing errors such as `zsh: command not found`.

Despite those shell errors, `douban-weread auth diagnose` still reported a valid Cookie header and `douban-weread auth check` succeeded.

### Environment

- macOS
- zsh
- Python virtual environment active
- `DOUBAN_COOKIE` supplied interactively with `read -s`

### Diagnosis

The first Cookie paste had already been consumed by `read -s` and exported successfully. The second paste occurred after the shell prompt had returned, so zsh treated the Cookie text as shell syntax. Semicolons split the text into separate shell commands.

### Root cause

The interactive `read -s` flow gives no visible feedback while the secret is being pasted. This makes it easy to paste once into the hidden prompt, press Enter, then paste the same value again at the normal shell prompt because the first paste was not visible.

### Resolution

Do not paste the Cookie again after the normal shell prompt returns. Confirm success with the value-safe command:

```bash
douban-weread auth diagnose
```

If it reports `Ready for auth check: True`, continue with `douban-weread auth check` without re-pasting the Cookie.

If a Cookie value is accidentally pasted into a chat, terminal transcript, screen recording, or other place that may be retained or shared, treat that session secret as exposed and replace the browser session before continuing.

### Prevention / test

- Prefer a single interactive secret-entry step followed immediately by `douban-weread auth diagnose`.
- Document the exact transition: **paste once → Enter → wait for normal prompt → do not paste again**.
- Never print the Cookie value for verification.
- Keep diagnostics structural only (`cookie_header`, parsed count, presence of `dbcl2` / `ck`).
