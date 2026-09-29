"""Cost ranking must retain the signed force floor and its provenance identity."""

from copy import deepcopy
import hashlib
import json

import pytest

from structural_analysis.benchmark.rc_control_candidate_cost import (
    COST_AUDIT_V1,
    COST_AUDIT_V2,
    COST_AUDIT_V3,
    FORCE_FLOOR_COMPARISON,
    FORCE_FLOOR_PLAN,
    candidate_cost_optimality_audit,
)


FLOOR = {
    "target_index": 0,
    "target_control_displacement_m": -0.02,
    "minimum_load_factor": 1.0,
}


def _case():
    rows = []
    for name, price, factor in (
        ("baseline", 300, 1.2),
        ("cheap", 100, -1.1),
        ("middle", 200, 1.1),
    ):
        rows.append(
            {
                "candidate_id": name,
                "material_estimate": {
                    "total": price,
                    "currency": "KRW",
                    "scope": "synthetic-test",
                    "price_table_hash": "common",
                },
                "full_reference_verification_pass": True,
                "screens": {
                    "limit": {"status": "pass"},
                    "load_factor_at_target": {
                        "value": factor,
                        "limit": FLOOR["minimum_load_factor"],
                        "status": (
                            "pass" if factor >= FLOOR["minimum_load_factor"] else "fail"
                        ),
                        "comparison": "at_least",
                    },
                },
            }
        )
    plan = {
        "schema_version": FORCE_FLOOR_PLAN,
        "source_revision": "a" * 40,
        "baseline_checksum": "sha256:baseline",
        "control_request": {"schema_version": "test-request.v1", "targets_m": [-0.02]},
        "force_response_floor": deepcopy(FLOOR),
        "pool": deepcopy(rows),
        "price_table_hash": "common",
        "history_limits": {"limit": 1},
        "material_limits": {},
        "terminal_limits": None,
        "plans": {"price_order": {"shortlist": ["cheap", "middle"]}},
    }
    reports = {
        name: {
            "schema_version": FORCE_FLOOR_COMPARISON,
            "source_revision": plan["source_revision"],
            "baseline_checksum": plan["baseline_checksum"],
            "control_request": deepcopy(plan["control_request"]),
            "force_response_floor": deepcopy(FLOOR),
            "rows": deepcopy(rows),
            "price_table_hash": "common",
            "report_hash": name,
            "selected_candidate_id": "middle",
        }
        for name in ("price_order", "exhaustive_oracle")
    }
    return plan, reports


def _legacy_case():
    plan, reports = _case()
    plan["schema_version"] = "experimental-rc-control-candidate-search-plan.v2"
    del plan["force_response_floor"]
    for report in reports.values():
        del report["force_response_floor"]
        for row in report["rows"]:
            del row["screens"]["load_factor_at_target"]
    return plan, reports


def test_cheaper_signed_floor_failure_is_excluded_from_oracle_minimum():
    plan, reports = _case()
    audit = candidate_cost_optimality_audit(plan, reports)
    assert audit["schema_version"] == COST_AUDIT_V3
    assert audit["force_response_floor"] == FLOOR
    assert audit["status"] == "complete"
    assert audit["pool_minimum_feasible_candidate_ids"] == ["middle"]
    assert audit["pool_minimum_feasible_estimate"] == 200
    assert audit["arms"]["price_order"]["selected_minus_pool_minimum_estimate"] == 0


def test_selected_cheaper_floor_failure_cannot_be_certified():
    plan, reports = _case()
    reports["price_order"]["selected_candidate_id"] = "cheap"
    with pytest.raises(ValueError, match="selection needs full reference"):
        candidate_cost_optimality_audit(plan, reports)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda screen: screen.clear(),
        lambda screen: screen.update(status="pass"),
        lambda screen: screen.update(comparison="absolute_at_least"),
        lambda screen: screen.update(limit=0.5),
        lambda screen: screen.update(limit=1),
        lambda screen: screen.update(value=float("nan")),
    ],
)
def test_missing_or_forged_oracle_floor_screen_keeps_minimum_unknown(mutation):
    plan, reports = _case()
    screen = reports["exhaustive_oracle"]["rows"][1]["screens"][
        "load_factor_at_target"
    ]
    mutation(screen)
    audit = candidate_cost_optimality_audit(plan, reports)
    assert audit["status"] == "oracle_incomplete"
    assert audit["oracle_unverifiable_candidate_ids"] == ["cheap"]
    assert audit["pool_minimum_feasible_estimate"] is None
    assert audit["arms"]["price_order"]["selected_minus_pool_minimum_estimate"] is None


@pytest.mark.parametrize("mutation", ["missing", "target", "limit", "type"])
def test_comparison_floor_identity_must_match_plan(mutation):
    plan, reports = _case()
    if mutation == "missing":
        del reports["price_order"]["force_response_floor"]
    elif mutation == "target":
        reports["price_order"]["force_response_floor"]["target_index"] = 1
    elif mutation == "type":
        reports["price_order"]["force_response_floor"][
            "minimum_load_factor"
        ] = 1
    else:
        reports["exhaustive_oracle"]["force_response_floor"][
            "minimum_load_factor"
        ] = 0.9
    with pytest.raises(ValueError, match="comparison force floor mismatch"):
        candidate_cost_optimality_audit(plan, reports)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("schema_version", "experimental-rc-control-design-comparison.v1"),
        ("control_request", {"schema_version": "test-request.v1", "targets_m": [-0.03]}),
        ("baseline_checksum", "sha256:other-baseline"),
        ("source_revision", "b" * 40),
    ],
)
def test_floor_comparison_source_identity_must_match_frozen_plan(field, replacement):
    plan, reports = _case()
    reports["exhaustive_oracle"][field] = replacement
    with pytest.raises(ValueError, match="comparison force floor source mismatch"):
        candidate_cost_optimality_audit(plan, reports)


@pytest.mark.parametrize("field", ["schema_version", "control_request", "baseline_checksum", "source_revision"])
def test_floor_comparison_cannot_omit_source_identity(field):
    plan, reports = _case()
    del reports["price_order"][field]
    with pytest.raises(ValueError, match="comparison force floor source mismatch"):
        candidate_cost_optimality_audit(plan, reports)


def test_floor_comparison_price_identity_must_match_frozen_plan():
    plan, reports = _case()
    reports["exhaustive_oracle"]["price_table_hash"] = "other"
    with pytest.raises(ValueError, match="comparison price table mismatch"):
        candidate_cost_optimality_audit(plan, reports)


@pytest.mark.parametrize("field", ["control_request", "baseline_checksum", "source_revision"])
def test_floor_plan_requires_source_identity(field):
    plan, reports = _case()
    del plan[field]
    with pytest.raises(ValueError, match="frozen force floor source identity"):
        candidate_cost_optimality_audit(plan, reports)


def test_floor_plan_cannot_downgrade_audit_version():
    plan, reports = _case()
    for version in (COST_AUDIT_V1, COST_AUDIT_V2):
        with pytest.raises(ValueError, match="force floor plan requires"):
            candidate_cost_optimality_audit(plan, reports, schema_version=version)


def test_legacy_v1_v2_audit_bytes_stay_stable():
    plan, reports = _legacy_case()
    assert candidate_cost_optimality_audit(plan, reports) == (
        candidate_cost_optimality_audit(plan, reports, schema_version=COST_AUDIT_V2)
    )
    for version, expected_sha256 in (
        (
            COST_AUDIT_V1,
            "ef5ca508e57845b0bdad997f654189e199c28a1e0fd3215df3403368c8200696",
        ),
        (
            COST_AUDIT_V2,
            "0afa6f9398638c75c922134e9ad0012762d7a01c5322e15e2abca8ada622b8fc",
        ),
    ):
        audit = candidate_cost_optimality_audit(plan, reports, schema_version=version)
        payload = json.dumps(audit, separators=(",", ":"), ensure_ascii=False).encode()
        assert hashlib.sha256(payload).hexdigest() == expected_sha256
