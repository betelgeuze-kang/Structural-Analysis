from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_quality_gate_module() -> ModuleType:
    script_path = REPO_ROOT / "scripts" / "verify_quality_gate.py"
    spec = importlib.util.spec_from_file_location(
        "verify_quality_gate_contract",
        script_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pytest_targets(commands: list[list[str]]) -> set[str]:
    targets: set[str] = set()
    for command in commands:
        if "pytest" not in command:
            continue
        targets.update(item for item in command if item.startswith("tests/"))
    return targets


def test_pr_quality_gate_keeps_core_adapter_and_viewer_regression_tests() -> None:
    gate = _load_quality_gate_module()
    commands = gate._command_groups("pr")
    targets = _pytest_targets(commands)

    assert "tests/test_structural_analysis_core_api.py" in targets
    assert "tests/test_engine_v2_cpu_fgmres_checkpoint_v1.py" in targets
    assert "tests/test_engine_v2_result_ir_v1.py" in targets
    assert "tests/test_engine_v2_engineering_result_v1.py" in targets
    assert "tests/test_engine_v2_nonlinear_result_recovery_v1.py" in targets
    assert "tests/test_engine_v2_nonlinear_recovery_source_binding.py" in targets
    assert "tests/test_engine_v2_core_dependency_boundary.py" in targets
    assert "tests/test_engine_v2_hip_primitive_parity.py" in targets
    assert "tests/test_engine_v2_hip_primitive_parity_runner.py" in targets
    assert "tests/test_engine_v2_hip_fgmres_recurrence.py" in targets
    assert "tests/test_engine_v2_hip_fgmres_recurrence_runner.py" in targets
    assert "tests/test_engine_v2_hip_fgmres_device_receipt.py" in targets
    assert "tests/test_engine_v2_hip_fgmres_stage4_status.py" in targets
    assert "tests/test_engine_v2_canonical_contract.py" in targets
    assert "tests/test_engine_v2_current_tangent_operator_v1.py" in targets
    assert "tests/test_engine_v2_hip_current_tangent_operator.py" in targets
    assert "tests/test_engine_v2_hip_current_tangent_operator_runner.py" in targets
    assert "tests/test_canonical_sparse_lu_factor.py" in targets
    assert "tests/test_engine_v2_hip_sparse_lu_apply.py" in targets
    assert "tests/test_engine_v2_hip_sparse_lu_apply_runner.py" in targets
    assert (
        "tests/test_build_g1_mgt_matrix_free_preconditioner_candidate_audit.py"
        in targets
    )
    assert "tests/test_runtime_dependency_contract.py" in targets
    assert "tests/test_midas_mgt_nodal_load_contract.py" in targets
    assert "tests/test_structure_viewer_dom_safety_contract.py" in targets
    assert (
        "tests/test_structure_viewer_workbench_v2_product_shell_contract.py" in targets
    )
    assert (
        "tests/test_build_phase2_adaptive_newton_continuation_artifacts.py" in targets
    )
    assert "tests/test_nonlinear_adaptive_continuation.py" in targets
    assert (
        "tests/test_build_phase2_state_updated_steel_material_artifacts.py" in targets
    )
    assert "tests/test_state_updated_steel_material_newton.py" in targets
    assert (
        "tests/test_build_phase2_state_updated_concrete_damage_artifacts.py" in targets
    )
    assert "tests/test_state_updated_concrete_damage_newton.py" in targets
    assert (
        "tests/test_build_phase2_state_updated_composite_section_artifacts.py"
        in targets
    )
    assert "tests/test_state_updated_composite_section_newton.py" in targets
    assert "tests/test_stateful_fiber_section.py" in targets
    assert "tests/test_stateful_fiber_beam2d.py" in targets
    assert "tests/test_stateful_fiber_frame2d.py" in targets
    assert "tests/test_stateful_fiber_frame2d_execution_topology.py" in targets
    assert "tests/test_stateful_fiber_frame2d_physical_equation_scaling.py" in targets
    assert "tests/test_stateful_fiber_frame2d_kinematic_state_chain.py" in targets
    assert (
        "tests/test_stateful_fiber_frame2d_nonlinear_execution_state_binding.py"
        in targets
    )
    assert "tests/test_stateful_fiber_frame2d_nonlinear_terminal_receipt.py" in targets
    assert "tests/test_stateful_fiber_frame2d_nonlinear_result_adapter.py" in targets
    assert "tests/test_stateful_fiber_frame2d_nonlinear_recovery.py" in targets
    assert "tests/test_public_rc_fiber_frame_api.py" in targets
    assert "tests/test_fiber_frame_solver_episode_adapter.py" in targets
    assert "tests/test_stateful_fiber_frame2d_material_state_bundle.py" in targets
    assert (
        "tests/test_stateful_fiber_frame2d_material_state_projection_chain.py"
        in targets
    )
    assert "tests/test_build_phase2_state_updated_bilinear_link_artifacts.py" in targets
    assert "tests/test_state_updated_bilinear_link_newton.py" in targets
    assert (
        "tests/test_build_phase2_geometric_nonlinear_benchmark_artifacts.py" in targets
    )
    assert "tests/test_geometric_nonlinear_benchmarks.py" in targets
    assert "tests/test_corotational_frame2d_basic_kinematics.py" in targets
    assert "tests/test_corotational_frame2d_element.py" in targets
    assert "tests/test_stateful_corotational_fiber_beam2d.py" in targets
    assert "tests/test_stateful_corotational_fiber_frame2d.py" in targets
    assert "tests/test_stateful_corotational_fiber_frame2d_adaptive.py" in targets
    assert "tests/test_stateful_corotational_fiber_frame2d_arc_length.py" in targets
    assert (
        "tests/test_stateful_corotational_composite_frame_cyclic_benchmark.py"
        in targets
    )
    assert (
        "tests/test_stateful_corotational_concrete_frame_cyclic_benchmark.py" in targets
    )
    assert "tests/test_stateful_corotational_steel_frame_cyclic_benchmark.py" in targets
    assert (
        "tests/test_stateful_corotational_linked_frame_cyclic_benchmark.py" in targets
    )
    assert (
        "tests/test_stateful_corotational_local_axis_linked_frame_cyclic_benchmark.py"
        in targets
    )
    assert (
        "tests/test_stateful_corotational_updated_axis_linked_frame_cyclic_benchmark.py"
        in targets
    )
    assert (
        "tests/test_stateful_corotational_rotational_linked_frame_cyclic_benchmark.py"
        in targets
    )
    assert (
        "tests/test_stateful_corotational_gap_linked_frame_cyclic_benchmark.py"
        in targets
    )
    assert "tests/test_stateful_corotational_fiber_frame2d_solver.py" in targets
    assert "tests/test_lee_frame_snapthrough_benchmark.py" in targets
    assert "tests/test_build_phase2_modal_buckling_kernel_artifacts.py" in targets
    assert "tests/test_build_phase2_whole_model_modal_artifacts.py" in targets
    assert "tests/test_whole_model_modal_analysis.py" in targets
    assert "tests/test_build_phase2_whole_model_buckling_artifacts.py" in targets
    assert "tests/test_whole_model_buckling_analysis.py" in targets
    assert "tests/test_external_code_to_code_technical_receipt.py" in targets
    assert "tests/test_external_modal_buckling_technical_receipt.py" in targets
    assert "tests/test_modal_generalized_eigen_v1.py" in targets
    assert "tests/test_buckling_generalized_eigen_v1.py" in targets
    assert "tests/test_build_phase2_shallow_arch_arc_length_artifacts.py" in targets
    assert "tests/test_nonlinear_arc_length.py" in targets
    assert "tests/test_shallow_arch_arc_length_benchmark.py" in targets
    assert (
        "tests/test_build_phase2_coupled_shallow_arch_vector_arc_length_artifacts.py"
        in targets
    )
    assert "tests/test_nonlinear_vector_arc_length.py" in targets
    assert "tests/test_coupled_shallow_arch_vector_arc_length_benchmark.py" in targets
    assert (
        "tests/test_build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts.py"
        in targets
    )
    assert "tests/test_engine_v2_cpu_fgmres_tangent.py" in targets
    assert "tests/test_arc_length_cpu_fgmres_tangent_bridge.py" in targets
    assert (
        "tests/test_build_phase2_arc_length_cpu_fgmres_continuation_artifacts.py"
        in targets
    )
    assert "tests/test_arc_length_cpu_fgmres_continuation.py" in targets
    assert (
        "tests/test_build_phase2_sparse_chain_cpu_fgmres_arc_length_artifacts.py"
        in targets
    )
    assert "tests/test_sparse_chain_cpu_fgmres_arc_length.py" in targets
    assert (
        "tests/"
        "test_build_phase2_load_coupled_sparse_chain_arc_length_artifacts.py" in targets
    )
    assert "tests/test_load_coupled_sparse_chain_arc_length.py" in targets
    assert (
        "tests/test_build_g1_mgt_load_coupled_arc_length_adapter_receipt.py" in targets
    )
    assert "tests/test_g1_mgt_load_coupled_arc_length_adapter.py" in targets
    assert (
        "tests/test_build_g1_mgt_state_updated_frame_axial_geometry_preflight.py"
        in targets
    )
    assert (
        "tests/"
        "test_build_g1_mgt_state_updated_frame_axial_geometry_adapter_receipt.py"
        in targets
    )
    assert (
        "tests/"
        "test_build_g1_mgt_state_updated_matrix_free_newton_"
        "diagnostic_receipt.py" in targets
    )
    assert "tests/test_mgt_state_updated_frame_axial_geometry.py" in targets
    assert "tests/test_mgt_physical_residual_assembly.py" in targets
    assert "tests/test_matrix_free_cpu_fgmres_state_tangent.py" in targets
    assert "tests/test_g1_mgt_semantic_live_linear_newton_continuation.py" in targets
    assert (
        "tests/"
        "test_build_g1_mgt_semantic_live_linear_newton_continuation_receipt.py"
        in targets
    )
    assert "tests/test_verify_quality_gate_contract.py" in targets
    assert [
        gate._python(),
        "scripts/run_engine_v2_hip_primitive_parity.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/run_engine_v2_hip_fgmres_recurrence.py",
        "--compile-only",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/run_engine_v2_hip_sparse_lu_apply.py",
        "--compile-only",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/run_engine_v2_hip_current_tangent_operator.py",
        "--compile-only",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/run_g1_mgt_hip_current_tangent_hardware_parity.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/run_engine_v2_hip_fgmres_recurrence.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/run_engine_v2_hip_fgmres_device_receipt.py",
        "--out",
        "implementation/phase1/release_evidence/productization/engine_v2_hip_fgmres_gfx1030_device_receipt.json",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_engine_v2_hip_fgmres_stage4_status.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase2_adaptive_newton_continuation_artifacts.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase2_state_updated_bilinear_link_artifacts.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase2_geometric_nonlinear_benchmark_artifacts.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase2_modal_buckling_kernel_artifacts.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase2_whole_model_modal_artifacts.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase2_whole_model_buckling_artifacts.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/run_external_code_to_code_technical_receipt.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/run_external_modal_buckling_technical_receipt.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase2_shallow_arch_arc_length_artifacts.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase2_coupled_shallow_arch_vector_arc_length_artifacts.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase2_arc_length_cpu_fgmres_continuation_artifacts.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase2_sparse_chain_cpu_fgmres_arc_length_artifacts.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase2_load_coupled_sparse_chain_arc_length_artifacts.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_g1_mgt_load_coupled_arc_length_adapter_receipt.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_g1_mgt_state_updated_frame_axial_geometry_preflight.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_g1_mgt_state_updated_frame_axial_geometry_adapter_receipt.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_g1_mgt_state_updated_matrix_free_newton_diagnostic_receipt.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_g1_mgt_matrix_free_preconditioner_candidate_audit.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_g1_mgt_semantic_live_linear_newton_continuation_receipt.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase2_state_updated_composite_section_artifacts.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase2_state_updated_concrete_damage_artifacts.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase2_state_updated_steel_material_artifacts.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
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
    ] in commands


def test_pr_quality_gate_owns_scientific_medium_benchmark_contracts() -> None:
    gate = _load_quality_gate_module()
    commands = gate._command_groups("pr")
    targets = _pytest_targets(commands)

    assert "tests/test_benchmark_scientific_acceptance.py" in targets
    assert "tests/test_analytic_frame_verification.py" in targets
    assert "tests/test_build_medium_benchmark_corpus_plan.py" in targets
    assert (
        "tests/test_build_phase3_medium_model_scorecard_readiness_receipt.py" in targets
    )
    assert "tests/test_build_phase6_benchmark_scale_status.py" in targets
    assert "tests/test_build_phase6_silent_import_loss_status.py" in targets
    assert "tests/test_build_developer_preview_rc_status.py" in targets
    assert "tests/test_build_developer_preview_final_gate_owner_packet.py" in targets
    assert "tests/test_build_structural_product_development_roadmap.py" in targets
    assert "tests/test_build_verification_hierarchy_status.py" in targets
    assert "tests/test_medium_benchmark_corpus_contract.py" in targets
    assert "tests/test_run_phase3_medium_model_scorecard_receipt.py" in targets
    assert "tests/test_verification_hierarchy_contract.py" in targets
    assert [
        gate._python(),
        "scripts/build_medium_benchmark_corpus_plan.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase3_medium_model_scorecard_readiness_receipt.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_analytic_frame_verification_artifact.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_verification_hierarchy_status.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase6_benchmark_scale_status.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_phase6_silent_import_loss_status.py",
        "--check",
    ] in commands
    assert [
        gate._python(),
        "scripts/build_developer_preview_rc_status.py",
        "--check",
    ] in commands
