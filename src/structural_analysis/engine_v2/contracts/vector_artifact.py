"""Descriptor-only binary artifacts for EquationScaling and residual traces."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from importlib import resources
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
    has_immutable_bytes_backing,
)
from .equation_scaling import (
    EquationScaling,
    ScaledResidualTrace,
    validate_equation_scaling,
    validate_scaled_residual_trace,
)

ENGINE_V2_VECTOR_ARTIFACT_SCHEMA_VERSION = (
    "structural-analysis-engine-v2-vector-artifacts.v1"
)
ENGINE_V2_VECTOR_STORAGE_PROFILE = "canonical_little_endian_fp64_binary.v1"

_HASH_ZERO = "sha256:" + "0" * 64
_OWNER_VECTOR_SPECS = {
    "equation_scaling": (
        (
            "scale_divisors_si",
            "scale_divisors_si.f64le",
            "global_equations",
        ),
    ),
    "scaled_residual_trace": (
        (
            "raw_residual_si",
            "raw_residual_si.f64le",
            "global_storage_free_equation_observation",
        ),
        (
            "scaled_residual",
            "scaled_residual.f64le",
            "global_storage_free_equation_observation",
        ),
    ),
}
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator, type_checker=_STRICT_JSON_TYPE_CHECKER
)


class EngineV2VectorArtifactError(ValueError):
    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class EngineV2VectorArtifactDescriptor:
    name: str
    dtype: Literal["<f8"]
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_order: Literal["little"]
    equation_scope: str
    byte_length: int
    data_hash: str
    content_hash: str
    source_vector_content_hash: str | None
    artifact_uri: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        return payload


@dataclass(frozen=True)
class EngineV2VectorArtifactBundle:
    schema_version: str
    storage_profile: str
    bundle_hash: str
    owner_kind: Literal["equation_scaling", "scaled_residual_trace"]
    owner_schema_version: str
    owner_hash: str
    execution_plan_hash: str
    scaling_hash: str
    dof_count: int
    descriptors: tuple[EngineV2VectorArtifactDescriptor, ...]
    _vectors: Mapping[str, np.ndarray]
    _source_owner: EquationScaling | ScaledResidualTrace

    def vector(self, name: str) -> np.ndarray:
        try:
            return self._vectors[name]
        except KeyError as exc:
            raise KeyError(f"Unknown Engine v2 vector artifact: {name}") from exc

    def to_manifest(self) -> dict[str, Any]:
        validate_engine_v2_vector_artifact_bundle(self)
        return _bundle_payload(self, include_bundle_hash=True)


def create_equation_scaling_vector_artifact_bundle(
    scaling: EquationScaling,
    *,
    artifact_uri_prefix: str,
) -> EngineV2VectorArtifactBundle:
    validated = validate_equation_scaling(scaling)
    return _create_bundle(
        owner_kind="equation_scaling",
        owner=validated,
        owner_schema_version=validated.schema_version,
        owner_hash=validated.scaling_hash,
        execution_plan_hash=validated.base_plan_hash,
        scaling_hash=validated.scaling_hash,
        vectors={"scale_divisors_si": validated.scale_divisors_si},
        source_content_hashes={
            "scale_divisors_si": validated.scale_vector_content_hash
        },
        artifact_uri_prefix=artifact_uri_prefix,
    )


def create_scaled_residual_vector_artifact_bundle(
    trace: ScaledResidualTrace,
    *,
    artifact_uri_prefix: str,
) -> EngineV2VectorArtifactBundle:
    validated = validate_scaled_residual_trace(trace)
    return _create_bundle(
        owner_kind="scaled_residual_trace",
        owner=validated,
        owner_schema_version=validated.schema_version,
        owner_hash=validated.trace_hash,
        execution_plan_hash=validated.execution_plan_hash,
        scaling_hash=validated.scaling_hash,
        vectors={
            "raw_residual_si": validated.raw_residual_si,
            "scaled_residual": validated.scaled_residual,
        },
        source_content_hashes={
            "raw_residual_si": None,
            "scaled_residual": None,
        },
        artifact_uri_prefix=artifact_uri_prefix,
    )


def validate_engine_v2_vector_artifact_bundle(
    bundle: EngineV2VectorArtifactBundle,
) -> EngineV2VectorArtifactBundle:
    if type(bundle) is not EngineV2VectorArtifactBundle:
        _fail("vector_bundle_type_invalid", "/", "Expected artifact bundle.")
    expected_source = _source_identity(bundle.owner_kind, bundle._source_owner)
    actual_source = {
        "owner_schema_version": bundle.owner_schema_version,
        "owner_hash": bundle.owner_hash,
        "execution_plan_hash": bundle.execution_plan_hash,
        "scaling_hash": bundle.scaling_hash,
        "dof_count": bundle.dof_count,
    }
    if actual_source != expected_source:
        _fail(
            "vector_bundle_source_mismatch",
            "/source_contract",
            "Bundle identifies another source contract.",
        )
    specs = _OWNER_VECTOR_SPECS[bundle.owner_kind]
    names = tuple(name for name, _filename, _scope in specs)
    if not isinstance(bundle._vectors, MappingProxyType):
        _fail("vector_bundle_vectors_mutable", "/artifacts", "Vector map is mutable.")
    if tuple(bundle._vectors) != names:
        _fail(
            "vector_bundle_vector_set_invalid", "/artifacts", "Vector set is invalid."
        )
    if (
        type(bundle.descriptors) is not tuple
        or tuple(row.name for row in bundle.descriptors) != names
        or any(
            type(row) is not EngineV2VectorArtifactDescriptor
            for row in bundle.descriptors
        )
    ):
        _fail(
            "vector_bundle_descriptor_set_invalid",
            "/artifacts",
            "Descriptor set or order is invalid.",
        )
    source_content_hashes = _source_content_hashes(
        bundle.owner_kind, bundle._source_owner
    )
    for descriptor, (name, _filename, scope) in zip(
        bundle.descriptors, specs, strict=True
    ):
        vector = bundle._vectors[name]
        _validate_vector(vector, shape=(bundle.dof_count,), path=f"/vectors/{name}")
        expected = _descriptor(
            name=name,
            vector=vector,
            equation_scope=scope,
            owner_kind=bundle.owner_kind,
            owner_hash=bundle.owner_hash,
            source_vector_content_hash=source_content_hashes[name],
            artifact_uri=descriptor.artifact_uri,
        )
        if descriptor != expected:
            _fail(
                "vector_bundle_descriptor_mismatch",
                f"/artifacts/{name}",
                "Descriptor does not match exact source bytes.",
            )
    validate_engine_v2_vector_artifact_manifest(
        _bundle_payload(bundle, include_bundle_hash=True)
    )
    if bundle.bundle_hash != _bundle_hash(bundle):
        _fail("vector_bundle_hash_mismatch", "/bundle_hash", "Bundle hash is stale.")
    return bundle


def validate_engine_v2_vector_artifact_manifest(
    payload: Any,
) -> Mapping[str, Any]:
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail("vector_bundle_schema_invalid", path or "/", error.message)
    if not isinstance(payload, Mapping):  # pragma: no cover
        _fail("vector_bundle_manifest_type_invalid", "/", "Expected an object.")
    source = payload["source_contract"]
    specs = _OWNER_VECTOR_SPECS[source["owner_kind"]]
    artifacts = payload["artifacts"]
    if [row["name"] for row in artifacts] != [row[0] for row in specs]:
        _fail(
            "vector_bundle_artifact_order_invalid",
            "/artifacts",
            "Artifact set or order is invalid.",
        )
    uris: list[str] = []
    for index, (artifact, (name, filename, scope)) in enumerate(
        zip(artifacts, specs, strict=True)
    ):
        if (
            artifact["shape"] != [source["dof_count"]]
            or artifact["byte_length"] != source["dof_count"] * 8
            or artifact["equation_scope"] != scope
            or not artifact["artifact_uri"].endswith(f"/{filename}")
        ):
            _fail(
                "vector_bundle_descriptor_semantics_invalid",
                f"/artifacts/{index}",
                "Descriptor shape, scope, byte length, or URI is stale.",
            )
        uris.append(artifact["artifact_uri"])
        if source["owner_kind"] == "equation_scaling":
            if artifact["source_vector_content_hash"] is None:
                _fail(
                    "vector_bundle_source_content_hash_missing",
                    f"/artifacts/{index}/source_vector_content_hash",
                    "EquationScaling content hash binding is required.",
                )
        elif artifact["source_vector_content_hash"] is not None:
            _fail(
                "vector_bundle_source_content_hash_unexpected",
                f"/artifacts/{index}/source_vector_content_hash",
                "ScaledResidualTrace v1 exposes raw data hashes only.",
            )
    if len(set(uris)) != len(uris):
        _fail(
            "vector_bundle_artifact_uri_duplicate",
            "/artifacts",
            "Artifact URIs must be unique.",
        )
    without_hash = dict(payload)
    claimed_hash = without_hash.pop("bundle_hash")
    if claimed_hash != canonical_hash(without_hash):
        _fail("vector_bundle_hash_mismatch", "/bundle_hash", "Bundle hash is stale.")
    return payload


def write_engine_v2_vector_artifacts(
    bundle: EngineV2VectorArtifactBundle,
    output_directory: str | Path,
) -> EngineV2VectorArtifactBundle:
    validated = validate_engine_v2_vector_artifact_bundle(bundle)
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    specs = _OWNER_VECTOR_SPECS[validated.owner_kind]
    targets = {name: directory / filename for name, filename, _scope in specs}
    for index, (name, target) in enumerate(targets.items()):
        if target.exists():
            _fail(
                "vector_bundle_target_exists",
                f"/artifacts/{index}",
                f"Refusing to overwrite existing artifact: {target}",
            )
    created: list[Path] = []
    try:
        for name, target in targets.items():
            with target.open("xb") as handle:
                created.append(target)
                handle.write(memoryview(validated.vector(name)).cast("B"))
            validate_engine_v2_vector_artifact_bytes(
                validated, name=name, data=target.read_bytes()
            )
    except Exception:
        for target in reversed(created):
            target.unlink(missing_ok=True)
        raise
    return validated


def validate_engine_v2_vector_artifact_bytes(
    bundle: EngineV2VectorArtifactBundle,
    *,
    name: str,
    data: bytes | bytearray | memoryview,
) -> None:
    validated = validate_engine_v2_vector_artifact_bundle(bundle)
    descriptor_by_name = {row.name: row for row in validated.descriptors}
    if name not in descriptor_by_name:
        _fail("vector_bundle_artifact_name_invalid", "/artifacts", "Unknown vector.")
    descriptor = descriptor_by_name[name]
    raw = bytes(data)
    if len(raw) != descriptor.byte_length:
        _fail(
            "vector_bundle_artifact_length_mismatch",
            f"/artifacts/{name}/byte_length",
            "Artifact byte length is stale.",
        )
    values = np.frombuffer(raw, dtype="<f8")
    expected = _descriptor(
        name=name,
        vector=values,
        equation_scope=descriptor.equation_scope,
        owner_kind=validated.owner_kind,
        owner_hash=validated.owner_hash,
        source_vector_content_hash=descriptor.source_vector_content_hash,
        artifact_uri=descriptor.artifact_uri,
    )
    if expected != descriptor:
        _fail(
            "vector_bundle_artifact_hash_mismatch",
            f"/artifacts/{name}",
            "Artifact bytes do not match the descriptor.",
        )


def _create_bundle(
    *,
    owner_kind: str,
    owner: EquationScaling | ScaledResidualTrace,
    owner_schema_version: str,
    owner_hash: str,
    execution_plan_hash: str,
    scaling_hash: str,
    vectors: Mapping[str, np.ndarray],
    source_content_hashes: Mapping[str, str | None],
    artifact_uri_prefix: str,
) -> EngineV2VectorArtifactBundle:
    prefix = _artifact_uri_prefix(artifact_uri_prefix)
    specs = _OWNER_VECTOR_SPECS[owner_kind]
    frozen_vectors = MappingProxyType(dict(vectors))
    dof_count = int(next(iter(frozen_vectors.values())).size)
    descriptors = tuple(
        _descriptor(
            name=name,
            vector=frozen_vectors[name],
            equation_scope=scope,
            owner_kind=owner_kind,
            owner_hash=owner_hash,
            source_vector_content_hash=source_content_hashes[name],
            artifact_uri=f"{prefix}/{filename}",
        )
        for name, filename, scope in specs
    )
    provisional = EngineV2VectorArtifactBundle(
        schema_version=ENGINE_V2_VECTOR_ARTIFACT_SCHEMA_VERSION,
        storage_profile=ENGINE_V2_VECTOR_STORAGE_PROFILE,
        bundle_hash=_HASH_ZERO,
        owner_kind=owner_kind,
        owner_schema_version=owner_schema_version,
        owner_hash=owner_hash,
        execution_plan_hash=execution_plan_hash,
        scaling_hash=scaling_hash,
        dof_count=dof_count,
        descriptors=descriptors,
        _vectors=frozen_vectors,
        _source_owner=owner,
    )
    bundle = replace(provisional, bundle_hash=_bundle_hash(provisional))
    return validate_engine_v2_vector_artifact_bundle(bundle)


def _source_identity(
    owner_kind: str, owner: EquationScaling | ScaledResidualTrace
) -> dict[str, Any]:
    if owner_kind == "equation_scaling":
        if type(owner) is not EquationScaling:
            _fail(
                "vector_bundle_source_type_invalid",
                "/source_contract",
                "Expected EquationScaling source.",
            )
        scaling = validate_equation_scaling(owner)
        return {
            "owner_schema_version": scaling.schema_version,
            "owner_hash": scaling.scaling_hash,
            "execution_plan_hash": scaling.base_plan_hash,
            "scaling_hash": scaling.scaling_hash,
            "dof_count": scaling.dof_count,
        }
    if owner_kind == "scaled_residual_trace":
        if type(owner) is not ScaledResidualTrace:
            _fail(
                "vector_bundle_source_type_invalid",
                "/source_contract",
                "Expected ScaledResidualTrace source.",
            )
        trace = validate_scaled_residual_trace(owner)
        return {
            "owner_schema_version": trace.schema_version,
            "owner_hash": trace.trace_hash,
            "execution_plan_hash": trace.execution_plan_hash,
            "scaling_hash": trace.scaling_hash,
            "dof_count": int(trace.raw_residual_si.size),
        }
    _fail(
        "vector_bundle_owner_kind_invalid",
        "/source_contract/owner_kind",
        "Unsupported source contract kind.",
    )


def _source_content_hashes(
    owner_kind: str, owner: EquationScaling | ScaledResidualTrace
) -> dict[str, str | None]:
    if owner_kind == "equation_scaling":
        assert isinstance(owner, EquationScaling)
        return {"scale_divisors_si": owner.scale_vector_content_hash}
    return {"raw_residual_si": None, "scaled_residual": None}


def _descriptor(
    *,
    name: str,
    vector: np.ndarray,
    equation_scope: str,
    owner_kind: str,
    owner_hash: str,
    source_vector_content_hash: str | None,
    artifact_uri: str,
) -> EngineV2VectorArtifactDescriptor:
    metadata = {
        "name": name,
        "dtype": "<f8",
        "shape": list(vector.shape),
        "layout": "C",
        "byte_order": "little",
        "equation_scope": equation_scope,
        "byte_length": int(vector.nbytes),
        "owner_kind": owner_kind,
        "owner_hash": owner_hash,
    }
    return EngineV2VectorArtifactDescriptor(
        name=name,
        dtype="<f8",
        shape=tuple(int(value) for value in vector.shape),
        layout="C",
        byte_order="little",
        equation_scope=equation_scope,
        byte_length=int(vector.nbytes),
        data_hash=array_data_hash(vector),
        content_hash=array_content_hash(metadata, vector),
        source_vector_content_hash=source_vector_content_hash,
        artifact_uri=artifact_uri,
    )


def _bundle_payload(
    bundle: EngineV2VectorArtifactBundle, *, include_bundle_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": bundle.schema_version,
        "storage_profile": bundle.storage_profile,
        "source_contract": {
            "owner_kind": bundle.owner_kind,
            "owner_schema_version": bundle.owner_schema_version,
            "owner_hash": bundle.owner_hash,
            "execution_plan_hash": bundle.execution_plan_hash,
            "scaling_hash": bundle.scaling_hash,
            "dof_count": bundle.dof_count,
        },
        "artifacts": [row.to_dict() for row in bundle.descriptors],
        "claim_boundary": {
            "inline_vectors": False,
            "canonical_little_endian_binary": True,
            "source_contract_authority_unchanged": True,
            "solver_or_result_authority": False,
        },
    }
    if include_bundle_hash:
        payload["bundle_hash"] = bundle.bundle_hash
    return payload


def _bundle_hash(bundle: EngineV2VectorArtifactBundle) -> str:
    return canonical_hash(_bundle_payload(bundle, include_bundle_hash=False))


def _validate_vector(vector: Any, *, shape: tuple[int, ...], path: str) -> None:
    if (
        not isinstance(vector, np.ndarray)
        or vector.dtype.str != "<f8"
        or vector.shape != shape
        or not vector.flags.c_contiguous
        or vector.flags.writeable
        or not has_immutable_bytes_backing(vector)
        or not np.all(np.isfinite(vector))
    ):
        _fail(
            "vector_bundle_vector_contract_invalid",
            path,
            "Expected immutable, finite canonical little-endian fp64 vector.",
        )


def _artifact_uri_prefix(value: Any) -> str:
    if type(value) is not str:
        _fail(
            "vector_bundle_artifact_uri_invalid",
            "/artifact_uri_prefix",
            "Expected text.",
        )
    normalized = value.rstrip("/")
    if not normalized or any(ord(character) < 32 for character in normalized):
        _fail(
            "vector_bundle_artifact_uri_invalid",
            "/artifact_uri_prefix",
            "Expected nonempty printable text.",
        )
    return normalized


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    resource = resources.files("structural_analysis.schemas").joinpath(
        "engine_v2_vector_artifacts_v1.schema.json"
    )
    with resource.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return _StrictDraft202012Validator(schema)


def _fail(code: str, path: str, message: str) -> None:
    raise EngineV2VectorArtifactError(code, path, message)
