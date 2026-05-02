# Release Publication Runbook

This runbook closes P0-1 release publication for `structural-analysis-artifacts-2026-04-26`.

## Current Open State

As of 2026-04-30, P0-1 is still open for one reason:

- The Git tag exists.
- The GitHub Release object is not yet published.
- The manifest lists 12 release assets, and those 12 assets are not yet visible on the release.
- The repo-local `implementation/phase1/release/` tree is stale and is not a safe upload source.

This is a release-publication gap, not a source-boundary gap. P0-2 through P0-6 are already closed, and P0 stays open until release publication closes.

## Guardrails

- Never wildcard-upload `implementation/phase1/release/`.
- Never use the stale repo-local release tree as the publication source.
- Only upload manifest-listed files from a freshly regenerated flat artifact root.
- Do not promote `implementation/phase1/release_artifacts_manifest.json` until the release asset listing and SHA/bytes checks pass.
- P0-1 must close before P1 breadth work starts.

## P0 Nightly Heavy Report Contract

- `implementation/phase1/release/nightly_release_gate_report.json` is the canonical nightly heavy report for P0 publication runs.
- `Nightly release gate summary:` is the triage contract for `Regenerate release viewer artifacts`; treat its `reason_code`, `reason`, first failed step, and captured tails as authoritative.
- The `release-publication-evidence` artifact must include the nightly heavy report together with the candidate manifest, release asset listing, upload plan, and closure status.
- KDS/frontend compliance must not depend on stale repo-local `implementation/phase1/release/**` files. The nightly gate rebuilds `pbd_review_package_report.json` from checked-in NDTHA evidence and rebuilds `pbd_review_compliance_slice_report.json` from the small source evidence under `implementation/phase1/release_evidence/kds/` before running the KDS gate.
- Reused reports that publish sidecar evidence must verify those sidecars exist. For example, `commercial_csv_gate_report.json` is not reusable for release publication unless `implementation/phase1/member_force_soft_accept_report.json` has also been materialized in the same checkout.
- GPU-only solver HIP e2e evidence is not regenerated on CPU-required GitHub runners. Those runners materialize `implementation/phase1/release_evidence/gpu/solver_hip_e2e_contract_report.json`; refreshing that evidence remains a GPU-capable validation task.

## GitHub Release Asset Hydrate Flow

"Hydrate" here has two explicit meanings:

- Before publication, materialize a fresh flat upload root from regenerated release outputs and a private work dir, not from the stale repo-local `implementation/phase1/release/` tree.
- After publication, download the published GitHub Release assets into a separate hydrated root with `hydrate_github_release_assets.py` and verify SHA/bytes against the candidate manifest.

1. Fetch release asset metadata with `fetch_github_release_assets.py` so the hydrate run starts from the published release state.
2. Build a fresh candidate manifest and flat root with `build_release_publication_candidate.py`.
3. Verify the hydrated root with `verify_release_artifacts_manifest.py --require-artifacts` and the upload plan with `prepare_release_upload_plan.py`.
4. Publish only manifest-listed files, then re-fetch the release assets and check metadata with `check_release_asset_listing.py`.
5. Download the published assets with `hydrate_github_release_assets.py --write` into a separate root and run `verify_release_artifacts_manifest.py --artifact-root <hydrated-root>` so the release is byte-verified from GitHub, not just locally generated.
6. Close P0 with `check_release_p0_closure.py` and `check_p0_closure_status.py`.

## Retry Checklist

When a publication run fails, rerun the same publication path instead of changing code:

1. Re-dispatch `Publish Release Assets` from the GitHub Actions UI, or use `python3 scripts/dispatch_release_publish_workflow.py --dry-run --json` followed by `GITHUB_TOKEN=<token> python3 scripts/dispatch_release_publish_workflow.py --json`.
2. If GitHub shows a `Node20` warning, treat it as a workflow-runtime warning. The publication result is still decided by the step exit code and the release evidence artifact.
3. If the run fails in `Regenerate release viewer artifacts`, open the log block that starts with `Nightly release gate summary:`. That block prints `reason_code`, `reason`, the first failed step, and the captured `stdout_tail` / `stderr_tail`.
4. Download the `release-publication-evidence` artifact from the failed run and inspect `implementation/phase1/release/nightly_release_gate_report.json` inside it.
5. Fix the failed gate, then rerun the workflow with the same inputs. Use `replace_existing=true` only when same-named assets should be replaced, and use `promote_manifest=true` only after the closure checks pass.

## Path A: GitHub Actions UI

1. Open the `Publish Release Assets` workflow in GitHub Actions and run `workflow_dispatch`.
2. Leave `replace_existing` as `false` unless the release already has same-named assets that you intend to replace.
3. Set `promote_manifest=true` only when you want the workflow to commit the verified candidate manifest after its built-in closure checks pass.
4. The workflow already performs source-boundary preflight, fresh candidate generation, upload-plan validation, publication, `fetch_github_release_assets.py`, `check_release_asset_listing.py`, `check_release_p0_closure.py`, `check_p0_closure_status.py`, published-asset hydration with SHA/bytes verification, evidence upload, and optional manifest promotion.
5. Download the publication evidence artifact after the workflow finishes; it contains the candidate manifest, release asset listing, upload plan, and overall P0 closure status.
6. If the workflow fails, stop at the first failed gate and fix that gate before rerunning.

## Path A-CLI: Dispatch The Workflow

Use this path when you have a token that can trigger Actions but want GitHub Actions to do the actual release publication with its own `GITHUB_TOKEN`.

1. Write a dry-run dispatch plan:

```bash
python3 scripts/dispatch_release_publish_workflow.py --dry-run --json --out <dispatch-plan.json>
```

2. Dispatch the workflow:

```bash
GITHUB_TOKEN=<token> python3 scripts/dispatch_release_publish_workflow.py --json
```

3. Check recent workflow runs:

```bash
GITHUB_TOKEN=<token> python3 scripts/dispatch_release_publish_workflow.py --status --json --out <workflow-runs.json>
```

4. Add `--promote-manifest` only when you want the workflow to commit the verified candidate manifest after its built-in closure checks pass.
5. Use `--replace-existing` only if a previous partial run created same-named assets and replacement is intended.
6. If the dispatch command reports missing token, either set `GITHUB_TOKEN` or `GH_TOKEN`, or run the workflow manually in the GitHub Actions UI.

## Path B: Token-Backed Hydrate Flow

1. Check the source manifest structure:

```bash
python3 scripts/verify_release_artifacts_manifest.py --manifest implementation/phase1/release_artifacts_manifest.json --structure-only
```

2. Build a fresh publication candidate outside the repo-local release tree:

```bash
python3 scripts/build_release_publication_candidate.py --manifest implementation/phase1/release_artifacts_manifest.json --artifact-root <fresh-root> --work-dir <private-work-dir> --manifest-out <candidate-manifest.json> --write
```

3. Verify the candidate against the fresh artifact root:

```bash
python3 scripts/verify_release_artifacts_manifest.py --manifest <candidate-manifest.json> --artifact-root <fresh-root> --require-artifacts
```

4. Build the safe upload plan and stop if it reports extra files:

```bash
python3 scripts/prepare_release_upload_plan.py --manifest <candidate-manifest.json> --artifact-root <fresh-root> --out <release-upload-plan.json>
```

5. Publish with a token:

```bash
python3 scripts/publish_github_release_assets.py --repo <owner/name> --manifest <candidate-manifest.json> --artifact-root <fresh-root> --assets-out <release-assets.json>
```

6. Fetch the GitHub Release asset listing and compare it to the manifest:

```bash
python3 scripts/fetch_github_release_assets.py --repo <owner/name> --tag <release-tag> --out <release-assets.json>
python3 scripts/check_release_asset_listing.py --manifest <candidate-manifest.json> --assets-json <release-assets.json> --require-all --require-exact
```

7. Hydrate the published GitHub Release assets and verify release-side SHA/bytes:

```bash
python3 scripts/hydrate_github_release_assets.py --repo <owner/name> --manifest <candidate-manifest.json> --artifact-root <hydrated-release-root> --write
python3 scripts/verify_release_artifacts_manifest.py --manifest <candidate-manifest.json> --artifact-root <hydrated-release-root>
```

8. Close the P0-1 gate:

```bash
python3 scripts/check_release_p0_closure.py --manifest <candidate-manifest.json> --assets-json <release-assets.json> --artifact-root <fresh-root> --tag-ref-present true --require-all --require-exact --fail-unclosed
```

9. Confirm overall P0 status:

```bash
python3 scripts/check_p0_closure_status.py --manifest <candidate-manifest.json> --release-assets-json <release-assets.json> --artifact-root <fresh-root> --tag-ref-present --fail-open
```

Note: `check_release_p0_closure.py` expects `--tag-ref-present true`, while `check_p0_closure_status.py` uses `--tag-ref-present` as a flag.

## Post-Success Status Order

After a successful publication rerun, capture the P0 status first and then check P1 in order:

1. Run `python3 scripts/check_p0_closure_status.py --manifest <candidate-manifest.json> --release-assets-json <release-assets.json> --artifact-root <fresh-release-asset-root> --tag-ref-present --json --out <p0-status.json> --out-md <p0-status.md> --fail-open`.
2. If that reports closed, run `python3 scripts/check_p1_readiness_status.py --p0-status <p0-status.json> --json --out <p1-readiness-status.json> --out-md <p1-readiness-status.md> --fail-blocked`.
3. If P1 readiness is unblocked, run `python3 scripts/check_p1_benchmark_breadth_status.py --p1-readiness-status <p1-readiness-status.json> --json --out <p1-benchmark-breadth-status.json> --out-md <p1-benchmark-breadth-status.md> --fail-blocked`.

## Completion Criteria

P0-1 is closed only when all of these are true:

- `fetch_github_release_assets.py` succeeds for the release tag.
- `check_release_asset_listing.py --require-all --require-exact` reports no missing required assets, no missing optional assets, no size mismatches, and no extra assets.
- `verify_release_artifacts_manifest.py --artifact-root <fresh-root> --require-artifacts` reports clean artifact-root SHA/bytes integrity.
- `hydrate_github_release_assets.py --write` can download the published GitHub Release assets into a separate root, and `verify_release_artifacts_manifest.py --artifact-root <hydrated-root>` reports clean SHA/bytes integrity against the downloaded bytes.
- `check_release_p0_closure.py --tag-ref-present true --require-all --require-exact --fail-unclosed` reports closed.
- `check_p0_closure_status.py --manifest <candidate-manifest.json> --release-assets-json <release-assets.json> --artifact-root <fresh-root> --tag-ref-present --fail-open` reports overall P0 closed. The `Publish Release Assets` workflow also writes `structural-p0-closure-status.json` and `structural-p0-closure-status.md` into the publication evidence artifact.
- The release contains exactly the 12 manifest-listed assets and no wildcard-uploaded extras.
- Only after that may the candidate manifest be promoted and P1 breadth work begin.

## Troubleshooting

- Missing token: `publish_github_release_assets.py` fails with a missing-token error. Set `GITHUB_TOKEN` or `GH_TOKEN`, or use the GitHub Actions workflow.
- Release not found: `fetch_github_release_assets.py` returns 404 when the release object is missing, the tag is not visible, the repo is wrong, or auth is insufficient. Verify the repo/tag and push the tag.
- Duplicate assets: `publish_github_release_assets.py` stops if the release already has same-named manifest assets. Use `--replace-existing` or workflow `replace_existing=true` only when replacement is intended.
- SHA/bytes mismatch: rebuild the fresh root and rerun `build_release_publication_candidate.py` plus `verify_release_artifacts_manifest.py`. A mismatch usually means stale local state or a manifest that no longer matches the candidate bytes.
- Stale local release tree: treat `implementation/phase1/release/` as stale. If `prepare_release_upload_plan.py` reports `extra_files`, do not upload that root.

## After P0-1

Do not start P1 breadth work until this runbook closes P0-1 and `check_p0_closure_status.py` reports closed. After that, the next order is P1 breadth, then later viewer/report polish.
