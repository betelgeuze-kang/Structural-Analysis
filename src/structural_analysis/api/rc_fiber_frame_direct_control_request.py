"""Strict opt-in request transport for the experimental small-displacement RC path."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from typing import Any

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig,
)
from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

REQUEST_SCHEMA_VERSION = "bounded-rc-fiber-direct-control-request.v1"
CONSTANT_REQUEST_SCHEMA_VERSION = "bounded-rc-fiber-direct-control-request.v2"
REQUEST_MAX_BYTES = 128 * 1024
_NEWTON_FIELDS = {
    "residual_tolerance",
    "increment_tolerance",
    "max_iterations",
    "line_search_alphas",
    "matrix_backend",
    "terminal_polishing",
}
_SOLVER_FIELDS = {"newton", "control_tolerance_m", "load_factor_coordinate_scale_m"}
_REQUEST_FIELDS = {
    "schema_version",
    "control_global_dof",
    "targets_m",
    "solver_config",
    "allow_reversals",
    "maximum_reversals",
    "maximum_targets",
}


def _json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_json(value)).hexdigest()


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _number(value, name):
    if type(value) not in (int, float) or (
        type(value) is int and abs(value) > 2**53 - 1
    ):
        raise ValueError(f"{name} must be a safe finite JSON number")
    try:
        normalized = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be finite") from error
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _object(value, allowed, name):
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise ValueError(f"{name} must be a JSON object with string keys")
    if value.keys() - allowed:
        raise ValueError(f"{name} has unknown fields")
    return value


def _solver(payload):
    values = dict(_object(payload, _SOLVER_FIELDS, "solver_config"))
    if "newton" in values:
        newton = dict(_object(values["newton"], _NEWTON_FIELDS, "solver_config.newton"))
        for key in ("residual_tolerance", "increment_tolerance"):
            if key in newton:
                newton[key] = _number(newton[key], key)
        if "max_iterations" in newton:
            _integer(newton["max_iterations"], "max_iterations", 0, 200)
        if (
            "terminal_polishing" in newton
            and type(newton["terminal_polishing"]) is not bool
        ):
            raise ValueError("terminal_polishing must be a boolean")
        if "matrix_backend" in newton and type(newton["matrix_backend"]) is not str:
            raise ValueError("matrix_backend must be a string")
        if "line_search_alphas" in newton:
            if type(newton["line_search_alphas"]) is not list:
                raise ValueError("line_search_alphas must be a JSON array")
            newton["line_search_alphas"] = tuple(
                _number(value, "line_search_alphas")
                for value in newton["line_search_alphas"]
            )
        values["newton"] = NewtonRaphsonConfig(**newton)
    for key in ("control_tolerance_m", "load_factor_coordinate_scale_m"):
        if key in values:
            values[key] = _number(values[key], key)
    return StatefulFiberFrame2DDisplacementControlConfig(**values)


def _constant_loads(rows):
    """Snapshot explicit node/FX/FY/MZ rows in kN and kN m; never infer units."""
    if type(rows) is not tuple or len(rows) > 16:
        raise ValueError("constant_nodal_loads must be a tuple of at most 16 rows")
    result = []
    seen = set()
    for row in rows:
        if type(row) is not tuple or len(row) != 4:
            raise ValueError(
                "constant load row must be (node_id, FX_kN, FY_kN, MZ_kNm)"
            )
        node = row[0]
        if type(node) is not str or not node or len(node) > 128 or node in seen:
            raise ValueError("constant load node must be a unique nonempty node ID")
        values = tuple(_number(value, "constant_nodal_loads") for value in row[1:])
        if not any(values):
            raise ValueError("constant load row must have a nonzero component")
        result.append((node, *values))
        seen.add(node)
    return tuple(sorted(result))


def _constant_load_payload(rows):
    return [
        dict(zip(("node_id", "FX_kN", "FY_kN", "MZ_kNm"), row, strict=True))
        for row in rows
    ]


def _decode_constant_loads(rows):
    if type(rows) is not list:
        raise ValueError("constant_nodal_loads must be a JSON array")
    keys = ("node_id", "FX_kN", "FY_kN", "MZ_kNm")
    if any(type(row) is not dict or set(row) != set(keys) for row in rows):
        raise ValueError("constant load row must declare node_id, FX_kN, FY_kN, MZ_kNm")
    return _constant_loads(tuple(tuple(row[key] for key in keys) for row in rows))


@dataclass(frozen=True)
class BoundedRCFiberDirectControlRequest:
    control_global_dof: int
    targets_m: tuple[float, ...]
    solver_config: StatefulFiberFrame2DDisplacementControlConfig = field(
        default_factory=StatefulFiberFrame2DDisplacementControlConfig
    )
    allow_reversals: bool = False
    maximum_reversals: int = 0
    maximum_targets: int = 255
    constant_nodal_loads: tuple[tuple[str, float, float, float], ...] = ()

    def __post_init__(self):
        object.__setattr__(
            self, "constant_nodal_loads", _constant_loads(self.constant_nodal_loads)
        )
        _integer(self.control_global_dof, "control_global_dof", 0, 47)
        if self.control_global_dof % 3 not in (0, 1):
            raise ValueError("control_global_dof must name a translational UX/UY DOF")
        _integer(self.maximum_targets, "maximum_targets", 1, 255)
        _integer(self.maximum_reversals, "maximum_reversals", 0, 254)
        if type(self.allow_reversals) is not bool or (
            not self.allow_reversals and self.maximum_reversals != 0
        ):
            raise ValueError("reversals require explicit boolean opt-in and budget")
        if (
            type(self.solver_config)
            is not StatefulFiberFrame2DDisplacementControlConfig
        ):
            raise ValueError("solver_config must be the exact RC control config")
        # Reconstruct all knobs so even a tampered typed object cannot cross transport.
        restored = _solver(
            asdict(self.solver_config)
            | {
                "newton": asdict(self.solver_config.newton)
                | {
                    "line_search_alphas": list(
                        self.solver_config.newton.line_search_alphas
                    )
                }
            }
        )
        if _json(restored.to_manifest()) != _json(self.solver_config.to_manifest()):
            raise ValueError("solver configuration roundtrip mismatch")
        if (
            type(self.targets_m) is not tuple
            or len(self.targets_m) > self.maximum_targets
        ):
            raise ValueError("targets_m must be a bounded tuple")
        targets = tuple(_number(value, "targets_m") for value in self.targets_m)
        if any(left == right for left, right in zip(targets, targets[1:])):
            raise ValueError("successive targets must differ")
        directions = [
            1 if right > left else -1 for left, right in zip(targets, targets[1:])
        ]
        if (
            sum(a != b for a, b in zip(directions, directions[1:]))
            > self.maximum_reversals
        ):
            raise ValueError("declared suffix already exceeds the reversal budget")
        object.__setattr__(self, "targets_m", targets)

    def api_kwargs(self) -> dict[str, Any]:
        return {
            "control_global_dof": self.control_global_dof,
            "config": self.solver_config,
            **(
                {"constant_nodal_loads": self.constant_nodal_loads}
                if self.constant_nodal_loads
                else {}
            ),
            "allow_reversals": self.allow_reversals,
            "maximum_reversals": self.maximum_reversals,
            "maximum_targets": self.maximum_targets,
        }

    def to_dict(self) -> dict[str, Any]:
        solver = asdict(self.solver_config)
        solver["newton"]["line_search_alphas"] = list(
            self.solver_config.newton.line_search_alphas
        )
        return {
            "schema_version": (
                CONSTANT_REQUEST_SCHEMA_VERSION
                if self.constant_nodal_loads
                else REQUEST_SCHEMA_VERSION
            ),
            **(
                {
                    "constant_nodal_loads": _constant_load_payload(
                        self.constant_nodal_loads
                    )
                }
                if self.constant_nodal_loads
                else {}
            ),
            "control_global_dof": self.control_global_dof,
            "targets_m": list(self.targets_m),
            "solver_config": solver,
            "allow_reversals": self.allow_reversals,
            "maximum_reversals": self.maximum_reversals,
            "maximum_targets": self.maximum_targets,
        }

    @property
    def request_hash(self):
        return _hash(self.to_dict())

    @property
    def resume_contract_hash(self):
        return _hash(
            {key: value for key, value in self.to_dict().items() if key != "targets_m"}
        )


def decode_bounded_rc_fiber_direct_control_request(
    data: bytes | dict[str, Any],
) -> BoundedRCFiberDirectControlRequest:
    """Decode without analysis; prefix-dependent checks remain with the core path."""
    if type(data) is dict:
        # Reject non-JSON mapping values before json.dumps could coerce their keys.
        pending = [(data, 0)]
        visited = 0
        while pending:
            visited += 1
            if visited + len(pending) > REQUEST_MAX_BYTES:
                raise ValueError("request mapping exceeds bounded JSON node count")
            value, depth = pending.pop()
            if depth > 64:
                raise ValueError("request exceeds maximum depth")
            if type(value) is dict:
                if any(type(key) is not str for key in value):
                    raise ValueError("request mapping keys must be strings")
                pending.extend((item, depth + 1) for item in value.values())
            elif type(value) is list:
                pending.extend((item, depth + 1) for item in value)
            elif type(value) is str and len(value) > REQUEST_MAX_BYTES:
                raise ValueError("request string exceeds byte budget")
            elif type(value) not in (str, bool, int, float, type(None)):
                raise ValueError("request mapping must contain only JSON values")
        try:
            data = _json(data)
        except (ValueError, UnicodeError, OverflowError, RecursionError) as error:
            raise ValueError(f"invalid request mapping: {error}") from error
    if not isinstance(data, bytes):
        raise ValueError("request must be JSON bytes or a JSON object")
    payload = strict_json_object_bytes(data, maximum_bytes=REQUEST_MAX_BYTES)
    constant = payload.get("schema_version") == CONSTANT_REQUEST_SCHEMA_VERSION
    _object(
        payload,
        _REQUEST_FIELDS | ({"constant_nodal_loads"} if constant else set()),
        "request",
    )
    if not {"schema_version", "control_global_dof", "targets_m"} <= payload.keys():
        raise ValueError("request is missing required fields")
    if payload["schema_version"] not in (
        REQUEST_SCHEMA_VERSION,
        CONSTANT_REQUEST_SCHEMA_VERSION,
    ):
        raise ValueError("request schema_version is unsupported")
    if type(payload["targets_m"]) is not list:
        raise ValueError("targets_m must be a JSON array")
    values = {key: value for key, value in payload.items() if key != "schema_version"}
    if constant:
        values["constant_nodal_loads"] = _decode_constant_loads(
            values.get("constant_nodal_loads")
        )
        if not values["constant_nodal_loads"]:
            raise ValueError("v2 requires a nonempty constant load pattern")
    values["targets_m"] = tuple(values["targets_m"])
    if "solver_config" in values:
        values["solver_config"] = _solver(values["solver_config"])
    return BoundedRCFiberDirectControlRequest(**values)


def bounded_rc_fiber_direct_control_request_payload(
    request: BoundedRCFiberDirectControlRequest,
) -> dict[str, Any]:
    if type(request) is not BoundedRCFiberDirectControlRequest:
        raise ValueError("request must be an exact BoundedRCFiberDirectControlRequest")
    payload = request.to_dict()
    restored = decode_bounded_rc_fiber_direct_control_request(payload)
    if restored != request or restored.request_hash != request.request_hash:
        raise ValueError("request serialization changed its typed identity")
    return payload
