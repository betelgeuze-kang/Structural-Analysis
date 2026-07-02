from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_fresh_full_validation_lane_status.py"
SPEC = importlib.util.spec_from_file_location("build_fresh_full_validation_lane_status", SCRIPT_PATH)
assert SPEC is not None
lane_status = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(lane_status)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sha256_ref(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _lane(materialized_path: Path) -> dict[str, object]:
    return {
        "lane_id": "gpu_hip_solver",
        "runner": "gpu_capable_rocm_hip_validation",
        "materialized_paths": [materialized_path],
        "doc_terms": ["GPU-capable validation task"],
    }


def _valid_receipt_payload(
    *,
    lane_id: str = "gpu_hip_solver",
    runner: str = "gpu_capable_rocm_hip_validation",
    reused_evidence: bool = False,
    contract_pass: bool = True,
    artifact_path: Path | None = None,
    artifact_sha256: str | None = None,
) -> dict[str, object]:
    artifact_ref = str(
        artifact_path
        or "implementation/phase1/release_evidence/gpu/solver_hip_e2e_contract_report.json"
    )
    digest_ref = artifact_sha256 or ("sha256:" + "a" * 64)
    return {
        "schema_version": "fresh-validation-receipt.v1",
        "lane_id": lane_id,
        "runner": runner,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": "abcdef1234567890",
        "engine_version": "engine@1.0.0",
        "input_checksums": {artifact_ref: digest_ref},
        "reused_evidence": reused_evidence,
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "FAIL",
        "validation_command": "python3 -m implementation.phase1.run_gpu_solver_hip_validation",
        "receipt_artifacts": [
            {
                "path": artifact_ref,
                "sha256": digest_ref,
                "kind": "contract_report",
            }
        ],
        "summary": {"case_count": 4, "passed_case_count": 4, "duration_seconds": 1.0},
        "claim_boundary": "Receipt attests fresh evidence; Level 3 promotion remains with the human owner.",
    }


def _legacy_fresh_receipt(
    *,
    reused_evidence: bool = False,
    contract_pass: bool = True,
) -> dict[str, object]:
    return {
        "contract_pass": contract_pass,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": "abcdef1234567890",
        "engine_version": "engine@1.0.0",
        "input_checksums": {"input": "sha256:abc"},
        "reused_evidence": reused_evidence,
    }


def _failed_result_payload() -> dict[str, object]:
    return {
        "schema_version": "fresh-validation-receipt-builder.v1",
        "contract_pass": False,
        "reason_code": "ERR_FRESH_VALIDATION_COMMAND_FAILED",
        "blockers": ["validation_command_exit_1"],
        "receipt_path": "",
        "command_result": {
            "returncode": 1,
            "stdout_tail": "Wrote solver hip e2e contract report\n",
            "stderr_tail": (
                "{\"event\":\"solver_hip_e2e.completed\","
                "\"contract_pass\":false,"
                "\"reason_code\":\"ERR_ROCM_RUNTIME_UNAVAILABLE\"}\n"
            ),
        },
    }


def test_fresh_full_validation_lane_status_blocks_missing_fresh_receipt(tmp_path: Path) -> None:
    docs = (_write_text(tmp_path / "runbook.md", "GPU-capable validation task\n"),)
    materialized = _write_json(tmp_path / "gpu" / "solver_hip_e2e_contract_report.json", {"contract_pass": True})

    payload = lane_status.build_status(
        docs=docs,
        receipt_root=tmp_path / "receipts",
        lanes=(_lane(materialized),),
    )

    assert payload["contract_pass"] is False
    assert payload["lane_contract_pass"] is True
    assert payload["fresh_full_validation_ready"] is False
    assert payload["summary"]["lane_contract_pass_count"] == 1
    assert payload["summary"]["fresh_validation_receipt_present_count"] == 0
    assert "gpu_hip_solver::fresh_validation_receipt_missing" in payload["blockers"]
    grouping = payload["blocker_grouping_metadata"]
    assert grouping["schema_version"] == "fresh-full-validation-blocker-groups.v1"
    assert grouping["blocker_count"] == len(payload["blockers"])
    assert grouping["unassigned_blockers"] == []
    assert "gpu_hip_solver::fresh_validation_receipt_missing" in grouping["groups"][
        "fresh_receipt_presence"
    ]["blockers"]
    lane_boundary = payload["lane_boundary_metadata"]
    assert lane_boundary["schema_version"] == "fresh-full-validation-lane-boundaries.v1"
    assert lane_boundary["lanes"]["gpu_hip_solver"]["scope"] == (
        "performance_track_after_cpu_reference_parity"
    )
    assert "must not be used to replace CPU" in lane_boundary["gpu_hip_policy"]


def test_fresh_full_validation_lane_status_passes_with_valid_fresh_receipt(tmp_path: Path) -> None:
    docs = (_write_text(tmp_path / "runbook.md", "GPU-capable validation task\n"),)
    materialized = _write_json(tmp_path / "gpu" / "solver_hip_e2e_contract_report.json", {"contract_pass": True})
    receipt_root = tmp_path / "receipts"
    _write_json(
        receipt_root / "gpu_hip_solver.fresh_validation_receipt.json",
        _valid_receipt_payload(
            artifact_path=materialized,
            artifact_sha256=_sha256_ref(materialized),
        ),
    )

    payload = lane_status.build_status(
        docs=docs,
        receipt_root=receipt_root,
        lanes=(_lane(materialized),),
    )

    assert payload["contract_pass"] is True
    assert payload["fresh_full_validation_ready"] is True
    assert payload["summary"]["fresh_validation_receipt_pass_count"] == 1
    assert payload["summary"]["fresh_validation_result_present_count"] == 0
    assert payload["blockers"] == []


def test_fresh_full_validation_lane_status_blocks_failed_latest_result(
    tmp_path: Path,
) -> None:
    docs = (_write_text(tmp_path / "runbook.md", "GPU-capable validation task\n"),)
    materialized = _write_json(
        tmp_path / "gpu" / "solver_hip_e2e_contract_report.json",
        {"contract_pass": False, "reason_code": "ERR_ROCM_RUNTIME_UNAVAILABLE"},
    )
    receipt_root = tmp_path / "receipts"
    _write_json(
        receipt_root / "gpu_hip_solver.fresh_validation_receipt.json",
        _valid_receipt_payload(
            artifact_path=materialized,
            artifact_sha256=_sha256_ref(materialized),
        ),
    )
    _write_json(
        receipt_root / "gpu_hip_solver.fresh_validation_receipt.result.json",
        _failed_result_payload(),
    )

    payload = lane_status.build_status(
        docs=docs,
        receipt_root=receipt_root,
        lanes=(_lane(materialized),),
    )

    assert payload["contract_pass"] is False
    assert payload["fresh_full_validation_ready"] is False
    assert payload["summary"]["fresh_validation_result_present_count"] == 1
    assert payload["summary"]["fresh_validation_result_failed_count"] == 1
    assert "gpu_hip_solver::fresh_validation_result_failed" in payload["blockers"]
    assert (
        "gpu_hip_solver::fresh_validation_result_failed:validation_command_exit_1"
        in payload["blockers"]
    )
    grouping = payload["blocker_grouping_metadata"]
    assert "gpu_hip_solver::fresh_validation_result_failed" in grouping["groups"][
        "fresh_receipt_execution_result"
    ]["blockers"]
    row = payload["rows"][0]
    assert row["fresh_validation_result_present"] is True
    assert row["fresh_validation_result_contract_pass"] is False
    assert row["fresh_validation_result_command_returncode"] == 1
    assert row["fresh_validation_result_latest_tail_reason_code"] == (
        "ERR_ROCM_RUNTIME_UNAVAILABLE"
    )
    assert row["fresh_validation_result_failure_class"] == (
        "rocm_runtime_unavailable"
    )
    remediation = row["fresh_validation_result_remediation"]
    assert remediation["schema_version"] == (
        "fresh-validation-result-remediation.v1"
    )
    assert remediation["status"] == "blocked_runtime_environment"
    assert remediation["failure_class"] == "rocm_runtime_unavailable"
    assert remediation["reason_code"] == "ERR_ROCM_RUNTIME_UNAVAILABLE"
    assert remediation["command_returncode"] == 1
    assert "/dev/kfd is present" in remediation["preflight_checks"][0]
    assert any(
        "build_fresh_validation_receipt.py" in command
        for command in remediation["validation_commands"]
    )
    assert payload["summary"][
        "fresh_validation_result_runtime_unavailable_count"
    ] == 1
    assert payload["failed_result_remediation_count"] == 1
    assert payload["failed_result_remediation_rows"][0]["lane_id"] == (
        "gpu_hip_solver"
    )


def test_fresh_full_validation_lane_status_suppresses_stale_receipt_mismatch_when_failed_result_is_newer(
    tmp_path: Path,
) -> None:
    docs = (_write_text(tmp_path / "runbook.md", "GPU-capable validation task\n"),)
    materialized = _write_json(
        tmp_path / "gpu" / "solver_hip_e2e_contract_report.json",
        {"contract_pass": False, "reason_code": "ERR_ROCM_RUNTIME_UNAVAILABLE"},
    )
    receipt_root = tmp_path / "receipts"
    receipt_path = _write_json(
        receipt_root / "gpu_hip_solver.fresh_validation_receipt.json",
        _valid_receipt_payload(
            artifact_path=materialized,
            artifact_sha256="sha256:" + "b" * 64,
        ),
    )
    result_path = _write_json(
        receipt_root / "gpu_hip_solver.fresh_validation_receipt.result.json",
        _failed_result_payload(),
    )
    os.utime(receipt_path, (1_000, 1_000))
    os.utime(result_path, (1_001, 1_001))

    payload = lane_status.build_status(
        docs=docs,
        receipt_root=receipt_root,
        lanes=(_lane(materialized),),
    )

    assert payload["contract_pass"] is False
    assert payload["summary"]["fresh_validation_receipt_superseded_by_failed_result_count"] == 1
    assert "gpu_hip_solver::fresh_validation_result_failed" in payload["blockers"]
    assert not any(
        blocker.startswith("gpu_hip_solver::fresh_validation_receipt_artifact_integrity_failed")
        for blocker in payload["blockers"]
    )
    row = payload["rows"][0]
    assert row["fresh_validation_receipt_superseded_by_failed_result"] is True
    assert row["fresh_validation_receipt_artifact_integrity_status"] == (
        "superseded_by_failed_result"
    )
    assert row["fresh_validation_receipt_artifact_integrity_blockers"] == []
    assert any(
        "sha256_mismatch" in blocker
        for blocker in row["fresh_validation_receipt_artifact_integrity_raw_blockers"]
    )
    grouping = payload["blocker_grouping_metadata"]
    assert grouping["groups"]["fresh_receipt_artifact_integrity"]["blocker_count"] == 0
    assert "gpu_hip_solver::fresh_validation_result_failed" in grouping["groups"][
        "fresh_receipt_execution_result"
    ]["blockers"]


def test_fresh_full_validation_lane_status_resolves_checksum_verified_path_alias(
    monkeypatch,
    tmp_path: Path,
) -> None:
    docs = (_write_text(tmp_path / "runbook.md", "GPU-capable validation task\n"),)
    materialized = _write_json(tmp_path / "gpu" / "solver_hip_e2e_contract_report.json", {"contract_pass": True})
    legacy_ref = "implementation/phase1/legacy_gpu_solver_hip_report.json"
    monkeypatch.setattr(
        lane_status,
        "FRESH_VALIDATION_PATH_ALIASES",
        {legacy_ref: (materialized,)},
    )
    receipt_root = tmp_path / "receipts"
    _write_json(
        receipt_root / "gpu_hip_solver.fresh_validation_receipt.json",
        _valid_receipt_payload(
            artifact_path=Path(legacy_ref),
            artifact_sha256=_sha256_ref(materialized),
        ),
    )

    payload = lane_status.build_status(
        docs=docs,
        receipt_root=receipt_root,
        lanes=(_lane(materialized),),
    )

    assert payload["contract_pass"] is True
    assert payload["blockers"] == []
    row = payload["rows"][0]
    assert row["fresh_validation_receipt_path_alias_count"] == 2
    assert payload["summary"]["fresh_validation_receipt_path_alias_count"] == 2
    assert all(alias["sha256_match"] is True for alias in row["fresh_validation_receipt_path_aliases"])


def test_fresh_full_validation_lane_status_blocks_artifact_sha_mismatch(tmp_path: Path) -> None:
    docs = (_write_text(tmp_path / "runbook.md", "GPU-capable validation task\n"),)
    materialized = _write_json(tmp_path / "gpu" / "solver_hip_e2e_contract_report.json", {"contract_pass": True})
    receipt_root = tmp_path / "receipts"
    _write_json(
        receipt_root / "gpu_hip_solver.fresh_validation_receipt.json",
        _valid_receipt_payload(
            artifact_path=materialized,
            artifact_sha256="sha256:" + "b" * 64,
        ),
    )

    payload = lane_status.build_status(
        docs=docs,
        receipt_root=receipt_root,
        lanes=(_lane(materialized),),
    )

    assert payload["contract_pass"] is False
    assert payload["summary"]["fresh_validation_receipt_pass_count"] == 0
    row = payload["rows"][0]
    assert row["fresh_validation_receipt_contract_pass"] is True
    assert row["fresh_validation_receipt_artifact_integrity_pass"] is False
    assert any(
        blocker.startswith(
            "gpu_hip_solver::fresh_validation_receipt_artifact_integrity_failed:"
        )
        and "sha256_mismatch" in blocker
        for blocker in payload["blockers"]
    )


def test_fresh_full_validation_lane_status_keeps_path_alias_sha_mismatch_blocked(
    monkeypatch,
    tmp_path: Path,
) -> None:
    docs = (_write_text(tmp_path / "runbook.md", "GPU-capable validation task\n"),)
    materialized = _write_json(tmp_path / "gpu" / "solver_hip_e2e_contract_report.json", {"contract_pass": True})
    legacy_ref = "implementation/phase1/legacy_gpu_solver_hip_report.json"
    monkeypatch.setattr(
        lane_status,
        "FRESH_VALIDATION_PATH_ALIASES",
        {legacy_ref: (materialized,)},
    )
    receipt_root = tmp_path / "receipts"
    _write_json(
        receipt_root / "gpu_hip_solver.fresh_validation_receipt.json",
        _valid_receipt_payload(
            artifact_path=Path(legacy_ref),
            artifact_sha256="sha256:" + "b" * 64,
        ),
    )

    payload = lane_status.build_status(
        docs=docs,
        receipt_root=receipt_root,
        lanes=(_lane(materialized),),
    )

    assert payload["contract_pass"] is False
    row = payload["rows"][0]
    assert row["fresh_validation_receipt_path_alias_count"] == 2
    assert any(alias["sha256_match"] is False for alias in row["fresh_validation_receipt_path_aliases"])
    assert any("sha256_mismatch" in blocker and legacy_ref in blocker for blocker in payload["blockers"])
    assert not any("path_missing" in blocker and legacy_ref in blocker for blocker in payload["blockers"])


def test_fresh_full_validation_lane_status_blocks_missing_receipt_artifact(tmp_path: Path) -> None:
    docs = (_write_text(tmp_path / "runbook.md", "GPU-capable validation task\n"),)
    materialized = _write_json(tmp_path / "gpu" / "solver_hip_e2e_contract_report.json", {"contract_pass": True})
    missing_artifact = tmp_path / "gpu" / "missing.json"
    receipt_root = tmp_path / "receipts"
    _write_json(
        receipt_root / "gpu_hip_solver.fresh_validation_receipt.json",
        _valid_receipt_payload(
            artifact_path=missing_artifact,
            artifact_sha256="sha256:" + "c" * 64,
        ),
    )

    payload = lane_status.build_status(
        docs=docs,
        receipt_root=receipt_root,
        lanes=(_lane(materialized),),
    )

    assert payload["contract_pass"] is False
    assert any(
        blocker.startswith(
            "gpu_hip_solver::fresh_validation_receipt_artifact_integrity_failed:"
        )
        and "path_missing" in blocker
        for blocker in payload["blockers"]
    )


def test_fresh_full_validation_lane_status_rejects_reused_receipt(tmp_path: Path) -> None:
    docs = (_write_text(tmp_path / "runbook.md", "GPU-capable validation task\n"),)
    materialized = _write_json(tmp_path / "gpu" / "solver_hip_e2e_contract_report.json", {"contract_pass": True})
    receipt_root = tmp_path / "receipts"
    _write_json(
        receipt_root / "gpu_hip_solver.fresh_validation_receipt.json",
        _valid_receipt_payload(reused_evidence=True),
    )

    payload = lane_status.build_status(
        docs=docs,
        receipt_root=receipt_root,
        lanes=(_lane(materialized),),
    )

    assert payload["contract_pass"] is False
    assert payload["summary"]["fresh_validation_receipt_present_count"] == 1
    assert "gpu_hip_solver::fresh_validation_receipt_reuses_evidence" in payload["blockers"]


def test_fresh_full_validation_lane_status_blocks_lane_and_runner_mismatch(tmp_path: Path) -> None:
    docs = (_write_text(tmp_path / "runbook.md", "GPU-capable validation task\n"),)
    materialized = _write_json(tmp_path / "gpu" / "solver_hip_e2e_contract_report.json", {"contract_pass": True})
    receipt_root = tmp_path / "receipts"
    _write_json(
        receipt_root / "gpu_hip_solver.fresh_validation_receipt.json",
        _valid_receipt_payload(lane_id="commercial_benchmark_torch", runner="torch_capable_benchmark_validation"),
    )

    payload = lane_status.build_status(
        docs=docs,
        receipt_root=receipt_root,
        lanes=(_lane(materialized),),
    )

    assert payload["contract_pass"] is False
    assert payload["summary"]["fresh_validation_receipt_pass_count"] == 0
    assert "gpu_hip_solver::fresh_validation_receipt_lane_mismatch" in payload["blockers"]
    assert "gpu_hip_solver::fresh_validation_receipt_runner_mismatch" in payload["blockers"]


def test_fresh_full_validation_lane_status_blocks_invalid_receipt_with_legacy_shape(tmp_path: Path) -> None:
    docs = (_write_text(tmp_path / "runbook.md", "GPU-capable validation task\n"),)
    materialized = _write_json(tmp_path / "gpu" / "solver_hip_e2e_contract_report.json", {"contract_pass": True})
    receipt_root = tmp_path / "receipts"
    _write_json(
        receipt_root / "gpu_hip_solver.fresh_validation_receipt.json",
        _legacy_fresh_receipt(),
    )

    payload = lane_status.build_status(
        docs=docs,
        receipt_root=receipt_root,
        lanes=(_lane(materialized),),
    )

    assert payload["contract_pass"] is False
    assert payload["summary"]["fresh_validation_receipt_present_count"] == 1
    assert any(
        blocker.startswith("gpu_hip_solver::fresh_validation_receipt_invalid")
        for blocker in payload["blockers"]
    )
    invalid_blockers = [
        blocker
        for blocker in payload["blockers"]
        if blocker.startswith("gpu_hip_solver::fresh_validation_receipt_invalid:")
    ]
    assert invalid_blockers, "expected validator-specific blockers to be surfaced"
    joined = " ".join(invalid_blockers)
    assert "missing_field:lane_id" in joined or "missing_field:validation_command" in joined
    assert "receipt_artifacts_missing_or_empty" in joined


def test_fresh_full_validation_lane_status_blocks_invalid_receipt_with_placeholder(tmp_path: Path) -> None:
    docs = (_write_text(tmp_path / "runbook.md", "GPU-capable validation task\n"),)
    materialized = _write_json(tmp_path / "gpu" / "solver_hip_e2e_contract_report.json", {"contract_pass": True})
    receipt_root = tmp_path / "receipts"
    payload_receipt = _valid_receipt_payload()
    payload_receipt["lane_id"] = "OWNER_INPUT_REQUIRED_LANE_ID"
    _write_json(receipt_root / "gpu_hip_solver.fresh_validation_receipt.json", payload_receipt)

    payload = lane_status.build_status(
        docs=docs,
        receipt_root=receipt_root,
        lanes=(_lane(materialized),),
    )

    assert payload["contract_pass"] is False
    assert any(
        blocker.endswith("placeholder_marker_present")
        for blocker in payload["blockers"]
        if blocker.startswith("gpu_hip_solver::fresh_validation_receipt_invalid:")
    )
