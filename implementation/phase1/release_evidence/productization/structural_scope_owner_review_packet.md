# Structural Scope Owner Review Packet

- `summary_line`: `Structural scope owner review: READY_FOR_OWNER_REVIEW | pending=86 | cleanup_pending=0 | excluded=86/86 | unquarantined=0`
- `contract_pass`: `True`
- `evidence_closure_pass`: `False`
- `owner_decision_recorded_count`: `0`
- `owner_decision_pending_count`: `86`
- `post_decision_cleanup_pending_count`: `0`
- `post_decision_cleanup_applied_count`: `0`
- `post_decision_cleanup_missing_owner_decision_count`: `0`
- `release_surface_excluded_path_count`: `86`
- `release_surface_path_count`: `3`
- `release_surface_owner_decision_required_count`: `3`
- `release_surface_post_decision_cleanup_pending_count`: `0`
- `unquarantined_non_structural_path_count`: `0`
- `owner_decisions_path`: `implementation/phase1/release_evidence/productization/structural_scope_owner_decisions.json`

## Release Surface First

- `allowed_owner_decisions`: `delete_from_structural_repository, extract_to_molecular_or_science_repository`
- `retain_quarantined_with_signed_owner_exception_allowed`: `False`

| Path | State | Owner Decision | Required Action |
|---|---|---|---|
| `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json` | `pending_owner_decision` | `` | `delete_or_extract_before_release_surface_cleanup` |
| `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json` | `pending_owner_decision` | `` | `delete_or_extract_before_release_surface_cleanup` |
| `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json` | `pending_owner_decision` | `` | `delete_or_extract_before_release_surface_cleanup` |

## Review Groups

| Family | Area | Paths | Recommended Decision |
|---|---|---:|---|
| `molecular_docking` | `productization_evidence` | 21 | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `molecular_docking` | `release_surface` | 1 | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `molecular_docking` | `script` | 13 | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `molecular_docking` | `test` | 13 | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `molecular_dynamics` | `implementation_phase1` | 9 | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `molecular_dynamics` | `productization_evidence` | 9 | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `molecular_dynamics` | `release_surface` | 1 | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `molecular_dynamics` | `script` | 3 | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `molecular_dynamics` | `test` | 3 | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `molecular_science_evidence` | `productization_evidence` | 6 | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `molecular_science_evidence` | `release_surface` | 1 | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `molecular_science_evidence` | `script` | 3 | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `molecular_science_evidence` | `test` | 3 | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |

## Owner Decision Rows

| Path | Area | Families | State | Release Surface | Recommended Decision |
|---|---|---|---|---|---|
| `implementation/phase1/md3bead_scientific_validity_report.md` | `implementation_phase1` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `implementation/phase1/md3bead_soa.py` | `implementation_phase1` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_intake_packet.json` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_intake_packet.md` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_template.json` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_product_report.json` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows_template.csv` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_suite_report.json` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_suite_report.md` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/h_bond_backmap_operator_intake_packet.json` | `productization_evidence` | `molecular_science_evidence` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/h_bond_backmap_operator_intake_packet.md` | `productization_evidence` | `molecular_science_evidence` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json` | `productization_evidence` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_delivery_handoff.json` | `productization_evidence` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake_packet.json` | `productization_evidence` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake_packet.md` | `productization_evidence` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_operator_template.json` | `productization_evidence` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_readonly_api.json` | `productization_evidence` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv` | `productization_evidence` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.json` | `productization_evidence` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.md` | `productization_evidence` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/public_benchmark_casf_pdbbind_operator_template.json` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_operator_template.json` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows_template.csv` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_scorecard.json` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/public_benchmark_pose_coordinate_operator_template.json` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/public_benchmark_pose_rows_template.csv` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/public_benchmark_pose_success_harness.json` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/public_benchmark_pose_validity_packet.json` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/public_benchmark_subset_rows_template.csv` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/public_benchmark_symmetry_rmsd_scorecard.json` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_comparison_adapter.json` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_operator_template.json` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template.csv` | `productization_evidence` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/science_actual_closure_operator_handoff.json` | `productization_evidence` | `molecular_science_evidence` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/science_actual_closure_operator_handoff.md` | `productization_evidence` | `molecular_science_evidence` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/science_actual_closure_row_audit.json` | `productization_evidence` | `molecular_science_evidence` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/productization/science_actual_closure_row_audit.md` | `productization_evidence` | `molecular_science_evidence` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json` | `release_surface` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json` | `release_surface` | `molecular_science_evidence` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json` | `release_surface` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `implementation/phase1/rust_hip_md3bead_hook.py` | `implementation_phase1` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `implementation/phase1/rust_hip_md3bead_hook/Cargo.lock` | `implementation_phase1` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `implementation/phase1/rust_hip_md3bead_hook/Cargo.toml` | `implementation_phase1` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `implementation/phase1/rust_hip_md3bead_hook/src/lib.rs` | `implementation_phase1` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `implementation/phase1/rust_hip_md3bead_hook/src/main.rs` | `implementation_phase1` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `implementation/phase1/rust_md3bead_parity_report.json` | `implementation_phase1` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `implementation/phase1/validate_md3bead_rust_parity.py` | `implementation_phase1` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/build_gpcr_hard_decoy_operator_intake_packet.py` | `script` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/build_gpcr_hard_decoy_product_report.py` | `script` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/build_h_bond_backmap_operator_intake_packet.py` | `script` | `molecular_science_evidence` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/build_pocketmd_lite_product_surface.py` | `script` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/build_science_actual_closure_operator_handoff.py` | `script` | `molecular_science_evidence` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py` | `script` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/materialize_gpcr_hard_decoy_suite_report.py` | `script` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/materialize_pocketmd_lite_operator_intake_from_rows.py` | `script` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/materialize_pocketmd_lite_topk_survival_report.py` | `script` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/materialize_public_benchmark_enrichment_scorecard.py` | `script` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/materialize_public_benchmark_pose_success_harness.py` | `script` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/materialize_public_benchmark_pose_validity_input.py` | `script` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/materialize_public_benchmark_posebusters_validity_packet.py` | `script` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/materialize_public_benchmark_subset_manifest.py` | `script` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py` | `script` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/materialize_science_actual_closure_from_rows.py` | `script` | `molecular_science_evidence` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/score_symmetry_aware_ligand_rmsd.py` | `script` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/validate_public_benchmark_pose_validity.py` | `script` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `scripts/validate_public_benchmark_subset_manifest.py` | `script` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_build_gpcr_hard_decoy_operator_intake_packet.py` | `test` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_build_gpcr_hard_decoy_product_report.py` | `test` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_build_h_bond_backmap_operator_intake_packet.py` | `test` | `molecular_science_evidence` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_build_pocketmd_lite_product_surface.py` | `test` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_build_science_actual_closure_operator_handoff.py` | `test` | `molecular_science_evidence` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_materialize_gpcr_hard_decoy_operator_template_from_rows.py` | `test` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_materialize_gpcr_hard_decoy_suite_report.py` | `test` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_materialize_pocketmd_lite_operator_intake_from_rows.py` | `test` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_materialize_pocketmd_lite_topk_survival_report.py` | `test` | `molecular_dynamics` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_materialize_public_benchmark_enrichment_scorecard.py` | `test` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_materialize_public_benchmark_pose_success_harness.py` | `test` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_materialize_public_benchmark_pose_validity_input.py` | `test` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_materialize_public_benchmark_posebusters_validity_packet.py` | `test` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_materialize_public_benchmark_subset_manifest.py` | `test` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_materialize_public_benchmark_vina_gnina_comparison_adapter.py` | `test` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_materialize_science_actual_closure_from_rows.py` | `test` | `molecular_science_evidence` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_score_symmetry_aware_ligand_rmsd.py` | `test` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_validate_public_benchmark_pose_validity.py` | `test` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `tests/test_validate_public_benchmark_subset_manifest.py` | `test` | `molecular_docking` | `pending_owner_decision` | `excluded_quarantined_legacy_artifact` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |

## Closure Blockers

- `owner_decision_pending_count=86`

## Claim Boundary

This packet is an owner handoff for quarantined non-structural molecular/GPCR/PocketMD/MD artifacts. It does not delete files, promote molecular evidence, or make quarantined rows eligible for building structural-analysis release claims. Closure requires a recorded owner decision per path followed by a refreshed structural scope contamination audit.
