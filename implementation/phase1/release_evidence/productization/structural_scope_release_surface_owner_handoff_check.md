# Structural Scope Release Surface Owner Handoff Check

- `status`: `ready_for_owner_review`
- `contract_pass`: `True`
- `expected_release_surface_path_count`: `3`

## Paths

- `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json`
- `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json`
- `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json`

## Owner Decision State

- `owner_decision_pending_count`: `251`
- `owner_decision_recorded_count`: `0`
- `release_surface_owner_decision_required_count`: `3`
- `release_surface_first_batch_application_ready`: `False`
- `release_surface_first_batch_ready`: `False`
- `retain_quarantined_exception_count`: `0`

## Blockers

- none

## Next Owner Input

- `allowed_owner_decisions`: `delete_from_structural_repository`, `extract_to_molecular_or_science_repository`
- `disallowed_owner_decisions`: `retain_quarantined_with_signed_owner_exception`
- `fill_command`: `python3 scripts/fill_structural_scope_release_surface_owner_decisions.py --template implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.release_surface_first.template.csv --decision-overrides <release-surface-decision-overrides.csv> --out <filled-release-surface-first-owner-decisions.json> --out-md <filled-release-surface-first-owner-decisions.md> --out-csv <filled-release-surface-first-owner-decisions.csv> --decision recommended_primary --owner-identity <owner-identity> --owner-role <owner-role> --decision-timestamp-utc <decision-timestamp-utc> --evidence-reference <owner-evidence-reference> --external-archive-reference <fallback-external-archive-reference-for-extract-decisions> --fail-blocked`
- `merge_command`: `python3 scripts/merge_structural_scope_owner_decision_batch.py --batch-owner-decisions <filled-release-surface-first-owner-decisions.csv> --out <candidate-owner-decisions.json> --out-md <candidate-owner-decisions.md> --fail-release-surface-first-blocked`

## Claim Boundary

This check only verifies that the release-surface-first owner-review handoff is internally consistent across templates, PM handoff, and roadmap surfaces. It is not an owner decision, does not delete or extract files, and does not close structural scope cleanup.
