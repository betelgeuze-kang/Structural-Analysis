from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_g1_mgt_hip_current_tangent_host_parser_receipt.py"
SPEC = importlib.util.spec_from_file_location(
    "build_g1_mgt_hip_current_tangent_host_parser_receipt",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _committed_receipt() -> dict:
    return module._read_json(ROOT / module.DEFAULT_OUT)


def test_committed_receipt_records_actual_mgt_host_parser_only() -> None:
    payload = _committed_receipt()

    assert module.validate_receipt(payload, repo_root=ROOT) == payload
    assert payload["status"] == "partial"
    assert payload["contract_pass"] is True
    assert payload["contract_scope"] == (
        "actual_mgt_dual_target_compile_and_host_fixture_parser_only"
    )
    assert payload["source_commit_exact_replay_claim"] is False

    fixture = payload["fixture"]
    assert fixture["fixture_hash"] == (
        "sha256:e1163543967ed51afb8db7a4fea0a684ef2e115543294f6073ab79a18060115d"
    )
    assert fixture["schedule_contract_hash"] == (
        "sha256:28c279ec2c02123e179509db764536cf5de694c65ece634607e6fdac58313b8b"
    )
    assert fixture["execution_contract_hash"] == (
        "sha256:586adf46e4ab752ce77d4495df657b21632a0646490adaef79e04c786bf5f5c5"
    )
    assert fixture["dimensions"] == {
        "equation_count": 70_560,
        "frame_element_count": 5_572,
        "frame_incidence_count": 61_494,
        "geometry_element_count": 5_572,
        "geometry_incidence_count": 61_494,
        "global_dof_count": 78_282,
        "reference_nnz": 1_262_462,
    }
    assert fixture["array_count"] == 21
    assert fixture["fixture_byte_length"] == 36_123_072
    assert fixture["fixture_binary_ephemeral"] is True
    assert fixture["fixture_binary_persisted"] is False

    source_compile = payload["synthetic_compile_receipt"]
    assert source_compile["fixture_equation_count"] == 5
    assert source_compile["target_binary_identity_pass"] is True
    assert [row["architecture"] for row in payload["targets"]] == [
        "gfx1030",
        "gfx1100",
    ]
    assert payload["targets"][0]["binary_byte_length"] == 56_912
    assert payload["targets"][0]["binary_sha256"] == (
        "sha256:2b579ec5b651a5c7503318a9fe59efcf688d1690726f8bb3e51662de942e39d4"
    )
    assert payload["targets"][1]["binary_byte_length"] == 57_680
    assert payload["targets"][1]["binary_sha256"] == (
        "sha256:2c99d9a6e65118185b783e5151af5480e17a86cb38dac907195d67a3e421b654"
    )
    assert all(
        row["target_compile"] is True
        and row["host_fixture_parser_execution"] is True
        and row["host_fixture_validation"]["contract_pass"] is True
        and row["host_fixture_validation"]["fixture_hash"] == fixture["fixture_hash"]
        and row["host_fixture_validation"]["equation_count"] == 70_560
        and row["host_fixture_validation"]["fixture_byte_length"] == 36_123_072
        and row["host_fixture_validation"]["actual_hardware_execution"] is False
        and row["host_fixture_validation"]["hip_runtime_api_call_count"] == 0
        for row in payload["targets"]
    )
    assert (
        payload["targets"][0]["host_fixture_validation"]
        == payload["targets"][1]["host_fixture_validation"]
    )

    claims = payload["claims"]
    assert claims["actual_mgt_fixture_constructed"] is True
    assert claims["actual_mgt_dual_target_host_fixture_parser_execution"] is True
    assert claims["actual_mgt_host_parser_hip_runtime_api_calls_zero"] is True
    assert claims["synthetic_and_actual_parser_binary_identity"] is True
    assert claims["actual_hardware_execution"] is False
    assert claims["current_tangent_action_executed"] is False
    assert claims["cpu_hip_numerical_parity"] is False
    assert claims["device_resident_current_tangent_fgmres"] is False
    assert claims["performance"] is False
    assert claims["g1_full_building_closure"] is False
    assert (
        "actual_hardware_current_tangent_action_not_executed"
        in payload["blockers_remaining"]
    )
    assert (
        "actual_mgt_current_tangent_cpu_hip_parity_not_verified"
        in payload["blockers_remaining"]
    )

    schema = json.loads((ROOT / module.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def test_receipt_hash_validation_fails_closed() -> None:
    payload = _committed_receipt()
    payload["receipt_hash"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="receipt_hash_mismatch"):
        module.validate_receipt(payload, repo_root=ROOT)


def test_committed_input_checksums_match_files() -> None:
    payload = _committed_receipt()

    for relative_path, expected in payload["input_checksums"].items():
        assert module.file_sha256(ROOT / relative_path) == expected


def test_committed_receipt_source_identity_is_offline_checkable() -> None:
    passed, reason = module.check_receipt_source_only(repo_root=ROOT)

    assert passed is True, reason
    assert reason == ("g1_mgt_hip_current_tangent_host_parser_sources_consistent")


def test_non_exact_receipt_is_bound_by_current_source_checksums() -> None:
    payload = deepcopy(_committed_receipt())
    assert payload["source_commit_exact_replay_claim"] is False
    payload["source_commit_sha"] = "0" * 40
    payload["receipt_hash"] = module._receipt_hash(payload)

    assert (
        module.validate_receipt(
            payload,
            repo_root=ROOT,
            require_current_sources=True,
        )
        == payload
    )


def test_committed_receipt_is_reproducible() -> None:
    passed, reason = module.check_receipt(repo_root=ROOT)

    assert passed is True, reason
    assert reason == "g1_mgt_hip_current_tangent_host_parser_consistent"
