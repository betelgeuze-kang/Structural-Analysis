from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/build_phase2_nonlinear_load_step_artifacts.py"
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location(
    "build_phase2_nonlinear_load_step_artifacts",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_phase2_nonlinear_load_step_builds_honest_seed_artifacts() -> None:
    artifacts = module.build_nonlinear_load_step_artifacts(repo_root=REPO_ROOT)
    summary = artifacts["summary"]
    partitions_payload = artifacts["partitions"]
    partitions = partitions_payload["partitions"]

    assert summary["status"] == "ready"
    assert summary["contract_pass"] is True
    assert summary["g1_closure_claim"] is False
    assert summary["nonlinear_newton_closure_claim"] is False
    assert summary["residual_contract"] == "F_internal_minus_F_external"
    assert summary["partition_step_counts"] == [1, 2, 4, 8]
    assert summary["partition_spread_gate_passed"] is True
    assert summary["full_load_gate_passed"] is True
    assert summary["max_partition_final_displacement_spread_m"] <= 1.0e-10
    assert summary["blockers_remaining"] == [
        "full_mesh_full_load_nonlinear_equilibrium_not_closed",
        "frame_shell_material_coupling_not_closed",
        "mesh_load_step_nonlinear_convergence_suite_not_closed",
        "sparse_matrix_backend_not_closed",
        "production_rocm_hip_parity_not_closed",
        "general_newton_jacobian_assembly_not_closed",
    ]

    assert partitions_payload["status"] == "ready"
    assert partitions_payload["contract_pass"] is True
    assert partitions_payload["g1_closure_claim"] is False
    assert partitions_payload["nonlinear_newton_closure_claim"] is False
    assert partitions_payload["residual_formula"] == "F_internal_minus_F_external"
    assert partitions_payload["target_load_factor"] == 1.0
    assert len(partitions) == 4

    final_displacements = [row["final_displacement_m"] for row in partitions]
    assert max(final_displacements) - min(final_displacements) <= 1.0e-10

    for partition in partitions:
        assert partition["partition_contract_pass"] is True
        assert partition["final_load_factor"] == 1.0
        assert partition["regularization_used"] is False
        assert partition["fallback_used"] is False
        assert partition["partition_step_count"] == len(partition["steps"])

        for step_index, step in enumerate(partition["steps"], start=1):
            assert step["step_index"] == step_index
            assert step["partition_step_count"] == partition["partition_step_count"]
            assert step["status"] == "ready"
            assert step["contract_pass"] is True
            assert step["residual_gate_passed"] is True
            assert step["increment_gate_passed"] is True
            assert step["displacement_gate_passed"] is True
            assert step["regularization_used"] is False
            assert step["fallback_used"] is False
            assert step["residual_formula"] == "F_internal_minus_F_external"
            assert step["iteration_count"] >= 1
            assert step["displacement_abs_error_m"] <= 1.0e-10
            if step_index == 1:
                assert step["initial_displacement_m"] == 0.0
            else:
                assert step["initial_displacement_m"] == partition["steps"][step_index - 2][
                    "final_displacement_m"
                ]

    eight_step_partition = next(row for row in partitions if row["partition_step_count"] == 8)
    assert eight_step_partition["total_iteration_count"] > partitions[0]["total_iteration_count"]


def test_phase2_nonlinear_load_step_check_detects_stale_outputs(tmp_path: Path) -> None:
    ok, message = module.check_nonlinear_load_step_artifacts(
        repo_root=REPO_ROOT,
        partitions_out=tmp_path / "missing_partitions.json",
        summary_out=tmp_path / "missing_summary.json",
    )

    assert ok is False
    assert message.startswith("phase2_nonlinear_load_step_missing:")


def test_phase2_nonlinear_load_step_partition_load_factors_are_deterministic() -> None:
    base_problem = module.ScalarNonlinearAxialReference()
    config = module.NewtonRaphsonConfig(max_iterations=25)

    partition = module.run_load_step_partition(
        base_problem,
        partition_step_count=4,
        config=config,
    )

    assert [step["load_factor"] for step in partition["steps"]] == [0.25, 0.5, 0.75, 1.0]
