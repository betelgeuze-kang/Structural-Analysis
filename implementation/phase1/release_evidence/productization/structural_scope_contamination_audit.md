# Structural Scope Contamination Audit

- `status`: `quarantined`
- `contract_pass`: `True`
- `non_structural_path_count`: `86`
- `non_structural_tracked_path_count`: `86`
- `non_structural_untracked_path_count`: `0`
- `quarantined_non_structural_path_count`: `86`
- `unquarantined_non_structural_path_count`: `0`
- `first_non_structural_path`: `implementation/phase1/md3bead_scientific_validity_report.md`
- `first_unquarantined_non_structural_path`: `none`
- `release_surface_text_leak_path_count`: `0`

## Quarantine

- `manifest_present`: `True`
- `manifest_path`: `implementation/phase1/release_evidence/productization/structural_scope_quarantine_manifest.json`
- `manifest_quarantined_path_count`: `86`

| Git State | Count |
|---|---:|
| `tracked` | 86 |

| Area | Count |
|---|---:|
| `implementation_phase1` | 9 |
| `productization_evidence` | 36 |
| `release_surface` | 3 |
| `script` | 19 |
| `test` | 19 |

| Family | Count |
|---|---:|
| `molecular_docking` | 48 |
| `molecular_dynamics` | 25 |
| `molecular_science_evidence` | 13 |

## Release Surface Text Guard

No guarded structural release surface text leaks detected.

| Path | Git State | Area | Quarantine | Families | Tokens |
|---|---|---|---|---|---|
| `implementation/phase1/md3bead_scientific_validity_report.md` | `tracked` | `implementation_phase1` | `quarantined` | `molecular_dynamics` | `md3bead` |
| `implementation/phase1/md3bead_soa.py` | `tracked` | `implementation_phase1` | `quarantined` | `molecular_dynamics` | `md3bead` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_intake_packet.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_intake_packet.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_template.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_product_report.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows_template.csv` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_suite_report.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_suite_report.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gpcr` |
| `implementation/phase1/release_evidence/productization/h_bond_backmap_operator_intake_packet.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_science_evidence` | `h_bond` |
| `implementation/phase1/release_evidence/productization/h_bond_backmap_operator_intake_packet.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_science_evidence` | `h_bond` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_delivery_handoff.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake_packet.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake_packet.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_operator_template.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_readonly_api.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.md` | `tracked` | `productization_evidence` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `implementation/phase1/release_evidence/productization/public_benchmark_casf_pdbbind_operator_template.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `casf_pdbbind, pdbbind` |
| `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_operator_template.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_enrichment` |
| `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows_template.csv` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_enrichment` |
| `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_scorecard.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_enrichment` |
| `implementation/phase1/release_evidence/productization/public_benchmark_pose_coordinate_operator_template.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `implementation/phase1/release_evidence/productization/public_benchmark_pose_rows_template.csv` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `implementation/phase1/release_evidence/productization/public_benchmark_pose_success_harness.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `implementation/phase1/release_evidence/productization/public_benchmark_pose_validity_packet.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_subset` |
| `implementation/phase1/release_evidence/productization/public_benchmark_subset_rows_template.csv` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `public_benchmark_subset` |
| `implementation/phase1/release_evidence/productization/public_benchmark_symmetry_rmsd_scorecard.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `symmetry_rmsd` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_comparison_adapter.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_operator_template.json` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template.csv` | `tracked` | `productization_evidence` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
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
| `scripts/build_gpcr_hard_decoy_operator_intake_packet.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gpcr` |
| `scripts/build_gpcr_hard_decoy_product_report.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gpcr` |
| `scripts/build_h_bond_backmap_operator_intake_packet.py` | `tracked` | `script` | `quarantined` | `molecular_science_evidence` | `h_bond` |
| `scripts/build_pocketmd_lite_product_surface.py` | `tracked` | `script` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `scripts/build_science_actual_closure_operator_handoff.py` | `tracked` | `script` | `quarantined` | `molecular_science_evidence` | `science_actual` |
| `scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gpcr` |
| `scripts/materialize_gpcr_hard_decoy_suite_report.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gpcr` |
| `scripts/materialize_pocketmd_lite_operator_intake_from_rows.py` | `tracked` | `script` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `scripts/materialize_pocketmd_lite_topk_survival_report.py` | `tracked` | `script` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `scripts/materialize_public_benchmark_enrichment_scorecard.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `public_benchmark_enrichment` |
| `scripts/materialize_public_benchmark_pose_success_harness.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `scripts/materialize_public_benchmark_pose_validity_input.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `scripts/materialize_public_benchmark_posebusters_validity_packet.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `posebusters, public_benchmark_pose` |
| `scripts/materialize_public_benchmark_subset_manifest.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `public_benchmark_subset` |
| `scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `scripts/materialize_science_actual_closure_from_rows.py` | `tracked` | `script` | `quarantined` | `molecular_science_evidence` | `science_actual` |
| `scripts/score_symmetry_aware_ligand_rmsd.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `ligand, symmetry_aware_ligand` |
| `scripts/validate_public_benchmark_pose_validity.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `scripts/validate_public_benchmark_subset_manifest.py` | `tracked` | `script` | `quarantined` | `molecular_docking` | `public_benchmark_subset` |
| `tests/test_build_gpcr_hard_decoy_operator_intake_packet.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gpcr` |
| `tests/test_build_gpcr_hard_decoy_product_report.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gpcr` |
| `tests/test_build_h_bond_backmap_operator_intake_packet.py` | `tracked` | `test` | `quarantined` | `molecular_science_evidence` | `h_bond` |
| `tests/test_build_pocketmd_lite_product_surface.py` | `tracked` | `test` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `tests/test_build_science_actual_closure_operator_handoff.py` | `tracked` | `test` | `quarantined` | `molecular_science_evidence` | `science_actual` |
| `tests/test_materialize_gpcr_hard_decoy_operator_template_from_rows.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gpcr` |
| `tests/test_materialize_gpcr_hard_decoy_suite_report.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gpcr` |
| `tests/test_materialize_pocketmd_lite_operator_intake_from_rows.py` | `tracked` | `test` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `tests/test_materialize_pocketmd_lite_topk_survival_report.py` | `tracked` | `test` | `quarantined` | `molecular_dynamics` | `pocketmd` |
| `tests/test_materialize_public_benchmark_enrichment_scorecard.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `public_benchmark_enrichment` |
| `tests/test_materialize_public_benchmark_pose_success_harness.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `tests/test_materialize_public_benchmark_pose_validity_input.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `tests/test_materialize_public_benchmark_posebusters_validity_packet.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `posebusters, public_benchmark_pose` |
| `tests/test_materialize_public_benchmark_subset_manifest.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `public_benchmark_subset` |
| `tests/test_materialize_public_benchmark_vina_gnina_comparison_adapter.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `gnina, public_benchmark_vina_gnina, vina` |
| `tests/test_materialize_science_actual_closure_from_rows.py` | `tracked` | `test` | `quarantined` | `molecular_science_evidence` | `science_actual` |
| `tests/test_score_symmetry_aware_ligand_rmsd.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `ligand, symmetry_aware_ligand` |
| `tests/test_validate_public_benchmark_pose_validity.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `public_benchmark_pose` |
| `tests/test_validate_public_benchmark_subset_manifest.py` | `tracked` | `test` | `quarantined` | `molecular_docking` | `public_benchmark_subset` |

This audit protects the building structural-analysis product scope. It does not delete files; it identifies molecular, ligand, GPCR, PocketMD, and MD paths and requires either deletion/extraction or an exact quarantine manifest that excludes them from the structural release surface. Quarantined paths remain visible and must not be counted as structural solver release evidence.
