from __future__ import annotations

import json
from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks/rc_fiber/zenodo_18735817_flexural_source.v1.json"
)


def test_source_qualification_cannot_be_mistaken_for_data_or_model_admission() -> None:
    record = json.loads(SOURCE.read_text(encoding="utf-8"))

    assert record["source_status"] == "original_measurement_source_qualified"
    assert record["source_role"] == "prospective_held_out_evaluation_only"
    assert record["dataset"]["license_id_from_dataset_metadata"] == "cc-by-4.0"
    assert record["dataset"]["doi"] == "10.5281/zenodo.18735817"

    measurement = record["original_measurement_file"]
    assert measurement["sha256"] == (
        "2b4564e6623ac0c693e72340eff618822ca70be0365b0d47a5d8b337c996a509"
    )
    assert measurement["column_order"] == [
        "Centerline Displacement (in)",
        "Applied Load (kips)",
    ]
    assert measurement["data_row_count"] == 76114
    assert measurement["time_column_present"] is False
    assert measurement["sample_time_reconstruction_allowed"] is False

    boundary = record["crosswalk_and_model_boundary"]
    assert boundary["current_public_compiler_compatible"] is False
    window = boundary["prospective_predebonding_window"]
    assert window["status"] == "proposal_only_no_comparison_authority"
    assert 0 < window["first_excluded_data_row_1_based"] < measurement["data_row_count"]

    gates = record["admission_gates"]
    assert gates["source_rights_and_original_bytes"] == "qualified"
    assert gates["specimen_to_supported_physics"] == "blocked"
    assert gates["independent_held_out_comparison"] == "not_run"
    assert gates["measured_evaluation_rows"] == "not_admitted"
    assert gates["measured_training_rows"] == "not_admitted"
    assert record["training_row_count"] == 0
    assert record["measured_rows_ingested"] is False
    assert record["comparison_executed"] is False
    assert record["physical_validation_claim"] is False
