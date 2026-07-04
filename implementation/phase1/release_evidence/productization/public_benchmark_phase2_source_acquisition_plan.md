# Public Benchmark Phase 2 Source Acquisition Plan

- `status`: `operator_acquisition_required`
- `contract_pass`: `True`
- `phase2_ready`: `False`
- `actual_closure_ready`: `False`
- `blocker_count`: `5`
- `official_source_receipt_plan_status`: `operator_receipts_required`
- `official_source_receipt_role_count`: `4`
- `official_source_catalog_count`: `6`
- `phase2_row_audit`: `implementation/phase1/release_evidence/productization/public_benchmark_phase2_row_audit.json`
- `phase2_row_audit_status`: `operator_evidence_required`
- `phase2_row_audit_missing_row_inputs`: `vina_gnina_rows`
- `phase2_row_audit_source_actuality_scope`: `provided_row_inputs_only`
- `phase2_row_audit_source_actuality_contract_pass`: `True`
- `phase2_row_audit_source_actuality_blocker_count`: `0`
- `phase2_exit_criterion_count`: `5`
- `phase2_row_closure_matrix_count`: `4`
- `missing_row_input_action_count`: `1`
- `vina_gnina_execution_plan`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_execution_plan.json`
- `vina_gnina_execution_plan_status`: `engine_input_blocked`
- `vina_gnina_required_engine_run_count`: `24`
- `vina_gnina_input_manifest_status`: `not_detected`
- `vina_gnina_input_manifest_row_count`: `0`
- `vina_gnina_runtime_readiness`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_runtime_readiness.json`
- `vina_gnina_runtime_readiness_status`: `execution_plan_blocked`
- `vina_gnina_runtime_ready_engine_run_slot_count`: `0`
- `vina_gnina_runtime_case_input_slot_count`: `12`
- `vina_gnina_runtime_blocked_case_input_slot_count`: `12`
- `vina_gnina_runtime_engine_run_slot_count`: `24`
- `vina_gnina_runtime_blocked_engine_run_slot_count`: `24`
- `vina_gnina_adapter_row_preflight_status`: `row_artifact_missing`
- `vina_gnina_runtime_missing_engine_ids`: `vina, gnina`

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
| `vina_gnina_comparison_ready` | `vina_gnina_comparison_adapter` | `False` | `{"contract_pass": false, "ready": false, "real_comparison_case_count": 0}` | `{"contract_pass": true, "ready": true, "real_comparison_case_count": 1}` | `vina_gnina_rows_not_provided` |
| `dud_e_or_lit_pcba_enrichment_ready` | `dud_e_or_lit_pcba_enrichment` | `True` | `{"contract_pass": true, "ready": true, "real_enrichment_target_count": 1}` | `{"contract_pass": true, "ready": true, "real_enrichment_target_count": 1}` | `none` |

## Phase 2 Row Closure Matrix

| Row Input | Status | Closes Criteria | Components | Materialization Chain |
|---|---|---|---|---|
| `subset_rows` | `provided` | `casf_pdbbind_pose_success_harness_ready` | `casf_pdbbind_pose_success_harness` | `materialize_public_benchmark_subset_manifest`, `validate_public_benchmark_subset_manifest`, `materialize_public_benchmark_pose_validity_input`, `materialize_public_benchmark_pose_success_harness` |
| `pose_rows` | `provided` | `casf_pdbbind_pose_success_harness_ready`, `symmetry_aware_ligand_rmsd_ready`, `posebusters_style_pose_validity_ready` | `symmetry_aware_ligand_rmsd`, `posebusters_style_pose_validity`, `casf_pdbbind_pose_success_harness` | `materialize_public_benchmark_pose_validity_input`, `validate_public_benchmark_pose_validity`, `materialize_public_benchmark_posebusters_validity_packet`, `materialize_public_benchmark_rmsd_scorecard`, `materialize_public_benchmark_pose_success_harness` |
| `enrichment_rows` | `provided` | `dud_e_or_lit_pcba_enrichment_ready` | `dud_e_or_lit_pcba_enrichment` | `materialize_public_benchmark_enrichment_scorecard` |
| `vina_gnina_rows` | `missing` | `vina_gnina_comparison_ready` | `vina_gnina_comparison_adapter` | `materialize_public_benchmark_vina_gnina_comparison_adapter` |

## Missing Row Input Actions

| Row Input | Action | Closes Phase 2 Criteria | Unblocks | Materialization | Direct Adapter |
|---|---|---|---|---|---|
| `vina_gnina_rows` | `attach_vina_gnina_rows_then_run_phase2_row_audit` | `vina_gnina_comparison_ready` | `vina_gnina_comparison_adapter` | `python3 scripts/materialize_public_benchmark_phase2_from_rows.py --fail-blocked` | `python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py --intake <operator-vina-gnina-run-rows.csv|json|jsonl|ndjson> --out-adapter implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_comparison_adapter.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_materialization_report.json --fail-blocked` |

### Vina/GNINA Input Manifest Action

- `status`: `operator_manifest_required`
- `template_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template.csv`
- `expected_manifest_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.csv`
- `template_to_manifest_command`: `cp implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template.csv implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.csv`
- `verify_execution_plan_command`: `python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_execution_plan.json`
- `verify_runtime_readiness_command`: `python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_runtime_readiness.json`
- `operator_must_fill_or_verify`: `prepared_receptor_path`, `prepared_receptor_checksum`, `prepared_ligand_path`, `prepared_ligand_checksum`, `vina_config_ref`, `gnina_config_ref`, `vina_run_receipt_ref`, `gnina_run_receipt_ref`, `input_preparation_provenance_ref`
- `template_is_not_evidence`: `True`
- `do_not_treat_blank_prepared_checksums_as_ready`: `True`

### Vina/GNINA Adapter Row Preflight Action

- `status`: `row_artifact_missing`
- `expected_rows_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json`
- `supported_candidate_paths`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json`, `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.jsonl`, `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.ndjson`, `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.csv`
- `detected_row_artifact_count`: `0`
- `selected_path`: ``
- `adapter_preflight_status`: `missing`
- `adapter_preflight_blockers`: `none`
- `direct_adapter_materialization_command`: `python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py --intake <operator-vina-gnina-run-rows.csv|json|jsonl|ndjson> --out-adapter implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_comparison_adapter.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_materialization_report.json --fail-blocked`
- `operator_rows_must_be_real_engine_outputs`: `True`
- `preflight_does_not_run_engines`: `True`

## Vina/GNINA Runtime

- `operator_unblock_status`: `engine_inputs_required`
- `input_manifest_template_artifact`: `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template.csv`
- `blocked_case_input_slot_count`: `12`
- `blocked_engine_run_slot_count`: `24`
- `adapter_row_preflight_status`: `row_artifact_missing`

### Vina/GNINA Case Input Slots

| Slot | Case | Complex | Status | Action | Blockers |
|---|---|---|---|---|---|
| `casf2016_2v00_case_inputs` | `casf2016_2v00` | `2v00` | `blocked` | `fill_vina_gnina_input_manifest_row_for_casf2016_2v00` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing` |
| `casf2016_3prs_case_inputs` | `casf2016_3prs` | `3prs` | `blocked` | `fill_vina_gnina_input_manifest_row_for_casf2016_3prs` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing` |
| `casf2016_3pww_case_inputs` | `casf2016_3pww` | `3pww` | `blocked` | `fill_vina_gnina_input_manifest_row_for_casf2016_3pww` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing` |
| `casf2016_3ui7_case_inputs` | `casf2016_3ui7` | `3ui7` | `blocked` | `fill_vina_gnina_input_manifest_row_for_casf2016_3ui7` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing` |
| `casf2016_3uri_case_inputs` | `casf2016_3uri` | `3uri` | `blocked` | `fill_vina_gnina_input_manifest_row_for_casf2016_3uri` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing` |
| `casf2016_3uuo_case_inputs` | `casf2016_3uuo` | `3uuo` | `blocked` | `fill_vina_gnina_input_manifest_row_for_casf2016_3uuo` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing` |
| `casf2016_3wz8_case_inputs` | `casf2016_3wz8` | `3wz8` | `blocked` | `fill_vina_gnina_input_manifest_row_for_casf2016_3wz8` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing` |
| `casf2016_4llx_case_inputs` | `casf2016_4llx` | `4llx` | `blocked` | `fill_vina_gnina_input_manifest_row_for_casf2016_4llx` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing` |
| `casf2016_4m0y_case_inputs` | `casf2016_4m0y` | `4m0y` | `blocked` | `fill_vina_gnina_input_manifest_row_for_casf2016_4m0y` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing` |
| `casf2016_4m0z_case_inputs` | `casf2016_4m0z` | `4m0z` | `blocked` | `fill_vina_gnina_input_manifest_row_for_casf2016_4m0z` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing` |
| `casf2016_5c28_case_inputs` | `casf2016_5c28` | `5c28` | `blocked` | `fill_vina_gnina_input_manifest_row_for_casf2016_5c28` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing` |
| `casf2016_5c2h_case_inputs` | `casf2016_5c2h` | `5c2h` | `blocked` | `fill_vina_gnina_input_manifest_row_for_casf2016_5c2h` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing` |

### Vina/GNINA Engine Run Slots

| Slot | Case | Engine | Status | Actions | Blockers |
|---|---|---|---|---|---|
| `casf2016_4llx_vina` | `casf2016_4llx` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_4llx`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_4llx_vina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `vina_binary_missing` |
| `casf2016_4llx_gnina` | `casf2016_4llx` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_4llx`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_4llx_gnina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `gnina_binary_missing` |
| `casf2016_5c28_vina` | `casf2016_5c28` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_5c28`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_5c28_vina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `vina_binary_missing` |
| `casf2016_5c28_gnina` | `casf2016_5c28` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_5c28`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_5c28_gnina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `gnina_binary_missing` |
| `casf2016_3uuo_vina` | `casf2016_3uuo` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3uuo`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3uuo_vina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `vina_binary_missing` |
| `casf2016_3uuo_gnina` | `casf2016_3uuo` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3uuo`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3uuo_gnina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `gnina_binary_missing` |
| `casf2016_3ui7_vina` | `casf2016_3ui7` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3ui7`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3ui7_vina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `vina_binary_missing` |
| `casf2016_3ui7_gnina` | `casf2016_3ui7` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3ui7`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3ui7_gnina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `gnina_binary_missing` |
| `casf2016_5c2h_vina` | `casf2016_5c2h` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_5c2h`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_5c2h_vina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `vina_binary_missing` |
| `casf2016_5c2h_gnina` | `casf2016_5c2h` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_5c2h`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_5c2h_gnina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `gnina_binary_missing` |
| `casf2016_2v00_vina` | `casf2016_2v00` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_2v00`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_2v00_vina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `vina_binary_missing` |
| `casf2016_2v00_gnina` | `casf2016_2v00` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_2v00`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_2v00_gnina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `gnina_binary_missing` |
| `casf2016_3wz8_vina` | `casf2016_3wz8` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3wz8`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3wz8_vina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `vina_binary_missing` |
| `casf2016_3wz8_gnina` | `casf2016_3wz8` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3wz8`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3wz8_gnina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `gnina_binary_missing` |
| `casf2016_3pww_vina` | `casf2016_3pww` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3pww`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3pww_vina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `vina_binary_missing` |
| `casf2016_3pww_gnina` | `casf2016_3pww` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3pww`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3pww_gnina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `gnina_binary_missing` |
| `casf2016_3prs_vina` | `casf2016_3prs` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3prs`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3prs_vina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `vina_binary_missing` |
| `casf2016_3prs_gnina` | `casf2016_3prs` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3prs`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3prs_gnina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `gnina_binary_missing` |
| `casf2016_3uri_vina` | `casf2016_3uri` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3uri`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3uri_vina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `vina_binary_missing` |
| `casf2016_3uri_gnina` | `casf2016_3uri` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_3uri`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_3uri_gnina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `gnina_binary_missing` |
| `casf2016_4m0z_vina` | `casf2016_4m0z` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_4m0z`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_4m0z_vina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `vina_binary_missing` |
| `casf2016_4m0z_gnina` | `casf2016_4m0z` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_4m0z`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_4m0z_gnina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `gnina_binary_missing` |
| `casf2016_4m0y_vina` | `casf2016_4m0y` | `vina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_4m0y`, `configure_vina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_4m0y_vina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `vina_binary_missing` |
| `casf2016_4m0y_gnina` | `casf2016_4m0y` | `gnina` | `blocked` | `resolve_vina_gnina_case_inputs_for_casf2016_4m0y`, `configure_gnina_runtime`, `attach_vina_gnina_adapter_row_for_casf2016_4m0y_gnina` | `protein_structure_path_missing`, `reference_ligand_path_missing`, `prepared_receptor_path_missing`, `prepared_ligand_path_missing`, `gnina_binary_missing` |

| Engine | Container Status | Docker Daemon | Image Env Var | Image Present |
|---|---|---|---|---|
| `vina` | `container_image_not_configured` | `True` | `PUBLIC_BENCHMARK_VINA_CONTAINER_IMAGE` | `False` |
| `gnina` | `container_image_not_configured` | `True` | `PUBLIC_BENCHMARK_GNINA_CONTAINER_IMAGE` | `False` |

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

## Commands

- `write_plan`: `python3 scripts/build_public_benchmark_phase2_source_acquisition_plan.py`
- `import_operator_bundle`: `python3 scripts/materialize_public_benchmark_operator_bundle_from_rows.py --subset-rows <operator-casf-pdbbind-subset-rows.jsonl> --pose-rows <operator-pose-coordinate-rows.jsonl> --enrichment-rows <operator-dud-e-lit-pcba-scored-molecule-rows.csv> --vina-gnina-rows <operator-vina-gnina-run-rows.csv> --target-subset-case-count 12 --out implementation/phase1/release_evidence/productization/public_benchmark_operator_bundle.json`
- `phase2_row_audit`: `python3 scripts/materialize_public_benchmark_phase2_from_rows.py --fail-blocked`
- `build_vina_gnina_execution_plan`: `python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_execution_plan.json`
- `check_vina_gnina_runtime_readiness`: `python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_runtime_readiness.json`
- `materialize_vina_gnina_adapter`: `python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py --intake <operator-vina-gnina-run-rows.csv|json|jsonl|ndjson> --out-adapter implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_comparison_adapter.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_materialization_report.json --fail-blocked`
- `materialize_harness_bundle`: `python3 scripts/materialize_public_benchmark_harness_bundle.py --bundle implementation/phase1/release_evidence/productization/public_benchmark_operator_bundle.json --out-dir implementation/phase1/release_evidence/productization --fail-blocked`
- `refresh_source_of_truth`: `python3 scripts/build_public_benchmark_source_of_truth.py --source-of-truth-out implementation/phase1/release_evidence/productization/public_benchmark_source_of_truth.json`

This plan records the operator source acquisition contract for Public Benchmark Phase 2. It does not download, redistribute, license, or synthesize CASF/PDBBind, DUD-E, LIT-PCBA, Vina, or GNINA evidence, and it does not close external beta until real rows and receipts pass the materializers.
