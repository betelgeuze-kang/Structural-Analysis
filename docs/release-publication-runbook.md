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

## Path A: GitHub Actions UI

1. Open the `Publish Release Assets` workflow in GitHub Actions and run `workflow_dispatch`.
2. Leave `replace_existing` as `false` unless the release already has same-named assets that you intend to replace.
3. Set `promote_manifest=true` only when you want the workflow to commit the verified candidate manifest after its built-in closure checks pass.
4. The workflow already performs source-boundary preflight, fresh candidate generation, upload-plan validation, publication, `fetch_github_release_assets.py`, `check_release_asset_listing.py`, `check_release_p0_closure.py`, `check_p0_closure_status.py`, evidence upload, and optional manifest promotion.
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

## Path B: Token-Backed CLI

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
python3 scripts/check_release_asset_listing.py --manifest <candidate-manifest.json> --assets-json <release-assets.json> --require-all
```

7. Close the P0-1 gate:

```bash
python3 scripts/check_release_p0_closure.py --manifest <candidate-manifest.json> --assets-json <release-assets.json> --artifact-root <fresh-root> --tag-ref-present true --require-all --fail-unclosed
```

8. Confirm overall P0 status:

```bash
python3 scripts/check_p0_closure_status.py --manifest <candidate-manifest.json> --release-assets-json <release-assets.json> --artifact-root <fresh-root> --tag-ref-present --fail-open
```

Note: `check_release_p0_closure.py` expects `--tag-ref-present true`, while `check_p0_closure_status.py` uses `--tag-ref-present` as a flag.

## Completion Criteria

P0-1 is closed only when all of these are true:

- `fetch_github_release_assets.py` succeeds for the release tag.
- `check_release_asset_listing.py --require-all` reports no missing required assets and no size mismatches.
- `verify_release_artifacts_manifest.py --artifact-root <fresh-root> --require-artifacts` reports clean artifact-root SHA/bytes integrity.
- `check_release_p0_closure.py --tag-ref-present true --require-all --fail-unclosed` reports closed.
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
