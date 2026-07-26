from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_p3_entry_gate.py"
SPEC = importlib.util.spec_from_file_location("build_p3_entry_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _load(relative: str) -> dict[str, object]:
    payload = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_current_p3_entry_gate_is_current_and_fail_closed() -> None:
    payload = module.build_p3_entry_gate(ROOT)

    assert payload["schema_version"] == "structural-analysis-p3-entry-gate.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is True
    assert payload["authoritative_release_snapshot"] is False
    assert payload["entry_gate_pass"] is False
    assert payload["p3_completion_pass"] is False
    assert all(
        row["observed"] == "blocked" and row["pass"] is False
        for row in payload["phase_prerequisite_checks"]
    )
    pr_check = next(
        row
        for row in payload["snapshot_and_sequence_checks"]
        if row["id"] == "ordered_prs_1_through_18_closed"
    )
    assert pr_check["observed"] == 0
    assert pr_check["missing_or_open_pr_numbers"] == list(range(1, 19))
    assert all(row["pass"] is False for row in payload["external_evidence_checks"])

    feature_rows = payload["p3_feature_checks"]
    assert {row["capability_id"] for row in feature_rows} == set(
        module.P3_CAPABILITY_IDS
    )
    assert all(row["status"] == "blocked" for row in feature_rows)
    assert all(row["public"] is False for row in feature_rows)
    assert all(row["authority"] == "none" for row in feature_rows)
    assert all(row["completion_pass"] is False for row in feature_rows)
    assert payload["customer_shadow_check"]["observed"] == 0
    assert payload["customer_shadow_check"]["required_minimum"] == 3
    assert payload["customer_shadow_check"]["pass"] is False
    assert all(row["promotable"] is False for row in payload["proxy_inventory"])

    current, message = module.check_p3_entry_gate(repo_root=ROOT)
    assert current is True
    assert message == "p3_entry_gate_current"


def test_entry_gate_can_open_only_when_every_precondition_is_authoritative() -> None:
    roadmap = _load("artifacts/manifests/product_roadmap_status.json")
    registry = _load("artifacts/manifests/capabilities.yaml")
    customer = _load("implementation/phase1/customer_shadow_evidence_status.json")

    roadmap["phases"] = {"P0": "closed", "P1": "closed", "P2": "closed", "P3": "blocked"}
    roadmap["pull_requests"] = [
        {"number": number, "phase": "P0", "status": "closed"}
        for number in range(1, 19)
    ]
    roadmap["authoritative_release_snapshot"] = True
    roadmap["closure_pass"] = True
    roadmap["required_external_evidence"] = {
        evidence_id: True for evidence_id in module.REQUIRED_EXTERNAL_EVIDENCE_IDS
    }

    payload = module.evaluate_p3_entry_gate(
        roadmap_status=roadmap,
        capability_registry=registry,
        customer_shadow_status=customer,
        input_checksums={},
    )

    assert payload["entry_gate_pass"] is True
    assert payload["p3_completion_pass"] is False
    assert payload["customer_shadow_check"]["pass"] is False
    assert all(row["completion_pass"] is False for row in payload["p3_feature_checks"])


def test_missing_external_evidence_key_fails_closed() -> None:
    roadmap = _load("artifacts/manifests/product_roadmap_status.json")
    registry = _load("artifacts/manifests/capabilities.yaml")
    customer = _load("implementation/phase1/customer_shadow_evidence_status.json")
    external = dict(roadmap["required_external_evidence"])
    external.pop("signed_engineering_review")
    roadmap["required_external_evidence"] = external

    payload = module.evaluate_p3_entry_gate(
        roadmap_status=roadmap,
        capability_registry=registry,
        customer_shadow_status=customer,
        input_checksums={},
    )
    check = next(
        row
        for row in payload["external_evidence_checks"]
        if row["id"] == "signed_engineering_review"
    )

    assert check["observed"] is None
    assert check["pass"] is False
    assert "signed_engineering_review" in payload["blockers"]
