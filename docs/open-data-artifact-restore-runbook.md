# Open-Data Artifact Restore Runbook

This runbook prepares P1 heavy validation without pulling large raw data back
into Git.

## Current Boundary

The source repository keeps large open-data artifacts outside Git. Their target
paths, byte counts, SHA-256 digests, and source families are recorded in
`implementation/phase1/open_data_external_artifacts_manifest.json`.

The restore target is always the original path under
`implementation/phase1/open_data/`. The preferred cache layout is:

```text
<cache-root>/<source_family>/<sha256>/<basename>
```

This layout avoids filename collisions and lets duplicate artifacts share the
same checksum record.

## Plan A Restore

1. Validate the manifest structure:

```bash
python3 scripts/verify_open_data_external_artifacts_manifest.py --manifest implementation/phase1/open_data_external_artifacts_manifest.json --structure-only
```

2. Build a restore plan against a local artifact cache:

```bash
python3 scripts/plan_open_data_artifact_restore.py --cache-root <cache-root> --json --out <restore-plan.json>
```

3. If the plan has blocked artifacts, fetch those files from the approved
GitHub Release asset set or source-family artifact cache. Do not commit them to
Git.

4. After placing cache files in the expected layout, rerun:

```bash
python3 scripts/plan_open_data_artifact_restore.py --cache-root <cache-root> --fail-unready
```

5. Copy only cache-ready files to their original paths when running heavy
validation locally. The JSON plan includes a `restore_command` per row.

6. Verify the restored files before running heavy validation:

```bash
python3 scripts/verify_open_data_external_artifacts_manifest.py --manifest implementation/phase1/open_data_external_artifacts_manifest.json --require-artifacts
```

## Guardrails

- Do not commit restored raw data.
- Do not place private or licensed raw files into release assets without a
document-level redistribution review.
- Do not weaken SHA/bytes checks to make a heavy run pass.
- If a cache file has the right name but a wrong digest, treat it as the wrong
artifact and fetch it again from the approved source.

## Completion Signal

The heavy-validation environment is ready when:

- `plan_open_data_artifact_restore.py --cache-root <cache-root> --fail-unready`
  exits `0`.
- `verify_open_data_external_artifacts_manifest.py --require-artifacts` exits
  `0` after restoring files to their original paths.
- `scripts/check_repo_hygiene.py --strict-source-boundary` still passes before
  committing any source changes.
