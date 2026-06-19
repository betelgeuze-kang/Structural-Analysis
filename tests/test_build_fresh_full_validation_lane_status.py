from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
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


def _lane(materialized_path: Path) -> dict[str, object]:
    return {
        "lane_id": "gpu_hip_solver",
        "runner": "gpu_capable_rocm_hip_validation",
        "materialized_paths": [materialized_path],
        "doc_terms": ["GPU-capable validation task"],
    }


def _fresh_receipt(*, reused_evidence: bool = False, contract_pass: bool = True) -> dict[str, object]:
    return {
        "contract_pass": contract_pass,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": "abcdef1234567890",
        "engine_version": "engine@1.0.0",
        "input_checksums": {"input": "sha256:abc"},
        "reused_evidence": reused_evidence,
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


def test_fresh_full_validation_lane_status_passes_with_fresh_receipt(tmp_path: Path) -> None:
    docs = (_write_text(tmp_path / "runbook.md", "GPU-capable validation task\n"),)
    materialized = _write_json(tmp_path / "gpu" / "solver_hip_e2e_contract_report.json", {"contract_pass": True})
    receipt_root = tmp_path / "receipts"
    _write_json(receipt_root / "gpu_hip_solver.fresh_validation_receipt.json", _fresh_receipt())

    payload = lane_status.build_status(
        docs=docs,
        receipt_root=receipt_root,
        lanes=(_lane(materialized),),
    )

    assert payload["contract_pass"] is True
    assert payload["fresh_full_validation_ready"] is True
    assert payload["summary"]["fresh_validation_receipt_pass_count"] == 1
    assert payload["blockers"] == []


def test_fresh_full_validation_lane_status_rejects_reused_receipt(tmp_path: Path) -> None:
    docs = (_write_text(tmp_path / "runbook.md", "GPU-capable validation task\n"),)
    materialized = _write_json(tmp_path / "gpu" / "solver_hip_e2e_contract_report.json", {"contract_pass": True})
    receipt_root = tmp_path / "receipts"
    _write_json(
        receipt_root / "gpu_hip_solver.fresh_validation_receipt.json",
        _fresh_receipt(reused_evidence=True),
    )

    payload = lane_status.build_status(
        docs=docs,
        receipt_root=receipt_root,
        lanes=(_lane(materialized),),
    )

    assert payload["contract_pass"] is False
    assert payload["summary"]["fresh_validation_receipt_present_count"] == 1
    assert "gpu_hip_solver::fresh_validation_receipt_reuses_evidence" in payload["blockers"]
