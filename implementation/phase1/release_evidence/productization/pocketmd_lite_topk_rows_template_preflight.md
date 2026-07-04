# PocketMD Lite Top-k Rows Template Preflight

- `status`: `operator_rows_completion_required`
- `contract_pass`: `True`
- `top_k_template_ready`: `False`
- `template_row_count`: `6`
- `expected_slot_count`: `6`
- `missing_required_value_count`: `78`
- `missing_metric_value_count`: `42`
- `missing_receipt_value_count`: `24`
- `invalid_metric_value_count`: `0`
- `expected_rows_detected`: `False`

## Row Slots

| Slot | Case | Rank | Status | Missing Metrics | Missing Receipts |
|---|---|---|---|---|---|
| `pocketmd_lite_case_001_rank_01` | `pocketmd_lite_case_001` | `1` | `operator_completion_required` | `7` | `4` |
| `pocketmd_lite_case_001_rank_02` | `pocketmd_lite_case_001` | `2` | `operator_completion_required` | `7` | `4` |
| `pocketmd_lite_case_002_rank_01` | `pocketmd_lite_case_002` | `1` | `operator_completion_required` | `7` | `4` |
| `pocketmd_lite_case_002_rank_02` | `pocketmd_lite_case_002` | `2` | `operator_completion_required` | `7` | `4` |
| `pocketmd_lite_case_003_rank_01` | `pocketmd_lite_case_003` | `1` | `operator_completion_required` | `7` | `4` |
| `pocketmd_lite_case_003_rank_02` | `pocketmd_lite_case_003` | `2` | `operator_completion_required` | `7` | `4` |

## Commands

- `write_preflight`: `python3 scripts/build_pocketmd_lite_topk_rows_template_preflight.py --out implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.json --out-md implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.md`
- `import_rows`: `python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py --rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --out implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --source-id <source-id> --source-url <source-url> --source-license <license>`
- `materialize_survival_report`: `python3 scripts/materialize_pocketmd_lite_topk_survival_report.py --intake implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --contract implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json --out-report implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.json --out-surface implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json --fail-blocked`
- `rerun_refinement_execution_plan`: `python3 scripts/build_pocketmd_lite_refinement_execution_plan.py --out implementation/phase1/release_evidence/productization/pocketmd_lite_refinement_execution_plan.json`
- `rerun_science_actual_closure`: `python3 scripts/materialize_science_actual_closure_from_rows.py --pocketmd-rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --source-id <source-id> --source-url <source-url> --source-license <license> --fail-blocked`

This preflight audits the PocketMD Lite top-k rows template only. It does not promote the template to actual row evidence, run bounded refinement, synthesize local-min, contact, H-bond, clash, or uncertainty metrics, or close PocketMD Lite Phase 4.
