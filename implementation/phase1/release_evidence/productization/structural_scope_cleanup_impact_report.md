# Structural Scope Cleanup Impact Report

- `summary_line`: `Structural scope cleanup impact report: BLOCKED_CLEANUP_IMPACT | quarantined=86 | references=122 | blocking=73 | owner_pending=86`
- `contract_pass`: `False`
- `cleanup_impact_clear`: `False`
- `quarantined_path_count`: `86`
- `reference_path_count`: `122`
- `blocking_cleanup_reference_path_count`: `73`
- `owner_decision_pending_count`: `86`
- `release_surface_cleanup_blocked_path_count`: `0`
- `blocking_reference_cleanup_batch_count`: `5`

## Reference Roles

- `reference_role_counts`: `{'documentation_reference': 2, 'implementation_runtime_or_manifest_reference': 47, 'other_reference': 1, 'release_governance_reference': 19, 'scope_governance_reference': 30, 'script_reference': 10, 'test_reference': 13}`
- `blocking_reference_role_counts`: `{'documentation_reference': 2, 'implementation_runtime_or_manifest_reference': 47, 'other_reference': 1, 'script_reference': 10, 'test_reference': 13}`
- `blocking_reference_cleanup_action_counts`: `{'delete_or_extract_molecular_script_or_remove_quarantined_path_refs': 10, 'delete_or_extract_molecular_tests_or_update_scope_guard_tests': 13, 'remove_md3bead_runtime_manifest_or_regenerate_structural_runtime_artifacts': 47, 'remove_non_structural_scope_ignore_or_metadata_reference': 1, 'rewrite_structural_docs_to_scope_boundary_only': 2}`

## Cleanup Batches

| Batch | Priority | Role | Paths | Action |
|---|---:|---|---:|---|
| `cleanup_refs_02_implementation_runtime_or_manifest_reference` | 2 | `implementation_runtime_or_manifest_reference` | 47 | `remove_md3bead_runtime_manifest_or_regenerate_structural_runtime_artifacts` |
| `cleanup_refs_03_script_reference` | 3 | `script_reference` | 10 | `delete_or_extract_molecular_script_or_remove_quarantined_path_refs` |
| `cleanup_refs_04_test_reference` | 4 | `test_reference` | 13 | `delete_or_extract_molecular_tests_or_update_scope_guard_tests` |
| `cleanup_refs_05_documentation_reference` | 5 | `documentation_reference` | 2 | `rewrite_structural_docs_to_scope_boundary_only` |
| `cleanup_refs_06_other_reference` | 6 | `other_reference` | 1 | `remove_non_structural_scope_ignore_or_metadata_reference` |

## Release Surface First Impact

| Path | References | Blocking | Governance | Cleanup Ready After Owner Decision |
|---|---:|---:|---:|---:|
| `implementation/phase1/release_evidence/surface/gpcr_hard_decoy_evidence_surface.json` | 35 | 0 | 35 | `True` |
| `implementation/phase1/release_evidence/surface/h_bond_backmap_evidence_surface.json` | 31 | 0 | 31 | `True` |
| `implementation/phase1/release_evidence/surface/pocketmd_lite_science_product_surface.json` | 37 | 0 | 37 | `True` |

## Blocking References

| Path | Role | Terms | Scope Tokens | Quarantined Paths |
|---|---|---:|---|---:|
| `.gitignore` | `other_reference` | 1 | `md3bead` | 5 |
| `README.md` | `documentation_reference` | 0 | `gnina, gpcr, md3bead, pdbbind, pocketmd` | 0 |
| `docs/engine-ai-and-comparison-commercialization-gaps.md` | `documentation_reference` | 2 | `md3bead` | 5 |
| `implementation/phase1/README.md` | `implementation_runtime_or_manifest_reference` | 11 | `md3bead` | 8 |
| `implementation/phase1/branch64_microbatch_profile_report.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/ci-gate-reason-codebook.md` | `implementation_runtime_or_manifest_reference` | 0 | `md3bead` | 0 |
| `implementation/phase1/ci_artifact_manifest.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 1 |
| `implementation/phase1/ci_artifact_manifest.nightly.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 1 |
| `implementation/phase1/ci_artifact_manifest.nightly.require_ndtha.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 1 |
| `implementation/phase1/ci_artifact_manifest.pr.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 1 |
| `implementation/phase1/ci_artifact_manifest.pr.require_hip.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 1 |
| `implementation/phase1/ci_gate_report.json` | `implementation_runtime_or_manifest_reference` | 1 | `md3bead` | 1 |
| `implementation/phase1/ci_gate_report.nightly.json` | `implementation_runtime_or_manifest_reference` | 0 | `md3bead` | 0 |
| `implementation/phase1/ci_gate_report.nightly.require_ndtha.json` | `implementation_runtime_or_manifest_reference` | 1 | `md3bead` | 1 |
| `implementation/phase1/ci_gate_report.pr.json` | `implementation_runtime_or_manifest_reference` | 0 | `md3bead` | 0 |
| `implementation/phase1/ci_gate_report.pr.require_hip.json` | `implementation_runtime_or_manifest_reference` | 0 | `md3bead` | 0 |
| `implementation/phase1/commercial_readiness_report.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/commercialization-gap-redteam-playbook.md` | `implementation_runtime_or_manifest_reference` | 5 | `md3bead` | 5 |
| `implementation/phase1/native_runtime_artifact_manifest.json` | `implementation_runtime_or_manifest_reference` | 7 | `md3bead` | 5 |
| `implementation/phase1/nightly_release_gate_report.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/organize_phase1_workspace.py` | `implementation_runtime_or_manifest_reference` | 1 | `md3bead` | 5 |
| `implementation/phase1/p0_core_gap_report.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/p0_engine_perf_report.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/phase1_ci_gate.py` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 1 |
| `implementation/phase1/physics_branching_report.json` | `implementation_runtime_or_manifest_reference` | 1 | `md3bead` | 1 |
| `implementation/phase1/physics_guided_branching.py` | `implementation_runtime_or_manifest_reference` | 1 | `md3bead` | 1 |
| `implementation/phase1/profile_branch64_microbatch_cache.py` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/profile_p0_engine_path.py` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/release_evidence/commercial/commercial_readiness_report.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/run_megastructure_commercial_readiness.py` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/run_nightly_release_gate.py` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/run_p0_core_gap_pipeline.py` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/run_phase1_steps.py` | `implementation_runtime_or_manifest_reference` | 1 | `md3bead` | 1 |
| `implementation/phase1/run_phase1_topk_pipeline.py` | `implementation_runtime_or_manifest_reference` | 9 | `md3bead` | 7 |
| `implementation/phase1/run_scaleout_io_profile.py` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/runtime_sbom.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/runtime_version_compatibility_matrix.json` | `implementation_runtime_or_manifest_reference` | 1 | `md3bead` | 5 |
| `implementation/phase1/rust_nonlinear_frame_bridge.py` | `implementation_runtime_or_manifest_reference` | 1 | `md3bead` | 5 |
| `implementation/phase1/rust_track_lf_bridge.py` | `implementation_runtime_or_manifest_reference` | 1 | `md3bead` | 5 |
| `implementation/phase1/scaleout_io_profile_report.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/static_artifact_validation_report.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 1 |
| `implementation/phase1/static_artifact_validation_report.nightly.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 1 |
| `implementation/phase1/static_artifact_validation_report.pr.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 1 |
| `implementation/phase1/validate_phase1_artifacts.py` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 1 |
| `implementation/phase1/winning_ticket_backprop.py` | `implementation_runtime_or_manifest_reference` | 1 | `md3bead` | 1 |
| `implementation/phase1/winning_ticket_backprop_report.json` | `implementation_runtime_or_manifest_reference` | 1 | `md3bead` | 1 |
| `implementation/phase1/zero_copy_real_probe.py` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/zero_copy_real_probe_report.forbidden.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/zero_copy_real_probe_report.required.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `implementation/phase1/zero_copy_real_probe_report_strict.json` | `implementation_runtime_or_manifest_reference` | 3 | `md3bead` | 5 |
| `scripts/build_public_benchmark_operator_intake_packet.py` | `script_reference` | 51 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 22 |
| `scripts/build_public_benchmark_source_of_truth.py` | `script_reference` | 39 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 15 |
| `scripts/build_runtime_packaging_manifest.py` | `script_reference` | 3 | `md3bead` | 5 |
| `scripts/check_repo_hygiene.py` | `script_reference` | 1 | `md3bead` | 5 |
| `scripts/materialize_public_benchmark_harness_bundle.py` | `script_reference` | 18 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 12 |
| `scripts/materialize_public_benchmark_operator_bundle_from_rows.py` | `script_reference` | 2 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 2 |
| `scripts/materialize_public_benchmark_phase2_from_rows.py` | `script_reference` | 13 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 13 |
| `scripts/materialize_public_benchmark_rmsd_scorecard.py` | `script_reference` | 4 | `gnina, symmetry_aware_ligand` | 2 |
| `scripts/plan_source_boundary_cleanup.py` | `script_reference` | 1 | `md3bead` | 5 |
| `scripts/validate_public_benchmark_external_receipts.py` | `script_reference` | 0 | `casf_pdbbind, gnina, pdbbind` | 0 |
| `tests/test_build_goal_bottleneck_roadmap_surface.py` | `test_reference` | 0 | `gpcr, md3bead, pocketmd` | 0 |
| `tests/test_build_non_expert_release_briefing_report.py` | `test_reference` | 0 | `gpcr, md3bead, pdbbind, pocketmd` | 0 |
| `tests/test_build_product_capabilities_surface.py` | `test_reference` | 0 | `gpcr, md3bead, pocketmd` | 0 |
| `tests/test_build_public_benchmark_operator_intake_packet.py` | `test_reference` | 35 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 18 |
| `tests/test_build_public_benchmark_source_of_truth.py` | `test_reference` | 42 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 17 |
| `tests/test_build_runtime_packaging_manifest.py` | `test_reference` | 1 | `md3bead` | 5 |
| `tests/test_check_repo_hygiene.py` | `test_reference` | 1 | `md3bead` | 5 |
| `tests/test_materialize_public_benchmark_harness_bundle.py` | `test_reference` | 12 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 6 |
| `tests/test_materialize_public_benchmark_operator_bundle_from_rows.py` | `test_reference` | 2 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 2 |
| `tests/test_materialize_public_benchmark_phase2_from_rows.py` | `test_reference` | 0 | `casf_pdbbind, gnina, pdbbind, posebusters, symmetry_aware_ligand` | 0 |
| `tests/test_materialize_public_benchmark_rmsd_scorecard.py` | `test_reference` | 0 | `pdbbind` | 0 |
| `tests/test_plan_source_boundary_cleanup.py` | `test_reference` | 1 | `md3bead` | 5 |
| `tests/test_validate_public_benchmark_external_receipts.py` | `test_reference` | 0 | `casf_pdbbind, gnina, pdbbind` | 0 |

## Blockers

- `owner_decision_pending_count=86`
- `blocking_cleanup_reference_path_count=73`

## Next Actions

- `record owner delete/extract decisions for quarantined non-structural paths`
- `resolve non-governance references before applying delete/extract cleanup`
- `start blocking reference cleanup with cleanup_refs_02_implementation_runtime_or_manifest_reference`

## Claim Boundary

This impact report is non-mutating. It does not approve owner decisions, delete files, or close scope cleanup. It only identifies non-quarantined tracked references that must be reviewed before PocketMD/GPCR/MD3Bead-family artifacts are deleted or extracted from the structural-analysis repository.
