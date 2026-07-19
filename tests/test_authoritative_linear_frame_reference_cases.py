from __future__ import annotations

import json
from math import sqrt
from pathlib import Path

import pytest

from structural_analysis import AnalysisConfig, analyze, load_model
from structural_analysis.analyses import run_authoritative_linear_static


E = 200.0e6
NU = 0.3
IY = 8.0e-5
IZ = 5.0e-5
J = 1.0e-5
AREA = 0.02
LENGTH = 2.0


def _write_frame_case(
    path: Path,
    *,
    end: tuple[float, float, float] = (LENGTH, 0.0, 0.0),
    loads: list[dict[str, object]] | None = None,
    element_overrides: dict[str, object] | None = None,
) -> None:
    element: dict[str, object] = {
        "id": "F1",
        "type": "frame",
        "nodes": ["N1", "N2"],
        "section": "S1",
        "material": "M1",
    }
    if element_overrides:
        element.update(element_overrides)
    payload = {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": list(end)},
        ],
        "elements": [element],
        "materials": [
            {
                "id": "M1",
                "type": "elastic",
                "elastic_modulus": E,
                "poisson_ratio": NU,
            }
        ],
        "sections": [
            {
                "id": "S1",
                "type": "frame",
                "area": AREA,
                "iy": IY,
                "iz": IZ,
                "torsional_constant": J,
            }
        ],
        "loads": loads
        if loads is not None
        else [{"node": "N2", "components": {"FY": -10.0}}],
        "supports": [{"node": "N1", "dofs": "all"}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _solve(path: Path, *, load_case: str | None = None, tolerance: float = 1.0e-9):
    return analyze(
        load_model(path),
        AnalysisConfig(
            analysis_type="linear_static",
            load_case=load_case,
            tolerance=tolerance,
        ),
    )


def test_weak_axis_cantilever_matches_closed_form_solution(tmp_path: Path) -> None:
    path = tmp_path / "weak-axis.json"
    _write_frame_case(path, loads=[{"node": "N2", "components": {"FY": -10.0}}])

    result = _solve(path)

    expected = -10.0 * LENGTH**3 / (3.0 * E * IZ)
    assert result.status == "ready"
    assert result.metrics["displacements"]["N2"]["UY"] == pytest.approx(expected)
    assert result.metrics["reactions"]["N1"]["UY"] == pytest.approx(10.0)
    assert abs(result.metrics["reactions"]["N1"]["RZ"]) == pytest.approx(20.0)


def test_strong_axis_cantilever_matches_closed_form_solution(tmp_path: Path) -> None:
    path = tmp_path / "strong-axis.json"
    _write_frame_case(path, loads=[{"node": "N2", "components": {"FZ": -10.0}}])

    result = _solve(path)

    expected = -10.0 * LENGTH**3 / (3.0 * E * IY)
    assert result.status == "ready"
    assert result.metrics["displacements"]["N2"]["UZ"] == pytest.approx(expected)
    assert result.metrics["reactions"]["N1"]["UZ"] == pytest.approx(10.0)
    assert abs(result.metrics["reactions"]["N1"]["RY"]) == pytest.approx(20.0)


def test_cantilever_torsion_matches_closed_form_rotation(tmp_path: Path) -> None:
    path = tmp_path / "torsion.json"
    _write_frame_case(path, loads=[{"node": "N2", "components": {"MX": 5.0}}])

    result = _solve(path)

    shear_modulus = E / (2.0 * (1.0 + NU))
    expected_rotation = 5.0 * LENGTH / (shear_modulus * J)
    assert result.status == "ready"
    assert result.metrics["displacements"]["N2"]["RX"] == pytest.approx(expected_rotation)
    assert abs(result.metrics["reactions"]["N1"]["RX"]) == pytest.approx(5.0)


def test_rotated_frame_preserves_global_vertical_bending_response(tmp_path: Path) -> None:
    path = tmp_path / "rotated.json"
    diagonal = LENGTH / sqrt(2.0)
    _write_frame_case(
        path,
        end=(diagonal, diagonal, 0.0),
        loads=[{"node": "N2", "components": {"FZ": -10.0}}],
    )

    result = _solve(path)

    expected = -10.0 * LENGTH**3 / (3.0 * E * IY)
    assert result.status == "ready"
    assert result.metrics["displacements"]["N2"]["UZ"] == pytest.approx(expected)
    assert result.metrics["reactions"]["N1"]["UZ"] == pytest.approx(10.0)


def test_local_axis_roll_swaps_the_bending_inertia_used_for_global_y_load(tmp_path: Path) -> None:
    path = tmp_path / "rolled.json"
    _write_frame_case(
        path,
        loads=[{"node": "N2", "components": {"FY": -10.0}}],
        element_overrides={"local_axis_angle_deg": 90.0},
    )

    result = _solve(path)

    expected = -10.0 * LENGTH**3 / (3.0 * E * IY)
    assert result.status == "ready"
    assert result.metrics["displacements"]["N2"]["UY"] == pytest.approx(expected)


def test_multiple_named_load_cases_require_explicit_selection(tmp_path: Path) -> None:
    path = tmp_path / "multiple-load-cases.json"
    _write_frame_case(
        path,
        loads=[
            {"node": "N2", "load_case": "LC1", "components": {"FY": -10.0}},
            {"node": "N2", "load_case": "LC2", "components": {"FY": -20.0}},
        ],
    )

    blocked = _solve(path)
    selected = _solve(path, load_case="LC1")

    assert blocked.status == "blocked"
    assert {row["kind"] for row in blocked.unsupported_features} == {
        "linear_static_load_case_required"
    }
    expected = -10.0 * LENGTH**3 / (3.0 * E * IZ)
    assert selected.status == "ready"
    assert selected.metrics["displacements"]["N2"]["UY"] == pytest.approx(expected)


def test_named_and_unnamed_load_rows_are_not_combined(tmp_path: Path) -> None:
    path = tmp_path / "mixed-labels.json"
    _write_frame_case(
        path,
        loads=[
            {"node": "N2", "load_case": "LC1", "components": {"FY": -10.0}},
            {"node": "N2", "components": {"FY": -5.0}},
        ],
    )

    result = _solve(path, load_case="LC1")

    assert result.status == "blocked"
    assert {row["kind"] for row in result.unsupported_features} == {
        "linear_static_load_case_labeling_inconsistent"
    }


@pytest.mark.parametrize(
    ("loads", "element_overrides", "expected_kind"),
    [
        ([{"node": "N2", "components": {"FY": "nan"}}], None, "linear_static_load_components_invalid"),
        ([{"node": "N2", "components": [0.0, -10.0, 0.0, 1.0]}], None, "linear_static_load_components_invalid"),
        ([{"node": "N2", "components": {"FY": -10.0}}], {"local_axis_angle_deg": "nan"}, "linear_static_element_properties_invalid"),
    ],
)
def test_non_finite_or_malformed_engineering_inputs_are_blocked(
    tmp_path: Path,
    loads: list[dict[str, object]],
    element_overrides: dict[str, object] | None,
    expected_kind: str,
) -> None:
    path = tmp_path / f"invalid-{expected_kind}.json"
    _write_frame_case(path, loads=loads, element_overrides=element_overrides)

    result = _solve(path)

    assert result.status == "blocked"
    assert expected_kind in {row["kind"] for row in result.unsupported_features}
    assert result.metrics["production_fail_closed"] is True
    assert result.metrics["fallback_used"] is False


def test_non_positive_tolerance_is_blocked(tmp_path: Path) -> None:
    path = tmp_path / "invalid-tolerance.json"
    _write_frame_case(path)

    result = _solve(path, tolerance=0.0)

    assert result.status == "blocked"
    assert {row["kind"] for row in result.unsupported_features} == {
        "linear_static_tolerance_invalid"
    }


@pytest.mark.parametrize(
    ("tolerance", "receipt_value"),
    [
        pytest.param(True, True, id="boolean"),
        pytest.param("invalid", "invalid", id="non-numeric"),
        pytest.param(float("inf"), "positive_infinity", id="infinite"),
        pytest.param(float("nan"), "nan", id="nan"),
    ],
)
def test_direct_linear_driver_rejects_non_numeric_or_nonfinite_tolerance(
    tmp_path: Path,
    tolerance: object,
    receipt_value: object,
) -> None:
    path = tmp_path / "invalid-direct-tolerance.json"
    _write_frame_case(path)

    result = run_authoritative_linear_static(
        load_model(path),
        tolerance=tolerance,
        matrix_backend="numpy_linalg_solve_dense",
    )

    assert result.status == "blocked"
    assert result.unsupported_features[0]["kind"] == (
        "linear_static_tolerance_invalid"
    )
    assert result.unsupported_features[0]["tolerance"] == receipt_value
    assert result.metrics["fallback_used"] is False
    json.dumps(result.unsupported_features, allow_nan=False)
