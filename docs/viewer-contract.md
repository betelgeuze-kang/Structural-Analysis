# Viewer Contract

This repository keeps two viewer surfaces intentionally separate: repo-local source viewers for development and QA, and generated release viewers for delivery.

## Source Viewers

Source viewers live under `src/structure-viewer/` and are intended for local development, QA, and deterministic rebuilds from a clean clone.

- They may depend on repo-local vendor files such as `src/structure-viewer/vendor/three.module.js`.
- They may read committed `.data.js` sidecars that travel with the source viewer shell.
- The 3D source viewer keeps reusable browser/selection/provenance/real-drawing quality/rendering/stat summary helpers in ESM sidecars such as `viewer-real-drawing-browser-state.js`, `viewer-real-drawing-quality.js`, `viewer-real-drawing-panel-events.js`, `viewer-real-drawing-panel-model.js`, `viewer-real-drawing-panel-renderer.js`, `viewer-real-drawing-selection.js`, `viewer-real-drawing-tree-model.js`, `viewer-search-results-model.js`, `viewer-selection-summary-model.js`, `viewer-provenance-model.js`, `viewer-side-panel-model.js`, `viewer-stats-summary.js`, and `viewer-shared-selection-state.js`; release generators must inline those helpers for single-file delivery.
- They should remain runnable without downloading GitHub Release assets.
- They are validated by `python scripts/verify_structure_viewer_contracts.py`, the PR/full quality gates, `npm run verify:frontend-contract`, `npm run verify:frontend-browser-smoke`, and the frontend build.

## Generated Release Viewers

Generated viewers are delivery artifacts produced by the phase1 generators and listed in `implementation/phase1/release_artifacts_manifest.json`.

- They are treated as GitHub Release assets, not source-controlled files.
- They should be self-contained single-file viewers or packaged with an explicit registry/package manifest.
- Their integrity is represented by manifest `sha256` and `bytes` fields.
- Release verification runbook:
  1. Source CI: run `python3 scripts/verify_release_artifacts_manifest.py --manifest implementation/phase1/release_artifacts_manifest.json --structure-only` to validate manifest structure only.
  2. Metadata preflight: run `python3 scripts/fetch_github_release_assets.py --repo <owner/name> --tag <release-tag> --out <release-assets.json>` to export release asset metadata, then run `python3 scripts/check_release_asset_listing.py --manifest implementation/phase1/release_artifacts_manifest.json --assets-json <release-assets.json> --require-all --require-exact`.
  3. Fresh candidate root: run `python3 scripts/build_release_publication_candidate.py --manifest implementation/phase1/release_artifacts_manifest.json --artifact-root <root> --work-dir <private-work-dir> --manifest-out <candidate-manifest.json> --write`. The private work dir contains signing keys; the flat artifact root contains only uploadable manifest assets.
  4. Full integrity: run `python3 scripts/verify_release_artifacts_manifest.py --manifest <candidate-manifest.json> --artifact-root <root> --require-artifacts` to verify SHA/bytes integrity for the current manifest-listed assets, then write source-root metadata evidence with `python3 scripts/verify_release_artifacts_manifest.py --manifest <candidate-manifest.json> --artifact-root <root> --hydrate-preflight --out <metadata-preflight.json>`.
  5. Upload plan: run `python3 scripts/prepare_release_upload_plan.py --manifest <candidate-manifest.json> --artifact-root <root> --out <release-upload-plan.json>` and upload only the `upload_assets` entries. With `GITHUB_TOKEN` or `GH_TOKEN` set, `python3 scripts/publish_github_release_assets.py --repo betelgeuze-kang/Structural-Analysis --manifest <candidate-manifest.json> --artifact-root <root> --assets-out <release-assets.json>` creates/updates the GitHub Release and uploads exactly those files. Without a local token, use the `Publish Release Assets` GitHub Actions workflow so the token-backed publication happens inside GitHub Actions.
  6. Published-byte hydrate: run `python3 scripts/hydrate_github_release_assets.py --repo betelgeuze-kang/Structural-Analysis --manifest <candidate-manifest.json> --artifact-root <hydrated-root> --write --out <post-publish-roundtrip.json>`, then `python3 scripts/verify_release_artifacts_manifest.py --manifest <candidate-manifest.json> --artifact-root <hydrated-root>` to verify the actual GitHub Release bytes.
  7. Closure gate: run `python3 scripts/check_release_p0_closure.py --manifest <candidate-manifest.json> --assets-json <release-assets.json> --artifact-root <root> --upload-plan-json <release-upload-plan.json> --metadata-preflight-json <metadata-preflight.json> --post-publish-roundtrip-json <post-publish-roundtrip.json> --tag-ref-present true --require-all --require-exact --fail-unclosed`.
  8. Overall P0 status: run `python3 scripts/check_p0_closure_status.py --manifest <candidate-manifest.json> --release-assets-json <release-assets.json> --artifact-root <root> --upload-plan-json <release-upload-plan.json> --metadata-preflight-json <metadata-preflight.json> --post-publish-roundtrip-json <post-publish-roundtrip.json> --tag-ref-present --fail-open` to combine P0-1 release publication with P0-2..P0-6 core evidence.
  9. Promote manifest: after the GitHub Release asset listing and SHA/bytes checks pass, promote `<candidate-manifest.json>` into `implementation/phase1/release_artifacts_manifest.json` in a separate source commit.
  10. Published status: `structural-analysis-artifacts-2026-04-26` must match exactly the current 22 manifest-listed assets. Keep repo-local `implementation/phase1/release/` out of the upload path; use the release asset listing, upload plan, metadata preflight, post-publish round-trip JSON, and hydrated published-byte SHA/bytes checks as the delivery contract.
- P1 handoff: with P0-1 closed, run `python3 scripts/check_p1_readiness_status.py --p0-status <p0-status.json> --json --out <p1-readiness-status.json> --out-md <p1-readiness-status.md> --fail-blocked`, then `python3 scripts/check_p1_benchmark_breadth_status.py --p1-readiness-status <p1-readiness-status.json> --json --out <p1-benchmark-breadth-status.json> --out-md <p1-benchmark-breadth-status.md> --fail-blocked`, and finally `python3 scripts/materialize_p1_operational_queues.py --p1-benchmark-breadth-status <p1-benchmark-breadth-status.json> --json --out <p1-operational-queues.json> --out-md <p1-operational-queues.md> --fail-open` to move into the P1 quality/fallback/benchmark breadth slice with external submission receipts and residual holdout closure packet templates visible.
- Verification split: manifest structure, release asset listing, local fresh-root SHA/bytes, and published-byte hydrate checks are scriptable; fresh artifact root regeneration and GitHub Release publication require a token-backed publishing step.
- Do not wildcard-upload the repo-local `implementation/phase1/release/` tree; publish only manifest-listed assets from a freshly regenerated asset root.

## Repository Exclusions

`scripts/check_repo_hygiene.py` defines the source-repo boundary for generated and unsafe files.

- After a full `pytest`, run `python3 scripts/check_generated_worktree_clean.py --show-ok` as the `generated worktree clean` check before committing. If it fails, run `python3 scripts/report_worktree_drift.py` to confirm the generated/asset/source split, then run `python3 scripts/report_worktree_drift.py --json --fail-on-source --fail-on-other` as the no-write cleanup gate. Only after approval, use `--write-pathspec-dir` to write category pathspec files, then `python3 scripts/verify_worktree_cleanup_plan.py --pathspec-dir <dir>` to confirm the pathspec still matches the current worktree. Only treat the drift as cleanup when `source_changes` is `0`, and keep generated cleanup and user-owned asset deletion in separate approvals and separate commits. It should pass in clean clone/CI. It only checks tracked generated paths under `implementation/phase1/open_data/`, `implementation/phase1/stress/`, and `implementation/phase1/panel_zone_solver_verified_*.json`, so keep user source edits or intentional deletions elsewhere in the normal commit path. If the diff includes a user-owned asset deletion outside those tracked paths, confirm that separately before restoring or removing anything.
- Private signing keys (`*.pem` except public keys) stay out of Git.
- Large raw datasets remain outside the source repo boundary: tracked stress/workspace/output/rust target artifacts have been removed from Git tracking, and 25MiB+ open-data artifacts are represented by `implementation/phase1/open_data_external_artifacts_manifest.json`.
- Generated release folders under `implementation/phase1/release/`, repeat experiment archives under `implementation/phase1/experiments/`, and scratch data under `tmp/` stay out of Git.
- Build outputs such as `node_modules/` and `dist/` are also excluded.

## Shared Selection And Provenance Keys

Viewer handoff links should use the same semantic keys across 3D, charts, panel-zone, and optimization-history surfaces.

- `member`: primary structural member identifier.
- `load_case`: load case identifier.
- `combination`: governing load or design combination identifier.
- `focus_member`: member to focus or restore in the target viewer.

When both `member` and `focus_member` are present, `focus_member` controls the restored viewport and `member` remains the provenance anchor.
