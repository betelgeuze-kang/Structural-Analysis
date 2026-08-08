"""Authority-separated Engine v2 numerical result and diagnostic contracts.

``NumericalResultIR`` is deliberately narrower than an engineering result.  It
binds one converged, committed global displacement state to the exact scaled
ExecutionPlan, reduced CSR identity, solver solution bytes, and independent
residual/boundary-condition receipts.  Reaction and member-force recovery are
not performed here and therefore cannot acquire authority through this type.

``DiagnosticIR`` contains stable code/path observations only.  It preserves
partial, unsupported, fallback, and failed dispositions without carrying raw
exception text or acquiring numerical-result authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache
from importlib import resources
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Literal, Protocol

from jsonschema import Draft202012Validator, validators
import numpy as np

from ._canonical import (
    CanonicalContractError,
    array_content_hash,
    array_data_hash,
    canonical_hash,
    canonical_json_bytes,
    has_immutable_bytes_backing,
    immutable_array,
)
from .equation_scaling import (
    EquationScaling,
    execution_plan_scaling_hash,
    validate_equation_scaling_binding,
)
from .execution_plan import (
    EXECUTION_PLAN_DOF_COMPONENTS,
    EXECUTION_PLAN_RESIDUAL_SIGN,
    ExecutionPlan,
    validate_execution_plan,
)
from .execution_plan_reduced_csr import (
    ExecutionPlanReducedCSR,
    validate_execution_plan_reduced_csr,
)
from .state_ir import StateIR, validate_state_ir


NUMERICAL_RESULT_IR_SCHEMA_VERSION = "structural-analysis-numerical-result-ir.v1"
DIAGNOSTIC_IR_SCHEMA_VERSION = "structural-analysis-diagnostic-ir.v1"
NUMERICAL_RESULT_AUTHORITY_PROFILE = (
    "authoritative_converged_linear_static_displacement.v1"
)
DIAGNOSTIC_AUTHORITY_PROFILE = "non_authoritative_stable_observation.v1"
NUMERICAL_RESULT_KIND = "linear_static_numerical_state"
NUMERICAL_RESULT_PROMOTION_BASIS = (
    "converged_recurrence_plus_independent_full_residual_bc_and_committed_state.v1"
)
NUMERICAL_RESULT_DISPLACEMENT_ARTIFACT_NAME = "displacement_global_si"
NUMERICAL_RESULT_DISPLACEMENT_FILENAME = "displacement_global.f64le"
NUMERICAL_RESULT_STORAGE_PROFILE = "canonical_little_endian_fp64_binary.v1"
NUMERICAL_RESULT_DISPLACEMENT_UNIT_PROFILE = (
    "node_major_ux_uy_uz_m_rx_ry_rz_rad.v1"
)

NUMERICAL_RESULT_AUTHORITY_AXES = MappingProxyType(
    {
        "numerical_state": "authoritative",
        "convergence": "authoritative",
        "displacement": "authoritative",
        "reaction": "not_evaluated",
        "member_force": "not_evaluated",
        "engineering_design": "not_authoritative",
        "code_compliance": "not_authoritative",
        "release_readiness": "not_authoritative",
        "commercial_use": "not_authoritative",
    }
)
DIAGNOSTIC_AUTHORITY_AXES = MappingProxyType(
    {
        "numerical_state": "not_authoritative",
        "convergence": "not_authoritative",
        "displacement": "not_authoritative",
        "reaction": "not_authoritative",
        "member_force": "not_authoritative",
        "engineering_design": "not_authoritative",
        "code_compliance": "not_authoritative",
        "release_readiness": "not_authoritative",
        "commercial_use": "not_authoritative",
    }
)

NUMERICAL_RESULT_CLAIM_BOUNDARY = MappingProxyType(
    {
        "description": (
            "Authoritative committed numerical displacement state only; reaction, "
            "member-force, engineering-design, output-adapter, readiness, and "
            "commercial authority are outside this contract."
        ),
        "committed_numerical_state": True,
        "global_displacement_state_projection": True,
        "engineering_result_recovery": False,
        "reaction_authority": False,
        "member_force_authority": False,
        "legacy_output_adapter": False,
        "viewer_projection": False,
        "release_readiness": False,
        "commercial_claim": False,
    }
)
DIAGNOSTIC_CLAIM_BOUNDARY = MappingProxyType(
    {
        "description": (
            "Stable sanitized observations only; diagnostics cannot become solver, "
            "engineering-result, readiness, or commercial authority."
        ),
        "stable_code_path_only": True,
        "raw_exception_or_payload_included": False,
        "numerical_result_authority": False,
        "solver_convergence_authority": False,
        "fallback_promoted": False,
        "engineering_result_authority": False,
        "release_readiness": False,
        "commercial_claim": False,
    }
)

_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_DIAGNOSTIC_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,127}$")
_EXTENSION_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*:[A-Za-z0-9_.-]+$")
_SOURCE_AUTHORITY_PROFILES = frozenset(
    {
        "non_authoritative_solver_recurrence",
        "operator_probe",
        "backend_probe",
        "validation_gate",
    }
)
_CONVERGED_TERMINAL_REASONS = frozenset(
    {"initial_residual_satisfied", "converged_scaled_residual"}
)
_BACKEND_ROLES = frozenset({"cpu_reference", "cpu_optimized", "hip"})
_DIAGNOSTIC_SEVERITIES = frozenset({"info", "warning", "error"})
_DIAGNOSTIC_DISPOSITIONS = frozenset(
    {"observed", "partial", "unsupported", "fallback", "failed"}
)
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator, type_checker=_STRICT_JSON_TYPE_CHECKER
)


class ResultIRError(ValueError):
    """Fail-closed ResultIR/DiagnosticIR error with stable code and path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class NumericalResultVectorDescriptor:
    name: Literal["displacement_global_si"]
    dtype: Literal["<f8"]
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_order: Literal["little"]
    byte_length: int
    storage_profile: str
    unit_profile: str
    data_hash: str
    content_hash: str
    artifact_uri: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        return payload


@dataclass(frozen=True)
class DiagnosticEntry:
    code: str
    path: str
    severity: Literal["info", "warning", "error"]
    disposition: Literal[
        "observed", "partial", "unsupported", "fallback", "failed"
    ]
    occurrence_count: int
    evidence_hashes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_hashes"] = list(self.evidence_hashes)
        return payload


@dataclass(frozen=True)
class NumericalResultIR:
    schema_version: str
    result_id: str
    result_hash: str
    result_kind: str
    authority_profile: str
    model_ir_content_hash: str
    execution_plan_hash: str
    reduced_csr_identity_hash: str
    equation_scaling_hash: str
    operator_hash: str
    state_hash: str
    state_epoch: int
    load_pattern_id: str
    source_run_schema_version: str
    source_run_hash: str
    source_terminal_reason: str
    source_solution_data_hash: str
    source_free_solution_value_count: int
    convergence_receipt_hash: str
    full_residual_receipt_hash: str
    boundary_condition_receipt_hash: str
    backend_role: str
    backend_receipt_hash: str
    load_factor: float
    time_s: float
    dof_count: int
    displacement_artifact: NumericalResultVectorDescriptor
    diagnostic_ir_hashes: tuple[str, ...]
    extensions: Mapping[str, Any]
    _displacement_global_si: np.ndarray = field(repr=False, compare=False)
    _execution_plan: ExecutionPlan = field(repr=False, compare=False)
    _equation_scaling: EquationScaling = field(repr=False, compare=False)
    _reduced_csr: ExecutionPlanReducedCSR = field(repr=False, compare=False)
    _committed_state: StateIR = field(repr=False, compare=False)

    @property
    def displacement_global_si(self) -> np.ndarray:
        return self._displacement_global_si

    def to_manifest(self) -> dict[str, Any]:
        validate_numerical_result_ir(self)
        return _numerical_result_payload(self, include_result_hash=True)


@dataclass(frozen=True)
class DiagnosticIR:
    schema_version: str
    diagnostic_id: str
    diagnostic_hash: str
    authority_profile: str
    status: Literal["observed", "partial", "blocked"]
    model_ir_content_hash: str
    execution_plan_hash: str
    operator_hash: str
    load_pattern_id: str
    state_hash: str | None
    state_epoch: int | None
    equation_scaling_hash: str | None
    reduced_csr_identity_hash: str | None
    source_authority_profile: str
    source_receipt_schema_version: str
    source_receipt_hash: str
    backend_receipt_hash: str | None
    entries: tuple[DiagnosticEntry, ...]
    extensions: Mapping[str, Any]
    _execution_plan: ExecutionPlan | None = field(repr=False, compare=False)
    _state: StateIR | None = field(repr=False, compare=False)
    _equation_scaling: EquationScaling | None = field(repr=False, compare=False)
    _reduced_csr: ExecutionPlanReducedCSR | None = field(
        repr=False, compare=False
    )
    _source_adapter: DiagnosticIRSourceAdapter | None = field(
        default=None, repr=False, compare=False
    )

    def to_manifest(self) -> dict[str, Any]:
        validate_diagnostic_ir(self)
        return _diagnostic_payload(self, include_diagnostic_hash=True)


@dataclass(frozen=True)
class DiagnosticIRSourceSnapshot:
    """Validated source-neutral bindings for adapter-backed DiagnosticIR."""

    model_ir_content_hash: str
    execution_plan_hash: str
    operator_hash: str
    load_pattern_id: str
    state_hash: str | None
    state_epoch: int | None
    equation_scaling_hash: str | None
    reduced_csr_identity_hash: str | None
    source_authority_profile: str
    source_receipt_schema_version: str
    source_receipt_hash: str
    backend_receipt_hash: str | None
    entries: tuple[DiagnosticEntry, ...]


class DiagnosticIRSourceAdapter(Protocol):
    def validate_diagnostic_ir_source(self) -> DiagnosticIRSourceSnapshot: ...


def create_numerical_result_ir(
    *,
    result_id: str,
    execution_plan: ExecutionPlan,
    equation_scaling: EquationScaling,
    reduced_csr: ExecutionPlanReducedCSR,
    committed_state: StateIR,
    source_run_schema_version: str,
    source_run_hash: str,
    source_terminal_reason: str,
    source_solution_data_hash: str,
    convergence_receipt_hash: str,
    full_residual_receipt_hash: str,
    boundary_condition_receipt_hash: str,
    backend_role: Literal["cpu_reference", "cpu_optimized", "hip"],
    backend_receipt_hash: str,
    diagnostic_ir_hashes: Sequence[str] = (),
    extensions: Mapping[str, Any] | None = None,
) -> NumericalResultIR:
    """Create a displacement-only numerical result authority envelope.

    The source free-solution hash must equal the exact committed StateIR values
    at the ExecutionPlan free DOFs.  This prevents a converged recurrence receipt
    from being attached to a different committed numerical state.
    """

    plan = validate_execution_plan(execution_plan)
    scaling = equation_scaling
    validate_equation_scaling_binding(plan, scaling=scaling)
    reduced = validate_execution_plan_reduced_csr(
        reduced_csr, execution_plan=plan
    )
    state = validate_state_ir(committed_state, expected_plan=plan)
    normalized_id = _require_stable_id(result_id, "/result_id")
    if state.role != "committed" or state.epoch < 1:
        _fail(
            "result_state_not_committed_terminal",
            "/bindings/state_hash",
            "NumericalResultIR requires a positive-epoch committed state.",
        )
    if reduced.terminal_disposition != "solve_free_equations" or reduced.free_count < 1:
        _fail(
            "result_free_equation_solution_required",
            "/bindings/reduced_csr_identity_hash",
            "This v1 ResultIR profile requires a solved free-equation space.",
        )
    terminal_reason = _require_choice(
        source_terminal_reason,
        _CONVERGED_TERMINAL_REASONS,
        "/source_terminal/terminal_reason",
        "result_source_terminal_not_converged",
    )
    normalized_backend = _require_choice(
        backend_role,
        _BACKEND_ROLES,
        "/source_terminal/backend_role",
        "result_backend_role_invalid",
    )
    source_hash = _require_hash(source_solution_data_hash, "/source_terminal/solution_data_hash")
    free_solution = immutable_array(
        state.displacement_si[plan.array("free_dofs")], dtype="<f8"
    )
    if array_data_hash(free_solution) != source_hash:
        _fail(
            "result_source_solution_state_mismatch",
            "/source_terminal/solution_data_hash",
            "Source solution bytes do not match the committed StateIR free DOFs.",
        )
    displacement = immutable_array(state.displacement_si, dtype="<f8")
    descriptor = _displacement_descriptor(normalized_id, displacement)
    diagnostics = _sorted_unique_hashes(
        diagnostic_ir_hashes, "/diagnostic_ir_hashes"
    )
    frozen_extensions = _freeze_extensions({} if extensions is None else extensions)
    provisional = NumericalResultIR(
        schema_version=NUMERICAL_RESULT_IR_SCHEMA_VERSION,
        result_id=normalized_id,
        result_hash="sha256:" + "0" * 64,
        result_kind=NUMERICAL_RESULT_KIND,
        authority_profile=NUMERICAL_RESULT_AUTHORITY_PROFILE,
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        reduced_csr_identity_hash=reduced.identity_hash,
        equation_scaling_hash=scaling.scaling_hash,
        operator_hash=plan.operator_hash,
        state_hash=state.state_hash,
        state_epoch=state.epoch,
        load_pattern_id=plan.load_pattern_id,
        source_run_schema_version=_require_stable_id(
            source_run_schema_version, "/source_terminal/run_schema_version"
        ),
        source_run_hash=_require_hash(source_run_hash, "/source_terminal/run_hash"),
        source_terminal_reason=terminal_reason,
        source_solution_data_hash=source_hash,
        source_free_solution_value_count=int(free_solution.size),
        convergence_receipt_hash=_require_hash(
            convergence_receipt_hash,
            "/source_terminal/convergence_receipt_hash",
        ),
        full_residual_receipt_hash=_require_hash(
            full_residual_receipt_hash,
            "/source_terminal/full_residual_receipt_hash",
        ),
        boundary_condition_receipt_hash=_require_hash(
            boundary_condition_receipt_hash,
            "/source_terminal/boundary_condition_receipt_hash",
        ),
        backend_role=normalized_backend,
        backend_receipt_hash=_require_hash(
            backend_receipt_hash, "/source_terminal/backend_receipt_hash"
        ),
        load_factor=float(state.load_factor),
        time_s=float(state.time_s),
        dof_count=state.dof_count,
        displacement_artifact=descriptor,
        diagnostic_ir_hashes=diagnostics,
        extensions=frozen_extensions,
        _displacement_global_si=displacement,
        _execution_plan=plan,
        _equation_scaling=scaling,
        _reduced_csr=reduced,
        _committed_state=state,
    )
    result = replace(
        provisional,
        result_hash=canonical_hash(
            _numerical_result_payload(provisional, include_result_hash=False)
        ),
    )
    return validate_numerical_result_ir(result)


def create_diagnostic_entry(
    *,
    code: str,
    path: str,
    severity: Literal["info", "warning", "error"],
    disposition: Literal[
        "observed", "partial", "unsupported", "fallback", "failed"
    ],
    occurrence_count: int = 1,
    evidence_hashes: Sequence[str] = (),
) -> DiagnosticEntry:
    entry = DiagnosticEntry(
        code=_require_diagnostic_code(code, "/entries/code"),
        path=_require_json_pointer(path, "/entries/path"),
        severity=_require_choice(
            severity,
            _DIAGNOSTIC_SEVERITIES,
            "/entries/severity",
            "diagnostic_severity_invalid",
        ),
        disposition=_require_choice(
            disposition,
            _DIAGNOSTIC_DISPOSITIONS,
            "/entries/disposition",
            "diagnostic_disposition_invalid",
        ),
        occurrence_count=_require_exact_int(
            occurrence_count, "/entries/occurrence_count", minimum=1
        ),
        evidence_hashes=_sorted_unique_hashes(
            evidence_hashes, "/entries/evidence_hashes"
        ),
    )
    _validate_diagnostic_entry(entry, "/entries")
    return entry


def create_diagnostic_ir(
    *,
    diagnostic_id: str,
    execution_plan: ExecutionPlan,
    source_authority_profile: Literal[
        "non_authoritative_solver_recurrence",
        "operator_probe",
        "backend_probe",
        "validation_gate",
    ],
    source_receipt_schema_version: str,
    source_receipt_hash: str,
    entries: Sequence[DiagnosticEntry],
    state: StateIR | None = None,
    equation_scaling: EquationScaling | None = None,
    reduced_csr: ExecutionPlanReducedCSR | None = None,
    backend_receipt_hash: str | None = None,
    extensions: Mapping[str, Any] | None = None,
) -> DiagnosticIR:
    """Create a stable non-authoritative diagnostic observation."""

    plan = validate_execution_plan(execution_plan)
    if (equation_scaling is None) != (reduced_csr is None):
        _fail(
            "diagnostic_solver_binding_incomplete",
            "/bindings",
            "Equation scaling and reduced CSR must be supplied together.",
        )
    if equation_scaling is not None:
        validate_equation_scaling_binding(plan, scaling=equation_scaling)
        validate_execution_plan_reduced_csr(reduced_csr, execution_plan=plan)
    checked_state = None if state is None else validate_state_ir(state, expected_plan=plan)
    candidate_entries = tuple(entries)
    if not candidate_entries:
        _fail(
            "diagnostic_entries_empty",
            "/entries",
            "At least one diagnostic entry is required.",
        )
    for index, entry in enumerate(candidate_entries):
        _validate_diagnostic_entry(entry, f"/entries/{index}")
    normalized_entries = tuple(
        sorted(candidate_entries, key=_diagnostic_entry_sort_key)
    )
    if len(set(_diagnostic_entry_sort_key(row) for row in normalized_entries)) != len(
        normalized_entries
    ):
        _fail(
            "diagnostic_entries_duplicate",
            "/entries",
            "Diagnostic entries must be unique.",
        )
    source_profile = _require_choice(
        source_authority_profile,
        _SOURCE_AUTHORITY_PROFILES,
        "/source/authority_profile",
        "diagnostic_source_authority_profile_invalid",
    )
    normalized_backend_hash = (
        None
        if backend_receipt_hash is None
        else _require_hash(backend_receipt_hash, "/source/backend_receipt_hash")
    )
    provisional = DiagnosticIR(
        schema_version=DIAGNOSTIC_IR_SCHEMA_VERSION,
        diagnostic_id=_require_stable_id(diagnostic_id, "/diagnostic_id"),
        diagnostic_hash="sha256:" + "0" * 64,
        authority_profile=DIAGNOSTIC_AUTHORITY_PROFILE,
        status=_diagnostic_status(normalized_entries),
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        operator_hash=plan.operator_hash,
        load_pattern_id=plan.load_pattern_id,
        state_hash=None if checked_state is None else checked_state.state_hash,
        state_epoch=None if checked_state is None else checked_state.epoch,
        equation_scaling_hash=(
            None if equation_scaling is None else equation_scaling.scaling_hash
        ),
        reduced_csr_identity_hash=(
            None if reduced_csr is None else reduced_csr.identity_hash
        ),
        source_authority_profile=source_profile,
        source_receipt_schema_version=_require_stable_id(
            source_receipt_schema_version, "/source/receipt_schema_version"
        ),
        source_receipt_hash=_require_hash(
            source_receipt_hash, "/source/receipt_hash"
        ),
        backend_receipt_hash=normalized_backend_hash,
        entries=normalized_entries,
        extensions=_freeze_diagnostic_extensions(
            {} if extensions is None else extensions
        ),
        _execution_plan=plan,
        _state=checked_state,
        _equation_scaling=equation_scaling,
        _reduced_csr=reduced_csr,
    )
    diagnostic = replace(
        provisional,
        diagnostic_hash=canonical_hash(
            _diagnostic_payload(provisional, include_diagnostic_hash=False)
        ),
    )
    return validate_diagnostic_ir(diagnostic)


def create_adapter_bound_diagnostic_ir(
    *,
    diagnostic_id: str,
    source_adapter: DiagnosticIRSourceAdapter,
) -> DiagnosticIR:
    """Create DiagnosticIR v1 from a retained deterministic source adapter.

    This preserves the existing manifest and authority boundary while allowing
    source solvers whose mixed topology cannot be represented by the linear
    two-node ``ExecutionPlan v1`` shape to replay their own exact bindings.
    """

    snapshot = _adapter_diagnostic_snapshot(source_adapter)
    entries = snapshot.entries
    provisional = DiagnosticIR(
        schema_version=DIAGNOSTIC_IR_SCHEMA_VERSION,
        diagnostic_id=_require_stable_id(diagnostic_id, "/diagnostic_id"),
        diagnostic_hash="sha256:" + "0" * 64,
        authority_profile=DIAGNOSTIC_AUTHORITY_PROFILE,
        status=_diagnostic_status(entries),
        model_ir_content_hash=snapshot.model_ir_content_hash,
        execution_plan_hash=snapshot.execution_plan_hash,
        operator_hash=snapshot.operator_hash,
        load_pattern_id=snapshot.load_pattern_id,
        state_hash=snapshot.state_hash,
        state_epoch=snapshot.state_epoch,
        equation_scaling_hash=snapshot.equation_scaling_hash,
        reduced_csr_identity_hash=snapshot.reduced_csr_identity_hash,
        source_authority_profile=snapshot.source_authority_profile,
        source_receipt_schema_version=snapshot.source_receipt_schema_version,
        source_receipt_hash=snapshot.source_receipt_hash,
        backend_receipt_hash=snapshot.backend_receipt_hash,
        entries=entries,
        extensions=_freeze_diagnostic_extensions({}),
        _execution_plan=None,
        _state=None,
        _equation_scaling=None,
        _reduced_csr=None,
        _source_adapter=source_adapter,
    )
    diagnostic = replace(
        provisional,
        diagnostic_hash=canonical_hash(
            _diagnostic_payload(provisional, include_diagnostic_hash=False)
        ),
    )
    return validate_diagnostic_ir(diagnostic)


def validate_numerical_result_ir(result: NumericalResultIR) -> NumericalResultIR:
    if type(result) is not NumericalResultIR:
        _fail("numerical_result_type_invalid", "/", "Expected NumericalResultIR.")
    plan = validate_execution_plan(result._execution_plan)
    validate_equation_scaling_binding(plan, scaling=result._equation_scaling)
    reduced = validate_execution_plan_reduced_csr(
        result._reduced_csr, execution_plan=plan
    )
    state = validate_state_ir(result._committed_state, expected_plan=plan)
    if state.role != "committed" or state.epoch < 1:
        _fail(
            "result_state_not_committed_terminal",
            "/bindings/state_hash",
            "NumericalResultIR requires a positive-epoch committed state.",
        )
    scaling_hash = execution_plan_scaling_hash(plan)
    expected_bindings = {
        "model_ir_content_hash": plan.model_ir_content_hash,
        "execution_plan_hash": plan.plan_hash,
        "reduced_csr_identity_hash": reduced.identity_hash,
        "equation_scaling_hash": scaling_hash,
        "operator_hash": plan.operator_hash,
        "state_hash": state.state_hash,
        "state_epoch": state.epoch,
        "load_pattern_id": plan.load_pattern_id,
    }
    actual_bindings = {
        key: getattr(result, key) for key in expected_bindings
    }
    if actual_bindings != expected_bindings:
        _fail(
            "numerical_result_binding_mismatch",
            "/bindings",
            "Result bindings do not match the retained plan/scaling/state objects.",
        )
    if result.source_terminal_reason not in _CONVERGED_TERMINAL_REASONS:
        _fail(
            "result_source_terminal_not_converged",
            "/source_terminal/terminal_reason",
            "Only converged source terminal reasons can create this ResultIR.",
        )
    if result.backend_role not in _BACKEND_ROLES:
        _fail(
            "result_backend_role_invalid",
            "/source_terminal/backend_role",
            "Unsupported backend role.",
        )
    for path, value in (
        ("/result_hash", result.result_hash),
        ("/bindings/model_ir_content_hash", result.model_ir_content_hash),
        ("/bindings/execution_plan_hash", result.execution_plan_hash),
        ("/bindings/reduced_csr_identity_hash", result.reduced_csr_identity_hash),
        ("/bindings/equation_scaling_hash", result.equation_scaling_hash),
        ("/bindings/operator_hash", result.operator_hash),
        ("/bindings/state_hash", result.state_hash),
        ("/source_terminal/run_hash", result.source_run_hash),
        ("/source_terminal/solution_data_hash", result.source_solution_data_hash),
        (
            "/source_terminal/convergence_receipt_hash",
            result.convergence_receipt_hash,
        ),
        (
            "/source_terminal/full_residual_receipt_hash",
            result.full_residual_receipt_hash,
        ),
        (
            "/source_terminal/boundary_condition_receipt_hash",
            result.boundary_condition_receipt_hash,
        ),
        ("/source_terminal/backend_receipt_hash", result.backend_receipt_hash),
    ):
        _require_hash(value, path)
    _require_stable_id(result.result_id, "/result_id")
    _require_stable_id(
        result.source_run_schema_version, "/source_terminal/run_schema_version"
    )
    if result.result_kind != NUMERICAL_RESULT_KIND:
        _fail("result_kind_invalid", "/result_kind", "Unsupported result kind.")
    if result.authority_profile != NUMERICAL_RESULT_AUTHORITY_PROFILE:
        _fail(
            "result_authority_profile_invalid",
            "/authority_profile",
            "Unsupported numerical result authority profile.",
        )
    if result.state_epoch != state.epoch or result.dof_count != state.dof_count:
        _fail(
            "numerical_result_state_shape_mismatch",
            "/numerical_state",
            "State epoch or DOF count is stale.",
        )
    if result.load_factor != state.load_factor or result.time_s != state.time_s:
        _fail(
            "numerical_result_state_coordinate_mismatch",
            "/numerical_state",
            "Load factor or time does not match committed StateIR.",
        )
    displacement = result._displacement_global_si
    _validate_displacement_array(displacement, state.dof_count)
    if not np.array_equal(displacement, state.displacement_si):
        _fail(
            "numerical_result_displacement_state_mismatch",
            "/numerical_state/displacement_artifact",
            "Result displacement bytes differ from committed StateIR.",
        )
    expected_descriptor = _displacement_descriptor(result.result_id, displacement)
    if result.displacement_artifact != expected_descriptor:
        _fail(
            "numerical_result_artifact_descriptor_mismatch",
            "/numerical_state/displacement_artifact",
            "Displacement descriptor is stale for the retained bytes.",
        )
    free_solution = immutable_array(
        state.displacement_si[plan.array("free_dofs")], dtype="<f8"
    )
    if result.source_free_solution_value_count != int(free_solution.size):
        _fail(
            "result_source_solution_size_mismatch",
            "/source_terminal/free_solution_value_count",
            "Source free-solution size does not match reduced CSR.",
        )
    if result.source_solution_data_hash != array_data_hash(free_solution):
        _fail(
            "result_source_solution_state_mismatch",
            "/source_terminal/solution_data_hash",
            "Source solution hash differs from committed StateIR free DOFs.",
        )
    if result.diagnostic_ir_hashes != _sorted_unique_hashes(
        result.diagnostic_ir_hashes, "/diagnostic_ir_hashes"
    ):
        _fail(
            "diagnostic_hashes_not_canonical",
            "/diagnostic_ir_hashes",
            "Diagnostic hashes must be sorted and unique.",
        )
    _validate_extensions(result.extensions)
    expected_hash = canonical_hash(
        _numerical_result_payload(result, include_result_hash=False)
    )
    if result.result_hash != expected_hash:
        _fail(
            "numerical_result_hash_mismatch",
            "/result_hash",
            "Result hash does not match the canonical authority payload.",
        )
    validate_numerical_result_ir_manifest(
        _numerical_result_payload(result, include_result_hash=True)
    )
    return result


def validate_diagnostic_ir(diagnostic: DiagnosticIR) -> DiagnosticIR:
    if type(diagnostic) is not DiagnosticIR:
        _fail("diagnostic_ir_type_invalid", "/", "Expected DiagnosticIR.")
    if diagnostic._source_adapter is not None:
        if any(value is not None for value in (
            diagnostic._execution_plan, diagnostic._state,
            diagnostic._equation_scaling, diagnostic._reduced_csr,
        )):
            _fail("diagnostic_source_mode_ambiguous", "/", "Use one retained source mode.")
        snapshot = _adapter_diagnostic_snapshot(diagnostic._source_adapter)
        expected_bindings = {
            "model_ir_content_hash": snapshot.model_ir_content_hash,
            "execution_plan_hash": snapshot.execution_plan_hash,
            "operator_hash": snapshot.operator_hash,
            "load_pattern_id": snapshot.load_pattern_id,
            "state_hash": snapshot.state_hash,
            "state_epoch": snapshot.state_epoch,
            "equation_scaling_hash": snapshot.equation_scaling_hash,
            "reduced_csr_identity_hash": snapshot.reduced_csr_identity_hash,
        }
        expected_source = {
            "source_authority_profile": snapshot.source_authority_profile,
            "source_receipt_schema_version": snapshot.source_receipt_schema_version,
            "source_receipt_hash": snapshot.source_receipt_hash,
            "backend_receipt_hash": snapshot.backend_receipt_hash,
            "entries": snapshot.entries,
        }
        if any(getattr(diagnostic, key) != value for key, value in expected_source.items()):
            _fail("diagnostic_source_adapter_mismatch", "/source", "Diagnostic does not match adapter replay.")
    else:
        if diagnostic._execution_plan is None:
            _fail("diagnostic_execution_plan_missing", "/bindings", "ExecutionPlan is required.")
        plan = validate_execution_plan(diagnostic._execution_plan)
        state = diagnostic._state
        if state is not None:
            validate_state_ir(state, expected_plan=plan)
        if (diagnostic._equation_scaling is None) != (diagnostic._reduced_csr is None):
            _fail(
                "diagnostic_solver_binding_incomplete", "/bindings",
                "Equation scaling and reduced CSR must be supplied together.")
        if diagnostic._equation_scaling is not None:
            validate_equation_scaling_binding(plan, scaling=diagnostic._equation_scaling)
            validate_execution_plan_reduced_csr(diagnostic._reduced_csr, execution_plan=plan)
        expected_bindings = {
            "model_ir_content_hash": plan.model_ir_content_hash,
            "execution_plan_hash": plan.plan_hash,
            "operator_hash": plan.operator_hash,
            "load_pattern_id": plan.load_pattern_id,
            "state_hash": None if state is None else state.state_hash,
            "state_epoch": None if state is None else state.epoch,
            "equation_scaling_hash": None if diagnostic._equation_scaling is None else diagnostic._equation_scaling.scaling_hash,
            "reduced_csr_identity_hash": None if diagnostic._reduced_csr is None else diagnostic._reduced_csr.identity_hash,
        }
    if {key: getattr(diagnostic, key) for key in expected_bindings} != expected_bindings:
        _fail(
            "diagnostic_binding_mismatch",
            "/bindings",
            "Diagnostic bindings do not match retained source objects.",
        )
    _require_stable_id(diagnostic.diagnostic_id, "/diagnostic_id")
    _require_stable_id(
        diagnostic.source_receipt_schema_version,
        "/source/receipt_schema_version",
    )
    for path, value in (
        ("/diagnostic_hash", diagnostic.diagnostic_hash),
        ("/bindings/model_ir_content_hash", diagnostic.model_ir_content_hash),
        ("/bindings/execution_plan_hash", diagnostic.execution_plan_hash),
        ("/bindings/operator_hash", diagnostic.operator_hash),
        ("/source/receipt_hash", diagnostic.source_receipt_hash),
    ):
        _require_hash(value, path)
    if diagnostic.backend_receipt_hash is not None:
        _require_hash(diagnostic.backend_receipt_hash, "/source/backend_receipt_hash")
    if diagnostic.authority_profile != DIAGNOSTIC_AUTHORITY_PROFILE:
        _fail(
            "diagnostic_authority_profile_invalid",
            "/authority_profile",
            "Diagnostics must retain the non-authoritative profile.",
        )
    if diagnostic.source_authority_profile not in _SOURCE_AUTHORITY_PROFILES:
        _fail(
            "diagnostic_source_authority_profile_invalid",
            "/source/authority_profile",
            "Unsupported diagnostic source authority profile.",
        )
    if not diagnostic.entries:
        _fail("diagnostic_entries_empty", "/entries", "At least one entry is required.")
    if diagnostic.entries != tuple(
        sorted(diagnostic.entries, key=_diagnostic_entry_sort_key)
    ):
        _fail(
            "diagnostic_entries_not_canonical",
            "/entries",
            "Diagnostic entries must use canonical sort order.",
        )
    if len(set(_diagnostic_entry_sort_key(row) for row in diagnostic.entries)) != len(
        diagnostic.entries
    ):
        _fail(
            "diagnostic_entries_duplicate",
            "/entries",
            "Diagnostic entries must be unique.",
        )
    for index, entry in enumerate(diagnostic.entries):
        _validate_diagnostic_entry(entry, f"/entries/{index}")
    if diagnostic.status != _diagnostic_status(diagnostic.entries):
        _fail(
            "diagnostic_status_mismatch",
            "/status",
            "Diagnostic status does not match its entry dispositions.",
        )
    _validate_extensions(diagnostic.extensions)
    expected_hash = canonical_hash(
        _diagnostic_payload(diagnostic, include_diagnostic_hash=False)
    )
    if diagnostic.diagnostic_hash != expected_hash:
        _fail(
            "diagnostic_hash_mismatch",
            "/diagnostic_hash",
            "Diagnostic hash does not match the canonical observation payload.",
        )
    validate_diagnostic_ir_manifest(
        _diagnostic_payload(diagnostic, include_diagnostic_hash=True)
    )
    return diagnostic


def _adapter_diagnostic_snapshot(
    source_adapter: DiagnosticIRSourceAdapter,
) -> DiagnosticIRSourceSnapshot:
    validator = getattr(source_adapter, "validate_diagnostic_ir_source", None)
    if not callable(validator):
        _fail("diagnostic_source_adapter_invalid", "/", "Source adapter must expose deterministic replay validation.")
    return _validate_diagnostic_source_snapshot(validator())


def _validate_diagnostic_source_snapshot(
    snapshot: DiagnosticIRSourceSnapshot,
) -> DiagnosticIRSourceSnapshot:
    if type(snapshot) is not DiagnosticIRSourceSnapshot:
        _fail("diagnostic_source_snapshot_invalid", "/", "Expected DiagnosticIRSourceSnapshot.")
    _require_stable_id(snapshot.load_pattern_id, "/bindings/load_pattern_id")
    _require_stable_id(snapshot.source_receipt_schema_version, "/source/receipt_schema_version")
    for path, value in (
        ("/bindings/model_ir_content_hash", snapshot.model_ir_content_hash),
        ("/bindings/execution_plan_hash", snapshot.execution_plan_hash),
        ("/bindings/operator_hash", snapshot.operator_hash),
        ("/source/receipt_hash", snapshot.source_receipt_hash),
    ):
        _require_hash(value, path)
    for path, value in (
        ("/bindings/state_hash", snapshot.state_hash),
        ("/bindings/equation_scaling_hash", snapshot.equation_scaling_hash),
        ("/bindings/reduced_csr_identity_hash", snapshot.reduced_csr_identity_hash),
        ("/source/backend_receipt_hash", snapshot.backend_receipt_hash),
    ):
        if value is not None:
            _require_hash(value, path)
    if (snapshot.state_hash is None) != (snapshot.state_epoch is None):
        _fail("diagnostic_state_binding_incomplete", "/bindings/state_hash", "State hash and epoch must be supplied together.")
    if snapshot.state_epoch is not None:
        _require_exact_int(snapshot.state_epoch, "/bindings/state_epoch", minimum=0)
    if (snapshot.equation_scaling_hash is None) != (snapshot.reduced_csr_identity_hash is None):
        _fail("diagnostic_solver_binding_incomplete", "/bindings", "Scaling and reduced CSR identities must be supplied together.")
    if snapshot.source_authority_profile not in _SOURCE_AUTHORITY_PROFILES:
        _fail("diagnostic_source_authority_profile_invalid", "/source/authority_profile", "Unsupported source authority profile.")
    if type(snapshot.entries) is not tuple or not snapshot.entries:
        _fail("diagnostic_entries_empty", "/entries", "At least one entry is required.")
    if snapshot.entries != tuple(sorted(snapshot.entries, key=_diagnostic_entry_sort_key)):
        _fail("diagnostic_entries_not_canonical", "/entries", "Entries must use canonical sort order.")
    if len(set(_diagnostic_entry_sort_key(row) for row in snapshot.entries)) != len(snapshot.entries):
        _fail("diagnostic_entries_duplicate", "/entries", "Entries must be unique.")
    for index, entry in enumerate(snapshot.entries):
        _validate_diagnostic_entry(entry, f"/entries/{index}")
    return snapshot


def validate_numerical_result_ir_manifest(payload: Any) -> Mapping[str, Any]:
    manifest = _validate_schema(
        payload,
        schema_name="numerical_result_ir_v1.schema.json",
        code="numerical_result_schema_invalid",
    )
    state = manifest["numerical_state"]
    descriptor = state["displacement_artifact"]
    dof_count = int(state["dof_count"])
    bindings = manifest["bindings"]
    source = manifest["source_terminal"]
    _require_stable_id(manifest["result_id"], "/result_id")
    _require_stable_id(bindings["load_pattern_id"], "/bindings/load_pattern_id")
    _require_stable_id(
        source["run_schema_version"], "/source_terminal/run_schema_version"
    )
    for path, value in (
        ("/result_hash", manifest["result_hash"]),
        ("/bindings/model_ir_content_hash", bindings["model_ir_content_hash"]),
        ("/bindings/execution_plan_hash", bindings["execution_plan_hash"]),
        (
            "/bindings/reduced_csr_identity_hash",
            bindings["reduced_csr_identity_hash"],
        ),
        ("/bindings/equation_scaling_hash", bindings["equation_scaling_hash"]),
        ("/bindings/operator_hash", bindings["operator_hash"]),
        ("/bindings/state_hash", bindings["state_hash"]),
        ("/source_terminal/run_hash", source["run_hash"]),
        ("/source_terminal/solution_data_hash", source["solution_data_hash"]),
        (
            "/source_terminal/convergence_receipt_hash",
            source["convergence_receipt_hash"],
        ),
        (
            "/source_terminal/full_residual_receipt_hash",
            source["full_residual_receipt_hash"],
        ),
        (
            "/source_terminal/boundary_condition_receipt_hash",
            source["boundary_condition_receipt_hash"],
        ),
        ("/source_terminal/backend_receipt_hash", source["backend_receipt_hash"]),
        (
            "/numerical_state/displacement_artifact/data_hash",
            descriptor["data_hash"],
        ),
        (
            "/numerical_state/displacement_artifact/content_hash",
            descriptor["content_hash"],
        ),
    ):
        _require_hash(value, path)
    for index, value in enumerate(manifest["diagnostic_ir_hashes"]):
        _require_hash(value, f"/diagnostic_ir_hashes/{index}")
    _freeze_extensions(manifest["extensions"])
    if bindings["state_epoch"] != state["epoch"]:
        _fail(
            "numerical_result_state_epoch_mismatch",
            "/bindings/state_epoch",
            "Binding state epoch must match the numerical-state epoch.",
        )
    if int(source["free_solution_value_count"]) > dof_count:
        _fail(
            "result_source_solution_size_impossible",
            "/source_terminal/free_solution_value_count",
            "Free-solution value count cannot exceed the global DOF count.",
        )
    if descriptor["shape"] != [dof_count] or descriptor["byte_length"] != dof_count * 8:
        _fail(
            "numerical_result_artifact_shape_mismatch",
            "/numerical_state/displacement_artifact",
            "Displacement artifact shape and byte length must match DOF count.",
        )
    expected_uri = _displacement_artifact_uri(str(manifest["result_id"]))
    if descriptor["artifact_uri"] != expected_uri:
        _fail(
            "numerical_result_artifact_uri_invalid",
            "/numerical_state/displacement_artifact/artifact_uri",
            "Displacement artifact URI is not canonical for the result ID.",
        )
    diagnostic_hashes = tuple(manifest["diagnostic_ir_hashes"])
    if diagnostic_hashes != tuple(sorted(set(diagnostic_hashes))):
        _fail(
            "diagnostic_hashes_not_canonical",
            "/diagnostic_ir_hashes",
            "Diagnostic hashes must be sorted and unique.",
        )
    without_hash = dict(manifest)
    claimed_hash = without_hash.pop("result_hash")
    if claimed_hash != canonical_hash(without_hash):
        _fail(
            "numerical_result_hash_mismatch",
            "/result_hash",
            "Manifest result hash does not match its canonical payload.",
        )
    return manifest


def validate_diagnostic_ir_manifest(payload: Any) -> Mapping[str, Any]:
    manifest = _validate_schema(
        payload,
        schema_name="diagnostic_ir_v1.schema.json",
        code="diagnostic_schema_invalid",
    )
    _require_stable_id(manifest["diagnostic_id"], "/diagnostic_id")
    bindings = manifest["bindings"]
    _require_stable_id(bindings["load_pattern_id"], "/bindings/load_pattern_id")
    source = manifest["source"]
    _require_stable_id(
        source["receipt_schema_version"], "/source/receipt_schema_version"
    )
    for path, value in (
        ("/diagnostic_hash", manifest["diagnostic_hash"]),
        ("/bindings/model_ir_content_hash", bindings["model_ir_content_hash"]),
        ("/bindings/execution_plan_hash", bindings["execution_plan_hash"]),
        ("/bindings/operator_hash", bindings["operator_hash"]),
        ("/source/receipt_hash", source["receipt_hash"]),
    ):
        _require_hash(value, path)
    for path, value in (
        ("/bindings/state_hash", bindings["state_hash"]),
        ("/bindings/equation_scaling_hash", bindings["equation_scaling_hash"]),
        (
            "/bindings/reduced_csr_identity_hash",
            bindings["reduced_csr_identity_hash"],
        ),
        ("/source/backend_receipt_hash", source["backend_receipt_hash"]),
    ):
        if value is not None:
            _require_hash(value, path)
    _freeze_diagnostic_extensions(manifest["extensions"])
    entries = manifest["entries"]
    keys = [
        (
            row["code"],
            row["path"],
            row["severity"],
            row["disposition"],
            int(row["occurrence_count"]),
            tuple(row["evidence_hashes"]),
        )
        for row in entries
    ]
    if keys != sorted(keys) or len(set(keys)) != len(keys):
        _fail(
            "diagnostic_entries_not_canonical",
            "/entries",
            "Diagnostic entries must be sorted and unique.",
        )
    for index, row in enumerate(entries):
        _validate_diagnostic_entry_mapping(row, f"/entries/{index}")
    expected_status = _diagnostic_status_from_mappings(entries)
    if manifest["status"] != expected_status:
        _fail(
            "diagnostic_status_mismatch",
            "/status",
            "Diagnostic status does not match entry dispositions.",
        )
    if manifest["summary"] != _diagnostic_summary_from_mappings(entries):
        _fail(
            "diagnostic_summary_mismatch",
            "/summary",
            "Diagnostic summary does not match entries.",
        )
    if (bindings["state_hash"] is None) != (bindings["state_epoch"] is None):
        _fail(
            "diagnostic_state_binding_incomplete",
            "/bindings/state_hash",
            "State hash and epoch must both be null or both be present.",
        )
    if (bindings["equation_scaling_hash"] is None) != (
        bindings["reduced_csr_identity_hash"] is None
    ):
        _fail(
            "diagnostic_solver_binding_incomplete",
            "/bindings/equation_scaling_hash",
            "Scaling and reduced CSR hashes must both be null or both be present.",
        )
    without_hash = dict(manifest)
    claimed_hash = without_hash.pop("diagnostic_hash")
    if claimed_hash != canonical_hash(without_hash):
        _fail(
            "diagnostic_hash_mismatch",
            "/diagnostic_hash",
            "Manifest diagnostic hash does not match its canonical payload.",
        )
    return manifest


def validate_numerical_result_displacement_bytes(
    result: NumericalResultIR,
    data: bytes | bytearray | memoryview,
) -> np.ndarray:
    checked = validate_numerical_result_ir(result)
    raw = bytes(data)
    descriptor = checked.displacement_artifact
    if len(raw) != descriptor.byte_length:
        _fail(
            "numerical_result_artifact_byte_length_mismatch",
            "/numerical_state/displacement_artifact/byte_length",
            "Displacement artifact byte length does not match its descriptor.",
        )
    array = immutable_array(np.frombuffer(raw, dtype="<f8"), dtype="<f8")
    if array_data_hash(array) != descriptor.data_hash:
        _fail(
            "numerical_result_artifact_hash_mismatch",
            "/numerical_state/displacement_artifact/data_hash",
            "Displacement artifact bytes do not match the descriptor hash.",
        )
    expected = _displacement_descriptor(checked.result_id, array)
    if expected != descriptor:
        _fail(
            "numerical_result_artifact_content_hash_mismatch",
            "/numerical_state/displacement_artifact/content_hash",
            "Displacement artifact content hash is invalid.",
        )
    return array


def write_numerical_result_displacement_artifact(
    result: NumericalResultIR,
    target: str | Path,
) -> Path:
    checked = validate_numerical_result_ir(result)
    destination = Path(target)
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = checked.displacement_global_si.tobytes(order="C")
    try:
        handle = destination.open("xb")
    except FileExistsError:
        _fail(
            "numerical_result_artifact_target_exists",
            "/numerical_state/displacement_artifact/artifact_uri",
            "Result artifacts are immutable and cannot overwrite a target.",
        )
    try:
        with handle:
            handle.write(raw)
        validate_numerical_result_displacement_bytes(checked, destination.read_bytes())
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def _numerical_result_payload(
    result: NumericalResultIR, *, include_result_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": result.schema_version,
        "result_id": result.result_id,
        "result_kind": result.result_kind,
        "authority_profile": result.authority_profile,
        "promotion_basis": NUMERICAL_RESULT_PROMOTION_BASIS,
        "bindings": {
            "model_ir_content_hash": result.model_ir_content_hash,
            "execution_plan_hash": result.execution_plan_hash,
            "reduced_csr_identity_hash": result.reduced_csr_identity_hash,
            "equation_scaling_hash": result.equation_scaling_hash,
            "operator_hash": result.operator_hash,
            "state_hash": result.state_hash,
            "state_epoch": result.state_epoch,
            "load_pattern_id": result.load_pattern_id,
        },
        "source_terminal": {
            "run_schema_version": result.source_run_schema_version,
            "run_hash": result.source_run_hash,
            "source_authority": "non_authoritative_solver_recurrence",
            "terminal_reason": result.source_terminal_reason,
            "solution_data_hash": result.source_solution_data_hash,
            "free_solution_value_count": result.source_free_solution_value_count,
            "convergence_receipt_hash": result.convergence_receipt_hash,
            "full_residual_receipt_hash": result.full_residual_receipt_hash,
            "boundary_condition_receipt_hash": result.boundary_condition_receipt_hash,
            "backend_role": result.backend_role,
            "backend_receipt_hash": result.backend_receipt_hash,
            "residual_sign": EXECUTION_PLAN_RESIDUAL_SIGN,
            "fallback_count": 0,
            "regularization_count": 0,
            "convergence_gate_passed": True,
            "independent_full_residual_gate_passed": True,
            "boundary_condition_gate_passed": True,
            "committed_state_gate_passed": True,
        },
        "numerical_state": {
            "role": "committed",
            "epoch": result.state_epoch,
            "load_factor": result.load_factor,
            "time_s": result.time_s,
            "dof_count": result.dof_count,
            "dof_components": list(EXECUTION_PLAN_DOF_COMPONENTS),
            "displacement_artifact": result.displacement_artifact.to_dict(),
        },
        "authority": dict(NUMERICAL_RESULT_AUTHORITY_AXES),
        "diagnostic_ir_hashes": list(result.diagnostic_ir_hashes),
        "claim_boundary": dict(NUMERICAL_RESULT_CLAIM_BOUNDARY),
        "extensions": _thaw(result.extensions),
    }
    if include_result_hash:
        payload["result_hash"] = result.result_hash
    return payload


def _diagnostic_payload(
    diagnostic: DiagnosticIR, *, include_diagnostic_hash: bool
) -> dict[str, Any]:
    entries = [row.to_dict() for row in diagnostic.entries]
    payload: dict[str, Any] = {
        "schema_version": diagnostic.schema_version,
        "diagnostic_id": diagnostic.diagnostic_id,
        "authority_profile": diagnostic.authority_profile,
        "status": diagnostic.status,
        "bindings": {
            "model_ir_content_hash": diagnostic.model_ir_content_hash,
            "execution_plan_hash": diagnostic.execution_plan_hash,
            "operator_hash": diagnostic.operator_hash,
            "load_pattern_id": diagnostic.load_pattern_id,
            "state_hash": diagnostic.state_hash,
            "state_epoch": diagnostic.state_epoch,
            "equation_scaling_hash": diagnostic.equation_scaling_hash,
            "reduced_csr_identity_hash": diagnostic.reduced_csr_identity_hash,
        },
        "source": {
            "authority_profile": diagnostic.source_authority_profile,
            "receipt_schema_version": diagnostic.source_receipt_schema_version,
            "receipt_hash": diagnostic.source_receipt_hash,
            "backend_receipt_hash": diagnostic.backend_receipt_hash,
        },
        "entries": entries,
        "summary": _diagnostic_summary_from_mappings(entries),
        "authority": dict(DIAGNOSTIC_AUTHORITY_AXES),
        "claim_boundary": dict(DIAGNOSTIC_CLAIM_BOUNDARY),
        "extensions": _thaw(diagnostic.extensions),
    }
    if include_diagnostic_hash:
        payload["diagnostic_hash"] = diagnostic.diagnostic_hash
    return payload


def _displacement_descriptor(
    result_id: str, displacement: np.ndarray
) -> NumericalResultVectorDescriptor:
    metadata = {
        "name": NUMERICAL_RESULT_DISPLACEMENT_ARTIFACT_NAME,
        "dtype": "<f8",
        "shape": [int(displacement.size)],
        "layout": "C",
        "byte_order": "little",
        "byte_length": int(displacement.nbytes),
        "storage_profile": NUMERICAL_RESULT_STORAGE_PROFILE,
        "unit_profile": NUMERICAL_RESULT_DISPLACEMENT_UNIT_PROFILE,
        "artifact_uri": _displacement_artifact_uri(result_id),
    }
    return NumericalResultVectorDescriptor(
        **metadata,
        data_hash=array_data_hash(displacement),
        content_hash=array_content_hash(metadata, displacement),
    )


def _displacement_artifact_uri(result_id: str) -> str:
    return (
        f"artifact://engine-v2/results/{result_id}/"
        f"{NUMERICAL_RESULT_DISPLACEMENT_FILENAME}"
    )


def _validate_displacement_array(array: Any, dof_count: int) -> None:
    if not isinstance(array, np.ndarray):
        _fail(
            "numerical_result_artifact_array_invalid",
            "/numerical_state/displacement_artifact",
            "Expected a NumPy array.",
        )
    if array.dtype.str != "<f8" or array.shape != (dof_count,):
        _fail(
            "numerical_result_artifact_array_invalid",
            "/numerical_state/displacement_artifact",
            "Expected a flat canonical little-endian FP64 global DOF vector.",
        )
    if not array.flags.c_contiguous or not has_immutable_bytes_backing(array):
        _fail(
            "numerical_result_artifact_array_mutable",
            "/numerical_state/displacement_artifact",
            "Result artifact arrays must be immutable bytes-backed C-order arrays.",
        )
    if not np.all(np.isfinite(array)):
        _fail(
            "numerical_result_artifact_array_nonfinite",
            "/numerical_state/displacement_artifact",
            "Result displacement values must be finite.",
        )


def _validate_diagnostic_entry(entry: DiagnosticEntry, path: str) -> None:
    if type(entry) is not DiagnosticEntry:
        _fail("diagnostic_entry_type_invalid", path, "Expected DiagnosticEntry.")
    _require_diagnostic_code(entry.code, f"{path}/code")
    _require_json_pointer(entry.path, f"{path}/path")
    if entry.severity not in _DIAGNOSTIC_SEVERITIES:
        _fail("diagnostic_severity_invalid", f"{path}/severity", "Invalid severity.")
    if entry.disposition not in _DIAGNOSTIC_DISPOSITIONS:
        _fail(
            "diagnostic_disposition_invalid",
            f"{path}/disposition",
            "Invalid disposition.",
        )
    _require_exact_int(entry.occurrence_count, f"{path}/occurrence_count", minimum=1)
    if entry.evidence_hashes != _sorted_unique_hashes(
        entry.evidence_hashes, f"{path}/evidence_hashes"
    ):
        _fail(
            "diagnostic_evidence_hashes_not_canonical",
            f"{path}/evidence_hashes",
            "Evidence hashes must be sorted and unique.",
        )
    _validate_diagnostic_severity_disposition(
        entry.severity, entry.disposition, path
    )


def _validate_diagnostic_entry_mapping(row: Mapping[str, Any], path: str) -> None:
    _require_diagnostic_code(row["code"], f"{path}/code")
    _require_json_pointer(row["path"], f"{path}/path")
    evidence_hashes = tuple(row["evidence_hashes"])
    for index, value in enumerate(evidence_hashes):
        _require_hash(value, f"{path}/evidence_hashes/{index}")
    if evidence_hashes != tuple(sorted(set(evidence_hashes))):
        _fail(
            "diagnostic_evidence_hashes_not_canonical",
            f"{path}/evidence_hashes",
            "Evidence hashes must be sorted and unique.",
        )
    _validate_diagnostic_severity_disposition(
        str(row["severity"]), str(row["disposition"]), path
    )


def _validate_diagnostic_severity_disposition(
    severity: str, disposition: str, path: str
) -> None:
    if disposition == "failed" and severity != "error":
        _fail(
            "diagnostic_failed_severity_invalid",
            f"{path}/severity",
            "Failed diagnostics must use error severity.",
        )
    if disposition in {"unsupported", "fallback"} and severity == "info":
        _fail(
            "diagnostic_disposition_severity_invalid",
            f"{path}/severity",
            "Unsupported and fallback diagnostics cannot use info severity.",
        )
    if severity == "error" and disposition != "failed":
        _fail(
            "diagnostic_error_disposition_invalid",
            f"{path}/disposition",
            "Error severity is reserved for failed diagnostics.",
        )


def _diagnostic_entry_sort_key(entry: DiagnosticEntry) -> tuple[Any, ...]:
    return (
        entry.code,
        entry.path,
        entry.severity,
        entry.disposition,
        entry.occurrence_count,
        entry.evidence_hashes,
    )


def _diagnostic_status(entries: Sequence[DiagnosticEntry]) -> Literal[
    "observed", "partial", "blocked"
]:
    return _diagnostic_status_from_mappings([row.to_dict() for row in entries])


def _diagnostic_status_from_mappings(
    entries: Sequence[Mapping[str, Any]],
) -> Literal["observed", "partial", "blocked"]:
    dispositions = {str(row["disposition"]) for row in entries}
    if "failed" in dispositions:
        return "blocked"
    if dispositions & {"partial", "unsupported", "fallback"}:
        return "partial"
    return "observed"


def _diagnostic_summary_from_mappings(
    entries: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    return {
        "entry_count": len(entries),
        "info_count": sum(row["severity"] == "info" for row in entries),
        "warning_count": sum(row["severity"] == "warning" for row in entries),
        "error_count": sum(row["severity"] == "error" for row in entries),
        "partial_count": sum(row["disposition"] == "partial" for row in entries),
        "unsupported_count": sum(
            row["disposition"] == "unsupported" for row in entries
        ),
        "fallback_count": sum(row["disposition"] == "fallback" for row in entries),
        "failed_count": sum(row["disposition"] == "failed" for row in entries),
    }


def _sorted_unique_hashes(value: Sequence[str], path: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail("hash_sequence_invalid", path, "Expected a sequence of SHA-256 hashes.")
    values = tuple(value)
    for index, item in enumerate(values):
        _require_hash(item, f"{path}/{index}")
    if len(set(values)) != len(values):
        _fail("hash_sequence_duplicate", path, "Hash sequence contains duplicates.")
    return tuple(sorted(values))


def _freeze_extensions(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("extensions_invalid", "/extensions", "Expected an object.")
    try:
        normalized = json.loads(canonical_json_bytes(value))
    except (CanonicalContractError, json.JSONDecodeError) as exc:
        _fail("extensions_invalid", "/extensions", str(exc))
    for key in normalized:
        if _EXTENSION_KEY_PATTERN.fullmatch(key) is None:
            _fail(
                "extension_key_invalid",
                f"/extensions/{key}",
                "Extension keys must be namespaced.",
            )
    return _freeze(normalized)


def _freeze_diagnostic_extensions(value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen = _freeze_extensions(value)
    if frozen:
        _fail(
            "diagnostic_extensions_not_supported",
            "/extensions",
            "DiagnosticIR v1 does not allow extension payloads.",
        )
    return frozen


def _validate_extensions(value: Mapping[str, Any]) -> None:
    if not isinstance(value, MappingProxyType) or not _is_frozen(value):
        _fail(
            "extensions_mutable",
            "/extensions",
            "Extensions must be deeply immutable.",
        )
    _freeze_extensions(_thaw(value))


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _is_frozen(value: Any) -> bool:
    if isinstance(value, MappingProxyType):
        return all(_is_frozen(item) for item in value.values())
    if isinstance(value, tuple):
        return all(_is_frozen(item) for item in value)
    return value is None or type(value) in (str, bool, int, float)


def _require_hash(value: Any, path: str) -> str:
    if not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None:
        _fail("hash_invalid", path, "Expected sha256:<64 lowercase hex>.")
    return value


def _require_stable_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or _STABLE_ID_PATTERN.fullmatch(value) is None:
        _fail("stable_id_invalid", path, "Invalid stable identifier.")
    return value


def _require_diagnostic_code(value: Any, path: str) -> str:
    if not isinstance(value, str) or _DIAGNOSTIC_CODE_PATTERN.fullmatch(value) is None:
        _fail(
            "diagnostic_code_invalid",
            path,
            "Diagnostic codes must be stable lowercase snake-case identifiers.",
        )
    return value


def _require_json_pointer(value: Any, path: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or any(ord(character) < 0x20 for character in value)
        or re.search(r"~(?![01])", value) is not None
    ):
        _fail(
            "diagnostic_path_invalid",
            path,
            "Diagnostic paths must be sanitized absolute JSON pointers.",
        )
    return value


def _require_choice(
    value: Any,
    choices: frozenset[str],
    path: str,
    code: str,
) -> str:
    if not isinstance(value, str) or value not in choices:
        _fail(code, path, "Unsupported contract value.")
    return value


def _require_exact_int(value: Any, path: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail("integer_invalid", path, f"Expected an integer >= {minimum}.")
    return value


@lru_cache(maxsize=2)
def _schema_validator(schema_name: str) -> Draft202012Validator:
    resource = resources.files("structural_analysis.schemas").joinpath(schema_name)
    with resource.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    if not isinstance(schema, dict):  # pragma: no cover
        raise TypeError("Packaged ResultIR schema must be an object.")
    Draft202012Validator.check_schema(schema)
    return _StrictDraft202012Validator(schema)


def _validate_schema(
    payload: Any, *, schema_name: str, code: str
) -> Mapping[str, Any]:
    errors = sorted(
        _schema_validator(schema_name).iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail(code, path or "/", error.message)
    if not isinstance(payload, Mapping):  # pragma: no cover - schema invariant
        _fail(code, "/", "Expected an object.")
    return payload


def _fail(code: str, path: str, message: str) -> None:
    raise ResultIRError(code, path, message)


__all__ = [
    "DIAGNOSTIC_AUTHORITY_AXES",
    "DIAGNOSTIC_AUTHORITY_PROFILE",
    "DIAGNOSTIC_CLAIM_BOUNDARY",
    "DIAGNOSTIC_IR_SCHEMA_VERSION",
    "NUMERICAL_RESULT_AUTHORITY_AXES",
    "NUMERICAL_RESULT_AUTHORITY_PROFILE",
    "NUMERICAL_RESULT_CLAIM_BOUNDARY",
    "NUMERICAL_RESULT_DISPLACEMENT_ARTIFACT_NAME",
    "NUMERICAL_RESULT_DISPLACEMENT_FILENAME",
    "NUMERICAL_RESULT_DISPLACEMENT_UNIT_PROFILE",
    "NUMERICAL_RESULT_IR_SCHEMA_VERSION",
    "NUMERICAL_RESULT_KIND",
    "NUMERICAL_RESULT_PROMOTION_BASIS",
    "NUMERICAL_RESULT_STORAGE_PROFILE",
    "DiagnosticEntry",
    "DiagnosticIR",
    "DiagnosticIRSourceAdapter",
    "DiagnosticIRSourceSnapshot",
    "NumericalResultIR",
    "NumericalResultVectorDescriptor",
    "ResultIRError",
    "create_diagnostic_entry",
    "create_diagnostic_ir",
    "create_adapter_bound_diagnostic_ir",
    "create_numerical_result_ir",
    "validate_diagnostic_ir",
    "validate_diagnostic_ir_manifest",
    "validate_numerical_result_displacement_bytes",
    "validate_numerical_result_ir",
    "validate_numerical_result_ir_manifest",
    "write_numerical_result_displacement_artifact",
]
