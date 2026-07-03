# GPCR Hard-Decoy Source Acquisition Plan

- `status`: `operator_acquisition_required`
- `contract_pass`: `True`
- `actual_closure_ready`: `False`
- `blocker_count`: `3`

| Target | UniProt | ChEMBL | Role |
|---|---|---|---|
| `DRD2` | `P14416` | `CHEMBL217` | `positive_ligand_candidate_source_only` |
| `HTR2A` | `P28223` | `CHEMBL224` | `positive_ligand_candidate_source_only` |
| `OPRM1` | `P35372` | `CHEMBL233` | `positive_ligand_candidate_source_only` |

## Commands

- `write_plan`: `python3 scripts/build_gpcr_hard_decoy_source_acquisition_plan.py`
- `import_rows`: `python3 scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py --rows implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.json --out implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_template.json --source-id <source-id> --source-url <source-url> --source-license <license>`
- `materialize_suite`: `python3 scripts/materialize_gpcr_hard_decoy_suite_report.py --intake implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_template.json --out-report implementation/phase1/release_evidence/productization/gpcr_hard_decoy_suite_report.json --fail-blocked`
- `science_actual_closure`: `python3 scripts/materialize_science_actual_closure_from_rows.py --fail-blocked`

This plan records verified public target identifiers and the row/source contract needed to acquire GPCR hard-decoy evidence. It does not download or attach activity data, decoys, docking scores, or licenses, and it does not close Phase 3 until the raw rows pass the suite materializer.
