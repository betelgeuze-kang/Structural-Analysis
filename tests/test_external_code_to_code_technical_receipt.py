"""Tests for the non-promoting external code-to-code execution receipt."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_external_code_to_code_technical_receipt.py"
RECEIPT = (
    ROOT
    / "implementation/phase1/release_evidence/productization/"
    "external_code_to_code_technical_execution_receipt.json"
)
SPEC = importlib.util.spec_from_file_location(
    "run_external_code_to_code_technical_receipt",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _stored_receipt() -> dict[str, object]:
    payload = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_stored_receipt_validates_and_records_actual_technical_execution() -> None:
    payload = _stored_receipt()
    schema = json.loads((ROOT / module.SCHEMA_PATH).read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    module.validate_external_code_to_code_technical_receipt(
        payload,
        repo_root=ROOT,
        require_current_sources=True,
    )

    assert payload["status"] == "partial"
    assert payload["technical_contract_pass"] is True
    assert len(payload["external_assets"]) == 5
    assert all(not row["bundled_in_repository"] for row in payload["external_assets"])
    assert len(payload["comparisons"]) == 5
    assert all(row["contract_pass"] for row in payload["comparisons"])
    assert all(
        metric["contract_pass"]
        for case in payload["comparisons"]
        for metric in case["metrics"]
    )
    assert all(
        runtime["actual_external_execution"] and runtime["version_verified"]
        for runtime in payload["runtimes"].values()
    )
    replay = payload["replay_provenance"]
    assert replay["current_product_replay_pass"] is True
    fresh_execution = (
        replay["external_runtime_executed_in_this_generation"] is True
        and replay["external_execution_reused"] is False
    )
    reused_execution = (
        replay["external_runtime_executed_in_this_generation"] is False
        and replay["external_execution_reused"] is True
        and isinstance(replay["reuse_reason"], str)
        and bool(replay["reuse_reason"].strip())
    )
    assert fresh_execution or reused_execution
    assert (
        module.REUSED_EXECUTION_BLOCKER in payload["blockers_remaining"]
    ) is reused_execution
    portal = payload["comparisons"][2]
    assert portal["case_id"] == "public_corotational_portal_load_path"
    assert len(portal["metrics"]) == 12
    assert payload["claims"][
        "public_corotational_portal_technical_comparison"
    ] is True
    spatial_truss = payload["comparisons"][4]
    assert spatial_truss["case_id"] == (
        "tetrahedral_spatial_truss_combined_load"
    )
    assert len(spatial_truss["metrics"]) == 12
    assert payload["claims"][
        "calculix_spatial_truss_technical_comparison"
    ] is True
    assert payload["claims"]["second_solver_technical_comparison"] is True


def test_debian_metadata_parser_accepts_labeled_field_output(monkeypatch) -> None:
    completed = SimpleNamespace(
        returncode=0,
        stdout="Package: calculix-ccx\nVersion: 2.17-3\nArchitecture: amd64\n",
    )
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: completed)

    assert module._deb_metadata(Path("runtime.deb")) == (
        "calculix-ccx",
        "2.17-3",
        "amd64",
    )


def test_receipt_does_not_promote_legal_hierarchy_or_release_claims() -> None:
    payload = _stored_receipt()

    assert payload["verification_hierarchy_operator_manifest_attached"] is False
    assert payload["verification_hierarchy_credit"] is False
    assert payload["claims"]["product_legal_license_approval"] is False
    assert payload["claims"]["external_runtime_redistribution_approval"] is False
    assert payload["claims"]["verification_level_2"] is False
    assert payload["claims"]["commercial_equivalence"] is False
    assert payload["claims"]["release_readiness"] is False
    assert (
        "public_corotational_material_nonlinear_family_breadth_missing"
        in payload["blockers_remaining"]
    )
    assert len(payload["blockers_remaining"]) >= 8
    assert "does not achieve Verification Level 2" in payload["claim_boundary"]


def test_validation_rejects_rehashed_comparison_tampering() -> None:
    tampered = deepcopy(_stored_receipt())
    tampered["comparisons"][0]["metrics"][0]["product_value"] += 0.25
    tampered["artifact_hash"] = module._artifact_hash(tampered)

    with pytest.raises(
        module.ExternalCodeToCodeReceiptError,
        match="receipt_comparison_error_invalid",
    ):
        module.validate_external_code_to_code_technical_receipt(
            tampered,
            repo_root=ROOT,
            require_current_sources=False,
        )


def test_validation_rejects_rehashed_claim_promotion() -> None:
    tampered = deepcopy(_stored_receipt())
    tampered["claims"]["verification_level_2"] = True
    tampered["artifact_hash"] = module._artifact_hash(tampered)

    with pytest.raises(module.ExternalCodeToCodeReceiptError, match="schema_invalid"):
        module.validate_external_code_to_code_technical_receipt(
            tampered,
            repo_root=ROOT,
            require_current_sources=False,
        )


def test_product_replay_comparison_allows_only_bounded_runtime_drift() -> None:
    stored = _stored_receipt()["comparisons"]
    current = deepcopy(stored)
    metric = current[0]["metrics"][0]
    metric.update(
        module._comparison(
            metric["quantity"],
            metric["product_value"] + 1.0e-13,
            metric["reference_value"],
        )
    )
    assert module._product_replay_values_match(stored, current)

    metric.update(
        module._comparison(
            metric["quantity"],
            metric["product_value"] + 1.0e-6,
            metric["reference_value"],
        )
    )
    assert not module._product_replay_values_match(stored, current)


def test_product_replay_refresh_rebinds_current_sources_without_external_rerun() -> None:
    refreshed = module.refresh_external_code_to_code_product_replay(
        _stored_receipt(),
        repo_root=ROOT,
        reuse_reason="test_current_product_replay",
    )

    assert refreshed["status"] == "partial"
    assert refreshed["technical_contract_pass"] is True
    assert refreshed["replay_provenance"][
        "external_runtime_executed_in_this_generation"
    ] is False
    assert refreshed["replay_provenance"]["external_execution_reused"] is True
    assert refreshed["replay_provenance"]["current_product_replay_pass"] is True
    assert refreshed["replay_provenance"]["reuse_reason"] == (
        "test_current_product_replay"
    )
    assert refreshed["blockers_remaining"][-1] == (
        module.REUSED_EXECUTION_BLOCKER
    )


def test_cli_offline_check_validates_stored_receipt() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert "external_code_to_code_technical_receipt_consistent" in completed.stdout
