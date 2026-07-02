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

## Primary Cleanup Preview

- `safe_to_auto_apply`: `False`
- `primary_delete_path_count`: `3`
- `primary_extract_path_count`: `0`

## Post Batch Verification

- `python3 scripts/build_structural_scope_owner_decision_application_plan.py --fail-release-surface-first-blocked`
- `python3 scripts/check_structural_scope_contamination.py --tracked-only --fail-blocked`
- `python3 scripts/build_structural_scope_owner_review_packet.py --write-decision-template`
- `python3 scripts/build_structural_scope_owner_decision_application_plan.py --fail-invalid-owner-decisions`
- `python3 scripts/build_product_readiness_snapshot.py --check`

## Claim Boundary

This is a batch fill-in template and cleanup preview only. It is not an owner decision, does not delete files, and does not close scope cleanup without recorded owner evidence and refreshed audits.
