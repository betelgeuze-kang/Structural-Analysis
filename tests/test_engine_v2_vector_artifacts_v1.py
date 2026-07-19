from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
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
from structural_analysis.engine_v2.contracts.equation_scaling import (  # noqa: E402
    bind_equation_scaling_to_execution_plan,
    create_equation_scaling,
    trace_scaled_residual,
)
from structural_analysis.engine_v2.contracts.execution_plan import (  # noqa: E402
    create_execution_plan,
)
from structural_analysis.engine_v2.contracts.vector_artifact import (  # noqa: E402
    ENGINE_V2_VECTOR_ARTIFACT_SCHEMA_VERSION,
    ENGINE_V2_VECTOR_STORAGE_PROFILE,
    EngineV2VectorArtifactError,
    create_equation_scaling_vector_artifact_bundle,
    create_scaled_residual_vector_artifact_bundle,
    validate_engine_v2_vector_artifact_bundle,
    validate_engine_v2_vector_artifact_bytes,
    validate_engine_v2_vector_artifact_manifest,
    write_engine_v2_vector_artifacts,
)

SCHEMA = (
    REPO_ROOT
    / "src/structural_analysis/schemas/engine_v2_vector_artifacts_v1.schema.json"
)


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _sources():
    dof_count = 12
    free = np.arange(6, dof_count, dtype="<i4")
    constrained = np.arange(6, dtype="<i4")
    global_to_free = np.full(dof_count, -1, dtype="<i4")
    global_to_free[free] = np.arange(free.size, dtype="<i4")
    plan = create_execution_plan(
        model_ir_content_hash=_hash("1"),
        solver_buffer_schema_version="solver-model-buffers.v1",
        solver_numeric_buffer_hash=_hash("2"),
        solver_entity_mapping_hash=_hash("3"),
        solver_artifact_hash=_hash("4"),
        load_pattern_id="LC1",
        operator_id="linear-static-operator",
        operator_version="linear-static-operator.v1",
        operator_hash=_hash("5"),
        node_ids=("N1", "N2"),
        element_ids=("E1",),
        node_dof_indices=np.arange(dof_count, dtype="<i4").reshape(2, 6),
        global_to_free=global_to_free,
        element_global_dofs=np.arange(dof_count, dtype="<i4").reshape(1, 12),
        constrained_dofs=constrained,
        free_dofs=free,
        csr_row_ptr=np.arange(0, dof_count * dof_count + 1, dof_count, dtype="<i8"),
        csr_column_indices=np.tile(np.arange(dof_count, dtype="<i4"), dof_count),
    )
    coordinates = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype="<f8")
    loads = np.zeros(dof_count, dtype="<f8")
    loads[free] = np.asarray([2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
    scaling = create_equation_scaling(
        execution_plan=plan,
        node_coordinates_m=coordinates,
        reference_equation_load_si=loads,
    )
    bound = bind_equation_scaling_to_execution_plan(
        plan,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=loads,
    )
    raw_residual = np.zeros(dof_count, dtype="<f8")
    raw_residual[free] = np.asarray([8.0, -4.0, 2.0, 16.0, -8.0, 4.0])
    trace = trace_scaled_residual(
        execution_plan=bound,
        scaling=scaling,
        raw_residual_si=raw_residual,
    )
    return scaling, trace


def _rehash(payload: dict) -> None:
    without_hash = {
        key: value for key, value in payload.items() if key != "bundle_hash"
    }
    payload["bundle_hash"] = canonical_hash(without_hash)


def test_scaling_bundle_is_deterministic_schema_valid_and_descriptor_only() -> None:
    scaling, _trace = _sources()
    first = create_equation_scaling_vector_artifact_bundle(
        scaling, artifact_uri_prefix="artifact://run-1/scaling/"
    )
    second = create_equation_scaling_vector_artifact_bundle(
        scaling, artifact_uri_prefix="artifact://run-1/scaling"
    )
    payload = first.to_manifest()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    assert first.schema_version == ENGINE_V2_VECTOR_ARTIFACT_SCHEMA_VERSION
    assert first.storage_profile == ENGINE_V2_VECTOR_STORAGE_PROFILE
    assert first.bundle_hash == second.bundle_hash
    assert payload["source_contract"]["owner_hash"] == scaling.scaling_hash
    assert payload["claim_boundary"]["inline_vectors"] is False
    assert len(payload["artifacts"]) == 1
    descriptor = payload["artifacts"][0]
    assert descriptor["data_hash"] == scaling.scale_vector_data_hash
    assert descriptor["source_vector_content_hash"] == scaling.scale_vector_content_hash
    assert "values" not in descriptor


def test_residual_bundle_binds_both_exact_vectors_without_inline_values() -> None:
    _scaling, trace = _sources()
    bundle = create_scaled_residual_vector_artifact_bundle(
        trace, artifact_uri_prefix="artifact://run-1/residual"
    )
    payload = bundle.to_manifest()

    assert payload["source_contract"]["owner_hash"] == trace.trace_hash
    assert [row["name"] for row in payload["artifacts"]] == [
        "raw_residual_si",
        "scaled_residual",
    ]
    assert [row["data_hash"] for row in payload["artifacts"]] == [
        trace.raw_residual_data_hash,
        trace.scaled_residual_data_hash,
    ]
    assert all(
        row["source_vector_content_hash"] is None for row in payload["artifacts"]
    )
    assert all("values" not in row for row in payload["artifacts"])


def test_writer_emits_exact_bytes_rejects_tamper_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    _scaling, trace = _sources()
    bundle = create_scaled_residual_vector_artifact_bundle(
        trace, artifact_uri_prefix="artifact://run-1/residual"
    )
    output = tmp_path / "residual"
    write_engine_v2_vector_artifacts(bundle, output)

    filenames = {
        "raw_residual_si": "raw_residual_si.f64le",
        "scaled_residual": "scaled_residual.f64le",
    }
    for name, filename in filenames.items():
        raw = (output / filename).read_bytes()
        assert raw == memoryview(bundle.vector(name)).cast("B").tobytes()
        validate_engine_v2_vector_artifact_bytes(bundle, name=name, data=raw)

    tampered = bytearray((output / filenames["raw_residual_si"]).read_bytes())
    tampered[-1] ^= 1
    with pytest.raises(EngineV2VectorArtifactError) as tamper_error:
        validate_engine_v2_vector_artifact_bytes(
            bundle, name="raw_residual_si", data=tampered
        )
    assert tamper_error.value.code == "vector_bundle_artifact_hash_mismatch"

    with pytest.raises(EngineV2VectorArtifactError) as overwrite_error:
        write_engine_v2_vector_artifacts(bundle, output)
    assert overwrite_error.value.code == "vector_bundle_target_exists"


def test_manifest_rejects_stale_hash_and_coherently_rehashed_uri_tamper() -> None:
    scaling, _trace = _sources()
    bundle = create_equation_scaling_vector_artifact_bundle(
        scaling, artifact_uri_prefix="artifact://run-1/scaling"
    )
    stale = deepcopy(bundle.to_manifest())
    stale["artifacts"][0]["artifact_uri"] = "artifact://another/scale_divisors_si.f64le"
    with pytest.raises(EngineV2VectorArtifactError) as stale_error:
        validate_engine_v2_vector_artifact_manifest(stale)
    assert stale_error.value.code == "vector_bundle_hash_mismatch"

    forged = deepcopy(bundle.to_manifest())
    forged["artifacts"][0]["artifact_uri"] = "artifact://run-1/wrong.f64le"
    _rehash(forged)
    with pytest.raises(EngineV2VectorArtifactError) as uri_error:
        validate_engine_v2_vector_artifact_manifest(forged)
    assert uri_error.value.code == "vector_bundle_descriptor_semantics_invalid"


def test_object_validator_rejects_source_identity_forgery() -> None:
    scaling, _trace = _sources()
    bundle = create_equation_scaling_vector_artifact_bundle(
        scaling, artifact_uri_prefix="artifact://run-1/scaling"
    )
    forged = replace(bundle, owner_hash=_hash("9"))
    with pytest.raises(EngineV2VectorArtifactError) as error:
        validate_engine_v2_vector_artifact_bundle(forged)
    assert error.value.code == "vector_bundle_source_mismatch"


def test_vector_artifact_public_api_exports_contract() -> None:
    import structural_analysis.engine_v2 as engine_v2
    import structural_analysis.engine_v2.contracts as contracts

    assert (
        engine_v2.EngineV2VectorArtifactBundle is contracts.EngineV2VectorArtifactBundle
    )
    assert (
        engine_v2.create_equation_scaling_vector_artifact_bundle
        is contracts.create_equation_scaling_vector_artifact_bundle
    )
