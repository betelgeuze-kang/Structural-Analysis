# Public Benchmark Vina/GNINA Rows Template Preflight

- `status`: `operator_rows_completion_required`
- `contract_pass`: `True`
- `adapter_template_ready`: `False`
- `template_row_count`: `24`
- `expected_engine_run_slot_count`: `24`
- `missing_required_value_count`: `144`
- `missing_engine_run_receipt_value_count`: `72`
- `missing_local_ref_count`: `48`
- `missing_numeric_value_count`: `48`
- `invalid_pose_success_count`: `24`
- `role_receipt_plan_count`: `96`
- `role_receipt_blocked_count`: `72`
- `expected_rows_detected`: `False`

## Engine Run Rows

| Slot | Case | Engine | Status | Missing Receipts | Missing Values |
|---|---|---|---|---|---|
| `casf2016_4llx_vina_casf2016_4llx_vina_run` | `casf2016_4llx` | `vina` | `operator_completion_required` | `3` | `6` |
| `casf2016_4llx_gnina_casf2016_4llx_gnina_run` | `casf2016_4llx` | `gnina` | `operator_completion_required` | `3` | `6` |
| `casf2016_5c28_vina_casf2016_5c28_vina_run` | `casf2016_5c28` | `vina` | `operator_completion_required` | `3` | `6` |
| `casf2016_5c28_gnina_casf2016_5c28_gnina_run` | `casf2016_5c28` | `gnina` | `operator_completion_required` | `3` | `6` |
| `casf2016_3uuo_vina_casf2016_3uuo_vina_run` | `casf2016_3uuo` | `vina` | `operator_completion_required` | `3` | `6` |
| `casf2016_3uuo_gnina_casf2016_3uuo_gnina_run` | `casf2016_3uuo` | `gnina` | `operator_completion_required` | `3` | `6` |
| `casf2016_3ui7_vina_casf2016_3ui7_vina_run` | `casf2016_3ui7` | `vina` | `operator_completion_required` | `3` | `6` |
| `casf2016_3ui7_gnina_casf2016_3ui7_gnina_run` | `casf2016_3ui7` | `gnina` | `operator_completion_required` | `3` | `6` |
| `casf2016_5c2h_vina_casf2016_5c2h_vina_run` | `casf2016_5c2h` | `vina` | `operator_completion_required` | `3` | `6` |
| `casf2016_5c2h_gnina_casf2016_5c2h_gnina_run` | `casf2016_5c2h` | `gnina` | `operator_completion_required` | `3` | `6` |
| `casf2016_2v00_vina_casf2016_2v00_vina_run` | `casf2016_2v00` | `vina` | `operator_completion_required` | `3` | `6` |
| `casf2016_2v00_gnina_casf2016_2v00_gnina_run` | `casf2016_2v00` | `gnina` | `operator_completion_required` | `3` | `6` |
| `casf2016_3wz8_vina_casf2016_3wz8_vina_run` | `casf2016_3wz8` | `vina` | `operator_completion_required` | `3` | `6` |
| `casf2016_3wz8_gnina_casf2016_3wz8_gnina_run` | `casf2016_3wz8` | `gnina` | `operator_completion_required` | `3` | `6` |
| `casf2016_3pww_vina_casf2016_3pww_vina_run` | `casf2016_3pww` | `vina` | `operator_completion_required` | `3` | `6` |
| `casf2016_3pww_gnina_casf2016_3pww_gnina_run` | `casf2016_3pww` | `gnina` | `operator_completion_required` | `3` | `6` |
| `casf2016_3prs_vina_casf2016_3prs_vina_run` | `casf2016_3prs` | `vina` | `operator_completion_required` | `3` | `6` |
| `casf2016_3prs_gnina_casf2016_3prs_gnina_run` | `casf2016_3prs` | `gnina` | `operator_completion_required` | `3` | `6` |
| `casf2016_3uri_vina_casf2016_3uri_vina_run` | `casf2016_3uri` | `vina` | `operator_completion_required` | `3` | `6` |
| `casf2016_3uri_gnina_casf2016_3uri_gnina_run` | `casf2016_3uri` | `gnina` | `operator_completion_required` | `3` | `6` |
| `casf2016_4m0z_vina_casf2016_4m0z_vina_run` | `casf2016_4m0z` | `vina` | `operator_completion_required` | `3` | `6` |
| `casf2016_4m0z_gnina_casf2016_4m0z_gnina_run` | `casf2016_4m0z` | `gnina` | `operator_completion_required` | `3` | `6` |
| `casf2016_4m0y_vina_casf2016_4m0y_vina_run` | `casf2016_4m0y` | `vina` | `operator_completion_required` | `3` | `6` |
| `casf2016_4m0y_gnina_casf2016_4m0y_gnina_run` | `casf2016_4m0y` | `gnina` | `operator_completion_required` | `3` | `6` |

## Receipt Role Plan

| Slot | Role | Status | Missing Fields | Invalid Fields |
|---|---|---|---|---|
| `casf2016_4llx_vina_casf2016_4llx_vina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_4llx_vina_casf2016_4llx_vina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_4llx_vina_casf2016_4llx_vina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_4llx_vina_casf2016_4llx_vina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_4llx_gnina_casf2016_4llx_gnina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_4llx_gnina_casf2016_4llx_gnina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_4llx_gnina_casf2016_4llx_gnina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_4llx_gnina_casf2016_4llx_gnina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_5c28_vina_casf2016_5c28_vina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_5c28_vina_casf2016_5c28_vina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_5c28_vina_casf2016_5c28_vina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_5c28_vina_casf2016_5c28_vina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_5c28_gnina_casf2016_5c28_gnina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_5c28_gnina_casf2016_5c28_gnina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_5c28_gnina_casf2016_5c28_gnina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_5c28_gnina_casf2016_5c28_gnina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_3uuo_vina_casf2016_3uuo_vina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_3uuo_vina_casf2016_3uuo_vina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_3uuo_vina_casf2016_3uuo_vina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_3uuo_vina_casf2016_3uuo_vina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_3uuo_gnina_casf2016_3uuo_gnina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_3uuo_gnina_casf2016_3uuo_gnina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_3uuo_gnina_casf2016_3uuo_gnina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_3uuo_gnina_casf2016_3uuo_gnina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_3ui7_vina_casf2016_3ui7_vina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_3ui7_vina_casf2016_3ui7_vina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_3ui7_vina_casf2016_3ui7_vina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_3ui7_vina_casf2016_3ui7_vina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_3ui7_gnina_casf2016_3ui7_gnina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_3ui7_gnina_casf2016_3ui7_gnina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_3ui7_gnina_casf2016_3ui7_gnina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_3ui7_gnina_casf2016_3ui7_gnina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_5c2h_vina_casf2016_5c2h_vina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_5c2h_vina_casf2016_5c2h_vina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_5c2h_vina_casf2016_5c2h_vina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_5c2h_vina_casf2016_5c2h_vina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_5c2h_gnina_casf2016_5c2h_gnina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_5c2h_gnina_casf2016_5c2h_gnina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_5c2h_gnina_casf2016_5c2h_gnina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_5c2h_gnina_casf2016_5c2h_gnina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_2v00_vina_casf2016_2v00_vina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_2v00_vina_casf2016_2v00_vina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_2v00_vina_casf2016_2v00_vina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_2v00_vina_casf2016_2v00_vina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_2v00_gnina_casf2016_2v00_gnina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_2v00_gnina_casf2016_2v00_gnina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_2v00_gnina_casf2016_2v00_gnina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_2v00_gnina_casf2016_2v00_gnina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_3wz8_vina_casf2016_3wz8_vina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_3wz8_vina_casf2016_3wz8_vina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_3wz8_vina_casf2016_3wz8_vina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_3wz8_vina_casf2016_3wz8_vina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_3wz8_gnina_casf2016_3wz8_gnina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_3wz8_gnina_casf2016_3wz8_gnina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_3wz8_gnina_casf2016_3wz8_gnina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_3wz8_gnina_casf2016_3wz8_gnina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_3pww_vina_casf2016_3pww_vina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_3pww_vina_casf2016_3pww_vina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_3pww_vina_casf2016_3pww_vina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_3pww_vina_casf2016_3pww_vina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_3pww_gnina_casf2016_3pww_gnina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_3pww_gnina_casf2016_3pww_gnina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_3pww_gnina_casf2016_3pww_gnina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_3pww_gnina_casf2016_3pww_gnina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_3prs_vina_casf2016_3prs_vina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_3prs_vina_casf2016_3prs_vina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_3prs_vina_casf2016_3prs_vina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_3prs_vina_casf2016_3prs_vina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_3prs_gnina_casf2016_3prs_gnina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_3prs_gnina_casf2016_3prs_gnina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_3prs_gnina_casf2016_3prs_gnina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_3prs_gnina_casf2016_3prs_gnina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_3uri_vina_casf2016_3uri_vina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_3uri_vina_casf2016_3uri_vina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_3uri_vina_casf2016_3uri_vina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_3uri_vina_casf2016_3uri_vina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_3uri_gnina_casf2016_3uri_gnina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_3uri_gnina_casf2016_3uri_gnina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_3uri_gnina_casf2016_3uri_gnina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_3uri_gnina_casf2016_3uri_gnina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_4m0z_vina_casf2016_4m0z_vina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_4m0z_vina_casf2016_4m0z_vina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_4m0z_vina_casf2016_4m0z_vina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_4m0z_vina_casf2016_4m0z_vina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_4m0z_gnina_casf2016_4m0z_gnina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_4m0z_gnina_casf2016_4m0z_gnina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_4m0z_gnina_casf2016_4m0z_gnina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_4m0z_gnina_casf2016_4m0z_gnina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_4m0y_vina_casf2016_4m0y_vina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_4m0y_vina_casf2016_4m0y_vina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_4m0y_vina_casf2016_4m0y_vina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_4m0y_vina_casf2016_4m0y_vina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |
| `casf2016_4m0y_gnina_casf2016_4m0y_gnina_run` | `casf_pdbbind_case_source_receipt` | `ready` | `none` | `none` |
| `casf2016_4m0y_gnina_casf2016_4m0y_gnina_run` | `engine_run_artifact_receipt` | `operator_completion_required` | `predicted_ligand_checksum` | `engine_run_provenance_ref`, `predicted_ligand_path_or_pose_ref` |
| `casf2016_4m0y_gnina_casf2016_4m0y_gnina_run` | `engine_config_version_receipt` | `operator_completion_required` | `engine_config_checksum`, `engine_version` | `none` |
| `casf2016_4m0y_gnina_casf2016_4m0y_gnina_run` | `comparison_metric_receipt` | `operator_completion_required` | `pose_success`, `score`, `symmetry_aware_rmsd_angstrom` | `none` |

## Commands

- `write_preflight`: `python3 scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template_preflight.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template_preflight.md`
- `materialize_rows_from_template`: `python3 scripts/materialize_public_benchmark_vina_gnina_rows_from_template.py --template implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template.csv --out-rows implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_from_template_report.json`
- `materialize_adapter`: `python3 scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py --intake implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json --out-adapter implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_comparison_adapter.json --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_materialization_report.json --fail-blocked`
- `rerun_phase2_row_audit`: `python3 scripts/materialize_public_benchmark_phase2_from_rows.py --vina-gnina-rows implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json --fail-blocked`

This preflight audits the Vina/GNINA adapter rows template only. It does not promote the template to actual engine output rows, run Vina or GNINA, compute symmetry-aware RMSD, synthesize pose-success labels, or close Public Benchmark Phase 2.
