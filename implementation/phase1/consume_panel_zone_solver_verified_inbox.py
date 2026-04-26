#!/usr/bin/env python3
"""Consume staged panel-zone solver-verified inputs from the default inbox."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
from typing import Any

from run_panel_zone_solver_verified_handoff import (
    DEFAULT_ANCHORAGE_CONTRACT_OUT,
    DEFAULT_ANCHORAGE_SOURCE_OUT,
    DEFAULT_BUNDLE_OUT,
    DEFAULT_CLASH_ARTIFACT_OUT,
    DEFAULT_CLASH_CONTRACT_OUT,
    DEFAULT_CLASH_REPORT_OUT,
    DEFAULT_CLASH_SOURCE_OUT,
    DEFAULT_COMMITTEE_OUT_DIR,
    DEFAULT_DATASET,
    DEFAULT_EXTERNAL_LATEST,
    DEFAULT_EXTERNAL_LIGHT_LATEST,
    DEFAULT_JOINT_CONTRACT_OUT,
    DEFAULT_JOINT_SOURCE_OUT,
    DEFAULT_OUT,
    DEFAULT_PANEL_ZONE_INBOX,
    DEFAULT_PBD_PACKAGE,
    DEFAULT_RELEASE_GAP_JSON,
    DEFAULT_RELEASE_GAP_MD,
    DEFAULT_RELEASE_PRIVATE_KEY,
    DEFAULT_RELEASE_PUBLIC_KEY,
    DEFAULT_RELEASE_REGISTRY,
    DEFAULT_RELEASE_SIGNATURE,
)


KNOWN_INBOX_FILES = (
    "panel_zone_solver_verified_export_bundle.json",
    "joint_geometry.json",
    "rebar_anchorage.json",
    "clash_verification.json",
    "member_mapping_sidecar.json",
    "panel_zone_handoff_manifest.json",
)

REASONS = {
    "PASS": "panel-zone inbox consumption passed",
    "ERR_NO_INBOX_INPUT": "no usable panel-zone solver-verified input exists in the inbox",
    "ERR_HANDOFF_FAILED": "panel-zone handoff from inbox failed",
    "ERR_ARCHIVE_FAILED": "panel-zone handoff passed, but inbox archival or cleanup failed",
    "ERR_STATUS_REFRESH_FAILED": "panel-zone handoff passed, but post-consume inbox status refresh failed",
    "ERR_RELEASE_REFRESH_FAILED": "panel-zone handoff passed, but post-consume release surface refresh failed",
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    return {
        "command": shlex.join(cmd),
        "return_code": int(proc.returncode),
        "ok": bool(proc.returncode == 0),
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


def _has_inbox_input(inbox_dir: Path) -> bool:
    for name in KNOWN_INBOX_FILES:
        if (inbox_dir / name).exists():
            return True
    return False


def _archive_inbox(
    *,
    inbox_dir: Path,
    archive_root: Path,
    clean_on_success: bool,
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = archive_root / timestamp
    archive_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    deleted: list[str] = []
    for name in KNOWN_INBOX_FILES:
        src = inbox_dir / name
        if not src.exists():
            continue
        dst = archive_dir / name
        shutil.copy2(src, dst)
        copied.append(str(dst))
        if clean_on_success:
            src.unlink()
            deleted.append(str(src))
    return {
        "archive_dir": str(archive_dir),
        "copied_files": copied,
        "deleted_files": deleted,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inbox-dir", default=str(DEFAULT_PANEL_ZONE_INBOX))
    parser.add_argument("--handoff-report-out", default=str(DEFAULT_OUT))
    parser.add_argument("--design-optimization-dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--design-optimization-npz", default="")
    parser.add_argument("--pbd-review-package", default=str(DEFAULT_PBD_PACKAGE))
    parser.add_argument("--panel-zone-solver-export-bundle", default=str(DEFAULT_BUNDLE_OUT))
    parser.add_argument("--panel-zone-joint-geometry-source-output", default=str(DEFAULT_JOINT_SOURCE_OUT))
    parser.add_argument("--panel-zone-rebar-anchorage-source-output", default=str(DEFAULT_ANCHORAGE_SOURCE_OUT))
    parser.add_argument("--panel-zone-clash-verification-source-output", default=str(DEFAULT_CLASH_SOURCE_OUT))
    parser.add_argument("--panel-zone-joint-geometry-contract", default=str(DEFAULT_JOINT_CONTRACT_OUT))
    parser.add_argument("--panel-zone-rebar-anchorage-contract", default=str(DEFAULT_ANCHORAGE_CONTRACT_OUT))
    parser.add_argument("--panel-zone-clash-verification-contract", default=str(DEFAULT_CLASH_CONTRACT_OUT))
    parser.add_argument("--panel-zone-clash-artifact", default=str(DEFAULT_CLASH_ARTIFACT_OUT))
    parser.add_argument("--panel-zone-clash-report", default=str(DEFAULT_CLASH_REPORT_OUT))
    parser.add_argument("--inbox-status-report", default="implementation/phase1/panel_zone_solver_verified_inbox_status.json")
    parser.add_argument("--stage-report", default="")
    parser.add_argument("--refresh-release-surfaces", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--refresh-external-validation", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--archive-dir", default="implementation/phase1/inbox_archive/panel_zone_solver_verified")
    parser.add_argument("--archive-on-success", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--clean-inbox-on-success", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="implementation/phase1/inbox/panel_zone_solver_verified/consume_report.json")
    args = parser.parse_args()

    inbox_dir = Path(args.inbox_dir)
    handoff_report_out = Path(args.handoff_report_out)
    consume_report_out = Path(args.out)
    inbox_status_report = Path(str(args.inbox_status_report).strip() or "implementation/phase1/panel_zone_solver_verified_inbox_status.json")
    stage_report = Path(str(args.stage_report).strip()) if str(args.stage_report).strip() else inbox_dir / "stage_report.json"
    reason_code = "PASS"
    reason = REASONS["PASS"]
    archive_payload: dict[str, Any] = {}
    steps: list[dict[str, Any]] = []

    if not _has_inbox_input(inbox_dir):
        reason_code = "ERR_NO_INBOX_INPUT"
        reason = REASONS[reason_code]
    else:
        handoff_cmd = [
            sys.executable,
            "implementation/phase1/run_panel_zone_solver_verified_handoff.py",
            "--source-drop-dir",
            str(inbox_dir),
            "--design-optimization-dataset",
            str(args.design_optimization_dataset),
            "--pbd-review-package",
            str(args.pbd_review_package),
            "--panel-zone-solver-export-bundle",
            str(args.panel_zone_solver_export_bundle),
            "--panel-zone-joint-geometry-source-output",
            str(args.panel_zone_joint_geometry_source_output),
            "--panel-zone-rebar-anchorage-source-output",
            str(args.panel_zone_rebar_anchorage_source_output),
            "--panel-zone-clash-verification-source-output",
            str(args.panel_zone_clash_verification_source_output),
            "--panel-zone-joint-geometry-contract",
            str(args.panel_zone_joint_geometry_contract),
            "--panel-zone-rebar-anchorage-contract",
            str(args.panel_zone_rebar_anchorage_contract),
            "--panel-zone-clash-verification-contract",
            str(args.panel_zone_clash_verification_contract),
            "--panel-zone-clash-artifact",
            str(args.panel_zone_clash_artifact),
            "--panel-zone-clash-report",
            str(args.panel_zone_clash_report),
            "--out",
            str(handoff_report_out),
        ]
        if str(args.design_optimization_npz).strip():
            handoff_cmd.extend(["--design-optimization-npz", str(args.design_optimization_npz)])
        if bool(args.refresh_release_surfaces):
            handoff_cmd.append("--refresh-release-surfaces")
        if bool(args.refresh_external_validation):
            handoff_cmd.append("--refresh-external-validation")
        if bool(args.dry_run):
            handoff_cmd.append("--dry-run")

        handoff_step = _run(handoff_cmd)
        handoff_step["step"] = "run_panel_zone_solver_verified_handoff"
        steps.append(handoff_step)
        if not handoff_step["ok"]:
            reason_code = "ERR_HANDOFF_FAILED"
            reason = REASONS[reason_code]

    handoff_payload = _load_json(handoff_report_out)
    if reason_code == "PASS" and not bool(handoff_payload.get("contract_pass", False)):
        reason_code = "ERR_HANDOFF_FAILED"
        reason = REASONS[reason_code]

    if (
        reason_code == "PASS"
        and bool(args.archive_on_success)
        and not bool(args.dry_run)
    ):
        try:
            archive_payload = _archive_inbox(
                inbox_dir=inbox_dir,
                archive_root=Path(args.archive_dir),
                clean_on_success=bool(args.clean_inbox_on_success),
            )
        except Exception as exc:
            reason_code = "ERR_ARCHIVE_FAILED"
            reason = f"{REASONS[reason_code]}: {exc}"

    provisional_payload = {
        "schema_version": "1.0",
        "run_id": "phase1-consume-panel-zone-solver-verified-inbox",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": reason,
        "inputs": {
            "inbox_dir": str(inbox_dir),
            "handoff_report_out": str(handoff_report_out),
            "design_optimization_dataset": str(args.design_optimization_dataset),
            "design_optimization_npz": str(args.design_optimization_npz),
            "pbd_review_package": str(args.pbd_review_package),
            "refresh_release_surfaces": bool(args.refresh_release_surfaces),
            "refresh_external_validation": bool(args.refresh_external_validation),
            "inbox_status_report": str(inbox_status_report),
            "archive_dir": str(args.archive_dir),
            "archive_on_success": bool(args.archive_on_success),
            "clean_inbox_on_success": bool(args.clean_inbox_on_success),
            "dry_run": bool(args.dry_run),
        },
        "checks": {
            "inbox_has_input": bool(_has_inbox_input(inbox_dir)),
            "handoff_contract_pass": bool(handoff_payload.get("contract_pass", False)),
        },
        "summary": {
            "consumed_from_inbox": str(inbox_dir),
            "handoff_reason_code": str(handoff_payload.get("reason_code", "")),
            "source_origin_class": str(((handoff_payload.get("summary") or {}).get("source_origin_class", ""))),
            "panel_zone_constructability_mode": str(
                ((handoff_payload.get("summary") or {}).get("panel_zone_constructability_mode", ""))
            ),
            "panel_zone_source_contract_mode": str(
                ((handoff_payload.get("summary") or {}).get("panel_zone_source_contract_mode", ""))
            ),
        },
        "artifacts": {
            "handoff_report": str(handoff_report_out),
            "archive": archive_payload,
        },
        "steps": steps,
    }
    if not bool(args.dry_run):
        _write_json(consume_report_out, provisional_payload)

    status_refresh_pass = True
    if reason_code == "PASS" and not bool(args.dry_run):
        status_cmd = [
            sys.executable,
            "implementation/phase1/generate_panel_zone_solver_verified_inbox_status.py",
            "--inbox-dir",
            str(inbox_dir),
            "--consume-report",
            str(consume_report_out),
            "--stage-report",
            str(stage_report),
            "--archive-dir",
            str(args.archive_dir),
            "--out",
            str(inbox_status_report),
        ]
        status_step = _run(status_cmd)
        status_step["step"] = "panel_zone_solver_verified_inbox_status"
        steps.append(status_step)
        status_refresh_pass = bool(status_step["ok"])
        if not status_refresh_pass:
            reason_code = "ERR_STATUS_REFRESH_FAILED"
            reason = REASONS[reason_code]

    release_surface_refresh_pass = True
    external_validation_refresh_pass = True
    if reason_code == "PASS" and bool(args.refresh_release_surfaces):
        clash_report_cmd = [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(args.design_optimization_dataset),
            "--pbd-review-package",
            str(args.pbd_review_package),
            "--panel-zone-clash-artifact",
            str(args.panel_zone_clash_artifact),
            "--out",
            str(args.panel_zone_clash_report),
        ]
        release_gap_cmd = [
            sys.executable,
            "implementation/phase1/generate_release_gap_report.py",
            "--panel-zone-clash-report",
            str(args.panel_zone_clash_report),
            "--out-json",
            str(DEFAULT_RELEASE_GAP_JSON),
            "--out-md",
            str(DEFAULT_RELEASE_GAP_MD),
        ]
        registry_pass1_cmd = [
            sys.executable,
            "implementation/phase1/generate_signed_release_registry.py",
            "--gap-report",
            str(DEFAULT_RELEASE_GAP_JSON),
            "--committee-package",
            str(DEFAULT_COMMITTEE_OUT_DIR / "committee_review_package_report.json"),
            "--committee-summary",
            str(DEFAULT_COMMITTEE_OUT_DIR / "committee_summary.json"),
            "--private-key-out",
            str(DEFAULT_RELEASE_PRIVATE_KEY),
            "--public-key-out",
            str(DEFAULT_RELEASE_PUBLIC_KEY),
            "--signature-out",
            str(DEFAULT_RELEASE_SIGNATURE),
            "--out",
            str(DEFAULT_RELEASE_REGISTRY),
        ]
        committee_cmd = [
            sys.executable,
            "implementation/phase1/generate_committee_review_package.py",
            "--gap-report",
            str(DEFAULT_RELEASE_GAP_JSON),
            "--release-registry",
            str(DEFAULT_RELEASE_REGISTRY),
            "--out-dir",
            str(DEFAULT_COMMITTEE_OUT_DIR),
        ]
        registry_pass2_cmd = registry_pass1_cmd[:]
        for step_name, cmd in (
            ("post_consume_panel_zone_clash_report", clash_report_cmd),
            ("post_consume_release_gap_report", release_gap_cmd),
            ("post_consume_release_registry_pass1", registry_pass1_cmd),
            ("post_consume_committee_review_package", committee_cmd),
            ("post_consume_release_registry_pass2", registry_pass2_cmd),
        ):
            step = _run(cmd)
            step["step"] = step_name
            steps.append(step)
            if not step["ok"]:
                release_surface_refresh_pass = False
                break
        if release_surface_refresh_pass and bool(args.refresh_external_validation):
            external_cmd = [
                sys.executable,
                "implementation/phase1/prepare_external_validation_submission.py",
                "--release-dir",
                str(DEFAULT_RELEASE_GAP_JSON.parent),
                "--latest-pointer",
                str(DEFAULT_EXTERNAL_LATEST),
                "--light-latest-pointer",
                str(DEFAULT_EXTERNAL_LIGHT_LATEST),
                "--emit-lightweight",
                "--prune-old",
            ]
            external_step = _run(external_cmd)
            external_step["step"] = "post_consume_external_validation_submission"
            steps.append(external_step)
            external_validation_refresh_pass = bool(external_step["ok"])
            release_surface_refresh_pass = bool(release_surface_refresh_pass and external_validation_refresh_pass)
        if not release_surface_refresh_pass:
            reason_code = "ERR_RELEASE_REFRESH_FAILED"
            reason = REASONS[reason_code]

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-consume-panel-zone-solver-verified-inbox",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": reason,
        "inputs": {
            "inbox_dir": str(inbox_dir),
            "handoff_report_out": str(handoff_report_out),
            "design_optimization_dataset": str(args.design_optimization_dataset),
            "design_optimization_npz": str(args.design_optimization_npz),
            "pbd_review_package": str(args.pbd_review_package),
            "refresh_release_surfaces": bool(args.refresh_release_surfaces),
            "refresh_external_validation": bool(args.refresh_external_validation),
            "inbox_status_report": str(inbox_status_report),
            "archive_dir": str(args.archive_dir),
            "archive_on_success": bool(args.archive_on_success),
            "clean_inbox_on_success": bool(args.clean_inbox_on_success),
            "dry_run": bool(args.dry_run),
        },
        "checks": {
            "inbox_has_input": bool(_has_inbox_input(inbox_dir)),
            "handoff_contract_pass": bool(handoff_payload.get("contract_pass", False)),
            "status_refresh_pass": bool(status_refresh_pass),
            "release_surface_refresh_pass": bool(release_surface_refresh_pass),
            "external_validation_refresh_pass": bool(external_validation_refresh_pass),
        },
        "summary": {
            "consumed_from_inbox": str(inbox_dir),
            "handoff_reason_code": str(handoff_payload.get("reason_code", "")),
            "source_origin_class": str(((handoff_payload.get("summary") or {}).get("source_origin_class", ""))),
            "panel_zone_constructability_mode": str(
                ((handoff_payload.get("summary") or {}).get("panel_zone_constructability_mode", ""))
            ),
            "panel_zone_source_contract_mode": str(
                ((handoff_payload.get("summary") or {}).get("panel_zone_source_contract_mode", ""))
            ),
        },
        "artifacts": {
            "handoff_report": str(handoff_report_out),
            "inbox_status_report": str(inbox_status_report) if inbox_status_report.exists() else "",
            "archive": archive_payload,
        },
        "steps": steps,
    }
    _write_json(consume_report_out, payload)
    print(f"Wrote panel-zone inbox consume report: {consume_report_out}")

    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
