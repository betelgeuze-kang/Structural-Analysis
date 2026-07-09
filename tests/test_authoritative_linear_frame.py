from __future__ import annotations

import json
from pathlib import Path

import pytest

from structural_analysis import AnalysisConfig, analyze, load_model
from structural_analysis.api.cli import main as cli_main


def _write_frame_model(
    path: Path,
    *,
    all_fixed: bool = False,
    include_torsion: bool = True,
    load_case: str | None = None,
) -> None:
    section = {
        "id": "S1",
        "type": "frame",
        "area": 0.02,
        "iy": 8.0e-5,
        "iz": 5.0e-5,
    }
    if include_torsion:
        section["torsional_constant"] = 1.0e-5
    load = {
        "node": "N2",
        "components": {"FX": 0.0, "FY": -10.0, "FZ": 0.0},
    }
    if load_case is not None:
        load["load_case"] = load_case
    supports = [{"node": "N1", "dofs": "all"}]
    if all_fixed:
        supports.append({"node": "N2", "dofs": "all"})
    payload = {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
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
        "sections": [section],
        "loads": [load],
        "supports": supports,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(
    "backend",
    ["numpy_linalg_solve_dense", "scipy_sparse_spsolve_cpu"],
)
def test_cantilever_frame_uses_authoritative_6dof_path(
    tmp_path: Path,
    backend: str,
) -> None:
    model_path = tmp_path / "cantilever.json"
    _write_frame_model(model_path)

    result = analyze(
        load_model(model_path),
        AnalysisConfig(
            analysis_type="linear_static",
            matrix_backend=backend,
            tolerance=1.0e-9,
        ),
    )

    expected_tip = -10.0 * 2.0**3 / (3.0 * 200.0e6 * 5.0e-5)
    assert result.status == "ready"
    assert result.solver == "authoritative_cpu_linear_fea_3d_v1"
    assert result.metrics["fallback_used"] is False
    assert result.metrics["implicit_property_fallback_used"] is False
    assert result.metrics["automatic_support_generation_used"] is False
    assert result.metrics["displacements"]["N2"]["UY"] == pytest.approx(expected_tip)
    assert result.metrics["reactions"]["N1"]["UY"] == pytest.approx(10.0)
    assert abs(result.metrics["reactions"]["N1"]["RZ"]) == pytest.approx(20.0)
    assert result.metrics["member_forces"][0]["id"] == "F1"
    viewer = result.metrics["viewer_payload"]
    assert viewer["source"] == "authoritative_solver_result"
    assert viewer["solver_path_id"] == result.solver
    assert viewer["nodes"][1]["displacement"]["UY"] == pytest.approx(expected_tip)
    assert viewer["nodes"][0]["reaction"]["FY"] == pytest.approx(10.0)


def test_missing_frame_property_blocks_instead_of_fallback(tmp_path: Path) -> None:
    model_path = tmp_path / "missing_j.json"
    _write_frame_model(model_path, include_torsion=False)

    result = analyze(load_model(model_path), AnalysisConfig(analysis_type="linear_static"))

    assert result.status == "blocked"
    assert result.metrics["production_fail_closed"] is True
    assert result.metrics["fallback_used"] is False
    unsupported = {row["kind"] for row in result.unsupported_features}
    assert "linear_static_element_properties_invalid" in unsupported
    assert "linear_static_no_supported_elements" in unsupported


def test_all_fixed_model_returns_reactions_without_zero_dof_failure(tmp_path: Path) -> None:
    model_path = tmp_path / "all_fixed.json"
    _write_frame_model(model_path, all_fixed=True)

    result = analyze(load_model(model_path), AnalysisConfig(analysis_type="linear_static"))

    assert result.status == "ready"
    assert result.metrics["free_dof_count"] == 0
    assert result.metrics["max_displacement"] == 0.0
    assert result.metrics["reactions"]["N2"]["UY"] == pytest.approx(10.0)


def test_cli_and_python_api_emit_the_same_authoritative_viewer_payload(tmp_path: Path) -> None:
    model_path = tmp_path / "load_case.json"
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    _write_frame_model(model_path, load_case="LC1")
    model = load_model(model_path)
    expected = analyze(
        model,
        AnalysisConfig(analysis_type="linear_static", load_case="LC1"),
    )

    exit_code = cli_main(
        [
            str(model_path),
            "--analysis-type",
            "linear_static",
            "--load-case",
            "LC1",
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
        ]
    )

    actual = json.loads(result_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert actual == expected.to_dict()
    assert actual["metrics"]["viewer_payload"] == expected.metrics["viewer_payload"]
