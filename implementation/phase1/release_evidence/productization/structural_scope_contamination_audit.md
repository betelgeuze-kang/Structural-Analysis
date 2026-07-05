# Structural Scope Contamination Audit

- `status`: `quarantined`
- `contract_pass`: `True`
- `non_structural_path_count`: `251`
- `non_structural_tracked_path_count`: `251`
- `non_structural_untracked_path_count`: `0`
- `quarantined_non_structural_path_count`: `251`
- `unquarantined_non_structural_path_count`: `0`
- `first_non_structural_path`: `implementation/phase1/md3bead_scientific_validity_report.md`
- `first_unquarantined_non_structural_path`: `none`
- `release_surface_text_leak_path_count`: `0`
- `owner_cleanup_closure_ready`: `False`
- `owner_cleanup_pending_path_count`: `251`
- `release_surface_owner_cleanup_pending_path_count`: `3`

## Quarantine

- `manifest_present`: `True`
- `manifest_path`: `implementation/phase1/release_evidence/productization/structural_scope_quarantine_manifest.json`
- `manifest_quarantined_path_count`: `251`

| Git State | Count |
|---|---:|
| `tracked` | 251 |

| Area | Count |
|---|---:|
| `implementation_phase1` | 9 |
| `other` | 78 |
| `productization_evidence` | 79 |
| `release_surface` | 3 |
| `script` | 41 |
| `test` | 41 |

| Family | Count |
|---|---:|
| `molecular_docking` | 185 |
| `molecular_dynamics` | 57 |
| `molecular_science_evidence` | 13 |

## Release Surface Text Guard

No guarded structural release surface text leaks detected.

## Owner Cleanup Closure

- blockers:
  - `quarantined_non_structural_owner_cleanup_pending_count=251`
  - `release_surface_quarantined_owner_cleanup_pending_count=3`

## Release Surface Quarantine Boundary

- `status`: `quarantined_paths_excluded_pending_owner_cleanup`
- `quarantined_release_surface_path_count`: `3`
- `quarantined_paths_claim_eligible`: `False`

| Quarantined Release-Surface Path | Owner Action |
|---|---|
| `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json` | `delete_or_extract_after_owner_review` |
| `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json` | `delete_or_extract_after_owner_review` |
| `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json` | `delete_or_extract_after_owner_review` |

Quarantined release-surface paths are explicitly excluded from the building structural-analysis release surface. They are skipped by the structural text guard only because the quarantine manifest keeps them outside release claims; they still require owner delete/extract decisions before scope cleanup can close.


| Path | Git State | Area | Quarantine | Families | Tokens |
|---|---|---|---|---|---|
| `implementation/phase1/md3bead_scientific_validity_report.md` | `tracked` | `implementation_phase1` | `quarantined` | `molecular_dynamics` | `md3bead` |
| `implementation/phase1/md3bead_soa.py` | `tracked` | `implementation_phase1` | `quarantined` | `molecular_dynamics` | `md3bead` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_chembl_activity_rows.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_chembl_activity_rows.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_decoy_source_snapshot.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_decoy_source_snapshot.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_intake_packet.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_intake_packet.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_template.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_positive_source_snapshot.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_positive_source_snapshot.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_product_report.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows_template.csv` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_source_acquisition_plan.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_source_acquisition_plan.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_suite_report.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_suite_report.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/h_bond_backmap_operator_intake_packet.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_science_evidence` | `h_bond` |
| `implementation/phase1/release_evidence/productization/h_bond_backmap_operator_intake_packet.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_science_evidence` | `h_bond` |
| `implementation/phase1/release_evidence/productization/operator_attached/pocketmd_lite_refinement_sources/gpcr_chembl_topk_ligand_refinement_source.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking, molecular_dynamics` | `gpcr, ligand, pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_delivery_handoff.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_gpcr_chembl_refinement_receipts_report.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking, molecular_dynamics` | `gpcr, pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake_packet.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake_packet.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_operator_template.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_readonly_api.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_refinement_execution_plan.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_refinement_receipt_bundle.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_source_acquisition_plan.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_source_acquisition_plan.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_from_receipt_bundle_report.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_from_template_report.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template_preflight.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/public_benchmark_casf_pdbbind_operator_template.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `casf_pdbbind, pdbbind` |
| `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_operator_template.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_enrichment` |
| `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_enrichment` |
| `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows_template.csv` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_enrichment` |
| `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_scorecard.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_enrichment` |
| `implementation/phase1/release_evidence/productization/public_benchmark_pose_coordinate_operator_template.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `implementation/phase1/release_evidence/productization/public_benchmark_pose_rows.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `implementation/phase1/release_evidence/productization/public_benchmark_pose_rows_template.csv` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `implementation/phase1/release_evidence/productization/public_benchmark_pose_success_harness.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `implementation/phase1/release_evidence/productization/public_benchmark_pose_validity_input.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `implementation/phase1/release_evidence/productization/public_benchmark_pose_validity_packet.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_subset` |
| `implementation/phase1/release_evidence/productization/public_benchmark_subset_rows.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_subset` |
| `implementation/phase1/release_evidence/productization/public_benchmark_subset_rows_template.csv` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_subset` |
| `implementation/phase1/release_evidence/productization/public_benchmark_symmetry_rmsd_scorecard.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `symmetry_rmsd` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_comparison_adapter.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_engine_run_bundle.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_engine_run_commands.sh` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_engine_run_receipts_completion_report.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_execution_plan.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.csv` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_from_casf_archive_report.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_from_template_report.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template.csv` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_operator_template.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_prepared_inputs_report.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_from_engine_run_bundle_report.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_from_template_report.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template.csv` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template_preflight.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template_preflight.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_runtime_readiness.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/science_actual_closure_operator_handoff.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_science_evidence` | `science_actual` |
| `implementation/phase1/release_evidence/productization/science_actual_closure_operator_handoff.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_science_evidence` | `science_actual` |
| `implementation/phase1/release_evidence/productization/science_actual_closure_row_audit.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_science_evidence` | `science_actual` |
| `implementation/phase1/release_evidence/productization/science_actual_closure_row_audit.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_science_evidence` | `science_actual` |
| `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json` | `tracked` | `release_surface` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json` | `tracked` | `release_surface` | `quarantined` | `molecular_science_evidence` | `h_bond` |
| `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json` | `tracked` | `release_surface` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/rust_hip_md3bead_hook.py` | `tracked` | `implementation_phase1` | `quarantined` | `molecular_dynamics` | `md3bead` |
| `implementation/phase1/rust_hip_md3bead_hook/Cargo.lock` | `tracked` | `implementation_phase1` | `quarantined` | `molecular_dynamics` | `md3bead` |
| `implementation/phase1/rust_hip_md3bead_hook/Cargo.toml` | `tracked` | `implementation_phase1` | `quarantined` | `molecular_dynamics` | `md3bead` |
| `implementation/phase1/rust_hip_md3bead_hook/src/lib.rs` | `tracked` | `implementation_phase1` | `quarantined` | `molecular_dynamics` | `md3bead` |
| `implementation/phase1/rust_hip_md3bead_hook/src/main.rs` | `tracked` | `implementation_phase1` | `quarantined` | `molecular_dynamics` | `md3bead` |
| `implementation/phase1/rust_md3bead_parity_report.json` | `tracked` | `implementation_phase1` | `quarantined` | `molecular_dynamics` | `md3bead` |
| `implementation/phase1/validate_md3bead_rust_parity.py` | `tracked` | `implementation_phase1` | `quarantined` | `molecular_dynamics` | `md3bead` |
| `operator_attached/pocketmd_lite_refinement_receipts/pocketmd_lite_case_001/rank_01_refinement_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `operator_attached/pocketmd_lite_refinement_receipts/pocketmd_lite_case_001/rank_02_refinement_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `operator_attached/pocketmd_lite_refinement_receipts/pocketmd_lite_case_002/rank_01_refinement_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `operator_attached/pocketmd_lite_refinement_receipts/pocketmd_lite_case_002/rank_02_refinement_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `operator_attached/pocketmd_lite_refinement_receipts/pocketmd_lite_case_003/rank_01_refinement_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `operator_attached/pocketmd_lite_refinement_receipts/pocketmd_lite_case_003/rank_02_refinement_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `operator_attached/vina_gnina/casf2016_2v00/gnina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_2v00/gnina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_2v00/gnina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_2v00/vina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_2v00/vina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_2v00/vina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3prs/gnina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3prs/gnina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3prs/gnina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3prs/vina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3prs/vina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3prs/vina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3pww/gnina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3pww/gnina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3pww/gnina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3pww/vina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3pww/vina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3pww/vina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3ui7/gnina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3ui7/gnina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3ui7/gnina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3ui7/vina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3ui7/vina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3ui7/vina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3uri/gnina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3uri/gnina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3uri/gnina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3uri/vina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3uri/vina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3uri/vina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3uuo/gnina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3uuo/gnina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3uuo/gnina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3uuo/vina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3uuo/vina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3uuo/vina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3wz8/gnina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3wz8/gnina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3wz8/gnina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3wz8/vina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3wz8/vina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_3wz8/vina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4llx/gnina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4llx/gnina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4llx/gnina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4llx/vina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4llx/vina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4llx/vina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4m0y/gnina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4m0y/gnina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4m0y/gnina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4m0y/vina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4m0y/vina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4m0y/vina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4m0z/gnina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4m0z/gnina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4m0z/gnina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4m0z/vina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4m0z/vina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_4m0z/vina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_5c28/gnina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_5c28/gnina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_5c28/gnina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_5c28/vina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_5c28/vina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_5c28/vina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_5c2h/gnina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_5c2h/gnina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_5c2h/gnina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_5c2h/vina_config.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_5c2h/vina_pose.sdf` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `operator_attached/vina_gnina/casf2016_5c2h/vina_run_receipt.json` | `tracked` | `other` | `quarantined` | `molecular_docking` | `gnina, vina` |
| `scripts/build_gpcr_hard_decoy_chembl_activity_rows.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gpcr` |
| `scripts/build_gpcr_hard_decoy_decoy_source_snapshot.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gpcr` |
| `scripts/build_gpcr_hard_decoy_operator_intake_packet.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gpcr` |
| `scripts/build_gpcr_hard_decoy_positive_source_snapshot.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gpcr` |
| `scripts/build_gpcr_hard_decoy_product_report.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gpcr` |
| `scripts/build_gpcr_hard_decoy_source_acquisition_plan.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gpcr` |
| `scripts/build_h_bond_backmap_operator_intake_packet.py` | `tracked` | `script` | `quarantined` | `molecular_science_evidence` | `h_bond` |
| `scripts/build_pocketmd_lite_product_surface.py` | `tracked` | `script` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `scripts/build_pocketmd_lite_refinement_execution_plan.py` | `tracked` | `script` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `scripts/build_pocketmd_lite_source_acquisition_plan.py` | `tracked` | `script` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `scripts/build_pocketmd_lite_topk_rows_template_preflight.py` | `tracked` | `script` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `scripts/build_public_benchmark_vina_gnina_execution_plan.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `scripts/build_public_benchmark_vina_gnina_rows_template_preflight.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `scripts/build_public_benchmark_vina_gnina_runtime_readiness.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `scripts/build_science_actual_closure_operator_handoff.py` | `tracked` | `script` | `quarantined` | `molecular_science_evidence` | `science_actual` |
| `scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gpcr` |
| `scripts/materialize_gpcr_hard_decoy_suite_report.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gpcr` |
| `scripts/materialize_pocketmd_lite_gpcr_chembl_refinement_receipts.py` | `tracked` | `script` | `quarantined` | `molecular_docking, molecular_dynamics` | `gpcr, pocketmd` |
| `scripts/materialize_pocketmd_lite_operator_intake_from_rows.py` | `tracked` | `script` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `scripts/materialize_pocketmd_lite_refinement_receipt_bundle.py` | `tracked` | `script` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `scripts/materialize_pocketmd_lite_topk_rows_from_receipt_bundle.py` | `tracked` | `script` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `scripts/materialize_pocketmd_lite_topk_rows_from_template.py` | `tracked` | `script` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `scripts/materialize_pocketmd_lite_topk_survival_report.py` | `tracked` | `script` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `scripts/materialize_public_benchmark_enrichment_scorecard.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `public_benchmark_enrichment` |
| `scripts/materialize_public_benchmark_pose_success_harness.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `scripts/materialize_public_benchmark_pose_validity_input.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `scripts/materialize_public_benchmark_posebusters_validity_packet.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `posebusters, public_benchmark_pose` |
| `scripts/materialize_public_benchmark_subset_manifest.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `public_benchmark_subset` |
| `scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `scripts/materialize_public_benchmark_vina_gnina_engine_run_bundle.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_template.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `scripts/materialize_public_benchmark_vina_gnina_prepared_inputs.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `scripts/materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `scripts/materialize_public_benchmark_vina_gnina_rows_from_template.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `scripts/materialize_science_actual_closure_from_rows.py` | `tracked` | `script` | `quarantined` | `molecular_science_evidence` | `science_actual` |
| `scripts/run_public_benchmark_vina_gnina_engine_run_receipts.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `scripts/score_symmetry_aware_ligand_rmsd.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `ligand, symmetry_aware_ligand` |
| `scripts/validate_public_benchmark_pose_validity.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `scripts/validate_public_benchmark_subset_manifest.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `public_benchmark_subset` |
| `tests/test_build_gpcr_hard_decoy_chembl_activity_rows.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gpcr` |
| `tests/test_build_gpcr_hard_decoy_decoy_source_snapshot.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gpcr` |
| `tests/test_build_gpcr_hard_decoy_operator_intake_packet.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gpcr` |
| `tests/test_build_gpcr_hard_decoy_positive_source_snapshot.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gpcr` |
| `tests/test_build_gpcr_hard_decoy_product_report.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gpcr` |
| `tests/test_build_gpcr_hard_decoy_source_acquisition_plan.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gpcr` |
| `tests/test_build_h_bond_backmap_operator_intake_packet.py` | `tracked` | `test` | `quarantined` | `molecular_science_evidence` | `h_bond` |
| `tests/test_build_pocketmd_lite_product_surface.py` | `tracked` | `test` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `tests/test_build_pocketmd_lite_refinement_execution_plan.py` | `tracked` | `test` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `tests/test_build_pocketmd_lite_source_acquisition_plan.py` | `tracked` | `test` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `tests/test_build_pocketmd_lite_topk_rows_template_preflight.py` | `tracked` | `test` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `tests/test_build_public_benchmark_vina_gnina_execution_plan.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `tests/test_build_public_benchmark_vina_gnina_input_manifest_template_preflight.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `tests/test_build_public_benchmark_vina_gnina_rows_template_preflight.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `tests/test_build_public_benchmark_vina_gnina_runtime_readiness.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `tests/test_build_science_actual_closure_operator_handoff.py` | `tracked` | `test` | `quarantined` | `molecular_science_evidence` | `science_actual` |
| `tests/test_materialize_gpcr_hard_decoy_operator_template_from_rows.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gpcr` |
| `tests/test_materialize_gpcr_hard_decoy_suite_report.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gpcr` |
| `tests/test_materialize_pocketmd_lite_gpcr_chembl_refinement_receipts.py` | `tracked` | `test` | `quarantined` | `molecular_docking, molecular_dynamics` | `gpcr, pocketmd` |
| `tests/test_materialize_pocketmd_lite_operator_intake_from_rows.py` | `tracked` | `test` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `tests/test_materialize_pocketmd_lite_refinement_receipt_bundle.py` | `tracked` | `test` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `tests/test_materialize_pocketmd_lite_topk_rows_from_receipt_bundle.py` | `tracked` | `test` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `tests/test_materialize_pocketmd_lite_topk_rows_from_template.py` | `tracked` | `test` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `tests/test_materialize_pocketmd_lite_topk_survival_report.py` | `tracked` | `test` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `tests/test_materialize_public_benchmark_enrichment_scorecard.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `public_benchmark_enrichment` |
| `tests/test_materialize_public_benchmark_pose_success_harness.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `tests/test_materialize_public_benchmark_pose_validity_input.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `tests/test_materialize_public_benchmark_posebusters_validity_packet.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `posebusters, public_benchmark_pose` |
| `tests/test_materialize_public_benchmark_subset_manifest.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `public_benchmark_subset` |
| `tests/test_materialize_public_benchmark_vina_gnina_comparison_adapter.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `tests/test_materialize_public_benchmark_vina_gnina_engine_run_bundle.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `tests/test_materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `tests/test_materialize_public_benchmark_vina_gnina_input_manifest_from_template.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `tests/test_materialize_public_benchmark_vina_gnina_prepared_inputs.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `tests/test_materialize_public_benchmark_vina_gnina_rows_from_engine_run_bundle.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `tests/test_materialize_public_benchmark_vina_gnina_rows_from_template.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `tests/test_materialize_science_actual_closure_from_rows.py` | `tracked` | `test` | `quarantined` | `molecular_science_evidence` | `science_actual` |
| `tests/test_run_public_benchmark_vina_gnina_engine_run_receipts.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `tests/test_score_symmetry_aware_ligand_rmsd.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `ligand, symmetry_aware_ligand` |
| `tests/test_validate_public_benchmark_pose_validity.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `tests/test_validate_public_benchmark_subset_manifest.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `public_benchmark_subset` |

This audit protects the building structural-analysis product scope. It does not delete files; it identifies molecular, ligand, GPCR, PocketMD, and MD paths and requires either deletion/extraction or an exact quarantine manifest that excludes them from the structural release surface. Quarantined paths remain visible and must not be counted as structural solver release evidence.
