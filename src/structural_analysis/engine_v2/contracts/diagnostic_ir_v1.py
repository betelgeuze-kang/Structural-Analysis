"""HIP-source-bound nonconverged FGMRES partial-iterate diagnostic receipt.

``DiagnosticIRV1`` is deliberately not a solution or a result contract.  It
preserves the exact iterate produced when a bounded FGMRES policy exhausts
``max_iterations``, binds that iterate to an evaluated (but uncommitted)
``StateIR`` trial, and records enough detached metadata for strict replay.

The numerical arrays and state semantics are backend-independent, while this
v1 provenance profile deliberately requires an exact HIP source and ``gfx``
device lineage.  A future backend-neutral provenance union requires a new
profile rather than weakening this schema.

The serialized manifest contains array descriptors and byte commitments only;
the immutable array bytes remain process-local to the typed receipt.  Serialized
provenance is a detached commitment, not live HIP authority, so the public
builder emits ``diagnostic_ready=false`` and leaves raw-source preservation
claims false.  A backend-specific bridge must validate retained live authority
and use the private exact-object issuer before those scoped claims become true.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
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
from .state_ir import (
    StateIR,
    StateIRError,
    create_initial_state,
    rollback_trial_state,
    validate_state_ir,
)

DIAGNOSTIC_IR_V1_SCHEMA_VERSION = "structural-analysis-diagnostic-ir.v1"
DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE = (
    "hip_source_bound_fgmres_max_iterations_partial_iterate"
)
FGMRES_POLICY_V1_SCHEMA_VERSION = "structural-analysis-fgmres-policy.v1"

_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_BACKEND_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_ARCHITECTURE_PATTERN = re.compile(r"^gfx[0-9a-f]+(?::[A-Za-z0-9_+.-]+)*$")
_ARCHITECTURE_BASE_PATTERN = re.compile(r"^gfx[0-9a-f]+$")
_UUID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_PCI_BDF_PATTERN = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$")
_MAX_INDEX = int(np.iinfo(np.int32).max)
_DOF_COUNT_PER_NODE = len(DOF_ORDER)
_FORCE_UNITS = ("N", "N", "N", "N*m", "N*m", "N*m")
_DISPLACEMENT_UNITS = ("m", "m", "m", "rad", "rad", "rad")
_ARRAY_NAMES = (
    "partial_displacement_si",
    "residual_si",
    "exported_free_residual_si",
)
_SOURCE_L2_RELATIVE_TOLERANCE = 64.0 * float(np.finfo(np.float64).eps)


class DiagnosticIRV1Error(ValueError):
    """Stable fail-closed DiagnosticIR v1 contract or physics error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True, slots=True)
class DiagnosticArrayV1:
    """One immutable little-endian FP64 diagnostic array."""

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
class DiagnosticIRV1InputBindings:
    model_ir_content_hash: str
    solver_numeric_buffer_hash: str
    solver_entity_mapping_hash: str
    solver_artifact_hash: str
    execution_plan_hash: str
    accepted_state_hash: str
    evaluated_trial_state_hash: str
    committed_state_hash: None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DiagnosticIRV1Analysis:
    load_pattern_id: str
    operator_version: str
    operator_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "linear_static",
            "status": "not_ready_nonconverged",
            "state_disposition": "evaluated_trial_not_committed",
            "load_pattern_id": self.load_pattern_id,
            "residual_sign": "internal_minus_external",
            "exported_free_residual_sign": "external_minus_internal",
            "operator_version": self.operator_version,
            "operator_hash": self.operator_hash,
        }


@dataclass(frozen=True, slots=True)
class DiagnosticIRV1Ordering:
    node_ids: tuple[str, ...]
    constrained_dofs: tuple[int, ...]
    free_dofs: tuple[int, ...]
    ordering_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_ids": list(self.node_ids),
            "dof_components": list(DOF_ORDER),
            "constrained_dofs": list(self.constrained_dofs),
            "free_dofs": list(self.free_dofs),
            "ordering_hash": self.ordering_hash,
        }


@dataclass(frozen=True, slots=True)
class DiagnosticIRV1Arrays:
    partial_displacement_si: DiagnosticArrayV1
    residual_si: DiagnosticArrayV1
    exported_free_residual_si: DiagnosticArrayV1

    @property
    def full_partial_displacement_si(self) -> DiagnosticArrayV1:
        return self.partial_displacement_si

    @property
    def full_residual_si(self) -> DiagnosticArrayV1:
        return self.residual_si

    @property
    def exported_free_true_residual_si(self) -> DiagnosticArrayV1:
        return self.exported_free_residual_si

    def ordered(self) -> tuple[DiagnosticArrayV1, ...]:
        return tuple(getattr(self, name) for name in _ARRAY_NAMES)

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {row.name: row.to_dict() for row in self.ordered()}


@dataclass(frozen=True, slots=True)
class DiagnosticIRV1Policy:
    restart_dimension: int
    max_iterations: int
    absolute_tolerance: float
    relative_tolerance: float
    stagnation_checkpoint_limit: int
    stagnation_relative_tolerance: float
    divergence_factor: float
    policy_hash: str

    @property
    def schema_version(self) -> str:
        return FGMRES_POLICY_V1_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _policy_payload(self, include_hash=True)


@dataclass(frozen=True, slots=True)
class DiagnosticIRV1Counters:
    iteration_count: int
    restart_count: int
    operator_apply_count: int
    preconditioner_apply_count: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DiagnosticIRV1Metrics:
    initial_residual_l2: float
    solver_tolerance_l2: float
    final_residual_l2: float
    final_residual_linf: float
    scaled_true_residual: float
    load_scale: float
    free_residual_l2: float
    free_residual_linf: float
    scaled_free_residual: float
    exported_free_residual_l2: float
    exported_free_residual_linf: float
    scaled_exported_free_residual: float
    solver_tolerance_passed: Literal[False] = False
    authoritative_plan_tolerance_passed: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DiagnosticIRV1RestartRecord:
    restart_index: int
    start_iteration: int
    end_iteration: int
    arnoldi_step_count: int
    preconditioner_apply_count: int
    reorthogonalization_count: int
    estimated_residual_l2: float
    true_residual_l2: float
    true_residual_linf: float
    scaled_true_residual: float
    solution_update_l2: float
    termination_hint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DiagnosticIRV1Termination:
    policy: DiagnosticIRV1Policy
    counters: DiagnosticIRV1Counters
    metrics: DiagnosticIRV1Metrics
    history: tuple[DiagnosticIRV1RestartRecord, ...]
    status: Literal["max_iterations"] = "max_iterations"
    termination_code: Literal["max_iterations_exhausted"] = "max_iterations_exhausted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "termination_code": self.termination_code,
            "policy": self.policy.to_dict(),
            "counters": self.counters.to_dict(),
            "metrics": self.metrics.to_dict(),
            "history": [row.to_dict() for row in self.history],
        }


@dataclass(frozen=True, slots=True)
class DiagnosticSourceProvenanceV1:
    """Detached source commitments; never serialized live authority."""

    case_id: str
    case_parity_receipt_hash: str
    terminal_observation_receipt_hash: str
    completion_export_receipt_hash: str
    completion_export_payload_hash: str
    device_identity_receipt_hash: str
    source_schema_version: str
    cpu_result_hash: str
    terminal_outcome_hash: str
    terminal_observation_id: str
    completion_export_context_id: str
    source_binding_hash: str
    actual_backend: str
    solution_payload_sha256: str
    exported_free_residual_payload_sha256: str
    solve_record_payload_sha256: str
    compiled_architecture: str
    runtime_architecture_base: str
    device_ordinal: int
    device_uuid_bytes_hex: str
    device_pci_bdf: str
    source_kind: Literal["fgmres_partial_iterate"] = "fgmres_partial_iterate"
    additional_device_operation_count: Literal[0] = 0
    additional_d2h_operation_count: Literal[0] = 0
    additional_solve_count: Literal[0] = 0
    additional_export_count: Literal[0] = 0
    fallback_count: Literal[0] = 0
    live_authority_serialized: Literal[False] = False
    signed_evidence: Literal[False] = False
    standalone_provenance: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DiagnosticIRV1Claims:
    diagnostic_ready: bool = False
    diagnostic_ir_verified: Literal[True] = True
    partial_iterate_preserved: bool = False
    nonconverged_max_iterations_verified: bool = False
    evaluated_trial_state_verified: Literal[True] = True
    true_residual_replayed: Literal[True] = True
    restart_history_preserved: bool = False
    rollback_to_accepted_state_verified: Literal[True] = True
    committed_state_created: Literal[False] = False
    analysis_state_committed: Literal[False] = False
    solution_ready: Literal[False] = False
    result_ir_ready: Literal[False] = False
    restart_checkpoint_ready: Literal[False] = False
    code_check_ready: Literal[False] = False
    optimization_consumable: Literal[False] = False
    reaction_recovery_verified: Literal[False] = False
    member_force_recovery_verified: Literal[False] = False
    energy_identities_verified: Literal[False] = False
    device_execution_verified: Literal[False] = False
    iteration_host_copy_zero_proven: Literal[False] = False
    end_to_end_o_n_proven: Literal[False] = False
    performance_or_speedup_proven: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False
    signed_evidence: Literal[False] = False
    standalone_provenance: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


_DIAGNOSTIC_IR_V1_READY_MINT = object()


@dataclass(frozen=True, slots=True)
class _DiagnosticIRV1ReadyAuthority:
    """Non-serialized identity seal issued by the retained-source bridge."""

    receipt_identity: int
    diagnostic_ir_hash: str
    _mint: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class DiagnosticIRV1:
    """Immutable nonconverged partial-iterate diagnostic receipt."""

    diagnostic_id: str
    input_bindings: DiagnosticIRV1InputBindings
    analysis: DiagnosticIRV1Analysis
    ordering: DiagnosticIRV1Ordering
    arrays: DiagnosticIRV1Arrays
    termination: DiagnosticIRV1Termination
    source_provenance: DiagnosticSourceProvenanceV1
    claims: DiagnosticIRV1Claims
    numerical_diagnostic_hash: str
    diagnostic_ir_hash: str
    _diagnostic_ir_ready_authority: _DiagnosticIRV1ReadyAuthority | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    @property
    def schema_version(self) -> str:
        return DIAGNOSTIC_IR_V1_SCHEMA_VERSION

    @property
    def capability_profile(self) -> str:
        return DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capability_profile": self.capability_profile,
            "diagnostic_id": self.diagnostic_id,
            "input_bindings": self.input_bindings.to_dict(),
            "analysis": self.analysis.to_dict(),
            "ordering": self.ordering.to_dict(),
            "arrays": self.arrays.to_dict(),
            "termination": self.termination.to_dict(),
            "state_lifecycle": {
                "accepted_state_role": "committed",
                "evaluated_state_role": "trial",
                "accepted_state_preserved": True,
                "evaluated_trial_committed": False,
                "committed_state_hash": None,
                "rollback_result": "accepted_state_retained",
            },
            "source_provenance": self.source_provenance.to_dict(),
            "claims": self.claims.to_dict(),
            "numerical_diagnostic_hash": self.numerical_diagnostic_hash,
            "diagnostic_ir_hash": self.diagnostic_ir_hash,
            "extensions": {},
        }

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


def build_diagnostic_ir_v1(
    plan: ExecutionPlanV2,
    accepted_state: StateIR,
    evaluated_trial_state: StateIR,
    full_partial_displacement_si: Any,
    exported_free_residual_si: Any,
    termination: DiagnosticIRV1Termination,
    source_provenance: DiagnosticSourceProvenanceV1,
    *,
    diagnostic_id: str = "Diagnostic.max-iterations.v1",
) -> DiagnosticIRV1:
    """Build a replayable diagnostic without creating a committed state."""

    _validate_exact_sources(plan, accepted_state, evaluated_trial_state)
    _validate_termination(termination)
    _validate_source_provenance(source_provenance)
    _require_stable_id(diagnostic_id, "/diagnostic_id")

    displacement = _finite_flat_vector(
        full_partial_displacement_si,
        plan.dof_count,
        "/arrays/partial_displacement_si/values",
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
            "diagnostic_ir_v1_constrained_displacement_nonzero",
            "/arrays/partial_displacement_si",
            "Constrained partial-displacement entries must be exactly zero.",
        )
    try:
        residual = np.ascontiguousarray(plan.residual(displacement), dtype="<f8")
    except (TypeError, ValueError, FloatingPointError, OverflowError) as exc:
        raise DiagnosticIRV1Error(
            "diagnostic_ir_v1_residual_replay_failed",
            "/arrays/residual_si",
            f"ExecutionPlanV2 residual replay failed: {exc}",
        ) from exc
    if residual.shape != (plan.dof_count,) or not np.isfinite(residual).all():
        _raise(
            "diagnostic_ir_v1_residual_replay_invalid",
            "/arrays/residual_si",
            "ExecutionPlanV2 residual replay returned an invalid vector.",
        )
    residual[residual == 0.0] = 0.0

    free_components = tuple(
        DOF_ORDER[int(index) % _DOF_COUNT_PER_NODE] for index in free
    )
    free_units = tuple(_FORCE_UNITS[int(index) % _DOF_COUNT_PER_NODE] for index in free)
    global_components = tuple(
        DOF_ORDER[index % _DOF_COUNT_PER_NODE] for index in range(plan.dof_count)
    )
    global_displacement_units = tuple(
        _DISPLACEMENT_UNITS[index % _DOF_COUNT_PER_NODE]
        for index in range(plan.dof_count)
    )
    global_force_units = tuple(
        _FORCE_UNITS[index % _DOF_COUNT_PER_NODE] for index in range(plan.dof_count)
    )
    arrays = DiagnosticIRV1Arrays(
        partial_displacement_si=_array_artifact(
            "partial_displacement_si",
            displacement,
            axis_labels=("global_dof",),
            component_labels=global_components,
            component_units=global_displacement_units,
        ),
        residual_si=_array_artifact(
            "residual_si",
            residual,
            axis_labels=("global_dof",),
            component_labels=global_components,
            component_units=global_force_units,
        ),
        exported_free_residual_si=_array_artifact(
            "exported_free_residual_si",
            exported,
            axis_labels=("free_dof",),
            component_labels=free_components,
            component_units=free_units,
        ),
    )
    receipt = DiagnosticIRV1(
        diagnostic_id=diagnostic_id,
        input_bindings=DiagnosticIRV1InputBindings(
            model_ir_content_hash=plan.model_ir_content_hash,
            solver_numeric_buffer_hash=plan.solver_numeric_buffer_hash,
            solver_entity_mapping_hash=plan.solver_entity_mapping_hash,
            solver_artifact_hash=plan.solver_artifact_hash,
            execution_plan_hash=plan.plan_hash,
            accepted_state_hash=accepted_state.state_hash,
            evaluated_trial_state_hash=evaluated_trial_state.state_hash,
        ),
        analysis=DiagnosticIRV1Analysis(
            load_pattern_id=plan.load_pattern_id,
            operator_version=plan.operator_version,
            operator_hash=plan.operator_hash,
        ),
        ordering=DiagnosticIRV1Ordering(
            node_ids=plan.node_ids,
            constrained_dofs=tuple(int(value) for value in constrained),
            free_dofs=tuple(int(value) for value in free),
            ordering_hash=plan.ordering_hash,
        ),
        arrays=arrays,
        termination=termination,
        source_provenance=source_provenance,
        claims=DiagnosticIRV1Claims(),
        numerical_diagnostic_hash=_numerical_hash(arrays, termination),
        diagnostic_ir_hash="sha256:" + "0" * 64,
    )
    receipt = replace(receipt, diagnostic_ir_hash=_receipt_hash(receipt.to_dict()))
    return validate_diagnostic_ir_v1_physics(
        receipt,
        expected_plan=plan,
        expected_accepted_state=accepted_state,
        expected_evaluated_trial_state=evaluated_trial_state,
    )


def _issue_bridge_diagnostic_ir_v1_ready(receipt: DiagnosticIRV1) -> DiagnosticIRV1:
    """Issue scoped raw-source claims for one exact bridge-returned object.

    This private hook is intentionally absent from every public ``__all__``.
    The retained-source bridge calls it only after its second live-authority
    capture succeeds.  The identity seal is integrity metadata, not a security
    boundary against hostile code executing in the same Python process.
    """

    validate_diagnostic_ir_v1(receipt)
    if receipt.claims.diagnostic_ready:
        _raise(
            "diagnostic_ir_v1_ready_authority_already_issued",
            "/claims/diagnostic_ready",
            "Only a generic not-ready DiagnosticIR v1 can receive bridge authority.",
        )
    issued = replace(
        receipt,
        claims=replace(
            receipt.claims,
            diagnostic_ready=True,
            partial_iterate_preserved=True,
            nonconverged_max_iterations_verified=True,
            restart_history_preserved=True,
        ),
        diagnostic_ir_hash="sha256:" + "0" * 64,
    )
    issued = replace(issued, diagnostic_ir_hash=_receipt_hash(issued.to_dict()))
    authority = _DiagnosticIRV1ReadyAuthority(
        receipt_identity=id(issued),
        diagnostic_ir_hash=issued.diagnostic_ir_hash,
        _mint=_DIAGNOSTIC_IR_V1_READY_MINT,
    )
    object.__setattr__(issued, "_diagnostic_ir_ready_authority", authority)
    return validate_diagnostic_ir_v1(issued)


def _has_bridge_diagnostic_ir_ready_authority(receipt: DiagnosticIRV1) -> bool:
    authority = receipt._diagnostic_ir_ready_authority
    return (
        type(authority) is _DiagnosticIRV1ReadyAuthority
        and authority._mint is _DIAGNOSTIC_IR_V1_READY_MINT
        and authority.receipt_identity == id(receipt)
        and authority.diagnostic_ir_hash == receipt.diagnostic_ir_hash
    )


def validate_diagnostic_ir_v1(receipt: DiagnosticIRV1) -> DiagnosticIRV1:
    """Validate exact dataclass storage and detached commitments."""

    if type(receipt) is not DiagnosticIRV1:
        _raise("diagnostic_ir_v1_type_invalid", "/", "Expected exact DiagnosticIRV1.")
    exact_nested = (
        (receipt.input_bindings, DiagnosticIRV1InputBindings, "/input_bindings"),
        (receipt.analysis, DiagnosticIRV1Analysis, "/analysis"),
        (receipt.ordering, DiagnosticIRV1Ordering, "/ordering"),
        (receipt.arrays, DiagnosticIRV1Arrays, "/arrays"),
        (receipt.termination, DiagnosticIRV1Termination, "/termination"),
        (
            receipt.source_provenance,
            DiagnosticSourceProvenanceV1,
            "/source_provenance",
        ),
        (receipt.claims, DiagnosticIRV1Claims, "/claims"),
    )
    for value, expected_type, path in exact_nested:
        if type(value) is not expected_type:
            _raise(
                "diagnostic_ir_v1_container_invalid",
                path,
                f"Expected exact {expected_type.__name__} storage.",
            )
    _validate_receipt_scalars(receipt)
    if (
        type(receipt.ordering.node_ids) is not tuple
        or type(receipt.ordering.constrained_dofs) is not tuple
        or type(receipt.ordering.free_dofs) is not tuple
    ):
        _raise(
            "diagnostic_ir_v1_container_invalid",
            "/ordering",
            "Ordering containers must be exact tuples.",
        )
    artifacts = receipt.arrays.ordered()
    if any(type(row) is not DiagnosticArrayV1 for row in artifacts):
        _raise(
            "diagnostic_ir_v1_container_invalid",
            "/arrays",
            "All arrays must use exact DiagnosticArrayV1 storage.",
        )
    for row in artifacts:
        _validate_array_dataclass(row)
    _validate_termination(receipt.termination)
    _validate_source_provenance(receipt.source_provenance)
    _validate_diagnostic_ir_v1_manifest(
        receipt.to_dict(),
        allow_diagnostic_ready=receipt.claims.diagnostic_ready,
    )
    return receipt


def validate_diagnostic_ir_v1_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate a detached descriptor-only JSON-shaped manifest.

    Serialized data cannot retain exact process-local bridge identity, so this
    public validator accepts only the generic not-ready claim boundary.
    """

    _validate_diagnostic_ir_v1_manifest(manifest, allow_diagnostic_ready=False)


def _validate_diagnostic_ir_v1_manifest(
    manifest: Mapping[str, Any],
    *,
    allow_diagnostic_ready: bool,
) -> None:
    """Validate one manifest within an explicitly established authority scope."""

    if type(manifest) is not dict:
        _raise(
            "diagnostic_ir_v1_manifest_type_invalid",
            "/",
            "Serialized DiagnosticIR v1 must be an exact dictionary.",
        )
    errors = sorted(
        _schema_validator().iter_errors(manifest),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _raise("diagnostic_ir_v1_schema_invalid", path or "/", error.message)
    _validate_manifest_exact_scalars(manifest)
    _validate_manifest_array_metadata(manifest)
    _validate_manifest_termination(manifest["termination"])
    source_claims = manifest["claims"]
    if any(
        source_claims[field_name] is not source_claims["diagnostic_ready"]
        for field_name in (
            "partial_iterate_preserved",
            "nonconverged_max_iterations_verified",
            "restart_history_preserved",
        )
    ):
        _raise(
            "diagnostic_ir_v1_source_claim_scope_invalid",
            "/claims",
            "Raw-source claims must exactly follow diagnostic_ready authority.",
        )
    if source_claims["diagnostic_ready"] and not allow_diagnostic_ready:
        _raise(
            "diagnostic_ir_v1_ready_authority_unavailable",
            "/claims/diagnostic_ready",
            "Detached DiagnosticIR v1 has no process-local bridge authority.",
        )
    try:
        expected_numerical = _numerical_hash_from_manifest(manifest)
        expected_receipt = _receipt_hash(manifest)
    except CanonicalContractError as exc:
        raise DiagnosticIRV1Error(
            "diagnostic_ir_v1_manifest_noncanonical", "/", str(exc)
        ) from exc
    if manifest["numerical_diagnostic_hash"] != expected_numerical:
        _raise(
            "diagnostic_ir_v1_numerical_hash_mismatch",
            "/numerical_diagnostic_hash",
            "Numerical diagnostic commitment is stale.",
        )
    if manifest["diagnostic_ir_hash"] != expected_receipt:
        _raise(
            "diagnostic_ir_v1_aggregate_hash_mismatch",
            "/diagnostic_ir_hash",
            "Aggregate DiagnosticIR v1 commitment is stale.",
        )


def validate_diagnostic_ir_v1_physics(
    receipt: DiagnosticIRV1,
    *,
    expected_plan: ExecutionPlanV2,
    expected_accepted_state: StateIR,
    expected_evaluated_trial_state: StateIR,
) -> DiagnosticIRV1:
    """Replay exact plan/state bindings, residual signs, and metrics."""

    validate_diagnostic_ir_v1(receipt)
    _validate_exact_sources(
        expected_plan, expected_accepted_state, expected_evaluated_trial_state
    )
    _validate_source_bindings(
        receipt,
        expected_plan,
        expected_accepted_state,
        expected_evaluated_trial_state,
    )
    displacement = receipt.arrays.partial_displacement_si.values.reshape(-1)
    residual = receipt.arrays.residual_si.values.reshape(-1)
    exported = receipt.arrays.exported_free_residual_si.values.reshape(-1)
    free = expected_plan.array("free_dofs")
    constrained = expected_plan.array("constrained_dofs")
    if not np.array_equal(displacement, expected_evaluated_trial_state.displacement_si):
        _raise(
            "diagnostic_ir_v1_trial_displacement_mismatch",
            "/input_bindings/evaluated_trial_state_hash",
            "Partial iterate differs from the evaluated trial StateIR.",
        )
    if np.any(displacement[constrained] != 0.0):
        _raise(
            "diagnostic_ir_v1_constrained_displacement_nonzero",
            "/arrays/partial_displacement_si",
            "Constrained partial-displacement entries must be exactly zero.",
        )
    expected_residual = np.ascontiguousarray(
        expected_plan.residual(displacement), dtype="<f8"
    )
    expected_residual[expected_residual == 0.0] = 0.0
    if not np.array_equal(residual, expected_residual):
        _raise(
            "diagnostic_ir_v1_residual_invariant_failed",
            "/arrays/residual_si",
            "Full residual must exactly equal ExecutionPlanV2 K*u-F replay.",
        )
    if not np.allclose(
        exported,
        -expected_residual[free],
        rtol=1.0e-8,
        atol=1.0e-12,
    ):
        _raise(
            "diagnostic_ir_v1_exported_residual_sign_mismatch",
            "/arrays/exported_free_residual_si",
            "Exported free residual must approximate -(K*u-F)[free].",
        )

    metrics = receipt.termination.metrics
    rhs = expected_plan.array("global_load")[free]
    free_residual = expected_residual[free]
    load_scale = max(1.0, _linf(rhs))
    expected_metrics = {
        "initial_residual_l2": _stable_l2(rhs),
        "solver_tolerance_l2": max(
            receipt.termination.policy.absolute_tolerance,
            receipt.termination.policy.relative_tolerance * _stable_l2(rhs),
        ),
        "final_residual_l2": _stable_l2(exported),
        "final_residual_linf": _linf(exported),
        "scaled_true_residual": _linf(exported) / load_scale,
        "load_scale": load_scale,
        "free_residual_l2": _stable_l2(free_residual),
        "free_residual_linf": _linf(free_residual),
        "scaled_free_residual": _linf(free_residual) / load_scale,
        "exported_free_residual_l2": _stable_l2(exported),
        "exported_free_residual_linf": _linf(exported),
        "scaled_exported_free_residual": _linf(exported) / load_scale,
    }
    for field_name, expected in expected_metrics.items():
        if getattr(metrics, field_name) != expected:
            _raise(
                "diagnostic_ir_v1_metric_replay_mismatch",
                f"/termination/metrics/{field_name}",
                f"Expected {expected:.17g} from plan replay.",
            )
    if metrics.final_residual_l2 <= metrics.solver_tolerance_l2:
        _raise(
            "diagnostic_ir_v1_solver_gate_passed",
            "/termination/metrics/solver_tolerance_passed",
            "A max-iterations diagnostic must fail the solver L2 gate.",
        )
    if metrics.scaled_true_residual <= expected_plan.residual_tolerance:
        _raise(
            "diagnostic_ir_v1_authoritative_gate_passed",
            "/termination/metrics/authoritative_plan_tolerance_passed",
            "A max-iterations diagnostic must fail the plan residual gate.",
        )
    return receipt


def _validate_exact_sources(
    plan: ExecutionPlanV2,
    accepted: StateIR,
    trial: StateIR,
) -> None:
    if type(plan) is not ExecutionPlanV2:
        _raise(
            "diagnostic_ir_v1_plan_type_invalid",
            "/input_bindings/execution_plan_hash",
            "Expected exact ExecutionPlanV2 storage.",
        )
    try:
        validate_execution_plan_v2(plan)
    except ExecutionPlanV2Error as exc:
        raise DiagnosticIRV1Error(
            "diagnostic_ir_v1_plan_invalid",
            exc.path,
            f"{exc.code}: {exc.message}",
        ) from exc
    for state, label, path in (
        (accepted, "accepted", "/input_bindings/accepted_state_hash"),
        (trial, "evaluated trial", "/input_bindings/evaluated_trial_state_hash"),
    ):
        if type(state) is not StateIR:
            _raise(
                "diagnostic_ir_v1_state_type_invalid",
                path,
                f"Expected exact {label} StateIR storage.",
            )
        try:
            validate_state_ir(state, expected_plan=plan)
        except StateIRError as exc:
            raise DiagnosticIRV1Error(
                "diagnostic_ir_v1_state_invalid",
                path,
                f"{label} StateIR failed {exc.code}@{exc.path}: {exc.message}",
            ) from exc

    canonical_initial = create_initial_state(plan)
    if accepted.state_hash != canonical_initial.state_hash:
        _raise(
            "diagnostic_ir_v1_accepted_state_not_canonical_initial",
            "/input_bindings/accepted_state_hash",
            "Accepted StateIR must be the canonical zero epoch-0 initial state.",
        )
    if (
        accepted.role != "committed"
        or accepted.epoch != 0
        or accepted.parent_state_hash is not None
        or accepted.load_step != 0
        or accepted.iteration != 0
        or accepted.load_factor != 0.0
        or accepted.time_s != 0.0
        or np.any(accepted.displacement_si != 0.0)
        or np.any(accepted.velocity_si != 0.0)
        or np.any(accepted.acceleration_si != 0.0)
    ):
        _raise(
            "diagnostic_ir_v1_accepted_state_invalid",
            "/input_bindings/accepted_state_hash",
            "Accepted StateIR is not the canonical committed zero state.",
        )
    if (
        trial.role != "trial"
        or trial.epoch != 1
        or trial.parent_state_hash != accepted.state_hash
        or trial.load_step != 1
        or trial.load_factor != 1.0
        or trial.time_s != 0.0
        or not np.array_equal(trial.velocity_si, accepted.velocity_si)
        or not np.array_equal(trial.acceleration_si, accepted.acceleration_si)
    ):
        _raise(
            "diagnostic_ir_v1_trial_lineage_invalid",
            "/input_bindings/evaluated_trial_state_hash",
            "Evaluated trial must directly descend from the canonical initial state.",
        )
    try:
        rolled_back = rollback_trial_state(accepted, trial, expected_plan=plan)
    except StateIRError as exc:  # pragma: no cover - validation above is exhaustive
        raise DiagnosticIRV1Error(
            "diagnostic_ir_v1_rollback_invalid",
            "/state_lifecycle/rollback_result",
            f"{exc.code}@{exc.path}: {exc.message}",
        ) from exc
    if rolled_back is not accepted:
        _raise(
            "diagnostic_ir_v1_rollback_identity_invalid",
            "/state_lifecycle/rollback_result",
            "Rollback must retain the exact accepted StateIR object.",
        )


def _validate_source_bindings(
    receipt: DiagnosticIRV1,
    plan: ExecutionPlanV2,
    accepted: StateIR,
    trial: StateIR,
) -> None:
    expected_bindings = DiagnosticIRV1InputBindings(
        model_ir_content_hash=plan.model_ir_content_hash,
        solver_numeric_buffer_hash=plan.solver_numeric_buffer_hash,
        solver_entity_mapping_hash=plan.solver_entity_mapping_hash,
        solver_artifact_hash=plan.solver_artifact_hash,
        execution_plan_hash=plan.plan_hash,
        accepted_state_hash=accepted.state_hash,
        evaluated_trial_state_hash=trial.state_hash,
    )
    if receipt.input_bindings != expected_bindings:
        _raise(
            "diagnostic_ir_v1_input_binding_mismatch",
            "/input_bindings",
            "DiagnosticIR v1 is bound to different plan or StateIR sources.",
        )
    expected_analysis = DiagnosticIRV1Analysis(
        load_pattern_id=plan.load_pattern_id,
        operator_version=plan.operator_version,
        operator_hash=plan.operator_hash,
    )
    if receipt.analysis != expected_analysis:
        _raise(
            "diagnostic_ir_v1_analysis_binding_mismatch",
            "/analysis",
            "Analysis bindings differ from ExecutionPlanV2.",
        )
    expected_ordering = DiagnosticIRV1Ordering(
        node_ids=plan.node_ids,
        constrained_dofs=plan.constrained_dofs,
        free_dofs=plan.free_dofs,
        ordering_hash=plan.ordering_hash,
    )
    if receipt.ordering != expected_ordering:
        _raise(
            "diagnostic_ir_v1_ordering_binding_mismatch",
            "/ordering",
            "Diagnostic ordering differs from ExecutionPlanV2.",
        )
    expected_shapes = {
        "partial_displacement_si": (plan.dof_count,),
        "residual_si": (plan.dof_count,),
        "exported_free_residual_si": (len(plan.free_dofs),),
    }
    for row in receipt.arrays.ordered():
        if row.shape != expected_shapes[row.name]:
            _raise(
                "diagnostic_ir_v1_array_shape_mismatch",
                f"/arrays/{row.name}/shape",
                f"Expected {expected_shapes[row.name]}, got {row.shape}.",
            )
    if trial.iteration != receipt.termination.counters.iteration_count:
        _raise(
            "diagnostic_ir_v1_trial_iteration_mismatch",
            "/input_bindings/evaluated_trial_state_hash",
            "Trial iteration must equal the exhausted FGMRES iteration count.",
        )


def _policy_payload(
    policy: DiagnosticIRV1Policy, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": policy.schema_version,
        "method": "fixed_restart_right_preconditioned_fgmres",
        "restart_dimension": policy.restart_dimension,
        "max_iterations": policy.max_iterations,
        "absolute_tolerance": policy.absolute_tolerance,
        "relative_tolerance": policy.relative_tolerance,
        "stagnation_checkpoint_limit": policy.stagnation_checkpoint_limit,
        "stagnation_relative_tolerance": policy.stagnation_relative_tolerance,
        "divergence_factor": policy.divergence_factor,
        "orthogonalization": "dgks_conditional_two_pass_mgs",
        "preconditioner": "positive_unshifted_jacobi_right",
        "solver_norm": "l2",
        "authoritative_norm": "scaled_true_residual_linf",
        "fallback_forbidden": True,
    }
    if include_hash:
        payload["policy_hash"] = policy.policy_hash
    return payload


def _validate_policy(policy: DiagnosticIRV1Policy) -> None:
    if type(policy) is not DiagnosticIRV1Policy:
        _raise(
            "diagnostic_ir_v1_policy_type_invalid",
            "/termination/policy",
            "Expected exact DiagnosticIRV1Policy storage.",
        )
    if (
        type(policy.restart_dimension) is not int
        or not 1 <= policy.restart_dimension <= 16
        or type(policy.max_iterations) is not int
        or not 0 <= policy.max_iterations <= 4096
        or type(policy.stagnation_checkpoint_limit) is not int
        or not 2 <= policy.stagnation_checkpoint_limit <= 16
    ):
        _raise(
            "diagnostic_ir_v1_policy_count_invalid",
            "/termination/policy",
            "FGMRES policy bounds are invalid.",
        )
    for field_name, allow_zero in (
        ("absolute_tolerance", True),
        ("relative_tolerance", True),
        ("stagnation_relative_tolerance", False),
        ("divergence_factor", False),
    ):
        value = getattr(policy, field_name)
        if (
            type(value) is not float
            or not math.isfinite(value)
            or (value < 0.0 if allow_zero else value <= 0.0)
            or (value == 0.0 and math.copysign(1.0, value) < 0.0)
        ):
            _raise(
                "diagnostic_ir_v1_policy_scalar_invalid",
                f"/termination/policy/{field_name}",
                "FGMRES policy scalar is invalid.",
            )
    if policy.absolute_tolerance == 0.0 and policy.relative_tolerance == 0.0:
        _raise(
            "diagnostic_ir_v1_policy_tolerance_empty",
            "/termination/policy",
            "At least one FGMRES tolerance must be positive.",
        )
    if policy.stagnation_relative_tolerance >= 1.0:
        _raise(
            "diagnostic_ir_v1_policy_stagnation_invalid",
            "/termination/policy/stagnation_relative_tolerance",
            "Stagnation relative tolerance must be below one.",
        )
    if policy.divergence_factor <= 1.0:
        _raise(
            "diagnostic_ir_v1_policy_divergence_invalid",
            "/termination/policy/divergence_factor",
            "Divergence factor must exceed one.",
        )
    _require_hash(policy.policy_hash, "/termination/policy/policy_hash")
    if policy.policy_hash != canonical_hash(
        _policy_payload(policy, include_hash=False)
    ):
        _raise(
            "diagnostic_ir_v1_policy_hash_mismatch",
            "/termination/policy/policy_hash",
            "FGMRES policy commitment is stale.",
        )


def _validate_termination(termination: DiagnosticIRV1Termination) -> None:
    if type(termination) is not DiagnosticIRV1Termination:
        _raise(
            "diagnostic_ir_v1_termination_type_invalid",
            "/termination",
            "Expected exact DiagnosticIRV1Termination storage.",
        )
    if termination.status != "max_iterations" or type(termination.status) is not str:
        _raise(
            "diagnostic_ir_v1_status_invalid",
            "/termination/status",
            "Diagnostic status must be exactly max_iterations.",
        )
    if (
        termination.termination_code != "max_iterations_exhausted"
        or type(termination.termination_code) is not str
    ):
        _raise(
            "diagnostic_ir_v1_termination_code_invalid",
            "/termination/termination_code",
            "Termination code must be exactly max_iterations_exhausted.",
        )
    _validate_policy(termination.policy)
    if type(termination.counters) is not DiagnosticIRV1Counters:
        _raise(
            "diagnostic_ir_v1_counters_type_invalid",
            "/termination/counters",
            "Expected exact DiagnosticIRV1Counters storage.",
        )
    if type(termination.metrics) is not DiagnosticIRV1Metrics:
        _raise(
            "diagnostic_ir_v1_metrics_type_invalid",
            "/termination/metrics",
            "Expected exact DiagnosticIRV1Metrics storage.",
        )
    if type(termination.history) is not tuple or any(
        type(row) is not DiagnosticIRV1RestartRecord for row in termination.history
    ):
        _raise(
            "diagnostic_ir_v1_history_container_invalid",
            "/termination/history",
            "Restart history must be an exact tuple of exact records.",
        )
    counters = termination.counters
    for field_name in counters.__dataclass_fields__:
        value = getattr(counters, field_name)
        if type(value) is not int or value < 0 or value > _MAX_INDEX:
            _raise(
                "diagnostic_ir_v1_counter_invalid",
                f"/termination/counters/{field_name}",
                "Counter must be an exact nonnegative bounded integer.",
            )
    if (
        counters.iteration_count != termination.policy.max_iterations
        or counters.restart_count
        != (
            0
            if counters.iteration_count == 0
            else math.ceil(
                counters.iteration_count / termination.policy.restart_dimension
            )
        )
        or counters.restart_count != len(termination.history)
        or counters.preconditioner_apply_count != counters.iteration_count
        or counters.operator_apply_count < 1 + counters.iteration_count
    ):
        _raise(
            "diagnostic_ir_v1_counter_invariant_invalid",
            "/termination/counters",
            "Counters do not describe exact max-iterations exhaustion.",
        )
    metrics = termination.metrics
    for field_name in (
        "initial_residual_l2",
        "solver_tolerance_l2",
        "final_residual_l2",
        "final_residual_linf",
        "scaled_true_residual",
        "load_scale",
        "free_residual_l2",
        "free_residual_linf",
        "scaled_free_residual",
        "exported_free_residual_l2",
        "exported_free_residual_linf",
        "scaled_exported_free_residual",
    ):
        value = getattr(metrics, field_name)
        if (
            type(value) is not float
            or not math.isfinite(value)
            or value < 0.0
            or (value == 0.0 and math.copysign(1.0, value) < 0.0)
        ):
            _raise(
                "diagnostic_ir_v1_metric_invalid",
                f"/termination/metrics/{field_name}",
                "Metric must be an exact finite nonnegative float.",
            )
    if metrics.load_scale < 1.0:
        _raise(
            "diagnostic_ir_v1_metric_invalid",
            "/termination/metrics/load_scale",
            "Load scale must be at least one.",
        )
    expected_solver_tolerance = max(
        termination.policy.absolute_tolerance,
        termination.policy.relative_tolerance * metrics.initial_residual_l2,
    )
    if metrics.solver_tolerance_l2 != expected_solver_tolerance:
        _raise(
            "diagnostic_ir_v1_solver_tolerance_mismatch",
            "/termination/metrics/solver_tolerance_l2",
            "Solver tolerance must be derived from policy and initial L2 residual.",
        )
    if (
        type(metrics.solver_tolerance_passed) is not bool
        or metrics.solver_tolerance_passed
        or type(metrics.authoritative_plan_tolerance_passed) is not bool
        or metrics.authoritative_plan_tolerance_passed
    ):
        _raise(
            "diagnostic_ir_v1_nonconvergence_flag_invalid",
            "/termination/metrics",
            "Both convergence gates must be explicitly false.",
        )
    if metrics.final_residual_l2 <= metrics.solver_tolerance_l2:
        _raise(
            "diagnostic_ir_v1_solver_gate_passed",
            "/termination/metrics/solver_tolerance_passed",
            "A max-iterations diagnostic must fail the solver L2 gate.",
        )
    if (
        metrics.final_residual_linf > metrics.final_residual_l2
        or metrics.free_residual_linf > metrics.free_residual_l2
        or metrics.exported_free_residual_linf > metrics.exported_free_residual_l2
        or metrics.scaled_true_residual
        != metrics.final_residual_linf / metrics.load_scale
        or metrics.scaled_free_residual
        != metrics.free_residual_linf / metrics.load_scale
        or metrics.scaled_exported_free_residual
        != metrics.exported_free_residual_linf / metrics.load_scale
        or metrics.final_residual_l2 != metrics.exported_free_residual_l2
        or metrics.final_residual_linf != metrics.exported_free_residual_linf
    ):
        _raise(
            "diagnostic_ir_v1_metric_invariant_invalid",
            "/termination/metrics",
            "Terminal and full/free residual metrics are inconsistent.",
        )
    if metrics.final_residual_l2 > termination.policy.divergence_factor * max(
        metrics.initial_residual_l2, float(np.finfo(np.float64).tiny)
    ):
        _raise(
            "diagnostic_ir_v1_divergence_status_mismatch",
            "/termination/status",
            "A diverged outcome cannot be represented as max_iterations.",
        )

    cursor = 0
    step_total = 0
    for index, row in enumerate(termination.history, start=1):
        expected_step_count = min(
            termination.policy.restart_dimension,
            counters.iteration_count - cursor,
        )
        row_metrics = (
            row.estimated_residual_l2,
            row.true_residual_l2,
            row.true_residual_linf,
            row.scaled_true_residual,
            row.solution_update_l2,
        )
        integer_fields = (
            row.restart_index,
            row.start_iteration,
            row.end_iteration,
            row.arnoldi_step_count,
            row.preconditioner_apply_count,
            row.reorthogonalization_count,
        )
        if (
            any(type(value) is not int for value in integer_fields)
            or any(
                type(value) is not float
                or not math.isfinite(value)
                or value < 0.0
                or (value == 0.0 and math.copysign(1.0, value) < 0.0)
                for value in row_metrics
            )
            or type(row.termination_hint) is not str
            or row.restart_index != index
            or row.start_iteration != cursor
            or row.end_iteration - row.start_iteration != row.arnoldi_step_count
            or row.arnoldi_step_count != expected_step_count
            or row.preconditioner_apply_count != row.arnoldi_step_count
            or not 0 <= row.reorthogonalization_count <= row.arnoldi_step_count
            or row.true_residual_linf > row.true_residual_l2
            or row.scaled_true_residual != row.true_residual_linf / metrics.load_scale
            or row.termination_hint != "restart_completed"
        ):
            _raise(
                "diagnostic_ir_v1_history_invariant_invalid",
                f"/termination/history/{index - 1}",
                "Restart record is not contiguous fixed-restart FGMRES history.",
            )
        cursor = row.end_iteration
        step_total += row.arnoldi_step_count
    if step_total != counters.iteration_count:
        _raise(
            "diagnostic_ir_v1_history_count_mismatch",
            "/termination/history",
            "Restart history does not cover every exhausted iteration.",
        )
    if termination.history:
        final = termination.history[-1]
        if (
            final.end_iteration != counters.iteration_count
            or not _source_l2_close(
                final.true_residual_l2,
                metrics.final_residual_l2,
            )
            or final.true_residual_linf != metrics.final_residual_linf
            or final.scaled_true_residual != metrics.scaled_true_residual
        ):
            _raise(
                "diagnostic_ir_v1_terminal_history_mismatch",
                "/termination/history",
                "Final restart record differs from terminal metrics.",
            )


def _validate_source_provenance(
    provenance: DiagnosticSourceProvenanceV1,
) -> None:
    if type(provenance) is not DiagnosticSourceProvenanceV1:
        _raise(
            "diagnostic_ir_v1_provenance_type_invalid",
            "/source_provenance",
            "Expected exact DiagnosticSourceProvenanceV1 storage.",
        )
    _require_stable_id(provenance.case_id, "/source_provenance/case_id")
    _require_stable_id(
        provenance.source_schema_version,
        "/source_provenance/source_schema_version",
    )
    _require_stable_id(
        provenance.terminal_observation_id,
        "/source_provenance/terminal_observation_id",
    )
    for field_name in (
        "case_parity_receipt_hash",
        "terminal_observation_receipt_hash",
        "completion_export_receipt_hash",
        "completion_export_payload_hash",
        "device_identity_receipt_hash",
        "cpu_result_hash",
        "terminal_outcome_hash",
        "completion_export_context_id",
        "source_binding_hash",
        "solution_payload_sha256",
        "exported_free_residual_payload_sha256",
        "solve_record_payload_sha256",
    ):
        _require_hash(
            getattr(provenance, field_name), f"/source_provenance/{field_name}"
        )
    if (
        type(provenance.actual_backend) is not str
        or _BACKEND_PATTERN.fullmatch(provenance.actual_backend) is None
        or provenance.actual_backend != "hip"
    ):
        _raise(
            "diagnostic_ir_v1_backend_invalid",
            "/source_provenance/actual_backend",
            "Exact v1 source backend must be HIP.",
        )
    if (
        type(provenance.source_kind) is not str
        or provenance.source_kind != "fgmres_partial_iterate"
    ):
        _raise(
            "diagnostic_ir_v1_source_kind_invalid",
            "/source_provenance/source_kind",
            "Source kind must be the exact FGMRES partial-iterate profile.",
        )
    if (
        type(provenance.compiled_architecture) is not str
        or _ARCHITECTURE_PATTERN.fullmatch(provenance.compiled_architecture) is None
        or type(provenance.runtime_architecture_base) is not str
        or _ARCHITECTURE_BASE_PATTERN.fullmatch(provenance.runtime_architecture_base)
        is None
        or provenance.compiled_architecture.split(":", 1)[0]
        != provenance.runtime_architecture_base
    ):
        _raise(
            "diagnostic_ir_v1_architecture_invalid",
            "/source_provenance/compiled_architecture",
            "Compiled and runtime HIP architectures are invalid or mismatched.",
        )
    _require_index(provenance.device_ordinal, "/source_provenance/device_ordinal")
    if (
        type(provenance.device_uuid_bytes_hex) is not str
        or _UUID_PATTERN.fullmatch(provenance.device_uuid_bytes_hex) is None
        or provenance.device_uuid_bytes_hex == "0" * 32
    ):
        _raise(
            "diagnostic_ir_v1_device_uuid_invalid",
            "/source_provenance/device_uuid_bytes_hex",
            "Device UUID must be 16 non-zero lowercase hex bytes.",
        )
    if (
        type(provenance.device_pci_bdf) is not str
        or _PCI_BDF_PATTERN.fullmatch(provenance.device_pci_bdf) is None
    ):
        _raise(
            "diagnostic_ir_v1_device_pci_bdf_invalid",
            "/source_provenance/device_pci_bdf",
            "Device PCI BDF is invalid.",
        )
    for field_name in (
        "additional_device_operation_count",
        "additional_d2h_operation_count",
        "additional_solve_count",
        "additional_export_count",
        "fallback_count",
    ):
        value = getattr(provenance, field_name)
        if type(value) is not int or value != 0:
            _raise(
                "diagnostic_ir_v1_projection_count_invalid",
                f"/source_provenance/{field_name}",
                "Diagnostic projection must add exactly zero backend operations.",
            )
    for field_name in (
        "live_authority_serialized",
        "signed_evidence",
        "standalone_provenance",
    ):
        value = getattr(provenance, field_name)
        if type(value) is not bool or value:
            _raise(
                "diagnostic_ir_v1_provenance_claim_invalid",
                f"/source_provenance/{field_name}",
                "Detached provenance cannot serialize live or promoting authority.",
            )


def _validate_receipt_scalars(receipt: DiagnosticIRV1) -> None:
    _require_stable_id(receipt.diagnostic_id, "/diagnostic_id")
    for field_name in (
        "model_ir_content_hash",
        "solver_numeric_buffer_hash",
        "solver_entity_mapping_hash",
        "solver_artifact_hash",
        "execution_plan_hash",
        "accepted_state_hash",
        "evaluated_trial_state_hash",
    ):
        _require_hash(
            getattr(receipt.input_bindings, field_name),
            f"/input_bindings/{field_name}",
        )
    if receipt.input_bindings.committed_state_hash is not None:
        _raise(
            "diagnostic_ir_v1_committed_state_forbidden",
            "/input_bindings/committed_state_hash",
            "A nonconverged partial iterate must not bind a committed state.",
        )
    _require_stable_id(receipt.analysis.load_pattern_id, "/analysis/load_pattern_id")
    if type(receipt.analysis.operator_version) is not str:
        _raise(
            "diagnostic_ir_v1_scalar_type_invalid",
            "/analysis/operator_version",
            "Operator version must be an exact string.",
        )
    _require_hash(receipt.analysis.operator_hash, "/analysis/operator_hash")
    for value in receipt.ordering.node_ids:
        _require_stable_id(value, "/ordering/node_ids")
    for value in (*receipt.ordering.constrained_dofs, *receipt.ordering.free_dofs):
        _require_index(value, "/ordering")
    _require_hash(receipt.ordering.ordering_hash, "/ordering/ordering_hash")
    expected_claims = DiagnosticIRV1Claims()
    source_claim_fields = (
        "diagnostic_ready",
        "partial_iterate_preserved",
        "nonconverged_max_iterations_verified",
        "restart_history_preserved",
    )
    for field_name in receipt.claims.__dataclass_fields__:
        value = getattr(receipt.claims, field_name)
        if type(value) is not bool or (
            field_name not in source_claim_fields
            and value is not getattr(expected_claims, field_name)
        ):
            _raise(
                "diagnostic_ir_v1_claim_invalid",
                f"/claims/{field_name}",
                "DiagnosticIR v1 claim boundary is fixed and non-promoting.",
            )
    if any(
        getattr(receipt.claims, field_name) is not receipt.claims.diagnostic_ready
        for field_name in source_claim_fields[1:]
    ):
        _raise(
            "diagnostic_ir_v1_source_claim_scope_invalid",
            "/claims",
            "Raw-source claims must exactly follow diagnostic_ready authority.",
        )
    ready_authority_valid = _has_bridge_diagnostic_ir_ready_authority(receipt)
    if receipt.claims.diagnostic_ready and not ready_authority_valid:
        _raise(
            "diagnostic_ir_v1_ready_authority_unavailable",
            "/claims/diagnostic_ready",
            "diagnostic_ready=true requires the exact process-local bridge object.",
        )
    if not receipt.claims.diagnostic_ready and (
        receipt._diagnostic_ir_ready_authority is not None
    ):
        _raise(
            "diagnostic_ir_v1_ready_authority_invalid",
            "/claims/diagnostic_ready",
            "A not-ready DiagnosticIR v1 cannot retain bridge-ready authority.",
        )
    _require_hash(receipt.numerical_diagnostic_hash, "/numerical_diagnostic_hash")
    _require_hash(receipt.diagnostic_ir_hash, "/diagnostic_ir_hash")


def _array_artifact(
    name: str,
    values: Any,
    *,
    axis_labels: tuple[str, ...],
    component_labels: tuple[str, ...],
    component_units: tuple[str, ...],
) -> DiagnosticArrayV1:
    try:
        source = np.asarray(values, dtype="<f8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise DiagnosticIRV1Error(
            "diagnostic_ir_v1_array_value_invalid",
            f"/arrays/{name}/values",
            "Diagnostic array values cannot be represented as FP64.",
        ) from exc
    if source.ndim == 0 or any(value <= 0 for value in source.shape):
        _raise(
            "diagnostic_ir_v1_array_shape_invalid",
            f"/arrays/{name}/shape",
            "Diagnostic arrays must have non-empty dimensions.",
        )
    if len(axis_labels) != source.ndim or not np.isfinite(source).all():
        _raise(
            "diagnostic_ir_v1_array_metadata_invalid",
            f"/arrays/{name}",
            "Array rank, labels, or finite-value invariant failed.",
        )
    normalized = np.ascontiguousarray(source, dtype="<f8").copy()
    normalized[normalized == 0.0] = 0.0
    try:
        array = immutable_array(normalized, dtype="<f8")
    except CanonicalContractError as exc:  # pragma: no cover
        raise DiagnosticIRV1Error(
            "diagnostic_ir_v1_array_storage_invalid", f"/arrays/{name}", str(exc)
        ) from exc
    shape = tuple(int(value) for value in array.shape)
    metadata = _artifact_metadata(
        name=name,
        shape=shape,
        axis_labels=axis_labels,
        component_labels=component_labels,
        component_units=component_units,
        byte_length=int(array.nbytes),
    )
    return DiagnosticArrayV1(
        name=name,
        dtype="<f8",
        shape=shape,
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


def _validate_array_dataclass(row: DiagnosticArrayV1) -> None:
    path = f"/arrays/{row.name}"
    if (
        type(row.name) is not str
        or type(row.dtype) is not str
        or type(row.shape) is not tuple
        or type(row.layout) is not str
        or type(row.axis_labels) is not tuple
        or type(row.component_labels) is not tuple
        or type(row.component_units) is not tuple
        or type(row.byte_length) is not int
        or type(row.data_hash) is not str
        or type(row.content_hash) is not str
        or type(row._values) is not np.ndarray
        or any(type(value) is not int or value <= 0 for value in row.shape)
        or any(type(value) is not str or not value for value in row.axis_labels)
        or any(type(value) is not str or not value for value in row.component_labels)
        or any(type(value) is not str or not value for value in row.component_units)
    ):
        _raise(
            "diagnostic_ir_v1_array_container_invalid",
            path,
            "Array artifact containers must use exact contract types.",
        )
    if (
        row.dtype != "<f8"
        or row.layout != "C"
        or row._values.dtype.str != "<f8"
        or row._values.shape != row.shape
        or not row._values.flags.c_contiguous
        or not has_immutable_bytes_backing(row._values)
        or not np.isfinite(row._values).all()
        or np.any(np.signbit(row._values[row._values == 0.0]))
    ):
        _raise(
            "diagnostic_ir_v1_array_storage_invalid",
            path,
            "Array values must be finite normalized immutable C-order <f8 bytes.",
        )
    expected = _array_artifact(
        row.name,
        row._values,
        axis_labels=row.axis_labels,
        component_labels=row.component_labels,
        component_units=row.component_units,
    )
    fields = (
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
    if any(getattr(row, name) != getattr(expected, name) for name in fields):
        _raise(
            "diagnostic_ir_v1_array_descriptor_mismatch",
            path,
            "Array bytes, metadata, or hashes are stale.",
        )


def _finite_flat_vector(value: Any, count: int, path: str) -> np.ndarray:
    try:
        vector = np.asarray(value, dtype="<f8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise DiagnosticIRV1Error(
            "diagnostic_ir_v1_vector_invalid",
            path,
            "Vector cannot be represented as FP64.",
        ) from exc
    allowed_shapes = {(count,)}
    if count % _DOF_COUNT_PER_NODE == 0:
        allowed_shapes.add((count // _DOF_COUNT_PER_NODE, _DOF_COUNT_PER_NODE))
    if vector.shape not in allowed_shapes:
        _raise(
            "diagnostic_ir_v1_vector_shape_invalid",
            path,
            f"Expected {count} flat values.",
        )
    flat = np.ascontiguousarray(vector.reshape(-1), dtype="<f8").copy()
    if not np.isfinite(flat).all():
        _raise(
            "diagnostic_ir_v1_vector_nonfinite",
            path,
            "Vectors must contain only finite values.",
        )
    flat[flat == 0.0] = 0.0
    return flat


def _validate_manifest_exact_scalars(manifest: Mapping[str, Any]) -> None:
    ordering = manifest["ordering"]
    if any(type(value) is not str for value in ordering["node_ids"]):
        _raise(
            "diagnostic_ir_v1_scalar_type_invalid",
            "/ordering/node_ids",
            "Serialized node IDs must be exact strings.",
        )
    for field_name in ("constrained_dofs", "free_dofs"):
        if any(type(value) is not int for value in ordering[field_name]):
            _raise(
                "diagnostic_ir_v1_scalar_type_invalid",
                f"/ordering/{field_name}",
                "Serialized DOF indices must be exact integers.",
            )
    for name, row in manifest["arrays"].items():
        if (
            any(type(value) is not int for value in row["shape"])
            or type(row["byte_length"]) is not int
        ):
            _raise(
                "diagnostic_ir_v1_scalar_type_invalid",
                f"/arrays/{name}",
                "Serialized extents and byte length must be exact integers.",
            )
    provenance = manifest["source_provenance"]
    for field_name in (
        "device_ordinal",
        "additional_device_operation_count",
        "additional_d2h_operation_count",
        "additional_solve_count",
        "additional_export_count",
        "fallback_count",
    ):
        if type(provenance[field_name]) is not int:
            _raise(
                "diagnostic_ir_v1_scalar_type_invalid",
                f"/source_provenance/{field_name}",
                "Serialized operation counts must be exact integers.",
            )


def _validate_manifest_array_metadata(manifest: Mapping[str, Any]) -> None:
    ordering = manifest["ordering"]
    node_count = len(ordering["node_ids"])
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
            "diagnostic_ir_v1_partition_invalid",
            "/ordering",
            "Constrained/free DOFs must form a sorted disjoint global cover.",
        )
    free_components = [DOF_ORDER[index % _DOF_COUNT_PER_NODE] for index in free]
    free_units = [_FORCE_UNITS[index % _DOF_COUNT_PER_NODE] for index in free]
    global_components = [
        DOF_ORDER[index % _DOF_COUNT_PER_NODE] for index in range(dof_count)
    ]
    global_displacement_units = [
        _DISPLACEMENT_UNITS[index % _DOF_COUNT_PER_NODE] for index in range(dof_count)
    ]
    global_force_units = [
        _FORCE_UNITS[index % _DOF_COUNT_PER_NODE] for index in range(dof_count)
    ]
    expected: dict[str, tuple[list[int], list[str], list[str], list[str]]] = {
        "partial_displacement_si": (
            [dof_count],
            ["global_dof"],
            global_components,
            global_displacement_units,
        ),
        "residual_si": (
            [dof_count],
            ["global_dof"],
            global_components,
            global_force_units,
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
                "diagnostic_ir_v1_array_descriptor_mismatch",
                f"/arrays/{name}",
                "Descriptor-only metadata is inconsistent with ordering.",
            )


def _validate_manifest_termination(manifest: Mapping[str, Any]) -> None:
    policy_row = manifest["policy"]
    policy = DiagnosticIRV1Policy(
        restart_dimension=policy_row["restart_dimension"],
        max_iterations=policy_row["max_iterations"],
        absolute_tolerance=policy_row["absolute_tolerance"],
        relative_tolerance=policy_row["relative_tolerance"],
        stagnation_checkpoint_limit=policy_row["stagnation_checkpoint_limit"],
        stagnation_relative_tolerance=policy_row["stagnation_relative_tolerance"],
        divergence_factor=policy_row["divergence_factor"],
        policy_hash=policy_row["policy_hash"],
    )
    counts_row = manifest["counters"]
    counters = DiagnosticIRV1Counters(
        iteration_count=counts_row["iteration_count"],
        restart_count=counts_row["restart_count"],
        operator_apply_count=counts_row["operator_apply_count"],
        preconditioner_apply_count=counts_row["preconditioner_apply_count"],
    )
    metrics_row = manifest["metrics"]
    metrics = DiagnosticIRV1Metrics(
        **{
            name: metrics_row[name]
            for name in DiagnosticIRV1Metrics.__dataclass_fields__
        }
    )
    history = tuple(
        DiagnosticIRV1RestartRecord(
            **{
                name: row[name]
                for name in DiagnosticIRV1RestartRecord.__dataclass_fields__
            }
        )
        for row in manifest["history"]
    )
    _validate_termination(
        DiagnosticIRV1Termination(
            policy=policy,
            counters=counters,
            metrics=metrics,
            history=history,
            status=manifest["status"],
            termination_code=manifest["termination_code"],
        )
    )


def _numerical_hash(
    arrays: DiagnosticIRV1Arrays,
    termination: DiagnosticIRV1Termination,
) -> str:
    return canonical_hash(
        {
            "contract": "engine-v2-diagnostic-ir-numerical.v1",
            "arrays": [
                {
                    "name": row.name,
                    "data_hash": row.data_hash,
                    "content_hash": row.content_hash,
                }
                for row in arrays.ordered()
            ],
            "termination": termination.to_dict(),
        }
    )


def _numerical_hash_from_manifest(manifest: Mapping[str, Any]) -> str:
    return canonical_hash(
        {
            "contract": "engine-v2-diagnostic-ir-numerical.v1",
            "arrays": [
                {
                    "name": name,
                    "data_hash": manifest["arrays"][name]["data_hash"],
                    "content_hash": manifest["arrays"][name]["content_hash"],
                }
                for name in _ARRAY_NAMES
            ],
            "termination": manifest["termination"],
        }
    )


def _receipt_hash(manifest: Mapping[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("diagnostic_ir_hash", None)
    return canonical_hash(payload)


def _stable_l2(vector: np.ndarray) -> float:
    scale = 0.0
    sumsq = 1.0
    for raw in vector:
        value = abs(float(raw))
        if not math.isfinite(value):
            return float("inf")
        if value == 0.0:
            continue
        if scale < value:
            ratio = 0.0 if scale == 0.0 else scale / value
            sumsq = 1.0 + sumsq * ratio * ratio
            scale = value
        else:
            ratio = value / scale
            sumsq += ratio * ratio
    result = 0.0 if scale == 0.0 else scale * math.sqrt(sumsq)
    return result if math.isfinite(result) else float("inf")


def _source_l2_close(left: float, right: float) -> bool:
    """Bound source-tree versus canonical sequential LASSQ roundoff in v1."""

    return math.isclose(
        left,
        right,
        rel_tol=_SOURCE_L2_RELATIVE_TOLERANCE,
        abs_tol=0.0,
    )


def _linf(vector: np.ndarray) -> float:
    if vector.size == 0:
        return 0.0
    value = float(np.max(np.abs(vector)))
    return value if math.isfinite(value) else float("inf")


def _require_hash(value: Any, path: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        _raise(
            "diagnostic_ir_v1_hash_invalid",
            path,
            "Expected sha256:<64 lowercase hex>.",
        )
    return value


def _require_stable_id(value: Any, path: str) -> str:
    if type(value) is not str or _STABLE_ID_PATTERN.fullmatch(value) is None:
        _raise("diagnostic_ir_v1_stable_id_invalid", path, "Invalid stable identifier.")
    return value


def _require_index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_INDEX:
        _raise(
            "diagnostic_ir_v1_index_invalid",
            path,
            f"Expected an integer within [0, {_MAX_INDEX}].",
        )
    return value


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = (
        Path(__file__).resolve().parents[2] / "schemas" / "diagnostic_ir_v1.schema.json"
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _raise(code: str, path: str, message: str) -> None:
    raise DiagnosticIRV1Error(code, path, message)


__all__ = [
    "DIAGNOSTIC_IR_V1_CAPABILITY_PROFILE",
    "DIAGNOSTIC_IR_V1_SCHEMA_VERSION",
    "DiagnosticArrayV1",
    "DiagnosticIRV1",
    "DiagnosticIRV1Analysis",
    "DiagnosticIRV1Arrays",
    "DiagnosticIRV1Claims",
    "DiagnosticIRV1Counters",
    "DiagnosticIRV1Error",
    "DiagnosticIRV1InputBindings",
    "DiagnosticIRV1Metrics",
    "DiagnosticIRV1Ordering",
    "DiagnosticIRV1Policy",
    "DiagnosticIRV1RestartRecord",
    "DiagnosticIRV1Termination",
    "DiagnosticSourceProvenanceV1",
    "build_diagnostic_ir_v1",
    "validate_diagnostic_ir_v1",
    "validate_diagnostic_ir_v1_manifest",
    "validate_diagnostic_ir_v1_physics",
]
