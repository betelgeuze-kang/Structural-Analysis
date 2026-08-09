from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import sys

import numpy as np
import pytest
from scipy.sparse import csr_matrix


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


from structural_analysis.assembly.load_controlled_matrix_free_newton_result_adapter import (  # noqa: E402
    N1LoadControlledMatrixFreeResultAdapterError,
    N1LoadControlledMatrixFreeResultBinding,
    create_n1_load_controlled_matrix_free_numerical_result,
    n1_free_global_dof_order_hash,
)
from structural_analysis.engine_v2.contracts.nonlinear_result import (  # noqa: E402
    validate_nonlinear_numerical_result_ir,
)
from structural_analysis.solvers.nonlinear.load_controlled_matrix_free_newton import (  # noqa: E402
    LoadControlledMatrixFreeNewtonConfig,
    load_controlled_matrix_free_newton_continuation,
)
from structural_analysis.solvers.nonlinear.load_controlled_matrix_free_newton_checkpoint_io import (  # noqa: E402
    write_load_controlled_matrix_free_newton_checkpoint_artifact,
)
from structural_analysis.solvers.nonlinear.matrix_free_fgmres import (  # noqa: E402
    MatrixFreeCPUFGMRESConfig,
    create_matrix_free_cpu_fgmres_state_tangent_solver,
)


def _digest(character: str) -> str:
    return "sha256:" + character * 64


@dataclass
class _SixDofLinearProblem:
    diagonal_kn_per_m: np.ndarray
    load_kn: np.ndarray
    case_id: str = "n1-result-ir-six-dof"
    reference_preconditioner_contract: str = "n1-result-ir-diagonal-reference.v1"

    @property
    def equation_count(self) -> int:
        return 6

    def initial_free_displacements_m(self) -> np.ndarray:
        return np.zeros(6, dtype=np.float64)

    def initial_load_factor(self) -> float:
        return 0.0

    def reference_load_kn(self) -> np.ndarray:
        return self.load_kn.copy()

    def full_unit_zero_state_predictor_free_m(self) -> np.ndarray:
        return self.load_kn / self.diagonal_kn_per_m

    def reference_preconditioner_free_csr_n_per_m(self) -> csr_matrix:
        return csr_matrix(np.diag(self.diagonal_kn_per_m * 1000.0))

    def residual_kn(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
    ) -> np.ndarray:
        return (
            self.diagonal_kn_per_m * np.asarray(free_displacements_m)
            - float(load_factor) * self.load_kn
        )

    def negative_load_derivative_kn(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
    ) -> np.ndarray:
        del free_displacements_m, load_factor
        return self.load_kn.copy()

    def consistent_state_tangent_action_kn_per_m(
        self,
        free_displacements_m: np.ndarray,
        load_factor: float,
        direction_m: np.ndarray,
    ) -> np.ndarray:
        del free_displacements_m, load_factor
        return self.diagonal_kn_per_m * np.asarray(direction_m)


def _problem() -> _SixDofLinearProblem:
    return _SixDofLinearProblem(
        diagonal_kn_per_m=np.asarray([10.0, 12.0, 14.0, 16.0, 18.0, 20.0]),
        load_kn=np.asarray([1.0, -0.5, 0.25, 0.1, -0.2, 0.3]),
    )


def _solver(problem: _SixDofLinearProblem):
    return create_matrix_free_cpu_fgmres_state_tangent_solver(
        problem,
        config=MatrixFreeCPUFGMRESConfig(
            max_iterations=8,
            restart_length=6,
            relative_tolerance_l2=1.0e-12,
            absolute_tolerance_l2_kn=1.0e-14,
            explicit_residual_tolerance_inf_kn=1.0e-12,
        ),
    )


def _config() -> LoadControlledMatrixFreeNewtonConfig:
    return LoadControlledMatrixFreeNewtonConfig(
        target_load_factors=(0.5, 1.0),
        residual_tolerance_inf_kn=1.0e-12,
        increment_absolute_tolerance_inf_m=1.0e-12,
        increment_relative_tolerance=1.0e-10,
        tangent_solve_residual_tolerance_inf_kn=1.0e-12,
        maximum_newton_iterations=3,
    )


def _binding() -> N1LoadControlledMatrixFreeResultBinding:
    free_global_dofs = (7, 0, 11, 3, 9, 4)
    return N1LoadControlledMatrixFreeResultBinding(
        model_ir_content_hash=_digest("1"),
        execution_plan_hash=_digest("2"),
        equation_scaling_hash=_digest("3"),
        reduced_csr_identity_hash=_digest("4"),
        material_state_bundle_hash=_digest("5"),
        integration_point_order_hash=_digest("6"),
        boundary_condition_receipt_hash=_digest("7"),
        backend_receipt_hash=_digest("8"),
        global_dof_count=12,
        free_global_dofs=free_global_dofs,
        free_global_dof_order_hash=n1_free_global_dof_order_hash(
            global_dof_count=12,
            free_global_dofs=free_global_dofs,
        ),
    )


def _solve_pair():
    problem = _problem()
    solver = _solver(problem)
    config = _config()
    one_shot = load_controlled_matrix_free_newton_continuation(
        problem,
        solver,
        config=config,
    )
    midpoint = next(row for row in one_shot.checkpoints if row.load_factor == 0.5)
    restarted = load_controlled_matrix_free_newton_continuation(
        problem,
        solver,
        config=config,
        checkpoint=midpoint,
    )
    assert one_shot.status == restarted.status == "ready"
    return one_shot, restarted


def _create(result, target: Path, *, result_id: str = "n1.terminal.cpu"):
    durable = write_load_controlled_matrix_free_newton_checkpoint_artifact(
        result.final_checkpoint,
        target,
    )
    return create_n1_load_controlled_matrix_free_numerical_result(
        result_id=result_id,
        source_result=result,
        binding=_binding(),
        checkpoint_descriptor_path=durable.descriptor_path,
    )


def test_one_shot_and_restart_emit_identical_terminal_result_ir(
    tmp_path: Path,
) -> None:
    one_shot, restarted = _solve_pair()
    first = _create(one_shot, tmp_path / "one-shot.json")
    second = _create(restarted, tmp_path / "restarted.json")

    assert first.validate().result_hash == second.validate().result_hash
    assert first.numerical_result.to_manifest() == (
        second.numerical_result.to_manifest()
    )
    assert first.numerical_result.load_factor == 1.0
    assert first.numerical_result.backend_role == "cpu_reference"
    assert first.numerical_result.state_hash != one_shot.final_checkpoint.state_hash
    expected_global = np.zeros(12, dtype=np.float64)
    expected_global[np.asarray(_binding().free_global_dofs)] = (
        one_shot.final_free_displacements_m
    )
    np.testing.assert_array_equal(
        first.numerical_result.displacement_global_si, expected_global
    )
    assert first.numerical_result.dof_count == 12


def test_retained_result_ir_rejects_checkpoint_byte_tamper(tmp_path: Path) -> None:
    one_shot, _ = _solve_pair()
    wrapped = _create(one_shot, tmp_path / "terminal.json")
    vector_path = tmp_path / "terminal.f64le"
    raw = bytearray(vector_path.read_bytes())
    raw[-1] ^= 1
    vector_path.write_bytes(raw)

    with pytest.raises(Exception, match="data_hash mismatch"):
        validate_nonlinear_numerical_result_ir(wrapped.numerical_result)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("status", "blocked", "ready target-reached"),
        ("terminal_reason", "step_failed", "ready target-reached"),
    ),
)
def test_partial_or_rejected_terminal_result_cannot_create_result_ir(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    one_shot, _ = _solve_pair()
    rejected = replace(one_shot, **{field: value})
    durable = write_load_controlled_matrix_free_newton_checkpoint_artifact(
        one_shot.final_checkpoint,
        tmp_path / f"{field}.json",
    )
    with pytest.raises(N1LoadControlledMatrixFreeResultAdapterError, match=message):
        create_n1_load_controlled_matrix_free_numerical_result(
            result_id="n1.rejected.cpu",
            source_result=rejected,
            binding=_binding(),
            checkpoint_descriptor_path=durable.descriptor_path,
        )


@pytest.mark.parametrize("field", ("fallback_count", "regularization_count"))
def test_solver_escape_counts_cannot_create_result_ir(
    tmp_path: Path,
    field: str,
) -> None:
    one_shot, _ = _solve_pair()
    metrics = dict(one_shot.metrics)
    metrics[field] = 1
    escaped = replace(one_shot, metrics=metrics)
    durable = write_load_controlled_matrix_free_newton_checkpoint_artifact(
        one_shot.final_checkpoint,
        tmp_path / f"{field}.json",
    )
    with pytest.raises(N1LoadControlledMatrixFreeResultAdapterError, match=field):
        create_n1_load_controlled_matrix_free_numerical_result(
            result_id="n1.escape.cpu",
            source_result=escaped,
            binding=_binding(),
            checkpoint_descriptor_path=durable.descriptor_path,
        )


def test_explicit_binding_and_six_dof_order_fail_closed(tmp_path: Path) -> None:
    one_shot, _ = _solve_pair()
    with pytest.raises(
        N1LoadControlledMatrixFreeResultAdapterError,
        match="six-DOF",
    ):
        replace(_binding(), canonical_six_dof_order=False)
    with pytest.raises(
        N1LoadControlledMatrixFreeResultAdapterError,
        match="sha256",
    ):
        replace(_binding(), model_ir_content_hash="detached")
    with pytest.raises(
        N1LoadControlledMatrixFreeResultAdapterError,
        match="order_hash",
    ):
        replace(
            _binding(),
            free_global_dofs=(0, 7, 11, 3, 9, 4),
        )

    detached = replace(
        one_shot,
        final_checkpoint=one_shot.checkpoints[-2],
    )
    durable = write_load_controlled_matrix_free_newton_checkpoint_artifact(
        one_shot.checkpoints[-2],
        tmp_path / "detached.json",
    )
    with pytest.raises(
        N1LoadControlledMatrixFreeResultAdapterError,
        match="load factor 1.0",
    ):
        create_n1_load_controlled_matrix_free_numerical_result(
            result_id="n1.detached.cpu",
            source_result=detached,
            binding=_binding(),
            checkpoint_descriptor_path=durable.descriptor_path,
        )
