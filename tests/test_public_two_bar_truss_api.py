from __future__ import annotations

import json
from pathlib import Path

import pytest

from structural_analysis.api.nonlinear_truss import (
    PublicTwoBarTrussConfig,
    analyze_public_two_bar_truss,
    validate_public_two_bar_truss_result,
)
from structural_analysis.api.nonlinear_truss_cli import main as nonlinear_truss_cli
from structural_analysis.io.neutral.loader import load_neutral_json


def _payload(
    *,
    rise: float = 1.0,
    load_kn: float = 10.0,
    yield_stress_mpa: float = 250.0,
) -> dict:
    return {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {
            "axis_order": ["X", "Y", "Z"],
            "up_axis": "Z",
        },
        "nodes": [
            {"id": "left", "coordinates": [-1.0, 0.0, 0.0]},
            {"id": "right", "coordinates": [1.0, 0.0, 0.0]},
            {"id": "apex", "coordinates": [0.0, rise, 0.0]},
        ],
        "elements": [
            {
                "id": "left-bar",
                "type": "truss",
                "nodes": ["left", "apex"],
                "material": "steel",
                "section": "bar",
            },
            {
                "id": "right-bar",
                "type": "truss",
                "nodes": ["apex", "right"],
                "material": "steel",
                "section": "bar",
            },
        ],
        "materials": [
            {
                "id": "steel",
                "type": "bilinear_combined_hardening_steel",
                "elastic_modulus_mpa": 200000.0,
                "yield_stress_mpa": yield_stress_mpa,
                "isotropic_hardening_modulus_mpa": 3000.0,
                "kinematic_hardening_modulus_mpa": 5000.0,
            }
        ],
        "sections": [{"id": "bar", "type": "truss", "area": 0.001}],
        "loads": [
            {
                "node": "apex",
                "components": {
                    "FX": 0.0,
                    "FY": -load_kn,
                    "FZ": 0.0,
                    "MX": 0.0,
                    "MY": 0.0,
                    "MZ": 0.0,
                },
            }
        ],
        "supports": [
            {"node": "left", "dofs": ["UX", "UY"]},
            {"node": "right", "dofs": ["UX", "UY"]},
        ],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {"case_id": "public-two-bar-test"},
    }


def _model(tmp_path: Path, payload: dict | None = None):
    path = tmp_path / "model.json"
    path.write_text(json.dumps(payload or _payload()), encoding="utf-8")
    return path, load_neutral_json(path)


def test_public_api_solves_canonical_elastic_two_bar_model(tmp_path: Path) -> None:
    _, model = _model(tmp_path)
    result = analyze_public_two_bar_truss(
        model,
        PublicTwoBarTrussConfig(load_steps=5),
    )
    report = validate_public_two_bar_truss_result(result)

    assert result.status == "ready"
    assert result.contract_pass is True
    assert report.contract_pass is True
    assert result.solver_id == "public_cpu_stateful_two_bar_truss_newton_v1"
    assert result.metrics["committed_step_count"] == 5
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0
    assert len(result.node_displacements) == 3
    assert len(result.support_reactions) == 2
    assert len(result.element_results) == 2
    assert sum(row["FY_kN"] for row in result.support_reactions) == pytest.approx(
        10.0,
        abs=1.0e-7,
    )
    assert all(row["axial_force_kN"] < 0.0 for row in result.element_results)
    assert result.to_dict()["result_hash"] == result.result_hash


def test_public_api_commits_plastic_material_state(tmp_path: Path) -> None:
    _, model = _model(
        tmp_path,
        _payload(load_kn=400.0, yield_stress_mpa=100.0),
    )
    result = analyze_public_two_bar_truss(
        model,
        PublicTwoBarTrussConfig(load_steps=20, maximum_iterations=60),
    )

    assert result.status == "ready"
    assert result.metrics["material_state_changed_step_count"] > 0
    assert any(
        row["dissipated_energy_density_MJ_per_m3"] > 0.0
        for row in result.element_results
    )
    assert result.metrics["fallback_count"] == 0
    assert result.metrics["regularization_count"] == 0


def test_same_model_and_configuration_replay_exact_result_hash(tmp_path: Path) -> None:
    _, model = _model(tmp_path)
    config = PublicTwoBarTrussConfig(load_steps=6)
    first = analyze_public_two_bar_truss(model, config)
    second = analyze_public_two_bar_truss(model, config)
    assert first.to_dict() == second.to_dict()
    assert first.result_hash == second.result_hash


def test_asymmetric_geometry_fails_closed_before_solve(tmp_path: Path) -> None:
    payload = _payload()
    payload["nodes"][2]["coordinates"][0] = 0.1
    _, model = _model(tmp_path, payload)
    result = analyze_public_two_bar_truss(model)

    assert result.status == "blocked"
    assert result.contract_pass is False
    assert result.metrics["solver_executed"] is False
    assert any(
        row["kind"] == "two_bar_geometry_not_symmetric"
        for row in result.unsupported_features
    )


def test_general_topology_fails_closed_before_load_processing(tmp_path: Path) -> None:
    payload = _payload()
    payload["elements"][0]["type"] = "frame"
    _, model = _model(tmp_path, payload)
    result = analyze_public_two_bar_truss(model)

    kinds = {row["kind"] for row in result.unsupported_features}
    assert result.status == "blocked"
    assert result.metrics["solver_executed"] is False
    assert "two_bar_element_type_invalid" in kinds
    assert "two_bar_connectivity_incomplete" in kinds


def test_out_of_plane_or_moment_load_fails_closed(tmp_path: Path) -> None:
    payload = _payload()
    payload["loads"][0]["components"]["MZ"] = 1.0
    _, model = _model(tmp_path, payload)
    result = analyze_public_two_bar_truss(model)

    kinds = {row["kind"] for row in result.unsupported_features}
    assert result.status == "blocked"
    assert result.metrics["solver_executed"] is False
    assert "two_bar_load_must_be_downward_apex" in kinds


def test_failed_first_step_retains_exact_initial_state(tmp_path: Path) -> None:
    _, model = _model(tmp_path, _payload(load_kn=400.0, yield_stress_mpa=100.0))
    result = analyze_public_two_bar_truss(
        model,
        PublicTwoBarTrussConfig(
            load_steps=1,
            maximum_iterations=1,
            residual_tolerance_kn=1.0e-14,
            increment_tolerance_m=1.0e-14,
        ),
    )

    assert result.status == "blocked"
    assert result.contract_pass is False
    assert result.metrics["accepted_load_factor"] == pytest.approx(0.0)
    assert result.metrics["rollback_exact"] is True
    assert result.metrics["committed_step_count"] == 0


def test_dedicated_cli_matches_public_api_and_preserves_input(tmp_path: Path) -> None:
    model_path = tmp_path / "model.json"
    payload_text = json.dumps(_payload(), sort_keys=True)
    model_path.write_text(payload_text, encoding="utf-8")
    out = tmp_path / "result.json"
    report_out = tmp_path / "report.json"

    exit_code = nonlinear_truss_cli(
        [
            str(model_path),
            "--load-steps",
            "5",
            "--out",
            str(out),
            "--report-out",
            str(report_out),
        ]
    )

    assert exit_code == 0
    assert model_path.read_text(encoding="utf-8") == payload_text
    result_payload = json.loads(out.read_text(encoding="utf-8"))
    report_payload = json.loads(report_out.read_text(encoding="utf-8"))
    assert result_payload["contract_pass"] is True
    assert report_payload["contract_pass"] is True
    assert result_payload["result_hash"] == report_payload["result_hash"]


def test_cli_rejects_output_aliasing_model_input(tmp_path: Path) -> None:
    model_path = tmp_path / "model.json"
    model_path.write_text(json.dumps(_payload()), encoding="utf-8")
    with pytest.raises(SystemExit):
        nonlinear_truss_cli(
            [
                str(model_path),
                "--out",
                str(model_path),
                "--report-out",
                str(tmp_path / "report.json"),
            ]
        )
