#!/usr/bin/env python3
"""Summarize the current panel-zone solver-verified inbox state."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from run_panel_zone_solver_verified_handoff import (
    DEFAULT_PANEL_ZONE_INBOX,
    _bundle_source_origin_class,
    _discover_from_drop_dir,
    _drop_dir_source_origin_class,
    _release_refresh_source_allowed,
)


KNOWN_INBOX_FILES = (
    "panel_zone_solver_verified_export_bundle.json",
    "joint_geometry.json",
    "rebar_anchorage.json",
    "clash_verification.json",
    "member_mapping_sidecar.json",
    "panel_zone_handoff_manifest.json",
)

DEFAULT_ARCHIVE_ROOT = Path("implementation/phase1/inbox_archive/panel_zone_solver_verified")
DEFAULT_OUT = Path("implementation/phase1/panel_zone_solver_verified_inbox_status.json")


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


def _latest_archive_dir(archive_root: Path) -> Path | None:
    if not archive_root.exists():
        return None
    candidates = [path for path in archive_root.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.name)


def _input_mode(*, bundle_present: bool, raw_present_count: int, manifest_present: bool) -> str:
    if bundle_present:
        return "bundle"
    if raw_present_count >= 3:
        return "raw_triplet"
    if raw_present_count > 0:
        return "partial_raw"
    if manifest_present:
        return "manifest_only"
    return "empty"


def _status_mode(
    *,
    has_input: bool,
    input_mode: str,
    latest_consume_present: bool,
    latest_consume_pass: bool,
) -> str:
    if has_input:
        return f"pending_{input_mode}"
    if latest_consume_present and latest_consume_pass:
        return "empty_after_successful_consume"
    if latest_consume_present:
        return "empty_after_failed_consume"
    return "empty_without_history"


def _recommended_action(*, has_input: bool, latest_consume_present: bool, latest_consume_pass: bool) -> str:
    if has_input:
        return "consume_pending_input"
    if latest_consume_present and not latest_consume_pass:
        return "inspect_latest_consume_failure"
    return "wait_for_solver_drop"


def _handoff_surface(consume_payload: dict[str, Any]) -> dict[str, Any]:
    artifacts = consume_payload.get("artifacts") if isinstance(consume_payload.get("artifacts"), dict) else {}
    handoff_path_text = str(artifacts.get("handoff_report", "") or "").strip()
    handoff_path = Path(handoff_path_text) if handoff_path_text else None
    handoff_payload = _load_json(handoff_path) if handoff_path is not None else {}
    handoff_summary = (
        handoff_payload.get("summary")
        if isinstance(handoff_payload.get("summary"), dict)
        else {}
    )
    handoff_checks = (
        handoff_payload.get("checks")
        if isinstance(handoff_payload.get("checks"), dict)
        else {}
    )
    handoff_artifacts = (
        handoff_payload.get("artifacts")
        if isinstance(handoff_payload.get("artifacts"), dict)
        else {}
    )
    clash_report_path_text = str(handoff_artifacts.get("panel_zone_clash_report", "") or "").strip()
    clash_report_path = Path(clash_report_path_text) if clash_report_path_text else None
    clash_report_payload = _load_json(clash_report_path) if clash_report_path is not None else {}
    clash_summary = (
        clash_report_payload.get("summary")
        if isinstance(clash_report_payload.get("summary"), dict)
        else {}
    )
    return {
        "handoff_report_present": bool(handoff_payload),
        "handoff_report_path": str(handoff_path or ""),
        "handoff_contract_pass": bool(handoff_payload.get("contract_pass", False)),
        "handoff_panel_chain_pass": bool(
            handoff_summary.get(
                "panel_chain_pass",
                handoff_checks.get("panel_chain_pass", False),
            )
        ),
        "handoff_source_origin_class": str(handoff_summary.get("source_origin_class", "") or "").strip(),
        "clash_report_present": bool(clash_report_payload),
        "clash_report_path": str(clash_report_path or ""),
        "artifact_closed": bool(
            clash_summary.get("panel_zone_external_validation_artifact_closed", False)
        ),
        "artifact_closed_source": str(
            clash_summary.get("panel_zone_external_validation_artifact_closed_source", "") or ""
        ).strip(),
        "closure_mode": str(
            clash_summary.get("panel_zone_external_validation_closure_mode", "") or ""
        ).strip(),
        "status_label": str(
            clash_summary.get("panel_zone_external_validation_status_label", "") or ""
        ).strip(),
        "validation_boundary": str(
            clash_summary.get("panel_zone_validation_boundary", "") or ""
        ).strip(),
        "provenance_summary_label": str(
            clash_summary.get("panel_zone_external_validation_provenance_summary_label", "") or ""
        ).strip(),
        "source_count": int(clash_summary.get("panel_zone_external_validation_source_count", 0) or 0),
        "validated_source_count": int(
            clash_summary.get("panel_zone_external_validation_validated_source_count", 0) or 0
        ),
        "exact_source_count": int(
            clash_summary.get("panel_zone_external_validation_exact_source_count", 0) or 0
        ),
        "fallback_source_count": int(
            clash_summary.get("panel_zone_external_validation_fallback_source_count", 0) or 0
        ),
        "candidate_member_count": int(
            clash_summary.get("panel_zone_external_validation_candidate_member_count", 0) or 0
        ),
        "validated_member_count": int(
            clash_summary.get("panel_zone_external_validation_validated_member_count", 0) or 0
        ),
        "exact_member_count": int(
            clash_summary.get("panel_zone_external_validation_exact_member_count", 0) or 0
        ),
        "fallback_member_count": int(
            clash_summary.get("panel_zone_external_validation_fallback_member_count", 0) or 0
        ),
        "validated_row_count_total": int(
            clash_summary.get("panel_zone_external_validation_validated_row_count_total", 0) or 0
        ),
        "exact_validated_row_count": int(
            clash_summary.get("panel_zone_external_validation_exact_validated_row_count", 0) or 0
        ),
        "fallback_validated_row_count": int(
            clash_summary.get("panel_zone_external_validation_fallback_validated_row_count", 0) or 0
        ),
        "unattributed_validated_row_count": int(
            clash_summary.get("panel_zone_external_validation_unattributed_validated_row_count", 0) or 0
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inbox-dir", default=str(DEFAULT_PANEL_ZONE_INBOX))
    parser.add_argument("--consume-report", default="")
    parser.add_argument("--stage-report", default="")
    parser.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE_ROOT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    inbox_dir = Path(args.inbox_dir)
    consume_report = Path(args.consume_report) if str(args.consume_report).strip() else inbox_dir / "consume_report.json"
    stage_report = Path(args.stage_report) if str(args.stage_report).strip() else inbox_dir / "stage_report.json"
    archive_dir = Path(args.archive_dir)

    bundle_present = (inbox_dir / "panel_zone_solver_verified_export_bundle.json").exists()
    joint_present = (inbox_dir / "joint_geometry.json").exists()
    anchorage_present = (inbox_dir / "rebar_anchorage.json").exists()
    clash_present = (inbox_dir / "clash_verification.json").exists()
    manifest_present = (inbox_dir / "panel_zone_handoff_manifest.json").exists()
    member_mapping_sidecar_present = (inbox_dir / "member_mapping_sidecar.json").exists()
    raw_present_count = sum(bool(value) for value in (joint_present, anchorage_present, clash_present))
    has_input = any((inbox_dir / name).exists() for name in KNOWN_INBOX_FILES)
    input_mode = _input_mode(
        bundle_present=bundle_present,
        raw_present_count=raw_present_count,
        manifest_present=manifest_present,
    )
    discovered_inputs = _discover_from_drop_dir(inbox_dir) if inbox_dir.exists() else {}
    source_origin_class = ""
    if bundle_present:
        source_origin_class = _bundle_source_origin_class(inbox_dir / "panel_zone_solver_verified_export_bundle.json")
    if not source_origin_class and manifest_present:
        source_origin_class = _drop_dir_source_origin_class(inbox_dir)

    consume_payload = _load_json(consume_report)
    stage_payload = _load_json(stage_report)
    latest_archive = _latest_archive_dir(archive_dir)
    latest_consume_present = bool(consume_payload)
    latest_consume_pass = bool(consume_payload.get("contract_pass", False))
    handoff_surface = _handoff_surface(consume_payload)
    latest_handoff_origin_class = str(handoff_surface.get("handoff_source_origin_class", "") or "").strip()
    if not source_origin_class and latest_handoff_origin_class:
        source_origin_class = latest_handoff_origin_class
    release_refresh_source_allowed = bool(_release_refresh_source_allowed(source_origin_class))
    recommended_action = _recommended_action(
        has_input=bool(has_input),
        latest_consume_present=bool(latest_consume_present),
        latest_consume_pass=bool(latest_consume_pass),
    )
    if (
        not has_input
        and latest_consume_present
        and latest_consume_pass
        and bool(handoff_surface.get("artifact_closed", False))
    ):
        recommended_action = "local_closeout_closed"
    elif (
        not has_input
        and latest_consume_present
        and latest_consume_pass
        and not bool(handoff_surface.get("artifact_closed", False))
    ):
        recommended_action = "inspect_successful_consume_outputs"

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-panel-zone-solver-verified-inbox-status",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": True,
        "reason_code": "PASS",
        "reason": "panel-zone solver-verified inbox status generated",
        "inputs": {
            "inbox_dir": str(inbox_dir),
            "consume_report": str(consume_report),
            "stage_report": str(stage_report),
            "archive_dir": str(archive_dir),
        },
        "checks": {
            "inbox_exists": bool(inbox_dir.exists()),
            "inbox_has_input": bool(has_input),
            "bundle_present": bool(bundle_present),
            "raw_triplet_present": bool(raw_present_count >= 3),
            "manifest_present": bool(manifest_present),
            "latest_consume_report_present": bool(latest_consume_present),
            "latest_consume_contract_pass": bool(latest_consume_pass),
            "latest_stage_report_present": bool(stage_payload),
            "latest_archive_present": bool(latest_archive is not None),
            "latest_handoff_report_present": bool(handoff_surface["handoff_report_present"]),
            "latest_handoff_contract_pass": bool(handoff_surface["handoff_contract_pass"]),
            "latest_handoff_panel_chain_pass": bool(handoff_surface["handoff_panel_chain_pass"]),
            "latest_handoff_clash_report_present": bool(handoff_surface["clash_report_present"]),
            "latest_handoff_artifact_closed": bool(handoff_surface["artifact_closed"]),
        },
        "summary": {
            "panel_zone_solver_verified_inbox_status_mode": _status_mode(
                has_input=bool(has_input),
                input_mode=input_mode,
                latest_consume_present=bool(latest_consume_present),
                latest_consume_pass=bool(latest_consume_pass),
            ),
            "panel_zone_solver_verified_input_mode_detected": input_mode,
            "panel_zone_solver_verified_inbox_has_input": bool(has_input),
            "panel_zone_solver_verified_pending_input": bool(has_input),
            "panel_zone_solver_verified_bundle_present": bool(bundle_present),
            "panel_zone_solver_verified_raw_triplet_present": bool(raw_present_count >= 3),
            "panel_zone_solver_verified_manifest_present": bool(manifest_present),
            "panel_zone_solver_verified_member_mapping_sidecar_present": bool(member_mapping_sidecar_present),
            "panel_zone_solver_verified_partial_raw_file_count": int(raw_present_count),
            "panel_zone_solver_verified_latest_consume_report_present": bool(latest_consume_present),
            "panel_zone_solver_verified_latest_consume_contract_pass": bool(latest_consume_pass),
            "panel_zone_solver_verified_latest_consume_reason_code": str(consume_payload.get("reason_code", "")),
            "panel_zone_solver_verified_latest_consume_generated_at": str(consume_payload.get("generated_at", "")),
            "panel_zone_solver_verified_latest_handoff_reason_code": str(
                (consume_payload.get("summary") or {}).get("handoff_reason_code", "")
            ),
            "panel_zone_solver_verified_latest_stage_reason_code": str(stage_payload.get("reason_code", "")),
            "panel_zone_solver_verified_latest_archive_dir": str(latest_archive or ""),
            "panel_zone_solver_verified_source_origin_class": source_origin_class,
            "panel_zone_solver_verified_release_refresh_source_allowed": bool(
                release_refresh_source_allowed
            ),
            "panel_zone_solver_verified_discovered_inputs": {
                str(key): str(value) for key, value in sorted(discovered_inputs.items())
            },
            "panel_zone_solver_verified_latest_handoff_report_present": bool(
                handoff_surface["handoff_report_present"]
            ),
            "panel_zone_solver_verified_latest_handoff_report_path": str(
                handoff_surface["handoff_report_path"]
            ),
            "panel_zone_solver_verified_latest_handoff_contract_pass": bool(
                handoff_surface["handoff_contract_pass"]
            ),
            "panel_zone_solver_verified_latest_handoff_panel_chain_pass": bool(
                handoff_surface["handoff_panel_chain_pass"]
            ),
            "panel_zone_solver_verified_latest_handoff_clash_report_present": bool(
                handoff_surface["clash_report_present"]
            ),
            "panel_zone_solver_verified_latest_handoff_clash_report_path": str(
                handoff_surface["clash_report_path"]
            ),
            "panel_zone_solver_verified_latest_handoff_artifact_closed": bool(
                handoff_surface["artifact_closed"]
            ),
            "panel_zone_solver_verified_latest_handoff_artifact_closed_source": str(
                handoff_surface["artifact_closed_source"]
            ),
            "panel_zone_solver_verified_latest_handoff_closure_mode": str(
                handoff_surface["closure_mode"]
            ),
            "panel_zone_solver_verified_latest_handoff_status_label": str(
                handoff_surface["status_label"]
            ),
            "panel_zone_solver_verified_latest_handoff_validation_boundary": str(
                handoff_surface["validation_boundary"]
            ),
            "panel_zone_solver_verified_latest_handoff_provenance_summary_label": str(
                handoff_surface["provenance_summary_label"]
            ),
            "panel_zone_solver_verified_latest_handoff_source_count": int(
                handoff_surface["source_count"]
            ),
            "panel_zone_solver_verified_latest_handoff_validated_source_count": int(
                handoff_surface["validated_source_count"]
            ),
            "panel_zone_solver_verified_latest_handoff_exact_source_count": int(
                handoff_surface["exact_source_count"]
            ),
            "panel_zone_solver_verified_latest_handoff_fallback_source_count": int(
                handoff_surface["fallback_source_count"]
            ),
            "panel_zone_solver_verified_latest_handoff_candidate_member_count": int(
                handoff_surface["candidate_member_count"]
            ),
            "panel_zone_solver_verified_latest_handoff_validated_member_count": int(
                handoff_surface["validated_member_count"]
            ),
            "panel_zone_solver_verified_latest_handoff_exact_member_count": int(
                handoff_surface["exact_member_count"]
            ),
            "panel_zone_solver_verified_latest_handoff_fallback_member_count": int(
                handoff_surface["fallback_member_count"]
            ),
            "panel_zone_solver_verified_latest_handoff_validated_row_count_total": int(
                handoff_surface["validated_row_count_total"]
            ),
            "panel_zone_solver_verified_latest_handoff_exact_validated_row_count": int(
                handoff_surface["exact_validated_row_count"]
            ),
            "panel_zone_solver_verified_latest_handoff_fallback_validated_row_count": int(
                handoff_surface["fallback_validated_row_count"]
            ),
            "panel_zone_solver_verified_latest_handoff_unattributed_validated_row_count": int(
                handoff_surface["unattributed_validated_row_count"]
            ),
            "panel_zone_solver_verified_recommended_action": recommended_action,
        },
        "artifacts": {
            "consume_report": str(consume_report) if consume_report.exists() else "",
            "stage_report": str(stage_report) if stage_report.exists() else "",
            "latest_archive_dir": str(latest_archive or ""),
        },
    }
    _write_json(Path(args.out), payload)
    print(f"Wrote panel-zone solver-verified inbox status: {args.out}")


if __name__ == "__main__":
    main()
