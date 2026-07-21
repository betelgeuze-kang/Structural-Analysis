"""Fail-closed persisted checkpoints for the corotational fiber-frame path."""

from __future__ import annotations

from functools import lru_cache
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, validators
from jsonschema.exceptions import SchemaError, ValidationError

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DProblem,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.elements.stateful_corotational_fiber_beam2d_state import (
    StatefulCorotationalFiberBeam2DState,
)
from structural_analysis.elements.stateful_fiber_beam2d_state import (
    StatefulFiberBeam2DState,
)
from structural_analysis.materials.concrete_damage import (
    STATE_SCHEMA_VERSION as CONCRETE_DAMAGE_STATE_SCHEMA_VERSION,
)
from structural_analysis.materials.concrete_damage import ConcreteDamageState
from structural_analysis.materials.stateful_fiber_section import (
    FIBER_SECTION_STATE_SCHEMA_VERSION,
    StatefulFiberSectionState,
)
from structural_analysis.materials.uniaxial_plasticity import (
    STATE_SCHEMA_VERSION as UNIAXIAL_PLASTICITY_STATE_SCHEMA_VERSION,
)
from structural_analysis.materials.uniaxial_plasticity import (
    UniaxialPlasticityState,
)


STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_STORAGE_PROFILE = (
    "canonical-signed-zero-preserving-utf8-json.v1"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_MAX_BYTES = 4 * 1024 * 1024
STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_RESOURCE = (
    "stateful_corotational_fiber_frame2d_checkpoint_v1.schema.json"
)

_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator,
    type_checker=_STRICT_JSON_TYPE_CHECKER,
)


class StatefulCorotationalFiberFrame2DCheckpointArtifactError(ValueError):
    """Raised when persisted corotational checkpoint bytes fail closed."""


def _artifact_json_bytes(payload: Any) -> bytes:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint contains a non-JSON or non-finite value"
        ) from exc


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
                f"checkpoint JSON contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
        f"checkpoint JSON contains non-finite token {value}"
    )


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    try:
        schema_text = (
            resources.files("structural_analysis")
            .joinpath(
                "schemas",
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_RESOURCE,
            )
            .read_text(encoding="utf-8")
        )
        schema = json.loads(schema_text)
        _StrictDraft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint JSON Schema resource is invalid"
        ) from exc
    return _StrictDraft202012Validator(schema)


def _validate_schema(payload: Any) -> None:
    try:
        _schema_validator().validate(payload)
    except ValidationError as exc:
        path = "/" + "/".join(str(part) for part in exc.absolute_path)
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            f"checkpoint schema validation failed at {path}"
        ) from exc


def _require_roundtrip(payload: dict[str, Any], restored: Any, *, path: str) -> None:
    if _artifact_json_bytes(restored.to_dict()) != _artifact_json_bytes(payload):
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            f"{path} hash or canonical value mismatch"
        )


def _restore_fiber_state(
    template: Any,
    payload: dict[str, Any],
    *,
    path: str,
) -> UniaxialPlasticityState | ConcreteDamageState:
    try:
        if type(template) is UniaxialPlasticityState:
            if payload["schema_version"] != UNIAXIAL_PLASTICITY_STATE_SCHEMA_VERSION:
                raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
                    f"{path} material state type does not match the problem"
                )
            restored: UniaxialPlasticityState | ConcreteDamageState = (
                UniaxialPlasticityState(
                    plastic_strain=payload["plastic_strain"],
                    backstress_mpa=payload["backstress_mpa"],
                    accumulated_plastic_strain=payload["accumulated_plastic_strain"],
                    dissipated_energy_density_mj_per_m3=payload[
                        "dissipated_energy_density_mj_per_m3"
                    ],
                )
            )
        elif type(template) is ConcreteDamageState:
            if payload["schema_version"] != CONCRETE_DAMAGE_STATE_SCHEMA_VERSION:
                raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
                    f"{path} material state type does not match the problem"
                )
            restored = ConcreteDamageState(
                tensile_history_strain=payload["tensile_history_strain"],
                compressive_history_strain=payload["compressive_history_strain"],
                tensile_damage=payload["tensile_damage"],
                compressive_damage=payload["compressive_damage"],
                dissipated_energy_density_mj_per_m3=payload[
                    "dissipated_energy_density_mj_per_m3"
                ],
            )
        else:
            raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
                f"{path} uses an unsupported material-state codec"
            )
    except StatefulCorotationalFiberFrame2DCheckpointArtifactError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            f"{path} material state is invalid"
        ) from exc
    _require_roundtrip(payload, restored, path=path)
    return restored


def _restore_section_state(
    template: Any,
    payload: dict[str, Any],
    *,
    path: str,
) -> StatefulFiberSectionState:
    if type(template) is not StatefulFiberSectionState:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            f"{path} uses an unsupported axial-curvature section-state codec"
        )
    fiber_payloads = payload["fiber_states"]
    if len(fiber_payloads) != len(template.fiber_states):
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            f"{path} fiber-state count does not match the problem"
        )
    fibers = tuple(
        _restore_fiber_state(
            fiber_template,
            fiber_payload,
            path=f"{path}/fiber_states/{index}",
        )
        for index, (fiber_template, fiber_payload) in enumerate(
            zip(template.fiber_states, fiber_payloads, strict=True)
        )
    )
    try:
        if payload["schema_version"] != FIBER_SECTION_STATE_SCHEMA_VERSION:
            raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
                f"{path} section schema_version is invalid"
            )
        restored = StatefulFiberSectionState(
            section_id=payload["section_id"],
            section_contract_hash=payload["section_contract_hash"],
            step_index=payload["step_index"],
            axial_strain=payload["axial_strain"],
            curvature_z_per_m=payload["curvature_z_per_m"],
            fiber_states=fibers,
        )
    except StatefulCorotationalFiberFrame2DCheckpointArtifactError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            f"{path} section state is invalid"
        ) from exc
    _require_roundtrip(payload, restored, path=path)
    return restored


def _restore_basic_beam_state(
    template: StatefulFiberBeam2DState,
    payload: dict[str, Any],
    *,
    path: str,
) -> StatefulFiberBeam2DState:
    section_payloads = payload["integration_point_states"]
    if len(section_payloads) != len(template.integration_point_states):
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            f"{path} integration-point count does not match the problem"
        )
    sections = tuple(
        _restore_section_state(
            section_template,
            section_payload,
            path=f"{path}/integration_point_states/{index}",
        )
        for index, (section_template, section_payload) in enumerate(
            zip(
                template.integration_point_states,
                section_payloads,
                strict=True,
            )
        )
    )
    try:
        restored = StatefulFiberBeam2DState(
            element_id=payload["element_id"],
            element_contract_hash=payload["element_contract_hash"],
            step_index=payload["step_index"],
            local_displacements=tuple(payload["local_displacements"]),
            integration_point_states=sections,
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            f"{path} basic beam state is invalid"
        ) from exc
    _require_roundtrip(payload, restored, path=path)
    return restored


def _restore_corotational_element_state(
    template: StatefulCorotationalFiberBeam2DState,
    payload: dict[str, Any],
    *,
    path: str,
) -> StatefulCorotationalFiberBeam2DState:
    basic_state = _restore_basic_beam_state(
        template.basic_beam_state,
        payload["basic_beam_state"],
        path=f"{path}/basic_beam_state",
    )
    try:
        restored = StatefulCorotationalFiberBeam2DState(
            element_id=payload["element_id"],
            element_contract_hash=payload["element_contract_hash"],
            step_index=payload["step_index"],
            element_displacements=tuple(payload["element_displacements"]),
            chord_rotation_change_rad=payload["chord_rotation_change_rad"],
            basic_beam_state=basic_state,
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            f"{path} corotational element state is invalid"
        ) from exc
    _require_roundtrip(payload, restored, path=path)
    return restored


def load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
    data: bytes | bytearray | memoryview,
    problem: StatefulCorotationalFiberFrame2DProblem,
) -> StatefulCorotationalFiberFrame2DCheckpoint:
    """Restore exact canonical checkpoint bytes against one explicit problem."""

    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint artifact must be bytes"
        )
    raw = bytes(data)
    if len(raw) > STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_MAX_BYTES:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint artifact exceeds the bounded byte limit"
        )
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except StatefulCorotationalFiberFrame2DCheckpointArtifactError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint artifact is not valid UTF-8 JSON"
        ) from exc
    _validate_schema(parsed)
    if _artifact_json_bytes(parsed) != raw:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint artifact is not canonical JSON"
        )

    payload: dict[str, Any] = parsed
    element_payloads = payload["element_states"]
    if len(element_payloads) != len(problem.members):
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint element-state count does not match the problem"
        )
    element_states = tuple(
        _restore_corotational_element_state(
            member.element.initial_state(),
            element_payload,
            path=f"/element_states/{index}",
        )
        for index, (member, element_payload) in enumerate(
            zip(problem.members, element_payloads, strict=True)
        )
    )
    try:
        checkpoint = StatefulCorotationalFiberFrame2DCheckpoint(
            case_id=payload["case_id"],
            problem_contract_hash=payload["problem_contract_hash"],
            epoch=payload["epoch"],
            step_index=payload["step_index"],
            load_factor=payload["load_factor"],
            parent_state_hash=payload["parent_state_hash"],
            global_displacements=tuple(payload["global_displacements"]),
            element_states=element_states,
            role=payload["role"],
            state_hash=payload["state_hash"],
        )
        validate_stateful_corotational_fiber_frame2d_checkpoint(problem, checkpoint)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint does not match the supplied frame problem"
        ) from exc
    if _artifact_json_bytes(checkpoint.to_dict()) != raw:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint artifact round-trip mismatch"
        )
    return checkpoint


def dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(
    problem: StatefulCorotationalFiberFrame2DProblem,
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
) -> bytes:
    """Serialize one validated checkpoint to exact canonical artifact bytes."""

    try:
        validate_stateful_corotational_fiber_frame2d_checkpoint(problem, checkpoint)
    except ValueError as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint does not match the supplied frame problem"
        ) from exc
    payload = checkpoint.to_dict()
    _validate_schema(payload)
    raw = _artifact_json_bytes(payload)
    if len(raw) > STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_MAX_BYTES:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint artifact exceeds the bounded byte limit"
        )
    restored = load_stateful_corotational_fiber_frame2d_checkpoint_bytes(raw, problem)
    if restored.canonical_bytes() != checkpoint.canonical_bytes():
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint binary state changed during serialization"
        )
    return raw


def stateful_corotational_fiber_frame2d_checkpoint_artifact_hash(
    data: bytes | bytearray | memoryview,
) -> str:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint artifact must be bytes"
        )
    return "sha256:" + hashlib.sha256(bytes(data)).hexdigest()


def write_stateful_corotational_fiber_frame2d_checkpoint_artifact(
    problem: StatefulCorotationalFiberFrame2DProblem,
    checkpoint: StatefulCorotationalFiberFrame2DCheckpoint,
    target: str | Path,
) -> Path:
    """Persist exact bytes once; overwriting an existing target fails closed."""

    raw = dump_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        problem,
        checkpoint,
    )
    path = Path(target)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint artifact target already exists"
        ) from exc
    except OSError as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint artifact could not be written"
        ) from exc
    return path


def read_stateful_corotational_fiber_frame2d_checkpoint_artifact(
    problem: StatefulCorotationalFiberFrame2DProblem,
    source: str | Path,
) -> StatefulCorotationalFiberFrame2DCheckpoint:
    path = Path(source)
    try:
        size = path.stat().st_size
        if size > STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_MAX_BYTES:
            raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
                "checkpoint artifact exceeds the bounded byte limit"
            )
        raw = path.read_bytes()
    except StatefulCorotationalFiberFrame2DCheckpointArtifactError:
        raise
    except OSError as exc:
        raise StatefulCorotationalFiberFrame2DCheckpointArtifactError(
            "checkpoint artifact could not be read"
        ) from exc
    return load_stateful_corotational_fiber_frame2d_checkpoint_bytes(raw, problem)


__all__ = [
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_MAX_BYTES",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_RESOURCE",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_CHECKPOINT_STORAGE_PROFILE",
    "StatefulCorotationalFiberFrame2DCheckpointArtifactError",
    "dump_stateful_corotational_fiber_frame2d_checkpoint_bytes",
    "load_stateful_corotational_fiber_frame2d_checkpoint_bytes",
    "read_stateful_corotational_fiber_frame2d_checkpoint_artifact",
    "stateful_corotational_fiber_frame2d_checkpoint_artifact_hash",
    "write_stateful_corotational_fiber_frame2d_checkpoint_artifact",
]
