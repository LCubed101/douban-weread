## PIT-024 — Command advertised before CLI wiring existed

### Symptom

After the WeRead shelf provider and local shelf index tests passed, the following commands were attempted:

```bash
douban-weread weread shelf sync
douban-weread weread shelf status
douban-weread weread shelf lookup "白夜行"
```

All three failed immediately with argparse reporting:

```text
invalid choice: 'shelf'
```

### Environment

Branch: `agent/weread-shelf-baseline`

The repository had 144 passing tests covering the existing project plus the new `/shelf/sync` provider and SQLite shelf baseline.

### Diagnosis

The provider and storage layers had landed, but no `weread shelf` CLI route existed yet. The passing test suite therefore proved only the implemented lower layers; it did not prove that the proposed user-facing commands were available.

### Root cause

A planned next-step CLI surface was presented as if it had already been implemented and smoke-tested.

This was a workflow/release-boundary mistake, not a user shell or installation problem.

### Resolution

Add a dedicated read-only `weread_shelf_cli` and route:

```text
douban-weread weread shelf sync
douban-weread weread shelf status
douban-weread weread shelf lookup <title>
```

through the top-level dispatcher. Add CLI and dispatcher regression tests before asking for another live shelf request.

### Prevention / test

Before sharing any new executable command with a user:

1. confirm the command is present in the actual installed dispatch path;
2. add a CLI/dispatch regression test, not only provider/storage tests;
3. run a no-network smoke test such as `--help` or a local-only subcommand;
4. distinguish clearly between “implemented now” and “planned next”.
