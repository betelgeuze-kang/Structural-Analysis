from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("scripts/validate_p1_evidence_intake_manifest.py")
SCRIPT_PATH = Path(__file__).resolve().parent.parent / SCRIPT
SPEC = importlib.util.spec_from_file_location("validate_p1_evidence_intake_manifest", SCRIPT_PATH)
assert SPEC is not None
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)


QUEUE_IDS = ["hardest_external_10case", "tpu_hffb", "peer_spd_hinge", "korean_public_structures"]
RH_IDS = ["RH-001", "RH-002", "RH-003"]


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _intake_manifest(tmp_path: Path, *, complete: bool = True, missing_local_file: bool = False) -> Path:
    external_rows = {}
    residual_rows = {}
    for queue_id in (QUEUE_IDS if complete else QUEUE_IDS[:1]):
        external_rows[queue_id] = {
            "queue_id": queue_id,
            "receipt_url": f"https://bench.example/receipts/{queue_id}",
            "closure_evidence_path": f"https://bench.example/receipts/{queue_id}",
            "submitted_at_utc": "2026-05-05T01:02:03Z",
            "last_checked_at_utc": "2026-05-05T02:03:04Z",
        }
    for work_item_id in (RH_IDS if complete else RH_IDS[:1]):
        evidence = tmp_path / "evidence" / f"{work_item_id}.closure.json"
        if not missing_local_file:
            _write_json(evidence, {"work_item_id": work_item_id, "contract_pass": True})
        residual_rows[work_item_id] = {
            "work_item_id": work_item_id,
            "closure_evidence_path": str(evidence.relative_to(tmp_path)),
            "last_checked_at_utc": "2026-05-05T04:05:06Z",
            "closed_at_utc": "2026-05-05T04:06:07Z",
        }
    return _write_json(
        tmp_path / "p1-evidence-intake.json",
        {
            "schema_version": "p1-evidence-sidecar-intake.v1",
            "generated_at": "2026-05-05T06:07:08Z",
            "external_benchmark_receipts": external_rows,
            "residual_holdout_closures": residual_rows,
        },
    )


def test_validate_intake_manifest_passes_complete_real_references(tmp_path: Path) -> None:
    payload = validator.validate_intake_manifest(
        intake_manifest=_intake_manifest(tmp_path),
        repo_root=tmp_path,
    )

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["external_valid_count"] == 4
    assert payload["summary"]["residual_valid_count"] == 3
    assert payload["summary"]["url_evidence_count"] == 8
    assert payload["summary"]["local_evidence_count"] == 3
    local_rows = [row for row in payload["evidence_inventory"] if row["kind"] == "local_path"]
    assert all(row["sha256"] for row in local_rows)


def test_validate_intake_manifest_reports_missing_rows_paths_and_timestamps(tmp_path: Path) -> None:
    intake = json.loads(_intake_manifest(tmp_path, complete=False, missing_local_file=True).read_text(encoding="utf-8"))
    intake["external_benchmark_receipts"]["hardest_external_10case"]["submitted_at_utc"] = "not-a-date"
    intake_path = _write_json(tmp_path / "broken-intake.json", intake)

    payload = validator.validate_intake_manifest(intake_manifest=intake_path, repo_root=tmp_path)

    assert payload["contract_pass"] is False
    assert "external_submitted_at_utc_invalid:hardest_external_10case" in payload["blockers"]
    assert "external_intake_missing:tpu_hffb" in payload["blockers"]
    assert "residual_closure_reference_missing:RH-001" in payload["blockers"]
    assert "residual_intake_missing:RH-002" in payload["blockers"]


def test_validate_intake_manifest_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    out = tmp_path / "validation.json"
    out_md = tmp_path / "validation.md"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--intake-manifest",
            str(_intake_manifest(tmp_path, complete=False)),
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
    assert "P1 Evidence Intake Validation" in markdown
    assert "external_intake_missing:tpu_hffb" in markdown
