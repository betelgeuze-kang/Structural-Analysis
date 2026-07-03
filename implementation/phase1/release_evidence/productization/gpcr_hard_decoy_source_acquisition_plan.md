# GPCR Hard-Decoy Source Acquisition Plan

- `status`: `operator_acquisition_required`
- `contract_pass`: `True`
- `actual_closure_ready`: `False`
- `blocker_count`: `3`
- `positive_source_snapshot`: `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_positive_source_snapshot.json`
- `positive_source_ready`: `True`
- `decoy_source_snapshot`: `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_decoy_source_snapshot.json`
- `decoy_candidate_source_ready`: `True`

| Target | UniProt | ChEMBL | Role |
|---|---|---|---|
| `DRD2` | `P14416` | `CHEMBL217` | `target_activity_candidate_source_only` |
| `HTR2A` | `P28223` | `CHEMBL224` | `target_activity_candidate_source_only` |
| `OPRM1` | `P35372` | `CHEMBL233` | `target_activity_candidate_source_only` |

## Commands

- `write_plan`: `python3 scripts/build_gpcr_hard_decoy_source_acquisition_plan.py`
- `build_positive_source_snapshot`: `python3 scripts/build_gpcr_hard_decoy_positive_source_snapshot.py --out implementation/phase1/release_evidence/productization/gpcr_hard_decoy_positive_source_snapshot.json --out-md implementation/phase1/release_evidence/productization/gpcr_hard_decoy_positive_source_snapshot.md`
- `build_decoy_source_snapshot`: `python3 scripts/build_gpcr_hard_decoy_decoy_source_snapshot.py --out implementation/phase1/release_evidence/productization/gpcr_hard_decoy_decoy_source_snapshot.json --out-md implementation/phase1/release_evidence/productization/gpcr_hard_decoy_decoy_source_snapshot.md`
- `import_rows`: `python3 scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py --rows implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.json --out implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_template.json --source-id <source-id> --source-url <source-url> --source-license <license>`
- `materialize_suite`: `python3 scripts/materialize_gpcr_hard_decoy_suite_report.py --intake implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_template.json --out-report implementation/phase1/release_evidence/productization/gpcr_hard_decoy_suite_report.json --fail-blocked`
- `science_actual_closure`: `python3 scripts/materialize_science_actual_closure_from_rows.py --fail-blocked`

This plan records verified public target identifiers and the row/source contract needed to acquire GPCR hard-decoy evidence. Candidate ChEMBL snapshots are source receipts only; they do not attach curated decoys, docking scores, or licenses, and they do not close Phase 3 until the raw rows pass the suite materializer.
