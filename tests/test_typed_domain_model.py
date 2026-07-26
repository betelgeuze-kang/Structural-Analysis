from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from structural_analysis import (
    AnalysisConfig,
    ElasticMaterial,
    FrameElement,
    FrameSection,
    NodalLoad,
    Node,
    Support,
    analyze,
    load_model,
    to_legacy_mapping,
)
from structural_analysis.api import core as core_api


def _payload() -> dict:
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {
            "axis_order": ["X", "Y", "Z"],
            "up_axis": "Z",
        },
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {
                "id": "N2",
                "coordinates": [2.0, 0.0, 0.0],
                "label": "tip",
            },
        ],
        "elements": [
            {
                "id": "F1",
                "type": "frame",
                "nodes": ["N1", "N2"],
                "section": "S1",
                "material": "M1",
                "local_axis_angle_deg": 0.0,
            }
        ],
        "materials": [
            {
                "id": "M1",
                "type": "elastic",
                "elastic_modulus": 200.0e6,
                "poisson_ratio": 0.3,
            }
        ],
        "sections": [
            {
                "id": "S1",
                "type": "frame",
                "area": 0.02,
                "iy": 8.0e-5,
                "iz": 5.0e-5,
                "torsional_constant": 1.0e-5,
            }
        ],
        "loads": [
            {
                "node": "N2",
                "load_case": "LC1",
                "components": {"FY": -10.0},
            }
        ],
        "supports": [{"node": "N1", "dofs": "all"}],
        "metadata": {"case_id": "typed-domain-model"},
    }


def _write(path: Path, payload: dict | None = None) -> Path:
    path.write_text(
        json.dumps(payload or _payload(), sort_keys=True),
        encoding="utf-8",
    )
    return path


def test_model_exposes_immutable_typed_entities_without_breaking_raw_json(
    tmp_path: Path,
) -> None:
    model = load_model(_write(tmp_path / "frame.json"))
    typed = model.typed_entities

    assert isinstance(typed.nodes[0], Node)
    assert isinstance(typed.loads[0], NodalLoad)
    assert isinstance(typed.supports[0], Support)
    assert isinstance(typed.elastic_materials[0], ElasticMaterial)
    assert isinstance(typed.frame_sections[0], FrameSection)
    assert isinstance(typed.frame_elements[0], FrameElement)

    assert typed.nodes[1].coordinates == (2.0, 0.0, 0.0)
    assert typed.nodes[1]["label"] == "tip"
    assert typed.loads[0].components == (0.0, -10.0, 0.0, 0.0, 0.0, 0.0)
    assert typed.supports[0].all_dofs is True
    assert typed.supports[0].dofs == ("UX", "UY", "UZ", "RX", "RY", "RZ")
    assert typed.frame_elements[0].nodes == ("N1", "N2")

    with pytest.raises(FrozenInstanceError):
        typed.nodes[0].id = "changed"  # type: ignore[misc]

    # Stage 1 keeps the legacy raw mappings available to existing assembly code.
    assert isinstance(model.nodes, list)
    assert isinstance(model.nodes[0], dict)
    assert model.elements[0]["nodes"] == ["N1", "N2"]


def test_support_prescribed_values_are_typed_and_round_trip() -> None:
    support = Support.from_mapping(
        {
            "node": "N2",
            "dofs": ["UX", "UY", "RZ"],
            "prescribed_values": {"UX": 0.001, "RZ": -0.002},
        }
    )

    assert support.prescribed_values == (("RZ", -0.002), ("UX", 0.001))
    assert support.to_dict()["prescribed_values"] == {
        "RZ": -0.002,
        "UX": 0.001,
    }


def test_typed_entities_round_trip_to_fresh_legacy_mappings(tmp_path: Path) -> None:
    model = load_model(_write(tmp_path / "frame.json"))

    node = to_legacy_mapping(model.node_entities[1])
    load = to_legacy_mapping(model.load_entities[0])
    support = to_legacy_mapping(model.support_entities[0])
    material = to_legacy_mapping(model.elastic_material_entities[0])
    section = to_legacy_mapping(model.frame_section_entities[0])
    element = to_legacy_mapping(model.frame_element_entities[0])

    assert node == {
        "id": "N2",
        "coordinates": [2.0, 0.0, 0.0],
        "label": "tip",
    }
    assert load["node"] == "N2"
    assert load["load_case"] == "LC1"
    assert load["components"] == {
        "FX": 0.0,
        "FY": -10.0,
        "FZ": 0.0,
        "MX": 0.0,
        "MY": 0.0,
        "MZ": 0.0,
    }
    assert support == {"node": "N1", "dofs": "all"}
    assert material["elastic_modulus"] == 200.0e6
    assert section["torsional_constant"] == 1.0e-5
    assert element["nodes"] == ["N1", "N2"]

    node["coordinates"][0] = 999.0
    assert model.node_entities[1].coordinates == (2.0, 0.0, 0.0)


def test_canonical_checksum_is_source_path_independent(tmp_path: Path) -> None:
    first = load_model(_write(tmp_path / "first.json"))
    second = load_model(_write(tmp_path / "second.json"))

    assert first.source_path != second.source_path
    assert first.input_checksum == second.input_checksum
    assert first.canonical_model_checksum == second.canonical_model_checksum
    assert first.canonical_model_checksum.startswith("sha256:")
    assert first.to_dict()["canonical_model_checksum"] == (
        first.canonical_model_checksum
    )


def test_detached_analysis_snapshot_is_independent_of_legacy_mapping_mutation(
    tmp_path: Path,
) -> None:
    model = load_model(_write(tmp_path / "frame.json"))
    snapshot = model.detached_analysis_snapshot()
    original_checksum = snapshot.canonical_model_checksum

    assert snapshot is not model
    assert snapshot.nodes is not model.nodes
    assert snapshot.nodes[1] is not model.nodes[1]

    model.nodes[1]["coordinates"][0] = 999.0
    model.metadata["case_id"] = "mutated-after-snapshot"

    assert snapshot.nodes[1]["coordinates"] == [2.0, 0.0, 0.0]
    assert snapshot.metadata["case_id"] == "typed-domain-model"
    assert snapshot.canonical_model_checksum == original_checksum
    assert model.canonical_model_checksum != original_checksum


def test_public_analysis_uses_one_detached_snapshot_and_propagates_both_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = load_model(_write(tmp_path / "frame.json"))
    expected_source_checksum = model.input_checksum
    expected_canonical_checksum = model.canonical_model_checksum

    def fake_linear_static(snapshot, **_kwargs):
        assert snapshot is not model
        assert snapshot.canonical_model_checksum == expected_canonical_checksum
        model.nodes[1]["coordinates"][0] = 777.0
        assert snapshot.nodes[1]["coordinates"] == [2.0, 0.0, 0.0]
        return SimpleNamespace(
            status="ready",
            convergence_history=[],
            unsupported_features=[],
            warnings=[],
            metrics={"node_count": 2},
        )

    monkeypatch.setattr(core_api, "run_authoritative_linear_static", fake_linear_static)
    result = core_api.analyze(
        model,
        AnalysisConfig(analysis_type="linear_static", load_case="LC1"),
    )
    report = core_api.validate(result)

    assert result.input_checksum == expected_source_checksum
    assert result.canonical_model_checksum == expected_canonical_checksum
    assert result.metrics["analysis_input_snapshot"] == ("detached_canonical_model_v1")
    assert report.input_checksum == expected_source_checksum
    assert report.canonical_model_checksum == expected_canonical_checksum
    assert "canonical_model_checksum" in report.passed_fields
    assert model.canonical_model_checksum != expected_canonical_checksum


def test_existing_solver_path_consumes_legacy_mapping_compatibility(
    tmp_path: Path,
) -> None:
    model = load_model(_write(tmp_path / "frame.json"))
    result = analyze(
        model,
        AnalysisConfig(
            analysis_type="linear_static",
            load_case="LC1",
        ),
    )

    assert result.status == "ready"
    assert result.solver == "authoritative_cpu_linear_fea_3d_v1"
    assert result.metrics["node_count"] == 2
    assert result.input_checksum == model.input_checksum
    assert result.canonical_model_checksum == model.canonical_model_checksum
    assert result.metrics["analysis_input_snapshot"] == "detached_canonical_model_v1"
