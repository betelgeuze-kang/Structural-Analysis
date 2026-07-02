# Structural Scope Next Batch Decision Overrides Template

- `batch_id`: `release_surface_first`
- `path_area`: `release_surface`
- `csv`: `implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.next_batch.overrides.template.csv`

Fill only `owner_decision`, `external_archive_reference`, optionally `evidence_reference`; keep `path` unchanged.

Every row requires an explicit `owner_decision`. Blank rows intentionally block validation so this template cannot silently create all-delete decisions.

| Path | Primary Decision | Alternate Decision | Owner Decision | External Archive Reference | Signed Exception Reference |
|---|---|---|---|---|---|
| `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json` | `delete_from_structural_repository` | `extract_to_molecular_or_science_repository` | `` | `` | `` |
| `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json` | `delete_from_structural_repository` | `extract_to_molecular_or_science_repository` | `` | `` | `` |
| `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json` | `delete_from_structural_repository` | `extract_to_molecular_or_science_repository` | `` | `` | `` |

## Allowed Owner Decisions

- `delete_from_structural_repository`
- `extract_to_molecular_or_science_repository`

## Validation

- `python3 scripts/fill_structural_scope_owner_decisions_from_template.py --template implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.next_batch.template.csv --decision-overrides implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.next_batch.overrides.template.csv --out <filled-next-batch-owner-decisions.json> --out-md <filled-next-batch-owner-decisions.md> --out-csv <filled-next-batch-owner-decisions.csv> --owner-identity <owner-identity> --owner-role <owner-role> --decision-timestamp-utc <decision-timestamp-utc> --evidence-reference <owner-evidence-reference> --fail-blocked`
