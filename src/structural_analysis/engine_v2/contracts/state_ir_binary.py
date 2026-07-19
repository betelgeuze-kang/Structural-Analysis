"""Descriptor-only binary storage profile for large StateIR vectors."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from importlib import resources
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from jsonschema import Draft202012Validator, validators
import numpy as np

from ._canonical import (
    array_content_hash,
    array_data_hash,
    canonical_hash,
    immutable_array,
)
from .state_ir import StateIR, validate_state_ir

STATE_IR_BINARY_MANIFEST_SCHEMA_VERSION = (
    "structural-analysis-state-ir-binary-manifest.v1"
)
STATE_IR_BINARY_STORAGE_PROFILE = "canonical_little_endian_fp64_binary.v1"

_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator, type_checker=_STRICT_JSON_TYPE_CHECKER
)
_VECTOR_NAMES = ("displacement", "velocity", "acceleration", "constitutive")
_FILENAMES = {
    "displacement": "displacement_si.f64le",
    "velocity": "velocity_si.f64le",
    "acceleration": "acceleration_si.f64le",
    "constitutive": "constitutive_state.f64le",
}
_EMPTY_CONSTITUTIVE = immutable_array([], dtype="<f8")


class StateIRBinaryManifestError(ValueError):
    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class StateIRBinaryVectorDescriptor:
    name: str
    dtype: Literal["<f8"]
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_order: Literal["little"]
    byte_length: int
    data_hash: str
    content_hash: str
    artifact_uri: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        return payload


@dataclass(frozen=True)
class StateIRBinaryManifest:
    schema_version: str
    storage_profile: str
    manifest_hash: str
    state_hash: str
    dof_count: int
    vector_hashes: Mapping[str, str]
    descriptors: tuple[StateIRBinaryVectorDescriptor, ...]

    def descriptor(self, name: str) -> StateIRBinaryVectorDescriptor:
        for descriptor in self.descriptors:
            if descriptor.name == name:
                return descriptor
        raise KeyError(f"Unknown StateIR binary vector: {name}")

    def to_manifest(self) -> dict[str, Any]:
        validate_state_ir_binary_manifest(self)
        return _manifest_payload(self, include_manifest_hash=True)


def create_state_ir_binary_manifest(
    state: StateIR,
    *,
    artifact_uri_prefix: str,
) -> StateIRBinaryManifest:
    validated = validate_state_ir(state)
    prefix = _artifact_uri_prefix(artifact_uri_prefix)
    arrays = _state_arrays(validated)
    descriptors = tuple(
        _descriptor(
            name,
            arrays[name],
            artifact_uri=f"{prefix}/{_FILENAMES[name]}",
            state_hash=validated.state_hash,
        )
        for name in _VECTOR_NAMES
    )
    provisional = StateIRBinaryManifest(
        schema_version=STATE_IR_BINARY_MANIFEST_SCHEMA_VERSION,
        storage_profile=STATE_IR_BINARY_STORAGE_PROFILE,
        manifest_hash="sha256:" + "0" * 64,
        state_hash=validated.state_hash,
        dof_count=validated.dof_count,
        vector_hashes=MappingProxyType(dict(validated.vector_hashes)),
        descriptors=descriptors,
    )
    manifest = replace(provisional, manifest_hash=_manifest_hash(provisional))
    return validate_state_ir_binary_manifest(manifest, state=validated)


def write_state_ir_binary_artifacts(
    state: StateIR,
    output_directory: str | Path,
    *,
    artifact_uri_prefix: str,
) -> StateIRBinaryManifest:
    """Write exact vector bytes once; existing targets fail closed."""

    validated = validate_state_ir(state)
    manifest = create_state_ir_binary_manifest(
        validated, artifact_uri_prefix=artifact_uri_prefix
    )
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    arrays = _state_arrays(validated)
    targets = {name: directory / _FILENAMES[name] for name in _VECTOR_NAMES}
    for name, target in targets.items():
        if target.exists():
            _fail(
                "state_binary_target_exists",
                f"/artifacts/{name}",
                f"Refusing to overwrite existing artifact: {target}",
            )

    created_targets: list[Path] = []
    try:
        for name, target in targets.items():
            with target.open("xb") as handle:
                created_targets.append(target)
                handle.write(memoryview(arrays[name]).cast("B"))
            validate_state_ir_binary_artifact_bytes(
                manifest, name=name, data=target.read_bytes()
            )
    except Exception:
        for created_target in reversed(created_targets):
            created_target.unlink(missing_ok=True)
        raise
    return manifest


def validate_state_ir_binary_manifest(
    manifest: StateIRBinaryManifest,
    *,
    state: StateIR | None = None,
) -> StateIRBinaryManifest:
    if type(manifest) is not StateIRBinaryManifest:
        _fail("state_binary_manifest_type_invalid", "/", "Expected manifest object.")
    if not isinstance(manifest.vector_hashes, MappingProxyType):
        _fail(
            "state_binary_vector_hashes_mutable",
            "/source_state/vector_hashes",
            "Vector hash map must be immutable.",
        )
    if tuple(manifest.vector_hashes) != _VECTOR_NAMES:
        _fail(
            "state_binary_vector_hash_set_invalid",
            "/source_state/vector_hashes",
            "Vector hash set or order is invalid.",
        )
    if (
        type(manifest.descriptors) is not tuple
        or tuple(row.name for row in manifest.descriptors) != _VECTOR_NAMES
        or any(
            type(row) is not StateIRBinaryVectorDescriptor
            for row in manifest.descriptors
        )
    ):
        _fail(
            "state_binary_descriptor_set_invalid",
            "/artifacts",
            "Artifact descriptor set or order is invalid.",
        )
    validate_state_ir_binary_manifest_payload(
        _manifest_payload(manifest, include_manifest_hash=True)
    )
    if state is not None:
        validated = validate_state_ir(state)
        if (
            manifest.state_hash != validated.state_hash
            or manifest.dof_count != validated.dof_count
            or dict(manifest.vector_hashes) != dict(validated.vector_hashes)
        ):
            _fail(
                "state_binary_source_mismatch",
                "/source_state",
                "Binary manifest identifies another StateIR.",
            )
        arrays = _state_arrays(validated)
        for descriptor in manifest.descriptors:
            expected = _descriptor(
                descriptor.name,
                arrays[descriptor.name],
                artifact_uri=descriptor.artifact_uri,
                state_hash=validated.state_hash,
            )
            if descriptor != expected:
                _fail(
                    "state_binary_descriptor_mismatch",
                    f"/artifacts/{descriptor.name}",
                    "Descriptor does not match exact StateIR bytes.",
                )
    if manifest.manifest_hash != _manifest_hash(manifest):
        _fail(
            "state_binary_manifest_hash_mismatch",
            "/manifest_hash",
            "Manifest hash is stale.",
        )
    return manifest


def validate_state_ir_binary_manifest_payload(payload: Any) -> Mapping[str, Any]:
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail("state_binary_schema_invalid", path or "/", error.message)
    if not isinstance(payload, Mapping):  # pragma: no cover
        _fail("state_binary_manifest_type_invalid", "/", "Expected an object.")
    dof_count = payload["source_state"]["dof_count"]
    expected_shapes = {
        "displacement": [dof_count],
        "velocity": [dof_count],
        "acceleration": [dof_count],
        "constitutive": [0],
    }
    artifacts = payload["artifacts"]
    if [row["name"] for row in artifacts] != list(_VECTOR_NAMES):
        _fail(
            "state_binary_artifact_order_invalid",
            "/artifacts",
            "Artifact order or set is invalid.",
        )
    vector_hashes = payload["source_state"]["vector_hashes"]
    artifact_uris: list[str] = []
    for index, descriptor in enumerate(artifacts):
        name = descriptor["name"]
        if (
            descriptor["shape"] != expected_shapes[name]
            or descriptor["byte_length"] != 8 * expected_shapes[name][0]
            or descriptor["data_hash"] != vector_hashes[name]
        ):
            _fail(
                "state_binary_descriptor_semantics_invalid",
                f"/artifacts/{index}",
                "Descriptor shape, byte length, or StateIR vector hash is stale.",
            )
        artifact_uri = descriptor["artifact_uri"]
        artifact_uris.append(artifact_uri)
        if not artifact_uri.endswith(f"/{_FILENAMES[name]}"):
            _fail(
                "state_binary_artifact_uri_semantics_invalid",
                f"/artifacts/{index}/artifact_uri",
                "Artifact URI does not use the canonical vector filename.",
            )
    if len(set(artifact_uris)) != len(artifact_uris):
        _fail(
            "state_binary_artifact_uri_semantics_invalid",
            "/artifacts",
            "Artifact URIs must be unique.",
        )
    without_hash = dict(payload)
    claimed_hash = without_hash.pop("manifest_hash")
    if claimed_hash != canonical_hash(without_hash):
        _fail(
            "state_binary_manifest_hash_mismatch",
            "/manifest_hash",
            "Manifest hash is stale.",
        )
    return payload


def validate_state_ir_binary_artifact_bytes(
    manifest: StateIRBinaryManifest,
    *,
    name: str,
    data: bytes | bytearray | memoryview,
) -> None:
    validate_state_ir_binary_manifest(manifest)
    if name not in _VECTOR_NAMES:
        _fail("state_binary_artifact_name_invalid", "/artifacts", "Unknown vector.")
    raw = bytes(data)
    descriptor = manifest.descriptor(name)
    if len(raw) != descriptor.byte_length:
        _fail(
            "state_binary_artifact_length_mismatch",
            f"/artifacts/{name}/byte_length",
            "Artifact byte length is stale.",
        )
    data_hash = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    if data_hash != descriptor.data_hash:
        _fail(
            "state_binary_artifact_hash_mismatch",
            f"/artifacts/{name}/data_hash",
            "Artifact bytes do not match the descriptor.",
        )
    values = immutable_array(np.frombuffer(raw, dtype="<f8"), dtype="<f8")
    metadata = _content_metadata(
        name=name,
        shape=descriptor.shape,
        byte_length=descriptor.byte_length,
        state_hash=manifest.state_hash,
    )
    if array_content_hash(metadata, values) != descriptor.content_hash:
        _fail(
            "state_binary_artifact_content_hash_mismatch",
            f"/artifacts/{name}/content_hash",
            "Artifact content hash is stale.",
        )


def _state_arrays(state: StateIR) -> dict[str, np.ndarray]:
    return {
        "displacement": state.displacement_si,
        "velocity": state.velocity_si,
        "acceleration": state.acceleration_si,
        "constitutive": _EMPTY_CONSTITUTIVE,
    }


def _descriptor(
    name: str,
    array: np.ndarray,
    *,
    artifact_uri: str,
    state_hash: str,
) -> StateIRBinaryVectorDescriptor:
    metadata = _content_metadata(
        name=name,
        shape=tuple(int(value) for value in array.shape),
        byte_length=int(array.nbytes),
        state_hash=state_hash,
    )
    return StateIRBinaryVectorDescriptor(
        name=name,
        dtype="<f8",
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_order="little",
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
        artifact_uri=artifact_uri,
    )


def _content_metadata(
    *, name: str, shape: tuple[int, ...], byte_length: int, state_hash: str
) -> dict[str, Any]:
    return {
        "name": name,
        "dtype": "<f8",
        "shape": list(shape),
        "layout": "C",
        "byte_order": "little",
        "byte_length": byte_length,
        "state_hash": state_hash,
    }


def _manifest_payload(
    manifest: StateIRBinaryManifest, *, include_manifest_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": manifest.schema_version,
        "storage_profile": manifest.storage_profile,
        "source_state": {
            "state_hash": manifest.state_hash,
            "dof_count": manifest.dof_count,
            "vector_hashes": dict(manifest.vector_hashes),
        },
        "artifacts": [row.to_dict() for row in manifest.descriptors],
        "claim_boundary": {
            "inline_vectors": False,
            "canonical_little_endian_binary": True,
            "solver_or_result_authority": False,
        },
    }
    if include_manifest_hash:
        payload["manifest_hash"] = manifest.manifest_hash
    return payload


def _manifest_hash(manifest: StateIRBinaryManifest) -> str:
    return canonical_hash(_manifest_payload(manifest, include_manifest_hash=False))


def _artifact_uri_prefix(value: Any) -> str:
    if type(value) is not str:
        _fail(
            "state_binary_artifact_uri_invalid",
            "/artifact_uri_prefix",
            "Expected text.",
        )
    normalized = value.rstrip("/")
    if not normalized or any(ord(character) < 32 for character in normalized):
        _fail(
            "state_binary_artifact_uri_invalid",
            "/artifact_uri_prefix",
            "Artifact URI prefix must be nonempty printable text.",
        )
    return normalized


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    resource = resources.files("structural_analysis.schemas").joinpath(
        "state_ir_binary_manifest_v1.schema.json"
    )
    with resource.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return _StrictDraft202012Validator(schema)


def _fail(code: str, path: str, message: str) -> None:
    raise StateIRBinaryManifestError(code, path, message)
