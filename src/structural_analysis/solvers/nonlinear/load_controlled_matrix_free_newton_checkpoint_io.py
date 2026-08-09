"""Durable fail-closed I/O for load-controlled matrix-free checkpoints.

The existing checkpoint object remains the numerical authority.  This module
adds a canonical JSON commit marker and a separate little-endian FP64 vector.
The vector is installed first and the descriptor last, so an interrupted write
cannot expose a committed descriptor that points at incomplete bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
from importlib import resources
import json
import os
from pathlib import Path, PurePath
from tempfile import NamedTemporaryFile
from types import MappingProxyType
from typing import Any, Mapping

from jsonschema import Draft202012Validator, validators
from jsonschema.exceptions import SchemaError, ValidationError
import numpy as np

from structural_analysis.solvers.nonlinear.load_controlled_matrix_free_newton import (
    LoadControlledMatrixFreeNewtonCheckpoint,
)


LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_ARTIFACT_SCHEMA_VERSION = (
    "load-controlled-matrix-free-newton-checkpoint-artifact.v1"
)
LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_STORAGE_PROFILE = (
    "canonical-json-descriptor-plus-little-endian-fp64.v1"
)
LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_SCHEMA_RESOURCE = (
    "load_controlled_matrix_free_newton_checkpoint_artifact_v1.schema.json"
)
LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_MAX_EQUATIONS = 10_000_000
LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_MAX_DESCRIPTOR_BYTES = 64 * 1024

_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator,
    type_checker=_STRICT_JSON_TYPE_CHECKER,
)


class LoadControlledMatrixFreeNewtonCheckpointArtifactError(ValueError):
    """Raised when checkpoint persistence or replay fails closed."""


@dataclass(frozen=True)
class DurableLoadControlledMatrixFreeNewtonCheckpoint:
    checkpoint: LoadControlledMatrixFreeNewtonCheckpoint
    descriptor: Mapping[str, Any]
    descriptor_path: Path
    displacement_path: Path

    @property
    def descriptor_hash(self) -> str:
        return str(self.descriptor["descriptor_hash"])


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
                f"checkpoint descriptor contains duplicate key {key!r}"
            )
        value[key] = item
    return value


def _reject_constant(value: str) -> Any:
    raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
        f"checkpoint descriptor contains non-finite token {value}"
    )


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint descriptor is not finite canonical JSON"
        ) from exc


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _descriptor_hash(descriptor: Mapping[str, Any]) -> str:
    return _sha256(
        _canonical_json_bytes(
            {
                key: value
                for key, value in descriptor.items()
                if key != "descriptor_hash"
            }
        )
    )


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    try:
        schema = json.loads(
            resources.files("structural_analysis")
            .joinpath(
                "schemas",
                LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_SCHEMA_RESOURCE,
            )
            .read_text(encoding="utf-8")
        )
        _StrictDraft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint artifact schema resource is invalid"
        ) from exc
    return _StrictDraft202012Validator(schema)


def _validate_schema(descriptor: Any) -> None:
    try:
        _schema_validator().validate(descriptor)
    except ValidationError as exc:
        path = "/" + "/".join(str(value) for value in exc.absolute_path)
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            f"checkpoint descriptor schema validation failed at {path}"
        ) from exc


def _validate_file_name(value: str) -> str:
    if PurePath(value).name != value or not value.endswith(".f64le"):
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint displacement file_name is unsafe"
        )
    return value


def _checkpoint_vector_bytes(
    checkpoint: LoadControlledMatrixFreeNewtonCheckpoint,
) -> bytes:
    vector = np.asarray(checkpoint.free_displacements_m)
    if (
        vector.ndim != 1
        or vector.size < 1
        or vector.size > LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_MAX_EQUATIONS
        or not np.all(np.isfinite(vector))
    ):
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint displacement vector is outside the artifact contract"
        )
    canonical = np.ascontiguousarray(vector, dtype="<f8")
    return canonical.tobytes(order="C")


def _build_descriptor(
    checkpoint: LoadControlledMatrixFreeNewtonCheckpoint,
    *,
    displacement_file_name: str,
) -> dict[str, Any]:
    if type(checkpoint) is not LoadControlledMatrixFreeNewtonCheckpoint:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "exact LoadControlledMatrixFreeNewtonCheckpoint type required"
        )
    file_name = _validate_file_name(displacement_file_name)
    raw = _checkpoint_vector_bytes(checkpoint)
    equation_count = int(checkpoint.free_displacements_m.size)
    descriptor: dict[str, Any] = {
        "schema_version": (
            LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_ARTIFACT_SCHEMA_VERSION
        ),
        "storage_profile": (
            LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_STORAGE_PROFILE
        ),
        "core_checkpoint_schema_version": checkpoint.schema_version,
        "case_id": checkpoint.case_id,
        "path_contract_hash": checkpoint.path_contract_hash,
        "step_index": checkpoint.step_index,
        "load_factor": checkpoint.load_factor,
        "equation_count": equation_count,
        "displacement_artifact": {
            "file_name": file_name,
            "dtype": "<f8",
            "byte_order": "little",
            "shape": [equation_count],
            "byte_length": len(raw),
            "data_hash": _sha256(raw),
        },
        "checkpoint_state_hash": checkpoint.state_hash,
        "descriptor_hash": "sha256:" + "0" * 64,
    }
    descriptor["descriptor_hash"] = _descriptor_hash(descriptor)
    _validate_schema(descriptor)
    return descriptor


def _load_descriptor_bytes(raw: bytes) -> dict[str, Any]:
    if len(raw) > LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_MAX_DESCRIPTOR_BYTES:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint descriptor exceeds the bounded byte limit"
        )
    try:
        descriptor = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except LoadControlledMatrixFreeNewtonCheckpointArtifactError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint descriptor is not strict UTF-8 JSON"
        ) from exc
    if type(descriptor) is not dict:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint descriptor must be a JSON object"
        )
    _validate_schema(descriptor)
    if descriptor["descriptor_hash"] != _descriptor_hash(descriptor):
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint descriptor_hash mismatch"
        )
    return descriptor


def _read_bounded(path: Path, *, maximum_bytes: int, label: str) -> bytes:
    try:
        size = path.stat().st_size
        if size > maximum_bytes:
            raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
                f"checkpoint {label} exceeds the bounded byte limit"
            )
        return path.read_bytes()
    except LoadControlledMatrixFreeNewtonCheckpointArtifactError:
        raise
    except OSError as exc:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            f"checkpoint {label} could not be read"
        ) from exc


def read_load_controlled_matrix_free_newton_checkpoint_artifact(
    descriptor_path: str | Path,
    *,
    expected_case_id: str,
    expected_path_contract_hash: str,
    expected_equation_count: int | None = None,
    displacement_path: str | Path | None = None,
) -> DurableLoadControlledMatrixFreeNewtonCheckpoint:
    """Read, hash-check, and reconstruct one exact core checkpoint."""

    descriptor_target = Path(descriptor_path)
    descriptor = _load_descriptor_bytes(
        _read_bounded(
            descriptor_target,
            maximum_bytes=(
                LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_MAX_DESCRIPTOR_BYTES
            ),
            label="descriptor",
        )
    )
    if type(expected_case_id) is not str or descriptor["case_id"] != expected_case_id:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint case_id does not match the requested path"
        )
    if (
        type(expected_path_contract_hash) is not str
        or descriptor["path_contract_hash"] != expected_path_contract_hash
    ):
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint path_contract_hash does not match the requested path"
        )
    equation_count = descriptor["equation_count"]
    if expected_equation_count is not None and (
        type(expected_equation_count) is not int
        or equation_count != expected_equation_count
    ):
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint equation_count does not match the requested path"
        )
    artifact = descriptor["displacement_artifact"]
    declared_name = _validate_file_name(artifact["file_name"])
    vector_target = (
        descriptor_target.with_name(declared_name)
        if displacement_path is None
        else Path(displacement_path)
    )
    if vector_target.name != declared_name:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint displacement path is detached from the descriptor"
        )
    expected_bytes = 8 * equation_count
    if (
        artifact["shape"] != [equation_count]
        or artifact["byte_length"] != expected_bytes
    ):
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint displacement shape or byte length is inconsistent"
        )
    raw = _read_bounded(
        vector_target,
        maximum_bytes=8 * LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_MAX_EQUATIONS,
        label="displacement",
    )
    if len(raw) != expected_bytes:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint displacement byte length mismatch"
        )
    if _sha256(raw) != artifact["data_hash"]:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint displacement data_hash mismatch"
        )
    vector = np.frombuffer(raw, dtype="<f8")
    if vector.shape != (equation_count,) or not np.all(np.isfinite(vector)):
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint displacement contains invalid FP64 values"
        )
    try:
        checkpoint = LoadControlledMatrixFreeNewtonCheckpoint(
            schema_version=descriptor["core_checkpoint_schema_version"],
            case_id=descriptor["case_id"],
            path_contract_hash=descriptor["path_contract_hash"],
            step_index=descriptor["step_index"],
            load_factor=descriptor["load_factor"],
            free_displacements_m=vector,
            state_hash=descriptor["checkpoint_state_hash"],
        )
    except (TypeError, ValueError) as exc:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint core state reconstruction failed"
        ) from exc
    expected_descriptor = _build_descriptor(
        checkpoint,
        displacement_file_name=declared_name,
    )
    if descriptor != expected_descriptor:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint descriptor is not the canonical core-state projection"
        )
    return DurableLoadControlledMatrixFreeNewtonCheckpoint(
        checkpoint=checkpoint,
        descriptor=MappingProxyType(descriptor),
        descriptor_path=descriptor_target,
        displacement_path=vector_target,
    )


def _write_temporary(path: Path, raw: bytes) -> Path:
    try:
        with NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return temporary
    except OSError as exc:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint temporary artifact could not be written"
        ) from exc


def _install_no_replace(temporary: Path, target: Path) -> None:
    try:
        os.link(temporary, target)
        temporary.unlink()
    except FileExistsError as exc:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint artifact target already exists"
        ) from exc
    except OSError as exc:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint artifact could not be atomically installed"
        ) from exc


def write_load_controlled_matrix_free_newton_checkpoint_artifact(
    checkpoint: LoadControlledMatrixFreeNewtonCheckpoint,
    descriptor_path: str | Path,
    *,
    displacement_path: str | Path | None = None,
) -> DurableLoadControlledMatrixFreeNewtonCheckpoint:
    """Persist a vector and descriptor without overwriting an existing path."""

    descriptor_target = Path(descriptor_path)
    vector_target = (
        descriptor_target.with_suffix(".f64le")
        if displacement_path is None
        else Path(displacement_path)
    )
    if descriptor_target.parent != vector_target.parent:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint descriptor and displacement must share one directory"
        )
    if not descriptor_target.parent.is_dir():
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint artifact directory does not exist"
        )
    if descriptor_target == vector_target:
        raise LoadControlledMatrixFreeNewtonCheckpointArtifactError(
            "checkpoint descriptor and displacement paths must differ"
        )
    descriptor = _build_descriptor(
        checkpoint,
        displacement_file_name=vector_target.name,
    )
    vector_raw = _checkpoint_vector_bytes(checkpoint)
    descriptor_raw = _canonical_json_bytes(descriptor) + b"\n"
    vector_temporary: Path | None = None
    descriptor_temporary: Path | None = None
    vector_installed = False
    try:
        vector_temporary = _write_temporary(vector_target, vector_raw)
        descriptor_temporary = _write_temporary(descriptor_target, descriptor_raw)
        _install_no_replace(vector_temporary, vector_target)
        vector_temporary = None
        vector_installed = True
        _install_no_replace(descriptor_temporary, descriptor_target)
        descriptor_temporary = None
    except Exception:
        if vector_installed and not descriptor_target.exists():
            try:
                vector_target.unlink()
            except OSError:
                pass
        raise
    finally:
        for temporary in (vector_temporary, descriptor_temporary):
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    pass
    return read_load_controlled_matrix_free_newton_checkpoint_artifact(
        descriptor_target,
        expected_case_id=checkpoint.case_id,
        expected_path_contract_hash=checkpoint.path_contract_hash,
        expected_equation_count=int(checkpoint.free_displacements_m.size),
        displacement_path=vector_target,
    )


__all__ = [
    "LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_ARTIFACT_SCHEMA_VERSION",
    "LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_MAX_DESCRIPTOR_BYTES",
    "LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_MAX_EQUATIONS",
    "LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_SCHEMA_RESOURCE",
    "LOAD_CONTROLLED_MATRIX_FREE_NEWTON_CHECKPOINT_STORAGE_PROFILE",
    "DurableLoadControlledMatrixFreeNewtonCheckpoint",
    "LoadControlledMatrixFreeNewtonCheckpointArtifactError",
    "read_load_controlled_matrix_free_newton_checkpoint_artifact",
    "write_load_controlled_matrix_free_newton_checkpoint_artifact",
]
