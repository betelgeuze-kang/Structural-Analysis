# PocketMD Lite Top-k Rows Template Preflight

- `status`: `operator_rows_completion_required`
- `contract_pass`: `True`
- `top_k_template_ready`: `False`
- `template_row_count`: `6`
- `expected_slot_count`: `6`
- `missing_required_value_count`: `78`
- `missing_metric_value_count`: `42`
- `missing_energy_proxy_value_count`: `12`
- `missing_receipt_value_count`: `24`
- `invalid_metric_value_count`: `0`
- `invalid_energy_proxy_value_count`: `0`
- `role_receipt_blocked_count`: `24`
- `operator_input_source_receipt_blocked_count`: `5`
- `expected_rows_detected`: `False`

## Row Slots

| Slot | Case | Rank | Status | Missing Energy | Missing Metrics | Missing Receipts |
|---|---|---|---|---|---|---|
| `pocketmd_lite_case_001_rank_01` | `pocketmd_lite_case_001` | `1` | `operator_completion_required` | `2` | `7` | `4` |
| `pocketmd_lite_case_001_rank_02` | `pocketmd_lite_case_001` | `2` | `operator_completion_required` | `2` | `7` | `4` |
| `pocketmd_lite_case_002_rank_01` | `pocketmd_lite_case_002` | `1` | `operator_completion_required` | `2` | `7` | `4` |
| `pocketmd_lite_case_002_rank_02` | `pocketmd_lite_case_002` | `2` | `operator_completion_required` | `2` | `7` | `4` |
| `pocketmd_lite_case_003_rank_01` | `pocketmd_lite_case_003` | `1` | `operator_completion_required` | `2` | `7` | `4` |
| `pocketmd_lite_case_003_rank_02` | `pocketmd_lite_case_003` | `2` | `operator_completion_required` | `2` | `7` | `4` |

## Role Receipt Plan

| Candidate | Role | Status | Missing | Invalid | Action |
|---|---|---|---:|---:|---|
| `pocketmd_lite_case_001_rank_01` | `upstream_top_k_candidate_scope_receipt` | `operator_completion_required` | `2` | `0` | `attach_upstream_top_k_scope_receipt` |
| `pocketmd_lite_case_001_rank_01` | `lite_refinement_run_receipt` | `operator_completion_required` | `5` | `0` | `attach_lite_refinement_run_receipt` |
| `pocketmd_lite_case_001_rank_01` | `interaction_persistence_receipt` | `operator_completion_required` | `6` | `0` | `attach_contact_hbond_clash_metric_receipt` |
| `pocketmd_lite_case_001_rank_01` | `uncertainty_interval_receipt` | `operator_completion_required` | `4` | `0` | `attach_uncertainty_interval_receipt` |
| `pocketmd_lite_case_001_rank_02` | `upstream_top_k_candidate_scope_receipt` | `operator_completion_required` | `2` | `0` | `attach_upstream_top_k_scope_receipt` |
| `pocketmd_lite_case_001_rank_02` | `lite_refinement_run_receipt` | `operator_completion_required` | `5` | `0` | `attach_lite_refinement_run_receipt` |
| `pocketmd_lite_case_001_rank_02` | `interaction_persistence_receipt` | `operator_completion_required` | `6` | `0` | `attach_contact_hbond_clash_metric_receipt` |
| `pocketmd_lite_case_001_rank_02` | `uncertainty_interval_receipt` | `operator_completion_required` | `4` | `0` | `attach_uncertainty_interval_receipt` |
| `pocketmd_lite_case_002_rank_01` | `upstream_top_k_candidate_scope_receipt` | `operator_completion_required` | `2` | `0` | `attach_upstream_top_k_scope_receipt` |
| `pocketmd_lite_case_002_rank_01` | `lite_refinement_run_receipt` | `operator_completion_required` | `5` | `0` | `attach_lite_refinement_run_receipt` |
| `pocketmd_lite_case_002_rank_01` | `interaction_persistence_receipt` | `operator_completion_required` | `6` | `0` | `attach_contact_hbond_clash_metric_receipt` |
| `pocketmd_lite_case_002_rank_01` | `uncertainty_interval_receipt` | `operator_completion_required` | `4` | `0` | `attach_uncertainty_interval_receipt` |
| `pocketmd_lite_case_002_rank_02` | `upstream_top_k_candidate_scope_receipt` | `operator_completion_required` | `2` | `0` | `attach_upstream_top_k_scope_receipt` |
| `pocketmd_lite_case_002_rank_02` | `lite_refinement_run_receipt` | `operator_completion_required` | `5` | `0` | `attach_lite_refinement_run_receipt` |
| `pocketmd_lite_case_002_rank_02` | `interaction_persistence_receipt` | `operator_completion_required` | `6` | `0` | `attach_contact_hbond_clash_metric_receipt` |
| `pocketmd_lite_case_002_rank_02` | `uncertainty_interval_receipt` | `operator_completion_required` | `4` | `0` | `attach_uncertainty_interval_receipt` |
| `pocketmd_lite_case_003_rank_01` | `upstream_top_k_candidate_scope_receipt` | `operator_completion_required` | `2` | `0` | `attach_upstream_top_k_scope_receipt` |
| `pocketmd_lite_case_003_rank_01` | `lite_refinement_run_receipt` | `operator_completion_required` | `5` | `0` | `attach_lite_refinement_run_receipt` |
| `pocketmd_lite_case_003_rank_01` | `interaction_persistence_receipt` | `operator_completion_required` | `6` | `0` | `attach_contact_hbond_clash_metric_receipt` |
| `pocketmd_lite_case_003_rank_01` | `uncertainty_interval_receipt` | `operator_completion_required` | `4` | `0` | `attach_uncertainty_interval_receipt` |
| `pocketmd_lite_case_003_rank_02` | `upstream_top_k_candidate_scope_receipt` | `operator_completion_required` | `2` | `0` | `attach_upstream_top_k_scope_receipt` |
| `pocketmd_lite_case_003_rank_02` | `lite_refinement_run_receipt` | `operator_completion_required` | `5` | `0` | `attach_lite_refinement_run_receipt` |
| `pocketmd_lite_case_003_rank_02` | `interaction_persistence_receipt` | `operator_completion_required` | `6` | `0` | `attach_contact_hbond_clash_metric_receipt` |
| `pocketmd_lite_case_003_rank_02` | `uncertainty_interval_receipt` | `operator_completion_required` | `4` | `0` | `attach_uncertainty_interval_receipt` |

## Operator Input Source Receipt Plan

| Field | Status | Blocker | Action |
|---|---|---|---|
| `source_id` | `operator_completion_required` | `source_id_required` | `attach_operator_input_source_source_id` |
| `source_url` | `operator_completion_required` | `source_url_required` | `attach_operator_input_source_source_url` |
| `source_license` | `operator_completion_required` | `source_license_required` | `attach_operator_input_source_source_license` |
| `source_artifact` | `operator_completion_required` | `source_artifact_missing` | `write_pocketmd_lite_topk_rows_at_expected_artifact` |
| `source_artifact_sha256` | `operator_completion_required` | `source_artifact_sha256_required` | `compute_source_artifact_sha256_after_rows_written` |

## Commands

- `write_preflight`: `python3 scripts/build_pocketmd_lite_topk_rows_template_preflight.py --out implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.json --out-md implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.md`
- `import_rows`: `python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py --rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --out implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --source-id <source-id> --source-url <source-url> --source-license <license>`
- `materialize_survival_report`: `python3 scripts/materialize_pocketmd_lite_topk_survival_report.py --intake implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --contract implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json --out-report implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.json --out-surface implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json --fail-blocked`
- `rerun_refinement_execution_plan`: `python3 scripts/build_pocketmd_lite_refinement_execution_plan.py --out implementation/phase1/release_evidence/productization/pocketmd_lite_refinement_execution_plan.json`
- `rerun_science_actual_closure`: `python3 scripts/materialize_science_actual_closure_from_rows.py --pocketmd-rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --source-id <source-id> --source-url <source-url> --source-license <license> --fail-blocked`

This preflight audits the PocketMD Lite top-k rows template only. It does not promote the template to actual row evidence, run bounded refinement, synthesize local-min, contact, H-bond, clash, or uncertainty metrics, or close PocketMD Lite Phase 4.
