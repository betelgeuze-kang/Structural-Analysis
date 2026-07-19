"""Tests for the source-bound modal/buckling matrix-kernel receipt."""

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
SCRIPT = ROOT / "scripts/build_phase2_modal_buckling_kernel_artifacts.py"
SPEC = importlib.util.spec_from_file_location(
    "build_phase2_modal_buckling_kernel_artifacts",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_builder_records_four_matrix_gates_without_breadth_promotion() -> None:
    payloads = module.build_phase2_modal_buckling_kernel_artifacts(repo_root=ROOT)
    result = payloads["result"]
    summary = payloads["summary"]

    assert result["status"] == "partial"
    assert result["contract_pass"] is True
    assert result["summary"]["case_count"] == 4
    assert result["summary"]["passing_case_count"] == 4
    assert all(row["contract_pass"] for row in result["verification"].values())
    assert result["claims"]["modal_matrix_kernel_evidence"] is True
    assert result["claims"]["buckling_matrix_kernel_evidence"] is True
    assert result["claims"]["repeated_eigenspace_determinism_evidence"] is True
    assert result["claims"]["euler_column_analytic_bridge_evidence"] is True
    assert result["claims"]["whole_model_modal_workflow"] is False
    assert result["claims"]["whole_model_buckling_workflow"] is False
    assert result["claims"]["verification_level_2"] is False
    assert result["claims"]["release_readiness"] is False
    assert summary["passing_case_count"] == 4
    assert summary["result_artifact_hash"] == result["artifact_hash"]
    assert "does not prove whole-model" in result["claim_boundary"]


def test_result_validates_against_schema_and_recomputed_mode_hashes() -> None:
    result = module.build_phase2_modal_buckling_kernel_artifacts(
        repo_root=ROOT
    )["result"]
    schema = json.loads((ROOT / module.SCHEMA_PATH).read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)
    module._validate_result(result, repo_root=ROOT, require_current_sources=True)


def test_validation_rejects_stored_mode_hash_tampering() -> None:
    result = module.build_phase2_modal_buckling_kernel_artifacts(
        repo_root=ROOT
    )["result"]
    tampered = deepcopy(result)
    tampered["verification"]["modal_two_dof"]["mass_normalized_modes"][0][0] += 0.1
    tampered["artifact_hash"] = module._artifact_hash(tampered)

    with pytest.raises(module.ModalBucklingArtifactError, match="raw_result_hash_invalid"):
        module._validate_result(
            tampered,
            repo_root=ROOT,
            require_current_sources=False,
        )


def test_builder_check_reports_missing_artifacts(tmp_path: Path) -> None:
    ok, message = module.check_phase2_modal_buckling_kernel_artifacts(
        repo_root=ROOT,
        result_out=tmp_path / "missing-result.json",
        summary_out=tmp_path / "missing-summary.json",
    )

    assert ok is False
    assert message.startswith("phase2_modal_buckling_kernel_missing:")


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
    assert check.returncode == 0, check.stderr + check.stdout
    assert "phase2_modal_buckling_kernel_consistent" in check.stdout


def test_committed_modal_buckling_artifacts_match_builder() -> None:
    ok, message = module.check_phase2_modal_buckling_kernel_artifacts(
        repo_root=ROOT
    )

    assert ok is True
    assert message == "phase2_modal_buckling_kernel_consistent"
