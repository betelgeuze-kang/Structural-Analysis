# Source Boundary Restore Runbook

This repo keeps source-boundary cleanup non-destructive by default. Do not rewrite history, delete local source artifacts, or run `git rm --cached` during the normal PR gate.

## PR Gate Contract

- Run `python3 scripts/plan_source_boundary_cleanup.py --large-file-threshold-mib 10 --allowlist-manifest implementation/phase1/source_boundary_allowlist.json --fail-on-candidates`.
- Run `python3 scripts/report_source_boundary_footprint.py --check`.
- Unknown large/generated/private artifacts must fail the gate until they are removed from the source boundary or explicitly classified in the allowlist.
- Approved large tracked artifacts must stay classified as `source_required`, `release_asset`, or `external_restore`.

## Restore Policy

- `source_required` artifacts are kept because tests or offline viewer contracts consume them directly.
- `external_restore` artifacts remain tracked for the current branch, but the release path should prefer manifest hydration or a documented external source when practical.
- `generated_remove_candidate` may be proposed by a cleanup plan, but removal requires a separate explicit change request.

## Operator Steps

1. Inspect the footprint report and source-boundary cleanup plan.
2. For every new candidate, decide whether it is source-required, release-restorable, or generated output.
3. Update only the allowlist/runbook/manifest in normal PRs.
4. Keep local files intact unless a separate destructive cleanup task is approved.
