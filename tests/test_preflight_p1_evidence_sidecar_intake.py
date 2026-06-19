from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("scripts/preflight_p1_evidence_sidecar_intake.py")
SCRIPT_PATH = Path(__file__).resolve().parent.parent / SCRIPT
SPEC = importlib.util.spec_from_file_location("preflight_p1_evidence_sidecar_intake", SCRIPT_PATH)
assert SPEC is not None
preflight = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(preflight)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _external_updates(path: Path, *, attached: bool) -> Path:
    updates = {}
    for queue_id in [
        "hardest_external_10case",
        "tpu_hffb",
        "peer_spd_hinge",
        "korean_public_structures",
    ]:
        if attached:
            updates[queue_id] = {
                "receipt_status": "attached",
                "receipt_url": f"https://bench.example/receipts/{queue_id}",
                "closure_evidence_status": "attached",
                "closure_evidence_path": f"https://bench.example/receipts/{queue_id}",
                "submitted_at_utc": "2026-05-05T01:02:03Z",
                "last_checked_at_utc": "2026-05-05T02:03:04Z",
            }
        else:
            updates[queue_id] = {
                "receipt_status": "pending_external_submission_receipt",
                "closure_evidence_status": "pending",
                "closure_evidence_path": "",
                "last_checked_at_utc": "2026-05-05T02:03:04Z",
            }
    return _write_json(
        path,
        {
            "schema_version": "external-benchmark-submission-updates.v1",
            "updates": updates,
        },
    )


def _residual_updates(path: Path, *, repo_root: Path, closed: bool, missing_paths: bool = False) -> Path:
    updates = {}
    for work_item_id in ["RH-001", "RH-002", "RH-003"]:
        evidence_path = repo_root / "evidence" / f"{work_item_id}.closure.json"
        if closed and not missing_paths:
            _write_json(evidence_path, {"work_item_id": work_item_id, "contract_pass": True})
        updates[work_item_id] = {
            "status": "closed" if closed else "open",
            "queue_status": "closure_evidence_attached" if closed else "pending_review",
            "closure_evidence_status": "attached" if closed else "pending",
            "closure_evidence_path": str(evidence_path.relative_to(repo_root)) if closed else "",
            "last_checked_at_utc": "2026-05-05T04:05:06Z",
            "closed_at_utc": "2026-05-05T04:06:07Z" if closed else "",
        }
    return _write_json(
        path,
        {
            "schema_version": "residual-holdout-closure-updates.v1",
            "updates": updates,
        },
    )


def _signed_residual_updates(path: Path, *, repo_root: Path) -> Path:
    updates = {}
    for work_item_id in ["RH-001", "RH-002", "RH-003"]:
        evidence_path = repo_root / "evidence" / f"{work_item_id}.signed_closure.json"
        _write_json(evidence_path, {"work_item_id": work_item_id, "signature_status": "verified"})
        updates[work_item_id] = {
            "status": "closed",
            "queue_status": "closure_evidence_attached",
            "closure_evidence_status": "signed_attached",
            "closure_evidence_path": str(evidence_path.relative_to(repo_root)),
            "last_checked_at_utc": "2026-06-05T13:35:55Z",
            "closed_at_utc": "2026-06-05T13:35:56Z",
        }
    return _write_json(
        path,
        {
            "schema_version": "residual-holdout-closure-updates.v1",
            "updates": updates,
        },
    )


def test_preflight_reports_pending_current_sidecars(tmp_path: Path) -> None:
    payload = preflight.build_preflight(
        external_benchmark_submission_updates=_external_updates(tmp_path / "eb.json", attached=False),
        residual_holdout_closure_updates=_residual_updates(tmp_path / "rh.json", repo_root=tmp_path, closed=False),
        repo_root=tmp_path,
    )

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_P1_EVIDENCE_SIDECAR_INTAKE_PENDING"
    assert payload["summary"]["external_receipt_attached_count"] == 0
    assert payload["summary"]["external_receipt_pending_count"] == 4
    assert payload["summary"]["residual_closed_count"] == 0
    assert payload["summary"]["residual_closure_pending_count"] == 3
    assert payload["external_benchmark_submission"][0]["work_item_id"] == "EB-001"
    assert "external_receipt_or_closure_pending:hardest_external_10case" in payload["blockers"]
    assert "residual_closure_pending:RH-001" in payload["blockers"]


def test_preflight_structure_only_passes_when_expected_rows_exist(tmp_path: Path) -> None:
    payload = preflight.build_preflight(
        external_benchmark_submission_updates=_external_updates(tmp_path / "eb.json", attached=False),
        residual_holdout_closure_updates=_residual_updates(tmp_path / "rh.json", repo_root=tmp_path, closed=False),
        repo_root=tmp_path,
        structure_only=True,
    )

    assert payload["contract_mode"] == "structure_only"
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS_STRUCTURE_ONLY_PENDING_EVIDENCE"
    assert payload["summary"]["structure_only_contract_pass"] is True
    assert payload["summary"]["evidence_contract_pass"] is False
    assert payload["summary"]["external_receipt_attached_count"] == 0
    assert payload["summary"]["residual_closed_count"] == 0
    assert payload["blockers"] == []
    assert payload["structure_blockers"] == []
    assert "external_receipt_or_closure_pending:hardest_external_10case" in payload["pending_evidence_blockers"]
    assert "residual_closure_pending:RH-001" in payload["pending_evidence_blockers"]


def test_preflight_passes_only_with_real_receipts_and_closure_files(tmp_path: Path) -> None:
    payload = preflight.build_preflight(
        external_benchmark_submission_updates=_external_updates(tmp_path / "eb.json", attached=True),
        residual_holdout_closure_updates=_residual_updates(tmp_path / "rh.json", repo_root=tmp_path, closed=True),
        repo_root=tmp_path,
    )

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["external_receipt_attached_count"] == 4
    assert payload["summary"]["external_closure_evidence_attached_count"] == 4
    assert payload["summary"]["residual_closed_count"] == 3
    assert payload["summary"]["residual_closure_evidence_attached_count"] == 3
    assert payload["blockers"] == []


def test_preflight_accepts_signed_attached_residual_closure_files(tmp_path: Path) -> None:
    payload = preflight.build_preflight(
        external_benchmark_submission_updates=_external_updates(tmp_path / "eb.json", attached=False),
        residual_holdout_closure_updates=_signed_residual_updates(tmp_path / "rh.json", repo_root=tmp_path),
        repo_root=tmp_path,
    )

    assert payload["contract_pass"] is False
    assert payload["summary"]["external_receipt_attached_count"] == 0
    assert payload["summary"]["residual_closed_count"] == 3
    assert payload["summary"]["residual_closure_evidence_attached_count"] == 3
    assert "residual_closure_pending:RH-001" not in payload["blockers"]
    assert "external_receipt_or_closure_pending:hardest_external_10case" in payload["blockers"]


def test_preflight_rejects_closed_residual_rows_without_evidence_files(tmp_path: Path) -> None:
    payload = preflight.build_preflight(
        external_benchmark_submission_updates=_external_updates(tmp_path / "eb.json", attached=True),
        residual_holdout_closure_updates=_residual_updates(
            tmp_path / "rh.json",
            repo_root=tmp_path,
            closed=True,
            missing_paths=True,
        ),
        repo_root=tmp_path,
    )

    assert payload["contract_pass"] is False
    assert payload["summary"]["external_receipt_attached_count"] == 4
    assert payload["summary"]["residual_closed_count"] == 0
    assert payload["residual_holdout"][0]["missing_requirements"] == ["closure_evidence_path_exists"]
    assert "residual_closure_pending:RH-001" in payload["blockers"]


def test_preflight_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    out = tmp_path / "preflight.json"
    out_md = tmp_path / "preflight.md"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--external-benchmark-submission-updates",
            str(_external_updates(tmp_path / "eb.json", attached=False)),
            "--residual-holdout-closure-updates",
            str(_residual_updates(tmp_path / "rh.json", repo_root=tmp_path, closed=False)),
            "--repo-root",
            str(tmp_path),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
            "--json",
            "--fail-open",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["contract_pass"] is False
    assert "P1 Evidence Sidecar Intake Preflight" in markdown
    assert "external_receipt_attached_count" in markdown
    assert "residual_closure_pending:RH-001" in markdown


def test_preflight_cli_structure_only_fail_open_allows_pending_evidence(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--external-benchmark-submission-updates",
            str(_external_updates(tmp_path / "eb.json", attached=False)),
            "--residual-holdout-closure-updates",
            str(_residual_updates(tmp_path / "rh.json", repo_root=tmp_path, closed=False)),
            "--repo-root",
            str(tmp_path),
            "--json",
            "--fail-open",
            "--structure-only",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS_STRUCTURE_ONLY_PENDING_EVIDENCE"
    assert payload["pending_evidence_blockers"]
