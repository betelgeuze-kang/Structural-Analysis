# Structural Scope Owner Decision Application Plan

- `summary_line`: `Structural scope owner decision application plan: PENDING_OWNER_DECISIONS | recorded=0 | pending=86 | cleanup_pending=0 | delete=0 | extract=0 | retain=0 | unquarantined=0`
- `status`: `pending_owner_decisions`
- `contract_pass`: `True`
- `application_ready`: `False`
- `evidence_closure_pass`: `False`
- `owner_decision_validation_pass`: `False`
- `owner_decision_pending_count`: `86`
- `post_decision_cleanup_pending_count`: `0`
- `post_decision_cleanup_applied_count`: `0`
- `cleanup_required_count`: `0`
- `release_surface_cleanup_required_count`: `0`
- `delete_decision_count`: `0`
- `extract_decision_count`: `0`
- `retain_quarantined_exception_count`: `0`
- `release_surface_owner_decision_required_count`: `3`

## Pending Owner Decision Buckets

- `pending_owner_decision_path_area_counts`: `{'implementation_phase1': 9, 'productization_evidence': 36, 'release_surface': 3, 'script': 19, 'test': 19}`
- `pending_owner_decision_family_counts`: `{'molecular_docking': 48, 'molecular_dynamics': 25, 'molecular_science_evidence': 13}`
- `pending_owner_decision_recommended_owner_decision_counts`: `{'delete_from_structural_repository_or_extract_only_if_owner_requires_history': 39, 'extract_to_molecular_or_science_repository_or_delete_if_obsolete': 47}`
- `pending_owner_decision_primary_counts`: `{'delete_from_structural_repository': 39, 'extract_to_molecular_or_science_repository': 47}`
- `next_owner_review_batch`: `release_surface_first` paths=`3` area=`release_surface`
- `owner_review_priority_batches`: `5`

## Release Surface First Batch Intake

- `status`: `pending_owner_decisions`
- `ready_for_manual_cleanup_application`: `False`
- `expected_path_count`: `3`
- `valid_cleanup_decision_count`: `0`
- `pending_decision_count`: `3`
- `pending_release_surface_owner_decision_count=3`
- `release_surface_cleanup_decision_count_below_expected=0/3`

## Next Batch Decision Template

- `batch_id`: `release_surface_first`
- `decision_pending_count`: `3`
- `primary_delete_path_count`: `3`

| Row | Path | Primary Decision |
|---|---|---|
| `release_surface_first-001` | `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json` | `delete_from_structural_repository` |
| `release_surface_first-002` | `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json` | `delete_from_structural_repository` |
| `release_surface_first-003` | `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json` | `delete_from_structural_repository` |

## Owner Decision Validation Blockers

- `owner_decisions_missing`
- `owner_decision_pending_count=86`

## Plan Blockers

- `owner_decision_pending_count=86`

## Cleanup Rows

| Path | Decision | Required Action |
|---|---|---|

## Cleanup Command Manifest

- `safe_to_auto_apply`: `False`
- `manual_application_required`: `False`
- `delete_from_structural_repository.path_count`: `0`
- `extract_to_molecular_or_science_repository.path_count`: `0`

## Cleanup Application Preflight

- `status`: `no_cleanup_required`
- `ready`: `False`
- `destructive_commands_enabled`: `False`
- `safe_to_auto_apply`: `False`
- blockers: none

## Claim Boundary

This application plan is non-mutating. It never deletes or extracts files. It only classifies owner decisions into manual follow-up actions and keeps quarantined non-structural artifacts outside the building structural-analysis release surface until owner evidence and post-decision scope audit closure are present.
