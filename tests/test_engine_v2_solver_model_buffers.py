from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2 import (  # noqa: E402
    SOLVER_MODEL_BUFFERS_SCHEMA_VERSION,
    SolverModelBufferError,
    pack_solver_model_buffers,
    validate_solver_model_buffers,
)
from structural_analysis.model_ir import ModelIRDocument, load_model_ir_v2  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"
BUFFER_SNAPSHOT = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.buffers.expected.json"

EXPECTED_NAMES = {
    "node_coordinates_m",
    "element_connectivity",
    "element_type",
    "element_formulation_code",
    "element_material_index",
    "element_section_index",
    "material_law_code",
    "material_properties_si",
    "section_family_code",
    "section_properties_si",
    "element_local_axis_rotation_rad",
    "element_offsets_m",
    "element_release_mask",
    "support_mask",
    "prescribed_values_si",
    "load_vector_si",
}


def _payload() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_pack_solver_model_buffers_has_stable_shapes_dtypes_and_dof_order() -> None:
    document = load_model_ir_v2(FIXTURE)
    buffers = pack_solver_model_buffers(document, load_pattern_id="LC_AXIAL")
    descriptors = {row.name: row for row in buffers.descriptors}

    assert buffers.schema_version == SOLVER_MODEL_BUFFERS_SCHEMA_VERSION
    assert buffers.dof_order == ("UX", "UY", "UZ", "RX", "RY", "RZ")
    assert set(descriptors) == EXPECTED_NAMES
    assert descriptors["node_coordinates_m"].shape == (2, 3)
    assert descriptors["node_coordinates_m"].dtype == "<f8"
    assert descriptors["element_connectivity"].shape == (1, 2)
    assert descriptors["element_connectivity"].dtype == "<i4"
    assert descriptors["element_type"].dtype == "|u1"
    assert descriptors["element_material_index"].dtype == "<i4"
    assert descriptors["section_properties_si"].shape == (1, 6)
    assert descriptors["element_offsets_m"].shape == (1, 2, 3)
    assert descriptors["element_release_mask"].shape == (1, 2, 6)
    assert descriptors["support_mask"].shape == (2, 6)
    assert descriptors["load_vector_si"].shape == (2, 6)
    assert buffers.numeric_buffer_hash.startswith("sha256:")
    assert buffers.entity_mapping_hash.startswith("sha256:")
    assert buffers.artifact_hash.startswith("sha256:")
    assert len(buffers.numeric_buffer_hash) == 71
    assert descriptors["material_properties_si"].component_labels == (
        "elastic_modulus",
        "poisson_ratio",
        "density",
    )
    assert descriptors["load_vector_si"].component_units == (
        "N",
        "N",
        "N",
        "N*m",
        "N*m",
        "N*m",
    )
    assert validate_solver_model_buffers(buffers) is buffers


def test_packed_values_preserve_model_semantics_and_selected_load_pattern() -> None:
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_AXIAL"
    )

    np.testing.assert_array_equal(
        buffers.array("node_coordinates_m"),
        np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype="<f8"),
    )
    np.testing.assert_array_equal(
        buffers.array("element_connectivity"), np.array([[0, 1]], dtype="<i4")
    )
    np.testing.assert_array_equal(buffers.array("element_type"), np.array([2], dtype="u1"))
    np.testing.assert_allclose(
        buffers.array("material_properties_si"), [[200.0e9, 0.3, 7850.0]]
    )
    np.testing.assert_allclose(
        buffers.array("section_properties_si"),
        [[0.02, 8.0e-5, 5.0e-5, 1.0e-5, 0.016, 0.016]],
    )
    np.testing.assert_array_equal(
        buffers.array("support_mask"),
        np.array([[1, 1, 1, 1, 1, 1], [0, 0, 0, 0, 0, 0]], dtype="u1"),
    )
    np.testing.assert_allclose(
        buffers.array("load_vector_si"),
        [[0.0] * 6, [100000.0, 0.0, 0.0, 0.0, 0.0, 0.0]],
    )


def test_buffers_are_immutable_and_manifest_is_json_serializable() -> None:
    buffers = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_WEAK"
    )

    for descriptor in buffers.descriptors:
        assert buffers.array(descriptor.name).flags.c_contiguous
        assert buffers.array(descriptor.name).flags.writeable is False
        with pytest.raises(ValueError):
            buffers.array(descriptor.name).setflags(write=True)
    with pytest.raises(ValueError):
        buffers.array("load_vector_si")[1, 1] = 0.0
    manifest = buffers.to_manifest()
    assert json.loads(json.dumps(manifest)) == manifest
    assert manifest["claim_boundary"] == "backend_neutral_buffer_contract_not_solver_parity"
    assert manifest["code_tables"]["element_type"] == {"truss_3d": 1, "frame_3d": 2}
    assert manifest["entity_ids"]["nodes"] == ["N1", "N2"]
    assert manifest["index_policy"]["dtype"] == "<i4"


def test_non_load_buffers_match_across_cases_while_load_and_aggregate_hash_change() -> None:
    document = load_model_ir_v2(FIXTURE)
    axial = pack_solver_model_buffers(document, load_pattern_id="LC_AXIAL")
    torsion = pack_solver_model_buffers(document, load_pattern_id="LC_TORSION")
    axial_descriptors = {row.name: row for row in axial.descriptors}
    torsion_descriptors = {row.name: row for row in torsion.descriptors}

    for name in EXPECTED_NAMES - {"load_vector_si"}:
        assert axial_descriptors[name].content_hash == torsion_descriptors[name].content_hash
    assert axial_descriptors["load_vector_si"].content_hash != torsion_descriptors["load_vector_si"].content_hash
    assert axial.numeric_buffer_hash != torsion.numeric_buffer_hash
    assert axial.artifact_hash != torsion.artifact_hash


def test_buffer_hash_is_repeatable_for_same_document_and_case() -> None:
    first = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_STRONG"
    )
    second = pack_solver_model_buffers(
        load_model_ir_v2(FIXTURE), load_pattern_id="LC_STRONG"
    )

    assert first.model_ir_content_hash == second.model_ir_content_hash
    assert first.numeric_buffer_hash == second.numeric_buffer_hash
    assert first.entity_mapping_hash == second.entity_mapping_hash
    assert first.artifact_hash == second.artifact_hash
    assert [row.content_hash for row in first.descriptors] == [
        row.content_hash for row in second.descriptors
    ]


def test_missing_load_pattern_and_self_weight_fail_closed() -> None:
    document = load_model_ir_v2(FIXTURE)
    with pytest.raises(SolverModelBufferError) as missing:
        pack_solver_model_buffers(document, load_pattern_id="LC404")
    assert missing.value.code == "load_pattern_not_found"

    payload = _payload()
    payload["load_patterns"][0]["self_weight"] = [0.0, 0.0, -1.0]
    with pytest.raises(SolverModelBufferError) as self_weight:
        pack_solver_model_buffers(payload, load_pattern_id="LC_AXIAL")
    assert self_weight.value.code == "phase0_profile_feature_not_supported"


def test_blocking_unsupported_feature_prevents_buffer_compilation() -> None:
    payload = _payload()
    payload["unsupported_features"] = [
        {
            "feature_id": "UF1",
            "kind": "contact_not_in_phase0_profile",
            "source_entity_id": "CONTACT:1",
            "disposition": "blocked",
            "blocking": True,
            "detail": "Contact requires a later formulation.",
            "extensions": {},
        }
    ]

    with pytest.raises(SolverModelBufferError) as error:
        pack_solver_model_buffers(payload, load_pattern_id="LC_AXIAL")
    assert error.value.code == "model_ir_not_analysis_ready"


def test_semantically_invalid_model_never_reaches_buffer_compilation() -> None:
    payload = deepcopy(_payload())
    payload["elements"][0]["node_ids"][1] = "N404"

    with pytest.raises(SolverModelBufferError) as error:
        pack_solver_model_buffers(payload, load_pattern_id="LC_AXIAL")
    assert error.value.code == "model_ir_contract_invalid"


def test_numeric_hash_ignores_provenance_but_artifact_hash_does_not() -> None:
    baseline_payload = _payload()
    changed_provenance = deepcopy(baseline_payload)
    changed_provenance["provenance"]["source_ref"] = "generated:same-numerics-new-source"

    baseline = pack_solver_model_buffers(baseline_payload, load_pattern_id="LC_AXIAL")
    changed = pack_solver_model_buffers(changed_provenance, load_pattern_id="LC_AXIAL")

    assert baseline.numeric_buffer_hash == changed.numeric_buffer_hash
    assert baseline.entity_mapping_hash == changed.entity_mapping_hash
    assert baseline.model_ir_content_hash != changed.model_ir_content_hash
    assert baseline.artifact_hash != changed.artifact_hash


def test_signed_zero_and_integral_float_variants_pack_identically() -> None:
    baseline_payload = _payload()
    equivalent = deepcopy(baseline_payload)
    equivalent["nodes"][0]["coordinates_m"][0] = -0.0
    equivalent["nodes"][1]["coordinates_m"][0] = 2

    baseline = pack_solver_model_buffers(baseline_payload, load_pattern_id="LC_AXIAL")
    changed = pack_solver_model_buffers(equivalent, load_pattern_id="LC_AXIAL")

    assert baseline.model_ir_content_hash == changed.model_ir_content_hash
    assert baseline.numeric_buffer_hash == changed.numeric_buffer_hash
    assert baseline.artifact_hash == changed.artifact_hash


@pytest.mark.parametrize(
    "mutation",
    [
        "release",
        "prescribed_value",
        "load_combination",
        "time_function",
        "construction_stage",
    ],
)
def test_phase0_profile_features_fail_closed(mutation: str) -> None:
    payload = _payload()
    if mutation == "release":
        payload["elements"][0]["releases"]["i"] = ["RY"]
    elif mutation == "prescribed_value":
        payload["constraints"][0]["prescribed_values_si"]["UX"] = 0.001
    elif mutation == "load_combination":
        payload["load_combinations"] = [
            {
                "id": "C1",
                "index": 0,
                "combination_type": "linear",
                "terms": [{"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 1.0}],
                "source_id": "generated:C1",
                "extensions": {},
            }
        ]
    elif mutation == "time_function":
        payload["time_functions"] = [
            {
                "id": "TF1",
                "index": 0,
                "type": "piecewise_linear",
                "points": [[0.0, 0.0], [1.0, 1.0]],
                "extensions": {},
            }
        ]
    else:
        payload["construction_stages"] = [
            {
                "id": "ST1",
                "index": 0,
                "active_element_ids": ["E1"],
                "active_constraint_ids": ["BC1"],
                "load_pattern_ids": ["LC_AXIAL"],
                "extensions": {},
            }
        ]

    with pytest.raises(SolverModelBufferError) as error:
        pack_solver_model_buffers(payload, load_pattern_id="LC_AXIAL")
    assert error.value.code == "phase0_profile_feature_not_supported"


def test_forged_model_ir_document_is_revalidated() -> None:
    valid = load_model_ir_v2(FIXTURE)
    forged = ModelIRDocument(
        schema_version=valid.schema_version,
        model_id=valid.model_id,
        capability_profile=valid.capability_profile,
        canonical_json=valid.canonical_json,
        content_hash="sha256:" + "0" * 64,
        analysis_ready=True,
    )

    with pytest.raises(SolverModelBufferError) as error:
        pack_solver_model_buffers(forged, load_pattern_id="LC_AXIAL")
    assert error.value.code == "model_ir_document_hash_mismatch"


def test_solver_model_buffer_abi_matches_golden_snapshot() -> None:
    expected = json.loads(BUFFER_SNAPSHOT.read_text(encoding="utf-8"))
    document = load_model_ir_v2(FIXTURE)
    actual_cases = {}
    axial_buffers = None
    for case_id in ("LC_AXIAL", "LC_WEAK", "LC_STRONG", "LC_TORSION"):
        buffers = pack_solver_model_buffers(document, load_pattern_id=case_id)
        if case_id == "LC_AXIAL":
            axial_buffers = buffers
        load_descriptor = next(
            descriptor for descriptor in buffers.descriptors if descriptor.name == "load_vector_si"
        )
        actual_cases[case_id] = {
            "numeric_buffer_hash": buffers.numeric_buffer_hash,
            "artifact_hash": buffers.artifact_hash,
            "load_vector_content_hash": load_descriptor.content_hash,
        }

    assert axial_buffers is not None
    actual_contract = {
        descriptor.name: {
            "dtype": descriptor.dtype,
            "shape": list(descriptor.shape),
            "content_hash": descriptor.content_hash,
        }
        for descriptor in axial_buffers.descriptors
    }
    assert document.content_hash == expected["model_ir_content_hash"]
    assert axial_buffers.entity_mapping_hash == expected["entity_mapping_hash"]
    assert actual_cases == expected["cases"]
    assert actual_contract == expected["buffer_contract"]
