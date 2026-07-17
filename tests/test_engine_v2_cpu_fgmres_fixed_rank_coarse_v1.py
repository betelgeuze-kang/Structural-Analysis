from __future__ import annotations

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
    immutable_array,
)
from structural_analysis.engine_v2.contracts.execution_plan_v2 import (  # noqa: E402
    compile_execution_plan_v2,
)
from structural_analysis.engine_v2.operators.sparse_linear_static import (  # noqa: E402
    solve_sparse_execution_plan_v2,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres import (  # noqa: E402
    _csr_matvec,
    _fgmres_core,
    compile_fgmres_policy_v1,
    solve_cpu_fgmres_reference_v1,
)
from structural_analysis.engine_v2.solvers.cpu_fgmres_fixed_rank_coarse_v1 import (  # noqa: E402
    CPU_FGMRES_FIXED_RANK_COARSE_CAPABILITY_PROFILE_V1,
    CPU_FGMRES_FIXED_RANK_COARSE_RESULT_V1_SCHEMA_VERSION,
    CPU_FGMRES_FIXED_RANK_COARSE_SPACE_V1_SCHEMA_VERSION,
    MAX_CPU_FGMRES_COARSE_RANK_V1,
    CpuFgmresFixedRankCoarseError,
    apply_cpu_fgmres_fixed_rank_coarse_v1,
    build_cpu_fgmres_fixed_rank_coarse_space_v1,
    solve_cpu_fgmres_fixed_rank_coarse_v1,
    validate_cpu_fgmres_fixed_rank_coarse_result_v1,
    validate_cpu_fgmres_fixed_rank_coarse_space_v1,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
MODULE = (
    SRC_ROOT
    / "structural_analysis/engine_v2/solvers/cpu_fgmres_fixed_rank_coarse_v1.py"
)
SPACE_SCHEMA = (
    SRC_ROOT
    / "structural_analysis/schemas/cpu_fgmres_fixed_rank_coarse_space_v1.schema.json"
)
RESULT_SCHEMA = (
    SRC_ROOT
    / "structural_analysis/schemas/cpu_fgmres_fixed_rank_coarse_result_v1.schema.json"
)


def _plan(load_pattern_id: str = "LC_WEAK"):
    model = load_model_ir_v2(FIXTURE)
    buffers = pack_solver_model_buffers(model, load_pattern_id=load_pattern_id)
    return compile_execution_plan_v2(buffers)


def _direct_reduced(plan) -> np.ndarray:
    direct = solve_sparse_execution_plan_v2(plan)
    return immutable_array(
        direct.displacements_si.reshape(-1)[plan.array("free_dofs")],
        dtype="<f8",
    )


def _policy(**updates):
    values = {
        "restart_dimension": 4,
        "max_iterations": 16,
        "absolute_tolerance": 0.0,
        "relative_tolerance": 1.0e-10,
    }
    values.update(updates)
    return compile_fgmres_policy_v1(**values)


def _artifact(plan):
    return build_cpu_fgmres_fixed_rank_coarse_space_v1(
        plan,
        _direct_reduced(plan).reshape(-1, 1),
        rank_cap=1,
    )


def test_sparse_energy_scaled_space_replays_every_retained_array() -> None:
    plan = _plan()
    weak = _direct_reduced(plan)
    strong = _direct_reduced(_plan("LC_STRONG"))
    artifact = build_cpu_fgmres_fixed_rank_coarse_space_v1(
        plan,
        np.column_stack((weak, strong)),
        rank_cap=2,
    )

    assert (
        artifact.schema_version == CPU_FGMRES_FIXED_RANK_COARSE_SPACE_V1_SCHEMA_VERSION
    )
    assert (
        artifact.capability_profile
        == CPU_FGMRES_FIXED_RANK_COARSE_CAPABILITY_PROFILE_V1
    )
    assert artifact.execution_plan_hash == plan.plan_hash
    assert artifact.free_dof_count == plan.array("free_dofs").size
    assert artifact.reduced_nnz == plan.reduced_nnz
    assert artifact.retained_rank == 2
    np.testing.assert_allclose(
        artifact.scaled_basis_q.T @ artifact.scaled_basis_q,
        np.eye(2),
        rtol=0.0,
        atol=1.0e-14,
    )
    np.testing.assert_array_equal(
        artifact.physical_basis_z,
        artifact.inverse_sqrt_diagonal[:, None] * artifact.scaled_basis_q,
    )
    row_ptr = plan.array("reduced_csr_row_ptr")
    columns = plan.array("reduced_csr_column_indices")
    values = plan.array("reduced_stiffness_csr_values")
    for index in range(artifact.retained_rank):
        np.testing.assert_array_equal(
            artifact.operator_basis_az[:, index],
            _csr_matvec(
                row_ptr,
                columns,
                values,
                artifact.physical_basis_z[:, index],
            ),
        )
    np.testing.assert_allclose(
        artifact.coarse_cholesky_l @ artifact.coarse_cholesky_l.T,
        artifact.coarse_operator_e,
        rtol=1.0e-15,
        atol=1.0e-15,
    )
    validate_cpu_fgmres_fixed_rank_coarse_space_v1(
        artifact,
        expected_plan=plan,
    )
    for name in (
        "inverse_sqrt_diagonal",
        "candidate_vectors",
        "scaled_basis_q",
        "physical_basis_z",
        "operator_basis_az",
        "coarse_operator_e",
        "coarse_cholesky_l",
    ):
        array = artifact.array(name)
        assert array.dtype.str == "<f8"
        assert array.flags.c_contiguous
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.setflags(write=True)


def test_multiplicative_preconditioner_is_exact_on_each_coarse_mode() -> None:
    plan = _plan()
    weak = _direct_reduced(plan)
    strong = _direct_reduced(_plan("LC_STRONG"))
    artifact = build_cpu_fgmres_fixed_rank_coarse_space_v1(
        plan,
        np.column_stack((weak, strong)),
        rank_cap=2,
    )

    for index in range(artifact.retained_rank):
        mode = artifact.physical_basis_z[:, index]
        image = artifact.operator_basis_az[:, index]
        recovered = apply_cpu_fgmres_fixed_rank_coarse_v1(
            artifact,
            image,
            expected_plan=plan,
        )
        np.testing.assert_allclose(recovered, mode, rtol=2.0e-14, atol=1.0e-18)
        assert recovered.dtype.str == "<f8"
        assert not recovered.flags.writeable


def test_teacher_mode_is_consumed_by_actual_fgmres_right_preconditioner() -> None:
    plan = _plan()
    direct = _direct_reduced(plan)
    artifact = _artifact(plan)
    policy = _policy()

    jacobi = solve_cpu_fgmres_reference_v1(plan, policy)
    result = solve_cpu_fgmres_fixed_rank_coarse_v1(plan, policy, artifact)

    assert (
        result.schema_version == CPU_FGMRES_FIXED_RANK_COARSE_RESULT_V1_SCHEMA_VERSION
    )
    assert result.status == "converged"
    assert result.iteration_count == 1
    assert result.iteration_count < jacobi.iteration_count
    assert result.preconditioner_apply_count == 1
    assert result.complexity_receipt.total_coarse_rhs_dot_count == 1
    assert result.complexity_receipt.total_small_forward_solve_count == 1
    assert result.complexity_receipt.total_small_backward_solve_count == 1
    assert (
        result.complexity_receipt.additional_csr_apply_count_inside_preconditioner == 0
    )
    assert result.complexity_receipt.dense_projector_elements == 0
    np.testing.assert_allclose(
        result.reduced_solution,
        direct,
        rtol=1.0e-12,
        atol=1.0e-18,
    )
    validate_cpu_fgmres_fixed_rank_coarse_result_v1(
        result,
        expected_plan=plan,
        expected_policy=policy,
        expected_coarse_space=artifact,
    )
    claims = result.to_dict()["claims"]
    assert claims["fixed_rank_coarse_correction"] is True
    assert claims["hip_execution"] is False
    assert claims["amg_hierarchy"] is False
    assert claims["domain_decomposition"] is False
    assert claims["end_to_end_o_n_proven"] is False
    assert claims["commercial_ready"] is False


def test_initial_convergence_performs_no_coarse_application() -> None:
    plan = _plan("LC_TORSION")
    artifact = _artifact(plan)
    direct = solve_sparse_execution_plan_v2(plan)
    initial = immutable_array(direct.displacements_si.reshape(-1), dtype="<f8")

    result = solve_cpu_fgmres_fixed_rank_coarse_v1(
        plan,
        _policy(),
        artifact,
        initial_full_state=initial,
    )

    assert result.status == "converged"
    assert result.termination_code == "converged_initial_true_residual"
    assert result.iteration_count == 0
    assert result.preconditioner_apply_count == 0
    assert result.complexity_receipt.preconditioner_apply_count == 0
    assert result.complexity_receipt.total_coarse_rhs_dot_count == 0


def test_build_and_solve_are_byte_deterministic() -> None:
    plan = _plan()
    candidates = _direct_reduced(plan).reshape(-1, 1)
    first = build_cpu_fgmres_fixed_rank_coarse_space_v1(
        plan,
        candidates,
        rank_cap=1,
    )
    second = build_cpu_fgmres_fixed_rank_coarse_space_v1(
        plan,
        candidates,
        rank_cap=1,
    )
    policy = _policy()
    first_result = solve_cpu_fgmres_fixed_rank_coarse_v1(plan, policy, first)
    second_result = solve_cpu_fgmres_fixed_rank_coarse_v1(plan, policy, second)

    assert first.coarse_space_hash == second.coarse_space_hash
    assert first.to_dict() == second.to_dict()
    assert first_result.result_hash == second_result.result_hash
    assert first_result.to_dict() == second_result.to_dict()
    np.testing.assert_array_equal(
        first_result.reduced_solution,
        second_result.reduced_solution,
    )


def test_dependent_candidate_is_dropped_and_complexity_is_exact() -> None:
    plan = _plan()
    mode = _direct_reduced(plan)
    artifact = build_cpu_fgmres_fixed_rank_coarse_space_v1(
        plan,
        np.column_stack((mode, 2.0 * mode)),
        rank_cap=2,
    )
    receipt = artifact.complexity_receipt

    assert artifact.candidate_count == 2
    assert artifact.retained_rank == 1
    assert receipt.basis_scaling_multiply_count == artifact.free_dof_count * 2
    assert receipt.orthogonalization_dot_count == 2
    assert receipt.orthogonalization_axpy_count == 2
    assert receipt.operator_basis_csr_apply_count == 1
    assert receipt.operator_basis_csr_multiply_count == plan.reduced_nnz
    assert receipt.coarse_operator_dot_count == 1
    assert receipt.per_apply_coarse_rhs_dot_count == 1
    assert receipt.retained_scalar_count == (
        artifact.free_dof_count
        + artifact.free_dof_count * 2
        + 3 * artifact.free_dof_count
        + 2
    )
    assert receipt.dense_projector_elements == 0
    assert receipt.max_dense_square_dimension == 1
    assert receipt.build_complexity == "O(nnz*k + N*k^2 + k^3)"
    assert receipt.application_complexity == "O(N*k + k^2)"


@pytest.mark.parametrize("rank_cap", (0, 17, True, 1.5))
def test_invalid_rank_caps_fail_closed(rank_cap: object) -> None:
    plan = _plan()
    with pytest.raises(CpuFgmresFixedRankCoarseError) as error:
        build_cpu_fgmres_fixed_rank_coarse_space_v1(
            plan,
            _direct_reduced(plan).reshape(-1, 1),
            rank_cap=rank_cap,  # type: ignore[arg-type]
        )
    assert error.value.code == "cpu_fgmres_coarse_rank_cap_invalid"


def test_unbounded_zero_and_nonfinite_candidates_fail_closed() -> None:
    plan = _plan()
    count = plan.array("free_dofs").size
    with pytest.raises(CpuFgmresFixedRankCoarseError) as error:
        build_cpu_fgmres_fixed_rank_coarse_space_v1(
            plan,
            np.ones((count, MAX_CPU_FGMRES_COARSE_RANK_V1 + 1)),
        )
    assert error.value.code == "cpu_fgmres_coarse_candidate_count_exceeds_rank_cap"
    with pytest.raises(CpuFgmresFixedRankCoarseError) as error:
        build_cpu_fgmres_fixed_rank_coarse_space_v1(
            plan,
            np.zeros((count, 1)),
            rank_cap=1,
        )
    assert error.value.code == "cpu_fgmres_coarse_basis_rank_zero"
    invalid = np.ones((count, 1), dtype="<f8")
    invalid[0, 0] = np.nan
    with pytest.raises(CpuFgmresFixedRankCoarseError) as error:
        build_cpu_fgmres_fixed_rank_coarse_space_v1(plan, invalid, rank_cap=1)
    assert error.value.code == "cpu_fgmres_coarse_candidate_nonfinite"

    huge = np.full((count, 1), np.finfo(np.float64).max, dtype="<f8")
    with pytest.raises(CpuFgmresFixedRankCoarseError) as error:
        build_cpu_fgmres_fixed_rank_coarse_space_v1(plan, huge, rank_cap=1)
    assert error.value.code == "cpu_fgmres_coarse_scaled_candidate_nonfinite"


def test_exact_plan_identity_and_replay_reject_coherent_array_tampering() -> None:
    plan = _plan()
    artifact = _artifact(plan)
    other = _plan("LC_STRONG")

    with pytest.raises(CpuFgmresFixedRankCoarseError) as error:
        validate_cpu_fgmres_fixed_rank_coarse_space_v1(
            artifact,
            expected_plan=other,
        )
    assert error.value.code == "cpu_fgmres_coarse_expected_plan_mismatch"

    tampered_basis = immutable_array(
        artifact.scaled_basis_q + 1.0e-6,
        dtype="<f8",
    )
    tampered = replace(artifact, scaled_basis_q=tampered_basis)
    with pytest.raises(CpuFgmresFixedRankCoarseError) as error:
        validate_cpu_fgmres_fixed_rank_coarse_space_v1(
            tampered,
            expected_plan=plan,
        )
    assert error.value.code in {
        "cpu_fgmres_coarse_array_invalid",
        "cpu_fgmres_coarse_replay_array_mismatch",
    }


def test_result_tampering_fails_semantic_or_hash_validation() -> None:
    plan = _plan()
    artifact = _artifact(plan)
    policy = _policy()
    result = solve_cpu_fgmres_fixed_rank_coarse_v1(plan, policy, artifact)
    tampered = replace(result, iteration_count=result.iteration_count + 1)

    with pytest.raises(CpuFgmresFixedRankCoarseError) as error:
        validate_cpu_fgmres_fixed_rank_coarse_result_v1(
            tampered,
            expected_plan=plan,
            expected_policy=policy,
            expected_coarse_space=artifact,
        )
    assert error.value.code in {
        "cpu_fgmres_coarse_result_semantics_invalid",
        "cpu_fgmres_coarse_result_hash_mismatch",
    }


def test_optional_core_preconditioner_hook_preserves_default_recurrence() -> None:
    diagonal = np.array([1.0, 3.0, 7.0], dtype="<f8")
    inverse = 1.0 / diagonal
    policy = _policy(restart_dimension=3, max_iterations=3)
    kwargs = {
        "matvec": lambda vector: diagonal * vector,
        "rhs": np.ones(3, dtype="<f8"),
        "initial_solution": np.zeros(3, dtype="<f8"),
        "inverse_diagonal": inverse,
        "policy": policy,
        "authoritative_tolerance": 1.0e-10,
    }

    default = _fgmres_core(**kwargs)
    explicit = _fgmres_core(
        **kwargs,
        right_preconditioner=lambda vector: inverse * vector,
    )

    assert default.status == explicit.status
    assert default.termination_code == explicit.termination_code
    assert default.iteration_count == explicit.iteration_count
    assert default.restart_count == explicit.restart_count
    assert default.operator_apply_count == explicit.operator_apply_count
    assert default.preconditioner_apply_count == explicit.preconditioner_apply_count
    assert default.history == explicit.history
    np.testing.assert_array_equal(default.solution, explicit.solution)
    np.testing.assert_array_equal(default.residual, explicit.residual)


@pytest.mark.parametrize(
    "preconditioner",
    (
        lambda _vector: np.ones(2, dtype="<f8"),
        lambda vector: np.full_like(vector, np.nan),
        lambda _vector: (_ for _ in ()).throw(RuntimeError("injected")),
    ),
)
def test_optional_core_preconditioner_hook_fails_closed(
    preconditioner,
) -> None:
    outcome = _fgmres_core(
        matvec=lambda vector: vector.copy(),
        rhs=np.ones(3, dtype="<f8"),
        initial_solution=np.zeros(3, dtype="<f8"),
        inverse_diagonal=np.ones(3, dtype="<f8"),
        policy=_policy(restart_dimension=1, max_iterations=1),
        authoritative_tolerance=1.0e-10,
        right_preconditioner=preconditioner,
    )

    assert outcome.status == "numerical_failure"
    assert outcome.termination_code == "preconditioner_application_nonfinite"
    assert outcome.iteration_count == 0
    assert outcome.preconditioner_apply_count == 0


def test_schemas_validate_and_source_forbids_dense_projector_shortcuts() -> None:
    plan = _plan()
    artifact = _artifact(plan)
    result = solve_cpu_fgmres_fixed_rank_coarse_v1(plan, _policy(), artifact)
    space_schema = json.loads(SPACE_SCHEMA.read_text(encoding="utf-8"))
    result_schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(space_schema)
    Draft202012Validator.check_schema(result_schema)
    assert not list(Draft202012Validator(space_schema).iter_errors(artifact.to_dict()))
    assert not list(Draft202012Validator(result_schema).iter_errors(result.to_dict()))

    source = MODULE.read_text(encoding="utf-8")
    assert "np.outer" not in source
    assert "scipy" not in source.lower()
    assert "basis_q @ basis_q.T" not in source
    assert "physical_basis_z @ physical_basis_z.T" not in source
    manifest = artifact.to_dict()
    assert manifest["claims"]["explicit_dense_n_by_n_projector"] is False
    assert manifest["complexity"]["dense_projector_elements"] == 0
