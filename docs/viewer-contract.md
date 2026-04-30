# Viewer Contract

This repository keeps two viewer surfaces intentionally separate: repo-local source viewers for development and QA, and generated release viewers for delivery.

## Source Viewers

Source viewers live under `src/structure-viewer/` and are intended for local development, QA, and deterministic rebuilds from a clean clone.

- They may depend on repo-local vendor files such as `src/structure-viewer/vendor/three.module.js`.
- They may read committed `.data.js` sidecars that travel with the source viewer shell.
- They should remain runnable without downloading GitHub Release assets.
- They are validated by `npm run verify:frontend-contract`, `npm run verify:frontend-smoke`, and the frontend build.

## Generated Release Viewers

Generated viewers are delivery artifacts produced by the phase1 generators and listed in `implementation/phase1/release_artifacts_manifest.json`.

- They are treated as GitHub Release assets, not source-controlled files.
- They should be self-contained single-file viewers or packaged with an explicit registry/package manifest.
- Their integrity is represented by manifest `sha256` and `bytes` fields.
- Release verification runbook:
  1. Source CI: run `python3 scripts/verify_release_artifacts_manifest.py --manifest implementation/phase1/release_artifacts_manifest.json --structure-only` to validate manifest structure only.
  2. Metadata preflight: run `python3 scripts/fetch_github_release_assets.py --repo <owner/name> --tag <release-tag> --out <release-assets.json>` to export release asset metadata, then run `python3 scripts/check_release_asset_listing.py --manifest implementation/phase1/release_artifacts_manifest.json --assets-json <release-assets.json> --require-all`.
  3. Full integrity: download a fresh GitHub Release asset root for the manifest `release_tag`, then run `python3 scripts/verify_release_artifacts_manifest.py --manifest implementation/phase1/release_artifacts_manifest.json --artifact-root <root> --require-artifacts` to verify SHA/bytes integrity for the 12 manifest-listed assets.
  4. Upload plan: run `python3 scripts/prepare_release_upload_plan.py --manifest implementation/phase1/release_artifacts_manifest.json --artifact-root <root> --out <release-upload-plan.json>` and upload only the `upload_assets` entries.
  5. Current blocker: the tag/release may not exist yet, so P0-1 cannot close until the tag, release, and required assets are published.
- Do not wildcard-upload the repo-local `implementation/phase1/release/` tree; publish only manifest-listed assets from a freshly regenerated asset root.

## Repository Exclusions

`scripts/check_repo_hygiene.py` defines the source-repo boundary for generated and unsafe files.

- After a full `pytest`, run `python3 scripts/check_generated_worktree_clean.py --show-ok` as the `generated worktree clean` check before committing. If it fails, run `python3 scripts/report_worktree_drift.py` to confirm the generated/asset/source split, then run `python3 scripts/report_worktree_drift.py --json --fail-on-source --fail-on-other` as the no-write cleanup gate. Only after approval, use `--write-pathspec-dir` to write category pathspec files, then `python3 scripts/verify_worktree_cleanup_plan.py --pathspec-dir <dir>` to confirm the pathspec still matches the current worktree. Only treat the drift as cleanup when `source_changes` is `0`, and keep generated cleanup and user-owned asset deletion in separate approvals and separate commits. It should pass in clean clone/CI. It only checks tracked generated paths under `implementation/phase1/open_data/`, `implementation/phase1/stress/`, and `implementation/phase1/panel_zone_solver_verified_*.json`, so keep user source edits or intentional deletions elsewhere in the normal commit path. If the diff includes a user-owned asset deletion outside those tracked paths, confirm that separately before restoring or removing anything.
- Private signing keys (`*.pem` except public keys) stay out of Git.
- Large raw datasets, workspace inputs, and tracked stress/workspace/output/rust target paths are a P0 source-boundary item: build the 25MB+ data need inventory first, decide allowlist vs externalization, then remove/externalize in a separate commit.
- Generated release folders under `implementation/phase1/release/`, repeat experiment archives under `implementation/phase1/experiments/`, and scratch data under `tmp/` stay out of Git.
- Build outputs such as `node_modules/` and `dist/` are also excluded.

## Shared Selection And Provenance Keys

Viewer handoff links should use the same semantic keys across 3D, charts, panel-zone, and optimization-history surfaces.

- `member`: primary structural member identifier.
- `load_case`: load case identifier.
- `combination`: governing load or design combination identifier.
- `focus_member`: member to focus or restore in the target viewer.

When both `member` and `focus_member` are present, `focus_member` controls the restored viewport and `member` remains the provenance anchor.
