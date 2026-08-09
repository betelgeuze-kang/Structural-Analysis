from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

from structural_analysis.engine_v2.contracts.current_tangent_operator import (
    CURRENT_TANGENT_OPERATOR_PROFILE,
    CURRENT_TANGENT_OPERATOR_REFERENCE_EVALUATOR,
    create_current_tangent_operator,
)


PHASE1 = Path(__file__).resolve().parents[1] / "implementation" / "phase1"
MODULE_PATH = PHASE1 / "g1_mgt_load_coupled_arc_length_adapter.py"
SPEC = importlib.util.spec_from_file_location(
    "g1_mgt_load_coupled_arc_length_adapter",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _synthetic_problem():
    matrix = np.asarray(
        [
            [5000.0, -1200.0, 0.0],
            [-1200.0, 4200.0, -600.0],
            [0.0, -600.0, 3000.0],
        ],
        dtype=float,
    )
    load_coupling = np.diag([80.0, -25.0, 10.0])
    reference_load_n = np.asarray([1000.0, -250.0, 500.0])
    cubic_n_per_m3 = 2.0e5

    def residual_free_n(displacement: np.ndarray, load_factor: float) -> np.ndarray:
        return (
            matrix @ displacement
            + float(load_factor) * (load_coupling @ displacement)
            + cubic_n_per_m3 * displacement**3
            - float(load_factor) * reference_load_n
        )

    def negative_load_derivative_free_n(
        displacement: np.ndarray,
        load_factor: float,
    ) -> np.ndarray:
        del load_factor
        return reference_load_n - load_coupling @ displacement

    problem = module.LoadCoupledArcLengthCallbackProblem(
        case_id="synthetic_mgt_adapter_contract",
        initial_displacements_m=np.asarray([0.01, -0.004, 0.006]),
        initial_factor=0.656,
        reference_load_free_n=reference_load_n,
        residual_free_n=residual_free_n,
        negative_load_derivative_free_n=(negative_load_derivative_free_n),
        tangent_difference_step_m=1.0e-7,
    )
    return problem, matrix, load_coupling, cubic_n_per_m3


def test_roundtrip_json_hash_is_independent_of_checkout_path() -> None:
    mgt_path = PHASE1 / "open_data/midas/midas_generator_33.optimized.mgt"
    first = {
        "generated_at": "2026-07-19T00:00:00Z",
        "source": {
            "path": "/tmp/first-worktree/model.mgt",
            "sha256": "a" * 64,
        },
        "model": {"node_count": 2},
    }
    second = {
        **first,
        "generated_at": "2026-07-19T01:00:00Z",
        "source": {
            **first["source"],
            "path": "C:/second-worktree/model.mgt",
        },
    }

    assert module._canonical_roundtrip_json_hash(
        first,
        mgt_path=mgt_path,
    ) == module._canonical_roundtrip_json_hash(
        second,
        mgt_path=mgt_path,
    )
    assert first["source"]["path"] == "/tmp/first-worktree/model.mgt"


def test_callback_problem_converts_newtons_to_kilonewtons() -> None:
    problem, _, _, _ = _synthetic_problem()
    displacement = problem.initial_free_displacements_m()
    load_factor = problem.initial_load_factor()

    expected_residual_kn = problem.residual_free_n(displacement, load_factor) / 1000.0
    expected_load_rhs_kn = (
        problem.negative_load_derivative_free_n(displacement, load_factor) / 1000.0
    )

    np.testing.assert_array_equal(problem.reference_load_kn(), [1.0, -0.25, 0.5])
    np.testing.assert_allclose(
        problem.residual_kn(displacement, load_factor),
        expected_residual_kn,
    )
    np.testing.assert_allclose(
        problem.negative_load_derivative_kn(displacement, load_factor),
        expected_load_rhs_kn,
    )


def test_callback_problem_exposes_predictor_as_an_isolated_copy() -> None:
    problem, _, _, _ = _synthetic_problem()
    with pytest.raises(
        ValueError,
        match="zero-state predictor direction is unavailable",
    ):
        problem.full_unit_zero_state_predictor_free_m()

    source = np.asarray([0.1, -0.2, 0.3])
    problem_with_predictor = replace(
        problem,
        zero_state_predictor_free_m=source,
    )
    source[:] = 0.0

    first = problem_with_predictor.full_unit_zero_state_predictor_free_m()
    np.testing.assert_array_equal(first, [0.1, -0.2, 0.3])
    first[:] = 1.0
    np.testing.assert_array_equal(
        problem_with_predictor.full_unit_zero_state_predictor_free_m(),
        [0.1, -0.2, 0.3],
    )


def test_callback_tangent_action_matches_analytic_load_coupled_jacobian() -> None:
    problem, matrix, load_coupling, cubic = _synthetic_problem()
    displacement = problem.initial_free_displacements_m()
    load_factor = problem.initial_load_factor()
    direction = np.asarray([0.5, -0.2, 0.9])
    analytic = (
        (matrix + load_factor * load_coupling + np.diag(3.0 * cubic * displacement**2))
        @ direction
        / 1000.0
    )

    action = problem.consistent_state_tangent_action_kn_per_m(
        displacement,
        load_factor,
        direction,
    )

    np.testing.assert_allclose(action, analytic, rtol=1.0e-8, atol=1.0e-8)


def test_callback_prefers_bound_analytic_state_tangent_action() -> None:
    problem, matrix, load_coupling, cubic = _synthetic_problem()

    def analytic_action_n_per_m(
        displacement: np.ndarray,
        load_factor: float,
        direction: np.ndarray,
    ) -> np.ndarray:
        return (
            matrix
            + load_factor * load_coupling
            + np.diag(3.0 * cubic * displacement**2)
        ) @ direction

    bound = replace(
        problem,
        state_tangent_action_free_n_per_m=analytic_action_n_per_m,
    )
    displacement = bound.initial_free_displacements_m()
    load_factor = bound.initial_load_factor()
    direction = np.asarray([0.5, -0.2, 0.9])
    expected = (
        analytic_action_n_per_m(
            displacement,
            load_factor,
            direction,
        )
        / 1000.0
    )

    np.testing.assert_array_equal(
        bound.consistent_state_tangent_action_kn_per_m(
            displacement,
            load_factor,
            direction,
        ),
        expected,
    )
    assert bound.zero_state_problem().state_tangent_action_free_n_per_m is (
        analytic_action_n_per_m
    )


def test_initial_state_audit_passes_without_promoting_g1() -> None:
    problem, _, _, _ = _synthetic_problem()

    payload = module.audit_load_coupled_problem_at_initial_state(problem)

    assert payload["status"] == "partial"
    assert payload["contract_pass"] is True
    assert payload["promotes_g1_closure"] is False
    assert payload["residual_equilibrium_gate_required_by_adapter_audit"] is False
    assert payload["residual_equilibrium_gate_passed"] is False
    assert payload["negative_load_derivative_gate_passed"] is True
    assert payload["negative_load_derivative_absolute_tolerance_kn"] == 1.0e-6
    assert payload["negative_load_derivative_relative_tolerance"] == 1.0e-8
    assert payload["tangent_step_comparison_gate_passed"] is True
    assert payload["claims"]["actual_mgt_residual_adapter_evaluated"] is True
    assert payload["claims"]["full_arc_length_continuation"] is False
    assert payload["claims"]["engine_v2_production_krylov"] is False
    assert payload["claims"]["material_state_commit_rollback"] is False
    assert payload["claims"]["production_rocm_hip_nonlinear_parity"] is False
    assert payload["claims"]["g1_full_building_closure"] is False


def test_callback_problem_fails_closed_on_dimension_mismatch() -> None:
    problem, _, _, _ = _synthetic_problem()

    with pytest.raises(ValueError, match="dimension mismatch"):
        problem.residual_kn(np.zeros(2), problem.initial_load_factor())


def test_zero_state_problem_reuses_exact_linear_csr_tangent() -> None:
    tangent_n_per_m = np.asarray(
        [[4000.0, -1000.0], [-1000.0, 3000.0]],
        dtype=np.float64,
    )
    reference_load_n = np.asarray([500.0, -250.0], dtype=np.float64)

    def residual_free_n(
        displacement: np.ndarray,
        load_factor: float,
    ) -> np.ndarray:
        return tangent_n_per_m @ displacement - float(load_factor) * reference_load_n

    problem = module.LoadCoupledArcLengthCallbackProblem(
        case_id="linear_state_invariant_contract",
        initial_displacements_m=np.asarray([0.2, -0.1]),
        initial_factor=0.656,
        reference_load_free_n=reference_load_n,
        residual_free_n=residual_free_n,
        negative_load_derivative_free_n=(
            lambda displacement, load_factor: reference_load_n
        ),
        initial_state_policy="historical_checkpoint",
        state_invariant_tangent_csr_n_per_m=tangent_n_per_m,
        state_invariant_tangent_contract=(module.MGT_STATE_INVARIANT_TANGENT_CONTRACT),
    )

    zero_problem = problem.zero_state_problem()
    direction = np.asarray([0.7, -0.3], dtype=np.float64)

    assert zero_problem.initial_state_policy == "zero_state"
    assert zero_problem.initial_load_factor() == 0.0
    np.testing.assert_array_equal(
        zero_problem.initial_free_displacements_m(),
        np.zeros(2),
    )
    tangent = zero_problem.state_invariant_tangent_free_csr_n_per_m()
    np.testing.assert_allclose(tangent @ direction, tangent_n_per_m @ direction)
    np.testing.assert_allclose(
        zero_problem.consistent_state_tangent_action_kn_per_m(
            np.zeros(2),
            0.0,
            direction,
        ),
        (tangent_n_per_m @ direction) / 1000.0,
        rtol=1.0e-9,
        atol=1.0e-12,
    )


def test_state_invariant_tangent_contract_fails_closed() -> None:
    with pytest.raises(ValueError, match="initial_state_policy"):
        module.LoadCoupledArcLengthCallbackProblem(
            case_id="bad_policy",
            initial_displacements_m=np.zeros(2),
            initial_factor=0.0,
            reference_load_free_n=np.ones(2),
            residual_free_n=lambda displacement, load_factor: displacement,
            negative_load_derivative_free_n=(
                lambda displacement, load_factor: np.ones(2)
            ),
            initial_state_policy="implicit_checkpoint_guess",
        )

    with pytest.raises(ValueError, match="dimension mismatch"):
        module.LoadCoupledArcLengthCallbackProblem(
            case_id="bad_tangent",
            initial_displacements_m=np.zeros(2),
            initial_factor=0.0,
            reference_load_free_n=np.ones(2),
            residual_free_n=lambda displacement, load_factor: displacement,
            negative_load_derivative_free_n=(
                lambda displacement, load_factor: np.ones(2)
            ),
            state_invariant_tangent_csr_n_per_m=np.eye(3),
            state_invariant_tangent_contract=(
                module.MGT_STATE_INVARIANT_TANGENT_CONTRACT
            ),
        )


def test_reference_preconditioner_is_exposed_as_an_isolated_csr_copy() -> None:
    reference_preconditioner = np.asarray(
        [[4_000.0, -1_000.0], [-1_000.0, 3_000.0]],
        dtype=np.float64,
    )
    problem = module.LoadCoupledArcLengthCallbackProblem(
        case_id="reference_preconditioner_contract",
        initial_displacements_m=np.zeros(2),
        initial_factor=0.0,
        reference_load_free_n=np.asarray([500.0, -250.0]),
        residual_free_n=lambda displacement, load_factor: (
            reference_preconditioner @ displacement
            - load_factor * np.asarray([500.0, -250.0])
        ),
        negative_load_derivative_free_n=(
            lambda displacement, load_factor: np.asarray([500.0, -250.0])
        ),
        reference_preconditioner_csr_n_per_m=reference_preconditioner,
        reference_preconditioner_contract=(
            module.MGT_REFERENCE_PRECONDITIONER_CONTRACT
        ),
    )

    first = problem.reference_preconditioner_free_csr_n_per_m()
    np.testing.assert_allclose(first.toarray(), reference_preconditioner)
    first.data[:] = 0.0
    np.testing.assert_allclose(
        problem.reference_preconditioner_free_csr_n_per_m().toarray(),
        reference_preconditioner,
    )
    zero_problem = problem.zero_state_problem()
    assert zero_problem.reference_preconditioner_contract == (
        module.MGT_REFERENCE_PRECONDITIONER_CONTRACT
    )
    np.testing.assert_allclose(
        zero_problem.reference_preconditioner_free_csr_n_per_m().toarray(),
        reference_preconditioner,
    )


def test_reference_preconditioner_contract_fails_closed() -> None:
    common = {
        "case_id": "bad_reference_preconditioner",
        "initial_displacements_m": np.zeros(2),
        "initial_factor": 0.0,
        "reference_load_free_n": np.ones(2),
        "residual_free_n": lambda displacement, load_factor: displacement,
        "negative_load_derivative_free_n": (
            lambda displacement, load_factor: np.ones(2)
        ),
    }
    with pytest.raises(ValueError, match="dimension mismatch"):
        module.LoadCoupledArcLengthCallbackProblem(
            **common,
            reference_preconditioner_csr_n_per_m=np.eye(3),
            reference_preconditioner_contract=(
                module.MGT_REFERENCE_PRECONDITIONER_CONTRACT
            ),
        )
    with pytest.raises(ValueError, match="contract is required"):
        module.LoadCoupledArcLengthCallbackProblem(
            **common,
            reference_preconditioner_csr_n_per_m=np.eye(2),
        )


def test_matrix_free_operator_binding_propagates_to_zero_state() -> None:
    tangent_n_per_m = np.asarray(
        [[4000.0, -1000.0], [-1000.0, 3000.0]],
        dtype=np.float64,
    )
    reference_load_n = np.asarray([500.0, -250.0], dtype=np.float64)
    free_dofs = np.asarray([2, 5], dtype=np.int64)
    residual_formula_hash = "sha256:" + "4" * 64

    problem = module.LoadCoupledArcLengthCallbackProblem(
        case_id="matrix_free_bound_callback",
        initial_displacements_m=np.zeros(2),
        initial_factor=0.0,
        reference_load_free_n=reference_load_n,
        residual_free_n=lambda displacement, load_factor: (
            tangent_n_per_m @ displacement - load_factor * reference_load_n
        ),
        negative_load_derivative_free_n=(
            lambda displacement, load_factor: reference_load_n
        ),
        reference_preconditioner_csr_n_per_m=tangent_n_per_m,
        reference_preconditioner_contract=(
            module.MGT_REFERENCE_PRECONDITIONER_CONTRACT
        ),
        state_tangent_action_free_n_per_m=(
            lambda displacement, load_factor, direction: tangent_n_per_m @ direction
        ),
        free_equation_global_dofs=free_dofs,
        residual_formula_hash=residual_formula_hash,
        current_tangent_action_contract=(
            module.MGT_CURRENT_STATE_TANGENT_ACTION_CONTRACT
        ),
        source_commit_sha="a" * 40,
        model_source_sha256="sha256:" + "b" * 64,
        equilibrium_operator_binding_hash="sha256:" + "c" * 64,
    )

    binding = problem.matrix_free_current_tangent_operator_binding()
    assert binding is not None
    assert binding["equation_count"] == 2
    assert binding["free_equation_order_data_hash"] == module._array_hash(
        free_dofs,
        dtype="<i8",
    )
    assert binding["residual_formula_hash"] == residual_formula_hash
    assert binding["reference_load_free_n_data_hash"] == module._array_hash(
        reference_load_n,
        dtype="<f8",
    )
    assert binding["exact_restart_binding"] == {
        "source_commit_sha": "a" * 40,
        "model_source_sha256": "sha256:" + "b" * 64,
        "equilibrium_operator_binding_hash": "sha256:" + "c" * 64,
        "complete": True,
    }
    assert problem.free_equation_global_dofs is not None
    assert problem.free_equation_global_dofs.flags.writeable is False
    assert (
        problem.zero_state_problem().matrix_free_current_tangent_operator_binding()
        == binding
    )


@pytest.mark.parametrize(
    "restart_identity",
    [
        {},
        {
            "source_commit_sha": "a" * 40,
            "model_source_sha256": "sha256:" + "b" * 64,
        },
    ],
)
def test_matrix_free_operator_binding_omits_incomplete_exact_restart_identity(
    restart_identity: dict[str, str],
) -> None:
    reference_load_n = np.asarray([500.0, -250.0], dtype=np.float64)
    problem = module.LoadCoupledArcLengthCallbackProblem(
        case_id="matrix_free_without_complete_restart_identity",
        initial_displacements_m=np.zeros(2),
        initial_factor=0.0,
        reference_load_free_n=reference_load_n,
        residual_free_n=lambda displacement, load_factor: (
            displacement - load_factor * reference_load_n
        ),
        negative_load_derivative_free_n=(
            lambda displacement, load_factor: reference_load_n
        ),
        state_tangent_action_free_n_per_m=(
            lambda displacement, load_factor, direction: direction
        ),
        free_equation_global_dofs=np.asarray([2, 5], dtype=np.int64),
        residual_formula_hash="sha256:" + "4" * 64,
        current_tangent_action_contract=(
            module.MGT_CURRENT_STATE_TANGENT_ACTION_CONTRACT
        ),
        **restart_identity,
    )

    assert problem.exact_restart_binding()["complete"] is False
    binding = problem.matrix_free_current_tangent_operator_binding()
    assert binding is not None
    assert "exact_restart_binding" not in binding
    assert (
        problem.zero_state_problem().matrix_free_current_tangent_operator_binding()
        == binding
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_commit_sha", "not-a-commit", "source_commit_sha"),
        ("model_source_sha256", "sha256:short", "model_source_sha256"),
        (
            "equilibrium_operator_binding_hash",
            "sha256:short",
            "equilibrium_operator_binding_hash",
        ),
    ],
)
def test_exact_restart_binding_rejects_noncanonical_identity(
    field: str,
    value: str,
    message: str,
) -> None:
    kwargs = {
        "case_id": "invalid_restart_binding",
        "initial_displacements_m": np.zeros(2),
        "initial_factor": 0.0,
        "reference_load_free_n": np.ones(2),
        "residual_free_n": lambda displacement, load_factor: displacement,
        "negative_load_derivative_free_n": (
            lambda displacement, load_factor: np.ones(2)
        ),
        field: value,
    }
    with pytest.raises(ValueError, match=message):
        module.LoadCoupledArcLengthCallbackProblem(**kwargs)


def test_backend_neutral_operator_drives_callback_and_extended_binding() -> None:
    matrix = np.asarray(
        [[4000.0, -1000.0], [-1000.0, 3000.0]],
        dtype=np.float64,
    )
    free_dofs = np.asarray([0, 1], dtype=np.int64)
    residual_formula_hash = "sha256:" + "7" * 64
    operator = create_current_tangent_operator(
        case_id="contract_bound_callback",
        residual_formula_hash=residual_formula_hash,
        source_action_contract=module.MGT_CURRENT_STATE_TANGENT_ACTION_CONTRACT,
        reference_row_pointer=np.asarray([0, 2, 4], dtype=np.int64),
        reference_column_indices=np.asarray([0, 1, 0, 1], dtype=np.int64),
        reference_values_n_per_m=matrix.reshape(-1),
        free_global_dofs=free_dofs,
        background_global_displacements_m=np.zeros(2),
        frame_dofs=np.empty((0, 12), dtype=np.int64),
        frame_stiffness_delta_n_per_m=np.empty(
            (0, 12, 12),
            dtype=np.float64,
        ),
        geometry_dofs=np.empty((0, 12), dtype=np.int64),
        geometry_relative_translation_operators=np.empty(
            (0, 3, 12),
            dtype=np.float64,
        ),
        geometry_reference_chords_m=np.empty((0, 3), dtype=np.float64),
        geometry_reference_lengths_m=np.empty(0, dtype=np.float64),
        geometry_axial_stiffness_n_per_m=np.empty(0, dtype=np.float64),
    )
    problem = module.LoadCoupledArcLengthCallbackProblem(
        case_id="contract_bound_callback",
        initial_displacements_m=np.zeros(2),
        initial_factor=0.0,
        reference_load_free_n=np.asarray([500.0, -250.0]),
        residual_free_n=lambda displacement, load_factor: matrix @ displacement,
        negative_load_derivative_free_n=(
            lambda displacement, load_factor: np.asarray([500.0, -250.0])
        ),
        reference_preconditioner_csr_n_per_m=matrix,
        reference_preconditioner_contract=(
            module.MGT_REFERENCE_PRECONDITIONER_CONTRACT
        ),
        state_tangent_action_free_n_per_m=(
            lambda displacement, load_factor, direction: np.zeros(2)
        ),
        free_equation_global_dofs=free_dofs,
        residual_formula_hash=residual_formula_hash,
        current_tangent_action_contract=(
            module.MGT_CURRENT_STATE_TANGENT_ACTION_CONTRACT
        ),
        current_tangent_operator=operator,
    )
    direction = np.asarray([0.25, -0.5])

    np.testing.assert_array_equal(
        problem.consistent_state_tangent_action_kn_per_m(
            np.zeros(2),
            1.0,
            direction,
        ),
        matrix @ direction / 1000.0,
    )
    binding = problem.matrix_free_current_tangent_operator_binding()
    assert binding is not None
    assert binding["current_tangent_operator_profile"] == (
        CURRENT_TANGENT_OPERATOR_PROFILE
    )
    assert binding["current_tangent_operator_contract_hash"] == (operator.contract_hash)
    assert binding["current_tangent_operator_array_bundle_hash"] == (
        operator.array_bundle_hash
    )
    assert binding["operator_callback_reference_evaluator"] == (
        CURRENT_TANGENT_OPERATOR_REFERENCE_EVALUATOR
    )
    assert binding["operator_callback_outputs_in_contract"] is True
    assert problem.zero_state_problem().current_tangent_operator is operator


def test_matrix_free_operator_binding_fails_closed_when_partial() -> None:
    with pytest.raises(
        ValueError,
        match="requires a free equation order",
    ):
        module.LoadCoupledArcLengthCallbackProblem(
            case_id="partial_matrix_free_binding",
            initial_displacements_m=np.zeros(2),
            initial_factor=0.0,
            reference_load_free_n=np.ones(2),
            residual_free_n=lambda displacement, load_factor: displacement,
            negative_load_derivative_free_n=(
                lambda displacement, load_factor: np.ones(2)
            ),
            residual_formula_hash="sha256:" + "4" * 64,
        )


def test_parser_report_summary_discards_volatile_paths_and_time() -> None:
    payload = module._stable_parser_report_summary(
        {
            "schema_version": "1.1",
            "generated_at": "volatile",
            "inputs": {"npz_out": "/tmp/volatile.npz"},
            "contract_pass": True,
            "reason_code": "PASS",
            "metrics": {"node_count": 13_047, "runtime_seconds": 99.0},
            "checks": {"has_nodes": True, "future_check": True},
            "coarsening": {"applied": False, "future_field": "volatile"},
        }
    )

    assert payload == {
        "schema_version": "1.1",
        "contract_pass": True,
        "reason_code": "PASS",
        "metrics": {"node_count": 13_047},
        "checks": {"has_nodes": True},
        "coarsening": {"applied": False},
    }


def test_roundtrip_json_hash_discards_only_generated_at_fields() -> None:
    first = {
        "generated_at": "first",
        "model": {
            "nodes": [{"id": 1}],
            "audit": {"generated_at": "nested-first"},
        },
    }
    second = {
        "generated_at": "second",
        "model": {
            "nodes": [{"id": 1}],
            "audit": {"generated_at": "nested-second"},
        },
    }

    first_hash = module._canonical_json_hash_without_generated_at(first)

    assert first_hash == module._canonical_json_hash_without_generated_at(second)
    second["model"]["nodes"] = [{"id": 2}]
    assert first_hash != module._canonical_json_hash_without_generated_at(second)


def test_real_builder_fails_closed_when_inputs_are_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="mgt_path is missing"):
        module.build_real_mgt_load_coupled_arc_length_problem(
            mgt_path=tmp_path / "missing.mgt",
            roundtrip_npz=tmp_path / "missing.roundtrip.npz",
            checkpoint_npz=tmp_path / "missing-checkpoint.npz",
        )
