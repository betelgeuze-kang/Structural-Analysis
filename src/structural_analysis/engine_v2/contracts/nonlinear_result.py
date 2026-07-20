"""Authority-separated nonlinear numerical result contract.

A nonlinear result may be created only from one exact positive-epoch committed
``StateIR``, one committed ordered ``MaterialStateBundle`` bound to that state,
and one terminal receipt bound to both.  The terminal receipt must prove
residual and increment closure with zero fallback and regularization.

This type grants bounded numerical/convergence/displacement/material-state
authority only. Reaction, member force, integration-point engineering output,
design/code compliance, release, and commercial authority remain outside it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from functools import lru_cache
from importlib import resources
import json
import math
import re
from types import MappingProxyType
from typing import Any, Literal, Protocol

from jsonschema import Draft202012Validator, validators
import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.equation_scaling import (
    EquationScaling,
    execution_plan_scaling_hash,
    validate_equation_scaling_binding,
)
from structural_analysis.engine_v2.contracts.execution_plan import (
    ExecutionPlan,
    validate_execution_plan,
)
from structural_analysis.engine_v2.contracts.execution_plan_reduced_csr import (
    ExecutionPlanReducedCSR,
    validate_execution_plan_reduced_csr,
)
from structural_analysis.engine_v2.contracts.material_state_bundle import (
    MaterialStateBundle,
    validate_material_state_bundle,
)
from structural_analysis.engine_v2.contracts.state_ir import StateIR, validate_state_ir


NONLINEAR_TERMINAL_RECEIPT_SCHEMA_VERSION = (
    "structural-analysis-nonlinear-terminal-receipt.v1"
)
NONLINEAR_NUMERICAL_RESULT_IR_SCHEMA_VERSION = (
    "structural-analysis-nonlinear-numerical-result-ir.v1"
)
NONLINEAR_NUMERICAL_RESULT_AUTHORITY_PROFILE = (
    "authoritative_converged_nonlinear_numerical_and_terminal_material_state.v1"
)
NONLINEAR_NUMERICAL_RESULT_KIND = "nonlinear_static_numerical_state"
NONLINEAR_RESULT_STORAGE_PROFILE = "canonical_little_endian_fp64_binary.v1"
NONLINEAR_RESULT_DISPLACEMENT_UNIT_PROFILE = "node_major_ux_uy_uz_m_rx_ry_rz_rad.v1"
NONLINEAR_TERMINAL_RESIDUAL_NORM_PROFILE = "dimensionless_equation_scaled_free_linf.v1"
NONLINEAR_TERMINAL_INCREMENT_NORM_PROFILE = (
    "source_solver_dimensionless_coordinate_scaled_free_linf.v1"
)
NONLINEAR_RESULT_AUTHORITY_AXES = MappingProxyType(
    {
        "numerical_state": "authoritative",
        "convergence": "authoritative",
        "displacement": "authoritative",
        "material_state": "authoritative",
        "reaction": "not_evaluated",
        "member_force": "not_evaluated",
        "integration_point_engineering_output": "not_evaluated",
        "engineering_design": "not_authoritative",
        "code_compliance": "not_authoritative",
        "release_readiness": "not_authoritative",
        "commercial_use": "not_authoritative",
    }
)
NONLINEAR_RESULT_CLAIM_BOUNDARY = MappingProxyType(
    {
        "committed_nonlinear_state": True,
        "ordered_material_state_bundle": True,
        "equation_scaling_replay_bound": True,
        "reduced_csr_identity_bound": True,
        "source_free_solution_bytes_bound": True,
        "residual_and_increment_terminal_gate": True,
        "fallback_or_regularization_promoted": False,
        "constitutive_law_verified": False,
        "material_state_history_replayed": False,
        "fiber_frame_kinematic_adapter_authority": False,
        "reaction_authority": False,
        "member_force_authority": False,
        "integration_point_engineering_output_authority": False,
        "design_or_code_authority": False,
        "viewer_projection": False,
        "release_readiness": False,
        "commercial_claim": False,
    }
)
NONLINEAR_RESULT_ADAPTER_CLAIM_BOUNDARY = MappingProxyType(
    {
        **dict(NONLINEAR_RESULT_CLAIM_BOUNDARY),
        "fiber_frame_kinematic_adapter_authority": True,
    }
)

_HASH_ZERO = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_BACKEND_ROLES = {"cpu_reference", "cpu_optimized", "hip"}
_TERMINAL_REASONS = {"converged_residual_and_increment"}
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator,
    type_checker=_STRICT_JSON_TYPE_CHECKER,
)


class NonlinearResultIRError(ValueError):
    """Stable fail-closed nonlinear result error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class NonlinearTerminalReceipt:
    schema_version: str
    terminal_hash: str
    source_solver_schema_version: str
    source_solver_receipt_hash: str
    equation_scaling_hash: str
    reduced_csr_identity_hash: str
    source_solution_data_hash: str
    solver_coordinate_scaling_receipt_hash: str
    state_hash: str
    material_state_bundle_hash: str
    path_history_hash: str
    terminal_reason: str
    residual_norm_profile: str
    increment_norm_profile: str
    converged: bool
    final_residual_linf: float
    residual_tolerance_linf: float
    final_increment_linf: float
    increment_tolerance_linf: float
    accepted_step_count: int
    rejected_attempt_count: int
    rollback_count: int
    fallback_count: int
    regularization_count: int

    @property
    def contract_pass(self) -> bool:
        return bool(
            self.converged
            and self.terminal_reason in _TERMINAL_REASONS
            and self.final_residual_linf <= self.residual_tolerance_linf
            and self.final_increment_linf <= self.increment_tolerance_linf
            and self.accepted_step_count > 0
            and self.fallback_count == 0
            and self.regularization_count == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return _terminal_payload(self, include_terminal_hash=True)


@dataclass(frozen=True)
class NonlinearResultVectorDescriptor:
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
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "layout": self.layout,
            "byte_order": self.byte_order,
            "byte_length": self.byte_length,
            "storage_profile": self.storage_profile,
            "unit_profile": self.unit_profile,
            "data_hash": self.data_hash,
            "content_hash": self.content_hash,
            "artifact_uri": self.artifact_uri,
        }


@dataclass(frozen=True)
class NonlinearNumericalResultSourceSnapshot:
    """Validated source-neutral inputs for one nonlinear numerical result.

    Concrete nonlinear solvers may implement a replaying source adapter and
    return this snapshot without pretending to be ``ExecutionPlan v1`` or
    ``StateIR v1``.  The adapter remains retained by the result and is replayed
    on every in-memory validation.  This does not change the descriptor-only
    v1 result manifest or its canonical hash for existing callers.
    """

    model_ir_content_hash: str
    execution_plan_hash: str
    equation_scaling_hash: str
    reduced_csr_identity_hash: str
    operator_hash: str
    state_hash: str
    state_epoch: int
    material_state_bundle_hash: str
    integration_point_order_hash: str
    path_history_hash: str
    nonlinear_terminal_hash: str
    full_residual_receipt_hash: str
    boundary_condition_receipt_hash: str
    backend_role: Literal["cpu_reference", "cpu_optimized", "hip"]
    backend_receipt_hash: str
    load_factor: float
    time_s: float
    dof_count: int
    displacement_global_si: np.ndarray = field(repr=False, compare=False)


class NonlinearNumericalResultSourceAdapter(Protocol):
    """Replay protocol for a concrete nonlinear result source chain."""

    def validate_nonlinear_result_source(
        self,
    ) -> NonlinearNumericalResultSourceSnapshot: ...


@dataclass(frozen=True)
class NonlinearNumericalResultIR:
    schema_version: str
    result_id: str
    result_hash: str
    result_kind: str
    authority_profile: str
    model_ir_content_hash: str
    execution_plan_hash: str
    equation_scaling_hash: str
    reduced_csr_identity_hash: str
    operator_hash: str
    state_hash: str
    state_epoch: int
    material_state_bundle_hash: str
    integration_point_order_hash: str
    path_history_hash: str
    nonlinear_terminal_hash: str
    full_residual_receipt_hash: str
    boundary_condition_receipt_hash: str
    backend_role: str
    backend_receipt_hash: str
    load_factor: float
    time_s: float
    dof_count: int
    displacement_artifact: NonlinearResultVectorDescriptor
    extensions: Mapping[str, Any]
    _displacement_global_si: np.ndarray = field(repr=False, compare=False)
    _execution_plan: ExecutionPlan | None = field(repr=False, compare=False)
    _equation_scaling: EquationScaling | None = field(repr=False, compare=False)
    _reduced_csr: ExecutionPlanReducedCSR | None = field(repr=False, compare=False)
    _committed_state: StateIR | None = field(repr=False, compare=False)
    _material_state_bundle: MaterialStateBundle | None = field(
        repr=False,
        compare=False,
    )
    _terminal_receipt: NonlinearTerminalReceipt | None = field(
        repr=False,
        compare=False,
    )
    _source_adapter: NonlinearNumericalResultSourceAdapter | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    @property
    def displacement_global_si(self) -> np.ndarray:
        return self._displacement_global_si

    def to_manifest(self) -> dict[str, Any]:
        validate_nonlinear_numerical_result_ir(self)
        return _result_payload(self, include_result_hash=True)


def create_nonlinear_terminal_receipt(
    *,
    source_solver_schema_version: str,
    source_solver_receipt_hash: str,
    equation_scaling_hash: str,
    reduced_csr_identity_hash: str,
    source_solution_data_hash: str,
    solver_coordinate_scaling_receipt_hash: str,
    state_hash: str,
    material_state_bundle_hash: str,
    path_history_hash: str,
    terminal_reason: str,
    converged: bool,
    final_residual_linf: float,
    residual_tolerance_linf: float,
    final_increment_linf: float,
    increment_tolerance_linf: float,
    accepted_step_count: int,
    rejected_attempt_count: int = 0,
    rollback_count: int = 0,
    fallback_count: int = 0,
    regularization_count: int = 0,
) -> NonlinearTerminalReceipt:
    provisional = NonlinearTerminalReceipt(
        schema_version=NONLINEAR_TERMINAL_RECEIPT_SCHEMA_VERSION,
        terminal_hash=_HASH_ZERO,
        source_solver_schema_version=_stable_id(
            source_solver_schema_version,
            "/source_solver_schema_version",
        ),
        source_solver_receipt_hash=_hash(
            source_solver_receipt_hash,
            "/source_solver_receipt_hash",
        ),
        equation_scaling_hash=_hash(
            equation_scaling_hash,
            "/equation_scaling_hash",
        ),
        reduced_csr_identity_hash=_hash(
            reduced_csr_identity_hash,
            "/reduced_csr_identity_hash",
        ),
        source_solution_data_hash=_hash(
            source_solution_data_hash,
            "/source_solution_data_hash",
        ),
        solver_coordinate_scaling_receipt_hash=_hash(
            solver_coordinate_scaling_receipt_hash,
            "/solver_coordinate_scaling_receipt_hash",
        ),
        state_hash=_hash(state_hash, "/state_hash"),
        material_state_bundle_hash=_hash(
            material_state_bundle_hash,
            "/material_state_bundle_hash",
        ),
        path_history_hash=_hash(path_history_hash, "/path_history_hash"),
        terminal_reason=_choice(
            terminal_reason,
            _TERMINAL_REASONS,
            "/terminal_reason",
        ),
        residual_norm_profile=NONLINEAR_TERMINAL_RESIDUAL_NORM_PROFILE,
        increment_norm_profile=NONLINEAR_TERMINAL_INCREMENT_NORM_PROFILE,
        converged=_boolean(converged, "/converged"),
        final_residual_linf=_nonnegative(
            final_residual_linf,
            "/final_residual_linf",
        ),
        residual_tolerance_linf=_positive(
            residual_tolerance_linf,
            "/residual_tolerance_linf",
        ),
        final_increment_linf=_nonnegative(
            final_increment_linf,
            "/final_increment_linf",
        ),
        increment_tolerance_linf=_positive(
            increment_tolerance_linf,
            "/increment_tolerance_linf",
        ),
        accepted_step_count=_index(accepted_step_count, "/accepted_step_count"),
        rejected_attempt_count=_index(
            rejected_attempt_count,
            "/rejected_attempt_count",
        ),
        rollback_count=_index(rollback_count, "/rollback_count"),
        fallback_count=_index(fallback_count, "/fallback_count"),
        regularization_count=_index(
            regularization_count,
            "/regularization_count",
        ),
    )
    receipt = replace(
        provisional,
        terminal_hash=canonical_hash(
            _terminal_payload(provisional, include_terminal_hash=False)
        ),
    )
    return validate_nonlinear_terminal_receipt(receipt)


def validate_nonlinear_terminal_receipt(
    receipt: NonlinearTerminalReceipt,
) -> NonlinearTerminalReceipt:
    if type(receipt) is not NonlinearTerminalReceipt:
        _fail(
            "nonlinear_terminal_type_invalid",
            "/",
            "Expected NonlinearTerminalReceipt.",
        )
    if receipt.schema_version != NONLINEAR_TERMINAL_RECEIPT_SCHEMA_VERSION:
        _fail(
            "nonlinear_terminal_schema_invalid",
            "/schema_version",
            "Unsupported nonlinear terminal receipt schema.",
        )
    _stable_id(receipt.source_solver_schema_version, "/source_solver_schema_version")
    for path, value in (
        ("/terminal_hash", receipt.terminal_hash),
        ("/source_solver_receipt_hash", receipt.source_solver_receipt_hash),
        ("/equation_scaling_hash", receipt.equation_scaling_hash),
        ("/reduced_csr_identity_hash", receipt.reduced_csr_identity_hash),
        ("/source_solution_data_hash", receipt.source_solution_data_hash),
        (
            "/solver_coordinate_scaling_receipt_hash",
            receipt.solver_coordinate_scaling_receipt_hash,
        ),
        ("/state_hash", receipt.state_hash),
        ("/material_state_bundle_hash", receipt.material_state_bundle_hash),
        ("/path_history_hash", receipt.path_history_hash),
    ):
        _hash(value, path)
    _choice(receipt.terminal_reason, _TERMINAL_REASONS, "/terminal_reason")
    if receipt.residual_norm_profile != NONLINEAR_TERMINAL_RESIDUAL_NORM_PROFILE:
        _fail(
            "nonlinear_terminal_residual_norm_profile_invalid",
            "/residual_norm_profile",
            "Residual norm must use the bound dimensionless equation scaling.",
        )
    if receipt.increment_norm_profile != NONLINEAR_TERMINAL_INCREMENT_NORM_PROFILE:
        _fail(
            "nonlinear_terminal_increment_norm_profile_invalid",
            "/increment_norm_profile",
            "Increment norm must use a bound source-solver coordinate scaling.",
        )
    _boolean(receipt.converged, "/converged")
    _nonnegative(receipt.final_residual_linf, "/final_residual_linf")
    _positive(receipt.residual_tolerance_linf, "/residual_tolerance_linf")
    _nonnegative(receipt.final_increment_linf, "/final_increment_linf")
    _positive(receipt.increment_tolerance_linf, "/increment_tolerance_linf")
    for path, value in (
        ("/accepted_step_count", receipt.accepted_step_count),
        ("/rejected_attempt_count", receipt.rejected_attempt_count),
        ("/rollback_count", receipt.rollback_count),
        ("/fallback_count", receipt.fallback_count),
        ("/regularization_count", receipt.regularization_count),
    ):
        _index(value, path)
    if receipt.rollback_count > receipt.rejected_attempt_count:
        _fail(
            "nonlinear_terminal_history_count_invalid",
            "/rollback_count",
            "Rollback count cannot exceed rejected-attempt count.",
        )
    if not receipt.contract_pass:
        _fail(
            "nonlinear_terminal_gate_failed",
            "/",
            "Residual, increment, convergence, step, fallback, or regularization gate failed.",
        )
    expected_hash = canonical_hash(
        _terminal_payload(receipt, include_terminal_hash=False)
    )
    if receipt.terminal_hash != expected_hash:
        _fail(
            "nonlinear_terminal_hash_mismatch",
            "/terminal_hash",
            "Terminal hash does not match canonical content.",
        )
    return receipt


def _validate_source_chain(
    plan: ExecutionPlan,
    scaling: EquationScaling,
    reduced: ExecutionPlanReducedCSR,
    state: StateIR,
    bundle: MaterialStateBundle,
    terminal: NonlinearTerminalReceipt,
) -> None:
    """Validate the exact nonlinear state/material/terminal ancestry."""

    if state.role != "committed" or state.epoch < 1:
        _fail(
            "nonlinear_result_state_not_committed",
            "/bindings/state_hash",
            "A positive-epoch committed StateIR is required.",
        )
    if reduced.terminal_disposition != "solve_free_equations" or reduced.free_count < 1:
        _fail(
            "nonlinear_result_free_equation_solution_required",
            "/bindings/reduced_csr_identity_hash",
            "Nonlinear numerical authority requires a solved free-equation space.",
        )
    if bundle.role != "committed" or bundle.epoch != state.epoch:
        _fail(
            "nonlinear_result_material_bundle_not_committed",
            "/bindings/material_state_bundle_hash",
            "Material-state bundle must be committed at the same epoch.",
        )
    if (
        bundle.model_ir_content_hash != plan.model_ir_content_hash
        or bundle.execution_plan_hash != plan.plan_hash
        or bundle.solver_state_hash != state.state_hash
    ):
        _fail(
            "nonlinear_result_material_bundle_binding_mismatch",
            "/bindings/material_state_bundle_hash",
            "Material-state bundle does not match the exact model, plan, and StateIR.",
        )
    if (
        terminal.state_hash != state.state_hash
        or terminal.material_state_bundle_hash != bundle.bundle_hash
        or terminal.equation_scaling_hash != scaling.scaling_hash
        or terminal.reduced_csr_identity_hash != reduced.identity_hash
    ):
        _fail(
            "nonlinear_result_terminal_binding_mismatch",
            "/bindings/nonlinear_terminal_hash",
            "Terminal receipt does not bind the exact scaled plan, reduced CSR, state, and material bundle.",
        )
    if terminal.accepted_step_count != state.epoch:
        _fail(
            "nonlinear_result_accepted_step_epoch_mismatch",
            "/bindings/nonlinear_terminal_hash",
            "Terminal accepted-step count must match the committed StateIR/material epoch.",
        )
    free_solution = immutable_array(
        state.displacement_si[plan.array("free_dofs")],
        dtype="<f8",
    )
    if terminal.source_solution_data_hash != array_data_hash(free_solution):
        _fail(
            "nonlinear_result_source_solution_state_mismatch",
            "/bindings/nonlinear_terminal_hash",
            "Terminal source-solution bytes do not match the committed StateIR free DOFs.",
        )


def create_nonlinear_numerical_result_ir(
    *,
    result_id: str,
    execution_plan: ExecutionPlan,
    equation_scaling: EquationScaling,
    reduced_csr: ExecutionPlanReducedCSR,
    committed_state: StateIR,
    material_state_bundle: MaterialStateBundle,
    terminal_receipt: NonlinearTerminalReceipt,
    full_residual_receipt_hash: str,
    boundary_condition_receipt_hash: str,
    backend_role: Literal["cpu_reference", "cpu_optimized", "hip"],
    backend_receipt_hash: str,
) -> NonlinearNumericalResultIR:
    plan = validate_execution_plan(execution_plan)
    scaling = equation_scaling
    validate_equation_scaling_binding(plan, scaling=scaling)
    reduced = validate_execution_plan_reduced_csr(
        reduced_csr,
        execution_plan=plan,
    )
    state = validate_state_ir(committed_state, expected_plan=plan)
    bundle = validate_material_state_bundle(material_state_bundle)
    terminal = validate_nonlinear_terminal_receipt(terminal_receipt)
    _validate_source_chain(plan, scaling, reduced, state, bundle, terminal)

    normalized_id = _stable_id(result_id, "/result_id")
    displacement = immutable_array(state.displacement_si, dtype="<f8")
    descriptor = _displacement_descriptor(
        normalized_id,
        displacement,
        state_hash=state.state_hash,
        material_bundle_hash=bundle.bundle_hash,
    )
    provisional = NonlinearNumericalResultIR(
        schema_version=NONLINEAR_NUMERICAL_RESULT_IR_SCHEMA_VERSION,
        result_id=normalized_id,
        result_hash=_HASH_ZERO,
        result_kind=NONLINEAR_NUMERICAL_RESULT_KIND,
        authority_profile=NONLINEAR_NUMERICAL_RESULT_AUTHORITY_PROFILE,
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        equation_scaling_hash=scaling.scaling_hash,
        reduced_csr_identity_hash=reduced.identity_hash,
        operator_hash=plan.operator_hash,
        state_hash=state.state_hash,
        state_epoch=state.epoch,
        material_state_bundle_hash=bundle.bundle_hash,
        integration_point_order_hash=bundle.integration_point_order_hash,
        path_history_hash=terminal.path_history_hash,
        nonlinear_terminal_hash=terminal.terminal_hash,
        full_residual_receipt_hash=_hash(
            full_residual_receipt_hash,
            "/bindings/full_residual_receipt_hash",
        ),
        boundary_condition_receipt_hash=_hash(
            boundary_condition_receipt_hash,
            "/bindings/boundary_condition_receipt_hash",
        ),
        backend_role=_choice(backend_role, _BACKEND_ROLES, "/backend/role"),
        backend_receipt_hash=_hash(
            backend_receipt_hash,
            "/backend/receipt_hash",
        ),
        load_factor=state.load_factor,
        time_s=state.time_s,
        dof_count=state.dof_count,
        displacement_artifact=descriptor,
        extensions=MappingProxyType({}),
        _displacement_global_si=displacement,
        _execution_plan=plan,
        _equation_scaling=scaling,
        _reduced_csr=reduced,
        _committed_state=state,
        _material_state_bundle=bundle,
        _terminal_receipt=terminal,
    )
    result = replace(
        provisional,
        result_hash=canonical_hash(
            _result_payload(provisional, include_result_hash=False)
        ),
    )
    return validate_nonlinear_numerical_result_ir(result)


def create_adapter_bound_nonlinear_numerical_result_ir(
    *,
    result_id: str,
    source_adapter: NonlinearNumericalResultSourceAdapter,
) -> NonlinearNumericalResultIR:
    """Create a v1 result from one retained, fully replaying source adapter.

    The concrete adapter owns source-specific replay.  This factory only
    accepts the resulting normalized snapshot, binds its exact displacement
    bytes, and retains the adapter so every later in-memory validation replays
    the source chain again.
    """

    snapshot = _adapter_source_snapshot(source_adapter)
    normalized_id = _stable_id(result_id, "/result_id")
    displacement = snapshot.displacement_global_si
    descriptor = _displacement_descriptor(
        normalized_id,
        displacement,
        state_hash=snapshot.state_hash,
        material_bundle_hash=snapshot.material_state_bundle_hash,
    )
    provisional = NonlinearNumericalResultIR(
        schema_version=NONLINEAR_NUMERICAL_RESULT_IR_SCHEMA_VERSION,
        result_id=normalized_id,
        result_hash=_HASH_ZERO,
        result_kind=NONLINEAR_NUMERICAL_RESULT_KIND,
        authority_profile=NONLINEAR_NUMERICAL_RESULT_AUTHORITY_PROFILE,
        model_ir_content_hash=snapshot.model_ir_content_hash,
        execution_plan_hash=snapshot.execution_plan_hash,
        equation_scaling_hash=snapshot.equation_scaling_hash,
        reduced_csr_identity_hash=snapshot.reduced_csr_identity_hash,
        operator_hash=snapshot.operator_hash,
        state_hash=snapshot.state_hash,
        state_epoch=snapshot.state_epoch,
        material_state_bundle_hash=snapshot.material_state_bundle_hash,
        integration_point_order_hash=snapshot.integration_point_order_hash,
        path_history_hash=snapshot.path_history_hash,
        nonlinear_terminal_hash=snapshot.nonlinear_terminal_hash,
        full_residual_receipt_hash=snapshot.full_residual_receipt_hash,
        boundary_condition_receipt_hash=snapshot.boundary_condition_receipt_hash,
        backend_role=snapshot.backend_role,
        backend_receipt_hash=snapshot.backend_receipt_hash,
        load_factor=snapshot.load_factor,
        time_s=snapshot.time_s,
        dof_count=snapshot.dof_count,
        displacement_artifact=descriptor,
        extensions=MappingProxyType({}),
        _displacement_global_si=displacement,
        _execution_plan=None,
        _equation_scaling=None,
        _reduced_csr=None,
        _committed_state=None,
        _material_state_bundle=None,
        _terminal_receipt=None,
        _source_adapter=source_adapter,
    )
    result = replace(
        provisional,
        result_hash=canonical_hash(
            _result_payload(provisional, include_result_hash=False)
        ),
    )
    return validate_nonlinear_numerical_result_ir(result)


def validate_nonlinear_numerical_result_ir(
    result: NonlinearNumericalResultIR,
) -> NonlinearNumericalResultIR:
    if type(result) is not NonlinearNumericalResultIR:
        _fail(
            "nonlinear_result_type_invalid",
            "/",
            "Expected NonlinearNumericalResultIR.",
        )
    if result.schema_version != NONLINEAR_NUMERICAL_RESULT_IR_SCHEMA_VERSION:
        _fail(
            "nonlinear_result_schema_invalid",
            "/schema_version",
            "Unsupported nonlinear numerical result schema.",
        )
    if (
        result.result_kind != NONLINEAR_NUMERICAL_RESULT_KIND
        or result.authority_profile != NONLINEAR_NUMERICAL_RESULT_AUTHORITY_PROFILE
    ):
        _fail(
            "nonlinear_result_authority_profile_invalid",
            "/authority_profile",
            "Nonlinear result kind or authority profile changed.",
        )
    _stable_id(result.result_id, "/result_id")
    snapshot = _result_source_snapshot(result)

    expected = {
        "model_ir_content_hash": snapshot.model_ir_content_hash,
        "execution_plan_hash": snapshot.execution_plan_hash,
        "equation_scaling_hash": snapshot.equation_scaling_hash,
        "reduced_csr_identity_hash": snapshot.reduced_csr_identity_hash,
        "operator_hash": snapshot.operator_hash,
        "state_hash": snapshot.state_hash,
        "state_epoch": snapshot.state_epoch,
        "material_state_bundle_hash": snapshot.material_state_bundle_hash,
        "integration_point_order_hash": snapshot.integration_point_order_hash,
        "path_history_hash": snapshot.path_history_hash,
        "nonlinear_terminal_hash": snapshot.nonlinear_terminal_hash,
        "full_residual_receipt_hash": snapshot.full_residual_receipt_hash,
        "boundary_condition_receipt_hash": (snapshot.boundary_condition_receipt_hash),
        "backend_role": snapshot.backend_role,
        "backend_receipt_hash": snapshot.backend_receipt_hash,
        "load_factor": snapshot.load_factor,
        "time_s": snapshot.time_s,
        "dof_count": snapshot.dof_count,
    }
    if any(getattr(result, key) != value for key, value in expected.items()):
        _fail(
            "nonlinear_result_binding_mismatch",
            "/bindings",
            "Result does not match retained plan, state, material bundle, or terminal receipt.",
        )
    for path, value in (
        ("/result_hash", result.result_hash),
        ("/bindings/full_residual_receipt_hash", result.full_residual_receipt_hash),
        (
            "/bindings/boundary_condition_receipt_hash",
            result.boundary_condition_receipt_hash,
        ),
        ("/backend/receipt_hash", result.backend_receipt_hash),
    ):
        _hash(value, path)
    _choice(result.backend_role, _BACKEND_ROLES, "/backend/role")
    _index(result.state_epoch, "/bindings/state_epoch")
    _index(result.dof_count, "/dof_count")
    _finite(result.load_factor, "/load_factor")
    if _finite(result.time_s, "/time_s") < 0.0:
        _fail(
            "nonlinear_result_time_negative",
            "/time_s",
            "Result time must be non-negative.",
        )
    if not isinstance(result.extensions, MappingProxyType) or result.extensions:
        _fail(
            "nonlinear_result_extensions_invalid",
            "/extensions",
            "NonlinearNumericalResultIR v1 requires empty immutable extensions.",
        )

    displacement = snapshot.displacement_global_si
    if not has_immutable_bytes_backing(result._displacement_global_si):
        _fail(
            "nonlinear_result_displacement_mutable",
            "/displacement_artifact",
            "Retained displacement must have immutable bytes backing.",
        )
    if not np.array_equal(result._displacement_global_si, displacement):
        _fail(
            "nonlinear_result_displacement_state_mismatch",
            "/displacement_artifact",
            "Retained displacement does not equal the replayed committed state.",
        )
    expected_descriptor = _displacement_descriptor(
        result.result_id,
        displacement,
        state_hash=snapshot.state_hash,
        material_bundle_hash=snapshot.material_state_bundle_hash,
    )
    if result.displacement_artifact != expected_descriptor:
        _fail(
            "nonlinear_result_displacement_descriptor_mismatch",
            "/displacement_artifact",
            "Displacement descriptor does not match the committed bytes.",
        )
    expected_hash = canonical_hash(_result_payload(result, include_result_hash=False))
    if result.result_hash != expected_hash:
        _fail(
            "nonlinear_result_hash_mismatch",
            "/result_hash",
            "Result hash does not match canonical content.",
        )
    return result


def _result_source_snapshot(
    result: NonlinearNumericalResultIR,
) -> NonlinearNumericalResultSourceSnapshot:
    legacy_sources = (
        result._execution_plan,
        result._equation_scaling,
        result._reduced_csr,
        result._committed_state,
        result._material_state_bundle,
        result._terminal_receipt,
    )
    if result._source_adapter is not None:
        if any(value is not None for value in legacy_sources):
            _fail(
                "nonlinear_result_source_mode_invalid",
                "/",
                "Adapter-bound results cannot retain legacy source contracts.",
            )
        return _adapter_source_snapshot(result._source_adapter)
    if any(value is None for value in legacy_sources):
        _fail(
            "nonlinear_result_source_mode_invalid",
            "/",
            "Legacy results require the complete plan/state/terminal source chain.",
        )

    plan = validate_execution_plan(result._execution_plan)
    validate_equation_scaling_binding(plan, scaling=result._equation_scaling)
    reduced = validate_execution_plan_reduced_csr(
        result._reduced_csr,
        execution_plan=plan,
    )
    state = validate_state_ir(result._committed_state, expected_plan=plan)
    bundle = validate_material_state_bundle(result._material_state_bundle)
    terminal = validate_nonlinear_terminal_receipt(result._terminal_receipt)
    _validate_source_chain(
        plan,
        result._equation_scaling,
        reduced,
        state,
        bundle,
        terminal,
    )
    return _validate_source_snapshot(
        NonlinearNumericalResultSourceSnapshot(
            model_ir_content_hash=plan.model_ir_content_hash,
            execution_plan_hash=plan.plan_hash,
            equation_scaling_hash=execution_plan_scaling_hash(plan),
            reduced_csr_identity_hash=reduced.identity_hash,
            operator_hash=plan.operator_hash,
            state_hash=state.state_hash,
            state_epoch=state.epoch,
            material_state_bundle_hash=bundle.bundle_hash,
            integration_point_order_hash=bundle.integration_point_order_hash,
            path_history_hash=terminal.path_history_hash,
            nonlinear_terminal_hash=terminal.terminal_hash,
            full_residual_receipt_hash=result.full_residual_receipt_hash,
            boundary_condition_receipt_hash=result.boundary_condition_receipt_hash,
            backend_role=result.backend_role,
            backend_receipt_hash=result.backend_receipt_hash,
            load_factor=state.load_factor,
            time_s=state.time_s,
            dof_count=state.dof_count,
            displacement_global_si=state.displacement_si,
        )
    )


def _adapter_source_snapshot(
    source_adapter: NonlinearNumericalResultSourceAdapter,
) -> NonlinearNumericalResultSourceSnapshot:
    validator = getattr(source_adapter, "validate_nonlinear_result_source", None)
    if not callable(validator):
        _fail(
            "nonlinear_result_source_adapter_invalid",
            "/",
            "Source adapter must expose deterministic replay validation.",
        )
    return _validate_source_snapshot(validator())


def _validate_source_snapshot(
    snapshot: NonlinearNumericalResultSourceSnapshot,
) -> NonlinearNumericalResultSourceSnapshot:
    if type(snapshot) is not NonlinearNumericalResultSourceSnapshot:
        _fail(
            "nonlinear_result_source_snapshot_invalid",
            "/",
            "Source adapter must return NonlinearNumericalResultSourceSnapshot.",
        )
    for path, value in (
        ("/bindings/model_ir_content_hash", snapshot.model_ir_content_hash),
        ("/bindings/execution_plan_hash", snapshot.execution_plan_hash),
        ("/bindings/equation_scaling_hash", snapshot.equation_scaling_hash),
        (
            "/bindings/reduced_csr_identity_hash",
            snapshot.reduced_csr_identity_hash,
        ),
        ("/bindings/operator_hash", snapshot.operator_hash),
        ("/bindings/state_hash", snapshot.state_hash),
        (
            "/bindings/material_state_bundle_hash",
            snapshot.material_state_bundle_hash,
        ),
        (
            "/bindings/integration_point_order_hash",
            snapshot.integration_point_order_hash,
        ),
        ("/bindings/path_history_hash", snapshot.path_history_hash),
        ("/bindings/nonlinear_terminal_hash", snapshot.nonlinear_terminal_hash),
        (
            "/bindings/full_residual_receipt_hash",
            snapshot.full_residual_receipt_hash,
        ),
        (
            "/bindings/boundary_condition_receipt_hash",
            snapshot.boundary_condition_receipt_hash,
        ),
        ("/backend/receipt_hash", snapshot.backend_receipt_hash),
    ):
        _hash(value, path)
    if _index(snapshot.state_epoch, "/bindings/state_epoch") < 1:
        _fail(
            "nonlinear_result_source_state_epoch_invalid",
            "/bindings/state_epoch",
            "Adapter-bound state epoch must be positive.",
        )
    count = _index(snapshot.dof_count, "/dof_count")
    if count < 6 or count % 6 != 0:
        _fail(
            "nonlinear_result_source_dof_count_invalid",
            "/dof_count",
            "Adapter displacement must use canonical six-DOF node order.",
        )
    _choice(snapshot.backend_role, _BACKEND_ROLES, "/backend/role")
    _finite(snapshot.load_factor, "/load_factor")
    if _finite(snapshot.time_s, "/time_s") < 0.0:
        _fail(
            "nonlinear_result_time_negative",
            "/time_s",
            "Result time must be non-negative.",
        )
    displacement = snapshot.displacement_global_si
    if (
        type(displacement) is not np.ndarray
        or displacement.dtype != np.dtype("<f8")
        or displacement.shape != (count,)
        or not displacement.flags.c_contiguous
        or not np.all(np.isfinite(displacement))
    ):
        _fail(
            "nonlinear_result_source_displacement_invalid",
            "/displacement_artifact",
            "Source displacement must be finite contiguous canonical <f8 bytes.",
        )
    if not has_immutable_bytes_backing(displacement):
        _fail(
            "nonlinear_result_source_displacement_mutable",
            "/displacement_artifact",
            "Source displacement must have immutable bytes backing.",
        )
    return snapshot


def validate_nonlinear_result_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        _fail(
            "nonlinear_result_manifest_type_invalid",
            "/",
            "Nonlinear result manifest must be an object.",
        )
    try:
        normalized = json.loads(json.dumps(dict(payload), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise NonlinearResultIRError(
            "nonlinear_result_manifest_json_invalid",
            "/",
            "Nonlinear result manifest must be finite strict JSON.",
        ) from exc
    errors = sorted(
        _manifest_validator().iter_errors(normalized),
        key=lambda row: tuple(str(value) for value in row.absolute_path),
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(value) for value in first.absolute_path)
        _fail(
            "nonlinear_result_manifest_schema_invalid",
            path or "/",
            first.message,
        )
    claim_boundary = normalized["claim_boundary"]
    if claim_boundary not in (
        dict(NONLINEAR_RESULT_CLAIM_BOUNDARY),
        dict(NONLINEAR_RESULT_ADAPTER_CLAIM_BOUNDARY),
    ):
        _fail(
            "nonlinear_result_claim_boundary_invalid",
            "/claim_boundary",
            "Result claim boundary is not a recognized exact authority profile.",
        )
    descriptor = normalized["displacement_artifact"]
    dof_count = int(normalized["dof_count"])
    if descriptor["shape"] != [dof_count] or descriptor["byte_length"] != 8 * dof_count:
        _fail(
            "nonlinear_result_displacement_shape_mismatch",
            "/displacement_artifact",
            "Displacement shape and byte length must match the global DOF count.",
        )
    expected_uri = _displacement_artifact_uri(
        str(normalized["result_id"]),
        state_hash=str(normalized["bindings"]["state_hash"]),
        material_bundle_hash=str(normalized["bindings"]["material_state_bundle_hash"]),
    )
    if descriptor["artifact_uri"] != expected_uri:
        _fail(
            "nonlinear_result_displacement_uri_invalid",
            "/displacement_artifact/artifact_uri",
            "Displacement artifact URI is not canonical for the bound result state.",
        )
    expected_content_hash = canonical_hash(
        {key: value for key, value in descriptor.items() if key != "content_hash"}
    )
    if descriptor["content_hash"] != expected_content_hash:
        _fail(
            "nonlinear_result_displacement_content_hash_mismatch",
            "/displacement_artifact/content_hash",
            "Displacement descriptor content hash does not match metadata.",
        )
    expected_result_hash = canonical_hash(
        {key: value for key, value in normalized.items() if key != "result_hash"}
    )
    if normalized["result_hash"] != expected_result_hash:
        _fail(
            "nonlinear_result_hash_mismatch",
            "/result_hash",
            "Result hash does not match canonical content.",
        )
    return normalized


def validate_nonlinear_displacement_bytes(
    result: NonlinearNumericalResultIR,
    payload: bytes,
) -> np.ndarray:
    validate_nonlinear_numerical_result_ir(result)
    if type(payload) is not bytes:
        _fail(
            "nonlinear_result_artifact_bytes_invalid",
            "/displacement_artifact",
            "Displacement artifact must be immutable bytes.",
        )
    descriptor = result.displacement_artifact
    if len(payload) != descriptor.byte_length:
        _fail(
            "nonlinear_result_artifact_length_mismatch",
            "/displacement_artifact/byte_length",
            "Displacement artifact byte length does not match descriptor.",
        )
    array = immutable_array(np.frombuffer(payload, dtype="<f8"), dtype="<f8")
    if array.shape != descriptor.shape:
        _fail(
            "nonlinear_result_artifact_shape_mismatch",
            "/displacement_artifact/shape",
            "Displacement artifact bytes do not match the descriptor shape.",
        )
    if array_data_hash(array) != descriptor.data_hash:
        _fail(
            "nonlinear_result_artifact_hash_mismatch",
            "/displacement_artifact/data_hash",
            "Displacement artifact bytes do not match descriptor.",
        )
    return array


def _displacement_descriptor(
    result_id: str,
    displacement: np.ndarray,
    *,
    state_hash: str,
    material_bundle_hash: str,
) -> NonlinearResultVectorDescriptor:
    provisional = NonlinearResultVectorDescriptor(
        name="displacement_global_si",
        dtype="<f8",
        shape=tuple(int(value) for value in displacement.shape),
        layout="C",
        byte_order="little",
        byte_length=int(displacement.nbytes),
        storage_profile=NONLINEAR_RESULT_STORAGE_PROFILE,
        unit_profile=NONLINEAR_RESULT_DISPLACEMENT_UNIT_PROFILE,
        data_hash=array_data_hash(displacement),
        content_hash=_HASH_ZERO,
        artifact_uri=_displacement_artifact_uri(
            result_id,
            state_hash=state_hash,
            material_bundle_hash=material_bundle_hash,
        ),
    )
    return replace(
        provisional,
        content_hash=canonical_hash(
            {
                key: value
                for key, value in provisional.to_dict().items()
                if key != "content_hash"
            }
        ),
    )


def _displacement_artifact_uri(
    result_id: str,
    *,
    state_hash: str,
    material_bundle_hash: str,
) -> str:
    return (
        f"artifact://nonlinear-result/{result_id}/"
        f"{state_hash.split(':')[-1][:16]}/"
        f"{material_bundle_hash.split(':')[-1][:16]}/displacement_global.f64le"
    )


def _terminal_payload(
    receipt: NonlinearTerminalReceipt,
    *,
    include_terminal_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": receipt.schema_version,
        "terminal_hash": receipt.terminal_hash,
        "source_solver_schema_version": receipt.source_solver_schema_version,
        "source_solver_receipt_hash": receipt.source_solver_receipt_hash,
        "equation_scaling_hash": receipt.equation_scaling_hash,
        "reduced_csr_identity_hash": receipt.reduced_csr_identity_hash,
        "source_solution_data_hash": receipt.source_solution_data_hash,
        "solver_coordinate_scaling_receipt_hash": (
            receipt.solver_coordinate_scaling_receipt_hash
        ),
        "state_hash": receipt.state_hash,
        "material_state_bundle_hash": receipt.material_state_bundle_hash,
        "path_history_hash": receipt.path_history_hash,
        "terminal_reason": receipt.terminal_reason,
        "residual_norm_profile": receipt.residual_norm_profile,
        "increment_norm_profile": receipt.increment_norm_profile,
        "converged": receipt.converged,
        "final_residual_linf": receipt.final_residual_linf,
        "residual_tolerance_linf": receipt.residual_tolerance_linf,
        "final_increment_linf": receipt.final_increment_linf,
        "increment_tolerance_linf": receipt.increment_tolerance_linf,
        "accepted_step_count": receipt.accepted_step_count,
        "rejected_attempt_count": receipt.rejected_attempt_count,
        "rollback_count": receipt.rollback_count,
        "fallback_count": receipt.fallback_count,
        "regularization_count": receipt.regularization_count,
        "contract_pass": receipt.contract_pass,
    }
    if not include_terminal_hash:
        payload.pop("terminal_hash")
    return payload


def _result_payload(
    result: NonlinearNumericalResultIR,
    *,
    include_result_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": result.schema_version,
        "result_id": result.result_id,
        "result_hash": result.result_hash,
        "result_kind": result.result_kind,
        "authority_profile": result.authority_profile,
        "authority": dict(NONLINEAR_RESULT_AUTHORITY_AXES),
        "bindings": {
            "model_ir_content_hash": result.model_ir_content_hash,
            "execution_plan_hash": result.execution_plan_hash,
            "equation_scaling_hash": result.equation_scaling_hash,
            "reduced_csr_identity_hash": result.reduced_csr_identity_hash,
            "operator_hash": result.operator_hash,
            "state_hash": result.state_hash,
            "state_epoch": result.state_epoch,
            "material_state_bundle_hash": result.material_state_bundle_hash,
            "integration_point_order_hash": result.integration_point_order_hash,
            "path_history_hash": result.path_history_hash,
            "nonlinear_terminal_hash": result.nonlinear_terminal_hash,
            "full_residual_receipt_hash": result.full_residual_receipt_hash,
            "boundary_condition_receipt_hash": result.boundary_condition_receipt_hash,
        },
        "backend": {
            "role": result.backend_role,
            "receipt_hash": result.backend_receipt_hash,
        },
        "load_factor": result.load_factor,
        "time_s": result.time_s,
        "dof_count": result.dof_count,
        "displacement_artifact": result.displacement_artifact.to_dict(),
        "claim_boundary": dict(
            NONLINEAR_RESULT_ADAPTER_CLAIM_BOUNDARY
            if result._source_adapter is not None
            else NONLINEAR_RESULT_CLAIM_BOUNDARY
        ),
        "extensions": dict(result.extensions),
    }
    if not include_result_hash:
        payload.pop("result_hash")
    return payload


def _hash(value: Any, path: str) -> str:
    normalized = str(value).strip()
    if not _HASH_PATTERN.fullmatch(normalized):
        _fail("nonlinear_result_hash_invalid", path, "Expected sha256:<hex>.")
    return normalized


def _stable_id(value: Any, path: str) -> str:
    normalized = str(value).strip()
    if not _STABLE_ID_PATTERN.fullmatch(normalized):
        _fail("nonlinear_result_id_invalid", path, "Expected a stable identifier.")
    return normalized


def _index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > 2**31 - 1:
        _fail(
            "nonlinear_result_index_invalid",
            path,
            "Expected a non-negative 32-bit integer.",
        )
    return value


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        _fail("nonlinear_result_number_invalid", path, "Expected a finite number.")
    normalized = float(value)
    if not math.isfinite(normalized):
        _fail("nonlinear_result_number_invalid", path, "Expected a finite number.")
    return normalized


def _nonnegative(value: Any, path: str) -> float:
    normalized = _finite(value, path)
    if normalized < 0.0:
        _fail("nonlinear_result_number_negative", path, "Expected non-negative.")
    return normalized


def _positive(value: Any, path: str) -> float:
    normalized = _finite(value, path)
    if normalized <= 0.0:
        _fail("nonlinear_result_number_not_positive", path, "Expected positive.")
    return normalized


def _boolean(value: Any, path: str) -> bool:
    if type(value) is not bool:
        _fail("nonlinear_result_boolean_invalid", path, "Expected exact boolean.")
    return value


def _choice(value: Any, allowed: set[str], path: str) -> str:
    normalized = str(value)
    if normalized not in allowed:
        _fail("nonlinear_result_enum_invalid", path, f"Unsupported value: {normalized}")
    return normalized


@lru_cache(maxsize=1)
def _manifest_validator() -> Draft202012Validator:
    schema_path = resources.files("structural_analysis.schemas").joinpath(
        "nonlinear_numerical_result_ir_v1.schema.json"
    )
    return _StrictDraft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8"))
    )


def _fail(code: str, path: str, message: str) -> None:
    raise NonlinearResultIRError(code, path, message)


__all__ = [
    "NONLINEAR_NUMERICAL_RESULT_AUTHORITY_PROFILE",
    "NONLINEAR_NUMERICAL_RESULT_IR_SCHEMA_VERSION",
    "NONLINEAR_RESULT_ADAPTER_CLAIM_BOUNDARY",
    "NONLINEAR_RESULT_AUTHORITY_AXES",
    "NONLINEAR_RESULT_CLAIM_BOUNDARY",
    "NONLINEAR_TERMINAL_INCREMENT_NORM_PROFILE",
    "NONLINEAR_TERMINAL_RECEIPT_SCHEMA_VERSION",
    "NONLINEAR_TERMINAL_RESIDUAL_NORM_PROFILE",
    "NonlinearNumericalResultIR",
    "NonlinearNumericalResultSourceAdapter",
    "NonlinearNumericalResultSourceSnapshot",
    "NonlinearResultIRError",
    "NonlinearResultVectorDescriptor",
    "NonlinearTerminalReceipt",
    "create_adapter_bound_nonlinear_numerical_result_ir",
    "create_nonlinear_numerical_result_ir",
    "create_nonlinear_terminal_receipt",
    "validate_nonlinear_displacement_bytes",
    "validate_nonlinear_numerical_result_ir",
    "validate_nonlinear_result_manifest",
    "validate_nonlinear_terminal_receipt",
]
