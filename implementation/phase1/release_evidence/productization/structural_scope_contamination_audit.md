# Structural Scope Contamination Audit

- `status`: `pass`
- `contract_pass`: `True`
- `non_structural_path_count`: `0`
- `non_structural_tracked_path_count`: `0`
- `non_structural_untracked_path_count`: `0`
- `quarantined_non_structural_path_count`: `0`
- `unquarantined_non_structural_path_count`: `0`
- `first_non_structural_path`: `none`
- `first_unquarantined_non_structural_path`: `none`
- `release_surface_text_leak_path_count`: `0`
- `owner_cleanup_closure_ready`: `True`
- `owner_cleanup_pending_path_count`: `0`
- `release_surface_owner_cleanup_pending_path_count`: `0`

## Quarantine

- `manifest_present`: `True`
- `manifest_path`: `implementation/phase1/release_evidence/productization/structural_scope_quarantine_manifest.json`
- `manifest_quarantined_path_count`: `86`

| Git State | Count |
|---|---:|

| Area | Count |
|---|---:|

| Family | Count |
|---|---:|

## Release Surface Text Guard

No guarded structural release surface text leaks detected.

## Owner Cleanup Closure

No owner cleanup closure blockers.

## Release Surface Quarantine Boundary

- `status`: `clean_structural_release_surface`
- `quarantined_release_surface_path_count`: `0`
- `quarantined_paths_claim_eligible`: `False`

No quarantined release-surface paths are currently skipped by the guard.

| Path | Git State | Area | Quarantine | Families | Tokens |
|---|---|---|---|---|---|

This audit protects the building structural-analysis product scope. It does not delete files; it identifies molecular, ligand, GPCR, PocketMD, and MD paths and requires either deletion/extraction or an exact quarantine manifest that excludes them from the structural release surface. Quarantined paths remain visible and must not be counted as structural solver release evidence.
