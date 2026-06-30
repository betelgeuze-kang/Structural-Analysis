# PocketMD Lite Operator Intake Packet

- `contract_pass`: `True`
- `status`: `ready_for_operator_input`
- `product_surface_ready`: `False`
- `first_blocked_target`: `top_k_refinement_operator_intake`
- `claim_boundary`: This packet is an owner-facing intake contract for bounded PocketMD Lite top-k refinement rows. It does not run MD, infer missing metrics, or unlock broad all-atom MD/FEP claims.

| Slot | Status | Required Fields |
|---|---|---|
| `top_k_refinement_rows` | `operator_input_required` | `case_id, source_family, top_k_rank, candidate_id, pre_refinement_energy_proxy, post_refinement_energy_proxy, local_min_survived, contact_persistence_rate, h_bond_persistence_rate, clash_count_before, clash_count_after, uncertainty_interval, provenance_ref, source_checksum` |

## Gate Unblock Plan

| Slot | Criteria | Minimum Evidence |
|---|---|---|
| `top_k_refinement_rows` | `top_k_refinement_rows_present`, `local_min_survival_materialized`, `contact_persistence_materialized`, `h_bond_persistence_materialized`, `clash_relief_materialized`, `uncertainty_summary_materialized`, `report_blockers_resolved` | `{"candidate_scope": "upstream_ranked_top_k_candidates_only", "operator_input_source_receipt_policy": {"required_mode": "raw_top_k_refinement_rows", "required_operator_input_source_fields": ["mode", "source_artifact", "source_artifact_sha256", "source_id", "source_url", "source_license"], "source_artifact_sha256_policy": "sha256:<64 lowercase or uppercase hex characters>"}, "raw_row_supported_formats": ["csv", "tsv", "json", "jsonl", "ndjson"], "real_refinement_case_count": 1, "receipt_fields": ["provenance_ref", "source_checksum", "operator_input_source.source_artifact", "operator_input_source.source_artifact_sha256", "operator_input_source.source_id", "operator_input_source.source_url", "operator_input_source.source_license"], "required_case_fields": ["case_id", "source_family", "top_k_rank", "candidate_id", "pre_refinement_energy_proxy", "post_refinement_energy_proxy", "local_min_survived", "contact_persistence_rate", "h_bond_persistence_rate", "clash_count_before", "clash_count_after", "uncertainty_interval", "provenance_ref", "source_checksum"], "source_checksum_policy": {"accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>", "required_receipt_field": "source_checksum"}, "top_k_candidate_count": 1}` |

## Materialization Sequence

- `materialize_pocketmd_lite_operator_intake_from_rows`: `python3 scripts/materialize_pocketmd_lite_operator_intake_from_rows.py --rows <operator-pocketmd-lite-refinement-rows.csv|tsv|json|jsonl|ndjson> --out <operator-pocketmd-lite-intake.json> --source-id <source-id> --source-url <source-url> --source-license <license>`
- `fill_pocketmd_lite_operator_intake_packet`: `create <operator-pocketmd-lite-intake.json> from implementation/phase1/release_evidence/productization/pocketmd_lite_operator_template.json`
- `materialize_pocketmd_lite_topk_survival_report`: `python3 scripts/materialize_pocketmd_lite_topk_survival_report.py --intake <operator-pocketmd-lite-intake.json> --contract implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json --out-report implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.json --out-surface implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json --fail-blocked`
- `refresh_product_capabilities_surface`: `python3 scripts/build_product_capabilities_surface.py --out implementation/phase1/release_evidence/surface/product_capabilities_surface.json`
- `refresh_goal_bottleneck_roadmap_surface`: `python3 scripts/build_goal_bottleneck_roadmap_surface.py --out implementation/phase1/release_evidence/productization/goal_bottleneck_roadmap_surface.json`

## Acceptance Criteria

- `pocketmd_lite_topk_survival_report.real_refinement_case_count > 0`
- `pocketmd_lite_topk_survival_report.blockers == []`
- `pocketmd_lite_topk_survival_report.phase4_exit_gate.status == ready`
- `pocketmd_lite_topk_survival_report.product_surface_ready == true`
- `pocketmd_lite_science_product_surface.locked == false`
- `broad_all_atom_md_claim and free_energy_perturbation_claim remain locked unless separately evidenced`
