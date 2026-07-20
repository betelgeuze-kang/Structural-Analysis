#!/usr/bin/env python3
"""Run release-quality gates with explicit PR and full modes."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _python() -> str:
    return sys.executable


def _npm() -> str:
    return "npm.cmd" if sys.platform == "win32" else "npm"


def _lane_command(lane: str) -> list[str]:
    return [
        _python(),
        "scripts/run_product_ci_lane.py",
        "--lane",
        lane,
        "--ruff",
        "--compile",
    ]


def _structural_scope_command(*, fail_blocked: bool) -> list[str]:
    command = [
        _python(),
        "scripts/check_structural_scope_contamination.py",
        "--tracked-only",
        "--check",
    ]
    if fail_blocked:
        command.append("--fail-blocked")
    return command


def _pr_commands(
    *,
    p1_failure_mode: str = "core",
    fail_structural_scope_blocked: bool = False,
) -> list[list[str]]:
    source_boundary = [
        _python(),
        "scripts/plan_source_boundary_cleanup.py",
        "--large-file-threshold-mib",
        "10",
        "--allowlist-manifest",
        "implementation/phase1/source_boundary_allowlist.json",
        "--fail-on-candidates",
    ]
    p1_failure_flag = (
        "--fail-blocked" if p1_failure_mode == "blocked" else "--fail-core-open"
    )
    return [
        [_python(), "scripts/check_repo_hygiene.py", "--show-ok"],
        source_boundary,
        [_python(), "scripts/report_source_boundary_footprint.py", "--check"],
        _structural_scope_command(fail_blocked=fail_structural_scope_blocked),
        [
            _python(),
            "scripts/check_product_ci_boundaries.py",
            "--fail-blocked",
        ],
        [_python(), "scripts/check_git_remote_safety.py", "--show-ok"],
        _lane_command("core"),
        [
            _python(),
            "scripts/run_engine_v2_hip_primitive_parity.py",
            "--check",
        ],
        [
            _python(),
            "scripts/run_engine_v2_hip_fgmres_recurrence.py",
            "--compile-only",
            "--check",
        ],
        [
            _python(),
            "scripts/run_engine_v2_hip_sparse_lu_apply.py",
            "--compile-only",
            "--check",
        ],
        [
            _python(),
            "scripts/run_engine_v2_hip_current_tangent_operator.py",
            "--compile-only",
            "--check",
        ],
        [
            _python(),
            "scripts/run_g1_mgt_hip_current_tangent_hardware_parity.py",
            "--check",
        ],
        [
            _python(),
            "scripts/run_engine_v2_hip_fgmres_recurrence.py",
            "--check",
        ],
        [
            _python(),
            "scripts/run_engine_v2_hip_fgmres_device_receipt.py",
            "--out",
            "implementation/phase1/release_evidence/productization/engine_v2_hip_fgmres_gfx1030_device_receipt.json",
            "--check",
        ],
        [
            _python(),
            "scripts/build_engine_v2_hip_fgmres_stage4_status.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_adaptive_newton_continuation_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_state_updated_steel_material_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_state_updated_concrete_damage_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_state_updated_composite_section_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_state_updated_bilinear_link_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_geometric_nonlinear_benchmark_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_modal_buckling_kernel_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_whole_model_modal_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_whole_model_buckling_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/run_external_code_to_code_technical_receipt.py",
            "--check",
        ],
        [
            _python(),
            "scripts/run_external_modal_buckling_technical_receipt.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_shallow_arch_arc_length_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_coupled_shallow_arch_vector_arc_length_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_arc_length_cpu_fgmres_continuation_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_sparse_chain_cpu_fgmres_arc_length_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_load_coupled_sparse_chain_arc_length_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_g1_mgt_load_coupled_arc_length_adapter_receipt.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_g1_mgt_state_updated_frame_axial_geometry_preflight.py",
            "--check",
        ],
        [
            _python(),
            "scripts/"
            "build_g1_mgt_state_updated_frame_axial_geometry_adapter_receipt.py",
            "--check",
        ],
        [
            _python(),
            "scripts/"
            "build_g1_mgt_state_updated_matrix_free_newton_"
            "diagnostic_receipt.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_g1_mgt_matrix_free_preconditioner_candidate_audit.py",
            "--check",
        ],
        [
            _python(),
            "scripts/"
            "build_g1_mgt_semantic_live_linear_newton_continuation_receipt.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_medium_benchmark_corpus_plan.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase3_medium_model_scorecard_readiness_receipt.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_analytic_frame_verification_artifact.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_verification_hierarchy_status.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase6_benchmark_scale_status.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase6_silent_import_loss_status.py",
            "--check",
        ],
        [_python(), "scripts/build_developer_preview_rc_status.py", "--check"],
        [_python(), "scripts/check_p0_closure_status.py", "--json", "--fail-core-open"],
        [_python(), "scripts/check_p1_readiness_status.py", "--json", p1_failure_flag],
        [
            _python(),
            "scripts/check_p1_benchmark_breadth_status.py",
            "--json",
            p1_failure_flag,
        ],
        [_npm(), "ci"],
        [_npm(), "audit", "--audit-level", "high"],
        [
            _python(),
            "scripts/verify_release_artifacts_manifest.py",
            "--manifest",
            "implementation/phase1/release_artifacts_manifest.json",
            "--structure-only",
        ],
        [
            _python(),
            "scripts/verify_open_data_external_artifacts_manifest.py",
            "--manifest",
            "implementation/phase1/open_data_external_artifacts_manifest.json",
            "--structure-only",
        ],
        [_npm(), "run", "verify:frontend-contract"],
        [_npm(), "run", "build"],
        [_npm(), "run", "verify:viewer-manifest"],
        [_python(), "scripts/verify_structure_viewer_contracts.py"],
        [_npm(), "run", "verify:frontend-browser-smoke", "--", "--mode", "minimal"],
        [
            _python(),
            "-m",
            "pytest",
            "-q",
            "tests/test_project_ops_api_service.py",
            "tests/test_engine_v2_cpu_fgmres_checkpoint_v1.py",
            "tests/test_engine_v2_result_ir_v1.py",
            "tests/test_engine_v2_engineering_result_v1.py",
            "tests/test_engine_v2_nonlinear_result_recovery_v1.py",
            "tests/test_engine_v2_nonlinear_recovery_source_binding.py",
            "tests/test_engine_v2_core_dependency_boundary.py",
            "tests/test_engine_v2_hip_primitive_parity.py",
            "tests/test_engine_v2_hip_primitive_parity_runner.py",
            "tests/test_engine_v2_hip_fgmres_recurrence.py",
            "tests/test_engine_v2_hip_fgmres_recurrence_runner.py",
            "tests/test_engine_v2_hip_fgmres_device_receipt.py",
            "tests/test_engine_v2_hip_fgmres_stage4_status.py",
            "tests/test_build_phase2_adaptive_newton_continuation_artifacts.py",
            "tests/test_nonlinear_adaptive_continuation.py",
            "tests/test_build_phase2_state_updated_steel_material_artifacts.py",
            "tests/test_state_updated_steel_material_newton.py",
            "tests/test_build_phase2_state_updated_concrete_damage_artifacts.py",
            "tests/test_state_updated_concrete_damage_newton.py",
            "tests/test_build_phase2_state_updated_composite_section_artifacts.py",
            "tests/test_state_updated_composite_section_newton.py",
            "tests/test_stateful_fiber_section.py",
            "tests/test_stateful_fiber_beam2d.py",
            "tests/test_stateful_fiber_frame2d.py",
            "tests/test_stateful_fiber_frame2d_execution_topology.py",
            "tests/test_stateful_fiber_frame2d_physical_equation_scaling.py",
            "tests/test_stateful_fiber_frame2d_kinematic_state_chain.py",
            "tests/test_stateful_fiber_frame2d_nonlinear_execution_state_binding.py",
            "tests/test_stateful_fiber_frame2d_nonlinear_terminal_receipt.py",
            "tests/test_stateful_fiber_frame2d_nonlinear_result_adapter.py",
            "tests/test_stateful_fiber_frame2d_nonlinear_recovery.py",
            "tests/test_fiber_frame_solver_episode_adapter.py",
            "tests/test_stateful_fiber_frame2d_material_state_bundle.py",
            "tests/test_stateful_fiber_frame2d_material_state_projection_chain.py",
            "tests/test_build_phase2_state_updated_bilinear_link_artifacts.py",
            "tests/test_state_updated_bilinear_link_newton.py",
            "tests/test_build_phase2_geometric_nonlinear_benchmark_artifacts.py",
            "tests/test_geometric_nonlinear_benchmarks.py",
            "tests/test_build_phase2_modal_buckling_kernel_artifacts.py",
            "tests/test_build_phase2_whole_model_modal_artifacts.py",
            "tests/test_whole_model_modal_analysis.py",
            "tests/test_build_phase2_whole_model_buckling_artifacts.py",
            "tests/test_whole_model_buckling_analysis.py",
            "tests/test_external_code_to_code_technical_receipt.py",
            "tests/test_external_modal_buckling_technical_receipt.py",
            "tests/test_modal_generalized_eigen_v1.py",
            "tests/test_buckling_generalized_eigen_v1.py",
            "tests/test_build_phase2_shallow_arch_arc_length_artifacts.py",
            "tests/test_nonlinear_arc_length.py",
            "tests/test_shallow_arch_arc_length_benchmark.py",
            "tests/test_build_phase2_coupled_shallow_arch_vector_arc_length_artifacts.py",
            "tests/test_nonlinear_vector_arc_length.py",
            "tests/test_coupled_shallow_arch_vector_arc_length_benchmark.py",
            "tests/test_build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts.py",
            "tests/test_engine_v2_cpu_fgmres_tangent.py",
            "tests/test_arc_length_cpu_fgmres_tangent_bridge.py",
            "tests/test_build_phase2_arc_length_cpu_fgmres_continuation_artifacts.py",
            "tests/test_arc_length_cpu_fgmres_continuation.py",
            "tests/test_build_phase2_sparse_chain_cpu_fgmres_arc_length_artifacts.py",
            "tests/test_sparse_chain_cpu_fgmres_arc_length.py",
            "tests/test_build_phase2_load_coupled_sparse_chain_arc_length_artifacts.py",
            "tests/test_load_coupled_sparse_chain_arc_length.py",
            "tests/test_build_g1_mgt_load_coupled_arc_length_adapter_receipt.py",
            "tests/test_g1_mgt_load_coupled_arc_length_adapter.py",
            "tests/test_build_g1_mgt_state_updated_frame_axial_geometry_preflight.py",
            "tests/"
            "test_build_g1_mgt_state_updated_frame_axial_geometry_adapter_receipt.py",
            "tests/test_mgt_state_updated_frame_axial_geometry.py",
            "tests/test_mgt_physical_residual_assembly.py",
            "tests/test_matrix_free_cpu_fgmres_state_tangent.py",
            "tests/"
            "test_build_g1_mgt_state_updated_matrix_free_newton_"
            "diagnostic_receipt.py",
            "tests/test_g1_mgt_semantic_live_linear_newton_continuation.py",
            "tests/"
            "test_build_g1_mgt_semantic_live_linear_newton_continuation_receipt.py",
            "tests/test_benchmark_scientific_acceptance.py",
            "tests/test_analytic_frame_verification.py",
            "tests/test_build_medium_benchmark_corpus_plan.py",
            "tests/test_build_phase3_medium_model_scorecard_readiness_receipt.py",
            "tests/test_build_phase6_benchmark_scale_status.py",
            "tests/test_build_phase6_silent_import_loss_status.py",
            "tests/test_build_developer_preview_rc_status.py",
            "tests/test_build_developer_preview_final_gate_owner_packet.py",
            "tests/test_build_structural_product_development_roadmap.py",
            "tests/test_build_verification_hierarchy_status.py",
            "tests/test_medium_benchmark_corpus_contract.py",
            "tests/test_run_phase3_medium_model_scorecard_receipt.py",
            "tests/test_verification_hierarchy_contract.py",
            "tests/test_source_boundary_ci_contract.py",
            "tests/test_source_boundary_footprint_report.py",
            "tests/test_structural_analysis_core_api.py",
            "tests/test_runtime_dependency_contract.py",
            "tests/test_midas_mgt_nodal_load_contract.py",
            "tests/test_structure_viewer_dom_safety_contract.py",
            "tests/test_structure_viewer_workbench_v2_product_shell_contract.py",
            "tests/test_check_product_ci_boundaries.py",
            "tests/test_product_ci_workflow_contract.py",
            "tests/test_verify_quality_gate_contract.py",
        ],
        [
            _python(),
            "-m",
            "pytest",
            "-q",
            "tests/test_engine_v2_canonical_contract.py",
            "tests/test_engine_v2_current_tangent_operator_v1.py",
            "tests/test_engine_v2_hip_current_tangent_operator.py",
            "tests/test_engine_v2_hip_current_tangent_operator_runner.py",
            "tests/test_run_g1_mgt_hip_current_tangent_hardware_parity.py",
            "tests/test_canonical_sparse_lu_factor.py",
            "tests/test_engine_v2_hip_sparse_lu_apply.py",
            "tests/test_engine_v2_hip_sparse_lu_apply_runner.py",
            "tests/test_build_g1_mgt_matrix_free_preconditioner_candidate_audit.py",
            "-k",
            "not test_committed_receipt_is_reproducible and not "
            "test_committed_receipt_recomputes_cpu_reference_offline",
        ],
    ]


def _command_groups(mode: str) -> list[list[str]]:
    if mode == "pr":
        # Quarantined non-structural paths are valid while they remain fully
        # manifested and excluded from the structural product surface. The PR
        # lane checks audit consistency but leaves owner-decision closure to the
        # full/release lane and the dedicated quarantine workflow.
        return _pr_commands(
            p1_failure_mode="core",
            fail_structural_scope_blocked=False,
        )
    if mode == "release":
        return [
            *_command_groups("full"),
            [
                _python(),
                "scripts/check_github_actions_runner_policy.py",
                "--fail-blocked",
            ],
            [
                _python(),
                "scripts/check_github_actions_self_hosted_runner_status.py",
                "--out",
                "implementation/phase1/release_evidence/productization/"
                "github_actions_self_hosted_runner_status.json",
                "--check",
                "--fail-blocked",
            ],
            [
                _python(),
                "scripts/build_product_readiness_snapshot.py",
                "--out",
                "implementation/phase1/release_evidence/productization/"
                "product_readiness_snapshot.json",
                "--check",
                "--fail-blocked",
            ],
            [
                _python(),
                "-m",
                "pytest",
                "-q",
                "tests/test_product_readiness_snapshot_doc_sync.py",
            ],
            ["git", "diff", "--check"],
        ]
    return [
        [_python(), "scripts/check_p0_closure_status.py", "--json", "--fail-open"],
        *_pr_commands(
            p1_failure_mode="blocked",
            fail_structural_scope_blocked=True,
        ),
        _lane_command("legacy_evidence"),
        _lane_command("molecular_quarantine"),
        [_python(), "-m", "pytest", "-q"],
        [_npm(), "run", "verify:frontend-browser-smoke"],
        [_npm(), "run", "verify:viewer-report-pdf"],
        [_npm(), "run", "verify:viewer-performance-probe"],
        [_npm(), "run", "verify:viewer-visual-regression"],
        [
            _python(),
            "scripts/report_commercialization_level.py",
            "--closure-mode",
            "conditional",
            "--fail-below",
            "9.0",
        ],
        [_python(), "scripts/build_developer_preview_readiness.py", "--check"],
        [_python(), "scripts/build_phase1_core_api_contract_artifacts.py", "--check"],
        [_python(), "scripts/build_phase2_linear_reference_artifacts.py", "--check"],
        [
            _python(),
            "scripts/build_phase2_newton_globalization_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_adaptive_newton_continuation_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_state_updated_steel_material_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_state_updated_concrete_damage_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_state_updated_composite_section_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_state_updated_bilinear_link_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_geometric_nonlinear_benchmark_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_modal_buckling_kernel_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_whole_model_modal_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_whole_model_buckling_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_shallow_arch_arc_length_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_coupled_shallow_arch_vector_arc_length_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_arc_length_cpu_fgmres_continuation_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_sparse_chain_cpu_fgmres_arc_length_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_load_coupled_sparse_chain_arc_length_artifacts.py",
            "--check",
        ],
        [_python(), "scripts/build_phase2_nonlinear_load_step_artifacts.py", "--check"],
        [
            _python(),
            "scripts/build_phase2_material_newton_breadth_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_material_mesh_newton_artifacts.py",
            "--check",
        ],
        [_python(), "scripts/build_phase2_patch_rigidbody_artifacts.py", "--check"],
        [
            _python(),
            "scripts/build_phase2_mesh_load_step_convergence_artifacts.py",
            "--check",
        ],
        [
            _python(),
            "scripts/build_phase2_frame_shell_material_coupling_artifacts.py",
            "--check",
        ],
        [_python(), "scripts/build_phase3_benchmark_factory_artifacts.py", "--check"],
        [_python(), "scripts/check_workstation_delivery_readiness.py", "--json"],
        [_python(), "scripts/check_independent_product_readiness.py", "--json"],
        [_python(), "scripts/check_generated_worktree_clean.py", "--show-ok"],
        ["git", "diff", "--check"],
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("pr", "full", "release"), default="pr")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    exit_code = 0
    for command in _command_groups(args.mode):
        print(" ".join(command), flush=True)
        if args.dry_run:
            continue
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode != 0:
            if args.mode != "release":
                return int(result.returncode)
            exit_code = exit_code or int(result.returncode)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
