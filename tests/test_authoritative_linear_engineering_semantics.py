from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from structural_analysis import AnalysisConfig, analyze, load_model
from structural_analysis.api.core import CLAIM_BOUNDARY_VERSION
from structural_analysis.results.schema import RESULT_SCHEMA_VERSION
from structural_analysis.results.viewer import (
    VIEWER_MODEL_IDENTITY_POLICY,
    ViewerPayloadValidationError,
    bind_viewer_model_identity,
    validate_linear_static_viewer_payload,
)


ROOT = Path(__file__).resolve().parents[1]


def _write_frame_model(
    path: Path,
    *,
    axis_order: tuple[str, str, str] = ("X", "Y", "Z"),
    up_axis: str = "Z",
) -> None:
    payload = {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {
            "axis_order": list(axis_order),
            "up_axis": up_axis,
        },
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [2.0, 0.0, 0.0]},
        ],
        "elements": [
            {
                "id": "F1",
                "type": "frame",
                "nodes": ["N1", "N2"],
                "section": "S1",
                "material": "M1",
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
                "components": {
                    "FX": 0.0,
                    "FY": -10.0,
                    "FZ": 0.0,
                },
            }
        ],
        "supports": [{"node": "N1", "dofs": "all"}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_linear_static_blocks_noncanonical_coordinate_system(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "y_up_frame.json"
    _write_frame_model(
        model_path,
        axis_order=("X", "Z", "Y"),
        up_axis="Y",
    )

    result = analyze(
        load_model(model_path),
        AnalysisConfig(analysis_type="linear_static"),
    )

    assert result.status == "blocked"
    assert result.metrics["production_fail_closed"] is True
    row = next(
        item
        for item in result.unsupported_features
        if item["kind"] == "linear_static_coordinate_system_not_supported"
    )
    assert row["axis_order"] == ["X", "Z", "Y"]
    assert row["up_axis"] == "Y"
    assert row["required_axis_order"] == ["X", "Y", "Z"]
    assert row["required_up_axis"] == "Z"


def test_result_claim_and_solver_metadata_are_engine_owned(tmp_path: Path) -> None:
    model_path = tmp_path / "frame.json"
    _write_frame_model(model_path)

    result = analyze(
        load_model(model_path),
        AnalysisConfig(
            analysis_type="linear_static",
            solver="commercial_ready_solver",
            developer_preview=False,
            claim_boundary_version="commercial-ready-v1",
        ),
    )
    payload = result.to_dict()

    assert result.status == "ready"
    assert result.solver == "authoritative_cpu_linear_fea_3d_v1"
    assert result.developer_preview is True
    assert result.claim_boundary_version == CLAIM_BOUNDARY_VERSION
    assert result.result_schema_version == RESULT_SCHEMA_VERSION
    assert result.metrics["provenance_policy"] == "engine_owned"
    assert any("solver provenance is engine-owned" in row for row in result.warnings)
    assert any("developer_preview override was ignored" in row for row in result.warnings)
    assert any("claim_boundary_version override was ignored" in row for row in result.warnings)

    schema = json.loads(
        (ROOT / "src/structural_analysis/schemas/result.schema.json").read_text(
            encoding="utf-8"
        )
    )
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert errors == []


def test_reactions_residuals_and_increment_semantics_are_separated(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "frame.json"
    _write_frame_model(model_path)

    result = analyze(
        load_model(model_path),
        AnalysisConfig(analysis_type="linear_static", tolerance=1.0e-9),
    )

    expected_tip = -10.0 * 2.0**3 / (3.0 * 200.0e6 * 5.0e-5)
    assert result.status == "ready"
    assert result.metrics["displacements"]["N2"]["UY"] == pytest.approx(
        expected_tip
    )
    assert result.metrics["reactions"]["N1"]["UY"] == pytest.approx(10.0)
    assert result.metrics["reactions"]["N2"]["UY"] == 0.0
    assert result.metrics["equilibrium_residuals"]["N1"]["UY"] == 0.0
    assert abs(result.metrics["equilibrium_residuals"]["N2"]["UY"]) <= 1.0e-12
    assert result.metrics["reaction_definition"] == (
        "constrained_dof_internal_minus_external_force"
    )
    assert result.metrics["equilibrium_residual_definition"] == (
        "free_dof_internal_minus_external_force"
    )

    history = result.convergence_history[0]
    assert history["increment_norm"] == pytest.approx(
        result.metrics["max_displacement"]
    )
    assert history["relative_increment"] is None
    assert history["relative_increment_applicable"] is False
    assert "no iterative relative increment" in history["increment_definition"]
    scaling = result.metrics["equation_scaling"]
    assert scaling["status"] == "available"
    assert scaling["value"]["characteristic_length"] == pytest.approx(2.0)
    assert scaling["value"]["reference_force"] == pytest.approx(10.0)
    assert scaling["value"]["scaled_residual_norm"] <= 1.0e-12
    assert scaling["value"]["scaled_increment_norm"] > 0.0
    assert scaling["value"]["scaling_hash"].startswith("sha256:")
    assert (
        result.metrics["dimensionless_scaled_residual_norm"]
        == scaling["value"]["scaled_residual_norm"]
    )

    viewer = result.metrics["viewer_payload"]
    assert viewer["schema_version"] == "structural-analysis-viewer-payload.v2"
    assert validate_linear_static_viewer_payload(viewer) == viewer
    viewer_schema = json.loads(
        (ROOT / "src/structural_analysis/schemas/viewer_payload.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(viewer_schema)
    assert list(Draft202012Validator(viewer_schema).iter_errors(viewer)) == []
    identity = viewer["model_identity"]
    assert identity == {
        "identity_policy": VIEWER_MODEL_IDENTITY_POLICY,
        "source_input_checksum": result.input_checksum,
        "canonical_model_checksum": result.canonical_model_checksum,
        "analysis_input_snapshot": "detached_canonical_model_v1",
    }
    nodes = {row["id"]: row for row in viewer["nodes"]}
    assert nodes["N1"]["reaction"]["FY"] == pytest.approx(10.0)
    assert nodes["N2"]["reaction"]["FY"] == 0.0
    assert nodes["N1"]["equilibrium_residual"]["FY"] == 0.0
    assert abs(nodes["N2"]["equilibrium_residual"]["FY"]) <= 1.0e-12


def test_viewer_identity_separates_source_bytes_from_canonical_semantics(
    tmp_path: Path,
) -> None:
    compact_path = tmp_path / "compact.json"
    pretty_path = tmp_path / "pretty.json"
    _write_frame_model(compact_path)
    payload = json.loads(compact_path.read_text(encoding="utf-8"))
    pretty_path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    compact = analyze(
        load_model(compact_path),
        AnalysisConfig(analysis_type="linear_static", tolerance=1.0e-9),
    )
    pretty = analyze(
        load_model(pretty_path),
        AnalysisConfig(analysis_type="linear_static", tolerance=1.0e-9),
    )

    assert compact.input_checksum != pretty.input_checksum
    assert compact.canonical_model_checksum == pretty.canonical_model_checksum
    compact_identity = compact.metrics["viewer_payload"]["model_identity"]
    pretty_identity = pretty.metrics["viewer_payload"]["model_identity"]
    assert compact_identity["source_input_checksum"] == compact.input_checksum
    assert pretty_identity["source_input_checksum"] == pretty.input_checksum
    assert compact_identity["canonical_model_checksum"] == (
        pretty_identity["canonical_model_checksum"]
    )

    unbound = dict(compact.metrics["viewer_payload"])
    unbound.pop("model_identity")
    with pytest.raises(ViewerPayloadValidationError) as missing_identity:
        validate_linear_static_viewer_payload(unbound)
    assert missing_identity.value.code == "viewer_model_identity_missing"
    assert validate_linear_static_viewer_payload(
        unbound,
        require_bound_identity=False,
    ) == unbound

    with pytest.raises(ViewerPayloadValidationError, match="source_input_checksum"):
        bind_viewer_model_identity(
            unbound,
            source_input_checksum="not-a-sha256",
            canonical_model_checksum=str(compact.canonical_model_checksum),
        )
    with pytest.raises(
        ViewerPayloadValidationError,
        match="already contains model identity",
    ):
        bind_viewer_model_identity(
            compact.metrics["viewer_payload"],
            source_input_checksum=compact.input_checksum,
            canonical_model_checksum=str(compact.canonical_model_checksum),
        )


def test_viewer_validator_rejects_tampered_topology_and_nonfinite_values(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "frame.json"
    _write_frame_model(model_path)
    viewer = analyze(
        load_model(model_path),
        AnalysisConfig(analysis_type="linear_static", tolerance=1.0e-9),
    ).metrics["viewer_payload"]

    unknown = deepcopy(viewer)
    unknown["unexpected"] = False
    with pytest.raises(ViewerPayloadValidationError) as schema_error:
        validate_linear_static_viewer_payload(unknown)
    assert schema_error.value.code == "viewer_payload_schema_invalid"

    duplicate = deepcopy(viewer)
    duplicate["nodes"][1]["id"] = duplicate["nodes"][0]["id"]
    with pytest.raises(ViewerPayloadValidationError) as duplicate_error:
        validate_linear_static_viewer_payload(duplicate)
    assert duplicate_error.value.code == "viewer_node_id_duplicate"

    missing_reference = deepcopy(viewer)
    missing_reference["elements"][0]["nodes"][1] = "missing-node"
    with pytest.raises(ViewerPayloadValidationError) as reference_error:
        validate_linear_static_viewer_payload(missing_reference)
    assert reference_error.value.code == "viewer_element_node_missing"

    nonfinite = deepcopy(viewer)
    nonfinite["nodes"][0]["coordinates"][0] = float("nan")
    with pytest.raises(ViewerPayloadValidationError) as numeric_error:
        validate_linear_static_viewer_payload(nonfinite)
    assert numeric_error.value.code == "viewer_numeric_value_invalid"
