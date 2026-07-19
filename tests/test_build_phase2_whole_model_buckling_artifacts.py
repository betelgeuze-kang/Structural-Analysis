"""Tests for the source-bound whole-model linear-buckling receipt."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_phase2_whole_model_buckling_artifacts.py"
SPEC = importlib.util.spec_from_file_location(
    "build_phase2_whole_model_buckling_artifacts",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_builder_records_four_public_buckling_gates_without_breadth_promotion() -> None:
    payloads = module.build_phase2_whole_model_buckling_artifacts(repo_root=ROOT)
    result = payloads["result"]
    summary = payloads["summary"]

    assert result["status"] == "partial"
    assert result["contract_pass"] is True
    assert result["summary"]["case_count"] == 4
    assert result["summary"]["passing_case_count"] == 4
    assert all(row["contract_pass"] for row in result["verification"].values())
    assert result["claims"]["whole_model_frame_linear_buckling_evidence"] is True
    assert (
        result["claims"]["reference_static_initial_stress_assembly_evidence"]
        is True
    )
    assert result["claims"]["repeated_cluster_fail_closed_evidence"] is True
    assert result["claims"]["reference_axial_sign_fail_closed_evidence"] is True
    assert result["claims"]["general_frame_shell_linear_buckling"] is False
    assert result["claims"]["mixed_tension_compression_reference"] is False
    assert (
        result["claims"]["nonlinear_buckling_or_imperfection_sensitivity"]
        is False
    )
    assert result["claims"]["sparse_buckling_backend"] is False
    assert result["claims"]["large_mode_binary_vector_artifacts"] is False
    assert result["claims"]["rocm_hip_buckling_parity"] is False
    assert (
        result["claims"]["independent_code_to_code_or_verification_level_2"]
        is False
    )
    assert result["claims"]["release_readiness"] is False
    assert summary["passing_case_count"] == 4
    assert summary["result_artifact_hash"] == result["artifact_hash"]
    assert "does not prove general frame/shell stability" in result["claim_boundary"]


def test_result_validates_against_strict_schema_and_current_sources() -> None:
    result = module.build_phase2_whole_model_buckling_artifacts(
        repo_root=ROOT
    )["result"]
    schema = json.loads((ROOT / module.SCHEMA_PATH).read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)
    module._validate_result(result, repo_root=ROOT, require_current_sources=True)


def test_validation_rejects_recomputed_hash_numeric_tampering() -> None:
    result = module.build_phase2_whole_model_buckling_artifacts(
        repo_root=ROOT
    )["result"]
    tampered = deepcopy(result)
    tampered["verification"]["euler_two_plane"]["actual_load_factors"][0] *= 1.2
    tampered["artifact_hash"] = module._artifact_hash(tampered)

    with pytest.raises(
        module.WholeModelBucklingArtifactError,
        match="euler_error_invalid",
    ):
        module._validate_result(
            tampered,
            repo_root=ROOT,
            require_current_sources=False,
        )


def test_builder_check_reports_missing_artifacts(tmp_path: Path) -> None:
    ok, message = module.check_phase2_whole_model_buckling_artifacts(
        repo_root=ROOT,
        result_out=tmp_path / "missing-result.json",
        summary_out=tmp_path / "missing-summary.json",
    )

    assert ok is False
    assert message.startswith("phase2_whole_model_buckling_missing:")


def test_cli_write_and_check_round_trip(tmp_path: Path) -> None:
    result = tmp_path / "result.json"
    summary = tmp_path / "summary.json"
    command = [
        sys.executable,
        str(SCRIPT),
        "--result-out",
        str(result),
        "--summary-out",
        str(summary),
    ]
    write = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    check = subprocess.run(
        [*command, "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert write.returncode == 0, write.stderr + write.stdout
    assert "cases=4/4" in write.stdout
    assert "level2=False" in write.stdout
    assert check.returncode == 0, check.stderr + check.stdout
    assert "phase2_whole_model_buckling_consistent" in check.stdout


def test_committed_whole_model_buckling_artifacts_match_builder() -> None:
    ok, message = module.check_phase2_whole_model_buckling_artifacts(repo_root=ROOT)

    assert ok is True
    assert message == "phase2_whole_model_buckling_consistent"
