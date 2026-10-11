"""Pure request admission for future durable corotational RC execution.

This contract freezes authored inputs without running a numerical solver. A
source revision is a caller declaration, not an execution attestation. Progress
counts control attempts, and successful completion may occur before that cap.
Service admission, reservations, workers and artifact validation remain separate.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import json
import math
import re
from typing import Any, Mapping

from structural_analysis.api.rc_corotational_control_model import (
    compile_rc_corotational_control_model,
)
from structural_analysis.api.strict_json import strict_json_object_bytes
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
    _controlled_free_index,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes
from structural_analysis.model.schema import (
    CANONICAL_MODEL_SCHEMA_VERSION,
    CanonicalModel,
)
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_MATRIX_BACKENDS,
    NewtonRaphsonConfig,
)


RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSION = "structural-analysis-job-request.v6"
RC_COROTATIONAL_JOB_OPERATION = "bounded_rc_corotational_control"
RC_COROTATIONAL_JOB_RESULT_SCHEMA_VERSION = "bounded-rc-corotational-job-result.v1"
RC_COROTATIONAL_JOB_PROFILE = "bounded_rc_corotational_durable_execution.v1"
RC_COROTATIONAL_JOB_REQUEST_MAX_BYTES = 16 * 1024 * 1024
RC_COROTATIONAL_JOB_PROGRESS_UNIT = "control_solver_attempts"

_REQUEST_KEYS = {
    "schema_version",
    "operation",
    "case_id",
    "model",
    "config",
    "source_revision",
    "result_contract",
    "execution_config",
}
_CONFIG_KEYS = {
    "control_node_id",
    "control_component",
    "targets_m",
    "fixed_nodal_loads",
    "config",
    "preload_config",
    "maximum_attempt_count",
    "maximum_subdivision_depth",
    "experimental_pin_roller_beam",
    "experimental_fixed_guided_axial",
}
_MODEL_KEYS = {
    "schema_version",
    "units",
    "coordinate_system",
    "nodes",
    "elements",
    "materials",
    "sections",
    "loads",
    "supports",
    "unsupported_features",
    "warnings",
    "metadata",
}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z")


def rc_corotational_job_canonical_bytes(value: Any) -> bytes:
    """Encode exact JSON types, rejecting aliases such as tuples or integer keys."""
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 64:
            raise ValueError("corotational request JSON nesting exceeds bound")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("corotational request JSON keys must be strings")
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) not in (str, int, float, bool, type(None)):
            raise ValueError("corotational request requires exact JSON values")
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (ValueError, UnicodeError, OverflowError, RecursionError) as exc:
        raise ValueError("invalid corotational request JSON") from exc


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _object(value: Any, keys: set[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"{name} must contain exactly the declared fields")
    return value


def _integer(value: Any, name: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer in [{lower}, {upper}]")
    return value


def _number(value: Any, name: str) -> float:
    if type(value) not in (int, float) or (
        type(value) is int and abs(value) > 2**53 - 1
    ):
        raise ValueError(f"{name} must be a safe finite JSON number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be a safe finite JSON number")
    return normalized


def _solver(value: Any, *, preload: bool):
    cls = (
        NewtonRaphsonConfig
        if preload
        else StatefulCorotationalFiberFrame2DDisplacementControlConfig
    )
    name = "preload_config" if preload else "config.config"
    supplied = dict(_object(value, {field.name for field in fields(cls)}, name))
    iteration = "max_iterations" if preload else "maximum_iterations"
    supplied[iteration] = _integer(supplied[iteration], iteration, 0, 200)
    if type(supplied["matrix_backend"]) is not str:
        raise ValueError(f"{name}.matrix_backend must be a string")
    if preload and supplied["matrix_backend"] not in VECTOR_MATRIX_BACKENDS:
        raise ValueError("unsupported preload matrix backend")
    alphas = supplied["line_search_alphas"]
    if type(alphas) is not list or not 1 <= len(alphas) <= 64:
        raise ValueError("line_search_alphas must contain 1 to 64 JSON numbers")
    supplied["line_search_alphas"] = tuple(
        _number(alpha, "line_search_alpha") for alpha in alphas
    )
    for key in supplied.keys() - {iteration, "matrix_backend", "line_search_alphas"}:
        supplied[key] = _number(supplied[key], f"{name}.{key}")
    return cls(**supplied)


@dataclass(frozen=True)
class RCCorotationalJobControlConfig:
    control_node_id: str
    control_component: str
    targets_m: tuple[float, ...]
    fixed_nodal_loads: tuple[tuple[str, str, float], ...]
    solver_config: StatefulCorotationalFiberFrame2DDisplacementControlConfig
    preload_config: NewtonRaphsonConfig
    maximum_attempt_count: int
    maximum_subdivision_depth: int
    experimental_pin_roller_beam: bool
    experimental_fixed_guided_axial: bool

    def api_kwargs(self) -> dict[str, Any]:
        """Fresh keyword mapping; target history and restart are supplied separately."""
        return {
            "control_node_id": self.control_node_id,
            "control_component": self.control_component,
            "fixed_nodal_loads": self.fixed_nodal_loads,
            "config": self.solver_config,
            "preload_config": self.preload_config,
            "maximum_attempt_count": self.maximum_attempt_count,
            "maximum_subdivision_depth": self.maximum_subdivision_depth,
            "experimental_pin_roller_beam": self.experimental_pin_roller_beam,
            "experimental_fixed_guided_axial": self.experimental_fixed_guided_axial,
        }


@dataclass(frozen=True)
class RCCorotationalJobExecutionConfig:
    attempt_limit_per_call: int
    maximum_api_invocations: int


@dataclass(frozen=True)
class RCCorotationalJobRequest:
    case_id: str
    source_revision: str
    request_bytes: bytes
    model_bytes: bytes
    request_hash: str
    resume_contract_hash: str
    config: RCCorotationalJobControlConfig
    execution_config: RCCorotationalJobExecutionConfig
    source_model_checksum: str
    source_input_checksum: str
    problem_contract_hash: str

    @property
    def model(self) -> CanonicalModel:
        """Return a detached model each time; never expose retained mutable aliases."""
        return load_neutral_json_bytes(self.model_bytes)

    @property
    def targets_m(self) -> tuple[float, ...]:
        return self.config.targets_m

    @property
    def progress_total(self) -> int:
        return self.config.maximum_attempt_count

    @property
    def progress_unit(self) -> str:
        return RC_COROTATIONAL_JOB_PROGRESS_UNIT

    @property
    def source_revision_is_execution_attestation(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return strict_json_object_bytes(
            self.request_bytes,
            maximum_bytes=RC_COROTATIONAL_JOB_REQUEST_MAX_BYTES,
        )

    def api_kwargs(self) -> dict[str, Any]:
        return dict(
            self.config.api_kwargs(),
            attempt_limit_per_call=self.execution_config.attempt_limit_per_call,
        )


def validate_rc_corotational_job_request(
    request: Mapping[str, Any] | bytes,
) -> RCCorotationalJobRequest:
    """Validate supported model semantics and freeze all job inputs without solving."""
    raw = (
        request
        if type(request) is bytes
        else rc_corotational_job_canonical_bytes(request)
    )
    value = strict_json_object_bytes(
        raw,
        maximum_bytes=RC_COROTATIONAL_JOB_REQUEST_MAX_BYTES,
    )
    _object(value, _REQUEST_KEYS, "request")
    if (
        value["schema_version"] != RC_COROTATIONAL_JOB_REQUEST_SCHEMA_VERSION
        or value["operation"] != RC_COROTATIONAL_JOB_OPERATION
        or value["result_contract"] != RC_COROTATIONAL_JOB_RESULT_SCHEMA_VERSION
        or type(value["case_id"]) is not str
        or not _ID.fullmatch(value["case_id"])
        or type(value["source_revision"]) is not str
        or not _REVISION.fullmatch(value["source_revision"])
    ):
        raise ValueError("invalid corotational durable request identity")
    config = _object(value["config"], _CONFIG_KEYS, "config")
    node, component = config["control_node_id"], config["control_component"]
    if type(node) is not str or not _ID.fullmatch(node):
        raise ValueError("control_node_id must name a stable node identifier")
    if type(component) is not str or component not in ("UX", "UY"):
        raise ValueError("control_component must be UX or UY")
    targets = config["targets_m"]
    if type(targets) is not list or not 1 <= len(targets) <= 255:
        raise ValueError("targets_m must contain 1 to 255 JSON numbers")
    normalized_targets = tuple(_number(target, "targets_m") for target in targets)
    if any(a == b for a, b in zip(normalized_targets, normalized_targets[1:])):
        raise ValueError("consecutive control targets must differ")
    fixed = config["fixed_nodal_loads"]
    if type(fixed) is not list or len(fixed) > 48:
        raise ValueError("fixed_nodal_loads must contain at most 48 rows")
    normalized_fixed = []
    for row in fixed:
        if type(row) is not list or len(row) != 3:
            raise ValueError("fixed load must be a [node, component, value] JSON row")
        if type(row[0]) is not str or type(row[1]) is not str:
            raise ValueError("fixed load node and component must be strings")
        normalized_fixed.append((row[0], row[1], _number(row[2], "fixed load")))
    for flag in ("experimental_pin_roller_beam", "experimental_fixed_guided_axial"):
        if type(config[flag]) is not bool:
            raise ValueError(f"{flag} must be an explicit boolean")
    if (
        config["experimental_pin_roller_beam"]
        and config["experimental_fixed_guided_axial"]
    ):
        raise ValueError("support profiles are mutually exclusive")
    control = RCCorotationalJobControlConfig(
        control_node_id=node,
        control_component=component,
        targets_m=normalized_targets,
        fixed_nodal_loads=tuple(normalized_fixed),
        solver_config=_solver(config["config"], preload=False),
        preload_config=_solver(config["preload_config"], preload=True),
        maximum_attempt_count=_integer(
            config["maximum_attempt_count"], "maximum_attempt_count", 1, 4096
        ),
        maximum_subdivision_depth=_integer(
            config["maximum_subdivision_depth"], "maximum_subdivision_depth", 0, 20
        ),
        experimental_pin_roller_beam=config["experimental_pin_roller_beam"],
        experimental_fixed_guided_axial=config["experimental_fixed_guided_axial"],
    )
    execution = _object(
        value["execution_config"],
        {"attempt_limit_per_call", "maximum_api_invocations"},
        "execution_config",
    )
    execution_config = RCCorotationalJobExecutionConfig(
        _integer(
            execution["attempt_limit_per_call"], "attempt_limit_per_call", 1, 4096
        ),
        _integer(
            execution["maximum_api_invocations"], "maximum_api_invocations", 1, 100000
        ),
    )
    model_payload = _object(value["model"], _MODEL_KEYS, "model")
    if model_payload["schema_version"] != CANONICAL_MODEL_SCHEMA_VERSION:
        raise ValueError("invalid canonical model schema")
    _object(model_payload["units"], {"length", "force"}, "model.units")
    _object(
        model_payload["coordinate_system"],
        {"axis_order", "up_axis"},
        "model.coordinate_system",
    )
    if type(model_payload["warnings"]) is not list or any(
        type(warning) is not str for warning in model_payload["warnings"]
    ):
        raise ValueError("model warnings must contain strings")
    model_bytes = rc_corotational_job_canonical_bytes(model_payload)
    model = load_neutral_json_bytes(model_bytes)
    compiled = compile_rc_corotational_control_model(
        model,
        fixed_nodal_loads=control.fixed_nodal_loads,
        experimental_pin_roller_beam=control.experimental_pin_roller_beam,
        experimental_fixed_guided_axial=control.experimental_fixed_guided_axial,
    )
    if node not in compiled.node_ids:
        raise ValueError("unknown control node")
    _controlled_free_index(
        compiled.problem,
        3 * compiled.node_ids.index(node) + (component == "UY"),
    )
    request_bytes = rc_corotational_job_canonical_bytes(value)
    request_hash = _sha(request_bytes)
    return RCCorotationalJobRequest(
        case_id=value["case_id"],
        source_revision=value["source_revision"],
        request_bytes=request_bytes,
        model_bytes=model_bytes,
        request_hash=request_hash,
        resume_contract_hash=_sha(
            rc_corotational_job_canonical_bytes(
                {
                    "profile": RC_COROTATIONAL_JOB_PROFILE,
                    "request_hash": request_hash,
                }
            )
        ),
        config=control,
        execution_config=execution_config,
        source_model_checksum=compiled.source_model_checksum,
        source_input_checksum=compiled.source_input_checksum,
        problem_contract_hash=compiled.problem.contract_hash,
    )
