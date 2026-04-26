#!/usr/bin/env python3
"""Run a safe one-shot live intake for panel-zone solver-verified inbox input."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any

from generate_panel_zone_solver_verified_inbox_status import DEFAULT_ARCHIVE_ROOT
from run_panel_zone_solver_verified_handoff import (
    DEFAULT_PANEL_ZONE_INBOX,
    DEFAULT_TRUSTED_SOURCE_ORIGIN_CLASS,
    _release_refresh_source_allowed,
)


DEFAULT_OUT = Path("implementation/phase1/panel_zone_solver_verified_live_intake_report.json")
DEFAULT_INBOX_STATUS = Path("implementation/phase1/panel_zone_solver_verified_inbox_status.json")
DEFAULT_CONSUME_REPORT = Path("implementation/phase1/inbox/panel_zone_solver_verified/consume_report.json")
DEFAULT_HANDOFF_REPORT = Path("implementation/phase1/panel_zone_solver_verified_handoff_report.json")

REASONS = {
    "PASS": "panel-zone solver-verified live intake passed",
    "ERR_NO_PENDING_INPUT": "no pending solver-verified panel input exists in the inbox",
    "ERR_UNTRUSTED_SOURCE": "live intake is blocked because the inbox source provenance is not trusted for release refresh",
    "ERR_STATUS_FAIL": "failed to generate or read inbox status before live intake",
    "ERR_CONSUME_FAIL": "consume step failed during live intake",
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


def _run(cmd: list[str], *, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        return {
            "command": shlex.join(cmd),
            "return_code": 0,
            "ok": True,
            "status": "dry_run",
            "stdout_tail": "",
            "stderr_tail": "",
        }
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    return {
        "command": shlex.join(cmd),
        "return_code": int(proc.returncode),
        "ok": bool(proc.returncode == 0),
        "status": "ok" if proc.returncode == 0 else "failed",
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inbox-dir", default=str(DEFAULT_PANEL_ZONE_INBOX))
    parser.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE_ROOT))
    parser.add_argument("--inbox-status-report", default=str(DEFAULT_INBOX_STATUS))
    parser.add_argument("--consume-report-out", default=str(DEFAULT_CONSUME_REPORT))
    parser.add_argument("--handoff-report-out", default=str(DEFAULT_HANDOFF_REPORT))
    parser.add_argument("--trusted-source-origin-class", default=DEFAULT_TRUSTED_SOURCE_ORIGIN_CLASS)
    parser.add_argument("--allow-untrusted-source", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--archive-on-success", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--clean-inbox-on-success", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--refresh-external-validation", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    inbox_dir = Path(args.inbox_dir)
    inbox_status_report = Path(args.inbox_status_report)
    consume_report_out = Path(args.consume_report_out)
    handoff_report_out = Path(args.handoff_report_out)
    out = Path(args.out)

    steps: list[dict[str, Any]] = []
    reason_code = "PASS"
    reason = REASONS[reason_code]

    status_cmd = [
        sys.executable,
        "implementation/phase1/generate_panel_zone_solver_verified_inbox_status.py",
        "--inbox-dir",
        str(inbox_dir),
        "--archive-dir",
        str(args.archive_dir),
        "--out",
        str(inbox_status_report),
    ]
    status_step = _run(status_cmd, dry_run=False)
    status_step["step"] = "panel_zone_solver_verified_inbox_status"
    steps.append(status_step)
    if not status_step["ok"]:
        reason_code = "ERR_STATUS_FAIL"
        reason = REASONS[reason_code]

    inbox_status_payload = _load_json(inbox_status_report)
    inbox_summary = (
        inbox_status_payload.get("summary")
        if isinstance(inbox_status_payload.get("summary"), dict)
        else {}
    )
    pending_input = bool(inbox_summary.get("panel_zone_solver_verified_pending_input", False))
    source_origin_class = str(inbox_summary.get("panel_zone_solver_verified_source_origin_class", "") or "").strip()
    expected_trusted = str(args.trusted_source_origin_class).strip() or DEFAULT_TRUSTED_SOURCE_ORIGIN_CLASS
    trusted_source = bool(
        source_origin_class == expected_trusted and _release_refresh_source_allowed(source_origin_class)
    )

    if reason_code == "PASS" and not bool(args.dry_run) and not pending_input:
        reason_code = "ERR_NO_PENDING_INPUT"
        reason = REASONS[reason_code]
    if (
        reason_code == "PASS"
        and not bool(args.allow_untrusted_source)
        and not bool(args.dry_run)
        and not trusted_source
    ):
        reason_code = "ERR_UNTRUSTED_SOURCE"
        reason = (
            f"{REASONS[reason_code]}: source_origin_class="
            f"{source_origin_class or 'missing'}"
        )

    if reason_code == "PASS":
        consume_cmd = [
            sys.executable,
            "implementation/phase1/consume_panel_zone_solver_verified_inbox.py",
            "--inbox-dir",
            str(inbox_dir),
            "--handoff-report-out",
            str(handoff_report_out),
            "--inbox-status-report",
            str(inbox_status_report),
            "--archive-dir",
            str(args.archive_dir),
            "--archive-on-success" if bool(args.archive_on_success) else "--no-archive-on-success",
            "--clean-inbox-on-success" if bool(args.clean_inbox_on_success) else "--no-clean-inbox-on-success",
            "--refresh-release-surfaces",
            "--refresh-external-validation" if bool(args.refresh_external_validation) else "--no-refresh-external-validation",
            "--out",
            str(consume_report_out),
        ]
        if bool(args.dry_run):
            consume_cmd.append("--dry-run")
        consume_step = _run(consume_cmd, dry_run=False)
        consume_step["step"] = "consume_panel_zone_solver_verified_inbox"
        steps.append(consume_step)
        if not consume_step["ok"]:
            reason_code = "ERR_CONSUME_FAIL"
            reason = REASONS[reason_code]
        else:
            inbox_status_payload = _load_json(inbox_status_report)
            inbox_summary = (
                inbox_status_payload.get("summary")
                if isinstance(inbox_status_payload.get("summary"), dict)
                else {}
            )
            pending_input = bool(inbox_summary.get("panel_zone_solver_verified_pending_input", False))
            source_origin_class = str(inbox_summary.get("panel_zone_solver_verified_source_origin_class", "") or "").strip()
            trusted_source = bool(
                source_origin_class == expected_trusted and _release_refresh_source_allowed(source_origin_class)
            )

    consume_payload = _load_json(consume_report_out)
    handoff_payload = _load_json(handoff_report_out)
    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-panel-zone-solver-verified-live-intake",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": reason,
        "inputs": {
            "inbox_dir": str(inbox_dir),
            "archive_dir": str(args.archive_dir),
            "inbox_status_report": str(inbox_status_report),
            "consume_report_out": str(consume_report_out),
            "handoff_report_out": str(handoff_report_out),
            "trusted_source_origin_class": expected_trusted,
            "allow_untrusted_source": bool(args.allow_untrusted_source),
            "archive_on_success": bool(args.archive_on_success),
            "clean_inbox_on_success": bool(args.clean_inbox_on_success),
            "refresh_external_validation": bool(args.refresh_external_validation),
            "dry_run": bool(args.dry_run),
        },
        "checks": {
            "pending_input": bool(pending_input),
            "trusted_source": bool(trusted_source),
            "status_contract_pass": bool(inbox_status_payload.get("contract_pass", False)) if inbox_status_payload else bool(args.dry_run),
            "consume_contract_pass": bool(consume_payload.get("contract_pass", False)),
            "handoff_contract_pass": bool(handoff_payload.get("contract_pass", False)),
        },
        "summary": {
            "panel_zone_solver_verified_inbox_status_mode": str(
                inbox_summary.get("panel_zone_solver_verified_inbox_status_mode", "")
            ),
            "panel_zone_solver_verified_source_origin_class": source_origin_class,
            "panel_zone_solver_verified_release_refresh_source_allowed": bool(
                inbox_summary.get("panel_zone_solver_verified_release_refresh_source_allowed", False)
            ),
            "panel_zone_solver_verified_recommended_action": str(
                inbox_summary.get("panel_zone_solver_verified_recommended_action", "")
            ),
            "panel_zone_constructability_mode": str(
                (handoff_payload.get("summary") or {}).get("panel_zone_constructability_mode", "")
            ),
            "panel_zone_source_contract_mode": str(
                (handoff_payload.get("summary") or {}).get("panel_zone_source_contract_mode", "")
            ),
        },
        "artifacts": {
            "inbox_status_report": str(inbox_status_report),
            "consume_report": str(consume_report_out) if consume_report_out.exists() else "",
            "handoff_report": str(handoff_report_out) if handoff_report_out.exists() else "",
        },
        "steps": steps,
    }
    _write_json(out, payload)
    print(f"Wrote panel-zone live intake report: {out}")

    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
