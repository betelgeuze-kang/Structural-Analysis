"""Backend-neutral ordered material-state bundle contract.

``MaterialStateBundle`` binds opaque integration-point state bytes to one exact
model, execution plan, and solver ``StateIR`` hash.  It provides immutable
accepted/trial lineage and deterministic ordering without interpreting a
material law or granting numerical/engineering result authority.

The contract is deliberately descriptor-first: manifests contain identities,
byte lengths, and hashes, while the Python object retains immutable ``bytes``
for local validation.  Higher-level assemblers remain responsible for proving
that each material state was produced by the correct constitutive integration
and that a solver trial passed residual/increment gates before commit.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
import hashlib
from importlib import resources
import json
import re
from types import MappingProxyType
from typing import Any, Literal

from jsonschema import Draft202012Validator, validators

from structural_analysis.engine_v2.contracts._canonical import canonical_hash


MATERIAL_STATE_BUNDLE_SCHEMA_VERSION = (
    "structural-analysis-material-state-bundle.v1"
)
MATERIAL_STATE_BUNDLE_STORAGE_PROFILE = (
    "ordered_opaque_integration_point_state_bytes.v1"
)
MATERIAL_STATE_BUNDLE_AUTHORITY_PROFILE = (
    "non_authoritative_constitutive_state_transport.v1"
)
MATERIAL_STATE_BUNDLE_CLAIM_BOUNDARY = MappingProxyType(
    {
        "constitutive_state_bytes_bound": True,
        "integration_point_order_bound": True,
        "accepted_trial_lineage_bound": True,
        "constitutive_law_verified": False,
        "solver_convergence_authority": False,
        "numerical_result_authority": False,
        "engineering_result_authority": False,
        "release_readiness": False,
        "commercial_use": False,
    }
)

_HASH_ZERO = "sha256:" + "0" * 64
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_URI_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://\S+$")
_MAX_INDEX = 2**31 - 1
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator,
    type_checker=_STRICT_JSON_TYPE_CHECKER,
)


class MaterialStateBundleError(ValueError):
    """Stable fail-closed material-state contract error."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class MaterialStateInput:
    """One caller-supplied opaque material-state artifact."""

    entity_id: str
    integration_point_id: str
    material_type_id: str
    material_schema_version: str
    state_bytes: bytes
    parent_state_data_hash: str | None = None
    artifact_uri: str | None = None


@dataclass(frozen=True)
class MaterialStateEntryDescriptor:
    index: int
    entity_id: str
    integration_point_id: str
    material_type_id: str
    material_schema_version: str
    byte_length: int
    data_hash: str
    content_hash: str
    parent_state_data_hash: str | None
    artifact_uri: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "index": self.index,
            "entity_id": self.entity_id,
            "integration_point_id": self.integration_point_id,
            "material_type_id": self.material_type_id,
            "material_schema_version": self.material_schema_version,
            "byte_length": self.byte_length,
            "data_hash": self.data_hash,
            "content_hash": self.content_hash,
            "parent_state_data_hash": self.parent_state_data_hash,
        }
        if self.artifact_uri is not None:
            payload["artifact_uri"] = self.artifact_uri
        return payload


@dataclass(frozen=True)
class MaterialStateBundle:
    schema_version: str
    bundle_id: str
    bundle_hash: str
    storage_profile: str
    authority_profile: str
    model_ir_content_hash: str
    execution_plan_hash: str
    solver_state_hash: str
    role: Literal["committed", "trial"]
    epoch: int
    parent_bundle_hash: str | None
    integration_point_order_hash: str
    entry_count: int
    total_byte_length: int
    entries: tuple[MaterialStateEntryDescriptor, ...]
    extensions: Mapping[str, Any]
    _state_bytes: tuple[bytes, ...]

    def state_bytes(self, index: int) -> bytes:
        normalized = _require_index(index, "/index")
        try:
            return self._state_bytes[normalized]
        except IndexError as exc:
            _fail(
                "material_state_index_out_of_range",
                "/index",
                "Material-state index is outside the bundle.",
                cause=exc,
            )

    def to_manifest(self) -> dict[str, Any]:
        validate_material_state_bundle(self)
        return _bundle_payload(self, include_bundle_hash=True)


def create_initial_material_state_bundle(
    *,
    bundle_id: str,
    model_ir_content_hash: str,
    execution_plan_hash: str,
    solver_state_hash: str,
    entries: Sequence[MaterialStateInput],
) -> MaterialStateBundle:
    """Create an unparented committed epoch-zero material state."""

    normalized_entries = _normalize_inputs(
        entries,
        expected_parent_hashes=None,
        initial=True,
    )
    return _build_bundle(
        bundle_id=bundle_id,
        model_ir_content_hash=model_ir_content_hash,
        execution_plan_hash=execution_plan_hash,
        solver_state_hash=solver_state_hash,
        role="committed",
        epoch=0,
        parent_bundle_hash=None,
        entries=normalized_entries,
    )


def open_trial_material_state_bundle(
    accepted: MaterialStateBundle,
    *,
    solver_state_hash: str,
    entries: Sequence[MaterialStateInput],
    bundle_id: str | None = None,
) -> MaterialStateBundle:
    """Open one immutable trial from a committed material-state parent."""

    validate_material_state_bundle(accepted)
    if accepted.role != "committed":
        _fail(
            "accepted_material_bundle_role_invalid",
            "/role",
            "A material-state trial can only be opened from a committed bundle.",
        )
    expected_parent_hashes = tuple(row.data_hash for row in accepted.entries)
    normalized_entries = _normalize_inputs(
        entries,
        expected_parent_hashes=expected_parent_hashes,
        initial=False,
    )
    _validate_input_identity_against_bundle(
        normalized_entries,
        accepted,
        path="/entries",
    )
    next_epoch = accepted.epoch + 1
    return _build_bundle(
        bundle_id=(
            bundle_id
            or f"material-state.trial.e{next_epoch}.{accepted.bundle_id}"
        ),
        model_ir_content_hash=accepted.model_ir_content_hash,
        execution_plan_hash=accepted.execution_plan_hash,
        solver_state_hash=solver_state_hash,
        role="trial",
        epoch=next_epoch,
        parent_bundle_hash=accepted.bundle_hash,
        entries=normalized_entries,
    )


def commit_trial_material_state_bundle(
    accepted: MaterialStateBundle,
    trial: MaterialStateBundle,
    *,
    solver_state_hash: str,
    bundle_id: str | None = None,
) -> MaterialStateBundle:
    """Commit a validated trial without changing its material-state bytes."""

    _validate_trial_transition(accepted, trial)
    inputs = tuple(
        MaterialStateInput(
            entity_id=descriptor.entity_id,
            integration_point_id=descriptor.integration_point_id,
            material_type_id=descriptor.material_type_id,
            material_schema_version=descriptor.material_schema_version,
            state_bytes=trial.state_bytes(descriptor.index),
            parent_state_data_hash=descriptor.parent_state_data_hash,
            artifact_uri=descriptor.artifact_uri,
        )
        for descriptor in trial.entries
    )
    return _build_bundle(
        bundle_id=(
            bundle_id
            or f"material-state.committed.e{trial.epoch}.{accepted.bundle_id}"
        ),
        model_ir_content_hash=trial.model_ir_content_hash,
        execution_plan_hash=trial.execution_plan_hash,
        solver_state_hash=solver_state_hash,
        role="committed",
        epoch=trial.epoch,
        parent_bundle_hash=trial.bundle_hash,
        entries=inputs,
    )


def rollback_trial_material_state_bundle(
    accepted: MaterialStateBundle,
    trial: MaterialStateBundle,
) -> MaterialStateBundle:
    """Reject a trial and return the exact accepted object."""

    _validate_trial_transition(accepted, trial)
    return accepted


def validate_material_state_bundle(
    bundle: MaterialStateBundle,
) -> MaterialStateBundle:
    """Recompute all descriptor, byte, ordering, and lineage invariants."""

    if type(bundle) is not MaterialStateBundle:
        _fail(
            "material_state_bundle_type_invalid",
            "/",
            "Expected a MaterialStateBundle instance.",
        )
    if bundle.schema_version != MATERIAL_STATE_BUNDLE_SCHEMA_VERSION:
        _fail(
            "material_state_bundle_schema_invalid",
            "/schema_version",
            "Unsupported material-state bundle schema.",
        )
    if bundle.storage_profile != MATERIAL_STATE_BUNDLE_STORAGE_PROFILE:
        _fail(
            "material_state_storage_profile_invalid",
            "/storage_profile",
            "Unsupported material-state storage profile.",
        )
    if bundle.authority_profile != MATERIAL_STATE_BUNDLE_AUTHORITY_PROFILE:
        _fail(
            "material_state_authority_profile_invalid",
            "/authority_profile",
            "Material-state transport cannot acquire result authority.",
        )

    _require_stable_id(bundle.bundle_id, "/bundle_id")
    for path, value in (
        ("/bundle_hash", bundle.bundle_hash),
        ("/bindings/model_ir_content_hash", bundle.model_ir_content_hash),
        ("/bindings/execution_plan_hash", bundle.execution_plan_hash),
        ("/bindings/solver_state_hash", bundle.solver_state_hash),
        (
            "/integration_point_order_hash",
            bundle.integration_point_order_hash,
        ),
    ):
        _require_hash(value, path)
    if bundle.parent_bundle_hash is not None:
        _require_hash(bundle.parent_bundle_hash, "/parent_bundle_hash")
        if bundle.parent_bundle_hash == bundle.bundle_hash:
            _fail(
                "material_state_parent_cycle",
                "/parent_bundle_hash",
                "A material-state bundle cannot parent itself.",
            )

    if bundle.role not in ("committed", "trial"):
        _fail(
            "material_state_role_invalid",
            "/role",
            "Unknown material-state bundle role.",
        )
    epoch = _require_index(bundle.epoch, "/epoch")
    if epoch == 0:
        if bundle.role != "committed" or bundle.parent_bundle_hash is not None:
            _fail(
                "initial_material_state_lineage_invalid",
                "/parent_bundle_hash",
                "Epoch zero must be an unparented committed bundle.",
            )
    elif bundle.parent_bundle_hash is None:
        _fail(
            "material_state_parent_missing",
            "/parent_bundle_hash",
            "Every non-initial material-state bundle needs a parent.",
        )
    if bundle.role == "trial" and epoch == 0:
        _fail(
            "material_state_trial_epoch_invalid",
            "/epoch",
            "A trial material-state epoch must be positive.",
        )

    if type(bundle.entries) is not tuple or not bundle.entries:
        _fail(
            "material_state_entries_invalid",
            "/entries",
            "Material-state entries must be a non-empty tuple.",
        )
    if type(bundle._state_bytes) is not tuple:
        _fail(
            "material_state_bytes_container_mutable",
            "/artifacts",
            "Material-state byte artifacts must use an immutable tuple.",
        )
    if len(bundle.entries) != len(bundle._state_bytes):
        _fail(
            "material_state_artifact_count_mismatch",
            "/artifacts",
            "Descriptor and artifact counts differ.",
        )
    if bundle.entry_count != len(bundle.entries):
        _fail(
            "material_state_entry_count_mismatch",
            "/entry_count",
            "entry_count does not match the descriptor set.",
        )

    expected_descriptors: list[MaterialStateEntryDescriptor] = []
    for index, (descriptor, state_bytes) in enumerate(
        zip(bundle.entries, bundle._state_bytes, strict=True)
    ):
        if type(descriptor) is not MaterialStateEntryDescriptor:
            _fail(
                "material_state_descriptor_type_invalid",
                f"/entries/{index}",
                "Expected MaterialStateEntryDescriptor.",
            )
        normalized_input = MaterialStateInput(
            entity_id=descriptor.entity_id,
            integration_point_id=descriptor.integration_point_id,
            material_type_id=descriptor.material_type_id,
            material_schema_version=descriptor.material_schema_version,
            state_bytes=_require_bytes(
                state_bytes,
                f"/artifacts/{index}",
            ),
            parent_state_data_hash=descriptor.parent_state_data_hash,
            artifact_uri=descriptor.artifact_uri,
        )
        expected_descriptors.append(
            _descriptor(index=index, value=normalized_input)
        )
        if descriptor != expected_descriptors[-1]:
            _fail(
                "material_state_descriptor_mismatch",
                f"/entries/{index}",
                "Descriptor does not match retained state bytes and metadata.",
            )
        if epoch == 0 and descriptor.parent_state_data_hash is not None:
            _fail(
                "initial_material_entry_parent_invalid",
                f"/entries/{index}/parent_state_data_hash",
                "Initial material-state entries cannot identify parents.",
            )
        if epoch > 0 and descriptor.parent_state_data_hash is None:
            _fail(
                "material_entry_parent_missing",
                f"/entries/{index}/parent_state_data_hash",
                "Non-initial material-state entries must identify parents.",
            )

    expected_total = sum(row.byte_length for row in expected_descriptors)
    if bundle.total_byte_length != expected_total:
        _fail(
            "material_state_total_byte_length_mismatch",
            "/total_byte_length",
            "total_byte_length does not match retained artifacts.",
        )
    expected_order_hash = _order_hash(tuple(expected_descriptors))
    if bundle.integration_point_order_hash != expected_order_hash:
        _fail(
            "material_state_order_hash_mismatch",
            "/integration_point_order_hash",
            "Integration-point identity or order changed.",
        )
    if not isinstance(bundle.extensions, MappingProxyType) or bundle.extensions:
        _fail(
            "material_state_extensions_invalid",
            "/extensions",
            "MaterialStateBundle v1 requires an immutable empty extensions object.",
        )
    expected_hash = canonical_hash(
        _bundle_payload(bundle, include_bundle_hash=False)
    )
    if bundle.bundle_hash != expected_hash:
        _fail(
            "material_state_bundle_hash_mismatch",
            "/bundle_hash",
            "Bundle hash does not match canonical manifest content.",
        )
    return bundle


def validate_material_state_entry_bytes(
    bundle: MaterialStateBundle,
    *,
    index: int,
    state_bytes: bytes,
) -> bytes:
    """Validate one externally supplied artifact against its descriptor."""

    validate_material_state_bundle(bundle)
    normalized_index = _require_index(index, "/index")
    if normalized_index >= bundle.entry_count:
        _fail(
            "material_state_index_out_of_range",
            "/index",
            "Material-state index is outside the bundle.",
        )
    normalized_bytes = _require_bytes(state_bytes, "/state_bytes")
    descriptor = bundle.entries[normalized_index]
    if len(normalized_bytes) != descriptor.byte_length:
        _fail(
            "material_state_byte_length_mismatch",
            "/state_bytes",
            "Artifact byte length does not match the descriptor.",
        )
    if _data_hash(normalized_bytes) != descriptor.data_hash:
        _fail(
            "material_state_data_hash_mismatch",
            "/state_bytes",
            "Artifact bytes do not match the descriptor data hash.",
        )
    return normalized_bytes


def validate_material_state_bundle_manifest(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a descriptor-only imported manifest without fabricating bytes."""

    if not isinstance(payload, Mapping):
        _fail(
            "material_state_manifest_type_invalid",
            "/",
            "Material-state manifest must be an object.",
        )
    normalized = json.loads(json.dumps(dict(payload), allow_nan=False))
    errors = sorted(
        _manifest_validator().iter_errors(normalized),
        key=lambda row: tuple(str(value) for value in row.absolute_path),
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(value) for value in first.absolute_path)
        _fail(
            "material_state_manifest_schema_invalid",
            path or "/",
            first.message,
        )

    entries = normalized["entries"]
    for index, entry in enumerate(entries):
        expected_content_hash = canonical_hash(
            _entry_payload_from_manifest(entry, include_content_hash=False)
        )
        if entry["content_hash"] != expected_content_hash:
            _fail(
                "material_state_entry_content_hash_mismatch",
                f"/entries/{index}/content_hash",
                "Entry content hash does not match its descriptor metadata.",
            )
    if normalized["entry_count"] != len(entries):
        _fail(
            "material_state_entry_count_mismatch",
            "/entry_count",
            "entry_count does not match entries.",
        )
    if normalized["total_byte_length"] != sum(
        entry["byte_length"] for entry in entries
    ):
        _fail(
            "material_state_total_byte_length_mismatch",
            "/total_byte_length",
            "total_byte_length does not match entries.",
        )
    expected_order_hash = canonical_hash(
        [
            {
                "index": entry["index"],
                "entity_id": entry["entity_id"],
                "integration_point_id": entry["integration_point_id"],
                "material_type_id": entry["material_type_id"],
                "material_schema_version": entry["material_schema_version"],
            }
            for entry in entries
        ]
    )
    if normalized["integration_point_order_hash"] != expected_order_hash:
        _fail(
            "material_state_order_hash_mismatch",
            "/integration_point_order_hash",
            "Integration-point order hash does not match entries.",
        )
    expected_bundle_hash = canonical_hash(
        {
            key: value
            for key, value in normalized.items()
            if key != "bundle_hash"
        }
    )
    if normalized["bundle_hash"] != expected_bundle_hash:
        _fail(
            "material_state_bundle_hash_mismatch",
            "/bundle_hash",
            "Bundle hash does not match canonical manifest content.",
        )
    return normalized


def _build_bundle(
    *,
    bundle_id: str,
    model_ir_content_hash: str,
    execution_plan_hash: str,
    solver_state_hash: str,
    role: Literal["committed", "trial"],
    epoch: int,
    parent_bundle_hash: str | None,
    entries: Sequence[MaterialStateInput],
) -> MaterialStateBundle:
    normalized_id = _require_stable_id(bundle_id, "/bundle_id")
    model_hash = _require_hash(
        model_ir_content_hash,
        "/bindings/model_ir_content_hash",
    )
    plan_hash = _require_hash(
        execution_plan_hash,
        "/bindings/execution_plan_hash",
    )
    state_hash = _require_hash(
        solver_state_hash,
        "/bindings/solver_state_hash",
    )
    normalized_epoch = _require_index(epoch, "/epoch")
    if parent_bundle_hash is not None:
        parent_bundle_hash = _require_hash(
            parent_bundle_hash,
            "/parent_bundle_hash",
        )
    normalized_inputs = tuple(entries)
    if not normalized_inputs:
        _fail(
            "material_state_entries_empty",
            "/entries",
            "At least one material-state entry is required.",
        )
    descriptors = tuple(
        _descriptor(index=index, value=value)
        for index, value in enumerate(normalized_inputs)
    )
    state_bytes = tuple(
        _require_bytes(value.state_bytes, f"/artifacts/{index}")
        for index, value in enumerate(normalized_inputs)
    )
    provisional = MaterialStateBundle(
        schema_version=MATERIAL_STATE_BUNDLE_SCHEMA_VERSION,
        bundle_id=normalized_id,
        bundle_hash=_HASH_ZERO,
        storage_profile=MATERIAL_STATE_BUNDLE_STORAGE_PROFILE,
        authority_profile=MATERIAL_STATE_BUNDLE_AUTHORITY_PROFILE,
        model_ir_content_hash=model_hash,
        execution_plan_hash=plan_hash,
        solver_state_hash=state_hash,
        role=role,
        epoch=normalized_epoch,
        parent_bundle_hash=parent_bundle_hash,
        integration_point_order_hash=_order_hash(descriptors),
        entry_count=len(descriptors),
        total_byte_length=sum(row.byte_length for row in descriptors),
        entries=descriptors,
        extensions=MappingProxyType({}),
        _state_bytes=state_bytes,
    )
    bundle = replace(
        provisional,
        bundle_hash=canonical_hash(
            _bundle_payload(provisional, include_bundle_hash=False)
        ),
    )
    return validate_material_state_bundle(bundle)


def _normalize_inputs(
    values: Sequence[MaterialStateInput],
    *,
    expected_parent_hashes: tuple[str, ...] | None,
    initial: bool,
) -> tuple[MaterialStateInput, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(
        values,
        Sequence,
    ):
        _fail(
            "material_state_inputs_invalid",
            "/entries",
            "Material-state inputs must be a non-string sequence.",
        )
    normalized: list[MaterialStateInput] = []
    if expected_parent_hashes is not None and len(values) != len(
        expected_parent_hashes
    ):
        _fail(
            "material_state_input_count_mismatch",
            "/entries",
            "Trial entry count must match the accepted bundle.",
        )
    for index, value in enumerate(values):
        if type(value) is not MaterialStateInput:
            _fail(
                "material_state_input_type_invalid",
                f"/entries/{index}",
                "Expected MaterialStateInput.",
            )
        parent_hash = value.parent_state_data_hash
        if initial:
            if parent_hash is not None:
                _fail(
                    "initial_material_entry_parent_invalid",
                    f"/entries/{index}/parent_state_data_hash",
                    "Initial material-state inputs cannot identify parents.",
                )
        else:
            assert expected_parent_hashes is not None
            expected_parent = expected_parent_hashes[index]
            if parent_hash is None:
                parent_hash = expected_parent
            elif _require_hash(
                parent_hash,
                f"/entries/{index}/parent_state_data_hash",
            ) != expected_parent:
                _fail(
                    "material_state_entry_parent_mismatch",
                    f"/entries/{index}/parent_state_data_hash",
                    "Trial material state is not derived from the accepted entry.",
                )
        normalized.append(
            MaterialStateInput(
                entity_id=_require_stable_id(
                    value.entity_id,
                    f"/entries/{index}/entity_id",
                ),
                integration_point_id=_require_stable_id(
                    value.integration_point_id,
                    f"/entries/{index}/integration_point_id",
                ),
                material_type_id=_require_stable_id(
                    value.material_type_id,
                    f"/entries/{index}/material_type_id",
                ),
                material_schema_version=_require_stable_id(
                    value.material_schema_version,
                    f"/entries/{index}/material_schema_version",
                ),
                state_bytes=_require_bytes(
                    value.state_bytes,
                    f"/artifacts/{index}",
                ),
                parent_state_data_hash=parent_hash,
                artifact_uri=_require_uri(
                    value.artifact_uri,
                    f"/entries/{index}/artifact_uri",
                ),
            )
        )
    return tuple(normalized)


def _validate_input_identity_against_bundle(
    values: Sequence[MaterialStateInput],
    bundle: MaterialStateBundle,
    *,
    path: str,
) -> None:
    for index, (value, descriptor) in enumerate(
        zip(values, bundle.entries, strict=True)
    ):
        actual = (
            value.entity_id,
            value.integration_point_id,
            value.material_type_id,
            value.material_schema_version,
        )
        expected = (
            descriptor.entity_id,
            descriptor.integration_point_id,
            descriptor.material_type_id,
            descriptor.material_schema_version,
        )
        if actual != expected:
            _fail(
                "material_state_identity_mismatch",
                f"{path}/{index}",
                "Entity, integration-point, or material identity changed.",
            )


def _validate_trial_transition(
    accepted: MaterialStateBundle,
    trial: MaterialStateBundle,
) -> None:
    validate_material_state_bundle(accepted)
    validate_material_state_bundle(trial)
    if accepted.role != "committed" or trial.role != "trial":
        _fail(
            "material_state_transition_role_invalid",
            "/role",
            "Expected committed accepted bundle and trial bundle.",
        )
    if trial.epoch != accepted.epoch + 1:
        _fail(
            "material_state_transition_epoch_invalid",
            "/epoch",
            "Trial epoch must be exactly one greater than accepted epoch.",
        )
    if trial.parent_bundle_hash != accepted.bundle_hash:
        _fail(
            "material_state_transition_parent_mismatch",
            "/parent_bundle_hash",
            "Trial bundle is not parented by the accepted bundle.",
        )
    if (
        trial.model_ir_content_hash != accepted.model_ir_content_hash
        or trial.execution_plan_hash != accepted.execution_plan_hash
        or trial.integration_point_order_hash
        != accepted.integration_point_order_hash
        or trial.entry_count != accepted.entry_count
    ):
        _fail(
            "material_state_transition_binding_mismatch",
            "/bindings",
            "Trial bundle changed model, plan, order, or entry count.",
        )
    _validate_input_identity_against_bundle(
        tuple(
            MaterialStateInput(
                entity_id=row.entity_id,
                integration_point_id=row.integration_point_id,
                material_type_id=row.material_type_id,
                material_schema_version=row.material_schema_version,
                state_bytes=trial.state_bytes(row.index),
                parent_state_data_hash=row.parent_state_data_hash,
                artifact_uri=row.artifact_uri,
            )
            for row in trial.entries
        ),
        accepted,
        path="/entries",
    )
    for index, (accepted_entry, trial_entry) in enumerate(
        zip(accepted.entries, trial.entries, strict=True)
    ):
        if trial_entry.parent_state_data_hash != accepted_entry.data_hash:
            _fail(
                "material_state_transition_entry_parent_mismatch",
                f"/entries/{index}/parent_state_data_hash",
                "Trial entry is not derived from the accepted entry bytes.",
            )


def _descriptor(
    *,
    index: int,
    value: MaterialStateInput,
) -> MaterialStateEntryDescriptor:
    normalized_index = _require_index(index, "/entries/index")
    state_bytes = _require_bytes(value.state_bytes, f"/artifacts/{index}")
    parent_hash = value.parent_state_data_hash
    if parent_hash is not None:
        parent_hash = _require_hash(
            parent_hash,
            f"/entries/{index}/parent_state_data_hash",
        )
    provisional = MaterialStateEntryDescriptor(
        index=normalized_index,
        entity_id=_require_stable_id(
            value.entity_id,
            f"/entries/{index}/entity_id",
        ),
        integration_point_id=_require_stable_id(
            value.integration_point_id,
            f"/entries/{index}/integration_point_id",
        ),
        material_type_id=_require_stable_id(
            value.material_type_id,
            f"/entries/{index}/material_type_id",
        ),
        material_schema_version=_require_stable_id(
            value.material_schema_version,
            f"/entries/{index}/material_schema_version",
        ),
        byte_length=len(state_bytes),
        data_hash=_data_hash(state_bytes),
        content_hash=_HASH_ZERO,
        parent_state_data_hash=parent_hash,
        artifact_uri=_require_uri(
            value.artifact_uri,
            f"/entries/{index}/artifact_uri",
        ),
    )
    return replace(
        provisional,
        content_hash=canonical_hash(
            _entry_payload(provisional, include_content_hash=False)
        ),
    )


def _entry_payload(
    descriptor: MaterialStateEntryDescriptor,
    *,
    include_content_hash: bool,
) -> dict[str, Any]:
    payload = descriptor.to_dict()
    if not include_content_hash:
        payload.pop("content_hash")
    return payload


def _entry_payload_from_manifest(
    entry: Mapping[str, Any],
    *,
    include_content_hash: bool,
) -> dict[str, Any]:
    payload = dict(entry)
    if not include_content_hash:
        payload.pop("content_hash", None)
    return payload


def _order_hash(
    descriptors: tuple[MaterialStateEntryDescriptor, ...],
) -> str:
    return canonical_hash(
        [
            {
                "index": row.index,
                "entity_id": row.entity_id,
                "integration_point_id": row.integration_point_id,
                "material_type_id": row.material_type_id,
                "material_schema_version": row.material_schema_version,
            }
            for row in descriptors
        ]
    )


def _bundle_payload(
    bundle: MaterialStateBundle,
    *,
    include_bundle_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": bundle.schema_version,
        "bundle_id": bundle.bundle_id,
        "bundle_hash": bundle.bundle_hash,
        "storage_profile": bundle.storage_profile,
        "authority_profile": bundle.authority_profile,
        "bindings": {
            "model_ir_content_hash": bundle.model_ir_content_hash,
            "execution_plan_hash": bundle.execution_plan_hash,
            "solver_state_hash": bundle.solver_state_hash,
        },
        "role": bundle.role,
        "epoch": bundle.epoch,
        "parent_bundle_hash": bundle.parent_bundle_hash,
        "integration_point_order_hash": bundle.integration_point_order_hash,
        "entry_count": bundle.entry_count,
        "total_byte_length": bundle.total_byte_length,
        "entries": [row.to_dict() for row in bundle.entries],
        "extensions": dict(bundle.extensions),
    }
    if not include_bundle_hash:
        payload.pop("bundle_hash")
    return payload


def _data_hash(state_bytes: bytes) -> str:
    return "sha256:" + hashlib.sha256(state_bytes).hexdigest()


def _require_bytes(value: Any, path: str) -> bytes:
    if type(value) is not bytes or not value:
        _fail(
            "material_state_bytes_invalid",
            path,
            "Material-state artifacts must be non-empty immutable bytes.",
        )
    return value


def _require_hash(value: Any, path: str) -> str:
    normalized = str(value).strip()
    if not _HASH_PATTERN.fullmatch(normalized):
        _fail(
            "material_state_hash_invalid",
            path,
            "Expected a lowercase sha256:<hex> hash.",
        )
    return normalized


def _require_stable_id(value: Any, path: str) -> str:
    normalized = str(value).strip()
    if not _STABLE_ID_PATTERN.fullmatch(normalized):
        _fail(
            "material_state_id_invalid",
            path,
            "Expected a stable non-empty identifier.",
        )
    return normalized


def _require_uri(value: Any, path: str) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not _URI_PATTERN.fullmatch(normalized):
        _fail(
            "material_state_artifact_uri_invalid",
            path,
            "Expected an absolute scheme:// artifact URI.",
        )
    return normalized


def _require_index(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_INDEX:
        _fail(
            "material_state_index_invalid",
            path,
            "Expected a non-negative 32-bit integer.",
        )
    return value


@lru_cache(maxsize=1)
def _manifest_validator() -> Draft202012Validator:
    schema_path = resources.files("structural_analysis.schemas").joinpath(
        "material_state_bundle_v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return _StrictDraft202012Validator(schema)


def _fail(
    code: str,
    path: str,
    message: str,
    *,
    cause: Exception | None = None,
) -> None:
    error = MaterialStateBundleError(code, path, message)
    if cause is not None:
        raise error from cause
    raise error


__all__ = [
    "MATERIAL_STATE_BUNDLE_AUTHORITY_PROFILE",
    "MATERIAL_STATE_BUNDLE_CLAIM_BOUNDARY",
    "MATERIAL_STATE_BUNDLE_SCHEMA_VERSION",
    "MATERIAL_STATE_BUNDLE_STORAGE_PROFILE",
    "MaterialStateBundle",
    "MaterialStateBundleError",
    "MaterialStateEntryDescriptor",
    "MaterialStateInput",
    "commit_trial_material_state_bundle",
    "create_initial_material_state_bundle",
    "open_trial_material_state_bundle",
    "rollback_trial_material_state_bundle",
    "validate_material_state_bundle",
    "validate_material_state_bundle_manifest",
    "validate_material_state_entry_bytes",
]
