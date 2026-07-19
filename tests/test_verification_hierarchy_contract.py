from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from structural_analysis.benchmark.acceptance import decide_benchmark
from structural_analysis.benchmark.verification_hierarchy import (
    VERIFICATION_EVIDENCE_SCHEMA_VERSION,
    VERIFICATION_LEVELS,
    build_verification_hierarchy_readiness,
    inspect_verification_evidence,
)


ROOT = Path(__file__).resolve().parents[1]
SHA256 = "b" * 64


def _evidence(level: int, category: str, index: int) -> dict:
    policy = VERIFICATION_LEVELS[level - 1]
    source_scheme = (
        "generated://verification/analytic"
        if level == 1
        else (
            f"customer-shadow://{index:02d}"
            if level == 5
            else f"https://example.org/verification/{level}/{index}"
        )
    )
    license_receipt = {
        "id": f"license-{level}-{index}",
        "approval_status": "approved",
    }
    if level == 5:
        license_receipt["derived_metadata_use_allowed"] = True
    else:
        license_receipt["local_execution_allowed"] = True
        license_receipt["commercial_use_allowed"] = True
    payload = {
        "schema_version": VERIFICATION_EVIDENCE_SCHEMA_VERSION,
        "evidence_id": f"level-{level}-{category}-{index}",
        "level": level,
        "category": category,
        "truth_basis": policy.truth_basis,
        "declared_blockers": [],
        "source": {
            "url_or_doi": source_scheme,
            "sha256": SHA256,
            "license": license_receipt,
        },
        "artifacts": [
            {
                "path": f"evidence/level-{level}-{category}-{index}.json",
                "sha256": SHA256,
                "contract_pass": True,
            }
        ],
        "decision": decide_benchmark(
            [{"metric_family": f"{category}_comparison", "contract_pass": True}],
            decision="PASS",
            evaluated_at="2026-07-18T00:00:00Z",
        ),
    }
    if level == 2:
        payload["reference"] = {
            "name": "OpenSees" if category == "opensees_code_to_code" else "Code_Aster",
            "version": "3.7.1" if category == "opensees_code_to_code" else "17.2",
            "version_verified": True,
            "independent_from_product": True,
        }
    elif level == 3:
        payload["publication"] = {
            "benchmark_name": category,
            "publisher": "Independent benchmark publisher",
        }
    elif level == 4:
        payload["experiment"] = {
            "dataset_id": f"experiment-{index}",
            "measurement_categories": [category],
        }
    elif level == 5:
        payload["customer_shadow"] = {
            "case_id_hash": f"sha256:{index + 1:064x}",
            "project_status": "completed",
            "raw_data_retained_by_customer": True,
            "redistribution_allowed": False,
            "reviewer_id": f"customer-reviewer-{index}",
        }
    return payload


def _complete_hierarchy() -> list[dict]:
    rows: list[dict] = []
    index = 0
    for policy in VERIFICATION_LEVELS:
        for slot in policy.slots:
            for _ in range(slot.minimum_evidence_count):
                rows.append(_evidence(policy.level, slot.category, index))
                index += 1
    return rows


def test_empty_hierarchy_exposes_all_levels_without_promotion() -> None:
    result = build_verification_hierarchy_readiness([])

    assert result["contract_pass"] is False
    assert result["highest_verified_level"] == 0
    assert result["evidence_count"] == 0
    assert result["input_blockers"] == []
    assert [row["level_id"] for row in result["level_rows"]] == [
        "analytic",
        "code_to_code",
        "published_benchmark",
        "experimental",
        "customer_shadow",
    ]
    assert all(row["status"] == "missing" for row in result["level_rows"])


def test_complete_hierarchy_passes_contiguously_and_validates_schema() -> None:
    result = build_verification_hierarchy_readiness(_complete_hierarchy())

    assert result["contract_pass"] is True
    assert result["highest_verified_level"] == 5
    assert result["ready_evidence_count"] == 17
    assert all(row["promotion_contract_pass"] is True for row in result["level_rows"])
    schema = json.loads(
        (
            ROOT
            / "src/structural_analysis/schemas/structural_verification_hierarchy_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    evidence_schema = json.loads(
        (
            ROOT
            / "src/structural_analysis/schemas/structural_verification_evidence_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator.check_schema(evidence_schema)
    Draft202012Validator(schema).validate(result)
    Draft202012Validator(evidence_schema).validate(_complete_hierarchy()[0])


def test_higher_level_evidence_cannot_bypass_missing_analytic_level() -> None:
    level_two = [
        _evidence(2, "opensees_code_to_code", 1),
        _evidence(2, "second_solver_code_to_code", 2),
    ]

    result = build_verification_hierarchy_readiness(level_two)
    code_to_code = result["level_rows"][1]

    assert code_to_code["intrinsic_contract_pass"] is True
    assert code_to_code["promotion_contract_pass"] is False
    assert code_to_code["status"] == "blocked_by_prerequisite"
    assert (
        "verification_hierarchy_prerequisite_level_not_passed:1"
        in (code_to_code["blockers"])
    )
    assert result["highest_verified_level"] == 0


def test_level_specific_rules_and_decision_receipt_resist_boolean_forgery() -> None:
    row = _evidence(2, "opensees_code_to_code", 1)
    row["reference"]["independent_from_product"] = False
    row["artifacts"][0]["contract_pass"] = False
    row["decision"] = {
        "decision": "PASS",
        "decision_contract_pass": True,
        "benchmark_credit": True,
    }

    inspected = inspect_verification_evidence(row)

    assert inspected["ready_for_hierarchy_credit"] is False
    assert (
        "verification_evidence_reference_solver_not_independent"
        in inspected["blockers"]
    )
    assert (
        "verification_evidence_artifact_contract_not_passed:0" in inspected["blockers"]
    )
    assert any(
        blocker.startswith("verification_evidence_decision:")
        for blocker in inspected["blockers"]
    )


def test_duplicate_evidence_ids_remain_explicit_blockers() -> None:
    rows = _complete_hierarchy()
    duplicate = deepcopy(rows[0])
    rows.append(duplicate)

    result = build_verification_hierarchy_readiness(rows)

    assert result["contract_pass"] is False
    assert (
        f"verification_hierarchy_duplicate_evidence_id:{duplicate['evidence_id']}"
        in result["blockers"]
    )


def test_operator_manifest_blocker_cannot_be_hidden_by_complete_evidence() -> None:
    result = build_verification_hierarchy_readiness(
        _complete_hierarchy(),
        input_blockers=["verification_hierarchy_operator_manifest_schema_invalid"],
    )

    assert result["highest_verified_level"] == 5
    assert result["contract_pass"] is False
    assert result["input_blockers"] == [
        "verification_hierarchy_operator_manifest_schema_invalid"
    ]
