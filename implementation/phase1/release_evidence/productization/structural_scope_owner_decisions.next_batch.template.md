# Structural Scope Next Batch Owner Decision Template

- `batch_id`: `release_surface_first`
- `path_area`: `release_surface`
- `decision_pending_count`: `3`
- `external_archive_reference`: required when `owner_decision` is `extract_to_molecular_or_science_repository`
- `signed_owner_exception_reference`: required when `owner_decision` is `retain_quarantined_with_signed_owner_exception`

| Row | Path | Primary Decision | Alternate Decision |
|---|---|---|---|
| `release_surface_first-001` | `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json` | `delete_from_structural_repository` | `extract_to_molecular_or_science_repository` |
| `release_surface_first-002` | `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json` | `delete_from_structural_repository` | `extract_to_molecular_or_science_repository` |
| `release_surface_first-003` | `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json` | `delete_from_structural_repository` | `extract_to_molecular_or_science_repository` |

## Primary Cleanup Preview

- `safe_to_auto_apply`: `False`
- `primary_delete_path_count`: `3`
- `primary_extract_path_count`: `0`

## Claim Boundary

This is a batch fill-in template and cleanup preview only. It is not an owner decision, does not delete files, and does not close scope cleanup without recorded owner evidence and refreshed audits.
