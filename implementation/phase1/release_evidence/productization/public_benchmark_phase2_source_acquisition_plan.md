# Public Benchmark Phase 2 Source Acquisition Plan

- `status`: `operator_acquisition_required`
- `contract_pass`: `True`
- `phase2_ready`: `False`
- `actual_closure_ready`: `False`
- `blocker_count`: `1`
- `official_source_receipt_plan_status`: `operator_receipts_required`
- `official_source_receipt_role_count`: `4`
- `official_source_catalog_count`: `6`
- `official_source_access_preflight_count`: `6`
- `source_access_preflight_receipt_status`: `reachable`
- `source_access_preflight_receipt_ready`: `True`
- `source_access_preflight_reachable_count`: `6`
- `source_access_preflight_blocked_count`: `0`
- `external_receipts_validation_status`: `ready`
- `external_receipts_complete_artifact_roles`: `3/3`
- `external_receipt_completion_audit_status`: `operator_external_receipts_required`
- `external_receipt_blocked_official_role_count`: `1`
- `phase2_row_audit`: `implementation/phase1/release_evidence/productization/public_benchmark_phase2_row_audit.json`
- `phase2_row_audit_status`: `ready`
- `phase2_row_audit_completion_audit_status`: `pass`
- `phase2_row_audit_completion_requirement_pass_count`: `6/6`
- `phase2_row_audit_missing_row_inputs`: ``
- `phase2_row_audit_source_actuality_scope`: ``
- `phase2_row_audit_source_actuality_contract_pass`: `True`
- `phase2_row_audit_source_actuality_blocker_count`: `0`
- `phase2_exit_criterion_count`: `6`
- `phase2_row_closure_matrix_count`: `4`
- `phase2_harness_completion_audit_status`: `harness_inputs_blocked`
- `phase2_harness_ready_requirement_count`: `5`
- `phase2_harness_blocked_requirement_count`: `0`
- `phase2_harness_complete_except_vina_gnina_actual_rows`: `False`
- `missing_row_input_action_count`: `0`
- `vina_gnina_actual_evidence_audit_status`: `ready`
- `vina_gnina_actual_evidence_blocked_component_count`: `0`
- `vina_gnina_execution_plan`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_execution_plan.json`
- `vina_gnina_execution_plan_status`: `ready_for_engine_execution`
- `vina_gnina_required_engine_run_count`: `24`
- `vina_gnina_input_manifest_status`: `ready`
- `vina_gnina_input_manifest_row_count`: `12`
- `vina_gnina_input_manifest_verification_status`: `case_inputs_verified`
- `vina_gnina_input_manifest_verified_case_input_count`: `12`
- `vina_gnina_input_manifest_template_completion_blocked_case_count`: `0`
- `vina_gnina_runtime_readiness`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_runtime_readiness.json`
- `vina_gnina_runtime_readiness_status`: `adapter_materialization_ready`
- `vina_gnina_runtime_ready_engine_run_slot_count`: `24`
- `vina_gnina_runtime_case_input_slot_count`: `12`
- `vina_gnina_runtime_blocked_case_input_slot_count`: `0`
- `vina_gnina_runtime_engine_run_slot_count`: `24`
- `vina_gnina_runtime_blocked_engine_run_slot_count`: `0`
- `vina_gnina_adapter_row_preflight_status`: `row_artifact_detected_validated`
- `vina_gnina_engine_run_bundle_status`: `engine_run_bundle_materialized`
- `vina_gnina_engine_run_bundle_materialized`: `True`
- `vina_gnina_rows_from_engine_run_bundle_status`: `rows_materialized`
- `vina_gnina_rows_from_engine_run_bundle_materialized`: `True`
- `vina_gnina_rows_template_role_receipt_blocked_count`: `72`
- `vina_gnina_runtime_missing_engine_ids`: ``

## Operator Next Actions

| Step | Action |
|---:|---|
| 1 | `review_official_source_receipt_plan` |
| 2 | `attach_casf_pdbbind_subset_rows_with_local_file_checksums` |
| 3 | `attach_pose_coordinate_rows_with_symmetry_contracts` |
| 4 | `attach_dud_e_or_lit_pcba_scored_molecule_rows` |
| 5 | `build_vina_gnina_execution_plan_from_materialized_cases` |
| 6 | `fill_public_benchmark_vina_gnina_input_manifest` |
| 7 | `run_vina_gnina_runtime_readiness_check` |
| 8 | `attach_vina_gnina_engine_run_rows` |
| 9 | `build_source_access_preflight_receipt` |
| 10 | `attach_external_source_receipts_and_license_or_accession_refs` |
| 11 | `run_public_benchmark_operator_bundle_from_rows` |
| 12 | `run_public_benchmark_phase2_row_audit` |
| 13 | `run_public_benchmark_harness_bundle_materializer` |
| 14 | `refresh_public_benchmark_source_of_truth` |

## Source Access Preflight Receipt

- `artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.json`
- `status`: `reachable`
- `network_probe_performed`: `True`
- `source_access_ready`: `True`
- `reachable_count`: `6`
- `blocked_count`: `0`

| Source | Family | Status | Primary HTTP | Fallback HTTP | Blockers |
|---|---|---|---:|---:|---|
| `pdbbind_plus_casf` | `CASF/PDBBind` | `primary_reachable` | 200 | 200 | `none` |
| `dud_e` | `DUD-E` | `primary_reachable` | 200 | 200 | `none` |
| `lit_pcba` | `LIT-PCBA` | `primary_reachable` | 200 | 200 | `none` |
| `autodock_vina` | `Vina` | `primary_reachable` | 200 | 200 | `none` |
| `gnina` | `GNINA` | `primary_reachable` | 200 | 200 | `none` |
| `posebusters` | `PoseBusters` | `primary_reachable` | 200 | 200 | `none` |

## External Receipt Completion Audit

- `status`: `operator_external_receipts_required`
- `source_access_ready`: `True`
- `external_receipts_validation_status`: `ready`
- `external_receipts_ready_for_materialized_rows`: `True`
- `complete_artifact_roles`: `3/3`
- `all_expected_artifact_roles_complete`: `True`
- `missing_expected_artifact_roles`: `none`
- `blocked_official_receipt_role_count`: `1`
- `operator_action`: `attach_external_source_receipts_and_license_or_accession_refs`

| Receipt Role | Row Input | Status | Row Status | Sources Ready | Validator Role | Blockers |
|---|---|---|---|---|---|---|
| `casf_pdbbind_subset_source_receipt` | `subset_rows` | `ready` | `provided` | `True` | `casf_pdbbind_subset_manifest` | `none` |
| `casf_pdbbind_pose_coordinate_receipt` | `pose_rows` | `operator_receipt_required` | `provided` | `True` | `row_actuality` | `pose_rows_source_actuality_not_ready` |
| `dud_e_or_lit_pcba_enrichment_receipt` | `enrichment_rows` | `ready` | `provided` | `True` | `dud_e_lit_pcba_enrichment_scorecard` | `none` |
| `vina_gnina_engine_comparison_receipt` | `vina_gnina_rows` | `ready` | `provided` | `True` | `vina_gnina_comparison_adapter` | `none` |

## Phase 2 Harness Completion Audit

- `status`: `harness_inputs_blocked`
- `harness_contract_complete_except_vina_gnina_actual_rows`: `False`
- `remaining_row_inputs`: ``
- `remaining_operator_action`: `review_public_benchmark_phase2_row_audit_blockers`
- `vina_gnina_runtime_status`: `adapter_materialization_ready`
- `vina_gnina_input_manifest_status`: `ready`

| Requirement | Product Requirement | Status | Pass | Row Inputs | Blockers |
|---|---|---|---|---|---|
| `casf_pdbbind_pose_success_harness` | CASF/PDBBind pose-success harness | `ready` | `True` | `subset_rows`, `pose_rows` | `none` |
| `symmetry_aware_ligand_rmsd` | symmetry-aware ligand RMSD | `ready` | `True` | `pose_rows` | `none` |
| `posebusters_style_pose_validity_checks` | PoseBusters-style pose validity checks | `ready` | `True` | `pose_rows` | `none` |
| `vina_gnina_comparison_adapter` | Vina/GNINA comparison adapter | `ready` | `True` | `vina_gnina_rows` | `none` |
| `dud_e_or_lit_pcba_enrichment` | DUD-E or LIT-PCBA enrichment | `ready` | `True` | `enrichment_rows` | `none` |

## Vina/GNINA Actual Evidence Audit

- `status`: `ready`
- `actual_closure_ready`: `True`
- `ready_component_count`: `6`
- `blocked_component_count`: `0`
- `remaining_evidence`: ``
- `operator_blocker_family_count`: `7`
- `operator_blocker_family_missing_item_count`: `0`

| Component | Status | Pass | Current | Required | Blockers |
|---|---|---|---|---|---|
| `engine_input_manifest` | `ready` | `True` | `{"blocked_case_input_slot_count": 0, "blocked_source_file_count": 0, "case_input_slot_count": 12, "input_manifest_detected": true, "input_manifest_row_count": 12, "input_manifest_status": "ready", "input_manifest_syntax_ready": true, "input_manifest_verification_status": "case_inputs_verified", "prepared_input_gap_count": 0, "prepared_input_ready_case_count": 12, "required_case_count": 12, "source_extraction_status": "source_files_verified_prepared_inputs_required", "source_file_count": 24, "source_files_ready": true, "source_ready_case_count": 12, "template_completion_blocked_case_count": 0, "template_manifest_ready": true, "template_missing_local_file_count": 0, "template_missing_receipt_ref_count": 0, "template_preflight_status": "operator_manifest_complete", "verified_case_input_count": 12, "verified_source_file_count": 24}` | `{"blocked_case_input_slot_count": 0, "input_manifest_detected": true, "input_manifest_row_count": ">=12", "input_manifest_syntax_ready": true, "template_manifest_ready": true, "verified_case_input_count": ">=12"}` | `none` |
| `engine_runtime` | `ready` | `True` | `{"available_engine_count": 2, "missing_engine_count": 0, "missing_engine_ids": [], "runtime_ready_for_engine_execution": true, "runtime_status": "adapter_materialization_ready"}` | `{"missing_engine_count": 0, "runtime_ready_for_engine_execution": true}` | `none` |
| `engine_run_slots` | `ready` | `True` | `{"blocked_engine_run_slot_count": 0, "ready_engine_run_slot_count": 24, "required_engine_run_count": 24}` | `{"blocked_engine_run_slot_count": 0, "ready_engine_run_slot_count": 24}` | `none` |
| `adapter_rows` | `ready` | `True` | `{"adapter_case_count": 12, "adapter_preflight_contract_pass": true, "adapter_preflight_status": "ready", "adapter_rows_ready": true, "detected_row_artifact_count": 1, "row_candidate_status": "row_artifact_detected_validated", "selected_row_count": 12}` | `{"adapter_case_count": ">=1", "adapter_preflight_contract_pass": true, "detected_row_artifact_count": ">=1"}` | `none` |
| `per_engine_run_receipts` | `ready` | `True` | `{"adapter_template_ready": false, "expected_rows_detected": false, "missing_engine_run_receipt_value_count": 72, "ready_engine_run_count": 24, "role_receipt_blocked_count": 72, "role_receipt_plan_count": 96, "rows_from_engine_run_bundle_materialized": true, "rows_from_engine_run_bundle_status": "rows_materialized", "rows_template_preflight_status": "operator_rows_completion_required"}` | `{"adapter_template_ready_or_rows_from_engine_run_bundle_materialized": true, "expected_rows_detected_or_materialized_bundle_rows": true, "role_receipt_blocked_count_or_bundle_blocker_count": 0}` | `none` |
| `external_receipts` | `ready` | `True` | `{"all_expected_artifact_roles_complete": true, "blocked_official_receipt_role_count": 1, "external_receipt_completion_status": "operator_external_receipts_required", "missing_expected_artifact_roles": []}` | `{"all_expected_artifact_roles_complete": true, "blocked_official_receipt_role_count": 0}` | `pose_rows_source_actuality_not_ready` |

### Vina/GNINA Operator Blocker Families

| Family | Status | Missing Items | Blocked Cases | Operator Action | Command Key | Materialization Command |
|---|---|---:|---:|---|---|---|
| `manifest_required_values` | `ready` | 0 | 0 | `review_verified_vina_gnina_input_manifest` | `build_input_manifest_template_preflight` | `python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.md` |
| `official_source_files` | `ready` | 0 | 0 | `review_verified_casf_source_file_receipt` | `materialize_input_manifest_from_casf_archive` | `python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py --archive <CASF-2016.tar.gz> --out-manifest implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.csv --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_from_casf_archive_report.json --fail-blocked` |
| `prepared_input_files` | `ready` | 0 | 0 | `review_verified_vina_gnina_prepared_inputs` | `build_input_manifest_template_preflight` | `python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.md` |
| `input_and_engine_receipt_refs` | `ready` | 0 | 0 | `attach_vina_gnina_input_and_engine_receipt_refs` | `build_input_manifest_template_preflight` | `python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.md` |
| `engine_runtime` | `ready` | 0 | 0 | `configure_vina_gnina_binary_or_container_runtime` | `rerun_runtime_readiness` | `python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_runtime_readiness.json` |
| `engine_run_slots` | `ready` | 0 | 0 | `rerun_runtime_readiness_until_engine_run_slots_ready` | `rerun_runtime_readiness` | `python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_runtime_readiness.json` |
| `adapter_rows` | `ready` | 0 | 0 | `attach_or_materialize_public_benchmark_vina_gnina_rows` | `materialize_rows_from_engine_run_bundle` | `python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py --engine-run-bundle implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_engine_run_bundle.json --out-rows implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_from_engine_run_bundle_report.json` |

| Row Input | Source Family | Status | Unblocks |
|---|---|---|---|
| `subset_rows` | `CASF/PDBBind` | `operator_acquisition_required` | `casf_pdbbind_pose_success_harness` |
| `pose_rows` | `CASF/PDBBind` | `operator_acquisition_required` | `casf_pdbbind_pose_success_harness`, `symmetry_aware_ligand_rmsd`, `posebusters_style_pose_validity` |
| `enrichment_rows` | `DUD-E/LIT-PCBA` | `operator_acquisition_required` | `dud_e_or_lit_pcba_enrichment` |
| `vina_gnina_rows` | `CASF/PDBBind + Vina/GNINA` | `operator_acquisition_required` | `vina_gnina_comparison_adapter` |

## Phase 2 Exit Criteria

| Criterion | Component | Pass | Current | Required | Blockers |
|---|---|---|---|---|---|
| `casf_pdbbind_pose_success_harness_ready` | `casf_pdbbind_pose_success_harness` | `True` | `{"contract_pass": true, "ready": true, "real_benchmark_case_count": 12}` | `{"contract_pass": true, "ready": true, "real_benchmark_case_count": 12}` | `none` |
| `symmetry_aware_ligand_rmsd_ready` | `symmetry_aware_ligand_rmsd` | `True` | `{"contract_pass": true, "ready": true, "real_benchmark_case_count": 12}` | `{"contract_pass": true, "ready": true, "real_benchmark_case_count": 12}` | `none` |
| `posebusters_style_pose_validity_ready` | `posebusters_style_pose_validity` | `True` | `{"contract_pass": true, "ready": true, "real_benchmark_case_count": 12}` | `{"contract_pass": true, "ready": true, "real_benchmark_case_count": 12}` | `none` |
| `vina_gnina_comparison_ready` | `vina_gnina_comparison_adapter` | `True` | `{"contract_pass": true, "ready": true, "real_comparison_case_count": 12}` | `{"contract_pass": true, "ready": true, "real_comparison_case_count": 1}` | `none` |
| `dud_e_or_lit_pcba_enrichment_ready` | `dud_e_or_lit_pcba_enrichment` | `True` | `{"contract_pass": true, "ready": true, "real_enrichment_target_count": 1}` | `{"contract_pass": true, "ready": true, "real_enrichment_target_count": 1}` | `none` |
| `public_benchmark_source_actuality_ready` | `operator_attached_source_actuality` | `True` | `{"blocker_count": 0, "contract_pass": true}` | `{"blocker_count": 0, "contract_pass": true}` | `none` |

## Phase 2 Row Closure Matrix

| Row Input | Status | Closes Criteria | Components | Materialization Chain |
|---|---|---|---|---|
| `subset_rows` | `provided` | `casf_pdbbind_pose_success_harness_ready` | `casf_pdbbind_pose_success_harness` | `materialize_public_benchmark_subset_manifest`, `validate_public_benchmark_subset_manifest`, `materialize_public_benchmark_pose_validity_input`, `materialize_public_benchmark_pose_success_harness` |
| `pose_rows` | `provided` | `casf_pdbbind_pose_success_harness_ready`, `symmetry_aware_ligand_rmsd_ready`, `posebusters_style_pose_validity_ready` | `symmetry_aware_ligand_rmsd`, `posebusters_style_pose_validity`, `casf_pdbbind_pose_success_harness` | `materialize_public_benchmark_pose_validity_input`, `validate_public_benchmark_pose_validity`, `materialize_public_benchmark_posebusters_validity_packet`, `materialize_public_benchmark_rmsd_scorecard`, `materialize_public_benchmark_pose_success_harness` |
| `enrichment_rows` | `provided` | `dud_e_or_lit_pcba_enrichment_ready` | `dud_e_or_lit_pcba_enrichment` | `materialize_public_benchmark_enrichment_scorecard` |
| `vina_gnina_rows` | `provided` | `vina_gnina_comparison_ready` | `vina_gnina_comparison_adapter` | `materialize_public_benchmark_vina_gnina_comparison_adapter` |

## Vina/GNINA Runtime

- `operator_unblock_status`: `adapter_materialization_ready`
- `input_manifest_template_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template.csv`
- `blocked_case_input_slot_count`: `0`
- `blocked_engine_run_slot_count`: `0`
- `adapter_row_preflight_status`: `row_artifact_detected_validated`

### Vina/GNINA Case Input Slots

| Slot | Case | Complex | Status | Action | Blockers |
|---|---|---|---|---|---|
| `casf2016_2v00_case_inputs` | `casf2016_2v00` | `2v00` | `ready` | `review_vina_gnina_case_inputs_for_casf2016_2v00` | `none` |
| `casf2016_3prs_case_inputs` | `casf2016_3prs` | `3prs` | `ready` | `review_vina_gnina_case_inputs_for_casf2016_3prs` | `none` |
| `casf2016_3pww_case_inputs` | `casf2016_3pww` | `3pww` | `ready` | `review_vina_gnina_case_inputs_for_casf2016_3pww` | `none` |
| `casf2016_3ui7_case_inputs` | `casf2016_3ui7` | `3ui7` | `ready` | `review_vina_gnina_case_inputs_for_casf2016_3ui7` | `none` |
| `casf2016_3uri_case_inputs` | `casf2016_3uri` | `3uri` | `ready` | `review_vina_gnina_case_inputs_for_casf2016_3uri` | `none` |
| `casf2016_3uuo_case_inputs` | `casf2016_3uuo` | `3uuo` | `ready` | `review_vina_gnina_case_inputs_for_casf2016_3uuo` | `none` |
| `casf2016_3wz8_case_inputs` | `casf2016_3wz8` | `3wz8` | `ready` | `review_vina_gnina_case_inputs_for_casf2016_3wz8` | `none` |
| `casf2016_4llx_case_inputs` | `casf2016_4llx` | `4llx` | `ready` | `review_vina_gnina_case_inputs_for_casf2016_4llx` | `none` |
| `casf2016_4m0y_case_inputs` | `casf2016_4m0y` | `4m0y` | `ready` | `review_vina_gnina_case_inputs_for_casf2016_4m0y` | `none` |
| `casf2016_4m0z_case_inputs` | `casf2016_4m0z` | `4m0z` | `ready` | `review_vina_gnina_case_inputs_for_casf2016_4m0z` | `none` |
| `casf2016_5c28_case_inputs` | `casf2016_5c28` | `5c28` | `ready` | `review_vina_gnina_case_inputs_for_casf2016_5c28` | `none` |
| `casf2016_5c2h_case_inputs` | `casf2016_5c2h` | `5c2h` | `ready` | `review_vina_gnina_case_inputs_for_casf2016_5c2h` | `none` |

### Vina/GNINA Engine Run Slots

| Slot | Case | Engine | Status | Actions | Blockers |
|---|---|---|---|---|---|
| `casf2016_4llx_vina` | `casf2016_4llx` | `vina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_4llx`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_4llx_vina` | `none` |
| `casf2016_4llx_gnina` | `casf2016_4llx` | `gnina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_4llx`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_4llx_gnina` | `none` |
| `casf2016_5c28_vina` | `casf2016_5c28` | `vina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_5c28`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_5c28_vina` | `none` |
| `casf2016_5c28_gnina` | `casf2016_5c28` | `gnina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_5c28`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_5c28_gnina` | `none` |
| `casf2016_3uuo_vina` | `casf2016_3uuo` | `vina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_3uuo`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3uuo_vina` | `none` |
| `casf2016_3uuo_gnina` | `casf2016_3uuo` | `gnina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_3uuo`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3uuo_gnina` | `none` |
| `casf2016_3ui7_vina` | `casf2016_3ui7` | `vina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_3ui7`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3ui7_vina` | `none` |
| `casf2016_3ui7_gnina` | `casf2016_3ui7` | `gnina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_3ui7`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3ui7_gnina` | `none` |
| `casf2016_5c2h_vina` | `casf2016_5c2h` | `vina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_5c2h`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_5c2h_vina` | `none` |
| `casf2016_5c2h_gnina` | `casf2016_5c2h` | `gnina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_5c2h`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_5c2h_gnina` | `none` |
| `casf2016_2v00_vina` | `casf2016_2v00` | `vina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_2v00`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_2v00_vina` | `none` |
| `casf2016_2v00_gnina` | `casf2016_2v00` | `gnina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_2v00`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_2v00_gnina` | `none` |
| `casf2016_3wz8_vina` | `casf2016_3wz8` | `vina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_3wz8`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3wz8_vina` | `none` |
| `casf2016_3wz8_gnina` | `casf2016_3wz8` | `gnina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_3wz8`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3wz8_gnina` | `none` |
| `casf2016_3pww_vina` | `casf2016_3pww` | `vina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_3pww`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3pww_vina` | `none` |
| `casf2016_3pww_gnina` | `casf2016_3pww` | `gnina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_3pww`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3pww_gnina` | `none` |
| `casf2016_3prs_vina` | `casf2016_3prs` | `vina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_3prs`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3prs_vina` | `none` |
| `casf2016_3prs_gnina` | `casf2016_3prs` | `gnina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_3prs`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3prs_gnina` | `none` |
| `casf2016_3uri_vina` | `casf2016_3uri` | `vina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_3uri`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3uri_vina` | `none` |
| `casf2016_3uri_gnina` | `casf2016_3uri` | `gnina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_3uri`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3uri_gnina` | `none` |
| `casf2016_4m0z_vina` | `casf2016_4m0z` | `vina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_4m0z`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_4m0z_vina` | `none` |
| `casf2016_4m0z_gnina` | `casf2016_4m0z` | `gnina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_4m0z`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_4m0z_gnina` | `none` |
| `casf2016_4m0y_vina` | `casf2016_4m0y` | `vina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_4m0y`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_4m0y_vina` | `none` |
| `casf2016_4m0y_gnina` | `casf2016_4m0y` | `gnina` | `ready_for_engine_execution` | `resolve_vina_gnina_case_inputs_for_casf2016_4m0y`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_4m0y_gnina` | `none` |

| Engine | Container Status | Docker Daemon | Image Env Var | Image Present |
|---|---|---|---|---|
| `vina` | `container_image_not_configured` | `True` | `PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE` | `False` |
| `gnina` | `ready` | `True` | `PUBLIC_BENCHMARK_GNINA_CONTAINER_IMAGE` | `True` |

## Source Receipt Roles

| Row Input | Receipt Role | Required Receipt Fields |
|---|---|---|
| `subset_rows` | `casf_pdbbind_subset_source_receipt` | `source_license_or_accession`, `source_checksum`, `provenance_ref` |
| `pose_rows` | `casf_pdbbind_pose_coordinate_receipt` | `source_license_or_accession`, `source_checksum`, `provenance_ref`, `pose_preparation_provenance_ref` |
| `enrichment_rows` | `dud_e_or_lit_pcba_enrichment_receipt` | `source_license_or_accession`, `source_checksum`, `provenance_ref` |
| `vina_gnina_rows` | `vina_gnina_engine_comparison_receipt` | `source_license_or_accession`, `source_checksum`, `provenance_ref`, `predicted_ligand_checksum`, `engine_config_checksum`, `engine_run_provenance_ref` |

## Official Source Catalog

| Source | Family | Feeds Row Inputs | Primary URL |
|---|---|---|---|
| `pdbbind_plus_casf` | `CASF/PDBBind` | `subset_rows`, `pose_rows`, `vina_gnina_rows` | https://www.pdbbind-plus.org.cn/casf |
| `dud_e` | `DUD-E` | `enrichment_rows` | https://dude.docking.org/targets/ |
| `lit_pcba` | `LIT-PCBA` | `enrichment_rows` | https://drugdesign.unistra.fr/LIT-PCBA/ |
| `autodock_vina` | `Vina` | `vina_gnina_rows` | https://vina.scripps.edu/ |
| `gnina` | `GNINA` | `vina_gnina_rows` | https://github.com/gnina/gnina |
| `posebusters` | `PoseBusters` | `pose_rows` | https://github.com/maabuu/posebusters |

## Source Access Preflight

- `receipt_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.json`
- `receipt_command`: `python3 scripts/build_public_benchmark_source_access_preflight_receipt.py --out implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.md`
- `network_probe_command`: `python3 scripts/build_public_benchmark_source_access_preflight_receipt.py --out implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.md --probe-network`

| Source | Access Mode | Primary Probe | Fallback Probe |
|---|---|---|---|
| `pdbbind_plus_casf` | `operator_download_and_license_or_accession_receipt_required` | `curl --head --location --max-time 20 'https://www.pdbbind-plus.org.cn/casf'` | `curl --head --location --max-time 20 'https://www.pdbbind-plus.org.cn/'` |
| `dud_e` | `public_download_with_operator_checksum_receipt` | `curl --head --location --max-time 20 'https://dude.docking.org/targets/'` | `curl --head --location --max-time 20 'https://dude.docking.org/'` |
| `lit_pcba` | `public_download_with_operator_checksum_receipt` | `curl --head --location --max-time 20 'https://drugdesign.unistra.fr/LIT-PCBA/'` | `curl --head --location --max-time 20 'https://drugdesign.unistra.fr/LIT-PCBA/index.htm'` |
| `autodock_vina` | `engine_install_and_run_receipt_required` | `curl --head --location --max-time 20 'https://vina.scripps.edu/'` | `curl --head --location --max-time 20 'https://github.com/ccsb-scripps/AutoDock-Vina'` |
| `gnina` | `engine_install_and_run_receipt_required` | `curl --head --location --max-time 20 'https://github.com/gnina/gnina'` | `curl --head --location --max-time 20 'https://gnina.github.io/gnina/rsc_workshop2021/'` |
| `posebusters` | `reference_checklist_or_tool_run_receipt_required` | `curl --head --location --max-time 20 'https://github.com/maabuu/posebusters'` | `curl --head --location --max-time 20 'https://zenodo.org/records/8278563'` |

## Commands

- `write_plan`: `python3 scripts/build_public_benchmark_phase2_source_acquisition_plan.py`
- `import_operator_bundle`: `python3 scripts/materialize_public_benchmark_operator_bundle_from_rows.py --subset-rows <operator-casf-pdbbind-subset-rows.jsonl> --pose-rows <operator-pose-coordinate-rows.jsonl> --enrichment-rows <operator-dud-e-lit-pcba-scored-molecule-rows.csv> --vina-gnina-rows <operator-vina-gnina-run-rows.csv> --target-subset-case-count 12 --out implementation/phase1/release_evidence/productization/public_benchmark_operator_bundle.json`
- `phase2_row_audit`: `python3 scripts/materialize_public_benchmark_phase2_from_rows.py --fail-blocked`
- `build_vina_gnina_execution_plan`: `python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_execution_plan.json`
- `materialize_vina_gnina_input_manifest_from_template`: `python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_template.py --template implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template.csv --out-manifest implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.csv --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_from_template_report.json`
- `materialize_input_manifest_from_casf_archive`: `python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py --archive <CASF-2016.tar.gz> --out-manifest implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.csv --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_from_casf_archive_report.json --fail-blocked`
- `check_vina_gnina_runtime_readiness`: `python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_runtime_readiness.json`
- `build_vina_gnina_rows_template_preflight`: `python3 scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template_preflight.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template_preflight.md`
- `build_source_access_preflight_receipt`: `python3 scripts/build_public_benchmark_source_access_preflight_receipt.py --out implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.md`
- `probe_source_access_preflight`: `python3 scripts/build_public_benchmark_source_access_preflight_receipt.py --out implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.md --probe-network`
- `materialize_vina_gnina_adapter`: `python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py --intake <operator-vina-gnina-run-rows.csv|json|jsonl|ndjson> --out-adapter implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_comparison_adapter.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_materialization_report.json --fail-blocked`
- `materialize_harness_bundle`: `python3 scripts/materialize_public_benchmark_harness_bundle.py --bundle implementation/phase1/release_evidence/productization/public_benchmark_operator_bundle.json --out-dir implementation/phase1/release_evidence/productization --fail-blocked`
- `refresh_source_of_truth`: `python3 scripts/build_public_benchmark_source_of_truth.py --source-of-truth-out implementation/phase1/release_evidence/productization/public_benchmark_source_of_truth.json`

This plan records the operator source acquisition contract for Public Benchmark Phase 2. It does not download, redistribute, license, or synthesize CASF/PDBBind, DUD-E, LIT-PCBA, Vina, or GNINA evidence, and it does not close external beta until real rows and receipts pass the materializers.
