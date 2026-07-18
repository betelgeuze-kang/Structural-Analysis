"""Deterministic SI equation-scaling contracts for Engine v2.

This module defines preprocessing and residual-observation artifacts only.  It
does not decide convergence, produce an authoritative numerical result, or run
an execution backend.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import math
from typing import Any

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
from .execution_plan import (
    EXECUTION_PLAN_CAPABILITY_PROFILE,
    EXECUTION_PLAN_DOF_COMPONENTS,
    EXECUTION_PLAN_REQUIRED_EXTENSIONS_EXTENSION_KEY,
    EXECUTION_PLAN_REQUIRED_EXTENSIONS_SCHEMA_VERSION,
    EXECUTION_PLAN_SCALED_CAPABILITY_PROFILE,
    ExecutionPlan,
    _freeze_extensions,
    _plan_payload,
    _thaw,
    validate_execution_plan,
)

EQUATION_SCALING_SCHEMA_VERSION = "structural-analysis-equation-scaling.v1"
SCALED_RESIDUAL_TRACE_SCHEMA_VERSION = "structural-analysis-scaled-residual-trace.v1"
EQUATION_SCALING_EXTENSION_KEY = "engine-v2:equation-scaling"
CHARACTERISTIC_LENGTH_POLICY = "two_max_radius_from_fsum_centroid.v1"
REFERENCE_FORCE_POLICY = "max_translation_or_equivalent_moment_with_floor.v1"
REFERENCE_EQUATION_SCOPE = "free_equations"

_HASH_ZERO = "sha256:" + "0" * 64
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator, type_checker=_STRICT_JSON_TYPE_CHECKER
)


class EquationScalingError(ValueError):
    """Fail-closed equation-scaling error with a stable code and path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class EquationScaling:
    """Immutable per-equation divisors in canonical SI equation order."""

    schema_version: str
    scaling_hash: str
    base_plan_hash: str
    equation_order_hash: str
    source_model_ir_content_hash: str
    source_load_pattern_id: str
    reference_equation_scope: str
    source_free_dofs_content_hash: str
    source_node_coordinates_data_hash: str
    source_node_coordinates_content_hash: str
    source_reference_load_data_hash: str
    source_reference_load_content_hash: str
    source_commitment_hash: str
    characteristic_length_policy: str
    reference_force_policy: str
    characteristic_length_m: float
    minimum_characteristic_length_m: float
    reference_force_n: float
    minimum_reference_force_n: float
    dof_count: int
    scale_vector_data_hash: str
    scale_vector_content_hash: str
    _scale_divisors_si: np.ndarray

    @property
    def scale_divisors_si(self) -> np.ndarray:
        return self._scale_divisors_si

    def to_manifest(self) -> dict[str, Any]:
        validate_equation_scaling(self)
        return _scaling_payload(self, include_scaling_hash=True)


@dataclass(frozen=True)
class ScaledResidualTrace:
    """Non-authoritative raw/scaled residual observation."""

    schema_version: str
    trace_hash: str
    execution_plan_hash: str
    scaling_hash: str
    residual_sign: str
    equation_scope: str
    active_equations: tuple[int, ...]
    raw_residual_data_hash: str
    scaled_residual_data_hash: str
    raw_translation_l2_n: float
    raw_translation_linf_n: float
    raw_rotation_l2_nm: float
    raw_rotation_linf_nm: float
    scaled_l2: float
    scaled_linf: float
    governing_equation: int
    governing_node_id: str
    governing_dof: str
    _raw_residual_si: np.ndarray
    _scaled_residual: np.ndarray

    @property
    def raw_residual_si(self) -> np.ndarray:
        return self._raw_residual_si

    @property
    def scaled_residual(self) -> np.ndarray:
        return self._scaled_residual

    def to_manifest(self) -> dict[str, Any]:
        validate_scaled_residual_trace(self)
        return _trace_payload(self, include_trace_hash=True)


def create_equation_scaling(
    *,
    execution_plan: ExecutionPlan,
    node_coordinates_m: Any,
    reference_equation_load_si: Any,
    minimum_characteristic_length_m: float = 1.0e-12,
    minimum_reference_force_n: float = 1.0,
) -> EquationScaling:
    """Create O(N) force/moment nondimensionalization for a base plan."""

    plan = validate_execution_plan(execution_plan)
    if EQUATION_SCALING_EXTENSION_KEY in plan.extensions:
        _fail(
            "base_plan_already_scaled",
            "/execution_plan/extensions",
            "Scaling must be created against an unbound base plan.",
        )
    coordinates = _float_array(
        node_coordinates_m,
        shape=(plan.node_count, 3),
        path="/node_coordinates_m",
    )
    loads = _float_array(
        reference_equation_load_si,
        shape=(plan.dof_count,),
        path="/reference_equation_load_si",
    )
    equation_order_hash = _equation_order_hash(plan)
    source_commitment = _source_commitment_from_arrays(
        plan=plan,
        equation_order_hash=equation_order_hash,
        node_coordinates_m=coordinates,
        reference_equation_load_si=loads,
    )
    source_commitment_hash = canonical_hash(source_commitment)
    minimum_length = _positive_float(
        minimum_characteristic_length_m, "/minimum_characteristic_length_m"
    )
    minimum_force = _positive_float(
        minimum_reference_force_n, "/minimum_reference_force_n"
    )

    characteristic_length = _characteristic_length(coordinates, minimum_length)

    node_dofs = plan.array("node_dof_indices")
    translation_equations = node_dofs[:, :3].reshape(-1)
    rotation_equations = node_dofs[:, 3:].reshape(-1)
    reference_force = _reference_force(
        plan=plan,
        reference_equation_load_si=loads,
        characteristic_length_m=characteristic_length,
        minimum_reference_force_n=minimum_force,
    )
    moment_scale = reference_force * characteristic_length
    if not math.isfinite(reference_force) or not math.isfinite(moment_scale):
        _fail("scale_nonfinite", "/scale_divisors_si", "Scale overflowed fp64.")

    divisors = np.empty(plan.dof_count, dtype="<f8")
    divisors[translation_equations] = reference_force
    divisors[rotation_equations] = moment_scale
    immutable_divisors = _immutable_float_array(divisors, "/scale_divisors_si")
    vector_metadata = _vector_metadata(
        "scale_divisors_si", immutable_divisors, equation_order_hash
    )
    provisional = EquationScaling(
        schema_version=EQUATION_SCALING_SCHEMA_VERSION,
        scaling_hash=_HASH_ZERO,
        base_plan_hash=plan.plan_hash,
        equation_order_hash=equation_order_hash,
        source_model_ir_content_hash=plan.model_ir_content_hash,
        source_load_pattern_id=plan.load_pattern_id,
        reference_equation_scope=REFERENCE_EQUATION_SCOPE,
        source_free_dofs_content_hash=source_commitment["free_dofs_content_hash"],
        source_node_coordinates_data_hash=source_commitment["node_coordinates"][
            "data_hash"
        ],
        source_node_coordinates_content_hash=source_commitment["node_coordinates"][
            "content_hash"
        ],
        source_reference_load_data_hash=source_commitment["reference_equation_load"][
            "data_hash"
        ],
        source_reference_load_content_hash=source_commitment["reference_equation_load"][
            "content_hash"
        ],
        source_commitment_hash=source_commitment_hash,
        characteristic_length_policy=CHARACTERISTIC_LENGTH_POLICY,
        reference_force_policy=REFERENCE_FORCE_POLICY,
        characteristic_length_m=characteristic_length,
        minimum_characteristic_length_m=minimum_length,
        reference_force_n=reference_force,
        minimum_reference_force_n=minimum_force,
        dof_count=plan.dof_count,
        scale_vector_data_hash=array_data_hash(immutable_divisors),
        scale_vector_content_hash=array_content_hash(
            vector_metadata, immutable_divisors
        ),
        _scale_divisors_si=immutable_divisors,
    )
    scaling = replace(
        provisional,
        scaling_hash=canonical_hash(
            _scaling_payload(provisional, include_scaling_hash=False)
        ),
    )
    return validate_equation_scaling(
        scaling,
        execution_plan=plan,
        node_coordinates_m=coordinates,
        reference_equation_load_si=loads,
    )


def bind_equation_scaling_to_execution_plan(
    execution_plan: ExecutionPlan,
    scaling: EquationScaling,
    *,
    node_coordinates_m: Any,
    reference_equation_load_si: Any,
) -> ExecutionPlan:
    """Replay scaling sources and bind their hashes into a capability-gated plan."""

    if node_coordinates_m is None or reference_equation_load_si is None:
        _fail(
            "source_replay_required",
            "/source_commitment",
            "Binding requires coordinates and the reference equation-load vector.",
        )
    plan = validate_execution_plan(execution_plan)
    validate_equation_scaling(
        scaling,
        execution_plan=plan,
        node_coordinates_m=node_coordinates_m,
        reference_equation_load_si=reference_equation_load_si,
    )
    if EQUATION_SCALING_EXTENSION_KEY in plan.extensions:
        _fail(
            "scaling_binding_exists",
            f"/extensions/{EQUATION_SCALING_EXTENSION_KEY}",
            "ExecutionPlan already has an equation-scaling binding.",
        )
    extensions = _thaw(plan.extensions)
    required_extensions = sorted(
        {*plan.required_extensions, EQUATION_SCALING_EXTENSION_KEY}
    )
    extensions[EXECUTION_PLAN_REQUIRED_EXTENSIONS_EXTENSION_KEY] = {
        "schema_version": EXECUTION_PLAN_REQUIRED_EXTENSIONS_SCHEMA_VERSION,
        "required_extensions": required_extensions,
    }
    extensions[EQUATION_SCALING_EXTENSION_KEY] = {
        "schema_version": EQUATION_SCALING_SCHEMA_VERSION,
        "base_plan_hash": plan.plan_hash,
        "scaling_hash": scaling.scaling_hash,
        "scale_vector_hash": scaling.scale_vector_content_hash,
        "equation_order_hash": scaling.equation_order_hash,
        "source_commitment_hash": scaling.source_commitment_hash,
        "source_model_ir_content_hash": scaling.source_model_ir_content_hash,
        "source_load_pattern_id": scaling.source_load_pattern_id,
        "source_free_dofs_content_hash": scaling.source_free_dofs_content_hash,
        "reference_equation_scope": scaling.reference_equation_scope,
    }
    provisional = replace(
        plan,
        capability_profile=EXECUTION_PLAN_SCALED_CAPABILITY_PROFILE,
        plan_hash=_HASH_ZERO,
        extensions=_freeze_extensions(extensions),
    )
    bound = replace(
        provisional,
        plan_hash=canonical_hash(_plan_payload(provisional, include_plan_hash=False)),
    )
    validate_execution_plan(bound)
    validate_equation_scaling_binding(
        bound,
        scaling=scaling,
        node_coordinates_m=node_coordinates_m,
        reference_equation_load_si=reference_equation_load_si,
    )
    return bound


def execution_plan_scaling_hash(execution_plan: ExecutionPlan) -> str | None:
    """Return the typed scaling hash, or ``None`` for an unbound plan."""

    plan = validate_execution_plan(execution_plan)
    binding = plan.extensions.get(EQUATION_SCALING_EXTENSION_KEY)
    return None if binding is None else str(binding["scaling_hash"])


def validate_equation_scaling_binding(
    execution_plan: ExecutionPlan,
    *,
    scaling: EquationScaling | None = None,
    node_coordinates_m: Any | None = None,
    reference_equation_load_si: Any | None = None,
) -> ExecutionPlan:
    """Validate a bound plan, scaling identity, and optional full source replay."""

    plan = validate_execution_plan(execution_plan)
    base_plan = _validate_equation_scaling_binding_semantics(plan)
    binding = plan.extensions[EQUATION_SCALING_EXTENSION_KEY]
    if scaling is not None:
        validate_equation_scaling(
            scaling,
            execution_plan=base_plan,
            node_coordinates_m=node_coordinates_m,
            reference_equation_load_si=reference_equation_load_si,
        )
        expected = {
            "schema_version": scaling.schema_version,
            "base_plan_hash": scaling.base_plan_hash,
            "scaling_hash": scaling.scaling_hash,
            "scale_vector_hash": scaling.scale_vector_content_hash,
            "equation_order_hash": scaling.equation_order_hash,
            "source_commitment_hash": scaling.source_commitment_hash,
            "source_model_ir_content_hash": scaling.source_model_ir_content_hash,
            "source_load_pattern_id": scaling.source_load_pattern_id,
            "source_free_dofs_content_hash": scaling.source_free_dofs_content_hash,
            "reference_equation_scope": scaling.reference_equation_scope,
        }
        if _thaw(binding) != expected:
            _fail(
                "scaling_binding_mismatch",
                f"/extensions/{EQUATION_SCALING_EXTENSION_KEY}",
                "Binding does not match the supplied scaling artifact.",
            )
    elif node_coordinates_m is not None or reference_equation_load_si is not None:
        _fail(
            "source_replay_scaling_missing",
            "/source_commitment",
            "Source replay requires the scaling artifact.",
        )
    return plan


def _validate_equation_scaling_binding_semantics(
    execution_plan: ExecutionPlan,
) -> ExecutionPlan:
    """Validate binding semantics and return the exact reconstructed base plan."""

    plan = execution_plan
    binding = plan.extensions.get(EQUATION_SCALING_EXTENSION_KEY)
    if binding is None:
        _fail(
            "scaling_binding_missing",
            f"/extensions/{EQUATION_SCALING_EXTENSION_KEY}",
            "Equation-scaling binding is required.",
        )
    base_plan = _reconstruct_unbound_execution_plan(plan)
    if binding["base_plan_hash"] != base_plan.plan_hash:
        _fail(
            "base_plan_hash_mismatch",
            f"/extensions/{EQUATION_SCALING_EXTENSION_KEY}/base_plan_hash",
            "Binding does not identify the exact unbound plan.",
        )
    _validate_binding_plan_identity(
        binding,
        model_ir_content_hash=base_plan.model_ir_content_hash,
        load_pattern_id=base_plan.load_pattern_id,
        free_dofs_content_hash=next(
            row.content_hash for row in base_plan.descriptors if row.name == "free_dofs"
        ),
    )
    if binding["equation_order_hash"] != _equation_order_hash(base_plan):
        _fail(
            "equation_order_hash_mismatch",
            f"/extensions/{EQUATION_SCALING_EXTENSION_KEY}/equation_order_hash",
            "Binding does not match the plan equation order.",
        )
    if binding["reference_equation_scope"] != REFERENCE_EQUATION_SCOPE:
        _fail(
            "reference_equation_scope_mismatch",
            f"/extensions/{EQUATION_SCALING_EXTENSION_KEY}/reference_equation_scope",
            "Only free-equation scaling is supported.",
        )
    return base_plan


def _reconstruct_unbound_execution_plan(plan: ExecutionPlan) -> ExecutionPlan:
    extensions = _extensions_without_equation_scaling(plan.extensions)
    base_provisional = replace(
        plan,
        capability_profile=EXECUTION_PLAN_CAPABILITY_PROFILE,
        plan_hash=_HASH_ZERO,
        extensions=_freeze_extensions(extensions),
    )
    reconstructed_base_hash = canonical_hash(
        _plan_payload(base_provisional, include_plan_hash=False)
    )
    return validate_execution_plan(
        replace(base_provisional, plan_hash=reconstructed_base_hash)
    )


def _validate_equation_scaling_binding_manifest_semantics(
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Match manifest-only typed checks to the object-level binding validator."""

    binding = payload["extensions"][EQUATION_SCALING_EXTENSION_KEY]
    base_payload = _thaw(payload)
    base_payload["capability_profile"] = EXECUTION_PLAN_CAPABILITY_PROFILE
    base_payload["extensions"] = _extensions_without_equation_scaling(
        payload["extensions"]
    )
    base_payload.pop("plan_hash")
    reconstructed_base_hash = canonical_hash(base_payload)
    if binding["base_plan_hash"] != reconstructed_base_hash:
        _fail(
            "base_plan_hash_mismatch",
            f"/extensions/{EQUATION_SCALING_EXTENSION_KEY}/base_plan_hash",
            "Binding does not identify the exact unbound manifest.",
        )
    _validate_binding_plan_identity(
        binding,
        model_ir_content_hash=payload["model_ir_content_hash"],
        load_pattern_id=payload["analysis"]["load_pattern_id"],
        free_dofs_content_hash=payload["array_descriptors"]["free_dofs"][
            "content_hash"
        ],
    )
    expected_equation_order_hash = canonical_hash(
        {
            "node_ids": list(payload["entity_order"]["node_ids"]),
            "dof_components": list(payload["dof_layout"]["components"]),
            "node_dof_indices_data_hash": payload["array_descriptors"][
                "node_dof_indices"
            ]["data_hash"],
            "dof_count": payload["dof_layout"]["dof_count"],
        }
    )
    if binding["equation_order_hash"] != expected_equation_order_hash:
        _fail(
            "equation_order_hash_mismatch",
            f"/extensions/{EQUATION_SCALING_EXTENSION_KEY}/equation_order_hash",
            "Binding does not match the manifest equation order.",
        )
    if binding["reference_equation_scope"] != REFERENCE_EQUATION_SCOPE:
        _fail(
            "reference_equation_scope_mismatch",
            f"/extensions/{EQUATION_SCALING_EXTENSION_KEY}/reference_equation_scope",
            "Only free-equation scaling is supported.",
        )
    return payload


def _extensions_without_equation_scaling(
    extensions: Mapping[str, Any],
) -> dict[str, Any]:
    result = _thaw(extensions)
    del result[EQUATION_SCALING_EXTENSION_KEY]
    required = result[EXECUTION_PLAN_REQUIRED_EXTENSIONS_EXTENSION_KEY][
        "required_extensions"
    ]
    remaining = [key for key in required if key != EQUATION_SCALING_EXTENSION_KEY]
    if remaining:
        result[EXECUTION_PLAN_REQUIRED_EXTENSIONS_EXTENSION_KEY][
            "required_extensions"
        ] = remaining
    else:
        del result[EXECUTION_PLAN_REQUIRED_EXTENSIONS_EXTENSION_KEY]
    return result


def _validate_binding_plan_identity(
    binding: Mapping[str, Any],
    *,
    model_ir_content_hash: str,
    load_pattern_id: str,
    free_dofs_content_hash: str,
) -> None:
    comparisons = (
        (
            "source_model_ir_content_hash",
            model_ir_content_hash,
            "binding_source_model_ir_mismatch",
            "Binding identifies another ModelIR.",
        ),
        (
            "source_load_pattern_id",
            load_pattern_id,
            "binding_source_load_pattern_mismatch",
            "Binding identifies another load pattern.",
        ),
        (
            "source_free_dofs_content_hash",
            free_dofs_content_hash,
            "binding_source_free_dofs_mismatch",
            "Binding identifies another free-equation partition.",
        ),
    )
    for field, expected, code, message in comparisons:
        if binding[field] != expected:
            _fail(
                code,
                f"/extensions/{EQUATION_SCALING_EXTENSION_KEY}/{field}",
                message,
            )


def trace_scaled_residual(
    *,
    execution_plan: ExecutionPlan,
    scaling: EquationScaling,
    raw_residual_si: Any,
    active_equations: Sequence[int] | None = None,
) -> ScaledResidualTrace:
    """Create a non-authoritative dimensional and dimensionless residual trace."""

    plan = validate_execution_plan(execution_plan)
    validate_equation_scaling_binding(plan, scaling=scaling)
    raw = _float_array(
        raw_residual_si, shape=(plan.dof_count,), path="/raw_residual_si"
    )
    active = _active_equations(
        plan.free_dofs if active_equations is None else active_equations,
        plan.dof_count,
    )
    _require_free_equation_scope(active, plan)
    scaled = _immutable_float_array(raw / scaling.scale_divisors_si, "/scaled_residual")
    node_dofs = plan.array("node_dof_indices")
    translation_set = set(int(value) for value in node_dofs[:, :3].reshape(-1))
    rotation_set = set(int(value) for value in node_dofs[:, 3:].reshape(-1))
    translation_values = raw[[index for index in active if index in translation_set]]
    rotation_values = raw[[index for index in active if index in rotation_set]]
    active_scaled = scaled[list(active)]
    governing_position = int(np.argmax(np.abs(active_scaled)))
    governing_equation = active[governing_position]
    node_index, component_index = _equation_location(plan, governing_equation)
    immutable_raw = _immutable_float_array(raw, "/raw_residual_si")
    provisional = ScaledResidualTrace(
        schema_version=SCALED_RESIDUAL_TRACE_SCHEMA_VERSION,
        trace_hash=_HASH_ZERO,
        execution_plan_hash=plan.plan_hash,
        scaling_hash=scaling.scaling_hash,
        residual_sign="internal_minus_external",
        equation_scope=REFERENCE_EQUATION_SCOPE,
        active_equations=active,
        raw_residual_data_hash=array_data_hash(immutable_raw),
        scaled_residual_data_hash=array_data_hash(scaled),
        raw_translation_l2_n=_stable_l2(translation_values),
        raw_translation_linf_n=_linf(translation_values),
        raw_rotation_l2_nm=_stable_l2(rotation_values),
        raw_rotation_linf_nm=_linf(rotation_values),
        scaled_l2=_stable_l2(active_scaled),
        scaled_linf=_linf(active_scaled),
        governing_equation=governing_equation,
        governing_node_id=plan.node_ids[node_index],
        governing_dof=EXECUTION_PLAN_DOF_COMPONENTS[component_index],
        _raw_residual_si=immutable_raw,
        _scaled_residual=scaled,
    )
    trace = replace(
        provisional,
        trace_hash=canonical_hash(
            _trace_payload(provisional, include_trace_hash=False)
        ),
    )
    return validate_scaled_residual_trace(trace, execution_plan=plan, scaling=scaling)


def validate_equation_scaling(
    scaling: EquationScaling,
    *,
    execution_plan: ExecutionPlan | None = None,
    node_coordinates_m: Any | None = None,
    reference_equation_load_si: Any | None = None,
) -> EquationScaling:
    if not isinstance(scaling, EquationScaling):
        _fail("scaling_type_invalid", "/", "Expected EquationScaling.")
    if (node_coordinates_m is None) != (reference_equation_load_si is None):
        _fail(
            "source_commitment_inputs_incomplete",
            "/source_commitment",
            "Coordinates and reference load must be verified together.",
        )
    if node_coordinates_m is not None and execution_plan is None:
        _fail(
            "source_commitment_plan_missing",
            "/source_commitment",
            "Source verification requires the bound base ExecutionPlan.",
        )
    vector = scaling._scale_divisors_si
    _validate_float_contract_array(vector, (scaling.dof_count,), "/scale_divisors_si")
    if np.any(vector <= 0):
        _fail(
            "scale_nonpositive", "/scale_divisors_si", "All divisors must be positive."
        )
    if scaling.scale_vector_data_hash != array_data_hash(vector):
        _fail(
            "scale_vector_hash_mismatch",
            "/scale_vector/data_hash",
            "Raw vector hash is stale.",
        )
    metadata = _vector_metadata(
        "scale_divisors_si", vector, scaling.equation_order_hash
    )
    if scaling.scale_vector_content_hash != array_content_hash(metadata, vector):
        _fail(
            "scale_vector_hash_mismatch",
            "/scale_vector/content_hash",
            "Vector content hash is stale.",
        )
    source_payload = _source_commitment_payload(scaling, include_commitment_hash=False)
    if scaling.source_commitment_hash != canonical_hash(source_payload):
        _fail(
            "source_commitment_hash_mismatch",
            "/source_commitment/commitment_hash",
            "Scaling source commitment is stale.",
        )
    manifest = _scaling_payload(scaling, include_scaling_hash=True)
    validate_equation_scaling_manifest(manifest)
    if scaling.scaling_hash != canonical_hash(
        _scaling_payload(scaling, include_scaling_hash=False)
    ):
        _fail("scaling_hash_mismatch", "/scaling_hash", "Scaling hash is stale.")
    if execution_plan is not None:
        plan = validate_execution_plan(execution_plan)
        if plan.plan_hash != scaling.base_plan_hash:
            _fail(
                "base_plan_hash_mismatch",
                "/base_plan_hash",
                "Scaling was made for another plan.",
            )
        if scaling.equation_order_hash != _equation_order_hash(plan):
            _fail(
                "equation_order_hash_mismatch",
                "/equation_order_hash",
                "Equation order is stale.",
            )
        if scaling.source_model_ir_content_hash != plan.model_ir_content_hash:
            _fail(
                "source_model_ir_mismatch",
                "/source_commitment/model_ir_content_hash",
                "Scaling source identifies another ModelIR.",
            )
        if scaling.source_load_pattern_id != plan.load_pattern_id:
            _fail(
                "source_load_pattern_mismatch",
                "/source_commitment/load_pattern_id",
                "Scaling source identifies another load pattern.",
            )
        if scaling.reference_equation_scope != REFERENCE_EQUATION_SCOPE:
            _fail(
                "reference_equation_scope_mismatch",
                "/source_commitment/reference_equation_scope",
                "Reference force must be derived from free equations.",
            )
        free_dofs_descriptor = next(
            row for row in plan.descriptors if row.name == "free_dofs"
        )
        if scaling.source_free_dofs_content_hash != free_dofs_descriptor.content_hash:
            _fail(
                "source_free_dofs_mismatch",
                "/source_commitment/free_dofs_content_hash",
                "Scaling source identifies another free-equation partition.",
            )
        if scaling.dof_count != plan.dof_count:
            _fail(
                "dof_count_mismatch", "/dof_count", "DOF count differs from the plan."
            )
        if scaling.characteristic_length_m < scaling.minimum_characteristic_length_m:
            _fail(
                "characteristic_length_invalid",
                "/characteristic_length_m",
                "Characteristic length is below its explicit minimum.",
            )
        if scaling.reference_force_n < scaling.minimum_reference_force_n:
            _fail(
                "reference_force_invalid",
                "/reference_force_n",
                "Reference force is below its explicit minimum.",
            )
        node_dofs = plan.array("node_dof_indices")
        expected_divisors = np.empty(plan.dof_count, dtype="<f8")
        expected_divisors[node_dofs[:, :3].reshape(-1)] = scaling.reference_force_n
        expected_divisors[node_dofs[:, 3:].reshape(-1)] = (
            scaling.reference_force_n * scaling.characteristic_length_m
        )
        if not np.array_equal(scaling.scale_divisors_si, expected_divisors):
            _fail(
                "scale_vector_semantics_invalid",
                "/scale_divisors_si",
                "Divisors do not match the force/moment policy.",
            )
        if node_coordinates_m is not None:
            coordinates = _float_array(
                node_coordinates_m,
                shape=(plan.node_count, 3),
                path="/node_coordinates_m",
            )
            loads = _float_array(
                reference_equation_load_si,
                shape=(plan.dof_count,),
                path="/reference_equation_load_si",
            )
            expected_source = _source_commitment_from_arrays(
                plan=plan,
                equation_order_hash=scaling.equation_order_hash,
                node_coordinates_m=coordinates,
                reference_equation_load_si=loads,
            )
            if source_payload != expected_source:
                _fail(
                    "source_commitment_mismatch",
                    "/source_commitment",
                    "Supplied source arrays do not match the committed identities.",
                )
            expected_length = _characteristic_length(
                coordinates, scaling.minimum_characteristic_length_m
            )
            expected_force = _reference_force(
                plan=plan,
                reference_equation_load_si=loads,
                characteristic_length_m=expected_length,
                minimum_reference_force_n=scaling.minimum_reference_force_n,
            )
            if scaling.characteristic_length_m != expected_length:
                _fail(
                    "characteristic_length_mismatch",
                    "/characteristic_length_m",
                    "Characteristic length does not match the committed coordinates.",
                )
            if scaling.reference_force_n != expected_force:
                _fail(
                    "reference_force_mismatch",
                    "/reference_force_n",
                    "Reference force does not match the committed free-equation loads.",
                )
    return scaling


def validate_equation_scaling_manifest(payload: Any) -> Mapping[str, Any]:
    _validate_schema(payload, _equation_scaling_validator(), "equation_scaling")
    if not isinstance(payload, Mapping):  # pragma: no cover
        _fail("scaling_manifest_type_invalid", "/", "Expected an object.")
    dof_count = payload["dof_count"]
    vector_payload = payload["scale_vector"]
    values = _float_array(
        vector_payload["values"],
        shape=(dof_count,),
        path="/scale_vector/values",
    )
    if dof_count % len(EXECUTION_PLAN_DOF_COMPONENTS) != 0:
        _fail(
            "dof_count_invalid",
            "/dof_count",
            "Six-DOF node-major equation order is required.",
        )
    source_payload = payload["source_commitment"]
    expected_source_metadata = {
        "node_coordinates": _source_array_metadata(
            "node_coordinates_m",
            (dof_count // len(EXECUTION_PLAN_DOF_COMPONENTS), 3),
            payload["equation_order_hash"],
        ),
        "reference_equation_load": _source_array_metadata(
            "reference_equation_load_si",
            (dof_count,),
            payload["equation_order_hash"],
        ),
    }
    for descriptor_name, metadata in expected_source_metadata.items():
        descriptor = source_payload[descriptor_name]
        for key, expected in metadata.items():
            if descriptor[key] != expected:
                _fail(
                    "source_commitment_metadata_mismatch",
                    f"/source_commitment/{descriptor_name}/{key}",
                    "Source descriptor metadata is stale.",
                )
    source_without_hash = dict(source_payload)
    claimed_source_hash = source_without_hash.pop("commitment_hash")
    if claimed_source_hash != canonical_hash(source_without_hash):
        _fail(
            "source_commitment_hash_mismatch",
            "/source_commitment/commitment_hash",
            "Scaling source commitment is stale.",
        )
    expected_metadata = _vector_metadata(
        "scale_divisors_si", values, payload["equation_order_hash"]
    )
    for key, expected in expected_metadata.items():
        if vector_payload[key] != expected:
            _fail(
                "scale_vector_metadata_mismatch",
                f"/scale_vector/{key}",
                "Scale vector metadata is stale.",
            )
    if vector_payload["data_hash"] != array_data_hash(values):
        _fail(
            "scale_vector_hash_mismatch",
            "/scale_vector/data_hash",
            "Raw vector hash is stale.",
        )
    if vector_payload["content_hash"] != array_content_hash(expected_metadata, values):
        _fail(
            "scale_vector_hash_mismatch",
            "/scale_vector/content_hash",
            "Vector content hash is stale.",
        )
    characteristic_length = payload["characteristic_length_m"]
    reference_force = payload["reference_force_n"]
    if characteristic_length < payload["minimum_characteristic_length_m"]:
        _fail(
            "characteristic_length_invalid",
            "/characteristic_length_m",
            "Characteristic length is below its explicit minimum.",
        )
    if reference_force < payload["minimum_reference_force_n"]:
        _fail(
            "reference_force_invalid",
            "/reference_force_n",
            "Reference force is below its explicit minimum.",
        )
    expected_values = np.empty(dof_count, dtype="<f8")
    expected_values.reshape(-1, 6)[:, :3] = reference_force
    expected_values.reshape(-1, 6)[:, 3:] = reference_force * characteristic_length
    if not np.array_equal(values, expected_values):
        _fail(
            "scale_vector_semantics_invalid",
            "/scale_vector/values",
            "Divisors do not match the force/moment policy.",
        )
    without_hash = dict(payload)
    claimed = without_hash.pop("scaling_hash")
    if claimed != canonical_hash(without_hash):
        _fail(
            "scaling_hash_mismatch", "/scaling_hash", "Manifest scaling hash is stale."
        )
    return payload


def validate_scaled_residual_trace(
    trace: ScaledResidualTrace,
    *,
    execution_plan: ExecutionPlan | None = None,
    scaling: EquationScaling | None = None,
) -> ScaledResidualTrace:
    if not isinstance(trace, ScaledResidualTrace):
        _fail("trace_type_invalid", "/", "Expected ScaledResidualTrace.")
    raw = trace._raw_residual_si
    scaled = trace._scaled_residual
    _validate_float_contract_array(raw, (raw.size,), "/raw_residual_si")
    _validate_float_contract_array(scaled, raw.shape, "/scaled_residual")
    if trace.raw_residual_data_hash != array_data_hash(raw):
        _fail(
            "residual_hash_mismatch",
            "/vector_hashes/raw",
            "Raw residual hash is stale.",
        )
    if trace.scaled_residual_data_hash != array_data_hash(scaled):
        _fail(
            "residual_hash_mismatch",
            "/vector_hashes/scaled",
            "Scaled residual hash is stale.",
        )
    validate_scaled_residual_trace_manifest(
        _trace_payload(trace, include_trace_hash=True)
    )
    if trace.trace_hash != canonical_hash(
        _trace_payload(trace, include_trace_hash=False)
    ):
        _fail("trace_hash_mismatch", "/trace_hash", "Trace hash is stale.")
    if execution_plan is not None and scaling is not None:
        plan = validate_execution_plan(execution_plan)
        validate_equation_scaling_binding(plan, scaling=scaling)
        if raw.shape != (plan.dof_count,):
            _fail(
                "residual_shape_invalid",
                "/raw_residual_si",
                "Residual does not match plan DOFs.",
            )
        if (
            trace.execution_plan_hash != plan.plan_hash
            or trace.scaling_hash != scaling.scaling_hash
        ):
            _fail("trace_binding_mismatch", "/", "Trace binds different artifacts.")
        if trace.equation_scope != REFERENCE_EQUATION_SCOPE:
            _fail(
                "residual_scope_mismatch",
                "/equation_scope",
                "Only free-equation residual observation is supported.",
            )
        if not np.array_equal(scaled, raw / scaling.scale_divisors_si):
            _fail(
                "scaled_residual_mismatch",
                "/scaled_residual",
                "Scaled values are stale.",
            )
        # Metrics are recomputed directly to avoid recursive validation.
        _validate_trace_semantics(trace, plan)
    return trace


def validate_scaled_residual_trace_manifest(payload: Any) -> Mapping[str, Any]:
    _validate_schema(
        payload, _scaled_residual_trace_validator(), "scaled_residual_trace"
    )
    if not isinstance(payload, Mapping):  # pragma: no cover
        _fail("trace_manifest_type_invalid", "/", "Expected an object.")
    raw = _immutable_float_array(
        payload["vectors"]["raw_residual_si"], "/vectors/raw_residual_si"
    )
    scaled = _immutable_float_array(
        payload["vectors"]["scaled_residual"], "/vectors/scaled_residual"
    )
    if raw.ndim != 1 or raw.shape != scaled.shape:
        _fail(
            "residual_shape_invalid",
            "/vectors",
            "Raw and scaled residuals require the same rank-one shape.",
        )
    active = _active_equations(payload["active_equations"], raw.size)
    if payload["vector_hashes"]["raw"] != array_data_hash(raw):
        _fail(
            "residual_hash_mismatch",
            "/vector_hashes/raw",
            "Raw residual hash is stale.",
        )
    if payload["vector_hashes"]["scaled"] != array_data_hash(scaled):
        _fail(
            "residual_hash_mismatch",
            "/vector_hashes/scaled",
            "Scaled residual hash is stale.",
        )
    translation = [index for index in active if index % 6 < 3]
    rotation = [index for index in active if index % 6 >= 3]
    expected_norms = {
        "raw_translation_l2_n": _stable_l2(raw[translation]),
        "raw_translation_linf_n": _linf(raw[translation]),
        "raw_rotation_l2_nm": _stable_l2(raw[rotation]),
        "raw_rotation_linf_nm": _linf(raw[rotation]),
        "scaled_l2": _stable_l2(scaled[list(active)]),
        "scaled_linf": _linf(scaled[list(active)]),
    }
    if payload["norms"] != expected_norms:
        _fail("trace_metric_mismatch", "/norms", "Residual norms are stale.")
    governing = active[int(np.argmax(np.abs(scaled[list(active)])))]
    if payload["governing"]["equation"] != governing:
        _fail(
            "governing_dof_mismatch",
            "/governing/equation",
            "Governing equation is stale.",
        )
    if payload["governing"]["dof"] != EXECUTION_PLAN_DOF_COMPONENTS[governing % 6]:
        _fail(
            "governing_dof_mismatch",
            "/governing/dof",
            "Governing DOF is stale.",
        )
    without_hash = dict(payload)
    claimed = without_hash.pop("trace_hash")
    if claimed != canonical_hash(without_hash):
        _fail("trace_hash_mismatch", "/trace_hash", "Manifest trace hash is stale.")
    return payload


def _validate_trace_semantics(trace: ScaledResidualTrace, plan: ExecutionPlan) -> None:
    active = _active_equations(trace.active_equations, plan.dof_count)
    _require_free_equation_scope(active, plan)
    raw = trace.raw_residual_si
    scaled = trace.scaled_residual
    # ExecutionPlan v1 validates node-major six-DOF order, so this remains O(N).
    translation = [i for i in active if i % 6 < 3]
    rotation = [i for i in active if i % 6 >= 3]
    metrics = (
        _stable_l2(raw[translation]),
        _linf(raw[translation]),
        _stable_l2(raw[rotation]),
        _linf(raw[rotation]),
        _stable_l2(scaled[list(active)]),
        _linf(scaled[list(active)]),
    )
    claimed = (
        trace.raw_translation_l2_n,
        trace.raw_translation_linf_n,
        trace.raw_rotation_l2_nm,
        trace.raw_rotation_linf_nm,
        trace.scaled_l2,
        trace.scaled_linf,
    )
    if claimed != metrics:
        _fail("trace_metric_mismatch", "/norms", "Residual norms are stale.")
    governing = active[int(np.argmax(np.abs(scaled[list(active)])))]
    node, component = _equation_location(plan, governing)
    if (trace.governing_equation, trace.governing_node_id, trace.governing_dof) != (
        governing,
        plan.node_ids[node],
        EXECUTION_PLAN_DOF_COMPONENTS[component],
    ):
        _fail("governing_dof_mismatch", "/governing", "Governing equation is stale.")


def _scaling_payload(
    scaling: EquationScaling, *, include_scaling_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": scaling.schema_version,
        "base_plan_hash": scaling.base_plan_hash,
        "equation_order_hash": scaling.equation_order_hash,
        "source_commitment": _source_commitment_payload(
            scaling, include_commitment_hash=True
        ),
        "policies": {
            "characteristic_length": scaling.characteristic_length_policy,
            "reference_force": scaling.reference_force_policy,
        },
        "characteristic_length_m": scaling.characteristic_length_m,
        "minimum_characteristic_length_m": scaling.minimum_characteristic_length_m,
        "reference_force_n": scaling.reference_force_n,
        "minimum_reference_force_n": scaling.minimum_reference_force_n,
        "dof_count": scaling.dof_count,
        "scale_vector": {
            **_vector_metadata(
                "scale_divisors_si",
                scaling.scale_divisors_si,
                scaling.equation_order_hash,
            ),
            "data_hash": scaling.scale_vector_data_hash,
            "content_hash": scaling.scale_vector_content_hash,
            "values": scaling.scale_divisors_si.tolist(),
        },
    }
    if include_scaling_hash:
        payload["scaling_hash"] = scaling.scaling_hash
    return payload


def _trace_payload(
    trace: ScaledResidualTrace, *, include_trace_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": trace.schema_version,
        "authority": "non_authoritative_diagnostic",
        "execution_plan_hash": trace.execution_plan_hash,
        "scaling_hash": trace.scaling_hash,
        "residual_sign": trace.residual_sign,
        "equation_scope": trace.equation_scope,
        "active_equations": list(trace.active_equations),
        "vectors": {
            "raw_residual_si": trace.raw_residual_si.tolist(),
            "scaled_residual": trace.scaled_residual.tolist(),
        },
        "vector_hashes": {
            "raw": trace.raw_residual_data_hash,
            "scaled": trace.scaled_residual_data_hash,
        },
        "norms": {
            "raw_translation_l2_n": trace.raw_translation_l2_n,
            "raw_translation_linf_n": trace.raw_translation_linf_n,
            "raw_rotation_l2_nm": trace.raw_rotation_l2_nm,
            "raw_rotation_linf_nm": trace.raw_rotation_linf_nm,
            "scaled_l2": trace.scaled_l2,
            "scaled_linf": trace.scaled_linf,
        },
        "governing": {
            "equation": trace.governing_equation,
            "node_id": trace.governing_node_id,
            "dof": trace.governing_dof,
        },
    }
    if include_trace_hash:
        payload["trace_hash"] = trace.trace_hash
    return payload


def _equation_order_hash(plan: ExecutionPlan) -> str:
    return canonical_hash(
        {
            "node_ids": list(plan.node_ids),
            "dof_components": list(EXECUTION_PLAN_DOF_COMPONENTS),
            "node_dof_indices_data_hash": array_data_hash(
                plan.array("node_dof_indices")
            ),
            "dof_count": plan.dof_count,
        }
    )


def _vector_metadata(
    name: str, array: np.ndarray, equation_order_hash: str
) -> dict[str, Any]:
    return {
        "name": name,
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "layout": "C",
        "byte_length": int(array.nbytes),
        "equation_order_hash": equation_order_hash,
    }


def _source_array_metadata(
    name: str, shape: tuple[int, ...], equation_order_hash: str
) -> dict[str, Any]:
    item_count = math.prod(shape)
    return {
        "name": name,
        "dtype": "<f8",
        "shape": list(shape),
        "layout": "C",
        "byte_length": item_count * np.dtype("<f8").itemsize,
        "equation_order_hash": equation_order_hash,
    }


def _source_commitment_from_arrays(
    *,
    plan: ExecutionPlan,
    equation_order_hash: str,
    node_coordinates_m: np.ndarray,
    reference_equation_load_si: np.ndarray,
) -> dict[str, Any]:
    coordinate_metadata = _source_array_metadata(
        "node_coordinates_m", node_coordinates_m.shape, equation_order_hash
    )
    load_metadata = _source_array_metadata(
        "reference_equation_load_si",
        reference_equation_load_si.shape,
        equation_order_hash,
    )
    return {
        "model_ir_content_hash": plan.model_ir_content_hash,
        "load_pattern_id": plan.load_pattern_id,
        "reference_equation_scope": REFERENCE_EQUATION_SCOPE,
        "free_dofs_content_hash": next(
            row.content_hash for row in plan.descriptors if row.name == "free_dofs"
        ),
        "node_coordinates": {
            **coordinate_metadata,
            "data_hash": array_data_hash(node_coordinates_m),
            "content_hash": array_content_hash(coordinate_metadata, node_coordinates_m),
        },
        "reference_equation_load": {
            **load_metadata,
            "data_hash": array_data_hash(reference_equation_load_si),
            "content_hash": array_content_hash(
                load_metadata, reference_equation_load_si
            ),
        },
    }


def _source_commitment_payload(
    scaling: EquationScaling, *, include_commitment_hash: bool
) -> dict[str, Any]:
    coordinate_metadata = _source_array_metadata(
        "node_coordinates_m",
        (scaling.dof_count // len(EXECUTION_PLAN_DOF_COMPONENTS), 3),
        scaling.equation_order_hash,
    )
    load_metadata = _source_array_metadata(
        "reference_equation_load_si",
        (scaling.dof_count,),
        scaling.equation_order_hash,
    )
    payload: dict[str, Any] = {
        "model_ir_content_hash": scaling.source_model_ir_content_hash,
        "load_pattern_id": scaling.source_load_pattern_id,
        "reference_equation_scope": scaling.reference_equation_scope,
        "free_dofs_content_hash": scaling.source_free_dofs_content_hash,
        "node_coordinates": {
            **coordinate_metadata,
            "data_hash": scaling.source_node_coordinates_data_hash,
            "content_hash": scaling.source_node_coordinates_content_hash,
        },
        "reference_equation_load": {
            **load_metadata,
            "data_hash": scaling.source_reference_load_data_hash,
            "content_hash": scaling.source_reference_load_content_hash,
        },
    }
    if include_commitment_hash:
        payload["commitment_hash"] = scaling.source_commitment_hash
    return payload


def _float_array(value: Any, *, shape: tuple[int, ...], path: str) -> np.ndarray:
    result = _immutable_float_array(value, path)
    if result.shape != shape:
        _fail("array_shape_invalid", path, f"Expected shape {shape}.")
    return result


def _immutable_float_array(value: Any, path: str) -> np.ndarray:
    try:
        object_view = np.asarray(value, dtype=object)
    except (TypeError, ValueError, OverflowError) as exc:
        _fail("array_invalid", path, f"Value cannot be inspected: {exc}")
    if any(isinstance(item, (bool, np.bool_)) for item in object_view.reshape(-1)):
        _fail("array_invalid", path, "Boolean values are not physical numeric inputs.")
    try:
        return immutable_array(value, dtype="<f8")
    except CanonicalContractError as exc:
        _fail("array_invalid", path, str(exc))


def _validate_float_contract_array(
    array: Any, shape: tuple[int, ...], path: str
) -> None:
    if (
        not isinstance(array, np.ndarray)
        or array.dtype.str != "<f8"
        or array.shape != shape
    ):
        _fail("array_contract_invalid", path, "Expected canonical <f8 array and shape.")
    if not array.flags.c_contiguous or not has_immutable_bytes_backing(array):
        _fail("array_mutable", path, "Array requires immutable C-order byte backing.")
    if not np.all(np.isfinite(array)):
        _fail("array_nonfinite", path, "Array values must be finite.")


def _positive_float(value: Any, path: str) -> float:
    if (
        type(value) not in (int, float)
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        _fail(
            "positive_number_required",
            path,
            "Expected a finite number greater than zero.",
        )
    return float(value)


def _active_equations(value: Any, dof_count: int) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _fail(
            "active_equations_invalid",
            "/active_equations",
            "Expected an integer sequence.",
        )
    result = tuple(value)
    if not result:
        _fail(
            "active_equations_invalid",
            "/active_equations",
            "At least one equation is required.",
        )
    if any(type(item) is not int for item in result):
        _fail(
            "active_equations_invalid",
            "/active_equations",
            "Bool and non-integers are forbidden.",
        )
    if result != tuple(sorted(set(result))) or result[0] < 0 or result[-1] >= dof_count:
        _fail(
            "active_equations_invalid",
            "/active_equations",
            "Equations must be sorted, unique, and in range.",
        )
    return result


def _require_free_equation_scope(
    active_equations: tuple[int, ...], plan: ExecutionPlan
) -> None:
    if active_equations != plan.free_dofs:
        _fail(
            "residual_scope_mismatch",
            "/active_equations",
            "Active equations must exactly match ExecutionPlan.free_dofs.",
        )


def _equation_location(plan: ExecutionPlan, equation: int) -> tuple[int, int]:
    matches = np.argwhere(plan.array("node_dof_indices") == equation)
    if matches.shape != (1, 2):  # pragma: no cover - protected by plan validation
        _fail(
            "equation_order_invalid",
            "/equation",
            "Equation is not mapped exactly once.",
        )
    return int(matches[0, 0]), int(matches[0, 1])


def _characteristic_length(
    node_coordinates_m: np.ndarray, minimum_characteristic_length_m: float
) -> float:
    node_count = node_coordinates_m.shape[0]
    try:
        centroid = np.asarray(
            [
                math.fsum(
                    float(node_coordinates_m[row, column]) for row in range(node_count)
                )
                / node_count
                for column in range(3)
            ],
            dtype="<f8",
        )
    except OverflowError:
        _fail(
            "characteristic_length_invalid",
            "/characteristic_length_m",
            "Coordinate accumulation overflowed fp64.",
        )
    max_radius = 0.0
    for row in range(node_count):
        delta = node_coordinates_m[row] - centroid
        radius = math.hypot(float(delta[0]), float(delta[1]), float(delta[2]))
        max_radius = max(max_radius, radius)
    characteristic_length = 2.0 * max_radius
    if (
        not math.isfinite(characteristic_length)
        or characteristic_length < minimum_characteristic_length_m
    ):
        _fail(
            "characteristic_length_invalid",
            "/characteristic_length_m",
            "Model extent is below the explicit characteristic-length minimum.",
        )
    return characteristic_length


def _reference_force(
    *,
    plan: ExecutionPlan,
    reference_equation_load_si: np.ndarray,
    characteristic_length_m: float,
    minimum_reference_force_n: float,
) -> float:
    free_equations = plan.array("free_dofs")
    free_translation_equations = free_equations[free_equations % 6 < 3]
    free_rotation_equations = free_equations[free_equations % 6 >= 3]
    max_translation = _max_abs(reference_equation_load_si[free_translation_equations])
    max_equivalent_moment = (
        _max_abs(reference_equation_load_si[free_rotation_equations])
        / characteristic_length_m
    )
    reference_force = max(
        minimum_reference_force_n, max_translation, max_equivalent_moment
    )
    if not math.isfinite(reference_force):
        _fail(
            "scale_nonfinite",
            "/reference_force_n",
            "Reference-force scale overflowed fp64.",
        )
    return reference_force


def _max_abs(values: np.ndarray) -> float:
    return 0.0 if values.size == 0 else float(np.max(np.abs(values)))


def _linf(values: np.ndarray) -> float:
    return _max_abs(values)


def _stable_l2(values: np.ndarray) -> float:
    scale = 0.0
    sumsq = 1.0
    for item in values:
        absolute = abs(float(item))
        if absolute == 0.0:
            continue
        if scale < absolute:
            sumsq = 1.0 + sumsq * (scale / absolute) ** 2
            scale = absolute
        else:
            sumsq += (absolute / scale) ** 2
    result = 0.0 if scale == 0.0 else scale * math.sqrt(sumsq)
    if not math.isfinite(result):
        _fail("norm_nonfinite", "/norms", "Norm is not representable in fp64.")
    return result


def _validate_schema(
    payload: Any, validator: Draft202012Validator, prefix: str
) -> None:
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: tuple(str(x) for x in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail(f"{prefix}_schema_invalid", path or "/", error.message)


@lru_cache(maxsize=1)
def _equation_scaling_validator() -> Draft202012Validator:
    return _schema_validator("equation_scaling_v1.schema.json")


@lru_cache(maxsize=1)
def _scaled_residual_trace_validator() -> Draft202012Validator:
    return _schema_validator("scaled_residual_trace_v1.schema.json")


def _schema_validator(name: str) -> Draft202012Validator:
    resource = resources.files("structural_analysis.schemas").joinpath(name)
    with resource.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return _StrictDraft202012Validator(schema)


def _fail(code: str, path: str, message: str) -> None:
    raise EquationScalingError(code, path, message)


__all__ = [
    "CHARACTERISTIC_LENGTH_POLICY",
    "EQUATION_SCALING_EXTENSION_KEY",
    "EQUATION_SCALING_SCHEMA_VERSION",
    "REFERENCE_EQUATION_SCOPE",
    "REFERENCE_FORCE_POLICY",
    "SCALED_RESIDUAL_TRACE_SCHEMA_VERSION",
    "EquationScaling",
    "EquationScalingError",
    "ScaledResidualTrace",
    "bind_equation_scaling_to_execution_plan",
    "create_equation_scaling",
    "execution_plan_scaling_hash",
    "trace_scaled_residual",
    "validate_equation_scaling",
    "validate_equation_scaling_binding",
    "validate_equation_scaling_manifest",
    "validate_scaled_residual_trace",
    "validate_scaled_residual_trace_manifest",
]
