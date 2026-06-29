# GPCR Hard-Decoy Operator Intake Packet

- `contract_pass`: `True`
- `status`: `ready_for_operator_input`
- `broad_gpcr_family_claim_safe`: `False`
- `first_blocked_target`: `DRD2`
- `claim_boundary`: This packet is an owner-facing intake contract for GPCR hard-decoy metrics. It does not generate docking results, infer missing values, or promote broad GPCR claims. DRD2, HTR2A, and OPRM1 must all pass the numeric exit criteria.

| Target | Status | Required Fields |
|---|---|---|
| `DRD2` | `operator_input_required` | `target_id, ranking_pr_auc_ci_low, top20_hit_rate, decoys_above_positive_count, positive_out_anchored_by_top_decoys` |
| `HTR2A` | `operator_input_required` | `target_id, ranking_pr_auc_ci_low, top20_hit_rate, decoys_above_positive_count, positive_out_anchored_by_top_decoys` |
| `OPRM1` | `operator_input_required` | `target_id, ranking_pr_auc_ci_low, top20_hit_rate, decoys_above_positive_count, positive_out_anchored_by_top_decoys` |

## Gate Unblock Plan

| Target | Criteria | Minimum Evidence |
|---|---|---|
| `DRD2` | `ranking_pr_auc_ci_low_min`, `top20_hit_rate_min`, `decoys_above_positive_count_max`, `no_positive_out_anchored_by_top_decoys` | `{"criterion_by_field": {"decoys_above_positive_count": "decoys_above_positive_count_max", "positive_out_anchored_by_top_decoys": "no_positive_out_anchored_by_top_decoys", "ranking_pr_auc_ci_low": "ranking_pr_auc_ci_low_min", "top20_hit_rate": "top20_hit_rate_min"}, "required_operator_fields": ["target_id", "ranking_pr_auc_ci_low", "top20_hit_rate", "decoys_above_positive_count", "positive_out_anchored_by_top_decoys"], "target_id": "DRD2", "thresholds": {"decoys_above_positive_count": "<=0", "positive_out_anchored_by_top_decoys": false, "ranking_pr_auc_ci_low": ">=0.45", "top20_hit_rate": ">=0.2"}}` |
| `HTR2A` | `ranking_pr_auc_ci_low_min`, `top20_hit_rate_min`, `decoys_above_positive_count_max`, `no_positive_out_anchored_by_top_decoys` | `{"criterion_by_field": {"decoys_above_positive_count": "decoys_above_positive_count_max", "positive_out_anchored_by_top_decoys": "no_positive_out_anchored_by_top_decoys", "ranking_pr_auc_ci_low": "ranking_pr_auc_ci_low_min", "top20_hit_rate": "top20_hit_rate_min"}, "required_operator_fields": ["target_id", "ranking_pr_auc_ci_low", "top20_hit_rate", "decoys_above_positive_count", "positive_out_anchored_by_top_decoys"], "target_id": "HTR2A", "thresholds": {"decoys_above_positive_count": "<=0", "positive_out_anchored_by_top_decoys": false, "ranking_pr_auc_ci_low": ">=0.45", "top20_hit_rate": ">=0.2"}}` |
| `OPRM1` | `ranking_pr_auc_ci_low_min`, `top20_hit_rate_min`, `decoys_above_positive_count_max`, `no_positive_out_anchored_by_top_decoys` | `{"criterion_by_field": {"decoys_above_positive_count": "decoys_above_positive_count_max", "positive_out_anchored_by_top_decoys": "no_positive_out_anchored_by_top_decoys", "ranking_pr_auc_ci_low": "ranking_pr_auc_ci_low_min", "top20_hit_rate": "top20_hit_rate_min"}, "required_operator_fields": ["target_id", "ranking_pr_auc_ci_low", "top20_hit_rate", "decoys_above_positive_count", "positive_out_anchored_by_top_decoys"], "target_id": "OPRM1", "thresholds": {"decoys_above_positive_count": "<=0", "positive_out_anchored_by_top_decoys": false, "ranking_pr_auc_ci_low": ">=0.45", "top20_hit_rate": ">=0.2"}}` |

## Materialization Sequence

- `fill_gpcr_hard_decoy_operator_template`: `edit implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_template.json`
- `materialize_gpcr_hard_decoy_suite_report`: `python3 scripts/materialize_gpcr_hard_decoy_suite_report.py --intake implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_template.json --out-report implementation/phase1/release_evidence/productization/gpcr_hard_decoy_suite_report.json --out-surface implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json --fail-blocked`
- `refresh_gpcr_hard_decoy_product_report`: `python3 scripts/build_gpcr_hard_decoy_product_report.py --out implementation/phase1/release_evidence/productization/gpcr_hard_decoy_product_report.json`
- `refresh_product_capabilities_surface`: `python3 scripts/build_product_capabilities_surface.py --out implementation/phase1/release_evidence/surface/product_capabilities_surface.json`
- `refresh_goal_bottleneck_roadmap_surface`: `python3 scripts/build_goal_bottleneck_roadmap_surface.py --out implementation/phase1/release_evidence/productization/goal_bottleneck_roadmap_surface.json`

## Acceptance Criteria

- `gpcr_hard_decoy_suite_report.target_pass_count == 3`
- `gpcr_hard_decoy_suite_report.broad_gpcr_family_claim_safe == true`
- `gpcr_hard_decoy_suite_report.blockers == []`
- `gpcr_hard_decoy_product_report.science_claim_status == ready`
- `gpcr_hard_decoy_evidence_surface.locked == false`
