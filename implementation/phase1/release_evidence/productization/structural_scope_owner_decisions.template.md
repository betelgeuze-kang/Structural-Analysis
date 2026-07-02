# Structural Scope Owner Decision Template

- `status`: `pending_owner_decisions`
- `contract_pass`: `True`
- `decision_pending_count`: `86`
- `external_archive_reference`: required when `owner_decision` is `extract_to_molecular_or_science_repository`
- `signed_owner_exception_reference`: required when `owner_decision` is `retain_quarantined_with_signed_owner_exception`

## Placeholder Rejection Policy

- `rejected_fields`: `owner_identity, owner_role, evidence_reference, external_archive_reference, signed_owner_exception_reference`
- `rejected_values`: `<...>, TODO, TBD, placeholder, replace-me, fill-me, N/A, none, null, unknown`

| Row | Path | Recommended Decision |
|---|---|---|
| `structural-scope-owner-001` | `implementation/phase1/md3bead_scientific_validity_report.md` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-002` | `implementation/phase1/md3bead_soa.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-003` | `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_intake_packet.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-004` | `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_intake_packet.md` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-005` | `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_operator_template.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-006` | `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_product_report.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-007` | `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_rows_template.csv` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-008` | `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_suite_report.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-009` | `implementation/phase1/release_evidence/productization/gpcr_hard_decoy_suite_report.md` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-010` | `implementation/phase1/release_evidence/productization/h_bond_backmap_operator_intake_packet.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-011` | `implementation/phase1/release_evidence/productization/h_bond_backmap_operator_intake_packet.md` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-012` | `implementation/phase1/release_evidence/productization/pocketmd_lite_contract.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-013` | `implementation/phase1/release_evidence/productization/pocketmd_lite_delivery_handoff.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-014` | `implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake_packet.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-015` | `implementation/phase1/release_evidence/productization/pocketmd_lite_operator_intake_packet.md` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-016` | `implementation/phase1/release_evidence/productization/pocketmd_lite_operator_template.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-017` | `implementation/phase1/release_evidence/productization/pocketmd_lite_readonly_api.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-018` | `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_rows_template.csv` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-019` | `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-020` | `implementation/phase1/release_evidence/productization/pocketmd_lite_topk_survival_report.md` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-021` | `implementation/phase1/release_evidence/productization/public_benchmark_casf_pdbbind_operator_template.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-022` | `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_operator_template.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-023` | `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_rows_template.csv` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-024` | `implementation/phase1/release_evidence/productization/public_benchmark_enrichment_scorecard.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-025` | `implementation/phase1/release_evidence/productization/public_benchmark_pose_coordinate_operator_template.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-026` | `implementation/phase1/release_evidence/productization/public_benchmark_pose_rows_template.csv` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-027` | `implementation/phase1/release_evidence/productization/public_benchmark_pose_success_harness.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-028` | `implementation/phase1/release_evidence/productization/public_benchmark_pose_validity_packet.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-029` | `implementation/phase1/release_evidence/productization/public_benchmark_subset_manifest.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-030` | `implementation/phase1/release_evidence/productization/public_benchmark_subset_rows_template.csv` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-031` | `implementation/phase1/release_evidence/productization/public_benchmark_symmetry_rmsd_scorecard.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-032` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_comparison_adapter.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-033` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_operator_template.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-034` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_rows_template.csv` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-035` | `implementation/phase1/release_evidence/productization/science_actual_closure_operator_handoff.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-036` | `implementation/phase1/release_evidence/productization/science_actual_closure_operator_handoff.md` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-037` | `implementation/phase1/release_evidence/productization/science_actual_closure_row_audit.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-038` | `implementation/phase1/release_evidence/productization/science_actual_closure_row_audit.md` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-039` | `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-040` | `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-041` | `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json` | `delete_from_structural_repository_or_extract_only_if_owner_requires_history` |
| `structural-scope-owner-042` | `implementation/phase1/rust_hip_md3bead_hook.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-043` | `implementation/phase1/rust_hip_md3bead_hook/Cargo.lock` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-044` | `implementation/phase1/rust_hip_md3bead_hook/Cargo.toml` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-045` | `implementation/phase1/rust_hip_md3bead_hook/src/lib.rs` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-046` | `implementation/phase1/rust_hip_md3bead_hook/src/main.rs` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-047` | `implementation/phase1/rust_md3bead_parity_report.json` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-048` | `implementation/phase1/validate_md3bead_rust_parity.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-049` | `scripts/build_gpcr_hard_decoy_operator_intake_packet.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-050` | `scripts/build_gpcr_hard_decoy_product_report.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-051` | `scripts/build_h_bond_backmap_operator_intake_packet.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-052` | `scripts/build_pocketmd_lite_product_surface.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-053` | `scripts/build_science_actual_closure_operator_handoff.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-054` | `scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-055` | `scripts/materialize_gpcr_hard_decoy_suite_report.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-056` | `scripts/materialize_pocketmd_lite_operator_intake_from_rows.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-057` | `scripts/materialize_pocketmd_lite_topk_survival_report.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-058` | `scripts/materialize_public_benchmark_enrichment_scorecard.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-059` | `scripts/materialize_public_benchmark_pose_success_harness.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-060` | `scripts/materialize_public_benchmark_pose_validity_input.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-061` | `scripts/materialize_public_benchmark_posebusters_validity_packet.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-062` | `scripts/materialize_public_benchmark_subset_manifest.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-063` | `scripts/materialize_public_benchmark_vina_gnina_comparison_adapter.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-064` | `scripts/materialize_science_actual_closure_from_rows.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-065` | `scripts/score_symmetry_aware_ligand_rmsd.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-066` | `scripts/validate_public_benchmark_pose_validity.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-067` | `scripts/validate_public_benchmark_subset_manifest.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-068` | `tests/test_build_gpcr_hard_decoy_operator_intake_packet.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-069` | `tests/test_build_gpcr_hard_decoy_product_report.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-070` | `tests/test_build_h_bond_backmap_operator_intake_packet.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-071` | `tests/test_build_pocketmd_lite_product_surface.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-072` | `tests/test_build_science_actual_closure_operator_handoff.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-073` | `tests/test_materialize_gpcr_hard_decoy_operator_template_from_rows.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-074` | `tests/test_materialize_gpcr_hard_decoy_suite_report.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-075` | `tests/test_materialize_pocketmd_lite_operator_intake_from_rows.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-076` | `tests/test_materialize_pocketmd_lite_topk_survival_report.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-077` | `tests/test_materialize_public_benchmark_enrichment_scorecard.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-078` | `tests/test_materialize_public_benchmark_pose_success_harness.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-079` | `tests/test_materialize_public_benchmark_pose_validity_input.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-080` | `tests/test_materialize_public_benchmark_posebusters_validity_packet.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-081` | `tests/test_materialize_public_benchmark_subset_manifest.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-082` | `tests/test_materialize_public_benchmark_vina_gnina_comparison_adapter.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-083` | `tests/test_materialize_science_actual_closure_from_rows.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-084` | `tests/test_score_symmetry_aware_ligand_rmsd.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-085` | `tests/test_validate_public_benchmark_pose_validity.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |
| `structural-scope-owner-086` | `tests/test_validate_public_benchmark_subset_manifest.py` | `extract_to_molecular_or_science_repository_or_delete_if_obsolete` |

## Claim Boundary

This is a fill-in owner decision template. It is not approval, does not delete files, and does not close structural scope cleanup until every row has an allowed owner_decision, owner identity/role, decision timestamp, evidence reference, and any delete/extract decision has been applied and followed by a refreshed structural scope audit. Retain decisions require a signed owner-exception reference.
