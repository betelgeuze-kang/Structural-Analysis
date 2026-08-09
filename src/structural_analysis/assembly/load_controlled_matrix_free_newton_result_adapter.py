"""Internal N1 terminal adapter for ``NonlinearNumericalResultIR``.

The load-controlled solver does not own ModelIR, equation-scaling, reduced-CSR,
material-bundle, or boundary-condition identities.  Callers must therefore
supply those exact hashes.  This adapter refuses to invent them and only emits
a ResultIR after replaying a durable terminal checkpoint and every numerical
terminal gate.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Any, Literal

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.nonlinear_result import (
    NonlinearNumericalResultIR,
    NonlinearNumericalResultSourceSnapshot,
    create_adapter_bound_nonlinear_numerical_result_ir,
    validate_nonlinear_numerical_result_ir,
)
from structural_analysis.solvers.nonlinear.load_controlled_matrix_free_newton import (
    LOAD_CONTROLLED_MATRIX_FREE_NEWTON_SCHEMA_VERSION,
    LoadControlledMatrixFreeNewtonResult,
)
from structural_analysis.solvers.nonlinear.load_controlled_matrix_free_newton_checkpoint_io import (
    read_load_controlled_matrix_free_newton_checkpoint_artifact,
)


N1_LOAD_CONTROLLED_MATRIX_FREE_RESULT_ADAPTER_SCHEMA_VERSION = (
    "n1-load-controlled-matrix-free-result-adapter.v1"
)
N1_LOAD_CONTROLLED_MATRIX_FREE_RESULT_AUTHORITY_PROFILE = (
    "n1-terminal-cpu-six-dof-numerical-state.v1"
)
N1_LOAD_CONTROLLED_MATRIX_FREE_RESULT_CLAIM_BOUNDARY = {
    "target_load_factor_1p0": True,
    "physical_residual_gate": True,
    "increment_gate": True,
    "committed_checkpoint_replayed": True,
    "fallback_zero": True,
    "regularization_zero": True,
    "canonical_six_dof_order_explicit": True,
    "model_plan_scaling_csr_bindings_explicit": True,
    "durable_checkpoint_bytes_bound": True,
    "material_state_history_authority": False,
    "reaction_authority": False,
    "member_force_authority": False,
    "engineering_result_authority": False,
    "g1_production_authority": False,
    "release_readiness": False,
}

_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class N1LoadControlledMatrixFreeResultAdapterError(ValueError):
    """Raised when an N1 terminal result cannot support ResultIR."""


def _hash(value: Any, *, field: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        raise N1LoadControlledMatrixFreeResultAdapterError(
            f"{field} must be a sha256 digest"
        )
    return value


def _finite_number(
    value: Any,
    *,
    field: str,
    nonnegative: bool = False,
) -> float:
    if type(value) not in (int, float):
        raise N1LoadControlledMatrixFreeResultAdapterError(
            f"{field} must be a finite numeric value"
        )
    result = float(value)
    if not math.isfinite(result) or (nonnegative and result < 0.0):
        raise N1LoadControlledMatrixFreeResultAdapterError(
            f"{field} must be a finite numeric value"
        )
    return result


def n1_free_global_dof_order_hash(
    *,
    global_dof_count: int,
    free_global_dofs: tuple[int, ...],
) -> str:
    """Bind ordered reduced equations to canonical global six-DOF indices."""

    if (
        type(global_dof_count) is not int
        or global_dof_count < 6
        or global_dof_count % 6 != 0
    ):
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "global_dof_count must be a positive canonical six-DOF cardinality"
        )
    if type(free_global_dofs) is not tuple or not free_global_dofs:
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "free_global_dofs must be a non-empty exact tuple"
        )
    if any(type(value) is not int for value in free_global_dofs):
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "free_global_dofs must contain exact integer indices"
        )
    if (
        len(set(free_global_dofs)) != len(free_global_dofs)
        or min(free_global_dofs) < 0
        or max(free_global_dofs) >= global_dof_count
    ):
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "free_global_dofs must be unique indices inside global_dof_count"
        )
    ordered = np.asarray(free_global_dofs, dtype="<i8")
    return canonical_hash(
        {
            "profile": "ordered-free-to-global-six-dof-map.v1",
            "global_dof_count": global_dof_count,
            "free_dof_count": len(free_global_dofs),
            "free_global_dof_order_data_hash": array_data_hash(ordered),
        }
    )


@dataclass(frozen=True)
class N1LoadControlledMatrixFreeResultBinding:
    """Explicit identities that the numerical continuation does not own."""

    model_ir_content_hash: str
    execution_plan_hash: str
    equation_scaling_hash: str
    reduced_csr_identity_hash: str
    material_state_bundle_hash: str
    integration_point_order_hash: str
    boundary_condition_receipt_hash: str
    backend_receipt_hash: str
    global_dof_count: int
    free_global_dofs: tuple[int, ...]
    free_global_dof_order_hash: str
    backend_role: Literal["cpu_reference", "cpu_optimized"] = "cpu_reference"
    canonical_six_dof_order: bool = True
    prescribed_displacement_profile: str = "zero_prescribed_global_dofs.v1"

    def __post_init__(self) -> None:
        for field in (
            "model_ir_content_hash",
            "execution_plan_hash",
            "equation_scaling_hash",
            "reduced_csr_identity_hash",
            "material_state_bundle_hash",
            "integration_point_order_hash",
            "boundary_condition_receipt_hash",
            "backend_receipt_hash",
        ):
            _hash(getattr(self, field), field=field)
        if self.backend_role not in {"cpu_reference", "cpu_optimized"}:
            raise N1LoadControlledMatrixFreeResultAdapterError(
                "N1 CPU adapter backend_role must be a CPU role"
            )
        if self.canonical_six_dof_order is not True:
            raise N1LoadControlledMatrixFreeResultAdapterError(
                "canonical six-DOF global node order must be explicit"
            )
        expected_order_hash = n1_free_global_dof_order_hash(
            global_dof_count=self.global_dof_count,
            free_global_dofs=self.free_global_dofs,
        )
        if self.free_global_dof_order_hash != expected_order_hash:
            raise N1LoadControlledMatrixFreeResultAdapterError(
                "free_global_dof_order_hash does not match the ordered map"
            )
        if self.prescribed_displacement_profile != "zero_prescribed_global_dofs.v1":
            raise N1LoadControlledMatrixFreeResultAdapterError(
                "N1 ResultIR only supports an explicit zero prescribed base"
            )


def _source_replay_hash(result: LoadControlledMatrixFreeNewtonResult) -> str:
    return canonical_hash(result.to_dict())


def _terminal_row(result: LoadControlledMatrixFreeNewtonResult) -> dict[str, Any]:
    accepted = [row for row in result.attempts if row.get("accepted") is True]
    if not accepted:
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "terminal result contains no committed attempt"
        )
    attempt = accepted[-1]
    history = attempt.get("history")
    if type(history) is not list or not history or type(history[-1]) is not dict:
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "terminal committed attempt history is invalid"
        )
    if attempt.get("accepted_state_hash_after") != result.final_checkpoint.state_hash:
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "terminal committed attempt is detached from the final checkpoint"
        )
    return dict(history[-1])


def _terminal_projection(
    result: LoadControlledMatrixFreeNewtonResult,
) -> dict[str, Any]:
    if type(result) is not LoadControlledMatrixFreeNewtonResult:
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "exact LoadControlledMatrixFreeNewtonResult type required"
        )
    metrics = result.metrics
    if (
        result.status != "ready"
        or result.terminal_reason != "target_load_factor_reached"
        or metrics.get("contract_pass") is not True
        or metrics.get("target_load_factor_reached") is not True
    ):
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "only a ready target-reached continuation can create ResultIR"
        )
    target_load_factor = _finite_number(
        metrics.get("target_load_factor"),
        field="metrics.target_load_factor",
    )
    final_load_factor = _finite_number(
        metrics.get("final_load_factor"),
        field="metrics.final_load_factor",
    )
    checkpoint_load_factor = _finite_number(
        result.final_checkpoint.load_factor,
        field="final_checkpoint.load_factor",
    )
    if (
        target_load_factor != 1.0
        or final_load_factor != 1.0
        or checkpoint_load_factor != 1.0
    ):
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "N1 ResultIR requires exact target and final load factor 1.0"
        )
    if not result.checkpoints or (
        result.checkpoints[-1].state_hash != result.final_checkpoint.state_hash
    ):
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "final checkpoint is not the committed path terminal"
        )
    if (
        type(result.final_checkpoint.step_index) is not int
        or result.final_checkpoint.step_index < 1
    ):
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "terminal checkpoint must have a positive committed epoch"
        )
    equation_count = metrics.get("equation_count")
    if (
        type(equation_count) is not int
        or equation_count < 1
        or (result.final_checkpoint.free_displacements_m.size != equation_count)
    ):
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "terminal free-equation cardinality is invalid"
        )
    final_residual = _finite_number(
        metrics.get("final_residual_inf_kn"),
        field="metrics.final_residual_inf_kn",
        nonnegative=True,
    )
    if final_residual > result.config.residual_tolerance_inf_kn:
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "physical residual gate did not pass"
        )
    terminal = _terminal_row(result)
    terminal_residual = _finite_number(
        terminal.get("residual_inf_kn"),
        field="terminal.residual_inf_kn",
        nonnegative=True,
    )
    terminal_increment = _finite_number(
        terminal.get("last_increment_inf_m"),
        field="terminal.last_increment_inf_m",
        nonnegative=True,
    )
    terminal_relative_increment = _finite_number(
        terminal.get("last_relative_increment"),
        field="terminal.last_relative_increment",
        nonnegative=True,
    )
    if (
        terminal.get("convergence_gate_passed") is not True
        or terminal.get("residual_gate_passed") is not True
        or terminal.get("increment_gate_passed") is not True
        or metrics.get("residual_and_increment_acceptance_gate") is not True
    ):
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "residual-plus-increment terminal gate did not pass"
        )
    if (
        terminal_residual != final_residual
        or terminal_residual > result.config.residual_tolerance_inf_kn
        or (
            terminal_increment > result.config.increment_absolute_tolerance_inf_m
            and terminal_relative_increment > result.config.increment_relative_tolerance
        )
    ):
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "terminal residual/increment numeric gate did not pass"
        )
    fallback_count = metrics.get("fallback_count")
    regularization_count = metrics.get("regularization_count")
    if type(fallback_count) is not int or fallback_count != 0:
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "fallback_count must be exact integer zero"
        )
    if type(regularization_count) is not int or regularization_count != 0:
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "regularization_count must be exact integer zero"
        )
    if any(
        row.get("accepted") is False and row.get("rollback_exact") is not True
        for row in result.attempts
    ):
        raise N1LoadControlledMatrixFreeResultAdapterError(
            "a rejected trial lacks exact checkpoint rollback"
        )
    return {
        "schema_version": N1_LOAD_CONTROLLED_MATRIX_FREE_RESULT_ADAPTER_SCHEMA_VERSION,
        "source_solver_schema_version": LOAD_CONTROLLED_MATRIX_FREE_NEWTON_SCHEMA_VERSION,
        "authority_profile": N1_LOAD_CONTROLLED_MATRIX_FREE_RESULT_AUTHORITY_PROFILE,
        "case_id": result.case_id,
        "path_contract_hash": result.path_contract_hash,
        "solver_profile": result.solver_profile,
        "solver_contract_hash": result.solver_contract_hash,
        "target_load_factor": 1.0,
        "state_hash": result.final_checkpoint.state_hash,
        "state_epoch": result.final_checkpoint.step_index,
        "equation_count": equation_count,
        "terminal": {
            "residual_inf_kn": terminal_residual,
            "residual_tolerance_inf_kn": result.config.residual_tolerance_inf_kn,
            "increment_inf_m": terminal_increment,
            "relative_increment": terminal_relative_increment,
            "absolute_increment_tolerance_inf_m": (
                result.config.increment_absolute_tolerance_inf_m
            ),
            "relative_increment_tolerance": (
                result.config.increment_relative_tolerance
            ),
            "residual_gate_passed": True,
            "increment_gate_passed": True,
            "convergence_gate_passed": True,
        },
        "fallback_count": 0,
        "regularization_count": 0,
        "claim_boundary": dict(N1_LOAD_CONTROLLED_MATRIX_FREE_RESULT_CLAIM_BOUNDARY),
    }


@dataclass(frozen=True)
class N1LoadControlledMatrixFreeResultSourceAdapter:
    source_result: LoadControlledMatrixFreeNewtonResult
    binding: N1LoadControlledMatrixFreeResultBinding
    checkpoint_descriptor_path: Path
    checkpoint_descriptor_hash: str
    source_replay_hash: str

    def validate_nonlinear_result_source(
        self,
    ) -> NonlinearNumericalResultSourceSnapshot:
        projection = _terminal_projection(self.source_result)
        if len(self.binding.free_global_dofs) != projection["equation_count"]:
            raise N1LoadControlledMatrixFreeResultAdapterError(
                "free_global_dofs cardinality differs from the reduced equations"
            )
        if _source_replay_hash(self.source_result) != self.source_replay_hash:
            raise N1LoadControlledMatrixFreeResultAdapterError(
                "retained solver result changed after adapter creation"
            )
        durable = read_load_controlled_matrix_free_newton_checkpoint_artifact(
            self.checkpoint_descriptor_path,
            expected_case_id=self.source_result.case_id,
            expected_path_contract_hash=self.source_result.path_contract_hash,
            expected_equation_count=int(projection["equation_count"]),
        )
        if durable.descriptor_hash != self.checkpoint_descriptor_hash:
            raise N1LoadControlledMatrixFreeResultAdapterError(
                "durable checkpoint descriptor changed after adapter creation"
            )
        checkpoint = durable.checkpoint
        if (
            checkpoint.state_hash != self.source_result.final_checkpoint.state_hash
            or not np.array_equal(
                checkpoint.free_displacements_m,
                self.source_result.final_checkpoint.free_displacements_m,
            )
        ):
            raise N1LoadControlledMatrixFreeResultAdapterError(
                "durable checkpoint is detached from the terminal solver state"
            )
        terminal = projection["terminal"]
        free_vector = np.ascontiguousarray(
            checkpoint.free_displacements_m,
            dtype="<f8",
        )
        global_vector = np.zeros(self.binding.global_dof_count, dtype="<f8")
        global_vector[np.asarray(self.binding.free_global_dofs, dtype=np.int64)] = (
            free_vector
        )
        global_raw = global_vector.tobytes(order="C")
        displacement = immutable_array(
            np.frombuffer(global_raw, dtype="<f8"), dtype="<f8"
        )
        global_state_hash = canonical_hash(
            {
                "profile": "n1-global-six-dof-terminal-state.v1",
                "checkpoint_state_hash": projection["state_hash"],
                "free_global_dof_order_hash": (self.binding.free_global_dof_order_hash),
                "global_displacement_data_hash": array_data_hash(displacement),
                "prescribed_displacement_profile": (
                    self.binding.prescribed_displacement_profile
                ),
            }
        )
        path_history_hash = canonical_hash(
            {
                "profile": "n1-terminal-path-state.v1",
                "case_id": projection["case_id"],
                "path_contract_hash": projection["path_contract_hash"],
                "target_load_factor": 1.0,
                "state_epoch": projection["state_epoch"],
                "checkpoint_state_hash": projection["state_hash"],
                "global_state_hash": global_state_hash,
                "free_global_dof_order_hash": (self.binding.free_global_dof_order_hash),
            }
        )
        terminal_hash = canonical_hash(
            {
                "profile": "n1-terminal-residual-increment-gate.v1",
                "path_history_hash": path_history_hash,
                "terminal": terminal,
                "fallback_count": 0,
                "regularization_count": 0,
            }
        )
        residual_receipt_hash = canonical_hash(
            {
                "profile": "n1-terminal-physical-residual.v1",
                "state_hash": global_state_hash,
                "residual_inf_kn": terminal["residual_inf_kn"],
                "residual_tolerance_inf_kn": terminal["residual_tolerance_inf_kn"],
                "residual_gate_passed": True,
            }
        )
        return NonlinearNumericalResultSourceSnapshot(
            model_ir_content_hash=self.binding.model_ir_content_hash,
            execution_plan_hash=self.binding.execution_plan_hash,
            equation_scaling_hash=self.binding.equation_scaling_hash,
            reduced_csr_identity_hash=self.binding.reduced_csr_identity_hash,
            operator_hash=_hash(
                projection["solver_contract_hash"], field="solver_contract_hash"
            ),
            state_hash=global_state_hash,
            state_epoch=projection["state_epoch"],
            material_state_bundle_hash=self.binding.material_state_bundle_hash,
            integration_point_order_hash=self.binding.integration_point_order_hash,
            path_history_hash=path_history_hash,
            nonlinear_terminal_hash=terminal_hash,
            full_residual_receipt_hash=residual_receipt_hash,
            boundary_condition_receipt_hash=(
                self.binding.boundary_condition_receipt_hash
            ),
            backend_role=self.binding.backend_role,
            backend_receipt_hash=self.binding.backend_receipt_hash,
            load_factor=1.0,
            time_s=0.0,
            dof_count=self.binding.global_dof_count,
            displacement_global_si=displacement,
        )


@dataclass(frozen=True)
class N1LoadControlledMatrixFreeNumericalResult:
    source_adapter: N1LoadControlledMatrixFreeResultSourceAdapter
    numerical_result: NonlinearNumericalResultIR

    def validate(self) -> NonlinearNumericalResultIR:
        return validate_nonlinear_numerical_result_ir(self.numerical_result)


def create_n1_load_controlled_matrix_free_numerical_result(
    *,
    result_id: str,
    source_result: LoadControlledMatrixFreeNewtonResult,
    binding: N1LoadControlledMatrixFreeResultBinding,
    checkpoint_descriptor_path: str | Path,
) -> N1LoadControlledMatrixFreeNumericalResult:
    """Create a retained-source ResultIR after replaying all N1 terminal gates."""

    _terminal_projection(source_result)
    descriptor_path = Path(checkpoint_descriptor_path)
    durable = read_load_controlled_matrix_free_newton_checkpoint_artifact(
        descriptor_path,
        expected_case_id=source_result.case_id,
        expected_path_contract_hash=source_result.path_contract_hash,
        expected_equation_count=int(source_result.metrics["equation_count"]),
    )
    adapter = N1LoadControlledMatrixFreeResultSourceAdapter(
        source_result=source_result,
        binding=binding,
        checkpoint_descriptor_path=descriptor_path,
        checkpoint_descriptor_hash=durable.descriptor_hash,
        source_replay_hash=_source_replay_hash(source_result),
    )
    numerical_result = create_adapter_bound_nonlinear_numerical_result_ir(
        result_id=result_id,
        source_adapter=adapter,
    )
    return N1LoadControlledMatrixFreeNumericalResult(
        source_adapter=adapter,
        numerical_result=numerical_result,
    )


__all__ = [
    "N1_LOAD_CONTROLLED_MATRIX_FREE_RESULT_ADAPTER_SCHEMA_VERSION",
    "N1_LOAD_CONTROLLED_MATRIX_FREE_RESULT_AUTHORITY_PROFILE",
    "N1_LOAD_CONTROLLED_MATRIX_FREE_RESULT_CLAIM_BOUNDARY",
    "N1LoadControlledMatrixFreeNumericalResult",
    "N1LoadControlledMatrixFreeResultAdapterError",
    "N1LoadControlledMatrixFreeResultBinding",
    "N1LoadControlledMatrixFreeResultSourceAdapter",
    "create_n1_load_controlled_matrix_free_numerical_result",
    "n1_free_global_dof_order_hash",
]
