from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np
import pytest
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import splu

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.contracts.current_tangent_operator import (  # noqa: E402
    CURRENT_TANGENT_OPERATOR_PROFILE,
    CURRENT_TANGENT_OPERATOR_REFERENCE_EVALUATOR,
)
from structural_analysis.solvers.nonlinear.matrix_free_fgmres import (  # noqa: E402
    MATRIX_FREE_CPU_FGMRES_ACCUMULATION_PROFILE,
    MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PRECONDITIONER_PROFILE,
    MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PROFILE,
    MATRIX_FREE_CPU_FGMRES_PRECONDITIONER_PROFILE,
    MATRIX_FREE_CPU_FGMRES_PROFILE,
    MATRIX_FREE_CPU_FGMRES_RECURRENCE_PROFILE,
    MATRIX_FREE_STATE_TANGENT_OPERATOR_BINDING_SCHEMA_VERSION,
    MatrixFreeCPUFGMRESConfig,
    MatrixFreeCPUFGMRESError,
    create_matrix_free_cpu_fgmres_state_tangent_solver,
    create_matrix_free_cpu_fgmres_state_tangent_solver_from_canonical_sparse_lu,
)
from structural_analysis.solvers.nonlinear.canonical_sparse_lu import (  # noqa: E402
    CanonicalSparseLUFactor,
    create_canonical_sparse_lu_binary_artifact_bundle,
    create_canonical_sparse_lu_factor,
)


@dataclass
class _LoadCoupledStateProblem:
    base_tangent_kn_per_m: np.ndarray
    load_coupling_kn_per_m: np.ndarray
    cubic_kn_per_m3: np.ndarray
    case_id: str = "matrix_free_fgmres_synthetic"
    reference_preconditioner_contract: str = (
        "synthetic-zero-state-reference-csr-preconditioner.v1"
    )

    @property
    def equation_count(self) -> int:
        return int(self.base_tangent_kn_per_m.shape[0])

    def reference_preconditioner_free_csr_n_per_m(self) -> csr_matrix:
        return csr_matrix(self.base_tangent_kn_per_m * 1000.0)

    def consistent_state_tangent_action_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
        direction_m: np.ndarray,
    ) -> np.ndarray:
        tangent = (
            self.base_tangent_kn_per_m
            + float(load_factor) * self.load_coupling_kn_per_m
            + np.diag(
                3.0
                * self.cubic_kn_per_m3
                * np.asarray(free_displacements_m, dtype=np.float64) ** 2
            )
        )
        return tangent @ np.asarray(direction_m, dtype=np.float64)


def _problem() -> _LoadCoupledStateProblem:
    return _LoadCoupledStateProblem(
        base_tangent_kn_per_m=np.asarray(
            [
                [12.0, -2.0, 0.0, 0.0],
                [-2.0, 10.0, -1.5, 0.0],
                [0.0, -1.5, 9.0, -1.0],
                [0.0, 0.0, -1.0, 7.0],
            ],
            dtype=np.float64,
        ),
        load_coupling_kn_per_m=np.asarray(
            [
                [0.8, 0.1, 0.0, 0.0],
                [0.1, -0.3, 0.05, 0.0],
                [0.0, 0.05, 0.5, -0.1],
                [0.0, 0.0, -0.1, 0.2],
            ],
            dtype=np.float64,
        ),
        cubic_kn_per_m3=np.asarray([8.0, 4.0, 6.0, 3.0]),
    )


def _config() -> MatrixFreeCPUFGMRESConfig:
    return MatrixFreeCPUFGMRESConfig(
        max_iterations=8,
        restart_length=4,
        relative_tolerance_l2=1.0e-12,
        absolute_tolerance_l2_kn=1.0e-14,
        explicit_residual_tolerance_inf_kn=1.0e-11,
    )


def _canonical_factor_and_manifest(
    problem: _LoadCoupledStateProblem,
) -> tuple[CanonicalSparseLUFactor, dict[str, object]]:
    legacy = create_matrix_free_cpu_fgmres_state_tangent_solver(
        problem,
        config=_config(),
    )
    reference = problem.reference_preconditioner_free_csr_n_per_m()
    factorization = splu(reference.tocsc(), permc_spec="COLAMD")
    lower = factorization.L.tocsr(copy=True)
    upper = factorization.U.tocsr(copy=True)
    lower.sort_indices()
    upper.sort_indices()
    factor = create_canonical_sparse_lu_factor(
        lower_row_pointer=lower.indptr,
        lower_column_indices=lower.indices,
        lower_numeric_values=lower.data,
        upper_row_pointer=upper.indptr,
        upper_column_indices=upper.indices,
        upper_numeric_values=upper.data,
        row_permutation=factorization.perm_r,
        column_permutation=factorization.perm_c,
        source_operator_pattern_hash=(
            legacy.reference_preconditioner_pattern_hash
        ),
        source_operator_numeric_values_hash=(
            legacy.reference_preconditioner_values_hash
        ),
    )
    bundle = create_canonical_sparse_lu_binary_artifact_bundle(
        factor,
        artifact_uri_prefix="artifact://synthetic-canonical-factor",
    )
    return factor, bundle.to_manifest()


def test_matrix_free_fgmres_matches_dense_current_tangent() -> None:
    problem = _problem()
    solver = create_matrix_free_cpu_fgmres_state_tangent_solver(
        problem,
        config=_config(),
    )
    state = np.asarray([0.12, -0.08, 0.05, -0.03], dtype=np.float64)
    load_factor = 0.7
    right_hand_side = np.asarray([1.2, -0.5, 0.8, -0.3], dtype=np.float64)
    tangent = (
        problem.base_tangent_kn_per_m
        + load_factor * problem.load_coupling_kn_per_m
        + np.diag(3.0 * problem.cubic_kn_per_m3 * state**2)
    )
    expected = np.linalg.solve(tangent, right_hand_side)

    result = solver.solve_at_state(
        problem,
        state,
        right_hand_side,
        load_factor=load_factor,
        solve_id="dense-comparison",
    )

    assert solver.profile == MATRIX_FREE_CPU_FGMRES_PROFILE
    assert result.contract_pass is True
    assert result.terminal_reason == "converged_explicit_residual"
    np.testing.assert_allclose(
        result.solution_free,
        expected,
        rtol=1.0e-11,
        atol=1.0e-12,
    )
    receipt = result.receipt
    assert receipt["status"] == "ready"
    assert receipt["contract_pass"] is True
    assert receipt["matrix_free_current_state_operator_action"] is True
    assert receipt["materialized_current_tangent"] is False
    assert receipt["iteration_count"] <= 4
    assert receipt["operator_action_count"] >= receipt["iteration_count"] + 1
    assert receipt["preconditioner_application_count"] == receipt[
        "iteration_count"
    ]
    assert receipt["explicit_residual_inf_kn"] <= 1.0e-11
    assert receipt["fallback_count"] == 0
    assert receipt["regularization_count"] == 0
    assert receipt["operator_binding_ready"] is False
    assert receipt["operator_binding"]["status"] == "unbound"
    assert receipt["deterministic_host_recurrence_arithmetic_claim"] is True
    assert receipt["recurrence"]["profile"] == (
        MATRIX_FREE_CPU_FGMRES_RECURRENCE_PROFILE
    )
    assert receipt["recurrence"]["accumulation_profile"] == (
        MATRIX_FREE_CPU_FGMRES_ACCUMULATION_PROFILE
    )
    assert receipt["recurrence"]["deterministic_host_arithmetic"] is True
    assert receipt["recurrence"]["operator_callback_outputs_in_contract"] is False
    assert (
        receipt["recurrence"]["preconditioner_callback_outputs_in_contract"]
        is False
    )
    assert receipt["cross_platform_deterministic_recurrence_claim"] is False
    assert receipt["production_solver_claim"] is False
    assert receipt["rocm_hip_parity_claim"] is False
    assert receipt["promotes_g1_closure"] is False
    assert receipt["preconditioner"]["profile"] == (
        MATRIX_FREE_CPU_FGMRES_PRECONDITIONER_PROFILE
    )
    assert receipt["preconditioner"]["fixed_right_preconditioner"] is True
    assert receipt["preconditioner"]["current_jacobian_claim"] is False
    assert receipt["preconditioner"]["production_preconditioner_claim"] is False


def test_canonical_sparse_lu_factory_binds_factor_artifact_and_current_tangent(
) -> None:
    problem = _problem()
    factor, binary_manifest = _canonical_factor_and_manifest(problem)
    solver = (
        create_matrix_free_cpu_fgmres_state_tangent_solver_from_canonical_sparse_lu(
            problem,
            factor=factor,
            binary_artifact_manifest=binary_manifest,
            config=_config(),
        )
    )
    state = np.asarray([0.12, -0.08, 0.05, -0.03], dtype=np.float64)
    load_factor = 0.7
    right_hand_side = np.asarray([1.2, -0.5, 0.8, -0.3], dtype=np.float64)
    tangent = (
        problem.base_tangent_kn_per_m
        + load_factor * problem.load_coupling_kn_per_m
        + np.diag(3.0 * problem.cubic_kn_per_m3 * state**2)
    )

    result = solver.solve_at_state(
        problem,
        state,
        right_hand_side,
        load_factor=load_factor,
        solve_id="canonical-factor-current-tangent",
    )

    assert solver.profile == MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PROFILE
    assert solver.preconditioner_factor_contract_hash == factor.contract_hash
    assert solver.preconditioner_binary_artifact_bundle_hash == (
        binary_manifest["bundle_hash"]
    )
    assert result.contract_pass is True
    np.testing.assert_allclose(
        result.solution_free,
        np.linalg.solve(tangent, right_hand_side),
        rtol=1.0e-11,
        atol=1.0e-12,
    )
    receipt = result.receipt
    preconditioner = receipt["preconditioner"]
    assert preconditioner["profile"] == (
        MATRIX_FREE_CPU_FGMRES_CANONICAL_SPARSE_LU_PRECONDITIONER_PROFILE
    )
    assert preconditioner["factor_contract_hash"] == factor.contract_hash
    assert preconditioner["binary_artifact_bundle_hash"] == (
        binary_manifest["bundle_hash"]
    )
    assert preconditioner["binary_artifact_bundle_bound"] is True
    assert preconditioner["retained_release_artifact_claim"] is False
    assert preconditioner["production_preconditioner_claim"] is False
    assert receipt["recurrence"][
        "preconditioner_callback_outputs_in_contract"
    ] is True
    assert receipt["matrix_free_current_state_operator_action"] is True
    assert receipt["materialized_current_tangent"] is False
    assert receipt["cross_platform_deterministic_recurrence_claim"] is False
    assert receipt["production_solver_claim"] is False
    assert receipt["rocm_hip_parity_claim"] is False


def test_canonical_sparse_lu_factory_replays_exactly_in_one_runtime() -> None:
    problem = _problem()
    factor, binary_manifest = _canonical_factor_and_manifest(problem)
    solver = (
        create_matrix_free_cpu_fgmres_state_tangent_solver_from_canonical_sparse_lu(
            problem,
            factor=factor,
            binary_artifact_manifest=binary_manifest,
            config=_config(),
        )
    )
    state = np.asarray([0.12, -0.08, 0.05, -0.03], dtype=np.float64)
    right_hand_side = np.asarray([1.2, -0.5, 0.8, -0.3], dtype=np.float64)

    first = solver.solve_at_state(
        problem,
        state,
        right_hand_side,
        load_factor=0.7,
        solve_id="canonical-exact-replay",
    )
    second = solver.solve_at_state(
        problem,
        state,
        right_hand_side,
        load_factor=0.7,
        solve_id="canonical-exact-replay",
    )

    assert first.solution_free == second.solution_free
    assert first.receipt == second.receipt


def test_canonical_sparse_lu_factory_rejects_stale_source_binding() -> None:
    problem = _problem()
    factor, _binary_manifest = _canonical_factor_and_manifest(problem)
    stale = create_canonical_sparse_lu_factor(
        lower_row_pointer=factor.lower_row_pointer,
        lower_column_indices=factor.lower_column_indices,
        lower_numeric_values=factor.lower_numeric_values,
        upper_row_pointer=factor.upper_row_pointer,
        upper_column_indices=factor.upper_column_indices,
        upper_numeric_values=factor.upper_numeric_values,
        row_permutation=factor.row_permutation,
        column_permutation=factor.column_permutation,
        source_operator_pattern_hash="sha256:" + "9" * 64,
        source_operator_numeric_values_hash=(
            factor.source_operator_numeric_values_hash
        ),
    )

    with pytest.raises(
        MatrixFreeCPUFGMRESError,
        match="canonical reference preconditioner source binding mismatch",
    ):
        create_matrix_free_cpu_fgmres_state_tangent_solver_from_canonical_sparse_lu(
            problem,
            factor=stale,
            config=_config(),
        )


def test_canonical_sparse_lu_factory_rejects_forged_binary_manifest() -> None:
    problem = _problem()
    factor, binary_manifest = _canonical_factor_and_manifest(problem)
    forged = dict(binary_manifest)
    forged["factor_contract_hash"] = "sha256:" + "8" * 64

    with pytest.raises(
        MatrixFreeCPUFGMRESError,
        match="binary artifact manifest is invalid",
    ):
        create_matrix_free_cpu_fgmres_state_tangent_solver_from_canonical_sparse_lu(
            problem,
            factor=factor,
            binary_artifact_manifest=forged,
            config=_config(),
        )


def test_matrix_free_fgmres_replay_is_exact_for_same_local_runtime() -> None:
    problem = _problem()
    solver = create_matrix_free_cpu_fgmres_state_tangent_solver(
        problem,
        config=_config(),
    )
    state = np.asarray([0.12, -0.08, 0.05, -0.03], dtype=np.float64)
    right_hand_side = np.asarray([1.2, -0.5, 0.8, -0.3], dtype=np.float64)

    first = solver.solve_at_state(
        problem,
        state,
        right_hand_side,
        load_factor=0.7,
        solve_id="exact-local-replay",
    )
    second = solver.solve_at_state(
        problem,
        state,
        right_hand_side,
        load_factor=0.7,
        solve_id="exact-local-replay",
    )

    assert first.solution_free == second.solution_free
    assert first.receipt == second.receipt
    assert first.receipt[
        "cross_platform_deterministic_recurrence_claim"
    ] is False
    assert first.receipt["state_operator_binding_hash"] == second.receipt[
        "state_operator_binding_hash"
    ]


def test_matrix_free_fgmres_binds_operator_identity_when_exposed() -> None:
    problem = _problem()
    digest = "sha256:" + "1" * 64
    problem.matrix_free_current_tangent_operator_binding = lambda: {
        "schema_version": (
            MATRIX_FREE_STATE_TANGENT_OPERATOR_BINDING_SCHEMA_VERSION
        ),
        "case_id": problem.case_id,
        "equation_count": problem.equation_count,
        "free_equation_order_data_hash": digest,
        "residual_formula_hash": "sha256:" + "2" * 64,
        "current_tangent_action_contract": "synthetic-analytic-action.v1",
        "reference_load_free_n_data_hash": "sha256:" + "3" * 64,
        "residual_force_unit": "kN",
        "displacement_unit": "m",
        "tangent_action_unit": "kN/m",
        "load_factor_unit": "dimensionless",
    }
    solver = create_matrix_free_cpu_fgmres_state_tangent_solver(
        problem,
        config=_config(),
    )

    result = solver.solve_at_state(
        problem,
        np.asarray([0.12, -0.08, 0.05, -0.03], dtype=np.float64),
        np.asarray([1.2, -0.5, 0.8, -0.3], dtype=np.float64),
        load_factor=0.7,
        solve_id="bound-operator",
    )

    assert result.contract_pass is True
    assert result.receipt["operator_binding_ready"] is True
    assert result.receipt["operator_binding"][
        "free_equation_order_data_hash"
    ] == digest
    assert result.receipt["operator_binding"]["status"] == "ready"


def test_matrix_free_fgmres_marks_formula_bound_operator_outputs() -> None:
    problem = _problem()
    digest = "sha256:" + "4" * 64
    problem.matrix_free_current_tangent_operator_binding = lambda: {
        "schema_version": (
            MATRIX_FREE_STATE_TANGENT_OPERATOR_BINDING_SCHEMA_VERSION
        ),
        "case_id": problem.case_id,
        "equation_count": problem.equation_count,
        "free_equation_order_data_hash": "sha256:" + "1" * 64,
        "residual_formula_hash": "sha256:" + "2" * 64,
        "current_tangent_action_contract": "synthetic-analytic-action.v1",
        "reference_load_free_n_data_hash": "sha256:" + "3" * 64,
        "residual_force_unit": "kN",
        "displacement_unit": "m",
        "tangent_action_unit": "kN/m",
        "load_factor_unit": "dimensionless",
        "current_tangent_operator_profile": CURRENT_TANGENT_OPERATOR_PROFILE,
        "current_tangent_operator_contract_hash": digest,
        "current_tangent_operator_array_bundle_hash": "sha256:" + "5" * 64,
        "operator_callback_reference_evaluator": (
            CURRENT_TANGENT_OPERATOR_REFERENCE_EVALUATOR
        ),
        "operator_callback_outputs_in_contract": True,
    }
    solver = create_matrix_free_cpu_fgmres_state_tangent_solver(
        problem,
        config=_config(),
    )

    result = solver.solve_at_state(
        problem,
        np.asarray([0.12, -0.08, 0.05, -0.03], dtype=np.float64),
        np.asarray([1.2, -0.5, 0.8, -0.3], dtype=np.float64),
        load_factor=0.7,
        solve_id="formula-bound-operator",
    )

    assert result.contract_pass is True
    assert result.receipt["operator_binding"][
        "current_tangent_operator_contract_hash"
    ] == digest
    assert result.receipt["recurrence"][
        "operator_callback_outputs_in_contract"
    ] is True
    assert result.receipt["cross_platform_deterministic_recurrence_claim"] is False


def test_matrix_free_fgmres_rejects_mismatched_operator_binding() -> None:
    problem = _problem()
    problem.matrix_free_current_tangent_operator_binding = lambda: {
        "schema_version": (
            MATRIX_FREE_STATE_TANGENT_OPERATOR_BINDING_SCHEMA_VERSION
        ),
        "case_id": problem.case_id,
        "equation_count": problem.equation_count + 1,
        "free_equation_order_data_hash": "sha256:" + "1" * 64,
        "residual_formula_hash": "sha256:" + "2" * 64,
        "current_tangent_action_contract": "synthetic-analytic-action.v1",
        "reference_load_free_n_data_hash": "sha256:" + "3" * 64,
        "residual_force_unit": "kN",
        "displacement_unit": "m",
        "tangent_action_unit": "kN/m",
        "load_factor_unit": "dimensionless",
    }

    with pytest.raises(
        MatrixFreeCPUFGMRESError,
        match="operator binding equation_count mismatch",
    ):
        create_matrix_free_cpu_fgmres_state_tangent_solver(problem)


def test_matrix_free_fgmres_rechecks_operator_binding_at_solve_time() -> None:
    problem = _problem()

    def binding(residual_hash_digit: str) -> dict[str, object]:
        return {
            "schema_version": (
                MATRIX_FREE_STATE_TANGENT_OPERATOR_BINDING_SCHEMA_VERSION
            ),
            "case_id": problem.case_id,
            "equation_count": problem.equation_count,
            "free_equation_order_data_hash": "sha256:" + "1" * 64,
            "residual_formula_hash": (
                "sha256:" + residual_hash_digit * 64
            ),
            "current_tangent_action_contract": (
                "synthetic-analytic-action.v1"
            ),
            "reference_load_free_n_data_hash": "sha256:" + "3" * 64,
            "residual_force_unit": "kN",
            "displacement_unit": "m",
            "tangent_action_unit": "kN/m",
            "load_factor_unit": "dimensionless",
        }

    problem.matrix_free_current_tangent_operator_binding = lambda: binding(
        "2"
    )
    solver = create_matrix_free_cpu_fgmres_state_tangent_solver(
        problem,
        config=_config(),
    )
    problem.matrix_free_current_tangent_operator_binding = lambda: binding(
        "4"
    )

    with pytest.raises(
        MatrixFreeCPUFGMRESError,
        match="problem operator binding does not match the solver binding",
    ):
        solver.solve_at_state(
            problem,
            np.zeros(problem.equation_count),
            np.ones(problem.equation_count),
            load_factor=0.0,
            solve_id="swapped-operator-binding",
        )


def test_matrix_free_fgmres_accepts_zero_rhs_at_initial_gate() -> None:
    problem = _problem()
    solver = create_matrix_free_cpu_fgmres_state_tangent_solver(
        problem,
        config=_config(),
    )

    result = solver.solve_at_state(
        problem,
        np.zeros(problem.equation_count),
        np.zeros(problem.equation_count),
        load_factor=0.0,
        solve_id="zero-rhs",
    )

    assert result.contract_pass is True
    assert result.terminal_reason == "initial_explicit_residual_satisfied"
    assert result.solution_free == (0.0, 0.0, 0.0, 0.0)
    assert result.receipt["iteration_count"] == 0
    assert result.receipt["operator_action_count"] == 1
    assert result.receipt["explicit_residual_inf_kn"] == 0.0


def test_matrix_free_fgmres_factory_fails_closed_without_binding() -> None:
    problem = _problem()
    problem.reference_preconditioner_contract = "unavailable"

    with pytest.raises(
        MatrixFreeCPUFGMRESError,
        match="preconditioner contract is unavailable",
    ):
        create_matrix_free_cpu_fgmres_state_tangent_solver(problem)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_iterations": 0},
        {"max_iterations": 3, "restart_length": 4},
        {"relative_tolerance_l2": 0.0, "absolute_tolerance_l2_kn": 0.0},
        {"explicit_residual_tolerance_inf_kn": 0.0},
    ],
)
def test_matrix_free_fgmres_config_fails_closed(kwargs: dict) -> None:
    with pytest.raises(MatrixFreeCPUFGMRESError):
        MatrixFreeCPUFGMRESConfig(**kwargs)
