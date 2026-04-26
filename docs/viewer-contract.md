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
- Their integrity is represented by manifest `sha256` and `bytes` fields, and the manifest can be checked against a download with `python3 scripts/verify_release_artifacts_manifest.py --manifest implementation/phase1/release_artifacts_manifest.json --artifact-root <downloaded-release-root>`.

## Repository Exclusions

`scripts/check_repo_hygiene.py` defines the source-repo boundary for generated and unsafe files.

- Private signing keys (`*.pem` except public keys) stay out of Git.
- Large raw datasets and workspace inputs are externalized instead of being tracked in the repo.
- Generated release folders under `implementation/phase1/release/`, repeat experiment archives under `implementation/phase1/experiments/`, and scratch data under `tmp/` stay out of Git.
- Build outputs such as `node_modules/` and `dist/` are also excluded.

## Shared Selection And Provenance Keys

Viewer handoff links should use the same semantic keys across 3D, charts, panel-zone, and optimization-history surfaces.

- `member`: primary structural member identifier.
- `load_case`: load case identifier.
- `combination`: governing load or design combination identifier.
- `focus_member`: member to focus or restore in the target viewer.

When both `member` and `focus_member` are present, `focus_member` controls the restored viewport and `member` remains the provenance anchor.
