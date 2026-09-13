"""Strict JSON requests for the existing experimental Frame3D direct control API.

This transport profile does not grant solver, registry, or design authority.
Only the two named factorization policy profiles can cross this boundary.
"""

from __future__ import annotations

import json
import math
from typing import Any, NoReturn

from structural_analysis.api.frame3d_direct_control import (
    BoundedFrame3DDirectControlConfig,
)
from structural_analysis.assembly.stateful_corotational_frame3d_displacement_control import (
    StatefulCorotationalFrame3DDisplacementControlConfig,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    StatefulCorotationalFrame3DSparseConfig,
)
from structural_analysis.solvers.nonlinear.scalable_sparse_factorization import (
    SCALABLE_SPARSE_FACTORIZATION_POLICY_ID,
    ScalableSparseFactorizationPolicy,
)
from structural_analysis.solvers.nonlinear.sparse_factorization import (
    SPARSE_FACTORIZATION_POLICY_ID,
    SparseFactorizationPolicy,
)


BOUNDED_FRAME3D_DIRECT_CONTROL_REQUEST_SCHEMA_VERSION = (
    "bounded-frame3d-direct-control-request.v1"
)
BOUNDED_FRAME3D_DIRECT_CONTROL_REQUEST_MAX_BYTES = 128 * 1024
STRICT_JSON_MAX_DEPTH = 64

_SOLVER_FIELDS = {
    "frame_config": "object",
    "control_relative_tolerance": "number",
    "control_absolute_tolerance_m": "number",
    "control_absolute_tolerance_rad": "number",
    "minimum_control_reference_m": "number",
    "load_factor_increment_tolerance": "number",
    "maximum_iterations": "count",
    "maximum_path_targets": "count",
    "allow_direction_reversal": "boolean",
    "maximum_direction_reversals": "count",
    "adaptive_target_cutback_enabled": "boolean",
    "target_cutback_ratio": "number",
    "maximum_target_cutback_depth": "count",
    "maximum_target_cutback_substeps": "count",
    "maximum_path_solve_attempts": "count",
    "minimum_control_increment_m": "number",
    "minimum_control_increment_rad": "number",
    "line_search_alphas": "array",
}
_FRAME_FIELDS = {
    "residual_relative_tolerance": "number",
    "residual_absolute_tolerance_kn": "number",
    "increment_relative_tolerance": "number",
    "increment_absolute_tolerance_m": "number",
    "maximum_iterations": "count",
    "minimum_characteristic_length_m": "number",
    "minimum_reference_force_kn": "number",
    "line_search_alphas": "array",
    "adaptive_load_cutback_enabled": "boolean",
    "load_cutback_ratio": "number",
    "maximum_load_cutback_depth": "count",
    "maximum_load_cutback_substeps": "count",
    "minimum_load_increment_factor": "number",
    "factorization_policy": "object",
}
_POLICY_FIELDS = {
    "policy_id": "string",
    "maximum_condition_number_1": "number",
    "minimum_normalized_absolute_pivot": "number",
    "maximum_backward_error": "number",
}
_EXACT_POLICY_FIELDS = {
    **_POLICY_FIELDS,
    "maximum_exact_condition_equations": "count",
}
_SCALABLE_POLICY_FIELDS = {
    **_POLICY_FIELDS,
    "maximum_equations": "count",
    "inverse_solve_block_size": "count",
}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON number: {value}")


def strict_json_object_bytes(
    data: bytes,
    *,
    maximum_bytes: int = BOUNDED_FRAME3D_DIRECT_CONTROL_REQUEST_MAX_BYTES,
) -> dict[str, Any]:
    """Decode finite UTF-8 JSON once; reject duplicates, oversize and deep trees.

    This validates JSON transport only. A ModelIR caller must still apply its
    own document contract to the returned object, using these same input bytes.
    """
    if type(data) is not bytes:
        raise ValueError("JSON input must be bytes")
    if type(maximum_bytes) is not int or maximum_bytes < 1:
        raise ValueError("maximum_bytes must be a positive integer")
    if not data or len(data) > maximum_bytes:
        raise ValueError("JSON input is empty or exceeds maximum_bytes")
    try:
        payload = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        if type(payload) is not dict:
            raise ValueError("JSON root must be an object")
        stack = [(payload, 0)]
        while stack:
            item, depth = stack.pop()
            if depth > STRICT_JSON_MAX_DEPTH:
                raise ValueError("JSON nesting exceeds maximum depth")
            if type(item) in (int, float) and not math.isfinite(float(item)):
                raise ValueError("JSON number must be finite")
            if type(item) is str:
                item.encode("utf-8")
            elif type(item) is dict:
                stack.extend((key, depth + 1) for key in item)
                stack.extend((value, depth + 1) for value in item.values())
            elif type(item) is list:
                stack.extend((value, depth + 1) for value in item)
    except (ValueError, UnicodeError, OverflowError, RecursionError) as error:
        raise ValueError(f"invalid JSON object: {error}") from error
    return payload


def _arguments(payload: Any, fields: dict[str, str], path: str) -> dict[str, Any]:
    if type(payload) is not dict:
        raise ValueError(f"{path} must be an object")
    unknown = payload.keys() - fields.keys()
    if unknown:
        raise ValueError(f"{path} has unknown fields: {sorted(unknown)}")
    result = dict(payload)
    types = {
        "number": (int, float),
        "count": (int,),
        "boolean": (bool,),
        "object": (dict,),
        "string": (str,),
        "array": (list,),
    }
    for name, value in payload.items():
        if type(value) not in types[fields[name]]:
            raise ValueError(f"{path}.{name} must be {fields[name]}")
        if fields[name] == "number" and type(value) is int and float(value) != value:
            raise ValueError(f"{path}.{name} cannot be represented exactly as a float")
        if fields[name] == "array":
            if any(type(item) not in (int, float) for item in value):
                raise ValueError(f"{path}.{name} must contain numbers")
            if any(type(item) is int and float(item) != item for item in value):
                raise ValueError(
                    f"{path}.{name} cannot be represented exactly as floats"
                )
            result[name] = tuple(value)
    return result


def _policy(payload: dict[str, Any]):
    policy_id = payload.get("policy_id")
    if type(policy_id) is not str:
        raise ValueError("factorization_policy requires an explicit policy_id")
    if policy_id == SPARSE_FACTORIZATION_POLICY_ID:
        return SparseFactorizationPolicy(
            **_arguments(payload, _EXACT_POLICY_FIELDS, "factorization_policy")
        )
    if policy_id == SCALABLE_SPARSE_FACTORIZATION_POLICY_ID:
        return ScalableSparseFactorizationPolicy(
            **_arguments(payload, _SCALABLE_POLICY_FIELDS, "factorization_policy")
        )
    raise ValueError("factorization_policy.policy_id is unsupported")


def decode_bounded_frame3d_direct_control_request(
    data: bytes,
) -> BoundedFrame3DDirectControlConfig:
    """Restore exact typed solver configuration without executing an analysis."""
    payload = strict_json_object_bytes(data)
    required = {"schema_version", "control_node_id", "control_dof", "control_targets"}
    if not required <= payload.keys() or payload.keys() - required - {"solver_config"}:
        raise ValueError("direct-control request fields do not match v1")
    if (
        payload["schema_version"]
        != BOUNDED_FRAME3D_DIRECT_CONTROL_REQUEST_SCHEMA_VERSION
    ):
        raise ValueError("direct-control request schema_version is unsupported")
    values = _arguments(
        {key: value for key, value in payload.items() if key != "schema_version"},
        {
            "control_node_id": "string",
            "control_dof": "string",
            "control_targets": "array",
            "solver_config": "object",
        },
        "request",
    )
    if "solver_config" in values:
        solver = _arguments(values["solver_config"], _SOLVER_FIELDS, "solver_config")
        if "frame_config" in solver:
            frame = _arguments(solver["frame_config"], _FRAME_FIELDS, "frame_config")
            if "factorization_policy" in frame:
                frame["factorization_policy"] = _policy(frame["factorization_policy"])
            solver["frame_config"] = StatefulCorotationalFrame3DSparseConfig(**frame)
        values["solver_config"] = StatefulCorotationalFrame3DDisplacementControlConfig(
            **solver
        )
    return BoundedFrame3DDirectControlConfig(**values)


def _constructor_payload(config: Any, fields: dict[str, str]) -> dict[str, Any]:
    return {
        name: list(value) if type(value := getattr(config, name)) is tuple else value
        for name in fields
    }


def bounded_frame3d_direct_control_request_payload(
    config: BoundedFrame3DDirectControlConfig,
) -> dict[str, Any]:
    """Export every constructor knob, preserving request and resume identities."""
    if type(config) is not BoundedFrame3DDirectControlConfig:
        raise ValueError("config must be an exact BoundedFrame3DDirectControlConfig")
    solver = config.solver_config
    frame = solver.frame_config
    policy = frame.factorization_policy
    if type(policy) is SparseFactorizationPolicy:
        policy_fields = _EXACT_POLICY_FIELDS
    elif type(policy) is ScalableSparseFactorizationPolicy:
        policy_fields = _SCALABLE_POLICY_FIELDS
    else:
        raise ValueError("factorization_policy must be an exact supported policy")
    solver_payload = _constructor_payload(solver, _SOLVER_FIELDS)
    frame_payload = _constructor_payload(frame, _FRAME_FIELDS)
    frame_payload["factorization_policy"] = _constructor_payload(policy, policy_fields)
    solver_payload["frame_config"] = frame_payload
    payload = {
        "schema_version": BOUNDED_FRAME3D_DIRECT_CONTROL_REQUEST_SCHEMA_VERSION,
        "control_node_id": config.control_node_id,
        "control_dof": config.control_dof,
        "control_targets": list(config.control_targets),
        "solver_config": solver_payload,
    }
    # Keep exports inside this profile too (including size and known policy ID).
    try:
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        restored = decode_bounded_frame3d_direct_control_request(raw)
        if (
            restored.request_hash != config.request_hash
            or restored.resume_contract_hash != config.resume_contract_hash
        ):
            raise ValueError("serialized request changed the typed contract")
    except (ValueError, UnicodeError, OverflowError, TypeError) as error:
        raise ValueError(
            f"config cannot be serialized as a v1 request: {error}"
        ) from error
    return payload


__all__ = [
    "BOUNDED_FRAME3D_DIRECT_CONTROL_REQUEST_MAX_BYTES",
    "BOUNDED_FRAME3D_DIRECT_CONTROL_REQUEST_SCHEMA_VERSION",
    "bounded_frame3d_direct_control_request_payload",
    "decode_bounded_frame3d_direct_control_request",
    "strict_json_object_bytes",
]
