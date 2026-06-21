from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("scripts/build_p1_evidence_sidecar_updates.py")
SCRIPT_PATH = Path(__file__).resolve().parent.parent / SCRIPT
SPEC = importlib.util.spec_from_file_location("build_p1_evidence_sidecar_updates", SCRIPT_PATH)
assert SPEC is not None
builder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(builder)

PREFLIGHT_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "preflight_p1_evidence_sidecar_intake.py"
)
PREFLIGHT_SPEC = importlib.util.spec_from_file_location("preflight_p1_evidence_sidecar_intake", PREFLIGHT_SCRIPT_PATH)
assert PREFLIGHT_SPEC is not None
preflight = importlib.util.module_from_spec(PREFLIGHT_SPEC)
assert PREFLIGHT_SPEC.loader is not None
PREFLIGHT_SPEC.loader.exec_module(preflight)


QUEUE_IDS = ["hardest_external_10case", "tpu_hffb", "peer_spd_hinge", "korean_public_structures"]
RH_IDS = ["RH-001", "RH-002", "RH-003"]


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _intake_manifest(tmp_path: Path, *, complete: bool = True, missing_rh_file: bool = False) -> Path:
    external_rows = {}
    residual_rows = {}
    queue_ids = QUEUE_IDS if complete else QUEUE_IDS[:1]
    rh_ids = RH_IDS if complete else RH_IDS[:1]
    for queue_id in queue_ids:
        external_rows[queue_id] = {
            "receipt_url": f"https://bench.example/receipts/{queue_id}",
            "submitted_at_utc": "2026-05-05T01:02:03Z",
            "last_checked_at_utc": "2026-05-05T02:03:04Z",
        }
    for work_item_id in rh_ids:
        evidence = tmp_path / "evidence" / f"{work_item_id}.closure.json"
        if not missing_rh_file:
            _write_json(evidence, {"work_item_id": work_item_id, "contract_pass": True})
        residual_rows[work_item_id] = {
            "closure_evidence_path": str(evidence.relative_to(tmp_path)),
            "last_checked_at_utc": "2026-05-05T04:05:06Z",
            "closed_at_utc": "2026-05-05T04:06:07Z",
        }
    return _write_json(
        tmp_path / "intake.json",
        {
            "schema_version": "p1-evidence-sidecar-intake.v1",
            "generated_at": "2026-05-05T06:07:08Z",
            "external_benchmark_receipts": external_rows,
            "residual_holdout_closures": residual_rows,
        },
    )


def test_build_sidecars_from_complete_intake_passes_preflight(tmp_path: Path) -> None:
    external_payload, residual_payload = builder.build_sidecars(
        intake_manifest=_intake_manifest(tmp_path),
        base_external_updates=tmp_path / "missing-eb.json",
        base_residual_updates=tmp_path / "missing-rh.json",
        repo_root=tmp_path,
        require_complete=True,
    )
    external_out = tmp_path / "external_benchmark_submission_updates.json"
    residual_out = tmp_path / "residual_holdout_closure_updates.json"
    _write_json(external_out, external_payload)
    _write_json(residual_out, residual_payload)

    payload = preflight.build_preflight(
        external_benchmark_submission_updates=external_out,
        residual_holdout_closure_updates=residual_out,
        repo_root=tmp_path,
    )

    assert external_payload["updates"]["hardest_external_10case"]["receipt_status"] == "attached"
    assert "source_commit_sha" in external_payload
    assert external_payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert external_payload["reused_evidence"] is False
    assert external_payload["updates"]["hardest_external_10case"]["submission_lifecycle_status"] == (
        "submitted_receipt_attached"
    )
    assert residual_payload["updates"]["RH-001"]["status"] == "closed"
    assert payload["contract_pass"] is True
    assert payload["summary"]["external_receipt_attached_count"] == 4
    assert payload["summary"]["residual_closed_count"] == 3


def test_build_sidecars_leaves_missing_intake_rows_pending(tmp_path: Path) -> None:
    external_payload, residual_payload = builder.build_sidecars(
        intake_manifest=_intake_manifest(tmp_path, complete=False),
        base_external_updates=tmp_path / "missing-eb.json",
        base_residual_updates=tmp_path / "missing-rh.json",
        repo_root=tmp_path,
    )
    external_out = tmp_path / "external_benchmark_submission_updates.json"
    residual_out = tmp_path / "residual_holdout_closure_updates.json"
    _write_json(external_out, external_payload)
    _write_json(residual_out, residual_payload)

    payload = preflight.build_preflight(
        external_benchmark_submission_updates=external_out,
        residual_holdout_closure_updates=residual_out,
        repo_root=tmp_path,
    )

    assert payload["contract_pass"] is False
    assert payload["summary"]["external_receipt_attached_count"] == 1
    assert payload["summary"]["external_receipt_pending_count"] == 3
    assert payload["summary"]["residual_closed_count"] == 1
    assert "external_receipt_or_closure_pending:tpu_hffb" in payload["blockers"]
    assert "residual_closure_pending:RH-002" in payload["blockers"]


def test_build_sidecars_rejects_missing_local_closure_evidence(tmp_path: Path) -> None:
    try:
        builder.build_sidecars(
            intake_manifest=_intake_manifest(tmp_path, missing_rh_file=True),
            base_external_updates=tmp_path / "missing-eb.json",
            base_residual_updates=tmp_path / "missing-rh.json",
            repo_root=tmp_path,
        )
    except ValueError as exc:
        assert "RH-001 evidence reference is missing or does not exist" in str(exc)
    else:
        raise AssertionError("missing closure evidence path should fail intake build")


def test_build_sidecars_require_complete_rejects_partial_manifest(tmp_path: Path) -> None:
    try:
        builder.build_sidecars(
            intake_manifest=_intake_manifest(tmp_path, complete=False),
            base_external_updates=tmp_path / "missing-eb.json",
            base_residual_updates=tmp_path / "missing-rh.json",
            repo_root=tmp_path,
            require_complete=True,
        )
    except ValueError as exc:
        assert "complete intake required" in str(exc)
        assert "tpu_hffb" in str(exc)
        assert "RH-002" in str(exc)
    else:
        raise AssertionError("partial intake should fail when require_complete=True")


def test_metadata_only_sidecar_refresh_preserves_pending_rows(tmp_path: Path) -> None:
    base_external = _write_json(
        tmp_path / "base-external.json",
        {
            "schema_version": "external-benchmark-submission-updates.v1",
            "updates": {
                "hardest_external_10case": {
                    "submission_receipt": "pending",
                    "receipt_status": "pending_external_submission_receipt",
                }
            },
        },
    )
    base_residual = _write_json(
        tmp_path / "base-residual.json",
        {
            "schema_version": "residual-holdout-closure-updates.v1",
            "updates": {
                "RH-001": {
                    "status": "pending",
                    "closure_evidence_status": "pending",
                }
            },
        },
    )

    external_payload, residual_payload = builder.build_metadata_only_sidecars(
        base_external_updates=base_external,
        base_residual_updates=base_residual,
        repo_root=tmp_path,
    )

    assert external_payload["reused_evidence"] is True
    assert residual_payload["reused_evidence"] is True
    assert external_payload["updates"]["hardest_external_10case"]["submission_receipt"] == "pending"
    assert external_payload["updates"]["hardest_external_10case"]["receipt_status"] == (
        "pending_external_submission_receipt"
    )
    assert external_payload["updates"]["tpu_hffb"] == {}
    assert "does not create, infer, or attach receipts" in external_payload["claim_boundary"]


def test_build_sidecars_cli_writes_outputs_and_summary(tmp_path: Path) -> None:
    external_out = tmp_path / "out" / "external_benchmark_submission_updates.json"
    residual_out = tmp_path / "out" / "residual_holdout_closure_updates.json"
    summary_out = tmp_path / "out" / "summary.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--intake-manifest",
            str(_intake_manifest(tmp_path)),
            "--base-external-updates",
            str(tmp_path / "missing-eb.json"),
            "--base-residual-updates",
            str(tmp_path / "missing-rh.json"),
            "--external-out",
            str(external_out),
            "--residual-out",
            str(residual_out),
            "--summary-out",
            str(summary_out),
            "--repo-root",
            str(tmp_path),
            "--json",
            "--require-complete",
            "--fail-open",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert external_out.exists()
    assert residual_out.exists()
    summary = json.loads(summary_out.read_text(encoding="utf-8"))
    assert summary["contract_pass"] is True
    assert summary["summary"]["external_receipt_attached_count"] == 4
    assert summary["summary"]["residual_closed_count"] == 3


def test_build_sidecars_cli_reports_machine_readable_failure(tmp_path: Path) -> None:
    external_out = tmp_path / "out" / "external_benchmark_submission_updates.json"
    residual_out = tmp_path / "out" / "residual_holdout_closure_updates.json"
    summary_out = tmp_path / "out" / "summary.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--intake-manifest",
            str(_intake_manifest(tmp_path, complete=False)),
            "--base-external-updates",
            str(tmp_path / "missing-eb.json"),
            "--base-residual-updates",
            str(tmp_path / "missing-rh.json"),
            "--external-out",
            str(external_out),
            "--residual-out",
            str(residual_out),
            "--summary-out",
            str(summary_out),
            "--repo-root",
            str(tmp_path),
            "--json",
            "--require-complete",
            "--fail-open",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    summary = json.loads(summary_out.read_text(encoding="utf-8"))
    assert payload == summary
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_P1_EVIDENCE_SIDECAR_BUILD_FAILED"
    assert "complete intake required" in payload["blockers"][0]
    assert "tpu_hffb" in payload["blockers"][0]
    assert "RH-002" in payload["blockers"][0]
