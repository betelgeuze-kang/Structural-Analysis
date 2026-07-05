# Structural Scope Cleanup Impact Report

- `summary_line`: `Structural scope cleanup impact report: BLOCKED_CLEANUP_IMPACT | quarantined=251 | references=127 | blocking=56 | owner_pending=251`
- `contract_pass`: `False`
- `cleanup_impact_clear`: `False`
- `quarantined_path_count`: `251`
- `reference_path_count`: `127`
- `blocking_cleanup_reference_path_count`: `56`
- `owner_decision_pending_count`: `251`
- `release_surface_cleanup_blocked_path_count`: `2`
- `blocking_reference_cleanup_batch_count`: `4`
- `release_freshness_source_boundary_reference_count`: `1`

## Reference Roles

- `reference_role_counts`: `{'documentation_reference': 1, 'implementation_runtime_or_manifest_reference': 28, 'productization_evidence_reference': 14, 'release_governance_reference': 19, 'scope_governance_reference': 39, 'script_reference': 12, 'test_reference': 14}`
- `blocking_reference_role_counts`: `{'implementation_runtime_or_manifest_reference': 24, 'productization_evidence_reference': 11, 'script_reference': 11, 'test_reference': 10}`
- `blocking_reference_cleanup_action_counts`: `{'delete_or_extract_molecular_script_or_remove_quarantined_path_refs': 11, 'delete_or_extract_molecular_tests_or_update_scope_guard_tests': 10, 'regenerate_release_evidence_without_molecular_scope_references': 11, 'remove_md3bead_runtime_manifest_or_regenerate_structural_runtime_artifacts': 24}`

## Cleanup Batches

| Batch | Priority | Role | Paths | Source-Boundary Paths | Action |
|---|---:|---|---:|---:|---|
| `cleanup_refs_01_productization_evidence_reference` | 1 | `productization_evidence_reference` | 11 | 0 | `regenerate_release_evidence_without_molecular_scope_references` |
| `cleanup_refs_02_implementation_runtime_or_manifest_reference` | 2 | `implementation_runtime_or_manifest_reference` | 24 | 1 | `remove_md3bead_runtime_manifest_or_regenerate_structural_runtime_artifacts` |
| `cleanup_refs_03_script_reference` | 3 | `script_reference` | 11 | 0 | `delete_or_extract_molecular_script_or_remove_quarantined_path_refs` |
| `cleanup_refs_04_test_reference` | 4 | `test_reference` | 10 | 0 | `delete_or_extract_molecular_tests_or_update_scope_guard_tests` |

## Release Surface First Impact

| Path | References | Blocking | Governance | Cleanup Ready After Owner Decision |
|---|---:|---:|---:|---:|
| `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json` | 39 | 1 | 38 | `False` |
| `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json` | 34 | 0 | 34 | `True` |
| `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json` | 40 | 1 | 39 | `False` |

## Blocking References

| Path | Role | Source Boundary | Terms | Scope Tokens | Quarantined Paths |
|---|---|---:|---:|---|---:|
| `implementation/phase1/README.md` | `implementation_runtime_or_manifest_reference` | `True` | 11 | `md3bead` | 8 |
| `implementation/phase1/ci_artifact_manifest.json` | `implementation_runtime_or_manifest_reference` | `False` | 3 | `md3bead` | 1 |
| `implementation/phase1/ci_artifact_manifest.nightly.json` | `implementation_runtime_or_manifest_reference` | `False` | 3 | `md3bead` | 1 |
| `implementation/phase1/ci_artifact_manifest.nightly.require_ndtha.json` | `implementation_runtime_or_manifest_reference` | `False` | 3 | `md3bead` | 1 |
| `implementation/phase1/ci_artifact_manifest.pr.json` | `implementation_runtime_or_manifest_reference` | `False` | 3 | `md3bead` | 1 |
| `implementation/phase1/ci_artifact_manifest.pr.require_hip.json` | `implementation_runtime_or_manifest_reference` | `False` | 3 | `md3bead` | 1 |
| `implementation/phase1/ci_gate_report.json` | `implementation_runtime_or_manifest_reference` | `False` | 1 | `md3bead` | 1 |
| `implementation/phase1/ci_gate_report.nightly.require_ndtha.json` | `implementation_runtime_or_manifest_reference` | `False` | 1 | `md3bead` | 1 |
| `implementation/phase1/commercial_readiness_report.json` | `implementation_runtime_or_manifest_reference` | `False` | 3 | `md3bead` | 5 |
| `implementation/phase1/commercialization-gap-redteam-playbook.md` | `implementation_runtime_or_manifest_reference` | `False` | 5 | `md3bead` | 5 |
| `implementation/phase1/nightly_release_gate_report.json` | `implementation_runtime_or_manifest_reference` | `False` | 3 | `md3bead` | 5 |
| `implementation/phase1/p0_core_gap_report.json` | `implementation_runtime_or_manifest_reference` | `False` | 3 | `md3bead` | 5 |
| `implementation/phase1/phase1_ci_gate.py` | `implementation_runtime_or_manifest_reference` | `False` | 3 | `md3bead` | 1 |
| `implementation/phase1/physics_branching_report.json` | `implementation_runtime_or_manifest_reference` | `False` | 1 | `md3bead` | 1 |
| `implementation/phase1/physics_guided_branching.py` | `implementation_runtime_or_manifest_reference` | `False` | 1 | `md3bead` | 1 |
| `implementation/phase1/release_evidence/commercial/commercial_readiness_report.json` | `implementation_runtime_or_manifest_reference` | `False` | 3 | `md3bead` | 5 |
| `implementation/phase1/release_evidence/productization/public_benchmark_external_receipts_validation.json` | `productization_evidence_reference` | `False` | 1 | `casf_pdbbind, gnina, pdbbind` | 72 |
| `implementation/phase1/release_evidence/productization/public_benchmark_harness_bundle.json` | `productization_evidence_reference` | `False` | 19 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 78 |
| `implementation/phase1/release_evidence/productization/public_benchmark_harness_bundle_materialization_report.json` | `productization_evidence_reference` | `False` | 22 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 79 |
| `implementation/phase1/release_evidence/productization/public_benchmark_operator_bundle.json` | `productization_evidence_reference` | `False` | 72 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 79 |
| `implementation/phase1/release_evidence/productization/public_benchmark_operator_intake_packet.json` | `productization_evidence_reference` | `False` | 227 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 120 |
| `implementation/phase1/release_evidence/productization/public_benchmark_operator_intake_packet.md` | `productization_evidence_reference` | `False` | 78 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 101 |
| `implementation/phase1/release_evidence/productization/public_benchmark_phase2_row_audit.json` | `productization_evidence_reference` | `False` | 102 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 113 |
| `implementation/phase1/release_evidence/productization/public_benchmark_phase2_row_audit.md` | `productization_evidence_reference` | `False` | 13 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 76 |
| `implementation/phase1/release_evidence/productization/public_benchmark_phase2_source_acquisition_plan.json` | `productization_evidence_reference` | `False` | 198 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 113 |
| `implementation/phase1/release_evidence/productization/public_benchmark_phase2_source_acquisition_plan.md` | `productization_evidence_reference` | `False` | 77 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 106 |
| `implementation/phase1/release_evidence/productization/public_benchmark_source_of_truth.json` | `productization_evidence_reference` | `False` | 224 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 121 |
| `implementation/phase1/run_phase1_steps.py` | `implementation_runtime_or_manifest_reference` | `False` | 1 | `md3bead` | 1 |
| `implementation/phase1/run_phase1_topk_pipeline.py` | `implementation_runtime_or_manifest_reference` | `False` | 9 | `md3bead` | 7 |
| `implementation/phase1/static_artifact_validation_report.json` | `implementation_runtime_or_manifest_reference` | `False` | 3 | `md3bead` | 1 |
| `implementation/phase1/static_artifact_validation_report.nightly.json` | `implementation_runtime_or_manifest_reference` | `False` | 3 | `md3bead` | 1 |
| `implementation/phase1/static_artifact_validation_report.pr.json` | `implementation_runtime_or_manifest_reference` | `False` | 3 | `md3bead` | 1 |
| `implementation/phase1/validate_phase1_artifacts.py` | `implementation_runtime_or_manifest_reference` | `False` | 3 | `md3bead` | 1 |
| `implementation/phase1/winning_ticket_backprop.py` | `implementation_runtime_or_manifest_reference` | `False` | 1 | `md3bead` | 1 |
| `implementation/phase1/winning_ticket_backprop_report.json` | `implementation_runtime_or_manifest_reference` | `False` | 1 | `md3bead` | 1 |
| `scripts/build_goal_bottleneck_roadmap_surface.py` | `script_reference` | `False` | 11 | `gnina, gpcr, pdbbind, pocketmd, posebusters, science_actual` | 82 |
| `scripts/build_public_benchmark_operator_intake_packet.py` | `script_reference` | `False` | 74 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 109 |
| `scripts/build_public_benchmark_phase2_source_acquisition_plan.py` | `script_reference` | `False` | 69 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 103 |
| `scripts/build_public_benchmark_source_of_truth.py` | `script_reference` | `False` | 50 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 88 |
| `scripts/materialize_public_benchmark_casf_pose_rows.py` | `script_reference` | `False` | 5 | `gnina, pdbbind, symmetry_aware_ligand` | 3 |
| `scripts/materialize_public_benchmark_dude_enrichment_rows.py` | `script_reference` | `False` | 2 | `pdbbind` | 1 |
| `scripts/materialize_public_benchmark_harness_bundle.py` | `script_reference` | `False` | 21 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 85 |
| `scripts/materialize_public_benchmark_operator_bundle_from_rows.py` | `script_reference` | `False` | 4 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 75 |
| `scripts/materialize_public_benchmark_phase2_from_rows.py` | `script_reference` | `False` | 32 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 98 |
| `scripts/materialize_public_benchmark_rmsd_scorecard.py` | `script_reference` | `False` | 4 | `gnina, symmetry_aware_ligand` | 2 |
| `scripts/validate_public_benchmark_external_receipts.py` | `script_reference` | `False` | 1 | `casf_pdbbind, gnina, pdbbind` | 72 |
| `tests/test_build_goal_bottleneck_roadmap_surface.py` | `test_reference` | `False` | 13 | `casf_pdbbind, gnina, gpcr, h_bond, md3bead, pdbbind, pocketmd, posebusters, science_actual, symmetry_aware_ligand` | 84 |
| `tests/test_build_public_benchmark_operator_intake_packet.py` | `test_reference` | `False` | 73 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 106 |
| `tests/test_build_public_benchmark_phase2_source_acquisition_plan.py` | `test_reference` | `False` | 37 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 92 |
| `tests/test_build_public_benchmark_source_of_truth.py` | `test_reference` | `False` | 59 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 103 |
| `tests/test_build_support_bundle.py` | `test_reference` | `False` | 6 | `gpcr, pocketmd` | 2 |
| `tests/test_materialize_public_benchmark_dude_enrichment_rows.py` | `test_reference` | `False` | 2 | `` | 1 |
| `tests/test_materialize_public_benchmark_harness_bundle.py` | `test_reference` | `False` | 13 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 78 |
| `tests/test_materialize_public_benchmark_operator_bundle_from_rows.py` | `test_reference` | `False` | 4 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 75 |
| `tests/test_materialize_public_benchmark_phase2_from_rows.py` | `test_reference` | `False` | 42 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 92 |
| `tests/test_validate_public_benchmark_external_receipts.py` | `test_reference` | `False` | 1 | `casf_pdbbind, gnina, pdbbind` | 72 |

## Blockers

- `owner_decision_pending_count=251`
- `blocking_cleanup_reference_path_count=56`

## Next Actions

- `record owner delete/extract decisions for quarantined non-structural paths`
- `resolve non-governance references before applying delete/extract cleanup`
- `start blocking reference cleanup with cleanup_refs_01_productization_evidence_reference`

## Claim Boundary

This impact report is non-mutating. It does not approve owner decisions, delete files, or close scope cleanup. It only identifies non-quarantined tracked references that must be reviewed before PocketMD/GPCR/MD3Bead-family artifacts are deleted or extracted from the structural-analysis repository.
