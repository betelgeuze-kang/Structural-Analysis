from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
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

from structural_analysis.engine_v2.buffers import (  # noqa: E402
    pack_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (  # noqa: E402
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.operators.sparse_linear_static import (  # noqa: E402
    solve_sparse_execution_plan_v2,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (  # noqa: E402
    CPU_FGMRES_REFERENCE_RESULT_V1_SCHEMA_VERSION,
    CpuFgmresReferenceError,
    _array_descriptor,
    _csr_matvec,
    _fgmres_core,
    _linf,
    _result_payload,
    _stable_l2,
    compile_fgmres_policy_v1,
    solve_cpu_fgmres_reference_v1,
    validate_cpu_fgmres_reference_result_v1,
)
from structural_analysis.model_ir import parse_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
SCHEMA = (
    REPO_ROOT
    / "src/structural_analysis/schemas/cpu_fgmres_reference_result_v1.schema.json"
)


def _payload() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _plan(load_pattern_id: str = "LC_AXIAL", payload: dict | None = None):
    model = parse_model_ir_v2(_payload() if payload is None else payload)
    buffers = pack_solver_model_buffers(model, load_pattern_id=load_pattern_id)
    return compile_execution_plan_v2(buffers)


def _strict_policy(**updates):
    values = {
        "restart_dimension": 16,
        "max_iterations": 64,
        "absolute_tolerance": 0.0,
        "relative_tolerance": 1.0e-12,
    }
    values.update(updates)
    return compile_fgmres_policy_v1(**values)


@pytest.mark.parametrize(
    "load_pattern_id",
    ("LC_AXIAL", "LC_WEAK", "LC_STRONG", "LC_TORSION"),
)
def test_cpu_fgmres_matches_sparse_direct_and_replays_true_residual(
    load_pattern_id: str,
) -> None:
    plan = _plan(load_pattern_id)
    direct = solve_sparse_execution_plan_v2(plan)
    policy = _strict_policy()

    result = solve_cpu_fgmres_reference_v1(plan, policy)

    assert result.schema_version == CPU_FGMRES_REFERENCE_RESULT_V1_SCHEMA_VERSION
    assert result.status == "converged"
    assert result.solver_tolerance_passed is True
    assert result.authoritative_plan_tolerance_passed is True
    free = plan.array("free_dofs")
    assert result.iteration_count <= min(free.size, policy.max_iterations)
    assert result.preconditioner_apply_count == result.iteration_count
    assert np.allclose(
        result.reduced_solution,
        direct.displacements_si.reshape(-1)[free],
        rtol=1.0e-10,
        atol=1.0e-12,
    )
    row_ptr = plan.array("reduced_csr_row_ptr")
    columns = plan.array("reduced_csr_column_indices")
    values = plan.array("reduced_stiffness_csr_values")
    replay = np.zeros(free.size, dtype="<f8")
    for row in range(free.size):
        begin, end = int(row_ptr[row]), int(row_ptr[row + 1])
        replay[row] = np.dot(
            values[begin:end], result.reduced_solution[columns[begin:end]]
        )
    rhs = plan.array("global_load")[free]
    assert np.allclose(result.true_residual, rhs - replay, rtol=0.0, atol=1.0e-12)


def test_zero_rhs_and_zero_initial_state_converge_at_iteration_zero() -> None:
    payload = _payload()
    axial = next(row for row in payload["load_patterns"] if row["id"] == "LC_AXIAL")
    axial["nodal_loads"][0]["node_id"] = "N1"
    plan = _plan(payload=payload)

    result = solve_cpu_fgmres_reference_v1(plan, _strict_policy())

    assert result.status == "converged"
    assert result.termination_code == "converged_initial_true_residual"
    assert result.iteration_count == 0
    assert result.restart_count == 0
    assert result.preconditioner_apply_count == 0
    assert result.operator_apply_count == 1
    assert np.array_equal(
        result.reduced_solution, np.zeros(plan.array("free_dofs").size, dtype="<f8")
    )
    assert np.array_equal(
        result.true_residual, np.zeros(plan.array("free_dofs").size, dtype="<f8")
    )
    assert not np.signbit(result.true_residual).any()


def test_nonzero_initial_state_uses_actual_b_minus_ax0_and_converges() -> None:
    plan = _plan("LC_WEAK")
    initial = np.zeros(plan.dof_count, dtype="<f8")
    free = plan.array("free_dofs")
    initial[free] = np.linspace(
        -2.5e-5, 3.5e-5, free.size, dtype="<f8"
    )
    zero_start = solve_cpu_fgmres_reference_v1(plan, _strict_policy())

    result = solve_cpu_fgmres_reference_v1(
        plan,
        _strict_policy(),
        initial_full_state=initial,
    )

    assert result.status == "converged"
    assert result.initial_reduced_state_hash != zero_start.initial_reduced_state_hash
    assert np.allclose(
        result.reduced_solution,
        zero_start.reduced_solution,
        rtol=1.0e-10,
        atol=1.0e-12,
    )
    assert result.initial_residual_l2 > 0.0


def test_direct_solution_initial_state_is_decided_by_replayed_residual() -> None:
    plan = _plan("LC_TORSION")
    direct = solve_sparse_execution_plan_v2(plan)
    initial = immutable_array(direct.displacements_si.reshape(-1), dtype="<f8")

    result = solve_cpu_fgmres_reference_v1(
        plan,
        _strict_policy(relative_tolerance=1.0e-10),
        initial_full_state=initial,
    )

    assert result.status == "converged"
    assert result.termination_code == "converged_initial_true_residual"
    assert result.iteration_count == 0
    assert result.operator_apply_count == 1


def test_max_iterations_zero_performs_only_initial_true_residual_replay() -> None:
    plan = _plan()
    policy = _strict_policy(max_iterations=0)

    result = solve_cpu_fgmres_reference_v1(plan, policy)

    assert result.status == "max_iterations"
    assert result.termination_code == "max_iterations_exhausted"
    assert result.iteration_count == 0
    assert result.restart_count == 0
    assert result.operator_apply_count == 1
    assert result.preconditioner_apply_count == 0


def test_tiny_rhs_has_no_hidden_unit_relative_tolerance_floor() -> None:
    rhs = np.array([1.0e-20], dtype="<f8")
    outcome = _fgmres_core(
        matvec=lambda vector: vector.copy(),
        rhs=rhs,
        initial_solution=np.zeros(1, dtype="<f8"),
        inverse_diagonal=np.ones(1, dtype="<f8"),
        policy=_strict_policy(
            restart_dimension=1,
            max_iterations=1,
            relative_tolerance=1.0e-8,
        ),
        authoritative_tolerance=1.0e-30,
    )

    assert outcome.status == "converged"
    assert outcome.iteration_count == 1
    assert outcome.initial_residual_l2 == 1.0e-20
    assert outcome.tolerance_l2 == 1.0e-28


def test_scale_relative_backsolve_accepts_tiny_nonsingular_operator() -> None:
    scale = 1.0e-20
    outcome = _fgmres_core(
        matvec=lambda vector: scale * vector,
        rhs=np.array([scale], dtype="<f8"),
        initial_solution=np.zeros(1, dtype="<f8"),
        inverse_diagonal=np.ones(1, dtype="<f8"),
        policy=_strict_policy(
            restart_dimension=1,
            max_iterations=1,
            absolute_tolerance=1.0e-40,
            relative_tolerance=0.0,
        ),
        authoritative_tolerance=1.0e-30,
    )

    assert outcome.status == "converged"
    assert outcome.termination_code == "converged_happy_breakdown"
    assert np.array_equal(outcome.solution, np.ones(1, dtype="<f8"))


def test_happy_and_unhappy_arnoldi_breakdown_are_distinguished() -> None:
    policy = _strict_policy(
        restart_dimension=1,
        max_iterations=1,
        absolute_tolerance=1.0e-30,
        relative_tolerance=0.0,
    )
    happy = _fgmres_core(
        matvec=lambda vector: vector.copy(),
        rhs=np.array([1.0], dtype="<f8"),
        initial_solution=np.zeros(1, dtype="<f8"),
        inverse_diagonal=np.ones(1, dtype="<f8"),
        policy=policy,
        authoritative_tolerance=0.0,
    )
    unhappy = _fgmres_core(
        matvec=lambda vector: np.zeros_like(vector),
        rhs=np.array([1.0], dtype="<f8"),
        initial_solution=np.zeros(1, dtype="<f8"),
        inverse_diagonal=np.ones(1, dtype="<f8"),
        policy=policy,
        authoritative_tolerance=0.0,
    )

    assert happy.status == "converged"
    assert happy.termination_code == "converged_happy_breakdown"
    assert unhappy.status == "arnoldi_breakdown"
    assert unhappy.termination_code == "arnoldi_triangular_factor_breakdown"
    assert unhappy.iteration_count == 1


def test_global_iteration_cap_crosses_restart_boundaries_exactly() -> None:
    diagonal = np.arange(1.0, 7.0, dtype="<f8")
    policy = _strict_policy(
        restart_dimension=2,
        max_iterations=5,
        absolute_tolerance=1.0e-300,
        relative_tolerance=0.0,
    )

    outcome = _fgmres_core(
        matvec=lambda vector: diagonal * vector,
        rhs=np.ones(6, dtype="<f8"),
        initial_solution=np.zeros(6, dtype="<f8"),
        inverse_diagonal=np.ones(6, dtype="<f8"),
        policy=policy,
        authoritative_tolerance=0.0,
    )

    assert outcome.status == "max_iterations"
    assert outcome.iteration_count == 5
    assert outcome.restart_count == 3
    assert [row.arnoldi_step_count for row in outcome.history] == [2, 2, 1]
    assert [(row.start_iteration, row.end_iteration) for row in outcome.history] == [
        (0, 2),
        (2, 4),
        (4, 5),
    ]


def test_final_candidate_true_residual_is_not_replayed_twice() -> None:
    diagonal = np.array([1.0, 2.0], dtype="<f8")
    outcome = _fgmres_core(
        matvec=lambda vector: diagonal * vector,
        rhs=np.ones(2, dtype="<f8"),
        initial_solution=np.zeros(2, dtype="<f8"),
        inverse_diagonal=np.ones(2, dtype="<f8"),
        policy=_strict_policy(
            restart_dimension=1,
            max_iterations=1,
            relative_tolerance=1.0,
        ),
        authoritative_tolerance=0.0,
    )

    assert outcome.status == "max_iterations"
    assert outcome.operator_apply_count == 3


def test_result_schema_is_strict_and_claims_are_non_promoting() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    result = solve_cpu_fgmres_reference_v1(_plan(), _strict_policy())

    assert not list(validator.iter_errors(result.to_dict()))
    extra = deepcopy(result.to_dict())
    extra["untrusted"] = True
    assert list(validator.iter_errors(extra))
    promoted = deepcopy(result.to_dict())
    promoted["claims"]["commercial_ready"] = True
    assert list(validator.iter_errors(promoted))
    fallback = deepcopy(result.to_dict())
    fallback["claims"]["fallback_used"] = True
    assert list(validator.iter_errors(fallback))


def test_cpu_fgmres_public_api_exports_canonical_objects() -> None:
    import structural_analysis.engine_v2 as engine_v2
    import structural_analysis.engine_v2.solvers as solvers

    assert engine_v2.FgmresPolicyV1 is solvers.FgmresPolicyV1
    assert (
        engine_v2.CpuFgmresReferenceResultV1
        is solvers.CpuFgmresReferenceResultV1
    )
    assert engine_v2.compile_fgmres_policy_v1 is solvers.compile_fgmres_policy_v1
    assert (
        engine_v2.solve_cpu_fgmres_reference_v1
        is solvers.solve_cpu_fgmres_reference_v1
    )


def test_fully_rehashed_history_forgery_is_rejected_by_replay() -> None:
    plan = _plan("LC_STRONG")
    policy = _strict_policy()
    result = solve_cpu_fgmres_reference_v1(plan, policy)
    rows = list(result.history)
    rows[-1] = replace(
        rows[-1],
        estimated_residual_l2=rows[-1].estimated_residual_l2 + 1.0e-30,
    )
    forged = replace(result, history=tuple(rows))
    forged = replace(
        forged,
        result_hash=canonical_hash(_result_payload(forged, include_hash=False)),
    )

    with pytest.raises(CpuFgmresReferenceError) as error:
        validate_cpu_fgmres_reference_result_v1(
            forged,
            expected_plan=plan,
            expected_policy=policy,
        )
    assert error.value.code == "cpu_fgmres_replay_mismatch"


def test_strong_validator_rejects_rehashed_metric_and_count_forgery() -> None:
    plan = _plan()
    policy = _strict_policy()
    result = solve_cpu_fgmres_reference_v1(plan, policy)

    metric_forgery = replace(result, initial_residual_l2=0.0)
    metric_forgery = replace(
        metric_forgery,
        result_hash=canonical_hash(
            _result_payload(metric_forgery, include_hash=False)
        ),
    )
    with pytest.raises(CpuFgmresReferenceError) as metric_error:
        validate_cpu_fgmres_reference_result_v1(
            metric_forgery,
            expected_plan=plan,
            expected_policy=policy,
        )
    assert metric_error.value.code == "cpu_fgmres_initial_metric_mismatch"

    count_forgery = replace(
        result,
        iteration_count=result.iteration_count + 1,
        preconditioner_apply_count=result.preconditioner_apply_count + 1,
    )
    count_forgery = replace(
        count_forgery,
        result_hash=canonical_hash(
            _result_payload(count_forgery, include_hash=False)
        ),
    )
    with pytest.raises(CpuFgmresReferenceError) as count_error:
        validate_cpu_fgmres_reference_result_v1(
            count_forgery,
            expected_plan=plan,
            expected_policy=policy,
        )
    assert count_error.value.code == "cpu_fgmres_history_count_mismatch"


def test_iteration_zero_state_forgery_is_rejected_before_replay() -> None:
    plan = _plan()
    policy = _strict_policy(max_iterations=0)
    result = solve_cpu_fgmres_reference_v1(plan, policy)
    solution = np.asarray(result.reduced_solution).copy()
    solution[0] += 1.0e-8
    solution = immutable_array(solution, dtype="<f8")
    residual = plan.array("global_load")[plan.array("free_dofs")] - _csr_matvec(
        plan.array("reduced_csr_row_ptr"),
        plan.array("reduced_csr_column_indices"),
        plan.array("reduced_stiffness_csr_values"),
        solution,
    )
    residual[residual == 0.0] = 0.0
    residual = immutable_array(residual, dtype="<f8")
    final_l2 = _stable_l2(residual)
    final_linf = _linf(residual)
    scaled = final_linf / max(
        1.0,
        _linf(plan.array("global_load")[plan.array("free_dofs")]),
    )
    forged = replace(
        result,
        reduced_solution=solution,
        true_residual=residual,
        descriptors=(
            _array_descriptor("reduced_solution", solution),
            _array_descriptor("true_residual", residual),
        ),
        final_residual_l2=final_l2,
        final_residual_linf=final_linf,
        scaled_true_residual=scaled,
        solver_tolerance_passed=final_l2 <= result.solver_tolerance_l2,
        authoritative_plan_tolerance_passed=scaled <= plan.residual_tolerance,
    )
    forged = replace(
        forged,
        result_hash=canonical_hash(_result_payload(forged, include_hash=False)),
    )

    with pytest.raises(CpuFgmresReferenceError) as error:
        validate_cpu_fgmres_reference_result_v1(
            forged,
            expected_plan=plan,
            expected_policy=policy,
        )
    assert error.value.code == "cpu_fgmres_zero_iteration_state_invalid"


@pytest.mark.parametrize(
    ("status", "termination_code", "expected_code"),
    (
        ("diverged", "true_residual_diverged", "cpu_fgmres_divergence_terminal_invalid"),
        ("stagnated", "true_residual_stagnated", "cpu_fgmres_replay_mismatch"),
    ),
)
def test_rehashed_terminal_status_forgery_is_rejected(
    status: str,
    termination_code: str,
    expected_code: str,
) -> None:
    plan = _plan("LC_WEAK")
    policy = _strict_policy(restart_dimension=1, max_iterations=2)
    result = solve_cpu_fgmres_reference_v1(plan, policy)
    assert result.status == "max_iterations"
    forged = replace(result, status=status, termination_code=termination_code)
    forged = replace(
        forged,
        result_hash=canonical_hash(_result_payload(forged, include_hash=False)),
    )

    with pytest.raises(CpuFgmresReferenceError) as error:
        validate_cpu_fgmres_reference_result_v1(
            forged,
            expected_plan=plan,
            expected_policy=policy,
        )
    assert error.value.code == expected_code


def test_result_rejects_mutable_backing_negative_zero_and_list_containers() -> None:
    plan = _plan()
    policy = _strict_policy()
    result = solve_cpu_fgmres_reference_v1(plan, policy)

    owned = np.asarray(result.reduced_solution).copy()
    owned.setflags(write=False)
    with pytest.raises(CpuFgmresReferenceError) as backing_error:
        validate_cpu_fgmres_reference_result_v1(
            replace(result, reduced_solution=owned),
            expected_plan=plan,
            expected_policy=policy,
        )
    assert backing_error.value.code == "cpu_fgmres_array_invalid"

    negative_zero = np.asarray(result.true_residual).copy()
    zero_slots = np.flatnonzero(negative_zero == 0.0)
    assert zero_slots.size > 0
    negative_zero[int(zero_slots[0])] = -0.0
    with pytest.raises(CpuFgmresReferenceError) as zero_error:
        validate_cpu_fgmres_reference_result_v1(
            replace(
                result,
                true_residual=immutable_array(negative_zero, dtype="<f8"),
            ),
            expected_plan=plan,
            expected_policy=policy,
        )
    assert zero_error.value.code == "cpu_fgmres_array_invalid"

    with pytest.raises(CpuFgmresReferenceError) as container_error:
        validate_cpu_fgmres_reference_result_v1(
            replace(result, history=list(result.history)),
            expected_plan=plan,
            expected_policy=policy,
        )
    assert container_error.value.code == "cpu_fgmres_result_container_invalid"


def test_free_negative_zero_initial_state_is_canonicalized() -> None:
    payload = _payload()
    axial = next(row for row in payload["load_patterns"] if row["id"] == "LC_AXIAL")
    axial["nodal_loads"][0]["node_id"] = "N1"
    plan = _plan(payload=payload)
    initial = np.zeros(plan.dof_count, dtype="<f8")
    initial[int(plan.array("free_dofs")[0])] = -0.0

    result = solve_cpu_fgmres_reference_v1(
        plan,
        _strict_policy(),
        initial_full_state=initial,
    )

    assert result.status == "converged"
    assert result.iteration_count == 0
    assert not np.signbit(result.reduced_solution).any()


def test_policy_and_initial_state_validation_are_fail_closed() -> None:
    with pytest.raises(CpuFgmresReferenceError) as tolerance_error:
        compile_fgmres_policy_v1(absolute_tolerance=0.0, relative_tolerance=0.0)
    assert tolerance_error.value.code == "fgmres_tolerance_empty"

    for updates, code in (
        ({"relative_tolerance": float("nan")}, "fgmres_relative_tolerance_invalid"),
        ({"absolute_tolerance": float("inf")}, "fgmres_absolute_tolerance_invalid"),
        ({"max_iterations": object()}, "fgmres_max_iterations_invalid"),
    ):
        with pytest.raises(CpuFgmresReferenceError) as policy_error:
            compile_fgmres_policy_v1(**updates)
        assert policy_error.value.code == code

    plan = _plan()
    invalid = np.zeros(plan.dof_count, dtype="<f8")
    invalid[plan.constrained_dofs[0]] = -0.0
    with pytest.raises(CpuFgmresReferenceError) as state_error:
        solve_cpu_fgmres_reference_v1(
            plan,
            _strict_policy(),
            initial_full_state=invalid,
        )
    assert state_error.value.code == "cpu_fgmres_constrained_state_nonzero"


def test_operator_arithmetic_failure_has_stable_fail_closed_error() -> None:
    with pytest.raises(CpuFgmresReferenceError) as error:
        _fgmres_core(
            matvec=lambda vector: np.full_like(vector, np.nan),
            rhs=np.ones(2, dtype="<f8"),
            initial_solution=np.zeros(2, dtype="<f8"),
            inverse_diagonal=np.ones(2, dtype="<f8"),
            policy=_strict_policy(),
            authoritative_tolerance=1.0e-10,
        )
    assert error.value.code == "cpu_fgmres_initial_operator_application_failed"


def test_validator_converts_residual_replay_overflow_to_stable_error() -> None:
    plan = _plan()
    policy = _strict_policy()
    result = solve_cpu_fgmres_reference_v1(plan, policy)
    huge = immutable_array(
        np.full(result.reduced_solution.shape, 1.0e308, dtype="<f8"),
        dtype="<f8",
    )
    forged = replace(
        result,
        reduced_solution=huge,
        descriptors=(
            _array_descriptor("reduced_solution", huge),
            result.descriptors[1],
        ),
    )

    with pytest.raises(CpuFgmresReferenceError) as error:
        validate_cpu_fgmres_reference_result_v1(
            forged,
            expected_plan=plan,
            expected_policy=policy,
        )
    assert error.value.code == "cpu_fgmres_residual_replay_failed"


def test_converged_candidate_update_norm_overflow_is_numerical_failure() -> None:
    matrix = np.array(
        [
            [3.92837101e-301, 3.92837101e-301],
            [3.92837101e-301, 2.39283710e-300],
        ],
        dtype="<f8",
    )
    initial = np.array([-9.0e307, 0.0], dtype="<f8")
    exact = np.array([9.0e307, 0.0], dtype="<f8")

    outcome = _fgmres_core(
        matvec=lambda vector: matrix @ vector,
        rhs=matrix @ exact,
        initial_solution=initial,
        inverse_diagonal=1.0 / np.diag(matrix),
        policy=_strict_policy(restart_dimension=2, max_iterations=2),
        authoritative_tolerance=1.0e-10,
    )

    assert outcome.status == "numerical_failure"
    assert outcome.termination_code == "restart_state_nonfinite"
    assert all(
        np.isfinite(value)
        for value in (
            outcome.initial_residual_l2,
            outcome.tolerance_l2,
            *outcome.solution,
            *outcome.residual,
        )
    )
