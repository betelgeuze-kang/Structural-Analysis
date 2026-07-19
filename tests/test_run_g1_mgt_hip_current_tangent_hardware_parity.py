from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_g1_mgt_hip_current_tangent_hardware_parity.py"
SPEC = importlib.util.spec_from_file_location(
    "run_g1_mgt_hip_current_tangent_hardware_parity",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _committed_receipt() -> dict:
    return module._read_json(ROOT / module.DEFAULT_OUT)


def test_schema_and_runner_contract_are_present() -> None:
    schema = module._read_json(ROOT / module.SCHEMA_PATH)

    Draft202012Validator.check_schema(schema)
    source = SCRIPT.read_text(encoding="utf-8")
    assert "compile_and_run_hardware_fixture" in source
    assert "create_hip_current_tangent_operator_reference" in source
    assert "recompute_reference=True" in source
    assert "--check-source-only" in source
    assert "device_resident_current_tangent_fgmres_not_integrated" in source


def test_action_manifest_is_canonical_little_endian_binary() -> None:
    action = np.linspace(-1.0, 1.0, module.ACTION_COUNT, dtype=np.float64)

    manifest, raw = module._action_manifest(
        repo_root=ROOT,
        action_out=ROOT / module.DEFAULT_ACTION_OUT,
        action=action,
    )

    assert manifest["format"] == module.ACTION_FORMAT
    assert manifest["dtype"] == "<f8"
    assert manifest["shape"] == [70_560]
    assert manifest["byte_length"] == 564_480
    assert manifest["file_sha256"] == manifest["data_hash"]
    assert len(raw) == 564_480


def test_committed_receipt_records_actual_mgt_gfx1030_parity() -> None:
    payload = _committed_receipt()
    hardware = payload["hardware_execution"]
    comparison = payload["comparison"]
    generic = comparison["generic_comparison"]
    context = comparison["actual_mgt_context"]

    assert payload["schema_version"] == module.SCHEMA_VERSION
    assert payload["status"] == "partial"
    assert payload["contract_pass"] is True
    assert payload["contract_scope"] == module.CONTRACT_SCOPE
    assert payload["fixture"]["dimensions"]["equation_count"] == 70_560
    assert payload["fixture"]["fixture_byte_length"] == 36_123_072
    assert hardware["actual_hardware"] is True
    assert hardware["device_name"] == "AMD Radeon RX 6900 XT"
    assert hardware["gcn_arch_name"] == "gfx1030"
    assert hardware["binary_byte_length"] == 56_912
    assert hardware["binary_sha256"] == (
        "sha256:2b579ec5b651a5c7503318a9fe59efcf688d1690726f8bb3e51662de942e39d4"
    )
    assert hardware["runtime_metadata"]["kernel_invocation_count"] == 1
    assert hardware["runtime_metadata"]["mid_action_d2h_transfer_count"] == 0
    assert hardware["runtime_metadata"]["blocking_d2h_synchronization_count"] == 1
    assert hardware["runtime_output_hash"].startswith("sha256:")
    assert hardware["action_artifact"]["byte_length"] == 564_480
    assert hardware["action_artifact"]["data_hash"] == (
        "sha256:9c2eb32c3e568252b0b1a5c3b9e2f8176df19f597742fe6d1439b5cb733a97ab"
    )
    assert generic["contract_pass"] is True
    assert generic["canonical_cpu_max_abs_error_n_per_m"] == 0.0625
    assert generic["device_order_cpu_max_abs_error_n_per_m"] == 0.0
    assert generic["action_data_hash"] == generic["device_order_action_data_hash"]
    assert generic["canonical_action_data_hash"] == (
        "sha256:a4b5fd93cc47de5f86eb129d59d061b444d40e00fa2781a3a35e3b2cfcb2e8e0"
    )
    assert context["actual_mgt_fixture_identity_pass"] is True
    assert context["device_order_bitwise_match"] is True
    claims = payload["claims"]
    assert claims["actual_mgt_current_tangent_action_executed"] is True
    assert claims["cpu_hip_numerical_parity"] is True
    assert claims["device_order_bitwise_parity"] is True
    assert claims["independent_gfx1100_hardware_execution"] is False
    assert claims["device_resident_current_tangent_fgmres"] is False
    assert claims["production_preconditioner_integration"] is False
    assert claims["performance"] is False
    assert claims["g1_full_building_closure"] is False


def test_committed_receipt_and_action_are_source_bound() -> None:
    payload = _committed_receipt()

    validated = module.validate_receipt(
        payload,
        repo_root=ROOT,
        require_current_sources=True,
        require_action_artifact=True,
    )

    assert validated == payload
    passed, reason = module.check_source_only(repo_root=ROOT)
    assert passed is True
    assert reason == "g1_mgt_hip_hardware_parity_sources_consistent"


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


def test_receipt_hash_validation_fails_closed() -> None:
    payload = deepcopy(_committed_receipt())
    payload["receipt_hash"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="hardware_receipt_hash_mismatch"):
        module.validate_receipt(payload, repo_root=ROOT)


def test_committed_receipt_recomputes_cpu_reference_offline() -> None:
    passed, reason = module.check_receipt(repo_root=ROOT)

    assert passed is True
    assert reason == "g1_mgt_hip_hardware_parity_receipt_consistent"
