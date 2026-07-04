# GPCR Hard-Decoy Source Acquisition Plan

- `status`: `actual_closure_ready`
- `contract_pass`: `True`
- `actual_closure_ready`: `True`
- `blocker_count`: `0`
- `positive_source_snapshot`: `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_positive_source_snapshot.json`
- `positive_source_ready`: `True`
- `decoy_source_snapshot`: `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_decoy_source_snapshot.json`
- `decoy_candidate_source_ready`: `True`
- `chembl_activity_rows`: `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_chembl_activity_rows.json`
- `chembl_activity_rows_ready`: `True`
- `chembl_activity_row_count`: `96`
- `suite_report`: `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_suite_report.json`
- `suite_status`: `ready`
- `suite_target_pass_count`: `3`
- `completion_audit_status`: `pass`
- `completion_audit_requirements`: `9/9`

| Target | UniProt | ChEMBL | Role |
|---|---|---|---|
| `DRD2` | `P14416` | `CHEMBL217` | `target_activity_candidate_source_only` |
| `HTR2A` | `P28223` | `CHEMBL224` | `target_activity_candidate_source_only` |
| `OPRM1` | `P35372` | `CHEMBL233` | `target_activity_candidate_source_only` |

## Actual Closure Completion Audit

| Requirement | Status |
|---|---|
| `expected_gpcr_target_set_present` | `pass` |
| `operator_input_source_receipt_verified` | `pass` |
| `raw_hard_decoy_rows_actual_closure_computed` | `pass` |
| `ranking_pr_auc_ci_low_gate` | `pass` |
| `top20_hit_rate_gate` | `pass` |
| `decoys_above_positive_count_gate` | `pass` |
| `top_decoy_anchor_gate` | `pass` |
| `phase3_exit_gate_ready` | `pass` |
| `candidate_sources_and_activity_rows_ready` | `pass` |

| Target | PR AUC CI Low | Top20 Hit Rate | Decoys Above Positive | Out-Anchored | Raw Rows |
|---|---:|---:|---:|---|---|
| `DRD2` | `1.0` | `0.6` | `0` | `False` | `computed` |
| `HTR2A` | `1.0` | `0.6` | `0` | `False` | `computed` |
| `OPRM1` | `1.0` | `0.6` | `0` | `False` | `computed` |

## Commands

- `write_plan`: `python3 scripts/build_gpcr_hard_decoy_source_acquisition_plan.py`
- `build_positive_source_snapshot`: `python3 scripts/build_gpcr_hard_decoy_positive_source_snapshot.py --out implementation/phase1/release_evidence/productization/gpcr_hard_decoy_positive_source_snapshot.json --out-md implementation/phase1/release_evidence/productization/gpcr_hard_decoy_positive_source_snapshot.md`
- `build_decoy_source_snapshot`: `python3 scripts/build_gpcr_hard_decoy_decoy_source_snapshot.py --out implementation/phase1/release_evidence/productization/gpcr_hard_decoy_decoy_source_snapshot.json --out-md implementation/phase1/release_evidence/productization/gpcr_hard_decoy_decoy_source_snapshot.md`
- `build_chembl_activity_rows`: `python3 scripts/build_gpcr_hard_decoy_chembl_activity_rows.py --out implementation/phase1/release_evidence/productization/gpcr_hard_decoy_chembl_activity_rows.json --out-md implementation/phase1/release_evidence/productization/gpcr_hard_decoy_chembl_activity_rows.md`
- `import_rows`: `python3 scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py --rows implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.json --out implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_template.json --source-id <source-id> --source-url <source-url> --source-license <license>`
- `materialize_suite`: `python3 scripts/materialize_gpcr_hard_decoy_suite_report.py --intake implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_template.json --out-report implementation/phase1/release_evidence/productization/gpcr_hard_decoy_suite_report.json --fail-blocked`
- `science_actual_closure`: `python3 scripts/materialize_science_actual_closure_from_rows.py --fail-blocked`

This plan records verified public target identifiers and the row/source contract needed to acquire GPCR hard-decoy evidence. Candidate ChEMBL snapshots and ChEMBL activity-ranked rows are source receipts and import candidates only; they do not promote a broad GPCR claim until the accepted raw rows pass the suite materializer in the default path.
