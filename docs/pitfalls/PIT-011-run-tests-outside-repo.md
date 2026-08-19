# PIT-011 — Running Git/tests from the wrong working directory

## Symptom

A new terminal opened in the user's home directory (`~`) and the following commands were run immediately:

```bash
git fetch origin
git checkout -b agent/douban-wish-action origin/agent/douban-wish-action
python3 -m unittest discover -s tests -v
```

Git failed with:

```text
fatal: not a git repository (or any of the parent directories): .git
```

Then `unittest` reported unrelated failures such as:

```text
.../site-packages/tests/test_cli.py
ModuleNotFoundError: No module named 'pytest'
```

## Root cause

The shell was still in `~`, not inside the `douban-weread` repository.

Because there was no local project `tests/` directory at the expected path, Python test discovery resolved/imported an unrelated installed package named `tests` from `site-packages`. Those failures had nothing to do with `douban-weread`.

## Diagnosis

Check the current directory before repository-specific commands:

```bash
pwd
```

Expected project path on the validated Mac:

```text
/Users/ludao/douban-weread
```

Also verify the repository root:

```bash
git rev-parse --show-toplevel
```

## Resolution

Enter the repository and reactivate its virtual environment before fetching, switching branches, or running tests:

```bash
cd ~/douban-weread
source .venv/bin/activate
git fetch origin
git switch agent/douban-wish-action 2>/dev/null || git switch -c agent/douban-wish-action --track origin/agent/douban-wish-action
python3 -m unittest discover -s tests -v
```

## Prevention

Contributor instructions that start from a fresh terminal should include the repository entry step explicitly:

```bash
cd ~/douban-weread
source .venv/bin/activate
```

Do not interpret test failures from `.../site-packages/tests/...` as project failures unless the project intentionally imports those tests.

A useful preflight is:

```bash
pwd
git branch --show-current
which python3
```

The prompt should normally show both the project directory and the active environment, e.g.:

```text
(.venv) ... douban-weread %
```
