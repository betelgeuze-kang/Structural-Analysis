from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from structural_analysis.benchmark.acceptance import (
    BenchmarkAcceptanceError,
    compare_buckling,
    compare_displacements,
    compare_global_energy_norm,
    compare_member_forces_local,
    compare_modal,
    compare_nonlinear_path,
    compare_reactions,
    compare_residual_observation,
    decide_benchmark,
    inspect_benchmark_decision_receipt,
)


TOLERANCE = {
    "absolute": 1.0e-6,
    "relative": 2.0e-3,
    "near_zero_reference": 1.0e-9,
}
ROOT = Path(__file__).resolve().parents[1]


def test_displacement_uses_near_zero_absolute_and_global_norm_gates() -> None:
    passing = compare_displacements(
        [0.0, 1.0],
        [5.0e-7, 1.001],
        component_tolerance=TOLERANCE,
        norm_tolerance=TOLERANCE,
    )
    failing = compare_displacements(
        [0.0, 1.0],
        [2.0e-6, 1.001],
        component_tolerance=TOLERANCE,
        norm_tolerance=TOLERANCE,
    )

    assert passing["contract_pass"] is True
    assert passing["component_rows"][0]["tolerance_mode"] == "absolute_near_zero"
    assert passing["component_rows"][0]["relative_error"] is None
    assert passing["norm"]["difference_norm"] > 0.0
    assert failing["component_contract_pass"] is False
    assert failing["contract_pass"] is False


def test_reaction_comparison_keeps_equilibrium_as_an_independent_gate() -> None:
    result = compare_reactions(
        reference=[-10.0, 0.0],
        actual=[-9.9, 0.0],
        external_resultant=[10.0, 0.0],
        component_tolerance={
            "absolute": 0.2,
            "relative": 0.02,
            "near_zero_reference": 1.0e-9,
        },
        norm_tolerance={
            "absolute": 0.2,
            "relative": 0.02,
            "near_zero_reference": 1.0e-9,
        },
        equilibrium_absolute_tolerance=0.05,
    )

    assert result["component_contract_pass"] is True
    assert result["norm_contract_pass"] is True
    assert result["equilibrium"]["imbalance_norm"] == pytest.approx(0.1)
    assert result["equilibrium"]["contract_pass"] is False
    assert result["contract_pass"] is False


def test_member_force_and_global_energy_use_local_components_and_stiffness() -> None:
    member = compare_member_forces_local(
        reference={"N": [100.0, 0.0], "My": [10.0, -10.0]},
        actual={"N": [100.1, 5.0e-7], "My": [10.01, -10.01]},
        component_tolerances={"N": TOLERANCE, "My": TOLERANCE},
        norm_tolerance=TOLERANCE,
    )
    energy = compare_global_energy_norm(
        reference_displacement=[1.0, 2.0],
        actual_displacement=[1.001, 2.0],
        stiffness_matrix=[[4.0, 0.0], [0.0, 1.0]],
        absolute_tolerance=1.0e-6,
        relative_tolerance=1.0e-3,
    )

    assert member["contract_pass"] is True
    assert [row["local_component"] for row in member["local_component_rows"]] == [
        "My",
        "N",
    ]
    assert energy["reference_energy_norm"] == pytest.approx(2.8284271247461903)
    assert energy["error_energy_norm"] == pytest.approx(0.002)
    assert energy["contract_pass"] is True

    with pytest.raises(BenchmarkAcceptanceError) as exc_info:
        compare_global_energy_norm(
            [1.0, 0.0],
            [1.0, 0.0],
            [[1.0, 2.0], [0.0, 1.0]],
            absolute_tolerance=1.0e-6,
            relative_tolerance=1.0e-3,
        )
    assert exc_info.value.code == "benchmark_stiffness_not_symmetric"
    assert exc_info.value.path == "/global_energy/stiffness_matrix/0/1"


def test_modal_buckling_nonlinear_and_residual_families_have_distinct_policies() -> (
    None
):
    modal = compare_modal(
        [1.0, 2.0],
        [1.001, 1.999],
        [[1.0, 0.0], [0.0, 1.0]],
        [[-1.0, 0.0], [0.0, 1.0]],
        frequency_tolerance=TOLERANCE,
        minimum_mac=0.99,
    )
    buckling = compare_buckling(
        [10.0],
        [10.1],
        [[1.0, 0.0]],
        [[0.9, 0.1]],
        eigenvalue_tolerance=TOLERANCE,
        minimum_mac=0.99,
    )
    nonlinear = compare_nonlinear_path(
        [[0.0, 0.0], [0.5, 0.2], [1.0, 0.5]],
        [[0.0, 0.0], [0.5, 0.205], [1.0, 0.51]],
        load_scale=1.0,
        response_scale=0.5,
        maximum_path_distance=0.03,
        rms_path_distance=0.02,
    )
    residual = compare_residual_observation(
        raw_translation_norm=1.0e-8,
        raw_rotation_norm=2.0e-8,
        scaled_norm=5.0e-9,
        maximum_raw_translation_norm=1.0e-7,
        maximum_raw_rotation_norm=1.0e-7,
        maximum_scaled_norm=1.0e-8,
    )

    assert modal["contract_pass"] is True
    assert modal["mode_rows"][0]["mac"] == 1.0
    assert buckling["contract_pass"] is False
    assert buckling["mode_rows"][0]["value"]["contract_pass"] is False
    assert nonlinear["contract_pass"] is True
    assert nonlinear["maximum_path_distance"] == pytest.approx(0.02)
    assert residual["contract_pass"] is True


def test_pass_review_fail_decisions_do_not_hide_hard_blockers() -> None:
    passing_metric = {
        "metric_family": "displacement",
        "contract_pass": True,
    }
    failing_metric = {
        "metric_family": "reaction_equilibrium",
        "contract_pass": False,
    }
    evaluated_at = datetime(2026, 7, 18, tzinfo=timezone.utc)
    review = {
        "engineer_id": "PE-KR-1042",
        "reason": "Near-zero support reaction is accepted inside the documented scope.",
        "scope": ["reaction_equilibrium"],
        "evidence_ref": "operator-review://medium-case-4",
        "approved_at": "2026-07-17T10:00:00+09:00",
        "expires_at": "2026-08-18T00:00:00+09:00",
    }

    passed = decide_benchmark(
        [passing_metric],
        decision="PASS",
        evaluated_at=evaluated_at,
    )
    reviewed = decide_benchmark(
        [passing_metric, failing_metric],
        decision="REVIEW",
        review=review,
        evaluated_at=evaluated_at,
    )
    review_blocked = decide_benchmark(
        [failing_metric],
        decision="REVIEW",
        review=review,
        hard_blockers=["artifact_checksum_mismatch"],
        evaluated_at=evaluated_at,
    )
    failed = decide_benchmark(
        [failing_metric],
        decision="FAIL",
        hard_blockers=["artifact_checksum_mismatch"],
        evaluated_at=evaluated_at,
    )

    assert passed["benchmark_credit"] is True
    assert passed["numerical_pass"] is True
    assert passed["metric_families"] == ["displacement"]
    assert reviewed["numerical_pass"] is False
    assert reviewed["review"]["contract_pass"] is True
    assert reviewed["failing_metric_families"] == ["reaction_equilibrium"]
    assert reviewed["benchmark_credit"] is True
    assert review_blocked["decision_contract_pass"] is False
    assert review_blocked["benchmark_credit"] is False
    assert failed["decision_contract_pass"] is True
    assert failed["benchmark_credit"] is False

    acceptance_schema = json.loads(
        (
            ROOT
            / "src/structural_analysis/schemas/benchmark_scientific_acceptance_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    decision_schema = json.loads(
        (
            ROOT
            / "src/structural_analysis/schemas/benchmark_scientific_decision_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(acceptance_schema)
    Draft202012Validator.check_schema(decision_schema)
    Draft202012Validator(acceptance_schema).validate(
        passing_metric
        | {
            "schema_version": "benchmark-scientific-acceptance.v1",
        }
    )
    Draft202012Validator(decision_schema, format_checker=FormatChecker()).validate(
        reviewed
    )


def test_review_requires_complete_scope_and_unexpired_engineer_metadata() -> None:
    result = decide_benchmark(
        [{"metric_family": "member_force_local", "contract_pass": False}],
        decision="REVIEW",
        review={
            "engineer_id": "TBD",
            "reason": "",
            "scope": ["displacement"],
            "evidence_ref": "template://review",
            "approved_at": "2026-07-17T00:00:00Z",
            "expires_at": "2026-07-18T00:00:00Z",
        },
        evaluated_at="2026-07-18T01:00:00Z",
    )

    assert result["benchmark_credit"] is False
    assert "benchmark_review_engineer_id_missing" in result["decision_blockers"]
    assert "benchmark_review_reason_missing" in result["decision_blockers"]
    assert "benchmark_review_evidence_ref_invalid" in result["decision_blockers"]
    assert "benchmark_review_expired" in result["decision_blockers"]
    assert "benchmark_review_scope_incomplete" in result["decision_blockers"]


def test_non_finite_values_fail_with_stable_code_and_path() -> None:
    with pytest.raises(BenchmarkAcceptanceError) as exc_info:
        compare_displacements(
            [0.0],
            [float("nan")],
            component_tolerance=TOLERANCE,
            norm_tolerance=TOLERANCE,
        )

    assert exc_info.value.code == "benchmark_number_non_finite"
    assert exc_info.value.path == "/displacement/actual/0"


def test_decision_rejects_missing_and_duplicate_metric_family_ids() -> None:
    with pytest.raises(BenchmarkAcceptanceError) as missing:
        decide_benchmark([{"contract_pass": True}], decision="PASS")
    assert missing.value.code == "benchmark_metric_family_missing"
    assert missing.value.path == "/metric_results/0/metric_family"

    with pytest.raises(BenchmarkAcceptanceError) as duplicate:
        decide_benchmark(
            [
                {"metric_family": "displacement", "contract_pass": True},
                {"metric_family": "displacement", "contract_pass": True},
            ],
            decision="PASS",
        )
    assert duplicate.value.code == "benchmark_metric_family_duplicate"
    assert duplicate.value.path == "/metric_results/1/metric_family"


def test_serialized_decision_inspector_rejects_scope_and_count_forgery() -> None:
    decision = decide_benchmark(
        [
            {"metric_family": "displacement", "contract_pass": True},
            {"metric_family": "reaction_equilibrium", "contract_pass": False},
        ],
        decision="REVIEW",
        review={
            "engineer_id": "PE-KR-1042",
            "reason": "Scoped reaction review.",
            "scope": ["reaction_equilibrium"],
            "evidence_ref": "operator-review://case-2",
            "approved_at": "2026-07-17T00:00:00Z",
            "expires_at": "2026-08-18T00:00:00Z",
        },
        evaluated_at="2026-07-18T00:00:00Z",
    )

    valid = inspect_benchmark_decision_receipt(
        decision,
        required_metric_families=["displacement", "reaction_equilibrium"],
        as_of="2026-07-19T00:00:00Z",
    )
    forged = dict(decision)
    forged["failing_metric_families"] = []
    invalid = inspect_benchmark_decision_receipt(forged)

    assert valid["contract_pass"] is True
    assert invalid["contract_pass"] is False
    assert "benchmark_decision_receipt_failing_count_mismatch" in invalid["blockers"]
    assert "benchmark_decision_receipt_review_without_failures" in invalid["blockers"]


def test_serialized_review_expires_at_inspection_time() -> None:
    decision = decide_benchmark(
        [{"metric_family": "reaction_equilibrium", "contract_pass": False}],
        decision="REVIEW",
        review={
            "engineer_id": "PE-KR-1042",
            "reason": "Scoped reaction review.",
            "scope": ["reaction_equilibrium"],
            "evidence_ref": "operator-review://case-expiry",
            "approved_at": "2026-07-17T00:00:00Z",
            "expires_at": "2026-07-20T00:00:00Z",
        },
        evaluated_at="2026-07-18T00:00:00Z",
    )

    before_expiry = inspect_benchmark_decision_receipt(
        decision,
        as_of="2026-07-19T00:00:00Z",
    )
    after_expiry = inspect_benchmark_decision_receipt(
        decision,
        as_of="2026-07-21T00:00:00Z",
    )

    assert before_expiry["contract_pass"] is True
    assert after_expiry["contract_pass"] is False
    assert "benchmark_review_expired_at_inspection" in after_expiry["blockers"]
