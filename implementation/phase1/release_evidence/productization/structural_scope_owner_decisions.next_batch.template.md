# Structural Scope Next Batch Owner Decision Template

- `batch_id`: `release_surface_first`
- `path_area`: `release_surface`
- `decision_pending_count`: `3`
- `external_archive_reference`: required when `owner_decision` is `extract_to_molecular_or_science_repository`

## Path-Specific Restrictions

- `retain_quarantined_with_signed_owner_exception is not allowed when path_area=release_surface`

## Decision Rows

| Row | Path | Primary Decision | Alternate Decision |
|---|---|---|---|
| `release_surface_first-001` | `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json` | `delete_from_structural_repository` | `extract_to_molecular_or_science_repository` |
| `release_surface_first-002` | `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json` | `delete_from_structural_repository` | `extract_to_molecular_or_science_repository` |
| `release_surface_first-003` | `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json` | `delete_from_structural_repository` | `extract_to_molecular_or_science_repository` |

## Decision Overrides Template

- `csv`: `implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.next_batch.overrides.template.csv`
- `markdown`: `implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.next_batch.overrides.template.md`

| Row | Path | Owner Decision | External Archive Reference | Signed Exception Reference |
|---|---|---|---|---|
| `release_surface_first-001` | `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json` | `` | `` | `` |
| `release_surface_first-002` | `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json` | `` | `` | `` |
| `release_surface_first-003` | `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json` | `` | `` | `` |

## Primary Cleanup Preview

- `safe_to_auto_apply`: `False`
- `primary_delete_path_count`: `3`
- `primary_extract_path_count`: `0`

## Owner Decision Submission

- `canonical_owner_decisions_path`: `implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.json`
- `template_csv_path`: `implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.next_batch.template.csv`
- `fill_release_surface_owner_decisions_command`: `python3 scripts/fill_structural_scope_release_surface_owner_decisions.py --template implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.next_batch.template.csv --out <filled-next-batch-owner-decisions.json> --out-md <filled-next-batch-owner-decisions.md> --out-csv <filled-next-batch-owner-decisions.csv> --decision recommended_primary --owner-identity <owner-identity> --owner-role <owner-role> --decision-timestamp-utc <decision-timestamp-utc> --evidence-reference <owner-evidence-reference> --external-archive-reference <external-archive-reference-for-extract-decisions> --fail-blocked`
- `fill_release_surface_owner_decisions_with_overrides_command`: `python3 scripts/fill_structural_scope_release_surface_owner_decisions.py --template implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.next_batch.template.csv --decision-overrides <release-surface-decision-overrides.csv> --out <filled-next-batch-owner-decisions.json> --out-md <filled-next-batch-owner-decisions.md> --out-csv <filled-next-batch-owner-decisions.csv> --decision recommended_primary --owner-identity <owner-identity> --owner-role <owner-role> --decision-timestamp-utc <decision-timestamp-utc> --evidence-reference <owner-evidence-reference> --external-archive-reference <fallback-external-archive-reference-for-extract-decisions> --fail-blocked`
- `fill_owner_decisions_from_template_command`: `python3 scripts/fill_structural_scope_owner_decisions_from_template.py --template implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.next_batch.template.csv --out <filled-next-batch-owner-decisions.json> --out-md <filled-next-batch-owner-decisions.md> --out-csv <filled-next-batch-owner-decisions.csv> --decision recommended_primary --owner-identity <owner-identity> --owner-role <owner-role> --decision-timestamp-utc <decision-timestamp-utc> --evidence-reference <owner-evidence-reference> --external-archive-reference <external-archive-reference-for-extract-decisions> --fail-blocked`
- `fill_owner_decisions_from_template_with_overrides_command`: `python3 scripts/fill_structural_scope_owner_decisions_from_template.py --template implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.next_batch.template.csv --decision-overrides <owner-decision-overrides.csv> --out <filled-next-batch-owner-decisions.json> --out-md <filled-next-batch-owner-decisions.md> --out-csv <filled-next-batch-owner-decisions.csv> --decision recommended_primary --owner-identity <owner-identity> --owner-role <owner-role> --decision-timestamp-utc <decision-timestamp-utc> --evidence-reference <owner-evidence-reference> --external-archive-reference <fallback-external-archive-reference-for-extract-decisions> --fail-blocked`
- `validate_canonical_owner_decisions_command`: `python3 scripts/build_structural_scope_owner_decision_application_plan.py --fail-release-surface-first-blocked`
- `validate_filled_csv_command`: `python3 scripts/build_structural_scope_owner_decision_application_plan.py --owner-decisions <filled-next-batch-owner-decisions.csv> --fail-release-surface-first-blocked`
- `merge_filled_csv_to_candidate_command`: `python3 scripts/merge_structural_scope_owner_decision_batch.py --batch-owner-decisions <filled-next-batch-owner-decisions.csv> --out <candidate-owner-decisions.json> --out-md <candidate-owner-decisions.md>`
- `merge_and_validate_filled_csv_command`: `python3 scripts/merge_structural_scope_owner_decision_batch.py --batch-owner-decisions <filled-next-batch-owner-decisions.csv> --out <candidate-owner-decisions.json> --out-md <candidate-owner-decisions.md> --fail-release-surface-first-blocked`
- `validate_merged_candidate_command`: `python3 scripts/build_structural_scope_owner_decision_application_plan.py --owner-decisions <candidate-owner-decisions.json> --fail-release-surface-first-blocked`

## Post Batch Verification

- `python3 scripts/build_structural_scope_owner_decision_application_plan.py --fail-release-surface-first-blocked`
- `python3 scripts/check_structural_scope_contamination.py --tracked-only --check --fail-blocked`
- `python3 scripts/build_structural_scope_owner_review_packet.py --write-decision-template`
- `python3 scripts/build_structural_scope_owner_decision_application_plan.py --fail-invalid-owner-decisions`
- `python3 scripts/build_product_readiness_snapshot.py --check`

## Claim Boundary

This is a batch fill-in template and cleanup preview only. It is not an owner decision, does not delete files, and does not close scope cleanup without recorded owner evidence and refreshed audits.
