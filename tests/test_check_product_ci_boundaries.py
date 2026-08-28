from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "check_product_ci_boundaries.py"
)
SPEC = importlib.util.spec_from_file_location(
    "check_product_ci_boundaries",
    SCRIPT_PATH,
)
assert SPEC is not None
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _write_workflows(root: Path) -> None:
    for path, lane in module.REQUIRED_WORKFLOW_LANES.items():
        workflow = root / path
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(
            (
                f"name: {lane}\n"
                "jobs:\n"
                "  verify:\n"
                "    runs-on: ubuntu-24.04\n"
                "    steps:\n"
                f"      - run: python scripts/run_product_ci_lane.py --lane {lane}\n"
            ),
            encoding="utf-8",
        )


def _write_manifest(root: Path, paths: list[str]) -> Path:
    manifest = root / module.DEFAULT_QUARANTINE_MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "path_count": len(paths),
                "paths": [
                    {
                        "path": path,
                        "excluded_from_structural_release_surface": True,
                    }
                    for path in paths
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_classification_assigns_exact_product_ownership() -> None:
    quarantined = {"scripts/materialize_gpcr_rows.py"}

    assert (
        module.classify_path(
            "src/structural_analysis/api/core.py",
            quarantined_paths=quarantined,
        )
        == "core"
    )
    assert (
        module.classify_path(
            "scripts/build_phase2_linear_reference_artifacts.py",
            quarantined_paths=quarantined,
        )
        == "legacy_evidence"
    )
    assert (
        module.classify_path(
            "scripts/materialize_gpcr_rows.py",
            quarantined_paths=quarantined,
        )
        == "molecular_quarantine"
    )
    assert (
        module.classify_path(
            "tests/test_pocketmd_contract.py",
            quarantined_paths=set(),
        )
        == "molecular_quarantine"
    )

    for structural_benchmark_path in (
        "scripts/build_analytic_frame_verification_artifact.py",
        "scripts/build_medium_benchmark_corpus_plan.py",
        "scripts/build_phase3_medium_model_scorecard_readiness_receipt.py",
        "scripts/build_phase6_benchmark_scale_status.py",
        "scripts/build_phase6_silent_import_loss_status.py",
        "scripts/build_developer_preview_rc_status.py",
        "scripts/build_developer_preview_final_gate_owner_packet.py",
        "scripts/build_structural_product_development_roadmap.py",
        "scripts/build_verification_hierarchy_status.py",
        "scripts/run_phase3_medium_model_scorecard_receipt.py",
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
    ):
        assert (
            module.classify_path(
                structural_benchmark_path,
                quarantined_paths=set(),
            )
            == "core"
        )


def test_release_viewer_bundler_is_owned_by_the_core_lane() -> None:
    for path in (
        "implementation/phase1/release_viewer_bundler.py",
        "tests/test_release_viewer_bundler.py",
        "tests/test_structure_viewer_module_boundaries.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_repository_metadata_gates_are_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/check_large_git_blobs.py",
        "scripts/check_pr_issue_metadata.py",
        "tests/test_check_large_git_blobs.py",
        "tests/test_check_pr_issue_metadata.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_core_quality_gates_are_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/check_core_quality.py",
        "tests/test_core_quality_contract.py",
        "tests/test_current_head_readiness_ci.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_native_ci_control_plane_is_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/check_native_ci_contract.py",
        "scripts/check_native_capabilities.py",
        "scripts/check_native_dependency_boundary.py",
        "scripts/check_native_dependency_licenses.py",
        "scripts/classify_native_ci_scope.py",
        "tests/test_native_ci_scope.py",
        "tests/test_native_capability_manifest.py",
        "tests/test_native_ci_workflow_contract.py",
        "tests/test_native_dependency_license.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_adaptive_newton_continuation_is_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/build_phase2_adaptive_newton_continuation_artifacts.py",
        "tests/test_build_phase2_adaptive_newton_continuation_artifacts.py",
        "tests/test_nonlinear_adaptive_continuation.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_corotational_frame_adaptive_continuation_is_core_owned() -> None:
    for path in (
        "src/structural_analysis/assembly/stateful_corotational_fiber_frame2d_adaptive.py",
        "src/structural_analysis/assembly/stateful_corotational_fiber_frame2d_arc_length.py",
        "src/structural_analysis/benchmark/stateful_corotational_fiber_frame2d_diagnostics.py",
        "src/structural_analysis/benchmark/stateful_corotational_composite_frame_cyclic.py",
        "src/structural_analysis/benchmark/stateful_corotational_concrete_frame_cyclic.py",
        "src/structural_analysis/benchmark/stateful_corotational_steel_frame_cyclic.py",
        "src/structural_analysis/assembly/stateful_corotational_fiber_frame2d_link.py",
        "src/structural_analysis/benchmark/stateful_corotational_linked_frame_cyclic.py",
        "src/structural_analysis/benchmark/stateful_corotational_local_axis_linked_frame_cyclic.py",
        "src/structural_analysis/benchmark/stateful_corotational_updated_axis_linked_frame_cyclic.py",
        "src/structural_analysis/benchmark/stateful_corotational_rotational_linked_frame_cyclic.py",
        "src/structural_analysis/materials/bilinear_rotational_link.py",
        "src/structural_analysis/benchmark/stateful_corotational_gap_linked_frame_cyclic.py",
        "src/structural_analysis/benchmark/stateful_corotational_local_axis_gap_linked_frame_cyclic.py",
        "src/structural_analysis/materials/compression_only_gap_link.py",
        "src/structural_analysis/assembly/stateful_corotational_fiber_frame2d_checkpoint_io.py",
        "tests/test_stateful_corotational_fiber_frame2d_adaptive.py",
        "tests/test_stateful_corotational_fiber_frame2d_arc_length.py",
        "tests/test_stateful_corotational_composite_frame_cyclic_benchmark.py",
        "tests/test_stateful_corotational_concrete_frame_cyclic_benchmark.py",
        "tests/test_stateful_corotational_steel_frame_cyclic_benchmark.py",
        "tests/test_stateful_corotational_linked_frame_cyclic_benchmark.py",
        "tests/test_stateful_corotational_local_axis_linked_frame_cyclic_benchmark.py",
        "tests/test_stateful_corotational_updated_axis_linked_frame_cyclic_benchmark.py",
        "tests/test_stateful_corotational_rotational_linked_frame_cyclic_benchmark.py",
        "tests/test_stateful_corotational_gap_linked_frame_cyclic_benchmark.py",
        "tests/test_stateful_corotational_local_axis_gap_linked_frame_cyclic_benchmark.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_state_updated_steel_material_is_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/build_phase2_state_updated_steel_material_artifacts.py",
        "tests/test_build_phase2_state_updated_steel_material_artifacts.py",
        "tests/test_state_updated_steel_material_newton.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_state_updated_concrete_damage_is_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/build_phase2_state_updated_concrete_damage_artifacts.py",
        "tests/test_build_phase2_state_updated_concrete_damage_artifacts.py",
        "tests/test_state_updated_concrete_damage_newton.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_state_updated_composite_section_is_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/build_phase2_state_updated_composite_section_artifacts.py",
        "tests/test_build_phase2_state_updated_composite_section_artifacts.py",
        "tests/test_state_updated_composite_section_newton.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_state_updated_bilinear_link_is_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/build_phase2_state_updated_bilinear_link_artifacts.py",
        "tests/test_build_phase2_state_updated_bilinear_link_artifacts.py",
        "tests/test_state_updated_bilinear_link_newton.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_geometric_nonlinear_benchmarks_are_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/build_phase2_geometric_nonlinear_benchmark_artifacts.py",
        "tests/test_build_phase2_geometric_nonlinear_benchmark_artifacts.py",
        "tests/test_geometric_nonlinear_benchmarks.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_modal_buckling_kernels_are_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/build_phase2_modal_buckling_kernel_artifacts.py",
        "tests/test_build_phase2_modal_buckling_kernel_artifacts.py",
        "tests/test_modal_generalized_eigen_v1.py",
        "tests/test_buckling_generalized_eigen_v1.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_whole_model_modal_path_is_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/build_phase2_whole_model_modal_artifacts.py",
        "tests/test_build_phase2_whole_model_modal_artifacts.py",
        "tests/test_whole_model_modal_analysis.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_whole_model_buckling_path_is_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/build_phase2_whole_model_buckling_artifacts.py",
        "tests/test_build_phase2_whole_model_buckling_artifacts.py",
        "tests/test_whole_model_buckling_analysis.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_external_code_to_code_receipt_is_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/run_external_code_to_code_technical_receipt.py",
        "tests/test_external_code_to_code_technical_receipt.py",
        "scripts/run_external_modal_buckling_technical_receipt.py",
        "tests/test_external_modal_buckling_technical_receipt.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_shallow_arch_arc_length_is_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/build_phase2_shallow_arch_arc_length_artifacts.py",
        "tests/test_build_phase2_shallow_arch_arc_length_artifacts.py",
        "tests/test_nonlinear_arc_length.py",
        "tests/test_shallow_arch_arc_length_benchmark.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_coupled_vector_arc_length_is_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/build_phase2_coupled_shallow_arch_vector_arc_length_artifacts.py",
        "tests/test_build_phase2_coupled_shallow_arch_vector_arc_length_artifacts.py",
        "tests/test_coupled_shallow_arch_vector_arc_length_benchmark.py",
        "tests/test_nonlinear_vector_arc_length.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_arc_length_cpu_fgmres_bridge_is_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts.py",
        "tests/test_build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts.py",
        "tests/test_arc_length_cpu_fgmres_tangent_bridge.py",
        "tests/test_engine_v2_cpu_fgmres_tangent.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_arc_length_cpu_fgmres_continuation_is_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/build_phase2_arc_length_cpu_fgmres_continuation_artifacts.py",
        "tests/test_build_phase2_arc_length_cpu_fgmres_continuation_artifacts.py",
        "tests/test_arc_length_cpu_fgmres_continuation.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_sparse_chain_cpu_fgmres_arc_length_is_owned_by_the_core_lane() -> None:
    for path in (
        "scripts/build_phase2_sparse_chain_cpu_fgmres_arc_length_artifacts.py",
        "tests/test_build_phase2_sparse_chain_cpu_fgmres_arc_length_artifacts.py",
        "tests/test_sparse_chain_cpu_fgmres_arc_length.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_load_coupled_sparse_chain_arc_length_is_owned_by_core_lane() -> None:
    for path in (
        "scripts/build_phase2_load_coupled_sparse_chain_arc_length_artifacts.py",
        ("tests/test_build_phase2_load_coupled_sparse_chain_arc_length_artifacts.py"),
        "tests/test_load_coupled_sparse_chain_arc_length.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_actual_mgt_load_coupled_adapter_is_owned_by_core_lane() -> None:
    for path in (
        "implementation/phase1/g1_mgt_load_coupled_arc_length_adapter.py",
        "scripts/build_g1_mgt_load_coupled_arc_length_adapter_receipt.py",
        "tests/test_build_g1_mgt_load_coupled_arc_length_adapter_receipt.py",
        "tests/test_g1_mgt_load_coupled_arc_length_adapter.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_engine_v2_hip_backend_contracts_are_owned_by_the_core_lane() -> None:
    for path in (
        "tests/test_engine_v2_cpu_fgmres_checkpoint_v1.py",
        "scripts/run_engine_v2_hip_primitive_parity.py",
        "tests/test_engine_v2_hip_primitive_parity.py",
        "tests/test_engine_v2_hip_primitive_parity_runner.py",
        "scripts/run_engine_v2_hip_fgmres_recurrence.py",
        "tests/test_engine_v2_hip_fgmres_recurrence.py",
        "tests/test_engine_v2_hip_fgmres_recurrence_runner.py",
    ):
        assert module.classify_path(path, quarantined_paths=set()) == "core"


def test_boundary_report_accepts_complete_three_lane_partition(
    tmp_path: Path,
) -> None:
    molecular = "scripts/materialize_gpcr_rows.py"
    _write_workflows(tmp_path)
    manifest = _write_manifest(tmp_path, [molecular])
    tracked = [
        "src/structural_analysis/api/core.py",
        "scripts/build_phase2_linear_reference_artifacts.py",
        molecular,
    ]

    payload = module.build_report(
        repo_root=tmp_path,
        quarantine_manifest=manifest,
        tracked_python_paths=tracked,
    )

    assert payload["contract_pass"] is True
    assert payload["status"] == "ready"
    assert payload["lane_counts"] == {
        "core": 1,
        "legacy_evidence": 1,
        "molecular_quarantine": 1,
    }
    assert payload["blockers"] == []


def test_boundary_report_blocks_unmanifested_molecular_python(
    tmp_path: Path,
) -> None:
    _write_workflows(tmp_path)
    manifest = _write_manifest(tmp_path, [])

    payload = module.build_report(
        repo_root=tmp_path,
        quarantine_manifest=manifest,
        tracked_python_paths=["tests/test_gpcr_contract.py"],
    )

    assert payload["contract_pass"] is False
    assert payload["blockers"] == [
        "molecular_python_path_missing_from_quarantine_manifest:"
        "tests/test_gpcr_contract.py"
    ]


def test_boundary_report_blocks_missing_lane_workflow(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, [])

    payload = module.build_report(
        repo_root=tmp_path,
        quarantine_manifest=manifest,
        tracked_python_paths=["src/structural_analysis/api/core.py"],
    )

    assert payload["contract_pass"] is False
    assert any(
        blocker == "workflow_missing:.github/workflows/ci.yml"
        for blocker in payload["blockers"]
    )


def test_boundary_report_blocks_ubuntu_latest_alias(tmp_path: Path) -> None:
    _write_workflows(tmp_path)
    manifest = _write_manifest(tmp_path, [])
    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            "runs-on: ubuntu-24.04",
            "runs-on: ubuntu-latest",
        ),
        encoding="utf-8",
    )

    payload = module.build_report(
        repo_root=tmp_path,
        quarantine_manifest=manifest,
        tracked_python_paths=["src/structural_analysis/api/core.py"],
    )

    assert payload["contract_pass"] is False
    assert (
        "workflow_not_github_hosted:.github/workflows/ci.yml"
        in payload["blockers"]
    )
    assert payload["workflow_contracts"][0]["runner_labels"] == [
        "ubuntu-latest"
    ]


def test_boundary_report_blocks_unknown_runner_label(tmp_path: Path) -> None:
    _write_workflows(tmp_path)
    manifest = _write_manifest(tmp_path, [])
    workflow = tmp_path / ".github/workflows/science-quarantine-ci.yml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            "runs-on: ubuntu-24.04",
            "runs-on: vendor-hosted-linux",
        ),
        encoding="utf-8",
    )

    payload = module.build_report(
        repo_root=tmp_path,
        quarantine_manifest=manifest,
        tracked_python_paths=["src/structural_analysis/api/core.py"],
    )

    assert payload["contract_pass"] is False
    assert (
        "workflow_not_github_hosted:.github/workflows/science-quarantine-ci.yml"
        in payload["blockers"]
    )
