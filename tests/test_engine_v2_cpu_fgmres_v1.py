from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
    canonical_hash,
)
from structural_analysis.engine_v2.contracts.equation_scaling import (  # noqa: E402
    bind_equation_scaling_to_execution_plan,
    create_equation_scaling,
)
from structural_analysis.engine_v2.contracts.execution_plan import (  # noqa: E402
    create_execution_plan,
)
from structural_analysis.engine_v2.contracts.execution_plan_reduced_csr import (  # noqa: E402
    create_execution_plan_reduced_csr,
)
from structural_analysis.engine_v2.cpu_fgmres import (  # noqa: E402
    CPU_FGMRES_RECURRENCE_PROFILE,
    CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER,
    CPU_FGMRES_SCHEMA_VERSION,
    CPU_FGMRES_SOLUTION_FILENAME,
    CPUFGMRESError,
    build_cpu_fgmres_left_scaled_jacobi_inverse_diagonal,
    replay_cpu_fgmres_run,
    run_cpu_fgmres,
    validate_cpu_fgmres_manifest,
    validate_cpu_fgmres_solution_bytes,
    write_cpu_fgmres_solution_artifact,
)

SCHEMA = REPO_ROOT / "src/structural_analysis/schemas/cpu_fgmres_run_v1.schema.json"


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _problem(
    *,
    zero_operator: bool = False,
    free_matrix: np.ndarray | None = None,
) -> dict[str, object]:
    dof_count = 12
    free = np.arange(6, dof_count, dtype="<i4")
    constrained = np.arange(6, dtype="<i4")
    global_to_free = np.full(dof_count, -1, dtype="<i4")
    global_to_free[free] = np.arange(free.size, dtype="<i4")
    base = create_execution_plan(
        model_ir_content_hash=_hash("1"),
        solver_buffer_schema_version="solver-model-buffers.v1",
        solver_numeric_buffer_hash=_hash("2"),
        solver_entity_mapping_hash=_hash("3"),
        solver_artifact_hash=_hash("4"),
        load_pattern_id="LC1",
        operator_id="linear-static-operator",
        operator_version="linear-static-operator.v1",
        operator_hash=_hash("5"),
        node_ids=("N1", "N2"),
        element_ids=("E1",),
        node_dof_indices=np.arange(dof_count, dtype="<i4").reshape(2, 6),
        global_to_free=global_to_free,
        element_global_dofs=np.arange(dof_count, dtype="<i4").reshape(1, 12),
        constrained_dofs=constrained,
        free_dofs=free,
        csr_row_ptr=np.arange(0, dof_count * dof_count + 1, dof_count, dtype="<i8"),
        csr_column_indices=np.tile(np.arange(dof_count, dtype="<i4"), dof_count),
    )
    coordinates = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype="<f8")
    right_hand_side = np.zeros(dof_count, dtype="<f8")
    right_hand_side[free] = np.asarray([2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
    scaling = create_equation_scaling(
        execution_plan=base,
        node_coordinates_m=coordinates,
        reference_equation_load_si=right_hand_side,
    )
    bound = bind_equation_scaling_to_execution_plan(
        base,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=right_hand_side,
    )
    values = np.zeros(dof_count * dof_count, dtype="<f8")
    if free_matrix is not None:
        if free_matrix.shape != (free.size, free.size):
            raise AssertionError("test fixture free matrix shape is invalid")
        for free_row, global_row in enumerate(free):
            for free_column, global_column in enumerate(free):
                values[global_row * dof_count + global_column] = free_matrix[
                    free_row, free_column
                ]
    elif not zero_operator:
        for equation in range(dof_count):
            values[equation * dof_count + equation] = float(equation + 1)
    reduced = create_execution_plan_reduced_csr(
        bound,
        operator_numeric_values_hash=array_data_hash(values),
    )
    return {
        "base": base,
        "plan": bound,
        "scaling": scaling,
        "reduced": reduced,
        "coordinates": coordinates,
        "right_hand_side": right_hand_side,
        "values": values,
    }


def _run(problem: dict[str, object], **changes):
    arguments = {
        "execution_plan": problem["plan"],
        "scaling": problem["scaling"],
        "reduced_csr": problem["reduced"],
        "node_coordinates_m": problem["coordinates"],
        "reference_equation_load_si": problem["right_hand_side"],
        "global_csr_values_si": problem["values"],
        "right_hand_side_si": problem["right_hand_side"],
        "solution_artifact_uri": "artifact://run-1/solution_free.f64le",
        "max_iterations": 12,
        "restart_length": 6,
        "relative_tolerance_scaled_l2": 1.0e-12,
        "absolute_tolerance_scaled_l2": 1.0e-14,
    }
    arguments.update(changes)
    return run_cpu_fgmres(**arguments)


def _rehash(payload: dict, field: str) -> None:
    without_hash = {key: value for key, value in payload.items() if key != field}
    payload[field] = canonical_hash(without_hash)


def test_cpu_fgmres_converges_deterministically_and_replays_exactly() -> None:
    problem = _problem()
    first = _run(problem)
    second = _run(problem)
    payload = first.to_manifest()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    assert first.schema_version == CPU_FGMRES_SCHEMA_VERSION
    assert payload["solver"]["recurrence_profile"] == CPU_FGMRES_RECURRENCE_PROFILE
    assert first.run_hash == second.run_hash
    assert first.terminal_reason == "converged_scaled_residual"
    assert first.converged is True
    assert first.iteration_count <= 6
    np.testing.assert_allclose(
        first.solution_free,
        np.asarray([2 / 7, 3 / 8, 4 / 9, 5 / 10, 6 / 11, 7 / 12]),
        rtol=1.0e-12,
        atol=1.0e-14,
    )
    assert not first.solution_free.flags.writeable
    assert payload["claim_boundary"]["result_ir_authority"] is False
    assert payload["claim_boundary"]["iteration_vectors_inline"] is False
    assert all("values" not in descriptor for descriptor in payload["inputs"].values())
    assert "values" not in payload["solution_artifact"]
    assert len(payload["observations"]) == first.iteration_count + 1
    replay_cpu_fgmres_run(
        first,
        node_coordinates_m=problem["coordinates"],
        reference_equation_load_si=problem["right_hand_side"],
    )


def test_restart_history_and_max_iterations_are_explicit_terminal_state() -> None:
    run = _run(
        _problem(),
        max_iterations=2,
        restart_length=1,
        relative_tolerance_scaled_l2=1.0e-30,
        absolute_tolerance_scaled_l2=1.0e-30,
    )

    assert run.converged is False
    assert run.terminal_reason == "max_iterations"
    assert run.iteration_count == 2
    assert [row.disposition for row in run.restart_history] == [
        "restarted",
        "max_iterations",
    ]
    assert [
        (row.start_iteration, row.end_iteration) for row in run.restart_history
    ] == [
        (0, 1),
        (1, 2),
    ]
    assert run.observations[-1].scaled_l2 > run.convergence_threshold_scaled_l2


def test_coupled_spd_recurrence_matches_direct_reference_without_dense_solver_use() -> (
    None
):
    free_matrix = np.diag(np.full(6, 4.0))
    free_matrix += np.diag(np.full(5, -1.0), 1)
    free_matrix += np.diag(np.full(5, -1.0), -1)
    problem = _problem(free_matrix=np.asarray(free_matrix, dtype="<f8"))
    run = _run(problem)
    expected = np.linalg.solve(
        free_matrix,
        np.asarray(problem["right_hand_side"])[6:],
    )

    assert run.terminal_reason == "converged_scaled_residual"
    np.testing.assert_allclose(run.solution_free, expected, rtol=1.0e-11, atol=1.0e-13)
    assert run.observations[-1].scaled_l2 <= run.convergence_threshold_scaled_l2


def test_zero_initial_residual_and_zero_operator_breakdown_are_distinct() -> None:
    zero_rhs_problem = _problem()
    zero_rhs = np.zeros(12, dtype="<f8")
    initial = _run(
        zero_rhs_problem,
        right_hand_side_si=zero_rhs,
    )
    assert initial.terminal_reason == "initial_residual_satisfied"
    assert initial.iteration_count == 0
    assert initial.matvec_count == 1

    singular = _run(_problem(zero_operator=True), max_iterations=3)
    assert singular.terminal_reason == "arnoldi_breakdown"
    assert singular.converged is False
    assert singular.iteration_count == 1
    assert (
        singular.observations[-1].scaled_l2 > singular.convergence_threshold_scaled_l2
    )


def test_fixed_diagonal_preconditioner_is_hashed_and_replayable() -> None:
    problem = _problem()
    preconditioner = np.asarray([1 / 7, 1 / 8, 1 / 9, 1 / 10, 1 / 11, 1 / 12])
    run = _run(
        problem,
        right_preconditioner_inverse_diagonal=preconditioner,
        restart_length=2,
    )

    assert run.converged is True
    assert run.iteration_count == 2
    assert run.preconditioner_profile == "fixed_positive_inverse_diagonal_right.v1"
    assert run.to_manifest()["inputs"]["right_preconditioner_inverse_diagonal"][
        "data_hash"
    ] == array_data_hash(np.asarray(preconditioner, dtype="<f8"))
    replay_cpu_fgmres_run(
        run,
        node_coordinates_m=problem["coordinates"],
        reference_equation_load_si=problem["right_hand_side"],
    )


def test_operator_derived_left_scaled_jacobi_is_exact_and_replayable() -> None:
    problem = _problem()
    derived = build_cpu_fgmres_left_scaled_jacobi_inverse_diagonal(
        execution_plan=problem["plan"],
        scaling=problem["scaling"],
        reduced_csr=problem["reduced"],
        global_csr_values_si=problem["values"],
    )
    free_dofs = problem["plan"].array("free_dofs")
    expected = (
        problem["scaling"].scale_divisors_si[free_dofs]
        / np.arange(7.0, 13.0, dtype="<f8")
    )

    np.testing.assert_array_equal(derived, expected)
    assert not derived.flags.writeable
    run = _run(
        problem,
        right_preconditioner_profile=CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER,
        restart_length=2,
    )
    assert run.preconditioner_profile == CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER
    np.testing.assert_array_equal(
        run._input_arrays["right_preconditioner_inverse_diagonal"],
        derived,
    )
    replay_cpu_fgmres_run(
        run,
        node_coordinates_m=problem["coordinates"],
        reference_equation_load_si=problem["right_hand_side"],
    )

    stale = np.asarray(derived).copy()
    stale[0] = np.nextafter(stale[0], np.inf)
    with pytest.raises(CPUFGMRESError) as binding_error:
        _run(
            problem,
            right_preconditioner_profile=(
                CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER
            ),
            right_preconditioner_inverse_diagonal=stale,
        )
    assert binding_error.value.code == "fgmres_scaled_jacobi_binding_mismatch"

    with pytest.raises(CPUFGMRESError) as diagonal_error:
        _run(
            _problem(zero_operator=True),
            right_preconditioner_profile=(
                CPU_FGMRES_SCALED_JACOBI_PRECONDITIONER
            ),
        )
    assert diagonal_error.value.code == "fgmres_scaled_jacobi_diagonal_invalid"


def test_solver_fails_closed_on_source_hash_replay_and_parameter_mismatch() -> None:
    problem = _problem()
    stale_values = np.asarray(problem["values"]).copy()
    stale_values[0] = 99.0
    with pytest.raises(CPUFGMRESError) as values_error:
        _run(problem, global_csr_values_si=stale_values)
    assert values_error.value.code == "fgmres_operator_numeric_values_hash_mismatch"

    stale_coordinates = np.asarray(problem["coordinates"]).copy()
    stale_coordinates[1, 0] = 3.0
    with pytest.raises(Exception) as replay_error:
        _run(problem, node_coordinates_m=stale_coordinates)
    assert getattr(replay_error.value, "code", None) == "source_commitment_mismatch"

    with pytest.raises(CPUFGMRESError) as restart_error:
        _run(problem, restart_length=7)
    assert restart_error.value.code == "fgmres_restart_length_invalid"

    with pytest.raises(CPUFGMRESError) as preconditioner_error:
        _run(
            problem,
            right_preconditioner_inverse_diagonal=np.asarray(
                [1.0, 1.0, 1.0, 0.0, 1.0, 1.0]
            ),
        )
    assert preconditioner_error.value.code == "fgmres_preconditioner_invalid"


def test_solution_binary_writer_is_exact_fail_closed_and_non_overwriting(
    tmp_path: Path,
) -> None:
    run = _run(_problem())
    target = tmp_path / CPU_FGMRES_SOLUTION_FILENAME
    written = write_cpu_fgmres_solution_artifact(run, target)
    raw = written.read_bytes()

    assert raw == memoryview(run.solution_free).cast("B").tobytes()
    validate_cpu_fgmres_solution_bytes(run, raw)
    tampered = bytearray(raw)
    tampered[-1] ^= 1
    with pytest.raises(CPUFGMRESError) as tamper_error:
        validate_cpu_fgmres_solution_bytes(run, tampered)
    assert tamper_error.value.code == "fgmres_solution_hash_mismatch"

    with pytest.raises(CPUFGMRESError) as overwrite_error:
        write_cpu_fgmres_solution_artifact(run, target)
    assert overwrite_error.value.code == "fgmres_solution_target_exists"
    assert written.read_bytes() == raw


def test_manifest_rejects_stale_and_coherently_rehashed_governing_dof() -> None:
    payload = deepcopy(_run(_problem()).to_manifest())
    payload["solution_artifact"]["artifact_uri"] = (
        "artifact://another/solution_free.f64le"
    )
    with pytest.raises(CPUFGMRESError) as stale_error:
        validate_cpu_fgmres_manifest(payload)
    assert stale_error.value.code == "fgmres_run_hash_mismatch"

    forged = deepcopy(_run(_problem()).to_manifest())
    observation = forged["observations"][0]
    old_hash = observation["observation_hash"]
    observation["governing"]["dof"] = "RX"
    _rehash(observation, "observation_hash")
    new_hash = observation["observation_hash"]
    for record in forged["restart_history"]:
        if record["start_observation_hash"] == old_hash:
            record["start_observation_hash"] = new_hash
        if record["end_observation_hash"] == old_hash:
            record["end_observation_hash"] = new_hash
        _rehash(record, "restart_hash")
    if forged["terminal"]["final_observation_hash"] == old_hash:
        forged["terminal"]["final_observation_hash"] = new_hash
    _rehash(forged, "run_hash")
    with pytest.raises(CPUFGMRESError) as semantic_error:
        validate_cpu_fgmres_manifest(forged)
    assert semantic_error.value.code == "fgmres_governing_dof_invalid"


def test_cpu_fgmres_public_api_exports_without_result_ir() -> None:
    import structural_analysis.engine_v2 as engine_v2

    assert engine_v2.CPU_FGMRES_SCHEMA_VERSION == CPU_FGMRES_SCHEMA_VERSION
    assert engine_v2.run_cpu_fgmres is run_cpu_fgmres
    assert not hasattr(engine_v2, "ResultIR")
