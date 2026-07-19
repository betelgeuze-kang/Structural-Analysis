from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from structural_analysis.engine_v2.contracts._canonical import array_data_hash
from structural_analysis.engine_v2.contracts.equation_scaling import (
    bind_equation_scaling_to_execution_plan,
    create_equation_scaling,
)
from structural_analysis.engine_v2.contracts.execution_plan import (
    create_execution_plan,
)
from structural_analysis.engine_v2.cpu_fgmres_tangent import (
    CPU_FGMRES_TANGENT_SOLVE_PROFILE,
    CPUFGMRESTangentSolveError,
    solve_cpu_fgmres_tangent_system,
    validate_cpu_fgmres_tangent_solve,
)


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _binding() -> dict[str, object]:
    dof_count = 12
    free = np.asarray([6, 7], dtype="<i4")
    constrained = np.asarray(
        [0, 1, 2, 3, 4, 5, 8, 9, 10, 11],
        dtype="<i4",
    )
    global_to_free = np.full(dof_count, -1, dtype="<i4")
    global_to_free[free] = np.arange(free.size, dtype="<i4")
    base = create_execution_plan(
        model_ir_content_hash=_hash("1"),
        solver_buffer_schema_version="solver-model-buffers.v1",
        solver_numeric_buffer_hash=_hash("2"),
        solver_entity_mapping_hash=_hash("3"),
        solver_artifact_hash=_hash("4"),
        load_pattern_id="ARC_LENGTH_TANGENT",
        operator_id="nonlinear-tangent",
        operator_version="nonlinear-tangent.v1",
        operator_hash=_hash("5"),
        node_ids=("N1", "N2"),
        element_ids=("E1",),
        node_dof_indices=np.arange(dof_count, dtype="<i4").reshape(2, 6),
        global_to_free=global_to_free,
        element_global_dofs=np.arange(dof_count, dtype="<i4").reshape(1, 12),
        constrained_dofs=constrained,
        free_dofs=free,
        csr_row_ptr=np.arange(
            0,
            dof_count * dof_count + 1,
            dof_count,
            dtype="<i8",
        ),
        csr_column_indices=np.tile(
            np.arange(dof_count, dtype="<i4"),
            dof_count,
        ),
    )
    coordinates = np.asarray(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        dtype="<f8",
    )
    reference_load = np.zeros(dof_count, dtype="<f8")
    reference_load[free] = np.asarray([1.0, 1.0], dtype="<f8")
    scaling = create_equation_scaling(
        execution_plan=base,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_load,
    )
    plan = bind_equation_scaling_to_execution_plan(
        base,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=reference_load,
    )
    return {
        "plan": plan,
        "scaling": scaling,
        "coordinates": coordinates,
        "reference_load": reference_load,
        "free": free,
    }


def _global_values(binding: dict[str, object], matrix: np.ndarray) -> np.ndarray:
    plan = binding["plan"]
    free = np.asarray(binding["free"])
    values = np.zeros(plan.array("csr_column_indices").size, dtype="<f8")
    dof_count = plan.dof_count
    for row, global_row in enumerate(free):
        for column, global_column in enumerate(free):
            values[int(global_row) * dof_count + int(global_column)] = matrix[
                row,
                column,
            ]
    return values


def _solve(matrix: np.ndarray, right_hand_side: np.ndarray):
    binding = _binding()
    return solve_cpu_fgmres_tangent_system(
        execution_plan=binding["plan"],
        scaling=binding["scaling"],
        node_coordinates_m=binding["coordinates"],
        reference_equation_load_si=binding["reference_load"],
        global_csr_values_si=_global_values(binding, matrix),
        right_hand_side_free=right_hand_side,
        solution_artifact_uri="artifact://tangent/solution_free.f64le",
        max_iterations=4,
        restart_length=2,
        relative_tolerance_scaled_l2=1.0e-13,
        absolute_tolerance_scaled_l2=1.0e-14,
        explicit_residual_tolerance=1.0e-12,
    )


@pytest.mark.parametrize(
    "matrix",
    [
        np.asarray([[500.0, -140.0], [-140.0, 400.0]], dtype="<f8"),
        np.asarray([[-350.0, -140.0], [-140.0, 400.0]], dtype="<f8"),
    ],
)
def test_cpu_fgmres_tangent_matches_direct_spd_and_indefinite_solves(
    matrix: np.ndarray,
) -> None:
    right_hand_side = np.asarray([-0.3, 0.2], dtype="<f8")
    solve = _solve(matrix, right_hand_side)

    assert solve.status == "ready"
    assert solve.contract_pass is True
    assert solve.profile == CPU_FGMRES_TANGENT_SOLVE_PROFILE
    assert solve.converged is True
    assert solve.iteration_count == 2
    assert solve.explicit_residual_inf_norm <= 1.0e-12
    assert solve.fallback_count == 0
    assert solve.regularization_count == 0
    np.testing.assert_allclose(
        solve.solution_free,
        np.linalg.solve(matrix, right_hand_side),
        rtol=1.0e-13,
        atol=1.0e-15,
    )
    np.testing.assert_allclose(
        solve.explicit_residual_free,
        matrix @ solve.solution_free - right_hand_side,
        rtol=0.0,
        atol=1.0e-16,
    )


def test_cpu_fgmres_tangent_is_deterministic_and_descriptor_only() -> None:
    matrix = np.asarray([[500.0, -140.0], [-140.0, 400.0]], dtype="<f8")
    right_hand_side = np.asarray([1.0, 0.0], dtype="<f8")
    first = _solve(matrix, right_hand_side)
    second = _solve(matrix, right_hand_side)
    manifest = first.to_manifest()

    assert first.solve_hash == second.solve_hash
    assert first.run_hash == second.run_hash
    assert np.array_equal(first.solution_free, second.solution_free)
    assert manifest == second.to_manifest()
    assert "values" not in manifest["solution_artifact"]
    assert manifest["solution_artifact"]["data_hash"] == array_data_hash(
        first.solution_free
    )
    assert manifest["claim_boundary"]["arc_length_integration"] is False
    assert manifest["claim_boundary"]["rocm_hip_parity"] is False
    assert manifest["claim_boundary"]["g1_closure"] is False


def test_cpu_fgmres_tangent_tamper_fails_closed() -> None:
    solve = _solve(
        np.asarray([[500.0, -140.0], [-140.0, 400.0]], dtype="<f8"),
        np.asarray([1.0, 0.0], dtype="<f8"),
    )

    with pytest.raises(CPUFGMRESTangentSolveError, match="solve_hash mismatch"):
        validate_cpu_fgmres_tangent_solve(
            replace(solve, solve_hash="sha256:" + "0" * 64)
        )


def test_cpu_fgmres_tangent_rejects_nonfinite_inputs() -> None:
    binding = _binding()
    matrix = np.asarray([[500.0, -140.0], [-140.0, 400.0]], dtype="<f8")
    values = _global_values(binding, matrix)
    values[0] = np.nan

    with pytest.raises(CPUFGMRESTangentSolveError, match="global_csr_values_si"):
        solve_cpu_fgmres_tangent_system(
            execution_plan=binding["plan"],
            scaling=binding["scaling"],
            node_coordinates_m=binding["coordinates"],
            reference_equation_load_si=binding["reference_load"],
            global_csr_values_si=values,
            right_hand_side_free=np.asarray([1.0, 0.0], dtype="<f8"),
            solution_artifact_uri="artifact://tangent/solution_free.f64le",
        )
