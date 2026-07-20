"""Non-authoritative nonlinear reaction/member-force recovery candidate.

The candidate binds externally recovered element force vectors to one exact
``NonlinearNumericalResultIR`` and checks element-to-global assembly, free
equilibrium, and constrained reaction partitioning. Every source array used by
that replay—including external force, element DOF map, and element force
bytes—is descriptor- and hash-bound.

The candidate still does not recompute the constitutive/element law and
therefore cannot grant reaction or member-force authority. A future
authoritative operator must replay geometry, committed material state, and
recovery laws from the exact nonlinear state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
import math
import re
from types import MappingProxyType
from typing import Any, Literal

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)
from structural_analysis.engine_v2.contracts.nonlinear_result import (
    NonlinearNumericalResultIR,
    validate_nonlinear_numerical_result_ir,
)


NONLINEAR_RECOVERY_CANDIDATE_SCHEMA_VERSION = (
    "structural-analysis-nonlinear-recovery-candidate.v1"
)
NONLINEAR_RECOVERY_CANDIDATE_AUTHORITY_PROFILE = (
    "non_authoritative_bound_nonlinear_recovery_candidate.v1"
)
NONLINEAR_RECOVERY_CANDIDATE_AUTHORITY_AXES = MappingProxyType(
    {
        "numerical_state": "inherited_authoritative",
        "convergence": "inherited_authoritative",
        "displacement": "inherited_authoritative",
        "material_state": "inherited_authoritative",
        "reaction": "candidate_not_authoritative",
        "member_force": "candidate_not_authoritative",
        "engineering_design": "not_authoritative",
        "code_compliance": "not_authoritative",
        "release_readiness": "not_authoritative",
        "commercial_use": "not_authoritative",
    }
)
NONLINEAR_RECOVERY_CANDIDATE_CLAIM_BOUNDARY = MappingProxyType(
    {
        "source_nonlinear_result_bound": True,
        "global_external_force_bytes_bound": True,
        "global_internal_force_bytes_bound": True,
        "element_global_dof_bytes_bound": True,
        "element_internal_force_bytes_bound": True,
        "element_global_assembly_checked": True,
        "element_global_assembly_equation_scaling_bound": True,
        "free_equilibrium_checked": True,
        "free_equation_scaling_bound": True,
        "constrained_reaction_partitioned": True,
        "element_or_material_law_replayed": False,
        "reaction_authority": False,
        "member_force_authority": False,
        "integration_point_output_authority": False,
        "design_or_code_authority": False,
        "release_readiness": False,
        "commercial_claim": False,
    }
)

_HASH_ZERO = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_ASSEMBLY_SCALED_LINF_TOLERANCE = 1.0e-10
_SOURCE_ARRAY_SPECS = (
    ("element_global_dofs", "<i8", "element_order_global_equations"),
    ("element_internal_force_si", "<f8", "element_order_global_force_components"),
)
_VECTOR_SPECS = (
    ("global_external_force_si", "global_equations"),
    ("global_internal_force_si", "global_equations"),
    ("reaction_global_si", "global_constrained_equations"),
    ("equilibrium_residual_global_si", "global_free_equations"),
    ("member_axial_force_si", "element_order"),
)


class NonlinearRecoveryError(ValueError):
    """Stable fail-closed nonlinear recovery error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class NonlinearRecoverySourceArrayDescriptor:
    name: str
    dtype: Literal["<i8", "<f8"]
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_length: int
    semantic_scope: str
    data_hash: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "layout": self.layout,
            "byte_length": self.byte_length,
            "semantic_scope": self.semantic_scope,
            "data_hash": self.data_hash,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class NonlinearRecoveryVectorDescriptor:
    name: str
    dtype: Literal["<f8"]
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_length: int
    equation_scope: str
    data_hash: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "layout": self.layout,
            "byte_length": self.byte_length,
            "equation_scope": self.equation_scope,
            "data_hash": self.data_hash,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class NonlinearRecoveryCandidateIR:
    schema_version: str
    recovery_id: str
    recovery_hash: str
    authority_profile: str
    source_nonlinear_result_hash: str
    model_ir_content_hash: str
    execution_plan_hash: str
    state_hash: str
    material_state_bundle_hash: str
    recovery_law_receipt_hash: str
    dof_count: int
    element_count: int
    element_force_width: int
    element_assembly_scaled_linf: float
    free_scaled_residual_linf: float
    source_descriptors: tuple[NonlinearRecoverySourceArrayDescriptor, ...]
    descriptors: tuple[NonlinearRecoveryVectorDescriptor, ...]
    extensions: Mapping[str, Any]
    _source_arrays: Mapping[str, np.ndarray] = field(repr=False, compare=False)
    _vectors: Mapping[str, np.ndarray] = field(repr=False, compare=False)
    _source_result: NonlinearNumericalResultIR = field(repr=False, compare=False)

    def source_array(self, name: str) -> np.ndarray:
        try:
            return self._source_arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown nonlinear recovery source array: {name}") from exc

    def vector(self, name: str) -> np.ndarray:
        try:
            return self._vectors[name]
        except KeyError as exc:
            raise KeyError(f"Unknown nonlinear recovery vector: {name}") from exc

    @property
    def reaction_global_si(self) -> np.ndarray:
        return self.vector("reaction_global_si")

    @property
    def equilibrium_residual_global_si(self) -> np.ndarray:
        return self.vector("equilibrium_residual_global_si")

    @property
    def member_axial_force_si(self) -> np.ndarray:
        return self.vector("member_axial_force_si")

    def to_manifest(self) -> dict[str, Any]:
        validate_nonlinear_recovery_candidate(self)
        return _payload(self, include_recovery_hash=True)


def create_nonlinear_recovery_candidate(
    *,
    recovery_id: str,
    nonlinear_result: NonlinearNumericalResultIR,
    global_external_force_si: Any,
    global_internal_force_si: Any,
    element_global_dofs: Any,
    element_internal_force_si: Any,
    member_axial_force_si: Any,
    recovery_law_receipt_hash: str,
) -> NonlinearRecoveryCandidateIR:
    """Create a bound equilibrium/reaction/member-force candidate."""

    result = validate_nonlinear_numerical_result_ir(nonlinear_result)
    plan = result._execution_plan
    dof_count = result.dof_count
    global_external = _float_array(
        global_external_force_si,
        shape=(dof_count,),
        path="/vectors/global_external_force_si",
    )
    global_internal = _float_array(
        global_internal_force_si,
        shape=(dof_count,),
        path="/vectors/global_internal_force_si",
    )
    dofs = _integer_matrix(element_global_dofs, "/source_arrays/element_global_dofs")
    element_force = _float_array(
        element_internal_force_si,
        shape=dofs.shape,
        path="/source_arrays/element_internal_force_si",
    )
    member_force = _float_array(
        member_axial_force_si,
        shape=(dofs.shape[0],),
        path="/vectors/member_axial_force_si",
    )
    if np.any(dofs < 0) or np.any(dofs >= dof_count):
        _fail(
            "nonlinear_recovery_dof_out_of_range",
            "/source_arrays/element_global_dofs",
            "Element DOF indices are outside the result equation space.",
        )

    assembled = _scatter_element_forces(dofs, element_force, dof_count)
    scale_divisors = result._equation_scaling.scale_divisors_si
    assembly_error = float(
        np.linalg.norm(
            (assembled - global_internal) / scale_divisors,
            ord=np.inf,
        )
    )
    if assembly_error > _ASSEMBLY_SCALED_LINF_TOLERANCE:
        _fail(
            "nonlinear_recovery_element_assembly_failed",
            "/metrics/element_assembly_scaled_linf",
            "Scaled element force assembly does not match supplied global internal force.",
        )

    residual = global_internal - global_external
    free = plan.array("free_dofs").astype(np.int64, copy=False)
    constrained = plan.array("constrained_dofs").astype(np.int64, copy=False)
    scaled_residual = residual / result._equation_scaling.scale_divisors_si
    free_scaled_residual_norm = (
        float(np.linalg.norm(scaled_residual[free], ord=np.inf)) if free.size else 0.0
    )
    if free_scaled_residual_norm > result._terminal_receipt.residual_tolerance_linf:
        _fail(
            "nonlinear_recovery_free_equilibrium_failed",
            "/metrics/free_scaled_residual_linf",
            "Recovered scaled free-equation residual exceeds the terminal tolerance.",
        )

    reaction = np.zeros(dof_count, dtype="<f8")
    equilibrium_residual = np.zeros(dof_count, dtype="<f8")
    reaction[constrained] = residual[constrained]
    equilibrium_residual[free] = residual[free]
    source_arrays = MappingProxyType(
        {
            "element_global_dofs": dofs,
            "element_internal_force_si": element_force,
        }
    )
    vectors = MappingProxyType(
        {
            "global_external_force_si": global_external,
            "global_internal_force_si": global_internal,
            "reaction_global_si": immutable_array(reaction, dtype="<f8"),
            "equilibrium_residual_global_si": immutable_array(
                equilibrium_residual,
                dtype="<f8",
            ),
            "member_axial_force_si": member_force,
        }
    )
    source_descriptors = tuple(
        _source_descriptor(name, dtype, scope, source_arrays[name])
        for name, dtype, scope in _SOURCE_ARRAY_SPECS
    )
    descriptors = tuple(
        _vector_descriptor(name, scope, vectors[name]) for name, scope in _VECTOR_SPECS
    )
    provisional = NonlinearRecoveryCandidateIR(
        schema_version=NONLINEAR_RECOVERY_CANDIDATE_SCHEMA_VERSION,
        recovery_id=_stable_id(recovery_id, "/recovery_id"),
        recovery_hash=_HASH_ZERO,
        authority_profile=NONLINEAR_RECOVERY_CANDIDATE_AUTHORITY_PROFILE,
        source_nonlinear_result_hash=result.result_hash,
        model_ir_content_hash=result.model_ir_content_hash,
        execution_plan_hash=result.execution_plan_hash,
        state_hash=result.state_hash,
        material_state_bundle_hash=result.material_state_bundle_hash,
        recovery_law_receipt_hash=_sha256(
            recovery_law_receipt_hash,
            "/recovery_law_receipt_hash",
        ),
        dof_count=dof_count,
        element_count=int(dofs.shape[0]),
        element_force_width=int(dofs.shape[1]),
        element_assembly_scaled_linf=assembly_error,
        free_scaled_residual_linf=free_scaled_residual_norm,
        source_descriptors=source_descriptors,
        descriptors=descriptors,
        extensions=MappingProxyType({}),
        _source_arrays=source_arrays,
        _vectors=vectors,
        _source_result=result,
    )
    candidate = replace(
        provisional,
        recovery_hash=canonical_hash(
            _payload(provisional, include_recovery_hash=False)
        ),
    )
    return validate_nonlinear_recovery_candidate(candidate)


def validate_nonlinear_recovery_candidate(
    candidate: NonlinearRecoveryCandidateIR,
) -> NonlinearRecoveryCandidateIR:
    if type(candidate) is not NonlinearRecoveryCandidateIR:
        _fail(
            "nonlinear_recovery_type_invalid",
            "/",
            "Expected NonlinearRecoveryCandidateIR.",
        )
    if candidate.schema_version != NONLINEAR_RECOVERY_CANDIDATE_SCHEMA_VERSION:
        _fail(
            "nonlinear_recovery_schema_invalid",
            "/schema_version",
            "Unsupported nonlinear recovery candidate schema.",
        )
    if candidate.authority_profile != NONLINEAR_RECOVERY_CANDIDATE_AUTHORITY_PROFILE:
        _fail(
            "nonlinear_recovery_authority_profile_invalid",
            "/authority_profile",
            "Recovery candidates cannot acquire engineering authority.",
        )
    result = validate_nonlinear_numerical_result_ir(candidate._source_result)
    expected_bindings = {
        "source_nonlinear_result_hash": result.result_hash,
        "model_ir_content_hash": result.model_ir_content_hash,
        "execution_plan_hash": result.execution_plan_hash,
        "state_hash": result.state_hash,
        "material_state_bundle_hash": result.material_state_bundle_hash,
        "dof_count": result.dof_count,
    }
    if any(
        getattr(candidate, key) != value for key, value in expected_bindings.items()
    ):
        _fail(
            "nonlinear_recovery_binding_mismatch",
            "/bindings",
            "Recovery candidate does not match its source nonlinear result.",
        )
    _stable_id(candidate.recovery_id, "/recovery_id")
    _sha256(candidate.recovery_hash, "/recovery_hash")
    _sha256(candidate.recovery_law_receipt_hash, "/recovery_law_receipt_hash")
    for path, value in (
        ("/element_count", candidate.element_count),
        ("/element_force_width", candidate.element_force_width),
    ):
        if type(value) is not int or value < 1 or value > 2**31 - 1:
            _fail(
                "nonlinear_recovery_count_invalid",
                path,
                "Recovery counts must be positive 32-bit integers.",
            )
    for path, value in (
        (
            "/metrics/element_assembly_scaled_linf",
            candidate.element_assembly_scaled_linf,
        ),
        (
            "/metrics/free_scaled_residual_linf",
            candidate.free_scaled_residual_linf,
        ),
    ):
        if type(value) is not float or not math.isfinite(value) or value < 0.0:
            _fail(
                "nonlinear_recovery_metric_invalid",
                path,
                "Recovery metrics must be finite non-negative floats.",
            )

    if not isinstance(candidate._source_arrays, MappingProxyType):
        _fail(
            "nonlinear_recovery_source_arrays_mutable",
            "/source_arrays",
            "Recovery source-array map must be immutable.",
        )
    expected_source_names = tuple(name for name, _dtype, _scope in _SOURCE_ARRAY_SPECS)
    if tuple(candidate._source_arrays) != expected_source_names:
        _fail(
            "nonlinear_recovery_source_array_set_invalid",
            "/source_arrays",
            "Recovery source-array set or order changed.",
        )
    expected_source_descriptors = tuple(
        _source_descriptor(name, dtype, scope, candidate._source_arrays[name])
        for name, dtype, scope in _SOURCE_ARRAY_SPECS
    )
    if candidate.source_descriptors != expected_source_descriptors:
        _fail(
            "nonlinear_recovery_source_descriptor_mismatch",
            "/source_descriptors",
            "Source descriptors do not match retained element arrays.",
        )

    if not isinstance(candidate._vectors, MappingProxyType):
        _fail(
            "nonlinear_recovery_vectors_mutable",
            "/vectors",
            "Recovery vector map must be immutable.",
        )
    expected_vector_names = tuple(name for name, _scope in _VECTOR_SPECS)
    if tuple(candidate._vectors) != expected_vector_names:
        _fail(
            "nonlinear_recovery_vector_set_invalid",
            "/vectors",
            "Recovery vector set or order changed.",
        )
    expected_descriptors = tuple(
        _vector_descriptor(name, scope, candidate._vectors[name])
        for name, scope in _VECTOR_SPECS
    )
    if candidate.descriptors != expected_descriptors:
        _fail(
            "nonlinear_recovery_descriptor_mismatch",
            "/descriptors",
            "Recovery descriptors do not match retained vectors.",
        )

    dofs = candidate.source_array("element_global_dofs")
    element_force = candidate.source_array("element_internal_force_si")
    if dofs.shape != element_force.shape or dofs.shape != (
        candidate.element_count,
        candidate.element_force_width,
    ):
        _fail(
            "nonlinear_recovery_element_array_shape_invalid",
            "/source_arrays",
            "Element DOF and force arrays do not match declared shape.",
        )
    if np.any(dofs < 0) or np.any(dofs >= candidate.dof_count):
        _fail(
            "nonlinear_recovery_dof_out_of_range",
            "/source_arrays/element_global_dofs",
            "Element DOF indices are outside the result equation space.",
        )
    global_external = candidate.vector("global_external_force_si")
    global_internal = candidate.vector("global_internal_force_si")
    assembled = _scatter_element_forces(dofs, element_force, candidate.dof_count)
    scale_divisors = result._equation_scaling.scale_divisors_si
    assembly_error = float(
        np.linalg.norm(
            (assembled - global_internal) / scale_divisors,
            ord=np.inf,
        )
    )
    if assembly_error != candidate.element_assembly_scaled_linf:
        _fail(
            "nonlinear_recovery_metric_mismatch",
            "/metrics/element_assembly_scaled_linf",
            "Stored scaled assembly metric does not match retained arrays.",
        )
    if assembly_error > _ASSEMBLY_SCALED_LINF_TOLERANCE:
        _fail(
            "nonlinear_recovery_element_assembly_failed",
            "/metrics/element_assembly_scaled_linf",
            "Scaled element/global assembly gate failed.",
        )

    residual = global_internal - global_external
    free = result._execution_plan.array("free_dofs").astype(np.int64, copy=False)
    constrained = result._execution_plan.array("constrained_dofs").astype(
        np.int64,
        copy=False,
    )
    scaled_residual = residual / result._equation_scaling.scale_divisors_si
    free_scaled_norm = (
        float(np.linalg.norm(scaled_residual[free], ord=np.inf)) if free.size else 0.0
    )
    if free_scaled_norm != candidate.free_scaled_residual_linf:
        _fail(
            "nonlinear_recovery_metric_mismatch",
            "/metrics/free_scaled_residual_linf",
            "Stored scaled free residual metric does not match retained vectors.",
        )
    if free_scaled_norm > result._terminal_receipt.residual_tolerance_linf:
        _fail(
            "nonlinear_recovery_free_equilibrium_failed",
            "/metrics/free_scaled_residual_linf",
            "Recovered scaled free-equation residual exceeds the terminal tolerance.",
        )
    expected_reaction = np.zeros(candidate.dof_count, dtype="<f8")
    expected_free_residual = np.zeros(candidate.dof_count, dtype="<f8")
    expected_reaction[constrained] = residual[constrained]
    expected_free_residual[free] = residual[free]
    if not np.array_equal(candidate.reaction_global_si, expected_reaction):
        _fail(
            "nonlinear_recovery_reaction_partition_mismatch",
            "/vectors/reaction_global_si",
            "Reaction candidate does not match constrained residual.",
        )
    if not np.array_equal(
        candidate.equilibrium_residual_global_si,
        expected_free_residual,
    ):
        _fail(
            "nonlinear_recovery_free_residual_partition_mismatch",
            "/vectors/equilibrium_residual_global_si",
            "Free residual vector does not match free-equation partition.",
        )
    if not isinstance(candidate.extensions, MappingProxyType) or candidate.extensions:
        _fail(
            "nonlinear_recovery_extensions_invalid",
            "/extensions",
            "Recovery candidate v1 requires immutable empty extensions.",
        )
    expected_hash = canonical_hash(_payload(candidate, include_recovery_hash=False))
    if candidate.recovery_hash != expected_hash:
        _fail(
            "nonlinear_recovery_hash_mismatch",
            "/recovery_hash",
            "Recovery hash does not match canonical content.",
        )
    return candidate


def _scatter_element_forces(
    dofs: np.ndarray,
    element_force: np.ndarray,
    dof_count: int,
) -> np.ndarray:
    assembled = np.zeros(dof_count, dtype="<f8")
    for row_dofs, row_force in zip(dofs, element_force, strict=True):
        np.add.at(assembled, row_dofs, row_force)
    return assembled


def _float_array(value: Any, *, shape: tuple[int, ...], path: str) -> np.ndarray:
    try:
        array = immutable_array(value, dtype="<f8")
    except Exception as exc:
        _fail("nonlinear_recovery_array_invalid", path, str(exc))
    if array.shape != shape or not np.all(np.isfinite(array)):
        _fail(
            "nonlinear_recovery_array_shape_invalid",
            path,
            f"Expected finite array shape {shape}.",
        )
    return array


def _integer_matrix(value: Any, path: str) -> np.ndarray:
    try:
        array = np.asarray(value)
    except Exception as exc:
        _fail("nonlinear_recovery_dof_array_invalid", path, str(exc))
    if array.ndim != 2 or array.shape[0] < 1 or array.shape[1] < 1:
        _fail(
            "nonlinear_recovery_dof_array_shape_invalid",
            path,
            "Expected a non-empty 2D element DOF array.",
        )
    if array.dtype.kind not in {"i", "u"}:
        _fail(
            "nonlinear_recovery_dof_array_dtype_invalid",
            path,
            "Element DOF array must use an integer dtype.",
        )
    try:
        return immutable_array(array, dtype="<i8")
    except Exception as exc:
        _fail("nonlinear_recovery_dof_array_invalid", path, str(exc))


def _source_descriptor(
    name: str,
    dtype: Literal["<i8", "<f8"],
    scope: str,
    array: np.ndarray,
) -> NonlinearRecoverySourceArrayDescriptor:
    if not has_immutable_bytes_backing(array):
        _fail(
            "nonlinear_recovery_source_array_mutable",
            f"/source_arrays/{name}",
            "Recovery source arrays must have immutable bytes backing.",
        )
    if array.dtype.str != dtype:
        _fail(
            "nonlinear_recovery_source_array_dtype_invalid",
            f"/source_arrays/{name}",
            f"Expected dtype {dtype}.",
        )
    provisional = NonlinearRecoverySourceArrayDescriptor(
        name=name,
        dtype=dtype,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_length=int(array.nbytes),
        semantic_scope=scope,
        data_hash=array_data_hash(array),
        content_hash=_HASH_ZERO,
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


def _vector_descriptor(
    name: str,
    scope: str,
    vector: np.ndarray,
) -> NonlinearRecoveryVectorDescriptor:
    if not has_immutable_bytes_backing(vector):
        _fail(
            "nonlinear_recovery_vector_mutable",
            f"/vectors/{name}",
            "Recovery vectors must have immutable bytes backing.",
        )
    provisional = NonlinearRecoveryVectorDescriptor(
        name=name,
        dtype="<f8",
        shape=tuple(int(value) for value in vector.shape),
        layout="C",
        byte_length=int(vector.nbytes),
        equation_scope=scope,
        data_hash=array_data_hash(vector),
        content_hash=_HASH_ZERO,
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


def _payload(
    candidate: NonlinearRecoveryCandidateIR,
    *,
    include_recovery_hash: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": candidate.schema_version,
        "recovery_id": candidate.recovery_id,
        "recovery_hash": candidate.recovery_hash,
        "authority_profile": candidate.authority_profile,
        "authority": dict(NONLINEAR_RECOVERY_CANDIDATE_AUTHORITY_AXES),
        "bindings": {
            "source_nonlinear_result_hash": candidate.source_nonlinear_result_hash,
            "model_ir_content_hash": candidate.model_ir_content_hash,
            "execution_plan_hash": candidate.execution_plan_hash,
            "state_hash": candidate.state_hash,
            "material_state_bundle_hash": candidate.material_state_bundle_hash,
            "recovery_law_receipt_hash": candidate.recovery_law_receipt_hash,
        },
        "dof_count": candidate.dof_count,
        "element_count": candidate.element_count,
        "element_force_width": candidate.element_force_width,
        "metrics": {
            "element_assembly_scaled_linf": candidate.element_assembly_scaled_linf,
            "free_scaled_residual_linf": candidate.free_scaled_residual_linf,
        },
        "source_descriptors": [row.to_dict() for row in candidate.source_descriptors],
        "descriptors": [row.to_dict() for row in candidate.descriptors],
        "claim_boundary": dict(NONLINEAR_RECOVERY_CANDIDATE_CLAIM_BOUNDARY),
        "extensions": dict(candidate.extensions),
    }
    if not include_recovery_hash:
        payload.pop("recovery_hash")
    return payload


def _stable_id(value: Any, path: str) -> str:
    text = str(value).strip()
    if not _STABLE_ID_PATTERN.fullmatch(text):
        _fail("nonlinear_recovery_id_invalid", path, "Expected a stable identifier.")
    return text


def _sha256(value: Any, path: str) -> str:
    text = str(value).strip()
    if not _HASH_PATTERN.fullmatch(text):
        _fail("nonlinear_recovery_hash_invalid", path, "Expected sha256:<hex>.")
    return text


def _fail(code: str, path: str, message: str) -> None:
    raise NonlinearRecoveryError(code, path, message)


__all__ = [
    "NONLINEAR_RECOVERY_CANDIDATE_AUTHORITY_AXES",
    "NONLINEAR_RECOVERY_CANDIDATE_AUTHORITY_PROFILE",
    "NONLINEAR_RECOVERY_CANDIDATE_CLAIM_BOUNDARY",
    "NONLINEAR_RECOVERY_CANDIDATE_SCHEMA_VERSION",
    "NonlinearRecoveryCandidateIR",
    "NonlinearRecoveryError",
    "NonlinearRecoverySourceArrayDescriptor",
    "NonlinearRecoveryVectorDescriptor",
    "create_nonlinear_recovery_candidate",
    "validate_nonlinear_recovery_candidate",
]
