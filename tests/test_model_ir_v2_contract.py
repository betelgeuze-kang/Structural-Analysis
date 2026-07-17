from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.model_ir import (  # noqa: E402
    DuplicateJSONKeyError,
    MODEL_IR_V2_SCHEMA_VERSION,
    ModelIRValidationError,
    canonicalize_model_ir_v2,
    load_model_ir_v2,
    model_ir_v2_content_hash,
    parse_model_ir_v2,
    validate_model_ir_v2,
)
from structural_analysis.model_ir.validation import load_model_ir_v2_schema  # noqa: E402

FIXTURE = REPO_ROOT / "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"


def _payload() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _issue_codes(payload: dict) -> set[str]:
    return {issue.code for issue in validate_model_ir_v2(payload).issues}


def test_schema_is_draft_2020_12_and_golden_fixture_is_analysis_ready() -> None:
    schema = load_model_ir_v2_schema()
    Draft202012Validator.check_schema(schema)
    payload = _payload()

    report = validate_model_ir_v2(payload)
    document = load_model_ir_v2(FIXTURE)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert report.schema_version == MODEL_IR_V2_SCHEMA_VERSION
    assert report.schema_valid is True
    assert report.semantics_valid is True
    assert report.contract_valid is True
    assert report.analysis_ready is True
    assert report.issues == ()
    assert report.blocking_feature_ids == ()
    assert report.content_hash is not None
    assert document.content_hash == report.content_hash
    assert canonicalize_model_ir_v2(document.to_dict()) == canonicalize_model_ir_v2(
        payload
    )


def test_in_memory_parser_uses_the_same_contract_and_readiness_gate() -> None:
    payload = _payload()

    document = parse_model_ir_v2(payload)

    assert document.to_dict() == load_model_ir_v2(FIXTURE).to_dict()

    payload["unsupported_features"] = [
        {
            "feature_id": "BLOCKED_CARD",
            "kind": "mgt_unsupported_card",
            "source_entity_id": "MGT:OFFSET:1",
            "disposition": "blocked",
            "blocking": True,
            "detail": "Fixture blocker.",
            "extensions": {},
        }
    ]
    blocked = parse_model_ir_v2(payload, require_analysis_ready=False)
    assert blocked.analysis_ready is False
    with pytest.raises(ModelIRValidationError):
        parse_model_ir_v2(payload)


def test_canonical_hash_is_key_order_independent_and_normalizes_signed_zero() -> None:
    payload = _payload()
    reordered = json.loads(json.dumps(payload, sort_keys=True))
    reordered["coordinate_system"]["origin_m"][0] = -0.0

    assert model_ir_v2_content_hash(reordered) == model_ir_v2_content_hash(payload)
    assert canonicalize_model_ir_v2(reordered) == canonicalize_model_ir_v2(payload)


def test_unknown_element_field_is_rejected_instead_of_silently_ignored() -> None:
    payload = _payload()
    payload["elements"][0]["end_release_i"] = ["RY"]

    report = validate_model_ir_v2(payload)

    assert report.schema_valid is False
    assert report.analysis_ready is False
    assert "schema_validation_error" in {issue.code for issue in report.issues}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["nodes"][0].update({"index": 0.0}),
        lambda payload: payload["nodes"][0].update({"index": True}),
        lambda payload: payload["nodes"][0].update({"coordinates_m": ["0", 0.0, 0.0]}),
        lambda payload: payload["materials"][0]["state_schema"].update({"stateful": 0}),
    ],
)
def test_model_ir_rejects_wrong_exact_json_types(mutate) -> None:
    payload = _payload()
    mutate(payload)

    report = validate_model_ir_v2(payload)

    assert report.schema_valid is False
    assert report.analysis_ready is False
    assert "schema_validation_error" in {issue.code for issue in report.issues}


def test_duplicate_id_and_noncanonical_index_are_semantic_failures() -> None:
    payload = _payload()
    second = deepcopy(payload["nodes"][1])
    second["index"] = 3
    payload["nodes"].append(second)

    report = validate_model_ir_v2(payload)

    assert report.schema_valid is True
    assert report.semantics_valid is False
    assert {"duplicate_id", "noncanonical_index_order"}.issubset(_issue_codes(payload))


def test_dangling_reference_and_section_family_mismatch_are_blocked() -> None:
    payload = _payload()
    payload["elements"][0]["node_ids"][1] = "N404"
    payload["sections"][0]["family_id"] = "truss_3d"
    payload["sections"][0]["parameters"] = {"area_m2": 0.02}

    report = validate_model_ir_v2(payload)

    assert report.schema_valid is True
    assert report.analysis_ready is False
    assert {"dangling_reference", "element_section_family_mismatch"}.issubset(
        _issue_codes(payload)
    )


def test_zero_effective_length_after_offsets_is_blocked() -> None:
    payload = _payload()
    payload["elements"][0]["offsets"]["j_global_m"] = [-2.0, 0.0, 0.0]

    assert "element_zero_effective_length" in _issue_codes(payload)


def test_unit_scale_mismatch_is_blocked() -> None:
    payload = _payload()
    payload["provenance"]["source_units"]["force"] = "kN"

    report = validate_model_ir_v2(payload)

    assert report.schema_valid is True
    assert "unit_scale_mismatch" in _issue_codes(payload)


def test_load_combination_cycle_is_blocked() -> None:
    payload = _payload()
    payload["load_combinations"] = [
        {
            "id": "C1",
            "index": 0,
            "combination_type": "linear",
            "terms": [{"ref_id": "C2", "ref_kind": "load_combination", "factor": 1.0}],
            "source_id": "generated:C1",
            "extensions": {},
        },
        {
            "id": "C2",
            "index": 1,
            "combination_type": "linear",
            "terms": [{"ref_id": "C1", "ref_kind": "load_combination", "factor": 1.0}],
            "source_id": "generated:C2",
            "extensions": {},
        },
    ]

    assert "load_combination_cycle" in _issue_codes(payload)


def test_non_finite_number_is_blocked_even_when_jsonschema_accepts_number_type() -> (
    None
):
    payload = _payload()
    payload["nodes"][1]["coordinates_m"][0] = math.nan

    report = validate_model_ir_v2(payload)

    assert report.analysis_ready is False
    assert "non_finite_number" in _issue_codes(payload)
    assert report.content_hash is None


def test_blocking_unsupported_feature_is_valid_but_not_analysis_ready(
    tmp_path: Path,
) -> None:
    payload = _payload()
    payload["unsupported_features"] = [
        {
            "feature_id": "UF1",
            "kind": "shell_element_not_in_phase0_profile",
            "source_entity_id": "PLATE:1",
            "disposition": "blocked",
            "blocking": True,
            "detail": "Shell formulation is not in the Phase 0 linear 3D profile.",
            "extensions": {},
        }
    ]
    path = tmp_path / "blocked.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_model_ir_v2(payload)

    assert report.contract_valid is True
    assert report.analysis_ready is False
    assert report.blocking_feature_ids == ("UF1",)
    with pytest.raises(ModelIRValidationError):
        load_model_ir_v2(path)
    document = load_model_ir_v2(path, require_analysis_ready=False)
    assert document.analysis_ready is False
    assert document.blocking_feature_ids == ("UF1",)


def test_execution_plan_fields_are_rejected_from_authoritative_model_ir() -> None:
    payload = _payload()
    payload["tensor_catalog"] = []
    payload["operator_descriptors"] = []

    report = validate_model_ir_v2(payload)

    assert report.schema_valid is False
    assert report.analysis_ready is False


def test_duplicate_constraint_is_blocked() -> None:
    payload = _payload()
    duplicate = deepcopy(payload["constraints"][0])
    duplicate["id"] = "BC2"
    duplicate["index"] = 1
    payload["constraints"].append(duplicate)

    codes = _issue_codes(payload)

    assert "duplicate_constrained_dof" in codes


def test_validation_cli_emits_machine_readable_claim_bounded_report(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "report.json"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_model_ir_v2.py",
            str(FIXTURE),
            "--out",
            str(report_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert completed.returncode == 0, completed.stderr
    assert (
        report["schema_version"] == "structural-analysis-model-ir-validation-report.v1"
    )
    assert report["model_ir_schema_version"] == MODEL_IR_V2_SCHEMA_VERSION
    assert report["contract_valid"] is True
    assert report["analysis_ready"] is True
    assert (
        report["claim_boundary"] == "model_ir_contract_validation_not_solver_readiness"
    )
    assert report["content_hash"].startswith("sha256:")


def test_file_loader_rejects_duplicate_json_object_keys(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"schema_version":"structural-analysis-model-ir.v2",'
        '"schema_version":"structural-analysis-model-ir.v2"}',
        encoding="utf-8",
    )

    with pytest.raises(DuplicateJSONKeyError):
        load_model_ir_v2(duplicate)
