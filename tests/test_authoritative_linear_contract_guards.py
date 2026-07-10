from __future__ import annotations

from math import nan
from typing import Any

import pytest

from structural_analysis import AnalysisConfig, analyze
from structural_analysis.model.schema import (
    CANONICAL_MODEL_SCHEMA_VERSION,
    CanonicalModel,
)
from structural_analysis.units.schema import CoordinateSystem, UnitSystem


def _frame_model(
    *,
    loads: list[dict[str, Any]] | None = None,
    element_overrides: dict[str, Any] | None = None,
) -> CanonicalModel:
    element = {
        "id": "F1",
        "type": "frame",
        "nodes": ["N1", "N2"],
        "section": "S1",
        "material": "M1",
    }
    element.update(element_overrides or {})
    return CanonicalModel(
        schema_version=CANONICAL_MODEL_SCHEMA_VERSION,
        source_path="memory://authoritative-linear-contract",
        source_format="neutral_json",
        input_checksum="sha256:test",
        units=UnitSystem(length="m", force="kN"),
        coordinate_system=CoordinateSystem(
            axis_order=("X", "Y", "Z"),
            up_axis="Z",
        ),
        nodes=[
            {"id": "N1", "coordinates": [0.0, 0.0, 0.0]},
            {"id": "N2", "coordinates": [2.0, 0.0, 0.0]},
        ],
        elements=[element],
        materials=[
            {
                "id": "M1",
                "type": "elastic",
                "elastic_modulus": 200.0e6,
                "poisson_ratio": 0.3,
            }
        ],
        sections=[
            {
                "id": "S1",
                "type": "frame",
                "area": 0.02,
                "iy": 8.0e-5,
                "iz": 5.0e-5,
                "torsional_constant": 1.0e-5,
            }
        ],
        loads=loads
        if loads is not None
        else [{"node": "N2", "components": {"FY": -10.0}}],
        supports=[{"node": "N1", "dofs": "all"}],
    )


def _unsupported_kinds(result: Any) -> set[str]:
    return {str(row.get("kind")) for row in result.unsupported_features}


def test_multiple_named_load_cases_require_explicit_selection() -> None:
    model = _frame_model(
        loads=[
            {"node": "N2", "load_case": "DL", "components": {"FY": -10.0}},
            {"node": "N2", "load_case": "LL", "components": {"FY": -5.0}},
        ]
    )

    result = analyze(model, AnalysisConfig(analysis_type="linear_static"))

    assert result.status == "blocked"
    assert "linear_static_load_case_required" in _unsupported_kinds(result)
    assert result.metrics["fallback_used"] is False


def test_explicit_load_case_does_not_sum_other_named_cases() -> None:
    model = _frame_model(
        loads=[
            {"node": "N2", "load_case": "DL", "components": {"FY": -10.0}},
            {"node": "N2", "load_case": "LL", "components": {"FY": -5.0}},
        ]
    )

    result = analyze(
        model,
        AnalysisConfig(analysis_type="linear_static", load_case="LL"),
    )

    assert result.status == "ready"
    assert result.metrics["external_forces"]["N2"]["UY"] == pytest.approx(-5.0)
    assert result.metrics["reactions"]["N1"]["UY"] == pytest.approx(5.0)


def test_named_and_unnamed_load_rows_are_not_mixed() -> None:
    model = _frame_model(
        loads=[
            {"node": "N2", "load_case": "DL", "components": {"FY": -10.0}},
            {"node": "N2", "components": {"FY": -5.0}},
        ]
    )

    result = analyze(
        model,
        AnalysisConfig(analysis_type="linear_static", load_case="DL"),
    )

    assert result.status == "blocked"
    assert "linear_static_load_case_labeling_inconsistent" in _unsupported_kinds(result)


def test_nonfinite_load_component_is_blocked_before_assembly() -> None:
    model = _frame_model(loads=[{"node": "N2", "components": {"FY": nan}}])

    result = analyze(model, AnalysisConfig(analysis_type="linear_static"))

    assert result.status == "blocked"
    assert "linear_static_load_components_invalid" in _unsupported_kinds(result)


def test_nonfinite_frame_orientation_is_blocked() -> None:
    model = _frame_model(element_overrides={"local_axis_angle_deg": nan})

    result = analyze(model, AnalysisConfig(analysis_type="linear_static"))

    assert result.status == "blocked"
    assert "linear_static_element_properties_invalid" in _unsupported_kinds(result)


@pytest.mark.parametrize("tolerance", [0.0, -1.0, nan])
def test_invalid_solver_tolerance_is_blocked(tolerance: float) -> None:
    result = analyze(
        _frame_model(),
        AnalysisConfig(analysis_type="linear_static", tolerance=tolerance),
    )

    assert result.status == "blocked"
    assert "linear_static_tolerance_invalid" in _unsupported_kinds(result)
