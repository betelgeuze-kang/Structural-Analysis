# Ignored test experiment cleanup

`implementation/phase1/experiments/by_test/` contains ignored, reproducible
runtime output. It is not current product authority and must not be mixed with
the tracked release-evidence tree.

Preview cleanup without deleting anything:

```bash
python scripts/prune_ignored_test_experiments.py --json
```

The default policy preserves the two newest timestamped runs for every test
gate and any run named by `latest_manifest.json`. A plan is blocked when:

- the experiment root is not ignored or contains tracked files;
- a latest manifest is malformed or points outside its gate;
- a timestamped run is a symlink; or
- any experiment activity occurred in the previous five minutes.

Apply only a newly generated ready plan:

```bash
python scripts/prune_ignored_test_experiments.py --apply --json
```

Application rechecks Git safety, global experiment activity, every candidate
path, byte count, and modification timestamp before the first deletion. A new
run or late write after planning blocks the entire operation. Deleted runs are
not recoverable from Git because the tree is intentionally ignored, but every
deleted directory is reproducible by its owning test. Tracked
`implementation/phase1/release_evidence/` artifacts and local virtual
environments are outside this cleanup scope.
