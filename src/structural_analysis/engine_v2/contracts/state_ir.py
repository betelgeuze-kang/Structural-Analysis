"""Immutable StateIR v1 snapshots and trial/commit/rollback lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Literal

import numpy as np
from jsonschema import Draft202012Validator, validators

from structural_analysis.engine_v2.contracts._canonical import (
    CanonicalContractError,
    array_data_hash,
    canonical_hash,
    canonical_json_bytes,
    has_immutable_bytes_backing,
    immutable_array,
)

STATE_IR_SCHEMA_VERSION = "structural-analysis-state-ir.v1"
STATE_IR_DOF_COMPONENTS = ("UX", "UY", "UZ", "RX", "RY", "RZ")
STATE_IR_DISPLACEMENT_UNITS = ("m", "m", "m", "rad", "rad", "rad")
STATE_IR_VELOCITY_UNITS = (
    "m/s",
    "m/s",
    "m/s",
    "rad/s",
    "rad/s",
    "rad/s",
)
STATE_IR_ACCELERATION_UNITS = (
    "m/s2",
    "m/s2",
    "m/s2",
    "rad/s2",
    "rad/s2",
    "rad/s2",
)
STATE_IR_CONSTITUTIVE_MODE = "stateless_linear_elastic"

_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_EXTENSION_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*:[A-Za-z0-9_.-]+$")
_MAX_INDEX = np.iinfo(np.int32).max
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator, type_checker=_STRICT_JSON_TYPE_CHECKER
)
_CONSTITUTIVE_VALUES = immutable_array([], dtype="<f8")
_CONSTITUTIVE_HASH = array_data_hash(_CONSTITUTIVE_VALUES)


class StateIRError(ValueError):
    """Fail-closed StateIR contract or lifecycle violation."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class StateStep:
    load_step: int
    iteration: int


@dataclass(frozen=True)
class StateIR:
    """One immutable committed or trial state snapshot.

    Arrays are flat, node-major global-DOF vectors.  They use exact ``<f8``
    storage and are ultimately backed by immutable ``bytes``.
    """

    schema_version: str
    state_id: str
    model_ir_content_hash: str
    solver_numeric_buffer_hash: str
    solver_entity_mapping_hash: str
    solver_artifact_hash: str
    execution_plan_hash: str
    operator_hash: str
    load_pattern_id: str
    role: Literal["committed", "trial"]
    epoch: int
    parent_state_hash: str | None
    step: StateStep
    load_factor: float
    time_s: float
    dof_count: int
    displacement_si: np.ndarray
    velocity_si: np.ndarray
    acceleration_si: np.ndarray
    vector_hashes: Mapping[str, str]
    state_hash: str
    extensions: Mapping[str, Any]

    @property
    def load_step(self) -> int:
        return self.step.load_step

    @property
    def iteration(self) -> int:
        return self.step.iteration

    @property
    def solver_buffer_hash(self) -> str:
        """Compatibility alias for the aggregate solver-buffer artifact hash."""

        return self.solver_artifact_hash

    def to_dict(self) -> dict[str, Any]:
        """Return a schema-shaped JSON value after full semantic validation."""

        validate_state_ir(self)
        return _state_payload(self, include_state_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        """Alias for consumers that call contract receipts manifests."""

        return self.to_dict()


def create_initial_state(
    plan: Any,
    *,
    state_id: str = "state.committed.e0.s0.i0",
) -> StateIR:
    """Create the unique zero-valued committed epoch-0 state for a plan."""

    bindings = _plan_bindings(plan)
    zero = np.zeros(bindings["dof_count"], dtype="<f8")
    return _build_state(
        state_id=state_id,
        **bindings,
        role="committed",
        epoch=0,
        parent_state_hash=None,
        load_step=0,
        iteration=0,
        load_factor=0.0,
        time_s=0.0,
        displacement_si=zero,
        velocity_si=zero,
        acceleration_si=zero,
    )


def open_trial_state(
    accepted: StateIR,
    displacement_si: Any,
    *,
    velocity_si: Any | None = None,
    acceleration_si: Any | None = None,
    load_step: int | None = None,
    iteration: int = 0,
    load_factor: float = 1.0,
    time_s: float | None = None,
    state_id: str | None = None,
    expected_plan: Any | None = None,
) -> StateIR:
    """Open a prospective epoch without mutating the accepted state."""

    validate_state_ir(accepted, expected_plan=expected_plan)
    if accepted.role != "committed":
        raise StateIRError(
            "accepted_state_role_invalid",
            "/role",
            "A trial can only be opened from a committed state.",
        )
    next_epoch = accepted.epoch + 1
    next_load_step = accepted.load_step + 1 if load_step is None else load_step
    next_time = accepted.time_s if time_s is None else time_s
    trial_id = state_id or (f"state.trial.e{next_epoch}.s{next_load_step}.i{iteration}")
    return _build_state(
        state_id=trial_id,
        model_ir_content_hash=accepted.model_ir_content_hash,
        solver_numeric_buffer_hash=accepted.solver_numeric_buffer_hash,
        solver_entity_mapping_hash=accepted.solver_entity_mapping_hash,
        solver_artifact_hash=accepted.solver_artifact_hash,
        execution_plan_hash=accepted.execution_plan_hash,
        operator_hash=accepted.operator_hash,
        load_pattern_id=accepted.load_pattern_id,
        dof_count=accepted.dof_count,
        role="trial",
        epoch=next_epoch,
        parent_state_hash=accepted.state_hash,
        load_step=next_load_step,
        iteration=iteration,
        load_factor=load_factor,
        time_s=next_time,
        displacement_si=displacement_si,
        velocity_si=accepted.velocity_si if velocity_si is None else velocity_si,
        acceleration_si=(
            accepted.acceleration_si if acceleration_si is None else acceleration_si
        ),
    )


def commit_trial_state(
    accepted: StateIR,
    trial: StateIR,
    *,
    state_id: str | None = None,
    expected_plan: Any | None = None,
) -> StateIR:
    """Atomically materialize a validated trial as a new committed snapshot."""

    _validate_trial_transition(accepted, trial, expected_plan=expected_plan)
    committed_id = state_id or (
        f"state.committed.e{trial.epoch}.s{trial.load_step}.i{trial.iteration}"
    )
    return _build_state(
        state_id=committed_id,
        model_ir_content_hash=trial.model_ir_content_hash,
        solver_numeric_buffer_hash=trial.solver_numeric_buffer_hash,
        solver_entity_mapping_hash=trial.solver_entity_mapping_hash,
        solver_artifact_hash=trial.solver_artifact_hash,
        execution_plan_hash=trial.execution_plan_hash,
        operator_hash=trial.operator_hash,
        load_pattern_id=trial.load_pattern_id,
        dof_count=trial.dof_count,
        role="committed",
        epoch=trial.epoch,
        parent_state_hash=trial.state_hash,
        load_step=trial.load_step,
        iteration=trial.iteration,
        load_factor=trial.load_factor,
        time_s=trial.time_s,
        displacement_si=trial.displacement_si,
        velocity_si=trial.velocity_si,
        acceleration_si=trial.acceleration_si,
    )


def rollback_trial_state(
    accepted: StateIR,
    trial: StateIR,
    *,
    expected_plan: Any | None = None,
) -> StateIR:
    """Reject a trial and return the exact original accepted object."""

    _validate_trial_transition(accepted, trial, expected_plan=expected_plan)
    return accepted


def validate_state_ir(
    state: StateIR,
    *,
    expected_plan: Any | None = None,
) -> StateIR:
    """Recompute all StateIR invariants and reject stale or forged receipts."""

    if not isinstance(state, StateIR):
        raise StateIRError("state_type_invalid", "/", "Expected a StateIR instance.")
    if state.schema_version != STATE_IR_SCHEMA_VERSION:
        raise StateIRError(
            "schema_version_invalid", "/schema_version", "Unsupported StateIR schema."
        )
    _require_stable_id(state.state_id, "/state_id")
    _require_stable_id(state.load_pattern_id, "/load_pattern_id")
    for path, value in (
        ("/model_ir_content_hash", state.model_ir_content_hash),
        ("/solver_numeric_buffer_hash", state.solver_numeric_buffer_hash),
        ("/solver_entity_mapping_hash", state.solver_entity_mapping_hash),
        ("/solver_artifact_hash", state.solver_artifact_hash),
        ("/execution_plan_hash", state.execution_plan_hash),
        ("/operator_hash", state.operator_hash),
        ("/state_hash", state.state_hash),
    ):
        _require_hash(value, path)
    if state.parent_state_hash is not None:
        _require_hash(state.parent_state_hash, "/parent_state_hash")
        if state.parent_state_hash == state.state_hash:
            raise StateIRError(
                "state_parent_cycle",
                "/parent_state_hash",
                "State cannot parent itself.",
            )
    if state.role not in ("committed", "trial"):
        raise StateIRError("state_role_invalid", "/role", "Unknown StateIR role.")
    epoch = _require_index(state.epoch, "/epoch")
    if not isinstance(state.step, StateStep):
        raise StateIRError("state_step_invalid", "/step", "Expected a StateStep.")
    load_step = _require_index(state.load_step, "/step/load_step")
    _require_index(state.iteration, "/step/iteration")
    dof_count = _require_index(state.dof_count, "/dof_count", minimum=1)
    if dof_count % len(STATE_IR_DOF_COMPONENTS) != 0:
        raise StateIRError(
            "dof_count_invalid",
            "/dof_count",
            "Global DOF count must be divisible by six.",
        )
    load_factor = _require_finite(state.load_factor, "/load_factor")
    time_s = _require_finite(state.time_s, "/time_s")
    if time_s < 0.0:
        raise StateIRError("time_invalid", "/time_s", "Time cannot be negative.")

    if epoch == 0:
        if state.role != "committed" or state.parent_state_hash is not None:
            raise StateIRError(
                "initial_state_lineage_invalid",
                "/parent_state_hash",
                "Epoch zero must be an unparented committed state.",
            )
        if (
            load_step != 0
            or state.iteration != 0
            or load_factor != 0.0
            or time_s != 0.0
        ):
            raise StateIRError(
                "initial_state_coordinates_invalid",
                "/step",
                "Epoch zero must use zero step, iteration, factor, and time.",
            )
    elif state.parent_state_hash is None:
        raise StateIRError(
            "state_parent_missing",
            "/parent_state_hash",
            "Every non-initial state must identify its parent snapshot.",
        )
    if state.role == "trial" and epoch == 0:
        raise StateIRError(
            "trial_epoch_invalid", "/epoch", "A trial epoch must be positive."
        )

    arrays = {
        "displacement": state.displacement_si,
        "velocity": state.velocity_si,
        "acceleration": state.acceleration_si,
    }
    for name, array in arrays.items():
        _validate_vector(array, dof_count, f"/kinematics/{name}_si")
    if epoch == 0 and any(np.any(array != 0.0) for array in arrays.values()):
        raise StateIRError(
            "initial_state_nonzero",
            "/kinematics",
            "The initial linear-static state must contain zero vectors.",
        )

    if not isinstance(state.vector_hashes, MappingProxyType):
        raise StateIRError(
            "vector_hashes_mutable",
            "/vector_hashes",
            "Vector hashes must use an immutable mapping.",
        )
    expected_vector_hashes = {
        name: array_data_hash(array) for name, array in arrays.items()
    }
    expected_vector_hashes["constitutive"] = _CONSTITUTIVE_HASH
    if set(state.vector_hashes) != set(expected_vector_hashes):
        raise StateIRError(
            "vector_hash_keys_invalid",
            "/vector_hashes",
            "StateIR requires exactly four vector hashes.",
        )
    for name, expected_hash in expected_vector_hashes.items():
        claimed_hash = state.vector_hashes[name]
        _require_hash(claimed_hash, f"/vector_hashes/{name}")
        if claimed_hash != expected_hash:
            raise StateIRError(
                "vector_hash_mismatch",
                f"/vector_hashes/{name}",
                "Claimed vector hash does not match immutable FP64 bytes.",
            )

    _validate_extensions(state.extensions)
    expected_state_hash = canonical_hash(
        _state_payload(state, include_state_hash=False)
    )
    if state.state_hash != expected_state_hash:
        raise StateIRError(
            "state_hash_mismatch",
            "/state_hash",
            "Claimed state hash does not match the canonical state payload.",
        )
    validate_state_ir_manifest(_state_payload(state, include_state_hash=True))
    if expected_plan is not None:
        expected = _plan_bindings(expected_plan)
        actual = {
            "model_ir_content_hash": state.model_ir_content_hash,
            "solver_numeric_buffer_hash": state.solver_numeric_buffer_hash,
            "solver_entity_mapping_hash": state.solver_entity_mapping_hash,
            "solver_artifact_hash": state.solver_artifact_hash,
            "execution_plan_hash": state.execution_plan_hash,
            "operator_hash": state.operator_hash,
            "load_pattern_id": state.load_pattern_id,
            "dof_count": state.dof_count,
        }
        if actual != expected:
            raise StateIRError(
                "state_plan_binding_mismatch",
                "/execution_plan_hash",
                "StateIR bindings are stale for the expected execution plan.",
            )
    return state


def validate_state_ir_manifest(payload: Any) -> Mapping[str, Any]:
    """Reject malformed lifecycle semantics, vector receipts, and stale hashes."""

    errors = sorted(
        _state_schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        raise StateIRError("state_schema_invalid", path or "/", error.message)
    if not isinstance(payload, Mapping):  # pragma: no cover - schema invariant
        raise StateIRError("state_manifest_type_invalid", "/", "Expected an object.")
    _validate_state_ir_manifest_semantics(payload)
    without_hash = dict(payload)
    claimed_hash = without_hash.pop("state_hash")
    try:
        expected_hash = canonical_hash(without_hash)
    except CanonicalContractError as exc:
        raise StateIRError("state_manifest_invalid", "/", str(exc)) from exc
    if claimed_hash != expected_hash:
        raise StateIRError(
            "state_hash_mismatch",
            "/state_hash",
            "Manifest state hash does not match its canonical payload.",
        )
    return payload


def _validate_state_ir_manifest_semantics(payload: Mapping[str, Any]) -> None:
    role = str(payload["role"])
    epoch = int(payload["epoch"])
    parent_state_hash = payload["parent_state_hash"]
    load_step = int(payload["step"]["load_step"])
    iteration = int(payload["step"]["iteration"])
    load_factor = _require_finite(payload["load_factor"], "/load_factor")
    time_s = _require_finite(payload["time_s"], "/time_s")
    dof_count = int(payload["dof_count"])

    if dof_count % len(STATE_IR_DOF_COMPONENTS) != 0:
        raise StateIRError(
            "dof_count_invalid",
            "/dof_count",
            "Global DOF count must be divisible by six.",
        )
    if parent_state_hash == payload["state_hash"]:
        raise StateIRError(
            "state_parent_cycle",
            "/parent_state_hash",
            "State cannot parent itself.",
        )
    if epoch == 0:
        if role != "committed" or parent_state_hash is not None:
            raise StateIRError(
                "initial_state_lineage_invalid",
                "/parent_state_hash",
                "Epoch zero must be an unparented committed state.",
            )
        if load_step != 0 or iteration != 0 or load_factor != 0.0 or time_s != 0.0:
            raise StateIRError(
                "initial_state_coordinates_invalid",
                "/step",
                "Epoch zero must use zero step, iteration, factor, and time.",
            )
    elif parent_state_hash is None:
        raise StateIRError(
            "state_parent_missing",
            "/parent_state_hash",
            "Every non-initial state must identify its parent snapshot.",
        )
    if role == "trial" and epoch == 0:
        raise StateIRError(
            "trial_epoch_invalid", "/epoch", "A trial epoch must be positive."
        )

    kinematics = payload["kinematics"]
    arrays = {
        "displacement": _immutable_f64_vector(
            kinematics["displacement_si"],
            dof_count,
            "/kinematics/displacement_si",
        ),
        "velocity": _immutable_f64_vector(
            kinematics["velocity_si"], dof_count, "/kinematics/velocity_si"
        ),
        "acceleration": _immutable_f64_vector(
            kinematics["acceleration_si"],
            dof_count,
            "/kinematics/acceleration_si",
        ),
    }
    if epoch == 0 and any(np.any(array != 0.0) for array in arrays.values()):
        raise StateIRError(
            "initial_state_nonzero",
            "/kinematics",
            "The initial linear-static state must contain zero vectors.",
        )

    expected_vector_hashes = {
        name: array_data_hash(array) for name, array in arrays.items()
    }
    expected_vector_hashes["constitutive"] = _CONSTITUTIVE_HASH
    for name, expected_hash in expected_vector_hashes.items():
        if payload["vector_hashes"][name] != expected_hash:
            raise StateIRError(
                "vector_hash_mismatch",
                f"/vector_hashes/{name}",
                "Claimed vector hash does not match canonical FP64 bytes.",
            )


def _build_state(
    *,
    state_id: str,
    model_ir_content_hash: str,
    solver_numeric_buffer_hash: str,
    solver_entity_mapping_hash: str,
    solver_artifact_hash: str,
    execution_plan_hash: str,
    operator_hash: str,
    load_pattern_id: str,
    dof_count: int,
    role: Literal["committed", "trial"],
    epoch: int,
    parent_state_hash: str | None,
    load_step: int,
    iteration: int,
    load_factor: float,
    time_s: float,
    displacement_si: Any,
    velocity_si: Any,
    acceleration_si: Any,
    extensions: Mapping[str, Any] | None = None,
) -> StateIR:
    normalized_dof_count = _require_index(dof_count, "/dof_count", minimum=1)
    normalized_epoch = _require_index(epoch, "/epoch")
    normalized_load_step = _require_index(load_step, "/step/load_step")
    normalized_iteration = _require_index(iteration, "/step/iteration")
    normalized_load_factor = _require_finite(load_factor, "/load_factor")
    normalized_time = _require_finite(time_s, "/time_s")
    vectors = {
        "displacement": _immutable_f64_vector(
            displacement_si, normalized_dof_count, "/kinematics/displacement_si"
        ),
        "velocity": _immutable_f64_vector(
            velocity_si, normalized_dof_count, "/kinematics/velocity_si"
        ),
        "acceleration": _immutable_f64_vector(
            acceleration_si, normalized_dof_count, "/kinematics/acceleration_si"
        ),
    }
    hashes = MappingProxyType(
        {
            **{name: array_data_hash(array) for name, array in vectors.items()},
            "constitutive": _CONSTITUTIVE_HASH,
        }
    )
    frozen_extensions = _freeze_extensions({} if extensions is None else extensions)
    provisional = StateIR(
        schema_version=STATE_IR_SCHEMA_VERSION,
        state_id=state_id,
        model_ir_content_hash=model_ir_content_hash,
        solver_numeric_buffer_hash=solver_numeric_buffer_hash,
        solver_entity_mapping_hash=solver_entity_mapping_hash,
        solver_artifact_hash=solver_artifact_hash,
        execution_plan_hash=execution_plan_hash,
        operator_hash=operator_hash,
        load_pattern_id=load_pattern_id,
        role=role,
        epoch=normalized_epoch,
        parent_state_hash=parent_state_hash,
        step=StateStep(load_step=normalized_load_step, iteration=normalized_iteration),
        load_factor=normalized_load_factor,
        time_s=normalized_time,
        dof_count=normalized_dof_count,
        displacement_si=vectors["displacement"],
        velocity_si=vectors["velocity"],
        acceleration_si=vectors["acceleration"],
        vector_hashes=hashes,
        state_hash="sha256:" + "0" * 64,
        extensions=frozen_extensions,
    )
    state = StateIR(
        **{
            **provisional.__dict__,
            "state_hash": canonical_hash(
                _state_payload(provisional, include_state_hash=False)
            ),
        }
    )
    return validate_state_ir(state)


def _validate_trial_transition(
    accepted: StateIR,
    trial: StateIR,
    *,
    expected_plan: Any | None,
) -> None:
    validate_state_ir(accepted, expected_plan=expected_plan)
    validate_state_ir(trial, expected_plan=expected_plan)
    if accepted.role != "committed":
        raise StateIRError(
            "accepted_state_role_invalid", "/role", "Accepted state must be committed."
        )
    if trial.role != "trial":
        raise StateIRError(
            "trial_state_role_invalid", "/role", "Trial state is required."
        )
    if trial.parent_state_hash != accepted.state_hash:
        raise StateIRError(
            "trial_parent_mismatch",
            "/parent_state_hash",
            "Trial does not descend from the supplied accepted state.",
        )
    if trial.epoch != accepted.epoch + 1:
        raise StateIRError(
            "trial_epoch_mismatch",
            "/epoch",
            "Trial epoch must be exactly one beyond accepted epoch.",
        )
    if trial.load_step < accepted.load_step or trial.time_s < accepted.time_s:
        raise StateIRError(
            "trial_coordinates_stale",
            "/step",
            "Trial step and time cannot precede the accepted state.",
        )
    binding_fields = (
        "model_ir_content_hash",
        "solver_numeric_buffer_hash",
        "solver_entity_mapping_hash",
        "solver_artifact_hash",
        "execution_plan_hash",
        "operator_hash",
        "load_pattern_id",
        "dof_count",
    )
    if any(getattr(trial, name) != getattr(accepted, name) for name in binding_fields):
        raise StateIRError(
            "trial_binding_mismatch",
            "/execution_plan_hash",
            "Trial and accepted states must share exact model/operator bindings.",
        )


def _state_payload(state: StateIR, *, include_state_hash: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": state.schema_version,
        "state_id": state.state_id,
        "model_ir_content_hash": state.model_ir_content_hash,
        "solver_numeric_buffer_hash": state.solver_numeric_buffer_hash,
        "solver_entity_mapping_hash": state.solver_entity_mapping_hash,
        "solver_artifact_hash": state.solver_artifact_hash,
        "execution_plan_hash": state.execution_plan_hash,
        "operator_hash": state.operator_hash,
        "load_pattern_id": state.load_pattern_id,
        "role": state.role,
        "epoch": state.epoch,
        "parent_state_hash": state.parent_state_hash,
        "step": {
            "load_step": state.load_step,
            "iteration": state.iteration,
        },
        "load_factor": state.load_factor,
        "time_s": state.time_s,
        "dof_count": state.dof_count,
        "kinematics": {
            "dof_components": list(STATE_IR_DOF_COMPONENTS),
            "displacement_component_units": list(STATE_IR_DISPLACEMENT_UNITS),
            "velocity_component_units": list(STATE_IR_VELOCITY_UNITS),
            "acceleration_component_units": list(STATE_IR_ACCELERATION_UNITS),
            "displacement_si": state.displacement_si.tolist(),
            "velocity_si": state.velocity_si.tolist(),
            "acceleration_si": state.acceleration_si.tolist(),
        },
        "constitutive_state": {
            "mode": STATE_IR_CONSTITUTIVE_MODE,
            "stateful": False,
            "value_count": 0,
            "values": [],
        },
        "vector_hashes": dict(state.vector_hashes),
        "extensions": _thaw(state.extensions),
    }
    if include_state_hash:
        payload["state_hash"] = state.state_hash
    return payload


def _plan_bindings(plan: Any) -> dict[str, Any]:
    names = (
        "model_ir_content_hash",
        "solver_numeric_buffer_hash",
        "solver_entity_mapping_hash",
        "solver_artifact_hash",
        "plan_hash",
        "operator_hash",
        "load_pattern_id",
        "dof_count",
    )
    missing = [name for name in names if not hasattr(plan, name)]
    if missing:
        raise StateIRError(
            "execution_plan_binding_missing",
            "/",
            f"ExecutionPlan lacks required bindings: {', '.join(missing)}.",
        )
    result = {
        "model_ir_content_hash": getattr(plan, "model_ir_content_hash"),
        "solver_numeric_buffer_hash": getattr(plan, "solver_numeric_buffer_hash"),
        "solver_entity_mapping_hash": getattr(plan, "solver_entity_mapping_hash"),
        "solver_artifact_hash": getattr(plan, "solver_artifact_hash"),
        "execution_plan_hash": getattr(plan, "plan_hash"),
        "operator_hash": getattr(plan, "operator_hash"),
        "load_pattern_id": getattr(plan, "load_pattern_id"),
        "dof_count": getattr(plan, "dof_count"),
    }
    for name in (
        "model_ir_content_hash",
        "solver_numeric_buffer_hash",
        "solver_entity_mapping_hash",
        "solver_artifact_hash",
        "execution_plan_hash",
        "operator_hash",
    ):
        _require_hash(result[name], f"/{name}")
    _require_stable_id(result["load_pattern_id"], "/load_pattern_id")
    dof_count = _require_index(result["dof_count"], "/dof_count", minimum=1)
    result["dof_count"] = dof_count
    node_count = getattr(plan, "node_count", None)
    if node_count is not None:
        nodes = _require_index(node_count, "/node_count", minimum=1)
        if dof_count != nodes * len(STATE_IR_DOF_COMPONENTS):
            raise StateIRError(
                "execution_plan_dof_count_invalid",
                "/dof_count",
                "ExecutionPlan DOF count does not match node_count*6.",
            )
    return result


def _immutable_f64_vector(value: Any, count: int, path: str) -> np.ndarray:
    source = np.asarray(value)
    if source.dtype.kind not in "iuf":
        raise StateIRError(
            "state_vector_type_invalid",
            path,
            "State vectors must contain real numbers.",
        )
    try:
        converted = np.asarray(value, dtype="<f8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise StateIRError(
            "state_vector_type_invalid",
            path,
            "State vector cannot be converted to FP64.",
        ) from exc
    if converted.ndim != 1 or converted.shape != (count,):
        raise StateIRError(
            "state_vector_shape_invalid",
            path,
            f"Expected a flat vector with {count} entries.",
        )
    if not np.all(np.isfinite(converted)):
        raise StateIRError(
            "state_vector_nonfinite", path, "State vectors must be finite."
        )
    normalized = converted.copy(order="C")
    normalized[normalized == 0.0] = 0.0
    try:
        return immutable_array(normalized, dtype="<f8")
    except CanonicalContractError as exc:  # pragma: no cover - preconditions above
        raise StateIRError("state_vector_invalid", path, str(exc)) from exc


def _validate_vector(array: np.ndarray, count: int, path: str) -> None:
    if not isinstance(array, np.ndarray):
        raise StateIRError("state_vector_type_invalid", path, "Expected a NumPy array.")
    if array.dtype.str != "<f8":
        raise StateIRError(
            "state_vector_dtype_invalid",
            path,
            "State vectors must use little-endian FP64.",
        )
    if array.shape != (count,) or not array.flags.c_contiguous:
        raise StateIRError(
            "state_vector_shape_invalid",
            path,
            f"Expected C-contiguous shape ({count},).",
        )
    if not has_immutable_bytes_backing(array):
        raise StateIRError(
            "state_vector_mutable",
            path,
            "State vector must be backed by immutable bytes.",
        )
    if not np.all(np.isfinite(array)):
        raise StateIRError(
            "state_vector_nonfinite", path, "State vector is non-finite."
        )


def _freeze_extensions(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StateIRError("extensions_invalid", "/extensions", "Expected an object.")
    try:
        normalized = _json_roundtrip(value)
    except CanonicalContractError as exc:
        raise StateIRError("extensions_invalid", "/extensions", str(exc)) from exc
    return _freeze(normalized)


def _json_roundtrip(value: Any) -> Any:
    import json

    return json.loads(canonical_json_bytes(value))


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


def _validate_extensions(value: Mapping[str, Any]) -> None:
    if not isinstance(value, MappingProxyType):
        raise StateIRError(
            "extensions_mutable", "/extensions", "Extensions must be deeply immutable."
        )
    for key in value:
        if not isinstance(key, str) or _EXTENSION_KEY_PATTERN.fullmatch(key) is None:
            raise StateIRError(
                "extension_key_invalid", f"/extensions/{key}", "Invalid extension key."
            )
    if not _is_frozen(value):
        raise StateIRError(
            "extensions_mutable", "/extensions", "Extensions must be deeply immutable."
        )
    try:
        canonical_json_bytes(_thaw(value))
    except CanonicalContractError as exc:
        raise StateIRError("extensions_invalid", "/extensions", str(exc)) from exc


def _is_frozen(value: Any) -> bool:
    if isinstance(value, MappingProxyType):
        return all(_is_frozen(item) for item in value.values())
    if isinstance(value, tuple):
        return all(_is_frozen(item) for item in value)
    return value is None or isinstance(value, (str, bool, int, float))


def _require_hash(value: Any, path: str) -> str:
    if not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None:
        raise StateIRError("hash_invalid", path, "Expected sha256:<64 lowercase hex>.")
    return value


def _require_stable_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or _STABLE_ID_PATTERN.fullmatch(value) is None:
        raise StateIRError("stable_id_invalid", path, "Invalid stable identifier.")
    return value


def _require_index(value: Any, path: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise StateIRError("index_invalid", path, "Expected an integer index.")
    result = int(value)
    if result < minimum or result > _MAX_INDEX:
        raise StateIRError(
            "index_invalid", path, f"Index must be within [{minimum}, {_MAX_INDEX}]."
        )
    return result


def _require_finite(value: Any, path: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        raise StateIRError("number_invalid", path, "Expected a finite real number.")
    result = float(value)
    if not math.isfinite(result):
        raise StateIRError("number_nonfinite", path, "Expected a finite real number.")
    return 0.0 if result == 0.0 else result


@lru_cache(maxsize=1)
def _state_schema_validator() -> Draft202012Validator:
    path = Path(__file__).resolve().parents[2] / "schemas" / "state_ir_v1.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return _StrictDraft202012Validator(schema)
