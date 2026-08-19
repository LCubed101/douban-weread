# PIT-015 — Multi-line Python pasted into zsh one line at a time

## Symptom

A diagnostic Python snippet was intended to run as one complete heredoc block, but only the Python body was pasted into the shell. zsh then tried to execute Python statements as shell commands and produced errors such as:

```text
zsh: command not found: import
zsh: command not found: from
function>
zsh: parse error near `)'
zsh: command not found: PY
```

## Diagnosis

The Python interpreter never started. The errors came from zsh itself.

A heredoc such as:

```bash
python3 - <<'PY'
...
PY
```

is one shell command. The opening `python3 - <<'PY'` line and the closing `PY` delimiter are required. Pasting only the Python lines makes zsh interpret them as shell syntax.

## Root cause

Contributor instructions relied on a multi-line embedded Python diagnostic. This is easy to copy partially, especially when following terminal instructions step by step.

## Resolution

The project now provides a dedicated safe CLI diagnostic:

```bash
douban-weread auth diagnose
```

It performs no network request and prints only structural information:

- input format classification
- parsed cookie count
- whether `dbcl2` is present
- whether `ck` is present
- whether the input is ready for `auth check`

It never prints Cookie values.

## Prevention / documentation rule

For routine contributor workflows:

- prefer a project CLI command over ad-hoc embedded Python;
- if a heredoc is unavoidable, label the entire block as one executable command;
- do not present the Python body separately as something to paste line by line;
- keep secret diagnostics value-safe by design.

## General lesson

**If a diagnostic is likely to be used more than once, promote it into the CLI instead of making contributors reproduce a fragile multi-line snippet.**
