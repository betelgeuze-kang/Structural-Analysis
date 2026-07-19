"""Bound linear-static reaction and member-force recovery for Engine v2.

The recovery operator binds the exact global CSR numeric values used by the
reduced solve, the reference external load used by equation scaling, and an
element-local linear law.  ``EngineeringResultIR`` can only be created from an
authoritative ``NumericalResultIR`` when an independent replay satisfies the
free-equation residual and element/global operator consistency gates.

The contract remains deliberately narrow: it covers zero-prescribed-
displacement linear statics and local element end forces.  It does not perform
design checks, authenticate external receipts, create Viewer projections, or
establish release/commercial readiness.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Literal

from jsonschema import Draft202012Validator, validators
import numpy as np

from ._canonical import (
    CanonicalContractError,
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from .equation_scaling import EquationScaling, validate_equation_scaling_binding
from .execution_plan import (
    EXECUTION_PLAN_RESIDUAL_SIGN,
    ExecutionPlan,
    validate_execution_plan,
)
from .execution_plan_reduced_csr import (
    ExecutionPlanReducedCSR,
    validate_execution_plan_reduced_csr,
)
from .result_ir import NumericalResultIR, validate_numerical_result_ir


LINEAR_STATIC_RECOVERY_OPERATOR_SCHEMA_VERSION = (
    "structural-analysis-linear-static-recovery-operator.v1"
)
LINEAR_STATIC_RECOVERY_PROFILE = (
    "bound_global_csr_and_element_local_linear_law.v1"
)
LINEAR_STATIC_RECOVERY_AUTHORITY_PROFILE = (
    "non_authoritative_bound_recovery_operator.v1"
)
ENGINEERING_RESULT_IR_SCHEMA_VERSION = (
    "structural-analysis-engineering-result-ir.v1"
)
ENGINEERING_RESULT_KIND = "linear_static_reaction_and_member_force"
ENGINEERING_RESULT_AUTHORITY_PROFILE = (
    "authoritative_bound_linear_static_recovery.v1"
)
ENGINEERING_RESULT_PROMOTION_BASIS = (
    "authoritative_numerical_result_plus_exact_operator_replay_and_equilibrium.v1"
)
ENGINEERING_RESULT_STORAGE_PROFILE = "canonical_little_endian_fp64_binary.v1"
LINEAR_STATIC_RECOVERY_ASSEMBLY_SCALED_LINF_TOLERANCE = 1.0e-12
ENGINEERING_RESULT_FREE_RESIDUAL_SCALED_LINF_TOLERANCE = 1.0e-10
ENGINEERING_RESULT_ELEMENT_BALANCE_SCALED_LINF_TOLERANCE = 1.0e-10
ENGINEERING_RESULT_LOCAL_COMPONENTS = (
    "FX_I",
    "FY_I",
    "FZ_I",
    "MX_I",
    "MY_I",
    "MZ_I",
    "FX_J",
    "FY_J",
    "FZ_J",
    "MX_J",
    "MY_J",
    "MZ_J",
)
FRAME_LOCAL_END_FORCE_PROFILE = "frame_3d_local_end_force_12.v1"
AXIAL_LOCAL_END_FORCE_PROFILE = "axial_3d_local_end_force_fx_i_fx_j.v1"

ENGINEERING_RESULT_AUTHORITY_AXES = MappingProxyType(
    {
        "numerical_state": "inherited_authoritative",
        "convergence": "inherited_authoritative",
        "displacement": "inherited_authoritative",
        "reaction": "authoritative",
        "member_force": "authoritative",
        "engineering_design": "not_authoritative",
        "code_compliance": "not_authoritative",
        "release_readiness": "not_authoritative",
        "commercial_use": "not_authoritative",
    }
)
LINEAR_STATIC_RECOVERY_CLAIM_BOUNDARY = MappingProxyType(
    {
        "numeric_arrays_embedded": False,
        "global_csr_values_bound_to_reduced_solve": True,
        "reference_load_bound_to_equation_scaling": True,
        "element_law_assembly_replayed": True,
        "result_authority": False,
        "receipt_authenticity_established": False,
        "cpu_hip_parity_established": False,
    }
)
ENGINEERING_RESULT_CLAIM_BOUNDARY = MappingProxyType(
    {
        "linear_static_only": True,
        "zero_prescribed_displacement_only": True,
        "reaction_from_constrained_global_residual": True,
        "member_force_from_bound_local_element_law": True,
        "engineering_design": False,
        "code_compliance": False,
        "nonlinear_recovery": False,
        "legacy_output_adapter": False,
        "viewer_projection": False,
        "receipt_authenticity_established": False,
        "cpu_hip_parity_established": False,
        "release_readiness": False,
        "commercial_claim": False,
    }
)

_HASH_ZERO = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_SUPPORTED_ELEMENT_PROFILES = frozenset(
    {FRAME_LOCAL_END_FORCE_PROFILE, AXIAL_LOCAL_END_FORCE_PROFILE}
)
_AXIAL_ACTIVE_COMPONENTS = frozenset({0, 6})
_OPERATOR_ARRAY_SPECS = (
    ("global_csr_values_si", "<f8", 1),
    ("reference_external_load_global_si", "<f8", 1),
    ("element_kinematic_matrices", "<f8", 3),
    ("element_local_stiffness_matrices_si", "<f8", 3),
)
_OPERATOR_ARRAY_NAMES = tuple(row[0] for row in _OPERATOR_ARRAY_SPECS)
_RESULT_VECTOR_SPECS = (
    (
        "reaction_global_si",
        "reaction_global.f64le",
        "global_storage_constrained_equations",
        "node_major_fx_fy_fz_n_mx_my_mz_nm.v1",
    ),
    (
        "equilibrium_residual_global_si",
        "equilibrium_residual_global.f64le",
        "global_storage_free_equations",
        "node_major_fx_fy_fz_n_mx_my_mz_nm.v1",
    ),
    (
        "member_local_end_force_si",
        "member_local_end_force.f64le",
        "element_order_local_end_force_components",
        "element_major_fx_fy_fz_n_mx_my_mz_nm_i_then_j.v1",
    ),
)
_RESULT_VECTOR_NAMES = tuple(row[0] for row in _RESULT_VECTOR_SPECS)
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator, type_checker=_STRICT_JSON_TYPE_CHECKER
)


class EngineeringRecoveryError(ValueError):
    """Stable fail-closed error for recovery/result contracts."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class RecoveryArrayDescriptor:
    name: str
    dtype: Literal["<f8"]
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_length: int
    data_hash: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        return payload


@dataclass(frozen=True)
class EngineeringResultArtifactDescriptor:
    name: str
    dtype: Literal["<f8"]
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_order: Literal["little"]
    equation_scope: str
    unit_profile: str
    byte_length: int
    data_hash: str
    content_hash: str
    artifact_uri: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        return payload


@dataclass(frozen=True)
class LinearStaticRecoveryOperator:
    schema_version: str
    recovery_operator_hash: str
    profile: str
    authority_profile: str
    model_ir_content_hash: str
    execution_plan_hash: str
    reduced_csr_identity_hash: str
    equation_scaling_hash: str
    operator_hash: str
    load_pattern_id: str
    ordering_hash: str
    global_pattern_hash: str
    operator_numeric_values_hash: str
    reference_external_load_data_hash: str
    recovery_law_receipt_hash: str
    element_profile_hash: str
    element_result_profiles: tuple[str, ...]
    dof_count: int
    element_count: int
    global_nnz: int
    assembly_replay_scaled_linf: float
    local_stiffness_symmetry_scaled_linf: float
    array_bundle_hash: str
    descriptors: tuple[RecoveryArrayDescriptor, ...]
    _arrays: Mapping[str, np.ndarray]
    _execution_plan: ExecutionPlan
    _equation_scaling: EquationScaling
    _reduced_csr: ExecutionPlanReducedCSR

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown recovery operator array: {name}") from exc

    def to_manifest(self) -> dict[str, Any]:
        validate_linear_static_recovery_operator(self)
        return _recovery_operator_payload(self, include_hash=True)


@dataclass(frozen=True)
class EngineeringResultIR:
    schema_version: str
    engineering_result_id: str
    engineering_result_hash: str
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
    source_numerical_result_schema_version: str
    source_numerical_result_hash: str
    source_full_residual_receipt_hash: str
    source_boundary_condition_receipt_hash: str
    recovery_operator_hash: str
    recovery_law_receipt_hash: str
    element_profile_hash: str
    load_factor: float
    dof_count: int
    element_count: int
    constrained_reaction_count: int
    evaluated_member_force_value_count: int
    free_residual_scaled_linf: float
    element_balance_scaled_linf: float
    operator_assembly_scaled_linf: float
    descriptors: tuple[EngineeringResultArtifactDescriptor, ...]
    extensions: Mapping[str, Any]
    _vectors: Mapping[str, np.ndarray]
    _numerical_result: NumericalResultIR
    _recovery_operator: LinearStaticRecoveryOperator

    def vector(self, name: str) -> np.ndarray:
        try:
            return self._vectors[name]
        except KeyError as exc:
            raise KeyError(f"Unknown engineering-result vector: {name}") from exc

    @property
    def reaction_global_si(self) -> np.ndarray:
        return self.vector("reaction_global_si")

    @property
    def equilibrium_residual_global_si(self) -> np.ndarray:
        return self.vector("equilibrium_residual_global_si")

    @property
    def member_local_end_force_si(self) -> np.ndarray:
        return self.vector("member_local_end_force_si")

    def to_manifest(self) -> dict[str, Any]:
        validate_engineering_result_ir(self)
        return _engineering_result_payload(self, include_hash=True)


def create_linear_static_recovery_operator(
    *,
    execution_plan: ExecutionPlan,
    equation_scaling: EquationScaling,
    reduced_csr: ExecutionPlanReducedCSR,
    global_csr_values_si: Any,
    reference_external_load_global_si: Any,
    element_kinematic_matrices: Any,
    element_local_stiffness_matrices_si: Any,
    element_result_profiles: Sequence[str],
    recovery_law_receipt_hash: str,
) -> LinearStaticRecoveryOperator:
    """Freeze and cross-check the exact arrays needed for recovery replay."""

    plan = validate_execution_plan(execution_plan)
    scaling = equation_scaling
    validate_equation_scaling_binding(plan, scaling=scaling)
    reduced = validate_execution_plan_reduced_csr(
        reduced_csr, execution_plan=plan
    )
    raw_arrays = {
        "global_csr_values_si": global_csr_values_si,
        "reference_external_load_global_si": reference_external_load_global_si,
        "element_kinematic_matrices": element_kinematic_matrices,
        "element_local_stiffness_matrices_si": (
            element_local_stiffness_matrices_si
        ),
    }
    try:
        arrays = MappingProxyType(
            {
                name: immutable_array(raw_arrays[name], dtype=dtype)
                for name, dtype, _rank in _OPERATOR_ARRAY_SPECS
            }
        )
    except CanonicalContractError as exc:
        _fail(
            "recovery_operator_array_canonicalization_failed",
            "/arrays",
            str(exc),
            cause=exc,
        )
    profiles = _element_profiles(
        element_result_profiles,
        element_count=plan.element_count,
        path="/element_law/element_result_profiles",
    )
    _validate_operator_arrays_for_plan(plan, arrays)
    _validate_element_profile_laws(
        profiles, arrays["element_local_stiffness_matrices_si"]
    )
    descriptors = tuple(
        _recovery_array_descriptor(name, arrays[name])
        for name in _OPERATOR_ARRAY_NAMES
    )
    profile_hash = _element_profile_hash(plan, profiles)
    assembly_error = _assembly_replay_scaled_linf(plan, arrays)
    symmetry_error = _local_stiffness_symmetry_scaled_linf(
        arrays["element_local_stiffness_matrices_si"]
    )
    provisional = LinearStaticRecoveryOperator(
        schema_version=LINEAR_STATIC_RECOVERY_OPERATOR_SCHEMA_VERSION,
        recovery_operator_hash=_HASH_ZERO,
        profile=LINEAR_STATIC_RECOVERY_PROFILE,
        authority_profile=LINEAR_STATIC_RECOVERY_AUTHORITY_PROFILE,
        model_ir_content_hash=plan.model_ir_content_hash,
        execution_plan_hash=plan.plan_hash,
        reduced_csr_identity_hash=reduced.identity_hash,
        equation_scaling_hash=scaling.scaling_hash,
        operator_hash=plan.operator_hash,
        load_pattern_id=plan.load_pattern_id,
        ordering_hash=plan.ordering_hash,
        global_pattern_hash=plan.pattern_hash,
        operator_numeric_values_hash=array_data_hash(
            arrays["global_csr_values_si"]
        ),
        reference_external_load_data_hash=array_data_hash(
            arrays["reference_external_load_global_si"]
        ),
        recovery_law_receipt_hash=_require_hash(
            recovery_law_receipt_hash,
            "/element_law/recovery_law_receipt_hash",
        ),
        element_profile_hash=profile_hash,
        element_result_profiles=profiles,
        dof_count=plan.dof_count,
        element_count=plan.element_count,
        global_nnz=int(plan.array("csr_column_indices").size),
        assembly_replay_scaled_linf=assembly_error,
        local_stiffness_symmetry_scaled_linf=symmetry_error,
        array_bundle_hash=canonical_hash([row.to_dict() for row in descriptors]),
        descriptors=descriptors,
        _arrays=arrays,
        _execution_plan=plan,
        _equation_scaling=scaling,
        _reduced_csr=reduced,
    )
    operator = replace(
        provisional,
        recovery_operator_hash=canonical_hash(
            _recovery_operator_payload(provisional, include_hash=False)
        ),
    )
    return validate_linear_static_recovery_operator(operator)


def create_engineering_result_ir(
    *,
    engineering_result_id: str,
    numerical_result: NumericalResultIR,
    recovery_operator: LinearStaticRecoveryOperator,
) -> EngineeringResultIR:
    """Recover reactions/member forces after independent equilibrium replay."""

    numerical = validate_numerical_result_ir(numerical_result)
    operator = validate_linear_static_recovery_operator(recovery_operator)
    _validate_result_operator_bindings(numerical, operator)
    vectors, metrics = _evaluate_engineering_vectors(numerical, operator)
    normalized_id = _require_stable_id(
        engineering_result_id, "/engineering_result_id"
    )
    descriptors = tuple(
        _result_artifact_descriptor(
            name=name,
            vector=vectors[name],
            equation_scope=scope,
            unit_profile=unit_profile,
            engineering_result_id=normalized_id,
            source_numerical_result_hash=numerical.result_hash,
            recovery_operator_hash=operator.recovery_operator_hash,
            filename=filename,
        )
        for name, filename, scope, unit_profile in _RESULT_VECTOR_SPECS
    )
    plan = operator._execution_plan
    evaluated_count = sum(
        12 if profile == FRAME_LOCAL_END_FORCE_PROFILE else 2
        for profile in operator.element_result_profiles
    )
    provisional = EngineeringResultIR(
        schema_version=ENGINEERING_RESULT_IR_SCHEMA_VERSION,
        engineering_result_id=normalized_id,
        engineering_result_hash=_HASH_ZERO,
        result_kind=ENGINEERING_RESULT_KIND,
        authority_profile=ENGINEERING_RESULT_AUTHORITY_PROFILE,
        model_ir_content_hash=numerical.model_ir_content_hash,
        execution_plan_hash=numerical.execution_plan_hash,
        reduced_csr_identity_hash=numerical.reduced_csr_identity_hash,
        equation_scaling_hash=numerical.equation_scaling_hash,
        operator_hash=numerical.operator_hash,
        state_hash=numerical.state_hash,
        state_epoch=numerical.state_epoch,
        load_pattern_id=numerical.load_pattern_id,
        source_numerical_result_schema_version=numerical.schema_version,
        source_numerical_result_hash=numerical.result_hash,
        source_full_residual_receipt_hash=numerical.full_residual_receipt_hash,
        source_boundary_condition_receipt_hash=(
            numerical.boundary_condition_receipt_hash
        ),
        recovery_operator_hash=operator.recovery_operator_hash,
        recovery_law_receipt_hash=operator.recovery_law_receipt_hash,
        element_profile_hash=operator.element_profile_hash,
        load_factor=numerical.load_factor,
        dof_count=plan.dof_count,
        element_count=plan.element_count,
        constrained_reaction_count=int(plan.array("constrained_dofs").size),
        evaluated_member_force_value_count=evaluated_count,
        free_residual_scaled_linf=metrics["free_residual_scaled_linf"],
        element_balance_scaled_linf=metrics["element_balance_scaled_linf"],
        operator_assembly_scaled_linf=operator.assembly_replay_scaled_linf,
        descriptors=descriptors,
        extensions=MappingProxyType({}),
        _vectors=MappingProxyType(vectors),
        _numerical_result=numerical,
        _recovery_operator=operator,
    )
    result = replace(
        provisional,
        engineering_result_hash=canonical_hash(
            _engineering_result_payload(provisional, include_hash=False)
        ),
    )
    return validate_engineering_result_ir(result)


def validate_linear_static_recovery_operator(
    operator: LinearStaticRecoveryOperator,
) -> LinearStaticRecoveryOperator:
    """Reject stale bindings, mutable bytes, or inconsistent element laws."""

    if type(operator) is not LinearStaticRecoveryOperator:
        _fail(
            "recovery_operator_type_invalid",
            "/",
            "Expected LinearStaticRecoveryOperator.",
        )
    plan = validate_execution_plan(operator._execution_plan)
    scaling = operator._equation_scaling
    validate_equation_scaling_binding(plan, scaling=scaling)
    reduced = validate_execution_plan_reduced_csr(
        operator._reduced_csr, execution_plan=plan
    )
    if operator.schema_version != LINEAR_STATIC_RECOVERY_OPERATOR_SCHEMA_VERSION:
        _fail(
            "recovery_operator_schema_version_invalid",
            "/schema_version",
            "Unsupported recovery operator schema.",
        )
    if operator.profile != LINEAR_STATIC_RECOVERY_PROFILE:
        _fail(
            "recovery_operator_profile_invalid",
            "/profile",
            "Unsupported recovery operator profile.",
        )
    if operator.authority_profile != LINEAR_STATIC_RECOVERY_AUTHORITY_PROFILE:
        _fail(
            "recovery_operator_authority_profile_invalid",
            "/authority_profile",
            "Recovery operators cannot acquire result authority.",
        )
    for path, value in (
        ("/recovery_operator_hash", operator.recovery_operator_hash),
        ("/bindings/model_ir_content_hash", operator.model_ir_content_hash),
        ("/bindings/execution_plan_hash", operator.execution_plan_hash),
        (
            "/bindings/reduced_csr_identity_hash",
            operator.reduced_csr_identity_hash,
        ),
        ("/bindings/equation_scaling_hash", operator.equation_scaling_hash),
        ("/bindings/operator_hash", operator.operator_hash),
        ("/bindings/ordering_hash", operator.ordering_hash),
        ("/bindings/global_pattern_hash", operator.global_pattern_hash),
        (
            "/bindings/operator_numeric_values_hash",
            operator.operator_numeric_values_hash,
        ),
        (
            "/bindings/reference_external_load_data_hash",
            operator.reference_external_load_data_hash,
        ),
        (
            "/element_law/recovery_law_receipt_hash",
            operator.recovery_law_receipt_hash,
        ),
        ("/element_law/element_profile_hash", operator.element_profile_hash),
        ("/array_bundle_hash", operator.array_bundle_hash),
    ):
        _require_hash(value, path)
    expected_bindings = {
        "model_ir_content_hash": plan.model_ir_content_hash,
        "execution_plan_hash": plan.plan_hash,
        "reduced_csr_identity_hash": reduced.identity_hash,
        "equation_scaling_hash": scaling.scaling_hash,
        "operator_hash": plan.operator_hash,
        "load_pattern_id": plan.load_pattern_id,
        "ordering_hash": plan.ordering_hash,
        "global_pattern_hash": plan.pattern_hash,
        "operator_numeric_values_hash": reduced.operator_numeric_values_hash,
        "reference_external_load_data_hash": (
            scaling.source_reference_load_data_hash
        ),
    }
    actual_bindings = {key: getattr(operator, key) for key in expected_bindings}
    if actual_bindings != expected_bindings:
        _fail(
            "recovery_operator_binding_mismatch",
            "/bindings",
            "Recovery operator does not match its retained plan/scaling/CSR.",
        )
    if not isinstance(operator._arrays, MappingProxyType):
        _fail(
            "recovery_operator_arrays_mutable",
            "/arrays",
            "Recovery array map must be immutable.",
        )
    if tuple(operator._arrays) != _OPERATOR_ARRAY_NAMES:
        _fail(
            "recovery_operator_array_set_invalid",
            "/arrays",
            "Recovery array set or order is invalid.",
        )
    if (
        type(operator.descriptors) is not tuple
        or tuple(row.name for row in operator.descriptors)
        != _OPERATOR_ARRAY_NAMES
        or any(type(row) is not RecoveryArrayDescriptor for row in operator.descriptors)
    ):
        _fail(
            "recovery_operator_descriptor_set_invalid",
            "/array_descriptors",
            "Recovery descriptor set or order is invalid.",
        )
    _validate_operator_arrays_for_plan(plan, operator._arrays)
    descriptor_by_name = {row.name: row for row in operator.descriptors}
    for name, _dtype, _rank in _OPERATOR_ARRAY_SPECS:
        if descriptor_by_name[name] != _recovery_array_descriptor(
            name, operator.array(name)
        ):
            _fail(
                "recovery_operator_descriptor_mismatch",
                f"/array_descriptors/{name}",
                "Descriptor does not match immutable array bytes.",
            )
    if (
        array_data_hash(operator.array("global_csr_values_si"))
        != operator.operator_numeric_values_hash
    ):
        _fail(
            "recovery_operator_numeric_values_mismatch",
            "/bindings/operator_numeric_values_hash",
            "Global CSR values differ from the reduced-solve numeric binding.",
        )
    if (
        array_data_hash(operator.array("reference_external_load_global_si"))
        != operator.reference_external_load_data_hash
    ):
        _fail(
            "recovery_operator_reference_load_mismatch",
            "/bindings/reference_external_load_data_hash",
            "Reference load differs from the EquationScaling source bytes.",
        )
    if type(operator.element_result_profiles) is not tuple:
        _fail(
            "recovery_operator_element_profiles_mutable",
            "/element_law/element_result_profiles",
            "Element recovery profiles must use an immutable tuple.",
        )
    profiles = _element_profiles(
        operator.element_result_profiles,
        element_count=plan.element_count,
        path="/element_law/element_result_profiles",
    )
    _validate_element_profile_laws(
        profiles, operator.array("element_local_stiffness_matrices_si")
    )
    if operator.element_profile_hash != _element_profile_hash(plan, profiles):
        _fail(
            "recovery_operator_element_profile_hash_mismatch",
            "/element_law/element_profile_hash",
            "Element profile hash is stale.",
        )
    expected_symmetry = _local_stiffness_symmetry_scaled_linf(
        operator.array("element_local_stiffness_matrices_si")
    )
    expected_assembly = _assembly_replay_scaled_linf(plan, operator._arrays)
    if (
        operator.local_stiffness_symmetry_scaled_linf != expected_symmetry
        or expected_symmetry
        > LINEAR_STATIC_RECOVERY_ASSEMBLY_SCALED_LINF_TOLERANCE
    ):
        _fail(
            "recovery_operator_local_stiffness_nonsymmetric",
            "/consistency/local_stiffness_symmetry_scaled_linf",
            "Local stiffness symmetry gate failed.",
        )
    if (
        operator.assembly_replay_scaled_linf != expected_assembly
        or expected_assembly
        > LINEAR_STATIC_RECOVERY_ASSEMBLY_SCALED_LINF_TOLERANCE
    ):
        _fail(
            "recovery_operator_assembly_replay_failed",
            "/consistency/assembly_replay_scaled_linf",
            "Element laws do not reproduce the bound global CSR operator.",
        )
    expected_counts = (
        operator.dof_count == plan.dof_count
        and operator.element_count == plan.element_count
        and operator.global_nnz == plan.array("csr_column_indices").size
    )
    if not expected_counts:
        _fail(
            "recovery_operator_dimensions_mismatch",
            "/dimensions",
            "Recovery dimensions are stale.",
        )
    descriptor_payload = [row.to_dict() for row in operator.descriptors]
    if operator.array_bundle_hash != canonical_hash(descriptor_payload):
        _fail(
            "recovery_operator_array_bundle_hash_mismatch",
            "/array_bundle_hash",
            "Recovery array bundle hash is stale.",
        )
    validate_linear_static_recovery_operator_manifest(
        _recovery_operator_payload(operator, include_hash=True)
    )
    if operator.recovery_operator_hash != canonical_hash(
        _recovery_operator_payload(operator, include_hash=False)
    ):
        _fail(
            "recovery_operator_hash_mismatch",
            "/recovery_operator_hash",
            "Recovery operator hash is stale.",
        )
    return operator


def validate_engineering_result_ir(
    result: EngineeringResultIR,
) -> EngineeringResultIR:
    """Recompute the complete engineering-result replay and authority gates."""

    if type(result) is not EngineeringResultIR:
        _fail(
            "engineering_result_type_invalid",
            "/",
            "Expected EngineeringResultIR.",
        )
    numerical = validate_numerical_result_ir(result._numerical_result)
    operator = validate_linear_static_recovery_operator(result._recovery_operator)
    _validate_result_operator_bindings(numerical, operator)
    if result.schema_version != ENGINEERING_RESULT_IR_SCHEMA_VERSION:
        _fail(
            "engineering_result_schema_version_invalid",
            "/schema_version",
            "Unsupported engineering-result schema.",
        )
    _require_stable_id(result.engineering_result_id, "/engineering_result_id")
    if result.result_kind != ENGINEERING_RESULT_KIND:
        _fail(
            "engineering_result_kind_invalid",
            "/result_kind",
            "Unsupported engineering-result kind.",
        )
    if result.authority_profile != ENGINEERING_RESULT_AUTHORITY_PROFILE:
        _fail(
            "engineering_result_authority_profile_invalid",
            "/authority_profile",
            "Unsupported engineering-result authority profile.",
        )
    for path, value in (
        ("/engineering_result_hash", result.engineering_result_hash),
        ("/bindings/model_ir_content_hash", result.model_ir_content_hash),
        ("/bindings/execution_plan_hash", result.execution_plan_hash),
        (
            "/bindings/reduced_csr_identity_hash",
            result.reduced_csr_identity_hash,
        ),
        ("/bindings/equation_scaling_hash", result.equation_scaling_hash),
        ("/bindings/operator_hash", result.operator_hash),
        ("/bindings/state_hash", result.state_hash),
        (
            "/source_numerical_result/result_hash",
            result.source_numerical_result_hash,
        ),
        (
            "/source_numerical_result/full_residual_receipt_hash",
            result.source_full_residual_receipt_hash,
        ),
        (
            "/source_numerical_result/boundary_condition_receipt_hash",
            result.source_boundary_condition_receipt_hash,
        ),
        ("/recovery/recovery_operator_hash", result.recovery_operator_hash),
        (
            "/recovery/recovery_law_receipt_hash",
            result.recovery_law_receipt_hash,
        ),
        ("/recovery/element_profile_hash", result.element_profile_hash),
    ):
        _require_hash(value, path)
    expected_identity = {
        "model_ir_content_hash": numerical.model_ir_content_hash,
        "execution_plan_hash": numerical.execution_plan_hash,
        "reduced_csr_identity_hash": numerical.reduced_csr_identity_hash,
        "equation_scaling_hash": numerical.equation_scaling_hash,
        "operator_hash": numerical.operator_hash,
        "state_hash": numerical.state_hash,
        "state_epoch": numerical.state_epoch,
        "load_pattern_id": numerical.load_pattern_id,
        "source_numerical_result_schema_version": numerical.schema_version,
        "source_numerical_result_hash": numerical.result_hash,
        "source_full_residual_receipt_hash": numerical.full_residual_receipt_hash,
        "source_boundary_condition_receipt_hash": (
            numerical.boundary_condition_receipt_hash
        ),
        "recovery_operator_hash": operator.recovery_operator_hash,
        "recovery_law_receipt_hash": operator.recovery_law_receipt_hash,
        "element_profile_hash": operator.element_profile_hash,
        "load_factor": numerical.load_factor,
    }
    if {key: getattr(result, key) for key in expected_identity} != expected_identity:
        _fail(
            "engineering_result_binding_mismatch",
            "/bindings",
            "Engineering result identifies stale source artifacts.",
        )
    plan = operator._execution_plan
    expected_counts = {
        "dof_count": plan.dof_count,
        "element_count": plan.element_count,
        "constrained_reaction_count": int(plan.array("constrained_dofs").size),
        "evaluated_member_force_value_count": sum(
            12 if profile == FRAME_LOCAL_END_FORCE_PROFILE else 2
            for profile in operator.element_result_profiles
        ),
    }
    if {key: getattr(result, key) for key in expected_counts} != expected_counts:
        _fail(
            "engineering_result_dimensions_mismatch",
            "/dimensions",
            "Engineering-result dimensions are stale.",
        )
    if not isinstance(result.extensions, MappingProxyType) or result.extensions:
        _fail(
            "engineering_result_extensions_not_supported",
            "/extensions",
            "EngineeringResultIR v1 requires an empty immutable extension map.",
        )
    if not isinstance(result._vectors, MappingProxyType):
        _fail(
            "engineering_result_vectors_mutable",
            "/artifacts",
            "Engineering-result vector map must be immutable.",
        )
    if tuple(result._vectors) != _RESULT_VECTOR_NAMES:
        _fail(
            "engineering_result_vector_set_invalid",
            "/artifacts",
            "Engineering-result vector set or order is invalid.",
        )
    expected_vectors, expected_metrics = _evaluate_engineering_vectors(
        numerical, operator
    )
    expected_shapes = {
        "reaction_global_si": (plan.dof_count,),
        "equilibrium_residual_global_si": (plan.dof_count,),
        "member_local_end_force_si": (plan.element_count, 12),
    }
    for name in _RESULT_VECTOR_NAMES:
        vector = result.vector(name)
        _validate_float_array(
            vector,
            dtype="<f8",
            rank=len(expected_shapes[name]),
            shape=expected_shapes[name],
            path=f"/vectors/{name}",
        )
        if not np.array_equal(vector, expected_vectors[name]):
            _fail(
                "engineering_result_vector_replay_mismatch",
                f"/artifacts/{name}",
                "Engineering-result vector differs from deterministic replay.",
            )
    expected_metric_fields = {
        "free_residual_scaled_linf": expected_metrics[
            "free_residual_scaled_linf"
        ],
        "element_balance_scaled_linf": expected_metrics[
            "element_balance_scaled_linf"
        ],
        "operator_assembly_scaled_linf": operator.assembly_replay_scaled_linf,
    }
    if {
        key: getattr(result, key) for key in expected_metric_fields
    } != expected_metric_fields:
        _fail(
            "engineering_result_gate_metric_mismatch",
            "/gates",
            "Engineering-result gate metrics are stale.",
        )
    if (
        type(result.descriptors) is not tuple
        or tuple(row.name for row in result.descriptors) != _RESULT_VECTOR_NAMES
        or any(
            type(row) is not EngineeringResultArtifactDescriptor
            for row in result.descriptors
        )
    ):
        _fail(
            "engineering_result_descriptor_set_invalid",
            "/artifacts",
            "Engineering-result descriptor set or order is invalid.",
        )
    for descriptor, (name, filename, scope, unit_profile) in zip(
        result.descriptors, _RESULT_VECTOR_SPECS, strict=True
    ):
        expected_descriptor = _result_artifact_descriptor(
            name=name,
            vector=result.vector(name),
            equation_scope=scope,
            unit_profile=unit_profile,
            engineering_result_id=result.engineering_result_id,
            source_numerical_result_hash=result.source_numerical_result_hash,
            recovery_operator_hash=result.recovery_operator_hash,
            filename=filename,
        )
        if descriptor != expected_descriptor:
            _fail(
                "engineering_result_descriptor_mismatch",
                f"/artifacts/{name}",
                "Artifact descriptor does not match immutable result bytes.",
            )
    validate_engineering_result_ir_manifest(
        _engineering_result_payload(result, include_hash=True)
    )
    if result.engineering_result_hash != canonical_hash(
        _engineering_result_payload(result, include_hash=False)
    ):
        _fail(
            "engineering_result_hash_mismatch",
            "/engineering_result_hash",
            "Engineering-result hash is stale.",
        )
    return result


def validate_linear_static_recovery_operator_manifest(
    payload: Any,
) -> Mapping[str, Any]:
    """Validate a descriptor-only transport manifest."""

    checked = _validate_schema(
        payload,
        validator=_recovery_operator_schema_validator(),
        code="recovery_operator_schema_invalid",
    )
    dimensions = checked["dimensions"]
    descriptors = checked["array_descriptors"]
    expected_shapes = {
        "global_csr_values_si": [dimensions["global_nnz"]],
        "reference_external_load_global_si": [dimensions["dof_count"]],
        "element_kinematic_matrices": [
            dimensions["element_count"],
            12,
            12,
        ],
        "element_local_stiffness_matrices_si": [
            dimensions["element_count"],
            12,
            12,
        ],
    }
    ordered_descriptors: list[Mapping[str, Any]] = []
    for name, dtype, rank in _OPERATOR_ARRAY_SPECS:
        descriptor = descriptors[name]
        if (
            descriptor["name"] != name
            or descriptor["dtype"] != dtype
            or len(descriptor["shape"]) != rank
            or descriptor["shape"] != expected_shapes[name]
            or descriptor["byte_length"]
            != 8 * math.prod(expected_shapes[name])
        ):
            _fail(
                "recovery_operator_descriptor_semantics_invalid",
                f"/array_descriptors/{name}",
                "Descriptor dtype, shape, or byte length is stale.",
            )
        ordered_descriptors.append(descriptor)
    if checked["array_bundle_hash"] != canonical_hash(ordered_descriptors):
        _fail(
            "recovery_operator_array_bundle_hash_mismatch",
            "/array_bundle_hash",
            "Recovery array bundle hash is stale.",
        )
    bindings = checked["bindings"]
    if (
        descriptors["global_csr_values_si"]["data_hash"]
        != bindings["operator_numeric_values_hash"]
        or descriptors["reference_external_load_global_si"]["data_hash"]
        != bindings["reference_external_load_data_hash"]
    ):
        _fail(
            "recovery_operator_manifest_numeric_binding_mismatch",
            "/bindings",
            "Manifest numeric descriptors do not match their source bindings.",
        )
    element_order = checked["element_law"]["element_order"]
    profiles = checked["element_law"]["element_result_profiles"]
    if (
        len(element_order) != dimensions["element_count"]
        or len(profiles) != dimensions["element_count"]
        or len(set(element_order)) != len(element_order)
    ):
        _fail(
            "recovery_operator_manifest_element_order_invalid",
            "/element_law",
            "Element order/profile counts are inconsistent.",
        )
    expected_profile_hash = canonical_hash(
        {
            "element_ids": element_order,
            "element_result_profiles": profiles,
            "local_components": list(ENGINEERING_RESULT_LOCAL_COMPONENTS),
        }
    )
    if checked["element_law"]["element_profile_hash"] != expected_profile_hash:
        _fail(
            "recovery_operator_element_profile_hash_mismatch",
            "/element_law/element_profile_hash",
            "Element profile hash is stale.",
        )
    consistency = checked["consistency"]
    if (
        consistency["assembly_replay_scaled_linf_tolerance"]
        != LINEAR_STATIC_RECOVERY_ASSEMBLY_SCALED_LINF_TOLERANCE
        or consistency["assembly_replay_scaled_linf"]
        > LINEAR_STATIC_RECOVERY_ASSEMBLY_SCALED_LINF_TOLERANCE
        or consistency["local_stiffness_symmetry_scaled_linf"]
        > LINEAR_STATIC_RECOVERY_ASSEMBLY_SCALED_LINF_TOLERANCE
    ):
        _fail(
            "recovery_operator_manifest_consistency_gate_failed",
            "/consistency",
            "Recovery operator consistency metrics exceed the fixed gate.",
        )
    without_hash = dict(checked)
    claimed_hash = without_hash.pop("recovery_operator_hash")
    if claimed_hash != canonical_hash(without_hash):
        _fail(
            "recovery_operator_hash_mismatch",
            "/recovery_operator_hash",
            "Recovery operator hash is stale.",
        )
    return checked


def validate_engineering_result_ir_manifest(
    payload: Any,
) -> Mapping[str, Any]:
    """Validate an EngineeringResultIR manifest without artifact bytes."""

    checked = _validate_schema(
        payload,
        validator=_engineering_result_schema_validator(),
        code="engineering_result_schema_invalid",
    )
    dimensions = checked["dimensions"]
    evaluated_count = dimensions["evaluated_member_force_value_count"]
    if (
        dimensions["constrained_reaction_count"] > dimensions["dof_count"]
        or evaluated_count < 2 * dimensions["element_count"]
        or evaluated_count > 12 * dimensions["element_count"]
        or (evaluated_count - 2 * dimensions["element_count"]) % 10 != 0
    ):
        _fail(
            "engineering_result_manifest_dimensions_invalid",
            "/dimensions",
            "Reaction/member-force counts are impossible for the v1 profiles.",
        )
    artifacts = checked["outputs"]["artifacts"]
    expected_shapes = {
        "reaction_global_si": [dimensions["dof_count"]],
        "equilibrium_residual_global_si": [dimensions["dof_count"]],
        "member_local_end_force_si": [dimensions["element_count"], 12],
    }
    if [row["name"] for row in artifacts] != list(_RESULT_VECTOR_NAMES):
        _fail(
            "engineering_result_artifact_order_invalid",
            "/outputs/artifacts",
            "Engineering-result artifact set or order is invalid.",
        )
    for index, (artifact, spec) in enumerate(
        zip(artifacts, _RESULT_VECTOR_SPECS, strict=True)
    ):
        name, filename, scope, unit_profile = spec
        expected_shape = expected_shapes[name]
        expected_uri = (
            "artifact://engine-v2/engineering-results/"
            f"{checked['engineering_result_id']}/{filename}"
        )
        if (
            artifact["shape"] != expected_shape
            or artifact["byte_length"] != 8 * math.prod(expected_shape)
            or artifact["equation_scope"] != scope
            or artifact["unit_profile"] != unit_profile
            or artifact["artifact_uri"] != expected_uri
        ):
            _fail(
                "engineering_result_descriptor_semantics_invalid",
                f"/outputs/artifacts/{index}",
                "Artifact descriptor shape, scope, units, length, or URI is stale.",
            )
    gates = checked["gates"]
    if (
        checked["outputs"]["element_profile_hash"]
        != checked["recovery"]["element_profile_hash"]
    ):
        _fail(
            "engineering_result_element_profile_binding_mismatch",
            "/outputs/element_profile_hash",
            "Output element profiles differ from the bound recovery operator.",
        )
    expected_tolerances = {
        "operator_assembly_scaled_linf_tolerance": (
            LINEAR_STATIC_RECOVERY_ASSEMBLY_SCALED_LINF_TOLERANCE
        ),
        "free_residual_scaled_linf_tolerance": (
            ENGINEERING_RESULT_FREE_RESIDUAL_SCALED_LINF_TOLERANCE
        ),
        "element_balance_scaled_linf_tolerance": (
            ENGINEERING_RESULT_ELEMENT_BALANCE_SCALED_LINF_TOLERANCE
        ),
    }
    for field, expected in expected_tolerances.items():
        if gates[field] != expected:
            _fail(
                "engineering_result_gate_tolerance_invalid",
                f"/gates/{field}",
                "Engineering-result gate tolerance is fixed by v1.",
            )
    metric_pairs = (
        (
            "operator_assembly_scaled_linf",
            "operator_assembly_scaled_linf_tolerance",
        ),
        ("free_residual_scaled_linf", "free_residual_scaled_linf_tolerance"),
        (
            "element_balance_scaled_linf",
            "element_balance_scaled_linf_tolerance",
        ),
    )
    if any(gates[metric] > gates[tolerance] for metric, tolerance in metric_pairs):
        _fail(
            "engineering_result_manifest_gate_failed",
            "/gates",
            "Engineering-result manifest contains a failed authority gate.",
        )
    without_hash = dict(checked)
    claimed_hash = without_hash.pop("engineering_result_hash")
    if claimed_hash != canonical_hash(without_hash):
        _fail(
            "engineering_result_hash_mismatch",
            "/engineering_result_hash",
            "Engineering-result hash is stale.",
        )
    return checked


def write_engineering_result_artifacts(
    result: EngineeringResultIR,
    output_directory: str | Path,
) -> EngineeringResultIR:
    """Write all result arrays without overwriting any existing artifact."""

    checked = validate_engineering_result_ir(result)
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    targets = {
        name: directory / filename
        for name, filename, _scope, _units in _RESULT_VECTOR_SPECS
    }
    for index, target in enumerate(targets.values()):
        if target.exists():
            _fail(
                "engineering_result_artifact_target_exists",
                f"/outputs/artifacts/{index}",
                f"Refusing to overwrite existing artifact: {target}",
            )
    created: list[Path] = []
    try:
        for name, target in targets.items():
            try:
                handle = target.open("xb")
            except FileExistsError:
                _fail(
                    "engineering_result_artifact_target_exists",
                    f"/outputs/artifacts/{name}",
                    f"Refusing to overwrite existing artifact: {target}",
                )
            with handle:
                created.append(target)
                handle.write(memoryview(checked.vector(name)).cast("B"))
            validate_engineering_result_artifact_bytes(
                checked, name=name, data=target.read_bytes()
            )
    except Exception:
        for target in reversed(created):
            target.unlink(missing_ok=True)
        raise
    return checked


def validate_engineering_result_artifact_bytes(
    result: EngineeringResultIR,
    *,
    name: str,
    data: bytes | bytearray | memoryview,
) -> np.ndarray:
    """Validate and return one immutable canonical artifact array."""

    checked = validate_engineering_result_ir(result)
    descriptor_by_name = {row.name: row for row in checked.descriptors}
    if name not in descriptor_by_name:
        _fail(
            "engineering_result_artifact_name_invalid",
            "/outputs/artifacts",
            "Unknown engineering-result artifact.",
        )
    descriptor = descriptor_by_name[name]
    raw = bytes(data)
    if len(raw) != descriptor.byte_length:
        _fail(
            "engineering_result_artifact_length_mismatch",
            f"/outputs/artifacts/{name}/byte_length",
            "Artifact byte length is stale.",
        )
    vector = immutable_array(
        np.frombuffer(raw, dtype="<f8").reshape(descriptor.shape), dtype="<f8"
    )
    spec = next(row for row in _RESULT_VECTOR_SPECS if row[0] == name)
    expected = _result_artifact_descriptor(
        name=name,
        vector=vector,
        equation_scope=spec[2],
        unit_profile=spec[3],
        engineering_result_id=checked.engineering_result_id,
        source_numerical_result_hash=checked.source_numerical_result_hash,
        recovery_operator_hash=checked.recovery_operator_hash,
        filename=spec[1],
    )
    if expected != descriptor:
        _fail(
            "engineering_result_artifact_hash_mismatch",
            f"/outputs/artifacts/{name}",
            "Artifact bytes do not match the canonical descriptor.",
        )
    return vector


def _validate_result_operator_bindings(
    numerical: NumericalResultIR,
    operator: LinearStaticRecoveryOperator,
) -> None:
    expected = {
        "model_ir_content_hash": numerical.model_ir_content_hash,
        "execution_plan_hash": numerical.execution_plan_hash,
        "reduced_csr_identity_hash": numerical.reduced_csr_identity_hash,
        "equation_scaling_hash": numerical.equation_scaling_hash,
        "operator_hash": numerical.operator_hash,
        "load_pattern_id": numerical.load_pattern_id,
        "operator_numeric_values_hash": (
            numerical._reduced_csr.operator_numeric_values_hash
        ),
    }
    actual = {key: getattr(operator, key) for key in expected}
    if actual != expected:
        _fail(
            "engineering_result_recovery_source_mismatch",
            "/recovery",
            "Recovery operator was not created for the source NumericalResultIR.",
        )
    if (
        operator._execution_plan.plan_hash
        != numerical._execution_plan.plan_hash
        or operator._equation_scaling.scaling_hash
        != numerical._equation_scaling.scaling_hash
        or operator._reduced_csr.identity_hash
        != numerical._reduced_csr.identity_hash
    ):
        _fail(
            "engineering_result_retained_source_mismatch",
            "/recovery",
            "Retained recovery artifacts differ from NumericalResultIR sources.",
        )


def _evaluate_engineering_vectors(
    numerical: NumericalResultIR,
    operator: LinearStaticRecoveryOperator,
) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    plan = operator._execution_plan
    displacement = numerical.displacement_global_si
    constrained = plan.array("constrained_dofs")
    free = plan.array("free_dofs")
    if constrained.size and np.any(displacement[constrained] != 0.0):
        _fail(
            "engineering_result_nonzero_prescribed_displacement_unsupported",
            "/source_numerical_result/displacement",
            "EngineeringResultIR v1 only supports zero prescribed displacements.",
        )
    internal = _csr_action(
        row_ptr=plan.array("csr_row_ptr"),
        columns=plan.array("csr_column_indices"),
        values=operator.array("global_csr_values_si"),
        vector=displacement,
    )
    external = (
        numerical.load_factor
        * operator.array("reference_external_load_global_si")
    )
    residual = np.asarray(internal - external, dtype="<f8")
    scaling = operator._equation_scaling.scale_divisors_si
    free_residual_scaled_linf = _linf(residual[free] / scaling[free])
    if (
        free_residual_scaled_linf
        > ENGINEERING_RESULT_FREE_RESIDUAL_SCALED_LINF_TOLERANCE
    ):
        _fail(
            "engineering_result_free_equilibrium_gate_failed",
            "/gates/free_residual_scaled_linf",
            "Recovered global residual exceeds the fixed free-equation gate.",
        )

    element_dofs = plan.array("element_global_dofs")
    kinematic = operator.array("element_kinematic_matrices")
    local_stiffness = operator.array("element_local_stiffness_matrices_si")
    local_forces = np.zeros((plan.element_count, 12), dtype="<f8")
    global_contributions: list[list[float]] = [
        [] for _index in range(plan.dof_count)
    ]
    for element in range(plan.element_count):
        gathered = displacement[element_dofs[element]]
        local_displacement = _matrix_vector_fsum(
            kinematic[element], gathered
        )
        force = _matrix_vector_fsum(local_stiffness[element], local_displacement)
        local_forces[element] = force
        global_element_force = _transpose_matrix_vector_fsum(
            kinematic[element], force
        )
        for local_index, global_dof in enumerate(element_dofs[element]):
            global_contributions[int(global_dof)].append(
                float(global_element_force[local_index])
            )
    element_internal = np.asarray(
        [math.fsum(row) for row in global_contributions], dtype="<f8"
    )
    element_balance_scaled_linf = _linf(
        (element_internal - internal) / scaling
    )
    if (
        element_balance_scaled_linf
        > ENGINEERING_RESULT_ELEMENT_BALANCE_SCALED_LINF_TOLERANCE
    ):
        _fail(
            "engineering_result_element_balance_gate_failed",
            "/gates/element_balance_scaled_linf",
            "Element end forces do not reproduce the global internal force.",
        )
    reaction = np.zeros(plan.dof_count, dtype="<f8")
    equilibrium = np.zeros(plan.dof_count, dtype="<f8")
    reaction[constrained] = residual[constrained]
    equilibrium[free] = residual[free]
    vectors = {
        "reaction_global_si": immutable_array(reaction, dtype="<f8"),
        "equilibrium_residual_global_si": immutable_array(
            equilibrium, dtype="<f8"
        ),
        "member_local_end_force_si": immutable_array(
            local_forces, dtype="<f8"
        ),
    }
    return vectors, {
        "free_residual_scaled_linf": free_residual_scaled_linf,
        "element_balance_scaled_linf": element_balance_scaled_linf,
    }


def _validate_operator_arrays_for_plan(
    plan: ExecutionPlan,
    arrays: Mapping[str, np.ndarray],
) -> None:
    expected_shapes = {
        "global_csr_values_si": (
            int(plan.array("csr_column_indices").size),
        ),
        "reference_external_load_global_si": (plan.dof_count,),
        "element_kinematic_matrices": (plan.element_count, 12, 12),
        "element_local_stiffness_matrices_si": (
            plan.element_count,
            12,
            12,
        ),
    }
    for name, dtype, rank in _OPERATOR_ARRAY_SPECS:
        _validate_float_array(
            arrays[name],
            dtype=dtype,
            rank=rank,
            shape=expected_shapes[name],
            path=f"/arrays/{name}",
        )


def _validate_element_profile_laws(
    profiles: tuple[str, ...], local_stiffness: np.ndarray
) -> None:
    inactive = tuple(
        index for index in range(12) if index not in _AXIAL_ACTIVE_COMPONENTS
    )
    for element, profile in enumerate(profiles):
        if profile != AXIAL_LOCAL_END_FORCE_PROFILE:
            continue
        matrix = local_stiffness[element]
        if np.any(matrix[list(inactive), :] != 0.0) or np.any(
            matrix[:, list(inactive)] != 0.0
        ):
            _fail(
                "recovery_operator_axial_component_law_invalid",
                f"/element_law/element_result_profiles/{element}",
                "Axial recovery may evaluate only FX_I and FX_J.",
            )


def _element_profiles(
    values: Sequence[str], *, element_count: int, path: str
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        _fail(
            "recovery_operator_element_profiles_invalid",
            path,
            "Expected one ordered recovery profile per element.",
        )
    profiles = tuple(values)
    if len(profiles) != element_count:
        _fail(
            "recovery_operator_element_profiles_invalid",
            path,
            "Element profile count differs from ExecutionPlan element order.",
        )
    for index, profile in enumerate(profiles):
        if type(profile) is not str or profile not in _SUPPORTED_ELEMENT_PROFILES:
            _fail(
                "recovery_operator_element_profile_unsupported",
                f"{path}/{index}",
                "Unsupported element result profile.",
            )
    return profiles


def _element_profile_hash(
    plan: ExecutionPlan, profiles: tuple[str, ...]
) -> str:
    return canonical_hash(
        {
            "element_ids": list(plan.element_ids),
            "element_result_profiles": list(profiles),
            "local_components": list(ENGINEERING_RESULT_LOCAL_COMPONENTS),
        }
    )


def _local_stiffness_symmetry_scaled_linf(
    local_stiffness: np.ndarray,
) -> float:
    maximum = 0.0
    tiny = float(np.finfo(np.float64).tiny)
    for matrix in local_stiffness:
        scale = max(float(np.max(np.abs(matrix))), tiny)
        error = float(np.max(np.abs(matrix - matrix.T))) / scale
        maximum = max(maximum, error)
    return maximum


def _assembly_replay_scaled_linf(
    plan: ExecutionPlan,
    arrays: Mapping[str, np.ndarray],
) -> float:
    row_ptr = plan.array("csr_row_ptr")
    columns = plan.array("csr_column_indices")
    element_dofs = plan.array("element_global_dofs")
    global_values = arrays["global_csr_values_si"]
    kinematic = arrays["element_kinematic_matrices"]
    local_stiffness = arrays["element_local_stiffness_matrices_si"]
    assembled = np.zeros(global_values.shape, dtype=np.float64)
    omitted_by_row = np.zeros(plan.dof_count, dtype=np.float64)
    for element in range(plan.element_count):
        element_global = (
            kinematic[element].T
            @ local_stiffness[element]
            @ kinematic[element]
        )
        dofs = element_dofs[element]
        for local_row, global_row_value in enumerate(dofs):
            global_row = int(global_row_value)
            start = int(row_ptr[global_row])
            stop = int(row_ptr[global_row + 1])
            row_columns = columns[start:stop]
            for local_column, global_column_value in enumerate(dofs):
                value = float(element_global[local_row, local_column])
                global_column = int(global_column_value)
                offset = int(np.searchsorted(row_columns, global_column))
                if offset >= row_columns.size or int(row_columns[offset]) != global_column:
                    omitted_by_row[global_row] = max(
                        omitted_by_row[global_row], abs(value)
                    )
                    continue
                assembled[start + offset] += value
    maximum = 0.0
    tiny = float(np.finfo(np.float64).tiny)
    for row in range(plan.dof_count):
        start = int(row_ptr[row])
        stop = int(row_ptr[row + 1])
        difference = float(
            np.max(np.abs(assembled[start:stop] - global_values[start:stop]))
        )
        scale = max(
            float(np.max(np.abs(assembled[start:stop]))),
            float(np.max(np.abs(global_values[start:stop]))),
            omitted_by_row[row],
            tiny,
        )
        maximum = max(maximum, difference / scale, omitted_by_row[row] / scale)
    return maximum


def _csr_action(
    *,
    row_ptr: np.ndarray,
    columns: np.ndarray,
    values: np.ndarray,
    vector: np.ndarray,
) -> np.ndarray:
    result = np.zeros(row_ptr.size - 1, dtype="<f8")
    for row in range(result.size):
        start = int(row_ptr[row])
        stop = int(row_ptr[row + 1])
        result[row] = math.fsum(
            float(values[position]) * float(vector[int(columns[position])])
            for position in range(start, stop)
        )
    return result


def _matrix_vector_fsum(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    return np.asarray(
        [
            math.fsum(
                float(matrix[row, column]) * float(vector[column])
                for column in range(matrix.shape[1])
            )
            for row in range(matrix.shape[0])
        ],
        dtype="<f8",
    )


def _transpose_matrix_vector_fsum(
    matrix: np.ndarray, vector: np.ndarray
) -> np.ndarray:
    return np.asarray(
        [
            math.fsum(
                float(matrix[row, column]) * float(vector[row])
                for row in range(matrix.shape[0])
            )
            for column in range(matrix.shape[1])
        ],
        dtype="<f8",
    )


def _linf(values: np.ndarray) -> float:
    return 0.0 if values.size == 0 else float(np.max(np.abs(values)))


def _recovery_array_descriptor(
    name: str, array: np.ndarray
) -> RecoveryArrayDescriptor:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "layout": "C",
        "byte_length": int(array.nbytes),
    }
    return RecoveryArrayDescriptor(
        name=name,
        dtype="<f8",
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
    )


def _result_artifact_descriptor(
    *,
    name: str,
    vector: np.ndarray,
    equation_scope: str,
    unit_profile: str,
    engineering_result_id: str,
    source_numerical_result_hash: str,
    recovery_operator_hash: str,
    filename: str,
) -> EngineeringResultArtifactDescriptor:
    metadata = {
        "name": name,
        "dtype": "<f8",
        "shape": list(vector.shape),
        "layout": "C",
        "byte_order": "little",
        "equation_scope": equation_scope,
        "unit_profile": unit_profile,
        "byte_length": int(vector.nbytes),
        "engineering_result_id": engineering_result_id,
        "source_numerical_result_hash": source_numerical_result_hash,
        "recovery_operator_hash": recovery_operator_hash,
    }
    return EngineeringResultArtifactDescriptor(
        name=name,
        dtype="<f8",
        shape=tuple(int(value) for value in vector.shape),
        layout="C",
        byte_order="little",
        equation_scope=equation_scope,
        unit_profile=unit_profile,
        byte_length=int(vector.nbytes),
        data_hash=array_data_hash(vector),
        content_hash=array_content_hash(metadata, vector),
        artifact_uri=(
            "artifact://engine-v2/engineering-results/"
            f"{engineering_result_id}/{filename}"
        ),
    )


def _recovery_operator_payload(
    operator: LinearStaticRecoveryOperator, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": operator.schema_version,
        "profile": operator.profile,
        "authority_profile": operator.authority_profile,
        "bindings": {
            "model_ir_content_hash": operator.model_ir_content_hash,
            "execution_plan_hash": operator.execution_plan_hash,
            "reduced_csr_identity_hash": operator.reduced_csr_identity_hash,
            "equation_scaling_hash": operator.equation_scaling_hash,
            "operator_hash": operator.operator_hash,
            "load_pattern_id": operator.load_pattern_id,
            "ordering_hash": operator.ordering_hash,
            "global_pattern_hash": operator.global_pattern_hash,
            "operator_numeric_values_hash": (
                operator.operator_numeric_values_hash
            ),
            "reference_external_load_data_hash": (
                operator.reference_external_load_data_hash
            ),
        },
        "element_law": {
            "recovery_law_receipt_hash": operator.recovery_law_receipt_hash,
            "element_order": list(operator._execution_plan.element_ids),
            "element_result_profiles": list(operator.element_result_profiles),
            "element_profile_hash": operator.element_profile_hash,
            "local_components": list(ENGINEERING_RESULT_LOCAL_COMPONENTS),
            "kinematic_action": "u_local=Q_element*u_global_element",
            "force_action": "f_local=K_local*u_local",
            "global_action": "f_global_element=transpose(Q_element)*f_local",
        },
        "dimensions": {
            "dof_count": operator.dof_count,
            "element_count": operator.element_count,
            "global_nnz": operator.global_nnz,
            "element_dof_count": 12,
            "local_component_count": 12,
        },
        "consistency": {
            "assembly_replay_scaled_linf": (
                operator.assembly_replay_scaled_linf
            ),
            "local_stiffness_symmetry_scaled_linf": (
                operator.local_stiffness_symmetry_scaled_linf
            ),
            "assembly_replay_scaled_linf_tolerance": (
                LINEAR_STATIC_RECOVERY_ASSEMBLY_SCALED_LINF_TOLERANCE
            ),
            "assembly_replay_gate_passed": True,
            "local_stiffness_symmetry_gate_passed": True,
        },
        "array_bundle_hash": operator.array_bundle_hash,
        "array_descriptors": {
            row.name: row.to_dict() for row in operator.descriptors
        },
        "claim_boundary": dict(LINEAR_STATIC_RECOVERY_CLAIM_BOUNDARY),
    }
    if include_hash:
        payload["recovery_operator_hash"] = operator.recovery_operator_hash
    return payload


def _engineering_result_payload(
    result: EngineeringResultIR, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": result.schema_version,
        "engineering_result_id": result.engineering_result_id,
        "result_kind": result.result_kind,
        "authority_profile": result.authority_profile,
        "promotion_basis": ENGINEERING_RESULT_PROMOTION_BASIS,
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
        "source_numerical_result": {
            "schema_version": result.source_numerical_result_schema_version,
            "result_hash": result.source_numerical_result_hash,
            "full_residual_receipt_hash": (
                result.source_full_residual_receipt_hash
            ),
            "boundary_condition_receipt_hash": (
                result.source_boundary_condition_receipt_hash
            ),
            "authority_inherited": True,
        },
        "recovery": {
            "recovery_operator_hash": result.recovery_operator_hash,
            "recovery_law_receipt_hash": result.recovery_law_receipt_hash,
            "element_profile_hash": result.element_profile_hash,
            "residual_sign": EXECUTION_PLAN_RESIDUAL_SIGN,
            "reference_load_scaled_by_state_load_factor": True,
            "load_factor": result.load_factor,
        },
        "dimensions": {
            "dof_count": result.dof_count,
            "element_count": result.element_count,
            "constrained_reaction_count": result.constrained_reaction_count,
            "evaluated_member_force_value_count": (
                result.evaluated_member_force_value_count
            ),
            "local_component_count": 12,
        },
        "gates": {
            "operator_assembly_scaled_linf": (
                result.operator_assembly_scaled_linf
            ),
            "operator_assembly_scaled_linf_tolerance": (
                LINEAR_STATIC_RECOVERY_ASSEMBLY_SCALED_LINF_TOLERANCE
            ),
            "free_residual_scaled_linf": result.free_residual_scaled_linf,
            "free_residual_scaled_linf_tolerance": (
                ENGINEERING_RESULT_FREE_RESIDUAL_SCALED_LINF_TOLERANCE
            ),
            "element_balance_scaled_linf": result.element_balance_scaled_linf,
            "element_balance_scaled_linf_tolerance": (
                ENGINEERING_RESULT_ELEMENT_BALANCE_SCALED_LINF_TOLERANCE
            ),
            "operator_assembly_gate_passed": True,
            "free_equilibrium_gate_passed": True,
            "element_balance_gate_passed": True,
            "zero_prescribed_displacement_gate_passed": True,
        },
        "outputs": {
            "storage_profile": ENGINEERING_RESULT_STORAGE_PROFILE,
            "local_components": list(ENGINEERING_RESULT_LOCAL_COMPONENTS),
            "element_profile_hash": result.element_profile_hash,
            "artifacts": [row.to_dict() for row in result.descriptors],
        },
        "authority": dict(ENGINEERING_RESULT_AUTHORITY_AXES),
        "claim_boundary": dict(ENGINEERING_RESULT_CLAIM_BOUNDARY),
        "extensions": dict(result.extensions),
    }
    if include_hash:
        payload["engineering_result_hash"] = result.engineering_result_hash
    return payload


def _validate_float_array(
    array: Any,
    *,
    dtype: str,
    rank: int,
    shape: tuple[int, ...],
    path: str,
) -> None:
    if (
        type(array) is not np.ndarray
        or array.dtype.str != dtype
        or array.ndim != rank
        or array.shape != shape
        or not array.flags.c_contiguous
        or not has_immutable_bytes_backing(array)
        or not np.all(np.isfinite(array))
    ):
        _fail(
            "recovery_array_contract_invalid",
            path,
            f"Expected immutable finite canonical {dtype} array with shape {shape}.",
        )


def _require_hash(value: Any, path: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        _fail(
            "recovery_hash_invalid",
            path,
            "Expected sha256:<64 lowercase hex>.",
        )
    return value


def _require_stable_id(value: Any, path: str) -> str:
    if type(value) is not str or _STABLE_ID_PATTERN.fullmatch(value) is None:
        _fail(
            "engineering_result_id_invalid",
            path,
            "Expected a stable identifier.",
        )
    return value


def _validate_schema(
    payload: Any,
    *,
    validator: Draft202012Validator,
    code: str,
) -> Mapping[str, Any]:
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail(code, path or "/", error.message)
    if not isinstance(payload, Mapping):  # pragma: no cover - schema invariant
        _fail(code, "/", "Expected an object.")
    return payload


@lru_cache(maxsize=1)
def _recovery_operator_schema_validator() -> Draft202012Validator:
    resource = resources.files("structural_analysis.schemas").joinpath(
        "linear_static_recovery_operator_v1.schema.json"
    )
    with resource.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return _StrictDraft202012Validator(schema)


@lru_cache(maxsize=1)
def _engineering_result_schema_validator() -> Draft202012Validator:
    resource = resources.files("structural_analysis.schemas").joinpath(
        "engineering_result_ir_v1.schema.json"
    )
    with resource.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return _StrictDraft202012Validator(schema)


def _fail(
    code: str,
    path: str,
    message: str,
    *,
    cause: Exception | None = None,
) -> None:
    error = EngineeringRecoveryError(code, path, message)
    if cause is None:
        raise error
    raise error from cause


__all__ = [
    "AXIAL_LOCAL_END_FORCE_PROFILE",
    "ENGINEERING_RESULT_AUTHORITY_AXES",
    "ENGINEERING_RESULT_AUTHORITY_PROFILE",
    "ENGINEERING_RESULT_CLAIM_BOUNDARY",
    "ENGINEERING_RESULT_ELEMENT_BALANCE_SCALED_LINF_TOLERANCE",
    "ENGINEERING_RESULT_FREE_RESIDUAL_SCALED_LINF_TOLERANCE",
    "ENGINEERING_RESULT_IR_SCHEMA_VERSION",
    "ENGINEERING_RESULT_KIND",
    "ENGINEERING_RESULT_LOCAL_COMPONENTS",
    "ENGINEERING_RESULT_PROMOTION_BASIS",
    "ENGINEERING_RESULT_STORAGE_PROFILE",
    "FRAME_LOCAL_END_FORCE_PROFILE",
    "LINEAR_STATIC_RECOVERY_ASSEMBLY_SCALED_LINF_TOLERANCE",
    "LINEAR_STATIC_RECOVERY_AUTHORITY_PROFILE",
    "LINEAR_STATIC_RECOVERY_CLAIM_BOUNDARY",
    "LINEAR_STATIC_RECOVERY_OPERATOR_SCHEMA_VERSION",
    "LINEAR_STATIC_RECOVERY_PROFILE",
    "EngineeringRecoveryError",
    "EngineeringResultArtifactDescriptor",
    "EngineeringResultIR",
    "LinearStaticRecoveryOperator",
    "RecoveryArrayDescriptor",
    "create_engineering_result_ir",
    "create_linear_static_recovery_operator",
    "validate_engineering_result_artifact_bytes",
    "validate_engineering_result_ir",
    "validate_engineering_result_ir_manifest",
    "validate_linear_static_recovery_operator",
    "validate_linear_static_recovery_operator_manifest",
    "write_engineering_result_artifacts",
]
