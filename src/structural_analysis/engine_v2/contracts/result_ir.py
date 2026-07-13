"""Immutable ResultIR v1 receipts for Phase 0 linear-static verification.

The CPU reference result hash remains backend-native evidence.  ResultIR adds a
portable, aggregate receipt that binds every numerical artifact to the model,
compiled execution plan, evaluated trial state, committed state, tolerance,
and backend execution metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import metadata
import json
import math
from pathlib import Path
import platform
from typing import Any, Literal, Mapping

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.backends.cpu_reference.linear_static import (
    CPU_REFERENCE_OPERATOR_VERSION,
    LinearStaticResult,
)
from structural_analysis.engine_v2.buffers import DOF_ORDER, SolverModelBuffers

from ._canonical import canonical_hash, has_immutable_bytes_backing, raw_array_hash

RESULT_IR_SCHEMA_VERSION = "structural-analysis-result-ir.v1"
_MATRIX_BACKENDS = ("dense", "scipy_sparse")
_FORCE_UNITS = ("N", "N", "N", "N*m", "N*m", "N*m")
_KINEMATIC_UNITS = ("m", "m", "m", "rad", "rad", "rad")
_ARRAY_NAMES = (
    "displacements_si",
    "residual_si",
    "reactions_si",
    "element_end_forces_local_si",
    "element_strain_energy_j",
)


class ResultIRValidationError(ValueError):
    """Fail-closed ResultIR contract or physical-invariant violation."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class ArrayArtifact:
    """One immutable, little-endian FP64 ResultIR array artifact."""

    name: str
    dtype: str
    shape: tuple[int, ...]
    layout: str
    axis_labels: tuple[str, ...]
    component_labels: tuple[str, ...]
    component_units: tuple[str, ...]
    byte_length: int
    data_hash: str
    content_hash: str
    _values: np.ndarray

    @property
    def values(self) -> np.ndarray:
        return self._values

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "layout": self.layout,
            "axis_labels": list(self.axis_labels),
            "component_labels": list(self.component_labels),
            "component_units": list(self.component_units),
            "byte_length": self.byte_length,
            "data_hash": self.data_hash,
            "content_hash": self.content_hash,
            "values": self._values.tolist(),
        }


@dataclass(frozen=True)
class InputBindings:
    model_ir_content_hash: str
    solver_numeric_buffer_hash: str
    solver_entity_mapping_hash: str
    solver_artifact_hash: str
    execution_plan_hash: str
    evaluated_trial_state_hash: str
    committed_state_hash: str

    def to_dict(self) -> dict[str, str]:
        return {
            "model_ir_content_hash": self.model_ir_content_hash,
            "solver_numeric_buffer_hash": self.solver_numeric_buffer_hash,
            "solver_entity_mapping_hash": self.solver_entity_mapping_hash,
            "solver_artifact_hash": self.solver_artifact_hash,
            "execution_plan_hash": self.execution_plan_hash,
            "evaluated_trial_state_hash": self.evaluated_trial_state_hash,
            "committed_state_hash": self.committed_state_hash,
        }


@dataclass(frozen=True)
class AnalysisReceipt:
    load_pattern_id: str
    operator_hash: str
    recovery_operator_hash: str
    backend_native_result_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "linear_static",
            "status": "ready",
            "load_pattern_id": self.load_pattern_id,
            "residual_sign": "internal_minus_external",
            "operator_version": CPU_REFERENCE_OPERATOR_VERSION,
            "operator_hash": self.operator_hash,
            "recovery_operator_hash": self.recovery_operator_hash,
            "backend_native_result_hash": self.backend_native_result_hash,
        }


@dataclass(frozen=True)
class ResultOrdering:
    node_ids: tuple[str, ...]
    element_ids: tuple[str, ...]
    ordering_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_ids": list(self.node_ids),
            "element_ids": list(self.element_ids),
            "dof_components": list(DOF_ORDER),
            "element_end_order": ["i", "j"],
            "component_units": list(_FORCE_UNITS),
            "ordering_hash": self.ordering_hash,
        }


@dataclass(frozen=True)
class ResultArrays:
    displacements_si: ArrayArtifact
    residual_si: ArrayArtifact
    reactions_si: ArrayArtifact
    element_end_forces_local_si: ArrayArtifact
    element_strain_energy_j: ArrayArtifact

    def ordered(self) -> tuple[ArrayArtifact, ...]:
        return tuple(getattr(self, name) for name in _ARRAY_NAMES)

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {artifact.name: artifact.to_dict() for artifact in self.ordered()}


@dataclass(frozen=True)
class ConvergenceReceipt:
    requested_residual_tolerance: float
    free_residual_linf: float
    load_scale: float
    scaled_free_residual: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "converged": True,
            "requested_residual_tolerance": self.requested_residual_tolerance,
            "free_residual_linf": self.free_residual_linf,
            "load_scale": self.load_scale,
            "scaled_free_residual": self.scaled_free_residual,
            "solve_attempts": 1,
            "failure_code": None,
        }


@dataclass(frozen=True)
class HardwareReceipt:
    platform: str
    machine: str
    processor: str

    def to_dict(self) -> dict[str, str]:
        return {
            "platform": self.platform,
            "machine": self.machine,
            "processor": self.processor,
        }


@dataclass(frozen=True)
class BackendReceipt:
    matrix_backend: Literal["dense", "scipy_sparse"]
    numpy_version: str
    scipy_version: str | None
    hardware: HardwareReceipt

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_backend": "cpu_reference",
            "actual_backend": "cpu_reference",
            "matrix_backend": self.matrix_backend,
            "precision": "fp64",
            "deterministic": True,
            "fallback_policy": "forbidden",
            "fallback_used": False,
            "fallback_events": [],
            "numpy_version": self.numpy_version,
            "scipy_version": self.scipy_version,
            "hardware": self.hardware.to_dict(),
            "h2d_bytes": 0,
            "d2h_bytes": 0,
            "device_sync_count": 0,
            "timing": {
                "measurement_status": "not_instrumented",
                "clock": "not_available",
                "total_wall_time_s": None,
                "stage_wall_time_s": {
                    "assembly": None,
                    "constraint_partition": None,
                    "linear_solve": None,
                    "residual": None,
                    "reaction": None,
                    "result_recovery": None,
                    "energy": None,
                },
            },
            "peak_memory": {
                "measurement_status": "not_instrumented",
                "peak_host_bytes": None,
                "peak_device_bytes": 0,
            },
        }


@dataclass(frozen=True)
class ResultIR:
    """A successful immutable ResultIR v1 receipt."""

    result_id: str
    input_bindings: InputBindings
    analysis: AnalysisReceipt
    ordering: ResultOrdering
    arrays: ResultArrays
    total_strain_energy_j: float
    convergence: ConvergenceReceipt
    backend_receipt: BackendReceipt
    numerical_result_hash: str
    result_ir_hash: str

    @property
    def schema_version(self) -> str:
        return RESULT_IR_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capability_profile": "phase0_cpu_reference_linear_static",
            "result_id": self.result_id,
            "input_bindings": self.input_bindings.to_dict(),
            "analysis": self.analysis.to_dict(),
            "ordering": self.ordering.to_dict(),
            "arrays": self.arrays.to_dict(),
            "total_strain_energy_j": self.total_strain_energy_j,
            "convergence": self.convergence.to_dict(),
            "recovery": {
                "local_frame_convention": (
                    "engine_v2_frame_local_x_i_to_j_right_handed_v1"
                ),
                "end_force_order": (
                    "element_i_then_j_local_ux_uy_uz_rx_ry_rz"
                ),
                "reaction_definition": (
                    "full_residual_on_restrained_dofs_zero_elsewhere"
                ),
                "energy_definition": "half_local_u_transpose_k_local_u",
                "constitutive_source": (
                    "solver_model_buffers_linear_elastic_isotropic"
                ),
            },
            "backend_receipt": self.backend_receipt.to_dict(),
            "numerical_result_hash": self.numerical_result_hash,
            "result_ir_hash": self.result_ir_hash,
            "extensions": {},
        }

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


def build_result_ir(
    buffers: SolverModelBuffers,
    plan: Any,
    evaluated_trial_state: Any,
    committed_state: Any,
    backend_result: LinearStaticResult,
    *,
    matrix_backend: Literal["dense", "scipy_sparse"],
    requested_residual_tolerance: float,
    result_id: str = "Result.linear-static",
) -> ResultIR:
    """Build and fully validate one successful CPU-reference ResultIR receipt."""

    if matrix_backend not in _MATRIX_BACKENDS:
        raise ResultIRValidationError(
            "result_ir_matrix_backend_invalid",
            "/backend_receipt/matrix_backend",
            f"Unsupported matrix backend: {matrix_backend}",
        )
    if not math.isfinite(requested_residual_tolerance) or requested_residual_tolerance <= 0.0:
        raise ResultIRValidationError(
            "result_ir_tolerance_invalid",
            "/convergence/requested_residual_tolerance",
            "Requested residual tolerance must be finite and positive.",
        )

    _validate_execution_plan_first(plan, buffers)
    _validate_state_first(evaluated_trial_state, plan)
    _validate_state_first(committed_state, plan)

    plan_payload = _contract_dict(plan, "ExecutionPlan")
    trial_payload = _contract_dict(evaluated_trial_state, "evaluated trial StateIR")
    committed_payload = _contract_dict(committed_state, "committed StateIR")

    node_ids = tuple(str(value) for value in buffers.entity_ids["nodes"])
    element_ids = tuple(str(value) for value in buffers.entity_ids["elements"])
    plan_node_ids = _plan_ids(plan, plan_payload, "node_ids")
    plan_element_ids = _plan_ids(plan, plan_payload, "element_ids")
    ordering_hash = _plan_scalar(plan, plan_payload, "ordering_hash")
    plan_hash = _plan_scalar(plan, plan_payload, "plan_hash")
    operator_hash = _plan_scalar(plan, plan_payload, "operator_hash")
    recovery_operator_hash = _plan_scalar(
        plan, plan_payload, "recovery_operator_hash"
    )
    plan_load_pattern_id = _plan_scalar(plan, plan_payload, "load_pattern_id")

    if plan_node_ids != node_ids or plan_element_ids != element_ids:
        raise ResultIRValidationError(
            "result_ir_ordering_binding_mismatch",
            "/ordering",
            "ExecutionPlan entity order does not match SolverModelBuffers.",
        )

    artifacts = ResultArrays(
        displacements_si=_make_array_artifact(
            "displacements_si",
            backend_result.displacements_si,
            axis_labels=("node", "dof"),
            component_labels=DOF_ORDER,
            component_units=_KINEMATIC_UNITS,
        ),
        residual_si=_make_array_artifact(
            "residual_si",
            backend_result.residual_si,
            axis_labels=("node", "dof"),
            component_labels=DOF_ORDER,
            component_units=_FORCE_UNITS,
        ),
        reactions_si=_make_array_artifact(
            "reactions_si",
            backend_result.reactions_si,
            axis_labels=("node", "dof"),
            component_labels=DOF_ORDER,
            component_units=_FORCE_UNITS,
        ),
        element_end_forces_local_si=_make_array_artifact(
            "element_end_forces_local_si",
            backend_result.element_end_forces_local_si,
            axis_labels=("element", "end", "dof"),
            component_labels=DOF_ORDER,
            component_units=_FORCE_UNITS,
        ),
        element_strain_energy_j=_make_array_artifact(
            "element_strain_energy_j",
            backend_result.element_strain_energy_j,
            axis_labels=("element",),
            component_labels=("strain_energy",),
            component_units=("J",),
        ),
    )
    load = _plan_array(plan, "global_load").reshape(-1)
    free = _plan_array(plan, "free_dofs").astype(np.int64, copy=False).reshape(-1)
    load_scale = max(1.0, float(np.max(np.abs(load[free]))) if free.size else 0.0)

    bindings = InputBindings(
        model_ir_content_hash=buffers.model_ir_content_hash,
        solver_numeric_buffer_hash=buffers.numeric_buffer_hash,
        solver_entity_mapping_hash=buffers.entity_mapping_hash,
        solver_artifact_hash=buffers.artifact_hash,
        execution_plan_hash=str(plan_hash),
        evaluated_trial_state_hash=str(trial_payload["state_hash"]),
        committed_state_hash=str(committed_payload["state_hash"]),
    )
    analysis = AnalysisReceipt(
        load_pattern_id=str(plan_load_pattern_id),
        operator_hash=str(operator_hash),
        recovery_operator_hash=str(recovery_operator_hash),
        backend_native_result_hash=backend_result.result_hash,
    )
    convergence = ConvergenceReceipt(
        requested_residual_tolerance=float(requested_residual_tolerance),
        free_residual_linf=float(backend_result.free_residual_linf),
        load_scale=load_scale,
        scaled_free_residual=float(backend_result.scaled_free_residual),
    )
    backend_receipt = BackendReceipt(
        matrix_backend=matrix_backend,
        numpy_version=np.__version__,
        scipy_version=_installed_version("scipy"),
        hardware=HardwareReceipt(
            platform=platform.platform() or "unknown",
            machine=platform.machine(),
            processor=platform.processor(),
        ),
    )
    numerical_hash = _numerical_result_hash(
        artifacts, float(backend_result.total_strain_energy_j)
    )
    draft = ResultIR(
        result_id=result_id,
        input_bindings=bindings,
        analysis=analysis,
        ordering=ResultOrdering(
            node_ids=node_ids,
            element_ids=element_ids,
            ordering_hash=str(ordering_hash),
        ),
        arrays=artifacts,
        total_strain_energy_j=float(backend_result.total_strain_energy_j),
        convergence=convergence,
        backend_receipt=backend_receipt,
        numerical_result_hash=numerical_hash,
        result_ir_hash="sha256:" + "0" * 64,
    )
    receipt = replace(draft, result_ir_hash=_aggregate_hash(draft))
    validate_result_ir_v1(
        receipt,
        buffers=buffers,
        plan=plan,
        evaluated_trial_state=evaluated_trial_state,
        committed_state=committed_state,
        backend_result=backend_result,
    )
    return receipt


def validate_result_ir_v1(
    receipt: ResultIR,
    *,
    buffers: SolverModelBuffers,
    plan: Any,
    evaluated_trial_state: Any,
    committed_state: Any,
    backend_result: LinearStaticResult,
) -> None:
    """Validate schema, hashes, bindings, and all Phase 0 physical invariants."""

    _validate_execution_plan_first(plan, buffers)
    _validate_state_first(evaluated_trial_state, plan)
    _validate_state_first(committed_state, plan)
    _validate_envelope(receipt)

    plan_payload = _contract_dict(plan, "ExecutionPlan")
    trial_payload = _contract_dict(evaluated_trial_state, "evaluated trial StateIR")
    committed_payload = _contract_dict(committed_state, "committed StateIR")
    _validate_roles(trial_payload, committed_payload)
    _validate_bindings(
        receipt,
        buffers,
        plan,
        plan_payload,
        trial_payload,
        committed_payload,
    )
    _validate_backend(receipt, backend_result, plan_payload, buffers)
    _validate_numerical_invariants(
        receipt,
        plan,
        evaluated_trial_state,
        committed_state,
        backend_result,
    )


def _validate_envelope(receipt: ResultIR) -> None:
    if not isinstance(receipt, ResultIR):
        raise ResultIRValidationError(
            "result_ir_type_invalid", "/", "Expected a ResultIR artifact."
        )
    payload = receipt.to_dict()
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        raise ResultIRValidationError(
            "result_ir_schema_invalid", path or "/", error.message
        )

    for artifact in receipt.arrays.ordered():
        if (
            artifact.values.dtype.str != "<f8"
            or not artifact.values.flags.c_contiguous
            or not has_immutable_bytes_backing(artifact.values)
        ):
            raise ResultIRValidationError(
                "result_ir_array_storage_invalid",
                f"/arrays/{artifact.name}/values",
                "Result arrays must be immutable bytes-backed C-order <f8 storage.",
            )
        expected = _make_array_artifact(
            artifact.name,
            artifact.values,
            axis_labels=artifact.axis_labels,
            component_labels=artifact.component_labels,
            component_units=artifact.component_units,
        )
        if (
            artifact.dtype != expected.dtype
            or artifact.shape != expected.shape
            or artifact.layout != expected.layout
            or artifact.byte_length != expected.byte_length
            or artifact.data_hash != expected.data_hash
            or artifact.content_hash != expected.content_hash
        ):
            raise ResultIRValidationError(
                "result_ir_array_artifact_hash_mismatch",
                f"/arrays/{artifact.name}",
                "Array bytes or descriptor metadata do not match their hashes.",
            )

    if not math.isfinite(receipt.total_strain_energy_j):
        raise ResultIRValidationError(
            "result_ir_non_finite",
            "/total_strain_energy_j",
            "Total strain energy must be finite.",
        )
    convergence_values = (
        receipt.convergence.requested_residual_tolerance,
        receipt.convergence.free_residual_linf,
        receipt.convergence.load_scale,
        receipt.convergence.scaled_free_residual,
    )
    if not all(math.isfinite(value) for value in convergence_values):
        raise ResultIRValidationError(
            "result_ir_non_finite",
            "/convergence",
            "Convergence scalars must be finite.",
        )
    expected_numerical_hash = _numerical_result_hash(
        receipt.arrays, receipt.total_strain_energy_j
    )
    if receipt.numerical_result_hash != expected_numerical_hash:
        raise ResultIRValidationError(
            "result_ir_numerical_hash_mismatch",
            "/numerical_result_hash",
            "Numerical result hash does not bind the five arrays and total energy.",
        )
    expected_aggregate_hash = _aggregate_hash(receipt)
    if receipt.result_ir_hash != expected_aggregate_hash:
        raise ResultIRValidationError(
            "result_ir_aggregate_hash_mismatch",
            "/result_ir_hash",
            "ResultIR aggregate hash does not match its canonical receipt payload.",
        )


def _validate_roles(
    trial_payload: Mapping[str, Any], committed_payload: Mapping[str, Any]
) -> None:
    if trial_payload.get("role") != "trial":
        raise ResultIRValidationError(
            "result_ir_trial_role_invalid",
            "/input_bindings/evaluated_trial_state_hash",
            "Evaluated state must be a trial StateIR.",
        )
    if committed_payload.get("role") != "committed":
        raise ResultIRValidationError(
            "result_ir_committed_role_invalid",
            "/input_bindings/committed_state_hash",
            "Final state must be a committed StateIR.",
        )
    if committed_payload.get("parent_state_hash") != trial_payload.get("state_hash"):
        raise ResultIRValidationError(
            "result_ir_state_lineage_mismatch",
            "/input_bindings/committed_state_hash",
            "Committed StateIR must directly descend from the evaluated trial.",
        )
    for name in ("epoch", "step", "load_factor", "time_s", "vector_hashes"):
        if committed_payload.get(name) != trial_payload.get(name):
            raise ResultIRValidationError(
                "result_ir_state_commit_mismatch",
                "/input_bindings/committed_state_hash",
                f"Committed StateIR does not preserve trial field {name!r}.",
            )


def _validate_bindings(
    receipt: ResultIR,
    buffers: SolverModelBuffers,
    plan: Any,
    plan_payload: Mapping[str, Any],
    trial_payload: Mapping[str, Any],
    committed_payload: Mapping[str, Any],
) -> None:
    expected = InputBindings(
        model_ir_content_hash=buffers.model_ir_content_hash,
        solver_numeric_buffer_hash=buffers.numeric_buffer_hash,
        solver_entity_mapping_hash=buffers.entity_mapping_hash,
        solver_artifact_hash=buffers.artifact_hash,
        execution_plan_hash=str(_plan_scalar(plan, plan_payload, "plan_hash")),
        evaluated_trial_state_hash=str(trial_payload["state_hash"]),
        committed_state_hash=str(committed_payload["state_hash"]),
    )
    if receipt.input_bindings != expected:
        raise ResultIRValidationError(
            "result_ir_input_binding_mismatch",
            "/input_bindings",
            "ResultIR input bindings do not match the supplied artifacts.",
        )

    node_ids = tuple(str(value) for value in buffers.entity_ids["nodes"])
    element_ids = tuple(str(value) for value in buffers.entity_ids["elements"])
    if receipt.ordering.node_ids != node_ids or receipt.ordering.element_ids != element_ids:
        raise ResultIRValidationError(
            "result_ir_ordering_binding_mismatch",
            "/ordering",
            "ResultIR order does not match SolverModelBuffers entity mappings.",
        )
    if receipt.ordering.node_ids != _plan_ids(plan, plan_payload, "node_ids"):
        raise ResultIRValidationError(
            "result_ir_ordering_binding_mismatch",
            "/ordering/node_ids",
            "ResultIR node order does not match ExecutionPlan.",
        )
    if receipt.ordering.element_ids != _plan_ids(plan, plan_payload, "element_ids"):
        raise ResultIRValidationError(
            "result_ir_ordering_binding_mismatch",
            "/ordering/element_ids",
            "ResultIR element order does not match ExecutionPlan.",
        )
    expected_ordering_hash = str(_plan_scalar(plan, plan_payload, "ordering_hash"))
    if receipt.ordering.ordering_hash != expected_ordering_hash:
        raise ResultIRValidationError(
            "result_ir_ordering_hash_mismatch",
            "/ordering/ordering_hash",
            "ResultIR ordering hash does not match ExecutionPlan.",
        )

    expected_load_pattern = str(_plan_scalar(plan, plan_payload, "load_pattern_id"))
    expected_operator_hash = str(_plan_scalar(plan, plan_payload, "operator_hash"))
    expected_recovery_hash = str(
        _plan_scalar(plan, plan_payload, "recovery_operator_hash")
    )
    if receipt.analysis.load_pattern_id != expected_load_pattern:
        raise ResultIRValidationError(
            "result_ir_load_pattern_binding_mismatch",
            "/analysis/load_pattern_id",
            "ResultIR load pattern does not match ExecutionPlan.",
        )
    if receipt.analysis.operator_hash != expected_operator_hash:
        raise ResultIRValidationError(
            "result_ir_operator_hash_mismatch",
            "/analysis/operator_hash",
            "ResultIR operator hash does not match validated ExecutionPlan.",
        )
    if receipt.analysis.recovery_operator_hash != expected_recovery_hash:
        raise ResultIRValidationError(
            "result_ir_recovery_operator_hash_mismatch",
            "/analysis/recovery_operator_hash",
            "ResultIR recovery hash does not match validated ExecutionPlan.",
        )


def _validate_backend(
    receipt: ResultIR,
    backend_result: LinearStaticResult,
    plan_payload: Mapping[str, Any],
    buffers: SolverModelBuffers,
) -> None:
    matrix_backend = receipt.backend_receipt.matrix_backend
    expected_backend_name = f"cpu_reference_{matrix_backend}_fp64"
    if backend_result.backend != expected_backend_name:
        raise ResultIRValidationError(
            "result_ir_backend_binding_mismatch",
            "/backend_receipt/matrix_backend",
            f"Backend result reports {backend_result.backend}, expected {expected_backend_name}.",
        )
    if backend_result.status != "ready":
        raise ResultIRValidationError(
            "result_ir_backend_not_ready",
            "/analysis/status",
            "Only successful backend results can produce ResultIR v1 receipts.",
        )
    if backend_result.operator_version != CPU_REFERENCE_OPERATOR_VERSION:
        raise ResultIRValidationError(
            "result_ir_operator_version_mismatch",
            "/analysis/operator_version",
            "Backend result uses a different operator version.",
        )
    if backend_result.solver_buffer_hash != buffers.numeric_buffer_hash:
        raise ResultIRValidationError(
            "result_ir_backend_buffer_hash_mismatch",
            "/input_bindings/solver_numeric_buffer_hash",
            "Backend result does not bind the supplied numeric solver buffers.",
        )
    if backend_result.operator_hash != receipt.analysis.operator_hash:
        raise ResultIRValidationError(
            "result_ir_operator_hash_mismatch",
            "/analysis/operator_hash",
            "Backend result operator hash does not match ResultIR.",
        )
    if backend_result.result_hash != receipt.analysis.backend_native_result_hash:
        raise ResultIRValidationError(
            "result_ir_backend_native_hash_mismatch",
            "/analysis/backend_native_result_hash",
            "Backend-native result hash does not match the supplied backend result.",
        )

    linear_solver = str(plan_payload["solver_policy"]["linear_solver"])
    expected_solver = {
        "dense": "dense_direct",
        "scipy_sparse": "scipy_sparse_direct",
    }[matrix_backend]
    if linear_solver != expected_solver:
        raise ResultIRValidationError(
            "result_ir_backend_plan_mismatch",
            "/backend_receipt/matrix_backend",
            "Backend receipt does not match ExecutionPlan solver policy.",
        )
    plan_tolerance = float(plan_payload["solver_policy"]["residual_tolerance"])
    if receipt.convergence.requested_residual_tolerance != plan_tolerance:
        raise ResultIRValidationError(
            "result_ir_tolerance_binding_mismatch",
            "/convergence/requested_residual_tolerance",
            "Requested tolerance does not match ExecutionPlan solver policy.",
        )
    if matrix_backend == "scipy_sparse" and receipt.backend_receipt.scipy_version is None:
        raise ResultIRValidationError(
            "result_ir_scipy_version_missing",
            "/backend_receipt/scipy_version",
            "Sparse CPU execution must identify the SciPy version.",
        )


def _validate_numerical_invariants(
    receipt: ResultIR,
    plan: Any,
    evaluated_trial_state: Any,
    committed_state: Any,
    backend_result: LinearStaticResult,
) -> None:
    stiffness = _plan_array(plan, "global_stiffness_dense")
    load = _plan_array(plan, "global_load").reshape(-1)
    constrained = _plan_array(plan, "constrained_dofs").astype(
        np.int64, copy=False
    ).reshape(-1)
    free = _plan_array(plan, "free_dofs").astype(np.int64, copy=False).reshape(-1)
    displacement = receipt.arrays.displacements_si.values.reshape(-1)
    residual = receipt.arrays.residual_si.values.reshape(-1)
    reactions = receipt.arrays.reactions_si.values.reshape(-1)

    dof_count = load.size
    node_count = len(receipt.ordering.node_ids)
    element_count = len(receipt.ordering.element_ids)
    expected_shapes = {
        "displacements_si": (node_count, 6),
        "residual_si": (node_count, 6),
        "reactions_si": (node_count, 6),
        "element_end_forces_local_si": (element_count, 2, 6),
        "element_strain_energy_j": (element_count,),
    }
    expected_metadata = {
        "displacements_si": (("node", "dof"), DOF_ORDER, _KINEMATIC_UNITS),
        "residual_si": (("node", "dof"), DOF_ORDER, _FORCE_UNITS),
        "reactions_si": (("node", "dof"), DOF_ORDER, _FORCE_UNITS),
        "element_end_forces_local_si": (
            ("element", "end", "dof"),
            DOF_ORDER,
            _FORCE_UNITS,
        ),
        "element_strain_energy_j": (
            ("element",),
            ("strain_energy",),
            ("J",),
        ),
    }
    for artifact in receipt.arrays.ordered():
        if artifact.shape != expected_shapes[artifact.name]:
            raise ResultIRValidationError(
                "result_ir_array_shape_mismatch",
                f"/arrays/{artifact.name}/shape",
                f"Expected {expected_shapes[artifact.name]}, got {artifact.shape}.",
            )
        if (
            artifact.axis_labels,
            artifact.component_labels,
            artifact.component_units,
        ) != expected_metadata[artifact.name]:
            raise ResultIRValidationError(
                "result_ir_array_metadata_mismatch",
                f"/arrays/{artifact.name}",
                "Array axes, component labels, or component units are not canonical.",
            )
    if stiffness.shape != (dof_count, dof_count) or dof_count != node_count * 6:
        raise ResultIRValidationError(
            "result_ir_plan_operator_shape_invalid",
            "/arrays/displacements_si/shape",
            "ExecutionPlan operator dimensions do not match ResultIR order.",
        )

    expected_residual = stiffness @ displacement - load
    _assert_array_close(
        residual,
        expected_residual,
        "result_ir_residual_invariant_failed",
        "/arrays/residual_si",
        "Stored residual is not K*u-F.",
    )
    expected_reactions = np.zeros_like(expected_residual)
    expected_reactions[constrained] = expected_residual[constrained]
    _assert_array_close(
        reactions,
        expected_reactions,
        "result_ir_reaction_invariant_failed",
        "/arrays/reactions_si",
        "Reactions must equal the constrained residual and be zero on free DOFs.",
    )

    expected_free_linf = (
        float(np.max(np.abs(expected_residual[free]))) if free.size else 0.0
    )
    expected_load_scale = max(
        1.0, float(np.max(np.abs(load[free]))) if free.size else 0.0
    )
    expected_scaled = expected_free_linf / expected_load_scale
    _assert_scalar_close(
        receipt.convergence.free_residual_linf,
        expected_free_linf,
        "result_ir_free_residual_mismatch",
        "/convergence/free_residual_linf",
    )
    _assert_scalar_close(
        receipt.convergence.load_scale,
        expected_load_scale,
        "result_ir_load_scale_mismatch",
        "/convergence/load_scale",
    )
    _assert_scalar_close(
        receipt.convergence.scaled_free_residual,
        expected_scaled,
        "result_ir_scaled_residual_mismatch",
        "/convergence/scaled_free_residual",
    )
    if expected_scaled > receipt.convergence.requested_residual_tolerance:
        raise ResultIRValidationError(
            "result_ir_not_converged",
            "/convergence/converged",
            "Recomputed free residual exceeds the requested tolerance.",
        )

    if tuple(int(value) for value in backend_result.constrained_dofs) != tuple(
        int(value) for value in constrained
    ):
        raise ResultIRValidationError(
            "result_ir_constraint_partition_mismatch",
            "/arrays/reactions_si",
            "Backend constrained DOFs do not match ExecutionPlan.",
        )
    if tuple(int(value) for value in backend_result.free_dofs) != tuple(
        int(value) for value in free
    ):
        raise ResultIRValidationError(
            "result_ir_constraint_partition_mismatch",
            "/convergence/free_residual_linf",
            "Backend free DOFs do not match ExecutionPlan.",
        )

    _assert_array_close(
        receipt.arrays.displacements_si.values,
        backend_result.displacements_si,
        "result_ir_backend_array_mismatch",
        "/arrays/displacements_si",
        "Displacements differ from the supplied backend result.",
    )
    _assert_array_close(
        receipt.arrays.residual_si.values,
        backend_result.residual_si,
        "result_ir_backend_array_mismatch",
        "/arrays/residual_si",
        "Residual differs from the supplied backend result.",
    )
    _assert_array_close(
        receipt.arrays.reactions_si.values,
        backend_result.reactions_si,
        "result_ir_backend_array_mismatch",
        "/arrays/reactions_si",
        "Reactions differ from the supplied backend result.",
    )

    trial_displacement = _state_displacement(evaluated_trial_state)
    committed_displacement = _state_displacement(committed_state)
    _assert_array_close(
        displacement,
        trial_displacement,
        "result_ir_trial_state_displacement_mismatch",
        "/input_bindings/evaluated_trial_state_hash",
        "Evaluated trial displacement does not match ResultIR.",
    )
    _assert_array_close(
        displacement,
        committed_displacement,
        "result_ir_committed_state_displacement_mismatch",
        "/input_bindings/committed_state_hash",
        "Committed displacement does not match ResultIR.",
    )
    for vector_name in ("velocity_si", "acceleration_si"):
        _assert_array_close(
            _state_vector(evaluated_trial_state, vector_name),
            _state_vector(committed_state, vector_name),
            "result_ir_committed_state_vector_mismatch",
            "/input_bindings/committed_state_hash",
            f"Committed {vector_name} does not match the evaluated trial.",
        )

    global_dofs = _plan_array(plan, "element_global_dofs").astype(
        np.int64, copy=False
    )
    transforms = _plan_array(plan, "recovery_transform_global_to_local")
    local_stiffness = _plan_array(plan, "recovery_stiffness_local")
    if (
        global_dofs.shape != (element_count, 12)
        or transforms.shape != (element_count, 12, 12)
        or local_stiffness.shape != (element_count, 12, 12)
    ):
        raise ResultIRValidationError(
            "result_ir_recovery_operator_shape_invalid",
            "/arrays/element_end_forces_local_si",
            "ExecutionPlan recovery arrays have invalid dimensions.",
        )
    expected_forces = np.zeros((element_count, 2, 6), dtype="<f8")
    expected_element_energy = np.zeros(element_count, dtype="<f8")
    for index in range(element_count):
        local_displacement = transforms[index] @ displacement[global_dofs[index]]
        local_force = local_stiffness[index] @ local_displacement
        expected_forces[index] = local_force.reshape(2, 6)
        expected_element_energy[index] = 0.5 * float(
            local_displacement @ local_force
        )
    _assert_array_close(
        receipt.arrays.element_end_forces_local_si.values,
        expected_forces,
        "result_ir_recovery_force_invariant_failed",
        "/arrays/element_end_forces_local_si",
        "Element end forces do not match the validated recovery operator.",
    )
    _assert_array_close(
        receipt.arrays.element_strain_energy_j.values,
        expected_element_energy,
        "result_ir_element_energy_invariant_failed",
        "/arrays/element_strain_energy_j",
        "Element energies do not match recovered local work.",
    )
    _assert_array_close(
        receipt.arrays.element_end_forces_local_si.values,
        backend_result.element_end_forces_local_si,
        "result_ir_backend_array_mismatch",
        "/arrays/element_end_forces_local_si",
        "Element end forces differ from the supplied backend result.",
    )
    _assert_array_close(
        receipt.arrays.element_strain_energy_j.values,
        backend_result.element_strain_energy_j,
        "result_ir_backend_array_mismatch",
        "/arrays/element_strain_energy_j",
        "Element energies differ from the supplied backend result.",
    )

    element_total = float(np.sum(expected_element_energy))
    global_energy = 0.5 * float(displacement @ (stiffness @ displacement))
    external_work_energy = 0.5 * float(displacement @ load)
    for value, code, path in (
        (
            element_total,
            "result_ir_total_energy_sum_mismatch",
            "/total_strain_energy_j",
        ),
        (
            global_energy,
            "result_ir_global_energy_invariant_failed",
            "/total_strain_energy_j",
        ),
        (
            external_work_energy,
            "result_ir_external_work_invariant_failed",
            "/total_strain_energy_j",
        ),
        (
            float(backend_result.total_strain_energy_j),
            "result_ir_backend_energy_mismatch",
            "/total_strain_energy_j",
        ),
    ):
        _assert_scalar_close(
            receipt.total_strain_energy_j,
            value,
            code,
            path,
            relative_tolerance=2.0e-11,
        )


def _make_array_artifact(
    name: str,
    values: Any,
    *,
    axis_labels: tuple[str, ...],
    component_labels: tuple[str, ...],
    component_units: tuple[str, ...],
) -> ArrayArtifact:
    array = np.asarray(values, dtype="<f8")
    if array.ndim == 0 or any(dimension <= 0 for dimension in array.shape):
        raise ResultIRValidationError(
            "result_ir_array_shape_invalid",
            f"/arrays/{name}/shape",
            "Result arrays must have at least one non-empty dimension.",
        )
    if not np.all(np.isfinite(array)):
        raise ResultIRValidationError(
            "result_ir_non_finite",
            f"/arrays/{name}/values",
            "Result arrays cannot contain NaN or Infinity.",
        )
    if len(axis_labels) != array.ndim:
        raise ResultIRValidationError(
            "result_ir_axis_metadata_invalid",
            f"/arrays/{name}/axis_labels",
            "Axis label count must equal array rank.",
        )
    immutable = _immutable_f64_array(array)
    descriptor = {
        "name": name,
        "dtype": immutable.dtype.str,
        "shape": list(immutable.shape),
        "layout": "C",
        "axis_labels": list(axis_labels),
        "component_labels": list(component_labels),
        "component_units": list(component_units),
        "byte_length": int(immutable.nbytes),
        "data_hash": raw_array_hash(immutable),
    }
    return ArrayArtifact(
        name=name,
        dtype=immutable.dtype.str,
        shape=tuple(int(value) for value in immutable.shape),
        layout="C",
        axis_labels=tuple(axis_labels),
        component_labels=tuple(component_labels),
        component_units=tuple(component_units),
        byte_length=int(immutable.nbytes),
        data_hash=str(descriptor["data_hash"]),
        content_hash=canonical_hash(descriptor),
        _values=immutable,
    )


def _numerical_result_hash(arrays: ResultArrays, total_energy: float) -> str:
    return canonical_hash(
        {
            "contract": "engine-v2-result-ir-numerical.v1",
            "arrays": [
                {
                    "name": artifact.name,
                    "data_hash": artifact.data_hash,
                    "content_hash": artifact.content_hash,
                }
                for artifact in arrays.ordered()
            ],
            "total_strain_energy_j": float(total_energy),
        }
    )


def _aggregate_hash(receipt: ResultIR) -> str:
    payload = receipt.to_dict()
    payload.pop("result_ir_hash")
    return canonical_hash(payload)


def _immutable_f64_array(values: np.ndarray) -> np.ndarray:
    contiguous = np.ascontiguousarray(values, dtype="<f8")
    return np.frombuffer(
        contiguous.tobytes(order="C"), dtype="<f8"
    ).reshape(contiguous.shape)


def _plan_array(plan: Any, name: str) -> np.ndarray:
    try:
        array = plan.array(name)
    except (AttributeError, KeyError) as exc:
        raise ResultIRValidationError(
            "result_ir_plan_array_missing",
            "/",
            f"ExecutionPlan does not expose required array {name!r}.",
        ) from exc
    result = np.asarray(array)
    if not np.all(np.isfinite(result)):
        raise ResultIRValidationError(
            "result_ir_plan_array_non_finite",
            "/",
            f"ExecutionPlan array {name!r} contains NaN or Infinity.",
        )
    return result


def _state_displacement(state: Any) -> np.ndarray:
    return _state_vector(state, "displacement_si")


def _state_vector(state: Any, name: str) -> np.ndarray:
    value = getattr(state, name, None)
    if value is None:
        payload = _contract_dict(state, "StateIR")
        value = payload["kinematics"][name]
    result = np.asarray(value, dtype="<f8").reshape(-1)
    if not np.all(np.isfinite(result)):
        raise ResultIRValidationError(
            "result_ir_state_non_finite",
            "/input_bindings",
            "StateIR displacement contains NaN or Infinity.",
        )
    return result


def _plan_ids(
    plan: Any, payload: Mapping[str, Any], name: Literal["node_ids", "element_ids"]
) -> tuple[str, ...]:
    value = getattr(plan, name, None)
    if value is None:
        value = payload["entity_order"][name]
    return tuple(str(item) for item in value)


def _plan_scalar(plan: Any, payload: Mapping[str, Any], name: str) -> Any:
    value = getattr(plan, name, None)
    if value is not None:
        return value
    paths: dict[str, tuple[str, ...]] = {
        "plan_hash": ("plan_hash",),
        "operator_hash": ("analysis", "operator_hash"),
        "recovery_operator_hash": ("analysis", "recovery_operator_hash"),
        "ordering_hash": ("entity_order", "ordering_hash"),
        "load_pattern_id": ("solver_model_buffers", "load_pattern_id"),
    }
    current: Any = payload
    try:
        for key in paths[name]:
            current = current[key]
    except (KeyError, TypeError) as exc:
        raise ResultIRValidationError(
            "result_ir_plan_binding_missing",
            "/",
            f"ExecutionPlan does not expose required binding {name!r}.",
        ) from exc
    return current


def _contract_dict(value: Any, label: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    for method_name in ("to_dict", "to_manifest"):
        method = getattr(value, method_name, None)
        if callable(method):
            payload = method()
            if isinstance(payload, Mapping):
                return payload
    raise ResultIRValidationError(
        "result_ir_context_invalid", "/", f"{label} has no mapping representation."
    )


def _validate_execution_plan_first(plan: Any, buffers: SolverModelBuffers) -> None:
    from .execution_plan import validate_execution_plan

    validate_execution_plan(plan, expected_buffers=buffers)


def _validate_state_first(state: Any, plan: Any) -> None:
    from .state_ir import validate_state_ir

    validate_state_ir(state, expected_plan=plan)


def _assert_array_close(
    actual: Any,
    expected: Any,
    code: str,
    path: str,
    message: str,
    *,
    relative_tolerance: float = 5.0e-13,
) -> None:
    actual_array = np.asarray(actual, dtype="<f8")
    expected_array = np.asarray(expected, dtype="<f8")
    if actual_array.shape != expected_array.shape:
        raise ResultIRValidationError(
            code,
            path,
            f"{message} Shape {actual_array.shape} != {expected_array.shape}.",
        )
    scale = max(
        1.0,
        float(np.max(np.abs(actual_array))) if actual_array.size else 0.0,
        float(np.max(np.abs(expected_array))) if expected_array.size else 0.0,
    )
    if not np.allclose(
        actual_array,
        expected_array,
        rtol=relative_tolerance,
        atol=relative_tolerance * scale,
    ):
        difference = float(np.max(np.abs(actual_array - expected_array)))
        raise ResultIRValidationError(
            code, path, f"{message} Maximum absolute difference is {difference:.17g}."
        )


def _assert_scalar_close(
    actual: float,
    expected: float,
    code: str,
    path: str,
    *,
    relative_tolerance: float = 5.0e-13,
) -> None:
    if not math.isclose(
        actual,
        expected,
        rel_tol=relative_tolerance,
        abs_tol=relative_tolerance * max(1.0, abs(actual), abs(expected)),
    ):
        raise ResultIRValidationError(
            code, path, f"Expected {expected:.17g}, got {actual:.17g}."
        )


def _installed_version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).resolve().parents[2] / "schemas" / "result_ir_v1.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


__all__ = [
    "ArrayArtifact",
    "BackendReceipt",
    "RESULT_IR_SCHEMA_VERSION",
    "ResultIR",
    "ResultIRValidationError",
    "build_result_ir",
    "validate_result_ir_v1",
]
