# Structural Scope Release Surface Mixed Decision Overrides Template

- `batch_id`: `release_surface_first`
- `csv`: `implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.release_surface_first.overrides.template.csv`

Fill only `owner_decision`, `external_archive_reference`, and optionally `evidence_reference`; keep `path` unchanged.

Every row requires an explicit `owner_decision`. Blank rows intentionally block validation so this template cannot silently create all-delete decisions.

| Path | Primary Decision | Alternate Decision | Owner Decision | External Archive Reference |
|---|---|---|---|---|
| `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json` | `delete_from_structural_repository` | `extract_to_molecular_or_science_repository` | `` | `` |
| `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json` | `delete_from_structural_repository` | `extract_to_molecular_or_science_repository` | `` | `` |
| `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json` | `delete_from_structural_repository` | `extract_to_molecular_or_science_repository` | `` | `` |

## Allowed Owner Decisions

- `delete_from_structural_repository`
- `extract_to_molecular_or_science_repository`

## Validation

- `python3 scripts/fill_structural_scope_release_surface_owner_decisions.py --template implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.release_surface_first.template.csv --decision-overrides implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.release_surface_first.overrides.template.csv --out <filled-release-surface-first-owner-decisions.json> --out-md <filled-release-surface-first-owner-decisions.md> --out-csv <filled-release-surface-first-owner-decisions.csv> --owner-identity <owner-identity> --owner-role <owner-role> --decision-timestamp-utc <decision-timestamp-utc> --evidence-reference <owner-evidence-reference> --fail-blocked`
