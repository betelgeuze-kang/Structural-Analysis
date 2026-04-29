#!/usr/bin/env python3
"""Preview and optionally apply reviewer batch decisions for audit review packets."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any

from implementation.phase1.generate_external_benchmark_submission_readiness import (
    DEFAULT_COMMERCIAL_READINESS_REPORT,
    DEFAULT_PEER_SPD_HINGE_ALIGNMENT_REPORT,
    DEFAULT_PEER_SPD_HINGE_BENCHMARK_REPORT,
    DEFAULT_PEER_SPD_HINGE_FIXTURE_REGRESSION_REPORT,
    DEFAULT_RELEASE_GAP_REPORT,
    DEFAULT_TPU_HFFB_BENCHMARK_REPORT,
)


DEFAULT_QUEUE_MANIFEST = Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.audit_review_queue.json")
DEFAULT_OUT_DIR = Path("implementation/phase1/release/external_benchmark_kickoff")
DEFAULT_PREVIEW_OUT = DEFAULT_OUT_DIR / "audit_review_decision_batch.live_preview.json"
DEFAULT_OUT = DEFAULT_OUT_DIR / "audit_review_decision_batch_run_report.json"
REQUIRED_BATCH_ATTESTATION_FIELDS = (
    "reviewer_name",
    "reviewer_license_id",
    "decision_basis",
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_step(step: str, cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    return {
        "step": step,
        "command": shlex.join(cmd),
        "return_code": int(proc.returncode),
        "ok": bool(proc.returncode == 0),
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


def _normalize_attestation(payload: Any) -> dict[str, Any]:
    attestation = payload if isinstance(payload, dict) else {}
    return {
        "reviewer_name": str(attestation.get("reviewer_name", "") or "").strip(),
        "reviewer_license_id": str(attestation.get("reviewer_license_id", "") or "").strip(),
        "decision_basis": str(attestation.get("decision_basis", "") or "").strip(),
        "review_session_id": str(attestation.get("review_session_id", "") or "").strip(),
        "attested_at_utc": str(attestation.get("attested_at_utc", "") or "").strip(),
        "apply_live_acknowledged": bool(attestation.get("apply_live_acknowledged", False)),
    }


def _missing_attestation_fields(attestation: dict[str, Any]) -> list[str]:
    missing = [field for field in REQUIRED_BATCH_ATTESTATION_FIELDS if not str(attestation.get(field, "") or "").strip()]
    if not bool(attestation.get("apply_live_acknowledged", False)):
        missing.append("apply_live_acknowledged")
    return missing


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--queue-manifest", default=str(DEFAULT_QUEUE_MANIFEST))
    p.add_argument("--batch-updates-json", required=True)
    p.add_argument("--release-gap-report", default=str(DEFAULT_RELEASE_GAP_REPORT))
    p.add_argument("--commercial-readiness-report", default=str(DEFAULT_COMMERCIAL_READINESS_REPORT))
    p.add_argument("--tpu-hffb-benchmark-report", default=str(DEFAULT_TPU_HFFB_BENCHMARK_REPORT))
    p.add_argument("--peer-spd-hinge-benchmark-report", default=str(DEFAULT_PEER_SPD_HINGE_BENCHMARK_REPORT))
    p.add_argument("--peer-spd-hinge-fixture-regression-report", default=str(DEFAULT_PEER_SPD_HINGE_FIXTURE_REGRESSION_REPORT))
    p.add_argument("--peer-spd-hinge-alignment-report", default=str(DEFAULT_PEER_SPD_HINGE_ALIGNMENT_REPORT))
    p.add_argument("--preview-out", default=str(DEFAULT_PREVIEW_OUT))
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--mgt-export-report", default="")
    p.add_argument("--audit-review-followup-manifest", default="")
    p.add_argument("--audit-review-resolution-manifest", default="")
    p.add_argument("--audit-review-resolution-dir", default="")
    p.add_argument("--apply-live", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--refresh-release-surfaces", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=False)
    args = p.parse_args()

    queue_manifest = Path(args.queue_manifest)
    batch_updates = Path(args.batch_updates_json)
    preview_out = Path(args.preview_out)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    batch_payload = _load_json(batch_updates)
    batch_attestation = _normalize_attestation(
        batch_payload.get("attestation") if isinstance(batch_payload, dict) else {}
    )

    preview_cmd = [
        sys.executable,
        "implementation/phase1/preview_external_benchmark_submission_after_review_updates.py",
        "--queue-manifest",
        str(queue_manifest),
        "--batch-updates-json",
        str(batch_updates),
        "--release-gap-report",
        str(args.release_gap_report),
        "--commercial-readiness-report",
        str(args.commercial_readiness_report),
        "--tpu-hffb-benchmark-report",
        str(args.tpu_hffb_benchmark_report),
        "--peer-spd-hinge-benchmark-report",
        str(args.peer_spd_hinge_benchmark_report),
        "--peer-spd-hinge-fixture-regression-report",
        str(args.peer_spd_hinge_fixture_regression_report),
        "--peer-spd-hinge-alignment-report",
        str(args.peer_spd_hinge_alignment_report),
        "--out",
        str(preview_out),
    ]
    preview_step = _run_step("preview_submission_readiness", preview_cmd)
    if not preview_step["ok"]:
        payload = {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_PREVIEW_FAILED",
            "reason": "preview step failed",
            "apply_live": bool(args.apply_live),
            "dry_run": bool(args.dry_run),
            "steps": [preview_step],
        }
        _write_json(out, payload)
        raise SystemExit(1)

    preview_payload = _load_json(preview_out)

    readiness_summary = (
        preview_payload.get("readiness_preview", {}).get("summary")
        if isinstance(preview_payload.get("readiness_preview"), dict)
        and isinstance(preview_payload.get("readiness_preview", {}).get("summary"), dict)
        else {}
    )

    steps = [preview_step]
    apply_step: dict[str, Any] | None = None
    live_applied = False
    if args.apply_live:
        attestation_missing_fields = (
            _missing_attestation_fields(batch_attestation) if not bool(args.dry_run) else []
        )
        if attestation_missing_fields:
            payload = {
                "schema_version": "1.0",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "contract_pass": False,
                "reason_code": "ERR_MISSING_ATTESTATION",
                "reason": "apply-live requires reviewer attestation",
                "apply_live": bool(args.apply_live),
                "dry_run": bool(args.dry_run),
                "live_applied": False,
                "preview_out": str(preview_out),
                "preview_reason_code": str(preview_payload.get("reason_code", "") or ""),
                "preview_ready_full": bool(readiness_summary.get("ready_to_start_full_submission_now", False)),
                "preview_pending_count": int(readiness_summary.get("audit_review_queue_pending_count", 0) or 0),
                "preview_open_revision_count": int(
                    readiness_summary.get("audit_review_resolution_open_revision_count", 0) or 0
                ),
                "batch_attestation": batch_attestation,
                "batch_attestation_missing_fields": attestation_missing_fields,
                "steps": steps,
            }
            _write_json(out, payload)
            raise SystemExit(1)
        apply_cmd = [
            sys.executable,
            "implementation/phase1/update_audit_review_queue_status.py",
            "--queue-manifest",
            str(queue_manifest),
            "--batch-updates-json",
            str(batch_updates),
            "--out",
            str(out.with_name(out.stem + ".queue_update.json")),
        ]
        if args.mgt_export_report:
            apply_cmd.extend(["--mgt-export-report", str(args.mgt_export_report)])
        if args.audit_review_followup_manifest:
            apply_cmd.extend(["--audit-review-followup-manifest", str(args.audit_review_followup_manifest)])
        if args.audit_review_resolution_manifest:
            apply_cmd.extend(["--audit-review-resolution-manifest", str(args.audit_review_resolution_manifest)])
        if args.audit_review_resolution_dir:
            apply_cmd.extend(["--audit-review-resolution-dir", str(args.audit_review_resolution_dir)])
        if args.refresh_release_surfaces:
            apply_cmd.append("--refresh-release-surfaces")
        if args.dry_run:
            apply_cmd.append("--dry-run")
        apply_step = _run_step("apply_queue_decisions", apply_cmd)
        steps.append(apply_step)
        live_applied = bool(apply_step["ok"]) and not bool(args.dry_run)

    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(preview_step["ok"]) and (apply_step is None or bool(apply_step["ok"])),
        "reason_code": "PASS" if apply_step is None or bool(apply_step["ok"]) else "ERR_APPLY_FAILED",
        "reason": "preview completed" if apply_step is None else "preview and apply completed",
        "apply_live": bool(args.apply_live),
        "dry_run": bool(args.dry_run),
        "live_applied": bool(live_applied),
        "preview_out": str(preview_out),
        "preview_reason_code": str(preview_payload.get("reason_code", "") or ""),
        "preview_ready_full": bool(readiness_summary.get("ready_to_start_full_submission_now", False)),
        "preview_pending_count": int(readiness_summary.get("audit_review_queue_pending_count", 0) or 0),
        "preview_open_revision_count": int(readiness_summary.get("audit_review_resolution_open_revision_count", 0) or 0),
        "batch_attestation": batch_attestation,
        "batch_attestation_missing_fields": [],
        "steps": steps,
    }
    _write_json(out, payload)
    print(f"Wrote audit review decision batch run report: {out}")
    if not payload["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
