"""Sparse ``ExecutionPlanV2`` to immutable linear-static ``ResultIRV2``.

This contract is deliberately backend-neutral at the recovery boundary.  A
bridge supplies one exact HIP FGMRES solution, its exported free-space true
residual, and typed (but detached) source provenance.  Recovery itself uses
only :meth:`ExecutionPlanV2.residual` and the plan's element-local recovery
arrays.  It never materializes a dense global matrix and never invokes a
linear solver.

Two validation layers are intentionally public and separate:

* :func:`validate_result_ir_v2` validates the immutable serialized receipt;
* :func:`validate_result_ir_v2_physics` additionally replays the exact plan
  and trial/committed ``StateIR`` bindings and all physical identities.

The serialized provenance is a hash commitment, not live HIP authority.  A
HIP bridge must validate that authority before calling the builder.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from typing import Any, Literal

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.buffers import DOF_ORDER

from ._canonical import (
    CanonicalContractError,
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from .execution_plan_v2 import (
    ExecutionPlanV2,
    ExecutionPlanV2Error,
    validate_execution_plan_v2,
)
from .state_ir import StateIR, StateIRError, validate_state_ir

RESULT_IR_V2_SCHEMA_VERSION = "structural-analysis-result-ir.v2"
RESULT_IR_V2_CAPABILITY_PROFILE = "hip_fgmres_sparse_plan_recovery_linear_static"

_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_ARCHITECTURE_PATTERN = re.compile(r"^gfx[0-9a-f]+(?::[A-Za-z0-9_+.-]+)*$")
_ARCHITECTURE_BASE_PATTERN = re.compile(r"^gfx[0-9a-f]+$")
_UUID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_PCI_BDF_PATTERN = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$")
_MAX_INDEX = int(np.iinfo(np.int32).max)
_DOF_COUNT_PER_NODE = len(DOF_ORDER)
_FORCE_UNITS = ("N", "N", "N", "N*m", "N*m", "N*m")
_DISPLACEMENT_UNITS = ("m", "m", "m", "rad", "rad", "rad")
_ARRAY_NAMES = (
    "displacements_si",
    "residual_si",
    "reactions_si",
    "element_end_forces_local_si",
    "element_strain_energy_j",
    "exported_free_residual_si",
)


class ResultIRV2Error(ValueError):
    """Stable fail-closed ResultIR v2 contract or physics error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


ResultIRV2ValidationError = ResultIRV2Error


@dataclass(frozen=True, slots=True)
class ResultArrayV2:
    """One immutable little-endian FP64 array and its byte commitments."""

    name: str
    dtype: Literal["<f8"]
    shape: tuple[int, ...]
    layout: Literal["C"]
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
        }


@dataclass(frozen=True, slots=True)
class ResultIRV2InputBindings:
    model_ir_content_hash: str
    solver_numeric_buffer_hash: str
    solver_entity_mapping_hash: str
    solver_artifact_hash: str
    execution_plan_hash: str
    evaluated_trial_state_hash: str
    committed_state_hash: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResultIRV2Analysis:
    load_pattern_id: str
    operator_version: str
    operator_hash: str
    recovery_operator_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "linear_static",
            "status": "ready",
            "load_pattern_id": self.load_pattern_id,
            "residual_sign": "internal_minus_external",
            "exported_free_residual_sign": "external_minus_internal",
            "operator_version": self.operator_version,
            "operator_hash": self.operator_hash,
            "recovery_operator_hash": self.recovery_operator_hash,
        }


@dataclass(frozen=True, slots=True)
class ResultIRV2Ordering:
    node_ids: tuple[str, ...]
    element_ids: tuple[str, ...]
    constrained_dofs: tuple[int, ...]
    free_dofs: tuple[int, ...]
    ordering_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_ids": list(self.node_ids),
            "element_ids": list(self.element_ids),
            "dof_components": list(DOF_ORDER),
            "element_end_order": ["i", "j"],
            "constrained_dofs": list(self.constrained_dofs),
            "free_dofs": list(self.free_dofs),
            "ordering_hash": self.ordering_hash,
        }


@dataclass(frozen=True, slots=True)
class ResultIRV2Arrays:
    displacements_si: ResultArrayV2
    residual_si: ResultArrayV2
    reactions_si: ResultArrayV2
    element_end_forces_local_si: ResultArrayV2
    element_strain_energy_j: ResultArrayV2
    exported_free_residual_si: ResultArrayV2

    @property
    def full_residual_si(self) -> ResultArrayV2:
        """Explicit alias for the stored full ``K*u-F`` residual."""

        return self.residual_si

    @property
    def element_local_end_forces_si(self) -> ResultArrayV2:
        return self.element_end_forces_local_si

    @property
    def element_energy_j(self) -> ResultArrayV2:
        return self.element_strain_energy_j

    @property
    def exported_free_true_residual_si(self) -> ResultArrayV2:
        return self.exported_free_residual_si

    def ordered(self) -> tuple[ResultArrayV2, ...]:
        return tuple(getattr(self, name) for name in _ARRAY_NAMES)

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {row.name: row.to_dict() for row in self.ordered()}


@dataclass(frozen=True, slots=True)
class ResultIRV2Convergence:
    requested_residual_tolerance: float
    free_residual_linf: float
    exported_free_residual_linf: float
    load_scale: float
    scaled_free_residual: float
    scaled_exported_free_residual: float
    converged: Literal[True] = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResultIRV2Energy:
    total_strain_energy_j: float
    element_strain_energy_sum_j: float
    global_strain_energy_j: float
    external_work_energy_j: float
    residual_work_energy_j: float
    balance_error_j: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    """Detached HIP commitments supplied by a separately validating bridge.

    The five zero counters are a narrow direct-call-surface contract for the
    CPU recovery factory consuming retained host bytes.  They are not
    transitive or process-wide runtime instrumentation, and they do not restate
    or erase work already accounted for by the bound HIP completion/export
    receipts.
    """

    case_id: str
    case_parity_receipt_hash: str
    terminal_observation_receipt_hash: str
    completion_export_receipt_hash: str
    completion_export_payload_hash: str
    device_identity_receipt_hash: str
    solution_payload_sha256: str
    exported_free_residual_payload_sha256: str
    compiled_architecture: str
    runtime_architecture_base: str
    device_ordinal: int
    device_uuid_bytes_hex: str
    device_pci_bdf: str
    actual_backend: Literal["hip"] = "hip"
    recovery_backend: Literal["cpu_sparse_execution_plan_v2"] = (
        "cpu_sparse_execution_plan_v2"
    )
    additional_device_operation_count: Literal[0] = 0
    additional_d2h_operation_count: Literal[0] = 0
    additional_solve_count: Literal[0] = 0
    additional_export_count: Literal[0] = 0
    fallback_count: Literal[0] = 0
    live_authority_serialized: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ResultIRV2SourceProvenance = SourceProvenance


@dataclass(frozen=True, slots=True)
class ResultIRV2Claims:
    result_ir_verified: Literal[True] = True
    result_ir_ready: Literal[True] = True
    state_ir_lineage_verified: Literal[True] = True
    reaction_recovery_verified: Literal[True] = True
    member_force_recovery_verified: Literal[True] = True
    energy_identities_verified: Literal[True] = True
    device_recovery_verified: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    end_to_end_o_n_proven: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False
    signed_evidence: Literal[False] = False
    standalone_provenance: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResultIRV2:
    """Immutable sparse-recovery linear-static result receipt."""

    result_id: str
    input_bindings: ResultIRV2InputBindings
    analysis: ResultIRV2Analysis
    ordering: ResultIRV2Ordering
    arrays: ResultIRV2Arrays
    convergence: ResultIRV2Convergence
    energy: ResultIRV2Energy
    source_provenance: SourceProvenance
    claims: ResultIRV2Claims
    numerical_result_hash: str
    result_ir_hash: str

    @property
    def schema_version(self) -> str:
        return RESULT_IR_V2_SCHEMA_VERSION

    @property
    def capability_profile(self) -> str:
        return RESULT_IR_V2_CAPABILITY_PROFILE

    @property
    def total_strain_energy_j(self) -> float:
        return self.energy.total_strain_energy_j

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capability_profile": self.capability_profile,
            "result_id": self.result_id,
            "input_bindings": self.input_bindings.to_dict(),
            "analysis": self.analysis.to_dict(),
            "ordering": self.ordering.to_dict(),
            "arrays": self.arrays.to_dict(),
            "convergence": self.convergence.to_dict(),
            "energy": self.energy.to_dict(),
            "source_provenance": self.source_provenance.to_dict(),
            "recovery": {
                "global_operator": "execution_plan_v2_residual_csr",
                "element_operator": "execution_plan_v2_local_recovery_arrays",
                "reaction_definition": (
                    "full_internal_minus_external_residual_on_constrained_dofs"
                ),
                "element_force_definition": "k_local_times_u_local",
                "energy_definition": "half_u_transpose_force",
                "global_dense_matrix_materialized": False,
                "linear_solve_invoked": False,
            },
            "claims": self.claims.to_dict(),
            "numerical_result_hash": self.numerical_result_hash,
            "result_ir_hash": self.result_ir_hash,
            "extensions": {},
        }

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


def build_result_ir_v2(
    plan: ExecutionPlanV2,
    evaluated_trial_state: StateIR,
    committed_state: StateIR,
    full_displacement_si: Any,
    exported_free_residual_si: Any,
    source_provenance: SourceProvenance,
    *,
    result_id: str = "Result.linear-static.v2",
) -> ResultIRV2:
    """Recover six result arrays and build a fully replayed ResultIR v2.

    ``full_displacement_si`` is node-major global-DOF order.  The exported
    residual is free-DOF order and uses the FGMRES ``F-K*u`` sign.
    """

    _validate_exact_sources(plan, evaluated_trial_state, committed_state)
    _validate_source_provenance(source_provenance)
    _require_stable_id(result_id, "/result_id")

    displacement = _finite_flat_vector(
        full_displacement_si,
        plan.dof_count,
        "/arrays/displacements_si/values",
    )
    free = plan.array("free_dofs")
    constrained = plan.array("constrained_dofs")
    exported = _finite_flat_vector(
        exported_free_residual_si,
        int(free.size),
        "/arrays/exported_free_residual_si/values",
    )
    if np.any(displacement[constrained] != 0.0):
        _raise(
            "result_ir_v2_constrained_displacement_nonzero",
            "/arrays/displacements_si",
            "Zero-prescribed constrained displacements must remain exactly zero.",
        )

    try:
        residual = np.asarray(plan.residual(displacement), dtype="<f8")
    except (TypeError, ValueError) as exc:
        raise ResultIRV2Error(
            "result_ir_v2_residual_replay_failed",
            "/arrays/residual_si",
            f"ExecutionPlanV2 residual replay failed: {exc}",
        ) from exc
    reactions = np.zeros(plan.dof_count, dtype="<f8")
    reactions[constrained] = residual[constrained]
    element_forces, element_energy = _recover_elements(plan, displacement)

    free_units = tuple(_FORCE_UNITS[int(index) % _DOF_COUNT_PER_NODE] for index in free)
    free_components = tuple(
        DOF_ORDER[int(index) % _DOF_COUNT_PER_NODE] for index in free
    )
    arrays = ResultIRV2Arrays(
        displacements_si=_array_artifact(
            "displacements_si",
            displacement.reshape(plan.node_count, _DOF_COUNT_PER_NODE),
            axis_labels=("node", "dof"),
            component_labels=tuple(DOF_ORDER),
            component_units=_DISPLACEMENT_UNITS,
        ),
        residual_si=_array_artifact(
            "residual_si",
            residual.reshape(plan.node_count, _DOF_COUNT_PER_NODE),
            axis_labels=("node", "dof"),
            component_labels=tuple(DOF_ORDER),
            component_units=_FORCE_UNITS,
        ),
        reactions_si=_array_artifact(
            "reactions_si",
            reactions.reshape(plan.node_count, _DOF_COUNT_PER_NODE),
            axis_labels=("node", "dof"),
            component_labels=tuple(DOF_ORDER),
            component_units=_FORCE_UNITS,
        ),
        element_end_forces_local_si=_array_artifact(
            "element_end_forces_local_si",
            element_forces,
            axis_labels=("element", "end", "dof"),
            component_labels=tuple(DOF_ORDER),
            component_units=_FORCE_UNITS,
        ),
        element_strain_energy_j=_array_artifact(
            "element_strain_energy_j",
            element_energy,
            axis_labels=("element",),
            component_labels=("strain_energy",),
            component_units=("J",),
        ),
        exported_free_residual_si=_array_artifact(
            "exported_free_residual_si",
            exported,
            axis_labels=("free_dof",),
            component_labels=free_components,
            component_units=free_units,
        ),
    )
    load = plan.array("global_load")
    load_scale = max(1.0, float(np.max(np.abs(load[free]))))
    free_linf = float(np.max(np.abs(residual[free])))
    exported_linf = float(np.max(np.abs(exported)))
    convergence = ResultIRV2Convergence(
        requested_residual_tolerance=float(plan.residual_tolerance),
        free_residual_linf=free_linf,
        exported_free_residual_linf=exported_linf,
        load_scale=load_scale,
        scaled_free_residual=free_linf / load_scale,
        scaled_exported_free_residual=exported_linf / load_scale,
    )
    energy = _energy_receipt(displacement, residual, load, element_energy)
    receipt = ResultIRV2(
        result_id=result_id,
        input_bindings=ResultIRV2InputBindings(
            model_ir_content_hash=plan.model_ir_content_hash,
            solver_numeric_buffer_hash=plan.solver_numeric_buffer_hash,
            solver_entity_mapping_hash=plan.solver_entity_mapping_hash,
            solver_artifact_hash=plan.solver_artifact_hash,
            execution_plan_hash=plan.plan_hash,
            evaluated_trial_state_hash=evaluated_trial_state.state_hash,
            committed_state_hash=committed_state.state_hash,
        ),
        analysis=ResultIRV2Analysis(
            load_pattern_id=plan.load_pattern_id,
            operator_version=plan.operator_version,
            operator_hash=plan.operator_hash,
            recovery_operator_hash=plan.recovery_operator_hash,
        ),
        ordering=ResultIRV2Ordering(
            node_ids=plan.node_ids,
            element_ids=plan.element_ids,
            constrained_dofs=tuple(int(value) for value in constrained),
            free_dofs=tuple(int(value) for value in free),
            ordering_hash=plan.ordering_hash,
        ),
        arrays=arrays,
        convergence=convergence,
        energy=energy,
        source_provenance=source_provenance,
        claims=ResultIRV2Claims(),
        numerical_result_hash=_numerical_hash(arrays, convergence, energy),
        result_ir_hash="sha256:" + "0" * 64,
    )
    receipt = replace(receipt, result_ir_hash=_receipt_hash(receipt.to_dict()))
    return validate_result_ir_v2_physics(
        receipt,
        expected_plan=plan,
        expected_evaluated_trial_state=evaluated_trial_state,
        expected_committed_state=committed_state,
    )


def validate_result_ir_v2(receipt: ResultIRV2) -> ResultIRV2:
    """Validate exact dataclass/storage and detached serialized commitments."""

    if type(receipt) is not ResultIRV2:
        _raise("result_ir_v2_type_invalid", "/", "Expected an exact ResultIRV2.")
    exact_nested = (
        (receipt.input_bindings, ResultIRV2InputBindings, "/input_bindings"),
        (receipt.analysis, ResultIRV2Analysis, "/analysis"),
        (receipt.ordering, ResultIRV2Ordering, "/ordering"),
        (receipt.arrays, ResultIRV2Arrays, "/arrays"),
        (receipt.convergence, ResultIRV2Convergence, "/convergence"),
        (receipt.energy, ResultIRV2Energy, "/energy"),
        (receipt.source_provenance, SourceProvenance, "/source_provenance"),
        (receipt.claims, ResultIRV2Claims, "/claims"),
    )
    for value, expected_type, path in exact_nested:
        if type(value) is not expected_type:
            _raise(
                "result_ir_v2_container_invalid",
                path,
                f"Expected exact {expected_type.__name__} storage.",
            )
    _validate_receipt_scalars(receipt)
    if (
        type(receipt.ordering.node_ids) is not tuple
        or type(receipt.ordering.element_ids) is not tuple
        or type(receipt.ordering.constrained_dofs) is not tuple
        or type(receipt.ordering.free_dofs) is not tuple
    ):
        _raise(
            "result_ir_v2_container_invalid",
            "/ordering",
            "Ordering containers must be exact tuples.",
        )
    artifacts = receipt.arrays.ordered()
    if any(type(row) is not ResultArrayV2 for row in artifacts):
        _raise(
            "result_ir_v2_container_invalid",
            "/arrays",
            "All arrays must use exact ResultArrayV2 storage.",
        )
    for row in artifacts:
        _validate_array_dataclass(row)
    _validate_source_provenance(receipt.source_provenance)
    validate_result_ir_v2_manifest(receipt.to_dict())
    return receipt


def validate_result_ir_v2_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate a detached JSON-shaped ResultIR v2 without live sources."""

    if type(manifest) is not dict:
        _raise(
            "result_ir_v2_manifest_type_invalid",
            "/",
            "Serialized ResultIR v2 must be an exact dictionary.",
        )
    errors = sorted(
        _schema_validator().iter_errors(manifest),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _raise("result_ir_v2_schema_invalid", path or "/", error.message)

    _validate_manifest_array_metadata(manifest)
    _validate_manifest_scalars(manifest)

    try:
        expected_numerical = _numerical_hash_from_manifest(manifest)
    except CanonicalContractError as exc:
        raise ResultIRV2Error(
            "result_ir_v2_manifest_noncanonical", "/", str(exc)
        ) from exc
    if manifest["numerical_result_hash"] != expected_numerical:
        _raise(
            "result_ir_v2_numerical_hash_mismatch",
            "/numerical_result_hash",
            "Numerical result commitment is stale.",
        )
    try:
        expected_receipt_hash = _receipt_hash(manifest)
    except CanonicalContractError as exc:
        raise ResultIRV2Error(
            "result_ir_v2_manifest_noncanonical", "/", str(exc)
        ) from exc
    if manifest["result_ir_hash"] != expected_receipt_hash:
        _raise(
            "result_ir_v2_aggregate_hash_mismatch",
            "/result_ir_hash",
            "Aggregate ResultIR v2 commitment is stale.",
        )


def validate_result_ir_v2_physics(
    receipt: ResultIRV2,
    *,
    expected_plan: ExecutionPlanV2,
    expected_evaluated_trial_state: StateIR,
    expected_committed_state: StateIR,
) -> ResultIRV2:
    """Replay exact plan/state bindings and every supported physical identity."""

    validate_result_ir_v2(receipt)
    _validate_exact_sources(
        expected_plan,
        expected_evaluated_trial_state,
        expected_committed_state,
    )
    _validate_state_lineage(expected_evaluated_trial_state, expected_committed_state)
    _validate_source_bindings(
        receipt,
        expected_plan,
        expected_evaluated_trial_state,
        expected_committed_state,
    )

    plan = expected_plan
    displacement = receipt.arrays.displacements_si.values.reshape(-1)
    residual = receipt.arrays.residual_si.values.reshape(-1)
    reactions = receipt.arrays.reactions_si.values.reshape(-1)
    exported = receipt.arrays.exported_free_residual_si.values.reshape(-1)
    constrained = plan.array("constrained_dofs")
    free = plan.array("free_dofs")
    if not np.array_equal(displacement, expected_evaluated_trial_state.displacement_si):
        _raise(
            "result_ir_v2_trial_displacement_mismatch",
            "/input_bindings/evaluated_trial_state_hash",
            "Result displacement differs from the evaluated trial StateIR.",
        )
    if not np.array_equal(displacement, expected_committed_state.displacement_si):
        _raise(
            "result_ir_v2_committed_displacement_mismatch",
            "/input_bindings/committed_state_hash",
            "Result displacement differs from the committed StateIR.",
        )
    if np.any(displacement[constrained] != 0.0):
        _raise(
            "result_ir_v2_constrained_displacement_nonzero",
            "/arrays/displacements_si",
            "Constrained displacement entries must be exactly zero.",
        )

    expected_residual = np.asarray(plan.residual(displacement), dtype="<f8")
    _assert_array_close(
        residual,
        expected_residual,
        "result_ir_v2_residual_invariant_failed",
        "/arrays/residual_si",
        "Full residual must equal ExecutionPlanV2 K*u-F replay.",
    )
    expected_reactions = np.zeros(plan.dof_count, dtype="<f8")
    expected_reactions[constrained] = expected_residual[constrained]
    _assert_array_close(
        reactions,
        expected_reactions,
        "result_ir_v2_reaction_invariant_failed",
        "/arrays/reactions_si",
        "Reactions must retain constrained residual and be zero on free DOFs.",
    )
    load = plan.array("global_load")
    load_scale = max(1.0, float(np.max(np.abs(load[free]))))
    free_linf = float(np.max(np.abs(expected_residual[free])))
    exported_linf = float(np.max(np.abs(exported)))
    expected_scaled = free_linf / load_scale
    expected_exported_scaled = exported_linf / load_scale
    for actual, expected, field_name in (
        (receipt.convergence.load_scale, load_scale, "load_scale"),
        (receipt.convergence.free_residual_linf, free_linf, "free_residual_linf"),
        (
            receipt.convergence.exported_free_residual_linf,
            exported_linf,
            "exported_free_residual_linf",
        ),
        (
            receipt.convergence.scaled_free_residual,
            expected_scaled,
            "scaled_free_residual",
        ),
        (
            receipt.convergence.scaled_exported_free_residual,
            expected_exported_scaled,
            "scaled_exported_free_residual",
        ),
    ):
        _assert_scalar_close(
            actual,
            expected,
            "result_ir_v2_convergence_scalar_mismatch",
            f"/convergence/{field_name}",
        )
    if receipt.convergence.requested_residual_tolerance != plan.residual_tolerance:
        _raise(
            "result_ir_v2_tolerance_binding_mismatch",
            "/convergence/requested_residual_tolerance",
            "Receipt tolerance differs from ExecutionPlanV2.",
        )
    if expected_scaled > plan.residual_tolerance:
        _raise(
            "result_ir_v2_not_converged",
            "/convergence/scaled_free_residual",
            "Scaled free K*u-F residual exceeds the plan tolerance.",
        )
    if expected_exported_scaled > plan.residual_tolerance:
        _raise(
            "result_ir_v2_exported_residual_not_converged",
            "/convergence/scaled_exported_free_residual",
            "Scaled exported F-K*u residual exceeds the plan tolerance.",
        )
    if not np.allclose(
        exported,
        -expected_residual[free],
        rtol=1.0e-8,
        atol=1.0e-12,
    ):
        _raise(
            "result_ir_v2_exported_residual_sign_mismatch",
            "/arrays/exported_free_residual_si",
            "Exported free residual must approximate -(K*u-F)[free].",
        )

    expected_forces, expected_element_energy = _recover_elements(plan, displacement)
    _assert_array_close(
        receipt.arrays.element_end_forces_local_si.values,
        expected_forces,
        "result_ir_v2_member_force_invariant_failed",
        "/arrays/element_end_forces_local_si",
        "Element local end forces differ from plan recovery arrays.",
    )
    _assert_array_close(
        receipt.arrays.element_strain_energy_j.values,
        expected_element_energy,
        "result_ir_v2_element_energy_invariant_failed",
        "/arrays/element_strain_energy_j",
        "Element energies differ from half local displacement-force work.",
    )
    expected_energy = _energy_receipt(
        displacement, expected_residual, load, expected_element_energy
    )
    for field_name in expected_energy.__dataclass_fields__:
        _assert_scalar_close(
            getattr(receipt.energy, field_name),
            getattr(expected_energy, field_name),
            "result_ir_v2_energy_receipt_mismatch",
            f"/energy/{field_name}",
            relative_tolerance=2.0e-11,
        )
    _validate_energy_identities(receipt.energy)

    return receipt


def validate_result_ir_v2_against_sources(
    receipt: ResultIRV2,
    *,
    expected_plan: ExecutionPlanV2,
    expected_evaluated_trial_state: StateIR,
    expected_committed_state: StateIR,
) -> ResultIRV2:
    """Compatibility spelling for the explicit physical-source validator."""

    return validate_result_ir_v2_physics(
        receipt,
        expected_plan=expected_plan,
        expected_evaluated_trial_state=expected_evaluated_trial_state,
        expected_committed_state=expected_committed_state,
    )


def _validate_exact_sources(
    plan: ExecutionPlanV2,
    trial: StateIR,
    committed: StateIR,
) -> None:
    if type(plan) is not ExecutionPlanV2:
        _raise(
            "result_ir_v2_plan_type_invalid",
            "/input_bindings/execution_plan_hash",
            "Expected an exact ExecutionPlanV2.",
        )
    try:
        validate_execution_plan_v2(plan)
    except ExecutionPlanV2Error as exc:
        raise ResultIRV2Error(
            "result_ir_v2_plan_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc
    for state, label, path in (
        (trial, "evaluated trial", "/input_bindings/evaluated_trial_state_hash"),
        (committed, "committed", "/input_bindings/committed_state_hash"),
    ):
        if type(state) is not StateIR:
            _raise(
                "result_ir_v2_state_type_invalid",
                path,
                f"Expected an exact {label} StateIR.",
            )
        try:
            validate_state_ir(state, expected_plan=plan)
        except StateIRError as exc:
            raise ResultIRV2Error(
                "result_ir_v2_state_invalid",
                path,
                f"{label} StateIR failed {exc.code}@{exc.path}: {exc.message}",
            ) from exc
    _validate_state_lineage(trial, committed)


def _validate_state_lineage(trial: StateIR, committed: StateIR) -> None:
    if trial.role != "trial":
        _raise(
            "result_ir_v2_trial_role_invalid",
            "/input_bindings/evaluated_trial_state_hash",
            "Evaluated state must have trial role.",
        )
    if committed.role != "committed":
        _raise(
            "result_ir_v2_committed_role_invalid",
            "/input_bindings/committed_state_hash",
            "Final state must have committed role.",
        )
    if committed.parent_state_hash != trial.state_hash:
        _raise(
            "result_ir_v2_commit_lineage_invalid",
            "/input_bindings/committed_state_hash",
            "Committed StateIR must directly descend from the evaluated trial.",
        )
    scalar_fields = (
        "model_ir_content_hash",
        "solver_numeric_buffer_hash",
        "solver_entity_mapping_hash",
        "solver_artifact_hash",
        "execution_plan_hash",
        "operator_hash",
        "load_pattern_id",
        "epoch",
        "step",
        "load_factor",
        "time_s",
        "dof_count",
        "vector_hashes",
    )
    if any(
        getattr(trial, field_name) != getattr(committed, field_name)
        for field_name in scalar_fields
    ):
        _raise(
            "result_ir_v2_commit_state_mismatch",
            "/input_bindings/committed_state_hash",
            "Committed StateIR must preserve all evaluated trial fields.",
        )
    for field_name in ("displacement_si", "velocity_si", "acceleration_si"):
        if not np.array_equal(
            getattr(trial, field_name), getattr(committed, field_name)
        ):
            _raise(
                "result_ir_v2_commit_vector_mismatch",
                "/input_bindings/committed_state_hash",
                f"Committed StateIR does not preserve trial {field_name}.",
            )


def _validate_source_bindings(
    receipt: ResultIRV2,
    plan: ExecutionPlanV2,
    trial: StateIR,
    committed: StateIR,
) -> None:
    expected_bindings = ResultIRV2InputBindings(
        model_ir_content_hash=plan.model_ir_content_hash,
        solver_numeric_buffer_hash=plan.solver_numeric_buffer_hash,
        solver_entity_mapping_hash=plan.solver_entity_mapping_hash,
        solver_artifact_hash=plan.solver_artifact_hash,
        execution_plan_hash=plan.plan_hash,
        evaluated_trial_state_hash=trial.state_hash,
        committed_state_hash=committed.state_hash,
    )
    if receipt.input_bindings != expected_bindings:
        _raise(
            "result_ir_v2_input_binding_mismatch",
            "/input_bindings",
            "ResultIR v2 is bound to different plan or StateIR sources.",
        )
    expected_analysis = ResultIRV2Analysis(
        load_pattern_id=plan.load_pattern_id,
        operator_version=plan.operator_version,
        operator_hash=plan.operator_hash,
        recovery_operator_hash=plan.recovery_operator_hash,
    )
    if receipt.analysis != expected_analysis:
        _raise(
            "result_ir_v2_analysis_binding_mismatch",
            "/analysis",
            "Analysis bindings differ from ExecutionPlanV2.",
        )
    expected_ordering = ResultIRV2Ordering(
        node_ids=plan.node_ids,
        element_ids=plan.element_ids,
        constrained_dofs=plan.constrained_dofs,
        free_dofs=plan.free_dofs,
        ordering_hash=plan.ordering_hash,
    )
    if receipt.ordering != expected_ordering:
        _raise(
            "result_ir_v2_ordering_binding_mismatch",
            "/ordering",
            "Result ordering or constraint partition differs from ExecutionPlanV2.",
        )
    expected_shapes = {
        "displacements_si": (plan.node_count, _DOF_COUNT_PER_NODE),
        "residual_si": (plan.node_count, _DOF_COUNT_PER_NODE),
        "reactions_si": (plan.node_count, _DOF_COUNT_PER_NODE),
        "element_end_forces_local_si": (
            plan.element_count,
            2,
            _DOF_COUNT_PER_NODE,
        ),
        "element_strain_energy_j": (plan.element_count,),
        "exported_free_residual_si": (len(plan.free_dofs),),
    }
    for row in receipt.arrays.ordered():
        if row.shape != expected_shapes[row.name]:
            _raise(
                "result_ir_v2_array_shape_mismatch",
                f"/arrays/{row.name}/shape",
                f"Expected {expected_shapes[row.name]}, got {row.shape}.",
            )


def _recover_elements(
    plan: ExecutionPlanV2, displacement: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    global_dofs = plan.array("element_global_dofs")
    transforms = plan.array("recovery_transform_global_to_local")
    local_stiffness = plan.array("recovery_stiffness_local")
    expected_shapes = (
        global_dofs.shape == (plan.element_count, 12),
        transforms.shape == (plan.element_count, 12, 12),
        local_stiffness.shape == (plan.element_count, 12, 12),
    )
    if not all(expected_shapes):
        _raise(
            "result_ir_v2_recovery_shape_invalid",
            "/arrays/element_end_forces_local_si",
            "ExecutionPlanV2 recovery array shapes are invalid.",
        )
    forces = np.zeros((plan.element_count, 2, _DOF_COUNT_PER_NODE), dtype="<f8")
    energies = np.zeros(plan.element_count, dtype="<f8")
    for index in range(plan.element_count):
        local_displacement = transforms[index] @ displacement[global_dofs[index]]
        local_force = local_stiffness[index] @ local_displacement
        forces[index] = local_force.reshape(2, _DOF_COUNT_PER_NODE)
        energies[index] = 0.5 * float(local_displacement @ local_force)
    return forces, energies


def _energy_receipt(
    displacement: np.ndarray,
    residual: np.ndarray,
    load: np.ndarray,
    element_energy: np.ndarray,
) -> ResultIRV2Energy:
    element_sum = float(np.sum(element_energy))
    global_energy = 0.5 * float(displacement @ (residual + load))
    external_energy = 0.5 * float(displacement @ load)
    residual_energy = 0.5 * float(displacement @ residual)
    balance = global_energy - external_energy - residual_energy
    return ResultIRV2Energy(
        total_strain_energy_j=_normalize_scalar_zero(element_sum),
        element_strain_energy_sum_j=_normalize_scalar_zero(element_sum),
        global_strain_energy_j=_normalize_scalar_zero(global_energy),
        external_work_energy_j=_normalize_scalar_zero(external_energy),
        residual_work_energy_j=_normalize_scalar_zero(residual_energy),
        balance_error_j=_normalize_scalar_zero(balance),
    )


def _validate_energy_identities(energy: ResultIRV2Energy) -> None:
    _assert_scalar_close(
        energy.total_strain_energy_j,
        energy.element_strain_energy_sum_j,
        "result_ir_v2_element_energy_sum_identity_failed",
        "/energy/total_strain_energy_j",
        relative_tolerance=2.0e-11,
    )
    _assert_scalar_close(
        energy.total_strain_energy_j,
        energy.global_strain_energy_j,
        "result_ir_v2_global_energy_identity_failed",
        "/energy/global_strain_energy_j",
        relative_tolerance=2.0e-11,
    )
    expected_global = energy.external_work_energy_j + energy.residual_work_energy_j
    _assert_scalar_close(
        energy.global_strain_energy_j,
        expected_global,
        "result_ir_v2_residual_work_identity_failed",
        "/energy/residual_work_energy_j",
        relative_tolerance=2.0e-11,
    )
    _assert_scalar_close(
        energy.balance_error_j,
        0.0,
        "result_ir_v2_energy_balance_failed",
        "/energy/balance_error_j",
        relative_tolerance=2.0e-11,
    )


def _array_artifact(
    name: str,
    values: Any,
    *,
    axis_labels: tuple[str, ...],
    component_labels: tuple[str, ...],
    component_units: tuple[str, ...],
) -> ResultArrayV2:
    try:
        source = np.asarray(values, dtype="<f8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ResultIRV2Error(
            "result_ir_v2_array_value_invalid",
            f"/arrays/{name}/values",
            "Result array values cannot be represented as FP64.",
        ) from exc
    if source.ndim == 0 or any(value <= 0 for value in source.shape):
        _raise(
            "result_ir_v2_array_shape_invalid",
            f"/arrays/{name}/shape",
            "Result arrays must have non-empty dimensions.",
        )
    if len(axis_labels) != source.ndim:
        _raise(
            "result_ir_v2_array_axis_invalid",
            f"/arrays/{name}/axis_labels",
            "Axis label count must equal array rank.",
        )
    if not np.all(np.isfinite(source)):
        _raise(
            "result_ir_v2_array_nonfinite",
            f"/arrays/{name}/values",
            "Result arrays must contain only finite values.",
        )
    normalized = np.ascontiguousarray(source, dtype="<f8").copy()
    normalized[normalized == 0.0] = 0.0
    try:
        array = immutable_array(normalized, dtype="<f8")
    except CanonicalContractError as exc:  # pragma: no cover - preconditions above
        raise ResultIRV2Error(
            "result_ir_v2_array_storage_invalid", f"/arrays/{name}", str(exc)
        ) from exc
    metadata = _artifact_metadata(
        name=name,
        shape=tuple(int(value) for value in array.shape),
        axis_labels=axis_labels,
        component_labels=component_labels,
        component_units=component_units,
        byte_length=int(array.nbytes),
    )
    return ResultArrayV2(
        name=name,
        dtype="<f8",
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        axis_labels=axis_labels,
        component_labels=component_labels,
        component_units=component_units,
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
        _values=array,
    )


def _artifact_metadata(
    *,
    name: str,
    shape: tuple[int, ...],
    axis_labels: tuple[str, ...],
    component_labels: tuple[str, ...],
    component_units: tuple[str, ...],
    byte_length: int,
) -> dict[str, Any]:
    return {
        "name": name,
        "dtype": "<f8",
        "shape": list(shape),
        "layout": "C",
        "axis_labels": list(axis_labels),
        "component_labels": list(component_labels),
        "component_units": list(component_units),
        "byte_length": byte_length,
    }


def _validate_array_dataclass(row: ResultArrayV2) -> None:
    path = f"/arrays/{row.name}"
    if (
        type(row.name) is not str
        or type(row.dtype) is not str
        or type(row.shape) is not tuple
        or type(row.layout) is not str
        or type(row.axis_labels) is not tuple
        or type(row.component_labels) is not tuple
        or type(row.component_units) is not tuple
        or type(row._values) is not np.ndarray
        or any(type(value) is not int or value <= 0 for value in row.shape)
        or any(type(value) is not str or not value for value in row.axis_labels)
        or any(type(value) is not str or not value for value in row.component_labels)
        or any(type(value) is not str or not value for value in row.component_units)
        or type(row.byte_length) is not int
        or type(row.data_hash) is not str
        or type(row.content_hash) is not str
    ):
        _raise(
            "result_ir_v2_array_container_invalid",
            path,
            "Array artifact containers must use exact contract types.",
        )
    if (
        row.dtype != "<f8"
        or row.layout != "C"
        or row._values.dtype.str != "<f8"
        or not row._values.flags.c_contiguous
        or not has_immutable_bytes_backing(row._values)
    ):
        _raise(
            "result_ir_v2_array_storage_invalid",
            path,
            "Array values must be immutable bytes-backed C-order <f8.",
        )
    if np.any(np.signbit(row._values[row._values == 0.0])):
        _raise(
            "result_ir_v2_signed_zero_not_normalized",
            f"{path}/values",
            "ResultIR v2 arrays must normalize negative zero.",
        )
    expected = _array_artifact(
        row.name,
        row._values,
        axis_labels=row.axis_labels,
        component_labels=row.component_labels,
        component_units=row.component_units,
    )
    scalar_and_tuple_fields = (
        "name",
        "dtype",
        "shape",
        "layout",
        "axis_labels",
        "component_labels",
        "component_units",
        "byte_length",
        "data_hash",
        "content_hash",
    )
    if any(
        getattr(row, field_name) != getattr(expected, field_name)
        for field_name in scalar_and_tuple_fields
    ) or not np.array_equal(row._values, expected._values):
        _raise(
            "result_ir_v2_array_descriptor_mismatch",
            path,
            "Array bytes, metadata, or hashes are stale.",
        )


def _validate_source_provenance(provenance: SourceProvenance) -> None:
    if type(provenance) is not SourceProvenance:
        _raise(
            "result_ir_v2_provenance_type_invalid",
            "/source_provenance",
            "Expected exact SourceProvenance storage.",
        )
    _require_stable_id(provenance.case_id, "/source_provenance/case_id")
    for field_name in (
        "case_parity_receipt_hash",
        "terminal_observation_receipt_hash",
        "completion_export_receipt_hash",
        "completion_export_payload_hash",
        "device_identity_receipt_hash",
        "solution_payload_sha256",
        "exported_free_residual_payload_sha256",
    ):
        _require_hash(
            getattr(provenance, field_name),
            f"/source_provenance/{field_name}",
        )
    if (
        type(provenance.compiled_architecture) is not str
        or _ARCHITECTURE_PATTERN.fullmatch(provenance.compiled_architecture) is None
    ):
        _raise(
            "result_ir_v2_architecture_invalid",
            "/source_provenance/compiled_architecture",
            "Compiled HIP architecture is invalid.",
        )
    if (
        type(provenance.runtime_architecture_base) is not str
        or _ARCHITECTURE_BASE_PATTERN.fullmatch(provenance.runtime_architecture_base)
        is None
    ):
        _raise(
            "result_ir_v2_architecture_invalid",
            "/source_provenance/runtime_architecture_base",
            "Runtime HIP architecture base is invalid.",
        )
    if provenance.compiled_architecture.split(":", 1)[0] != (
        provenance.runtime_architecture_base
    ):
        _raise(
            "result_ir_v2_architecture_mismatch",
            "/source_provenance/runtime_architecture_base",
            "Compiled and runtime architecture bases differ.",
        )
    _require_index(provenance.device_ordinal, "/source_provenance/device_ordinal")
    if (
        type(provenance.device_uuid_bytes_hex) is not str
        or _UUID_PATTERN.fullmatch(provenance.device_uuid_bytes_hex) is None
        or provenance.device_uuid_bytes_hex == "0" * 32
    ):
        _raise(
            "result_ir_v2_device_uuid_invalid",
            "/source_provenance/device_uuid_bytes_hex",
            "Device UUID must be 16 non-zero lowercase hex bytes.",
        )
    if (
        type(provenance.device_pci_bdf) is not str
        or _PCI_BDF_PATTERN.fullmatch(provenance.device_pci_bdf) is None
    ):
        _raise(
            "result_ir_v2_device_pci_bdf_invalid",
            "/source_provenance/device_pci_bdf",
            "Device PCI BDF is invalid.",
        )
    if provenance.actual_backend != "hip":
        _raise(
            "result_ir_v2_backend_invalid",
            "/source_provenance/actual_backend",
            "Source backend must be HIP.",
        )
    if provenance.recovery_backend != "cpu_sparse_execution_plan_v2":
        _raise(
            "result_ir_v2_recovery_backend_invalid",
            "/source_provenance/recovery_backend",
            "Recovery backend must be CPU sparse ExecutionPlanV2 replay.",
        )
    for field_name in (
        "additional_device_operation_count",
        "additional_d2h_operation_count",
        "additional_solve_count",
        "additional_export_count",
        "fallback_count",
    ):
        if (
            type(getattr(provenance, field_name)) is not int
            or getattr(provenance, field_name) != 0
        ):
            _raise(
                "result_ir_v2_additional_operation_nonzero",
                f"/source_provenance/{field_name}",
                "Result recovery must perform zero additional device/export work.",
            )
    if type(provenance.live_authority_serialized) is not bool or (
        provenance.live_authority_serialized
    ):
        _raise(
            "result_ir_v2_live_authority_claim_invalid",
            "/source_provenance/live_authority_serialized",
            "Live process-local authority is not serialized in ResultIR v2.",
        )


def _validate_receipt_scalars(receipt: ResultIRV2) -> None:
    _require_stable_id(receipt.result_id, "/result_id")
    for field_name in receipt.input_bindings.__dataclass_fields__:
        _require_hash(
            getattr(receipt.input_bindings, field_name),
            f"/input_bindings/{field_name}",
        )
    _require_stable_id(receipt.analysis.load_pattern_id, "/analysis/load_pattern_id")
    if type(receipt.analysis.operator_version) is not str:
        _raise(
            "result_ir_v2_scalar_type_invalid",
            "/analysis/operator_version",
            "Operator version must be an exact string.",
        )
    for field_name in ("operator_hash", "recovery_operator_hash"):
        _require_hash(getattr(receipt.analysis, field_name), f"/analysis/{field_name}")
    if (
        any(type(value) is not str for value in receipt.ordering.node_ids)
        or any(type(value) is not str for value in receipt.ordering.element_ids)
        or any(type(value) is not int for value in receipt.ordering.constrained_dofs)
        or any(type(value) is not int for value in receipt.ordering.free_dofs)
    ):
        _raise(
            "result_ir_v2_scalar_type_invalid",
            "/ordering",
            "Ordering IDs and indices must use exact scalar types.",
        )
    for value in (*receipt.ordering.node_ids, *receipt.ordering.element_ids):
        _require_stable_id(value, "/ordering")
    for value in (*receipt.ordering.constrained_dofs, *receipt.ordering.free_dofs):
        _require_index(value, "/ordering")
    _require_hash(receipt.ordering.ordering_hash, "/ordering/ordering_hash")

    convergence_fields = (
        "requested_residual_tolerance",
        "free_residual_linf",
        "exported_free_residual_linf",
        "load_scale",
        "scaled_free_residual",
        "scaled_exported_free_residual",
    )
    for field_name in convergence_fields:
        value = getattr(receipt.convergence, field_name)
        _require_exact_finite_float(value, f"/convergence/{field_name}")
        if value == 0.0 and math.copysign(1.0, value) < 0.0:
            _raise(
                "result_ir_v2_signed_zero_not_normalized",
                f"/convergence/{field_name}",
                "Convergence scalars must normalize negative zero.",
            )
    if type(receipt.convergence.converged) is not bool or not (
        receipt.convergence.converged
    ):
        _raise(
            "result_ir_v2_claim_invalid",
            "/convergence/converged",
            "Successful ResultIR v2 must be converged.",
        )
    if (
        receipt.convergence.requested_residual_tolerance <= 0.0
        or receipt.convergence.load_scale < 1.0
        or receipt.convergence.free_residual_linf < 0.0
        or receipt.convergence.exported_free_residual_linf < 0.0
        or receipt.convergence.scaled_free_residual < 0.0
        or receipt.convergence.scaled_exported_free_residual < 0.0
        or receipt.convergence.scaled_free_residual
        > receipt.convergence.requested_residual_tolerance
        or receipt.convergence.scaled_exported_free_residual
        > receipt.convergence.requested_residual_tolerance
    ):
        _raise(
            "result_ir_v2_convergence_invalid",
            "/convergence",
            "Convergence scalars are inconsistent with a successful receipt.",
        )
    for field_name in receipt.energy.__dataclass_fields__:
        value = getattr(receipt.energy, field_name)
        _require_exact_finite_float(value, f"/energy/{field_name}")
        if value == 0.0 and math.copysign(1.0, value) < 0.0:
            _raise(
                "result_ir_v2_signed_zero_not_normalized",
                f"/energy/{field_name}",
                "Energy scalars must normalize negative zero.",
            )
    _validate_energy_identities(receipt.energy)
    expected_claims = ResultIRV2Claims()
    for field_name in receipt.claims.__dataclass_fields__:
        value = getattr(receipt.claims, field_name)
        if type(value) is not bool or value is not getattr(expected_claims, field_name):
            _raise(
                "result_ir_v2_claim_invalid",
                f"/claims/{field_name}",
                "ResultIR v2 claim boundary is fixed and non-promoting.",
            )
    _require_hash(receipt.numerical_result_hash, "/numerical_result_hash")
    _require_hash(receipt.result_ir_hash, "/result_ir_hash")


def _validate_manifest_scalars(manifest: Mapping[str, Any]) -> None:
    ordering = manifest["ordering"]
    for field_name in ("constrained_dofs", "free_dofs"):
        if any(type(value) is not int for value in ordering[field_name]):
            _raise(
                "result_ir_v2_scalar_type_invalid",
                f"/ordering/{field_name}",
                "Serialized DOF indices must be exact integers.",
            )
    for name, row in manifest["arrays"].items():
        if (
            any(type(value) is not int for value in row["shape"])
            or type(row["byte_length"]) is not int
        ):
            _raise(
                "result_ir_v2_scalar_type_invalid",
                f"/arrays/{name}",
                "Serialized array extents and byte length must be exact integers.",
            )

    convergence = manifest["convergence"]
    for field_name in (
        "requested_residual_tolerance",
        "free_residual_linf",
        "exported_free_residual_linf",
        "load_scale",
        "scaled_free_residual",
        "scaled_exported_free_residual",
    ):
        value = convergence[field_name]
        if type(value) is not float:
            _raise(
                "result_ir_v2_scalar_type_invalid",
                f"/convergence/{field_name}",
                "Expected an exact finite FP64 JSON number.",
            )
        scalar = float(value)
        if not math.isfinite(scalar):
            _raise(
                "result_ir_v2_scalar_nonfinite",
                f"/convergence/{field_name}",
                "Convergence scalar must be finite.",
            )
        if scalar == 0.0 and math.copysign(1.0, scalar) < 0.0:
            _raise(
                "result_ir_v2_signed_zero_not_normalized",
                f"/convergence/{field_name}",
                "Convergence scalars must normalize negative zero.",
            )
    if (
        convergence["scaled_free_residual"]
        > convergence["requested_residual_tolerance"]
        or convergence["scaled_exported_free_residual"]
        > convergence["requested_residual_tolerance"]
    ):
        _raise(
            "result_ir_v2_convergence_invalid",
            "/convergence",
            "Serialized convergence scalars contradict converged=true.",
        )
    energy = manifest["energy"]
    for field_name, value in energy.items():
        if type(value) is not float:
            _raise(
                "result_ir_v2_scalar_type_invalid",
                f"/energy/{field_name}",
                "Expected an exact finite FP64 JSON number.",
            )
        scalar = float(value)
        if not math.isfinite(scalar):
            _raise(
                "result_ir_v2_scalar_nonfinite",
                f"/energy/{field_name}",
                "Energy scalar must be finite.",
            )
        if scalar == 0.0 and math.copysign(1.0, scalar) < 0.0:
            _raise(
                "result_ir_v2_signed_zero_not_normalized",
                f"/energy/{field_name}",
                "Energy scalars must normalize negative zero.",
            )
    scale = max(1.0, *(abs(float(value)) for value in energy.values()))
    tolerance = 2.0e-11 * scale
    if (
        abs(energy["total_strain_energy_j"] - energy["element_strain_energy_sum_j"])
        > tolerance
        or abs(energy["total_strain_energy_j"] - energy["global_strain_energy_j"])
        > tolerance
        or abs(
            energy["global_strain_energy_j"]
            - energy["external_work_energy_j"]
            - energy["residual_work_energy_j"]
        )
        > tolerance
        or abs(energy["balance_error_j"]) > tolerance
    ):
        _raise(
            "result_ir_v2_energy_identity_failed",
            "/energy",
            "Serialized energy and residual-work identities are inconsistent.",
        )

    provenance = manifest["source_provenance"]
    if type(provenance["device_ordinal"]) is not int:
        _raise(
            "result_ir_v2_scalar_type_invalid",
            "/source_provenance/device_ordinal",
            "Device ordinal must be an exact integer.",
        )
    for field_name in (
        "additional_device_operation_count",
        "additional_d2h_operation_count",
        "additional_solve_count",
        "additional_export_count",
        "fallback_count",
    ):
        if type(provenance[field_name]) is not int or provenance[field_name] != 0:
            _raise(
                "result_ir_v2_scalar_type_invalid",
                f"/source_provenance/{field_name}",
                "Additional-operation counters must be exact integer zero.",
            )
    if type(provenance["live_authority_serialized"]) is not bool:
        _raise(
            "result_ir_v2_scalar_type_invalid",
            "/source_provenance/live_authority_serialized",
            "Live-authority serialization flag must be an exact boolean.",
        )
    if any(type(value) is not bool for value in manifest["claims"].values()):
        _raise(
            "result_ir_v2_scalar_type_invalid",
            "/claims",
            "Serialized claims must be exact booleans.",
        )
    for field_name in ("global_dense_matrix_materialized", "linear_solve_invoked"):
        if type(manifest["recovery"][field_name]) is not bool:
            _raise(
                "result_ir_v2_scalar_type_invalid",
                f"/recovery/{field_name}",
                "Recovery flags must be exact booleans.",
            )


def _finite_flat_vector(value: Any, count: int, path: str) -> np.ndarray:
    try:
        vector = np.asarray(value, dtype="<f8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ResultIRV2Error(
            "result_ir_v2_vector_invalid",
            path,
            "Expected a finite FP64 vector.",
        ) from exc
    if vector.ndim != 1 or vector.shape != (count,):
        _raise(
            "result_ir_v2_vector_shape_invalid",
            path,
            f"Expected a flat vector with {count} entries.",
        )
    if not np.all(np.isfinite(vector)):
        _raise(
            "result_ir_v2_vector_nonfinite", path, "Vector contains NaN or Infinity."
        )
    normalized = np.ascontiguousarray(vector, dtype="<f8").copy()
    normalized[normalized == 0.0] = 0.0
    return normalized


def _validate_manifest_array_metadata(manifest: Mapping[str, Any]) -> None:
    """Validate descriptor-only serialized array layout without duplicating data."""

    ordering = manifest["ordering"]
    node_count = len(ordering["node_ids"])
    element_count = len(ordering["element_ids"])
    dof_count = node_count * _DOF_COUNT_PER_NODE
    constrained = tuple(ordering["constrained_dofs"])
    free = tuple(ordering["free_dofs"])
    if (
        not constrained
        or not free
        or tuple(sorted(constrained)) != constrained
        or tuple(sorted(free)) != free
        or len(set(constrained)) != len(constrained)
        or len(set(free)) != len(free)
        or sorted((*constrained, *free)) != list(range(dof_count))
    ):
        _raise(
            "result_ir_v2_partition_invalid",
            "/ordering",
            "Serialized constrained/free DOFs must form a sorted disjoint cover.",
        )
    free_components = [DOF_ORDER[index % _DOF_COUNT_PER_NODE] for index in free]
    free_units = [_FORCE_UNITS[index % _DOF_COUNT_PER_NODE] for index in free]
    expected: dict[str, tuple[list[int], list[str], list[str], list[str]]] = {
        "displacements_si": (
            [node_count, _DOF_COUNT_PER_NODE],
            ["node", "dof"],
            list(DOF_ORDER),
            list(_DISPLACEMENT_UNITS),
        ),
        "residual_si": (
            [node_count, _DOF_COUNT_PER_NODE],
            ["node", "dof"],
            list(DOF_ORDER),
            list(_FORCE_UNITS),
        ),
        "reactions_si": (
            [node_count, _DOF_COUNT_PER_NODE],
            ["node", "dof"],
            list(DOF_ORDER),
            list(_FORCE_UNITS),
        ),
        "element_end_forces_local_si": (
            [element_count, 2, _DOF_COUNT_PER_NODE],
            ["element", "end", "dof"],
            list(DOF_ORDER),
            list(_FORCE_UNITS),
        ),
        "element_strain_energy_j": (
            [element_count],
            ["element"],
            ["strain_energy"],
            ["J"],
        ),
        "exported_free_residual_si": (
            [len(free)],
            ["free_dof"],
            free_components,
            free_units,
        ),
    }
    for name, (shape, axes, components, units) in expected.items():
        row = manifest["arrays"][name]
        if (
            row["name"] != name
            or row["shape"] != shape
            or row["axis_labels"] != axes
            or row["component_labels"] != components
            or row["component_units"] != units
            or row["byte_length"] != math.prod(shape) * 8
        ):
            _raise(
                "result_ir_v2_array_descriptor_mismatch",
                f"/arrays/{name}",
                "Descriptor-only array metadata is inconsistent with ordering.",
            )


def _numerical_hash(
    arrays: ResultIRV2Arrays,
    convergence: ResultIRV2Convergence,
    energy: ResultIRV2Energy,
) -> str:
    return canonical_hash(
        {
            "contract": "engine-v2-result-ir-numerical.v2",
            "arrays": [
                {
                    "name": row.name,
                    "data_hash": row.data_hash,
                    "content_hash": row.content_hash,
                }
                for row in arrays.ordered()
            ],
            "convergence": convergence.to_dict(),
            "energy": energy.to_dict(),
        }
    )


def _numerical_hash_from_manifest(manifest: Mapping[str, Any]) -> str:
    return canonical_hash(
        {
            "contract": "engine-v2-result-ir-numerical.v2",
            "arrays": [
                {
                    "name": name,
                    "data_hash": manifest["arrays"][name]["data_hash"],
                    "content_hash": manifest["arrays"][name]["content_hash"],
                }
                for name in _ARRAY_NAMES
            ],
            "convergence": manifest["convergence"],
            "energy": manifest["energy"],
        }
    )


def _receipt_hash(manifest: Mapping[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("result_ir_hash", None)
    return canonical_hash(payload)


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
        _raise(
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
        _raise(code, path, f"{message} Maximum difference is {difference:.17g}.")


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
        _raise(code, path, f"Expected {expected:.17g}, got {actual:.17g}.")


def _require_hash(value: Any, path: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        _raise(
            "result_ir_v2_hash_invalid",
            path,
            "Expected sha256:<64 lowercase hex>.",
        )
    return value


def _require_stable_id(value: Any, path: str) -> str:
    if type(value) is not str or _STABLE_ID_PATTERN.fullmatch(value) is None:
        _raise("result_ir_v2_stable_id_invalid", path, "Invalid stable identifier.")
    return value


def _require_index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_INDEX:
        _raise(
            "result_ir_v2_index_invalid",
            path,
            f"Expected an integer within [0, {_MAX_INDEX}].",
        )
    return value


def _require_exact_finite_float(value: Any, path: str) -> float:
    if type(value) is not float or not math.isfinite(value):
        _raise(
            "result_ir_v2_scalar_type_invalid",
            path,
            "Expected an exact finite float.",
        )
    return value


def _normalize_scalar_zero(value: float) -> float:
    return 0.0 if value == 0.0 else value


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).resolve().parents[2] / "schemas" / "result_ir_v2.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _raise(code: str, path: str, message: str) -> None:
    raise ResultIRV2Error(code, path, message)


__all__ = [
    "RESULT_IR_V2_CAPABILITY_PROFILE",
    "RESULT_IR_V2_SCHEMA_VERSION",
    "ResultArrayV2",
    "ResultIRV2",
    "ResultIRV2Analysis",
    "ResultIRV2Arrays",
    "ResultIRV2Claims",
    "ResultIRV2Convergence",
    "ResultIRV2Energy",
    "ResultIRV2Error",
    "ResultIRV2InputBindings",
    "ResultIRV2Ordering",
    "ResultIRV2SourceProvenance",
    "ResultIRV2ValidationError",
    "SourceProvenance",
    "build_result_ir_v2",
    "validate_result_ir_v2",
    "validate_result_ir_v2_against_sources",
    "validate_result_ir_v2_manifest",
    "validate_result_ir_v2_physics",
]
