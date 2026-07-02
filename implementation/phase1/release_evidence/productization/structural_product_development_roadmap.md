# Structural Product Development Roadmap

Structural product roadmap: BLOCKED | evidence_progress=64.6% | stage_average=53.2% | ready_stages=1/7 | primary_blocker=basic_ci::pr_ci_30_consecutive_pass_evidence_missing

## Current Position

- `developer_preview_final_gates`: `6/9`
- `g1_direct_residual_terminal_gate_ready`: `True`
- `g1_full_load_hip_newton_lane_ready`: `False`
- `limited_commercial_ready`: `False`
- `paid_pilot_ready`: `False`
- `pm_milestones`: `5/5`
- `pm_release_areas`: `13/16`
- `release_ready`: `False`
- `snapshot_blocker_count`: `69`
- `snapshot_status`: `blocked`
- `workstation_delivery_ready`: `True`

## Roadmap Stages

- `evidence_freshness_and_snapshot_integrity`: ready (3/3, 100.0%)
  - next action: `keep_release_evidence_freshness_report_green`
- `pm_release_gate`: partial (18/21, 85.7%)
  - first blocker: `basic_ci::pr_ci_30_consecutive_pass_evidence_missing`
  - next action: `collect_30_pr_ci_and_nightly_ci_streak_evidence`
- `developer_preview_rc`: partial (6/9, 66.7%)
  - first blocker: `selected_medium_models_pass_or_approved_review::medium_structural_models_current_below_required:2/5`
  - next action: `close_medium_model_pass_or_approved_review_gate`
- `g1_solver_closure`: partial (1/2, 50.0%)
  - first blocker: `auto_select_no_loadable_candidates`
  - next action: `generate_full_load_1p0_checkpoint_candidate`
- `paid_pilot_readiness`: partial (1/4, 25.0%)
  - first blocker: `customer_shadow_below_required:0/3`
  - next action: `complete_3_customer_shadow_cases`
- `commercial_solver_claim_upgrade`: partial (1/5, 20.0%)
  - first blocker: `independent_product_not_ready`
  - next action: `close_external_benchmark_receipts`
- `enterprise_productization`: partial (1/4, 25.0%)
  - first blocker: `independent_product_ready_false`
  - next action: `add_durable_queue_postgres_and_object_storage_receipts`

## Recommended Next Slices

- `land_ci_license_ux_release_area_evidence`
  - exit condition: 30 consecutive PR CI passes recorded
  - current `ci_nightly_consecutive_pass_count`: `0`
- `close_developer_preview_medium_large_and_parity_gates`
  - exit condition: five selected medium models have PASS or approved REVIEW receipts
  - current `developer_preview_final_gates`: `6/9`
- `continue_g1_full_load_hip_newton_from_consistent_residual_jacobian_path`
  - exit condition: full-load 1.0 checkpoint passes residual and increment gates
  - current `active_terminal_requirement`: `full_load_checkpoint_1p0`
- `collect_customer_shadow_and_external_benchmark_terminal_receipts`
  - exit condition: three customer shadow cases have reviewed terminal rows
  - current `completed_shadow_case_count`: `0`

## Claim Boundary

This surface summarizes current evidence-readiness progress for the structural solver product. It is not a product-complete, paid-pilot, limited-commercial, or GA/enterprise claim while any stage remains blocked.
