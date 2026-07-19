from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import sys

from jsonschema import Draft202012Validator
import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
)
from structural_analysis.engine_v2.contracts.state_ir import (  # noqa: E402
    create_initial_state,
    open_trial_state,
)
from structural_analysis.engine_v2.contracts.state_ir_binary import (  # noqa: E402
    STATE_IR_BINARY_MANIFEST_SCHEMA_VERSION,
    STATE_IR_BINARY_STORAGE_PROFILE,
    StateIRBinaryManifestError,
    create_state_ir_binary_manifest,
    validate_state_ir_binary_artifact_bytes,
    validate_state_ir_binary_manifest,
    validate_state_ir_binary_manifest_payload,
    write_state_ir_binary_artifacts,
)

SCHEMA = (
    REPO_ROOT
    / "src/structural_analysis/schemas/state_ir_binary_manifest_v1.schema.json"
)
FILENAMES = {
    "displacement": "displacement_si.f64le",
    "velocity": "velocity_si.f64le",
    "acceleration": "acceleration_si.f64le",
    "constitutive": "constitutive_state.f64le",
}


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _plan(**changes: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "model_ir_content_hash": _hash("1"),
        "solver_numeric_buffer_hash": _hash("2"),
        "solver_entity_mapping_hash": _hash("3"),
        "solver_artifact_hash": _hash("4"),
        "plan_hash": _hash("5"),
        "operator_hash": _hash("6"),
        "load_pattern_id": "LC1",
        "node_count": 2,
        "dof_count": 12,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def _state():
    initial = create_initial_state(_plan())
    displacement = np.linspace(0.0, 0.011, initial.dof_count, dtype="<f8")
    return open_trial_state(initial, displacement, load_step=1, load_factor=0.5)


def _rehash_manifest(payload: dict) -> None:
    without_hash = {
        key: value for key, value in payload.items() if key != "manifest_hash"
    }
    payload["manifest_hash"] = canonical_hash(without_hash)


def test_binary_manifest_is_schema_valid_deterministic_and_descriptor_only() -> None:
    state = _state()
    first = create_state_ir_binary_manifest(
        state, artifact_uri_prefix="artifact://run-1/state-1/"
    )
    second = create_state_ir_binary_manifest(
        state, artifact_uri_prefix="artifact://run-1/state-1"
    )
    payload = first.to_manifest()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    assert first.schema_version == STATE_IR_BINARY_MANIFEST_SCHEMA_VERSION
    assert first.storage_profile == STATE_IR_BINARY_STORAGE_PROFILE
    assert first.manifest_hash == second.manifest_hash
    assert first.state_hash == state.state_hash
    assert first.dof_count == state.dof_count
    assert isinstance(first.vector_hashes, MappingProxyType)
    assert payload["source_state"]["vector_hashes"] == dict(state.vector_hashes)
    assert [row["name"] for row in payload["artifacts"]] == list(FILENAMES)
    assert payload["claim_boundary"] == {
        "inline_vectors": False,
        "canonical_little_endian_binary": True,
        "solver_or_result_authority": False,
    }
    assert "kinematics" not in payload
    assert all("values" not in descriptor for descriptor in payload["artifacts"])
    for descriptor in first.descriptors:
        expected_count = state.dof_count if descriptor.name != "constitutive" else 0
        assert descriptor.dtype == "<f8"
        assert descriptor.shape == (expected_count,)
        assert descriptor.byte_length == expected_count * 8
        assert descriptor.data_hash == state.vector_hashes[descriptor.name]
        assert descriptor.artifact_uri.endswith(FILENAMES[descriptor.name])

    with pytest.raises(TypeError):
        first.vector_hashes["displacement"] = _hash("f")


def test_writer_emits_exact_bytes_and_refuses_all_overwrites(tmp_path: Path) -> None:
    state = _state()
    output = tmp_path / "state"
    manifest = write_state_ir_binary_artifacts(
        state,
        output,
        artifact_uri_prefix="artifact://run-1/state-1",
    )

    arrays = {
        "displacement": state.displacement_si,
        "velocity": state.velocity_si,
        "acceleration": state.acceleration_si,
        "constitutive": np.asarray([], dtype="<f8"),
    }
    before: dict[str, bytes] = {}
    for name, filename in FILENAMES.items():
        raw = (output / filename).read_bytes()
        before[name] = raw
        assert raw == memoryview(arrays[name]).cast("B").tobytes()
        validate_state_ir_binary_artifact_bytes(manifest, name=name, data=raw)

    with pytest.raises(StateIRBinaryManifestError) as error:
        write_state_ir_binary_artifacts(
            state,
            output,
            artifact_uri_prefix="artifact://run-1/state-1",
        )
    assert error.value.code == "state_binary_target_exists"
    assert {
        name: (output / filename).read_bytes() for name, filename in FILENAMES.items()
    } == before

    later_collision = tmp_path / "later-collision"
    later_collision.mkdir()
    existing = later_collision / FILENAMES["acceleration"]
    existing.write_bytes(b"preexisting")
    with pytest.raises(StateIRBinaryManifestError) as preflight_error:
        write_state_ir_binary_artifacts(
            state,
            later_collision,
            artifact_uri_prefix="artifact://run-1/state-1",
        )
    assert preflight_error.value.code == "state_binary_target_exists"
    assert existing.read_bytes() == b"preexisting"
    assert not (later_collision / FILENAMES["displacement"]).exists()
    assert not (later_collision / FILENAMES["velocity"]).exists()


def test_writer_removes_only_files_created_by_a_failed_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from structural_analysis.engine_v2.contracts import state_ir_binary

    state = _state()
    output = tmp_path / "failed-state"
    real_validator = state_ir_binary.validate_state_ir_binary_artifact_bytes

    def fail_on_velocity(manifest, *, name, data):
        if name == "velocity":
            raise OSError("simulated storage failure")
        return real_validator(manifest, name=name, data=data)

    monkeypatch.setattr(
        state_ir_binary,
        "validate_state_ir_binary_artifact_bytes",
        fail_on_velocity,
    )
    with pytest.raises(OSError, match="simulated storage failure"):
        write_state_ir_binary_artifacts(
            state,
            output,
            artifact_uri_prefix="artifact://run-1/state-1",
        )

    assert output.exists()
    assert list(output.iterdir()) == []


def test_artifact_byte_validation_fails_closed_on_tamper_and_truncation() -> None:
    state = _state()
    manifest = create_state_ir_binary_manifest(
        state, artifact_uri_prefix="artifact://run-1/state-1"
    )
    raw = bytearray(memoryview(state.displacement_si).cast("B"))
    raw[7] ^= 1

    with pytest.raises(StateIRBinaryManifestError) as tamper_error:
        validate_state_ir_binary_artifact_bytes(manifest, name="displacement", data=raw)
    assert tamper_error.value.code == "state_binary_artifact_hash_mismatch"

    with pytest.raises(StateIRBinaryManifestError) as length_error:
        validate_state_ir_binary_artifact_bytes(
            manifest,
            name="displacement",
            data=raw[:-1],
        )
    assert length_error.value.code == "state_binary_artifact_length_mismatch"


def test_manifest_rejects_stale_and_coherently_rehashed_descriptor_tamper() -> None:
    manifest = create_state_ir_binary_manifest(
        _state(), artifact_uri_prefix="artifact://run-1/state-1"
    )
    stale = deepcopy(manifest.to_manifest())
    stale["artifacts"][0]["artifact_uri"] = "artifact://another/displacement_si.f64le"
    with pytest.raises(StateIRBinaryManifestError) as stale_error:
        validate_state_ir_binary_manifest_payload(stale)
    assert stale_error.value.code == "state_binary_manifest_hash_mismatch"

    forged = deepcopy(manifest.to_manifest())
    forged["artifacts"][0]["shape"] = [6]
    forged["artifacts"][0]["byte_length"] = 48
    _rehash_manifest(forged)
    with pytest.raises(StateIRBinaryManifestError) as semantic_error:
        validate_state_ir_binary_manifest_payload(forged)
    assert semantic_error.value.code == "state_binary_descriptor_semantics_invalid"

    wrong_uri = deepcopy(manifest.to_manifest())
    wrong_uri["artifacts"][0]["artifact_uri"] = "artifact://run-1/wrong.f64le"
    _rehash_manifest(wrong_uri)
    with pytest.raises(StateIRBinaryManifestError) as uri_error:
        validate_state_ir_binary_manifest_payload(wrong_uri)
    assert uri_error.value.code == "state_binary_artifact_uri_semantics_invalid"


def test_object_validation_enforces_immutable_hashes_and_exact_source_state() -> None:
    state = _state()
    manifest = create_state_ir_binary_manifest(
        state, artifact_uri_prefix="artifact://run-1/state-1"
    )
    mutable = replace(manifest, vector_hashes=dict(manifest.vector_hashes))
    with pytest.raises(StateIRBinaryManifestError) as mutable_error:
        validate_state_ir_binary_manifest(mutable)
    assert mutable_error.value.code == "state_binary_vector_hashes_mutable"

    other = create_initial_state(_plan(plan_hash=_hash("9")))
    with pytest.raises(StateIRBinaryManifestError) as source_error:
        validate_state_ir_binary_manifest(manifest, state=other)
    assert source_error.value.code == "state_binary_source_mismatch"


def test_state_ir_binary_public_api_exports_contract() -> None:
    import structural_analysis.engine_v2 as engine_v2
    import structural_analysis.engine_v2.contracts as contracts

    assert engine_v2.StateIRBinaryManifest is contracts.StateIRBinaryManifest
    assert (
        engine_v2.create_state_ir_binary_manifest
        is contracts.create_state_ir_binary_manifest
    )
    assert (
        engine_v2.write_state_ir_binary_artifacts
        is contracts.write_state_ir_binary_artifacts
    )
