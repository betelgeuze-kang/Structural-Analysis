# PocketMD Lite Source Acquisition Plan

- `status`: `operator_acquisition_required`
- `contract_pass`: `True`
- `actual_closure_ready`: `False`
- `blocker_count`: `3`
- `phase4_refinement_receipt_plan_status`: `operator_receipts_required`
- `phase4_refinement_receipt_role_count`: `4`

| Case | Minimum Rows | Required Rank Prefix | Scope |
|---|---:|---|---|
| `pocketmd_lite_case_001` | 2 | `1,2` | `upstream_ranked_top_k_candidates_only` |
| `pocketmd_lite_case_002` | 2 | `1,2` | `upstream_ranked_top_k_candidates_only` |
| `pocketmd_lite_case_003` | 2 | `1,2` | `upstream_ranked_top_k_candidates_only` |

## Phase 4 Receipt Roles

| Receipt Role | Source Role | Closes Criteria |
|---|---|---|
| `upstream_top_k_candidate_scope_receipt` | `upstream_ranked_top_k_candidate_set` | `top_k_refinement_rows_present`, `top_k_refinement_case_coverage` |
| `lite_refinement_run_receipt` | `bounded_lite_refinement_run` | `local_min_survival_materialized`, `report_blockers_resolved` |
| `interaction_persistence_receipt` | `contact_hbond_clash_metric_rows` | `contact_persistence_materialized`, `h_bond_persistence_materialized`, `clash_relief_materialized`, `report_blockers_resolved` |
| `uncertainty_interval_receipt` | `candidate_uncertainty_interval_rows` | `uncertainty_summary_materialized`, `report_blockers_resolved` |

## Commands

- `write_plan`: `python3 scripts/build_pocketmd_lite_source_acquisition_plan.py`
- `import_rows`: `python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py --rows implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json --out implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --source-id <source-id> --source-url <source-url> --source-license <license>`
- `materialize_survival`: `python3 scripts/materialize_pocketmd_lite_topk_survival_report.py --intake implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json --contract implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json --out-report implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.json --out-surface implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json --fail-blocked`
- `science_actual_closure`: `python3 scripts/materialize_science_actual_closure_from_rows.py --fail-blocked`

This plan records the row, metric, and receipt contract needed to acquire PocketMD Lite top-k refinement evidence. It does not synthesize rows, run Lite refinement, infer missing metrics, or unlock broad all-atom MD/FEP claims before the materializer verifies real operator evidence.
