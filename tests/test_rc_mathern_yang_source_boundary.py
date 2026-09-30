"""Keep the public RC reference-beam source distinct from measured validation."""

from __future__ import annotations

import json
from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "rc_fiber"
    / "mathern_yang_2021_reference_source.v1.json"
)


def test_reference_beam_source_stays_source_only() -> None:
    record = json.loads(SOURCE.read_text(encoding="utf-8"))

    assert record["source"]["doi"] == "10.3390/ma14030506"
    assert record["source"]["license_in_article"] == "CC BY 4.0"
    assert record["specimen"]["identity"].startswith("unstrengthened")
    assert "CFRP" in record["specimen"]["excluded_companion"]

    geometry = record["specimen"]["geometry_from_figure_1_mm"]
    assert (
        geometry["nominal_each_support_to_nearby_nose"]
        == (geometry["support_center_span"] - geometry["load_nose_spacing"]) / 2
    )

    assert record["training_row_count"] == 0
    assert record["measured_evaluation_row_count"] == 0
    assert record["measured_rows_ingested"] is False
    assert record["curve_digitization_executed"] is False
    assert record["solver_comparison_executed"] is False
    assert record["physical_validation_claim"] is False
    assert (
        record["numeric_measurement_availability"][
            "ordered_numeric_curve_file_identified"
        ]
        is False
    )
    assert (
        record["crosswalk_and_model_boundary"]["current_public_compiler_compatible"]
        is False
    )
    assert record["admission_gates"]["measured_evaluation_rows"] == "not_admitted"
    assert record["admission_gates"]["measured_training_rows"] == "not_admitted"
