# Non-Expert Release Briefing

Status: `ready_release_blocked`
Release allowed: `False`
Primary blocker: `basic_ci::pr_ci_30_consecutive_pass_evidence_missing`

## Plain Status

Release is blocked. The product can remain in restricted alpha/beta preparation, but it must not be presented as fully release-ready.

## Human UX Gate

- Status: `blocked`
- Owner action: attach a passing human new-user observation record before claiming the UX release-area gate
- Workflow steps passed: `0/5`

## Science And Beta Blockers

- `phase_2_public_benchmark_harness`: Public benchmark harness blocked by `casf_pdbbind_source_material_not_attached`
- `phase_3_gpcr_hard_decoy_closure`: GPCR hard-decoy closure blocked by `DRD2:ranking_pr_auc_ci_low_required`
- `phase_4_pocketmd_lite`: PocketMD Lite science product surface blocked by `pocketmd_lite_topk_candidate_rows_missing`

## First Owner Handoff

- Slot: `casf_pdbbind_subset_intake`
- Action: attach at least 12 local CASF/PDBBind case descriptors
- Template: `implementation/phase1/release_evidence/productization/public_benchmark_casf_pdbbind_operator_template.json`

## Claim Boundaries

- `do_not_claim_limited_commercial_release_until_release_allowed_true`
- `do_not_claim_tier_beta_until_public_benchmark_ready_true`
- `do_not_claim_broad_gpcr_until_broad_gpcr_family_claim_safe_true`
- `do_not_claim_pocketmd_lite_ready_until_product_surface_ready_true`
- `do_not_replace_human_ux_observation_with_templates_or_automation`

## Report Boundary

This report is a plain-language read model over /goal bottleneck evidence. It does not create new release evidence, close human UX observation, attach public benchmark data, or unlock GPCR/PocketMD science claims.
