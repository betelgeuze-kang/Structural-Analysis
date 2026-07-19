from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2_backends.hip_current_tangent_operator import (  # noqa: E402
    HIP_CURRENT_TANGENT_ACCUMULATION_PROFILE,
    HIP_CURRENT_TANGENT_EXECUTION_PROFILE,
    HIP_CURRENT_TANGENT_FIXTURE_VALIDATION_OUTPUT_VERSION,
    HIP_CURRENT_TANGENT_OUTPUT_VERSION,
    build_hip_current_tangent_operator_reference,
    validate_hip_current_tangent_fixture_parser_output,
)


def _load_runner():
    path = ROOT / "scripts/run_engine_v2_hip_current_tangent_operator.py"
    spec = importlib.util.spec_from_file_location(
        "hip_current_tangent_runner",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("runner import failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runtime_output() -> dict[str, object]:
    reference = build_hip_current_tangent_operator_reference()
    fixture = reference.fixture
    return {
        "schema_version": HIP_CURRENT_TANGENT_OUTPUT_VERSION,
        "status": "ok",
        "cpu_backend": False,
        "device_name": "AMD Radeon test fixture",
        "gcn_arch_name": "gfx1030",
        "execution_profile": HIP_CURRENT_TANGENT_EXECUTION_PROFILE,
        "accumulation_profile": HIP_CURRENT_TANGENT_ACCUMULATION_PROFILE,
        "equation_count": fixture.equation_count,
        "kernel_invocation_count": fixture.expected_kernel_invocation_count,
        "mid_action_d2h_transfer_count": 0,
        "blocking_d2h_synchronization_count": 1,
        "action_n_per_m": reference.device_order_action_n_per_m.tolist(),
    }


def _host_fixture_validation() -> dict[str, object]:
    fixture = build_hip_current_tangent_operator_reference().fixture
    output = {
        "schema_version": (HIP_CURRENT_TANGENT_FIXTURE_VALIDATION_OUTPUT_VERSION),
        "status": "ok",
        "mode": "host_fixture_validation_only",
        "actual_hardware": False,
        "hip_runtime_api_call_count": 0,
        "equation_count": fixture.equation_count,
        "global_dof_count": fixture.global_dof_count,
        "reference_nnz": fixture.operator.reference_nnz,
        "frame_element_count": fixture.operator.frame_element_count,
        "geometry_element_count": fixture.operator.geometry_element_count,
        "frame_incidence_count": fixture.frame_incidence_count,
        "geometry_incidence_count": fixture.geometry_incidence_count,
        "expected_kernel_invocation_count": (fixture.expected_kernel_invocation_count),
        "fixture_byte_length": len(fixture.to_bytes()),
    }
    return validate_hip_current_tangent_fixture_parser_output(fixture, output)


def test_runner_builds_source_bound_partial_hardware_receipt() -> None:
    runner = _load_runner()

    receipt = runner.build_receipt_from_runtime_output(
        _runtime_output(),
        repo_root=ROOT,
        compiler_path="/opt/rocm/bin/hipcc",
        compiler_version_output="HIP version: synthetic-test\n",
        binary_sha256="sha256:" + "a" * 64,
    )

    assert receipt["status"] == "partial"
    assert receipt["contract_pass"] is True
    assert receipt["hardware_execution"]["actual_hardware"] is True
    assert receipt["comparison"]["contract_pass"] is True
    assert receipt["claims"]["actual_hardware_current_tangent_action"] is True
    assert receipt["claims"]["current_tangent_numerical_parity"] is True
    assert receipt["claims"]["gfx1030_local_current_tangent_action"] is True
    assert receipt["claims"]["gfx1100_independent_current_tangent_action"] is False
    assert receipt["claims"]["actual_mgt_current_tangent_action"] is False
    assert receipt["claims"]["production_current_tangent_fgmres"] is False
    assert receipt["claims"]["performance"] is False
    assert runner.validate_receipt(receipt, repo_root=ROOT) == receipt


def test_runner_rejects_stale_hardware_receipt_hash() -> None:
    runner = _load_runner()
    receipt = runner.build_receipt_from_runtime_output(
        _runtime_output(),
        repo_root=ROOT,
        compiler_path="/opt/rocm/bin/hipcc",
        compiler_version_output="HIP version: synthetic-test\n",
        binary_sha256="sha256:" + "b" * 64,
    )
    receipt["receipt_hash"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="receipt_hash_mismatch"):
        runner.validate_receipt(receipt, repo_root=ROOT)


def test_runner_builds_dual_target_compile_only_receipt() -> None:
    runner = _load_runner()

    receipt = runner.build_compile_receipt(
        repo_root=ROOT,
        compiler_path="/opt/rocm/bin/hipcc",
        compiler_version_output="HIP version: synthetic-test\n",
        targets=[
            {
                "architecture": "gfx1100",
                "target_compile": True,
                "binary_sha256": "sha256:" + "d" * 64,
                "binary_byte_length": 57_680,
                "host_fixture_parser_execution": True,
                "host_fixture_validation": _host_fixture_validation(),
            },
            {
                "architecture": "gfx1030",
                "target_compile": True,
                "binary_sha256": "sha256:" + "c" * 64,
                "binary_byte_length": 56_912,
                "host_fixture_parser_execution": True,
                "host_fixture_validation": _host_fixture_validation(),
            },
        ],
    )

    assert receipt["contract_scope"] == ("target_compile_and_host_fixture_parser_only")
    assert [row["architecture"] for row in receipt["targets"]] == [
        "gfx1030",
        "gfx1100",
    ]
    assert receipt["claims"]["gfx1030_target_compile"] is True
    assert receipt["claims"]["gfx1100_target_compile"] is True
    assert receipt["claims"]["dual_target_host_fixture_parser_execution"] is True
    assert all(
        row["host_fixture_parser_execution"] is True
        and row["host_fixture_validation"]["contract_pass"] is True
        and row["host_fixture_validation"]["actual_hardware_execution"] is False
        and row["host_fixture_validation"]["hip_runtime_api_call_count"] == 0
        for row in receipt["targets"]
    )
    assert receipt["claims"]["actual_hardware_execution"] is False
    assert receipt["claims"]["numerical_parity"] is False
    assert receipt["claims"]["actual_mgt_current_tangent_action"] is False
    assert receipt["claims"]["production_current_tangent_fgmres"] is False
    assert receipt["claims"]["performance"] is False
    assert runner.validate_compile_receipt(receipt, repo_root=ROOT) == receipt


def test_non_exact_compile_receipt_is_bound_by_current_source_checksums() -> None:
    runner = _load_runner()
    receipt = runner.build_compile_receipt(
        repo_root=ROOT,
        compiler_path="/opt/rocm/bin/hipcc",
        compiler_version_output="HIP version: synthetic-test\n",
        targets=[
            {
                "architecture": architecture,
                "target_compile": True,
                "binary_sha256": "sha256:" + marker * 64,
                "binary_byte_length": byte_length,
                "host_fixture_parser_execution": True,
                "host_fixture_validation": _host_fixture_validation(),
            }
            for architecture, marker, byte_length in (
                ("gfx1030", "c", 56_912),
                ("gfx1100", "d", 57_680),
            )
        ],
    )
    assert receipt["source"]["exact_source_commit_claim"] is False
    receipt["source"]["repository_base_commit_sha"] = "0" * 40
    receipt["receipt_hash"] = runner._receipt_hash(receipt)

    assert (
        runner.validate_compile_receipt(
            receipt,
            repo_root=ROOT,
            require_current_sources=True,
        )
        == receipt
    )


def test_runner_compile_receipt_rejects_duplicate_target() -> None:
    runner = _load_runner()
    target = {
        "architecture": "gfx1030",
        "target_compile": True,
        "binary_sha256": "sha256:" + "e" * 64,
        "binary_byte_length": 56_912,
        "host_fixture_parser_execution": True,
        "host_fixture_validation": _host_fixture_validation(),
    }

    with pytest.raises(ValueError, match="compile_targets_invalid"):
        runner.build_compile_receipt(
            repo_root=ROOT,
            compiler_path="/opt/rocm/bin/hipcc",
            compiler_version_output="HIP version: synthetic-test\n",
            targets=[target, dict(target)],
        )


def test_host_fixture_compile_helper_rejects_duplicate_target() -> None:
    runner = _load_runner()
    fixture = build_hip_current_tangent_operator_reference().fixture

    with pytest.raises(ValueError, match="host_parser_targets_invalid"):
        runner.compile_and_validate_host_fixture_for_targets(
            fixture,
            repo_root=ROOT,
            architectures=("gfx1030", "gfx1030"),
        )


def test_hardware_fixture_helper_rejects_invalid_architecture() -> None:
    runner = _load_runner()
    fixture = build_hip_current_tangent_operator_reference().fixture

    with pytest.raises(ValueError, match="current_tangent_arch_invalid"):
        runner.compile_and_run_hardware_fixture(
            fixture,
            repo_root=ROOT,
            architecture="gfx1030;unexpected",
        )


def test_runner_schema_and_kernel_source_contract_are_present() -> None:
    runner = _load_runner()
    schema = json.loads((ROOT / runner.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    compile_schema = json.loads(
        (ROOT / runner.COMPILE_SCHEMA_PATH).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(compile_schema)
    source = (ROOT / runner.SOURCE_PATH).read_text(encoding="utf-8")

    for token in (
        "current_tangent_action_kernel",
        "geometry_local_action",
        "reference_row_pointer",
        "frame_incidence_pointer",
        "geometry_incidence_pointer",
        "hipMemcpyDeviceToHost",
        "--validate-fixture-only",
        "hip_runtime_api_call_count",
    ):
        assert token in source
    assert "-ffp-contract=off" in (ROOT / runner.__file__).read_text(encoding="utf-8")


def test_runner_check_fails_closed_when_receipt_is_missing(
    tmp_path: Path,
) -> None:
    runner = _load_runner()
    missing = tmp_path / "missing-receipt.json"

    passed, reason = runner.check_committed_receipt(
        repo_root=ROOT,
        out_path=missing,
        compile_only=True,
    )

    assert passed is False
    assert reason == "receipt_missing"
