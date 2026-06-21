#!/usr/bin/env python3
"""Aggregate workstation delivery service readiness gates."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any


SCHEMA_VERSION = "workstation-delivery-readiness.v1"
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"
DEFAULT_OUT = Path("implementation/phase1/workstation_delivery_readiness.json")
DEFAULT_HARDWARE_PROFILE = Path("implementation/phase1/workstation_hardware_profile.json")
DEFAULT_SERVICE_BUDGET = Path("implementation/phase1/workstation_service_budget.json")
DEFAULT_DELIVERY_PACKAGE_MANIFEST = Path("implementation/phase1/workstation_delivery_package_manifest.json")
DEFAULT_CLIENT_INPUT_VALIDATION_REPORT = Path("implementation/phase1/client_input_validation_report.json")
DEFAULT_JOB_RECORD = Path("implementation/phase1/workstation_job_record.json")
DEFAULT_JOB_RETENTION_POLICY = Path("implementation/phase1/workstation_job_retention_policy.json")
DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE = Path("implementation/phase1/structure_viewer_browser_performance_probe.json")
DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE = Path("implementation/phase1/structure_viewer_visual_regression_baseline.json")
DEFAULT_DELIVERY_VIEWER_SMOKE = Path("implementation/phase1/workstation_delivery_viewer_smoke.json")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _gate(label: str, ok: bool, blockers: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "label": label,
        "status": "ready" if ok else "blocked",
        "ok": bool(ok),
        "blockers": blockers or [],
        **extra,
    }


def _hardware_gate(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    blockers = [
        *(["hardware_profile_missing"] if not path.exists() else []),
        *(["hardware_profile_not_green"] if path.exists() and not payload.get("contract_pass", False) else []),
    ]
    return _gate(
        "Workstation hardware profile",
        not blockers,
        blockers,
        path=str(path),
        summary_line=str(payload.get("summary_line", "")),
    )


def _service_budget_gate(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    blockers = [
        *(["service_budget_missing"] if not path.exists() else []),
        *(["service_budget_not_green"] if path.exists() and not payload.get("contract_pass", False) else []),
    ]
    return _gate(
        "Workstation service budget",
        not blockers,
        blockers,
        path=str(path),
        summary_line=str(payload.get("summary_line", "")),
    )


def _package_gate(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    required_sections = payload.get("required_sections", {})
    if not isinstance(required_sections, dict):
        required_sections = {}
    checksum = payload.get("checksum_self_test", {})
    restore = payload.get("restore_smoke", {})
    manifest_consistency = payload.get("manifest_consistency_self_test", {})
    proxy = str(payload.get("package_claim_boundary", "")).lower()
    blockers = [
        *(["delivery_package_manifest_missing"] if not path.exists() else []),
        *(["delivery_package_manifest_not_green"] if path.exists() and not payload.get("contract_pass", False) else []),
        *(
            f"required_section_missing:{name}"
            for name, ok in required_sections.items()
            if not bool(ok)
        ),
        *(["package_checksum_self_test_failed"] if path.exists() and not checksum.get("pass", False) else []),
        *(["package_restore_smoke_failed"] if path.exists() and not restore.get("pass", False) else []),
        *(
            ["package_manifest_consistency_self_test_failed"]
            if path.exists() and not manifest_consistency.get("pass", False)
            else []
        ),
        *(
            ["package_viewer_shell_marker_missing"]
            if path.exists() and not restore.get("viewer_shell_marker_pass", False)
            else []
        ),
        *(
            ["package_delivery_index_marker_missing"]
            if path.exists() and not restore.get("delivery_index_marker_pass", False)
            else []
        ),
        *(
            ["package_acceptance_packet_marker_missing"]
            if path.exists() and not restore.get("acceptance_packet_marker_pass", False)
            else []
        ),
        *(
            ["package_qa_summary_marker_missing"]
            if path.exists() and not restore.get("qa_summary_marker_pass", False)
            else []
        ),
        *(
            ["package_handoff_diff_marker_missing"]
            if path.exists() and not restore.get("handoff_diff_marker_pass", False)
            else []
        ),
        *(
            ["package_pdf_magic_missing"]
            if path.exists() and not restore.get("pdf_magic_pass", False)
            else []
        ),
        *(
            ["package_manifest_report_reference_missing"]
            if path.exists() and not restore.get("manifest_report_reference_pass", False)
            else []
        ),
        *(
            ["package_manifest_acceptance_reference_missing"]
            if path.exists() and not restore.get("manifest_acceptance_reference_pass", False)
            else []
        ),
        *(
            ["package_manifest_claim_boundary_missing"]
            if path.exists() and not restore.get("manifest_claim_boundary_pass", False)
            else []
        ),
        *(
            ["package_report_metadata_missing_or_invalid"]
            if path.exists() and not restore.get("report_metadata_pass", False)
            else []
        ),
        *(
            ["package_handoff_diff_summary_missing_or_invalid"]
            if path.exists() and not restore.get("handoff_diff_summary_pass", False)
            else []
        ),
        *(
            ["package_signing_manifest_missing_or_invalid"]
            if path.exists() and not restore.get("signing_manifest_pass", False)
            else []
        ),
        *(
            ["package_revision_policy_missing_or_invalid"]
            if path.exists() and not restore.get("revision_policy_pass", False)
            else []
        ),
        *(
            ["package_redelivery_comparison_missing_or_invalid"]
            if path.exists() and not restore.get("redelivery_comparison_pass", False)
            else []
        ),
        *(
            ["package_claim_boundary_missing"]
            if path.exists() and ("engineer" not in proxy or "not an autonomous" not in proxy)
            else []
        ),
    ]
    return _gate(
        "Delivery package manifest",
        not blockers,
        blockers,
        path=str(path),
        package_path=str(payload.get("package_path", "")),
        required_sections=required_sections,
        checksum_self_test_pass=bool(checksum.get("pass", False)),
        manifest_consistency_self_test_pass=bool(manifest_consistency.get("pass", False)),
        restore_smoke_pass=bool(restore.get("pass", False)),
        viewer_shell_marker_pass=bool(restore.get("viewer_shell_marker_pass", False)),
        delivery_index_marker_pass=bool(restore.get("delivery_index_marker_pass", False)),
        acceptance_packet_marker_pass=bool(restore.get("acceptance_packet_marker_pass", False)),
        qa_summary_marker_pass=bool(restore.get("qa_summary_marker_pass", False)),
        handoff_diff_marker_pass=bool(restore.get("handoff_diff_marker_pass", False)),
        pdf_magic_pass=bool(restore.get("pdf_magic_pass", False)),
        manifest_report_reference_pass=bool(restore.get("manifest_report_reference_pass", False)),
        manifest_acceptance_reference_pass=bool(restore.get("manifest_acceptance_reference_pass", False)),
        manifest_claim_boundary_pass=bool(restore.get("manifest_claim_boundary_pass", False)),
        report_metadata_pass=bool(restore.get("report_metadata_pass", False)),
        handoff_diff_summary_pass=bool(restore.get("handoff_diff_summary_pass", False)),
        signing_manifest_pass=bool(restore.get("signing_manifest_pass", False)),
        revision_policy_pass=bool(restore.get("revision_policy_pass", False)),
        redelivery_comparison_pass=bool(restore.get("redelivery_comparison_pass", False)),
    )


def _viewer_gate(viewer_probe_path: Path, visual_path: Path, viewer: dict[str, Any], visual: dict[str, Any]) -> dict[str, Any]:
    blockers = [
        *(["viewer_browser_performance_probe_missing"] if not viewer_probe_path.exists() else []),
        *(["viewer_browser_performance_probe_not_green"] if viewer_probe_path.exists() and not viewer.get("contract_pass", False) else []),
        *(["viewer_visual_regression_baseline_missing"] if not visual_path.exists() else []),
        *(["viewer_visual_regression_baseline_not_green"] if visual_path.exists() and not visual.get("contract_pass", False) else []),
    ]
    return _gate(
        "Viewer smoke and visual evidence",
        not blockers,
        blockers,
        viewer_browser_performance_probe=str(viewer_probe_path),
        viewer_visual_regression_baseline=str(visual_path),
        viewer_probe_summary=str(viewer.get("summary_line", "")),
        visual_summary=str(visual.get("summary_line", "")),
    )


def _delivery_viewer_smoke_gate(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    static_checks = payload.get("static_checks", {})
    if not isinstance(static_checks, dict):
        static_checks = {}
    browser_checks = payload.get("browser_checks", {})
    if not isinstance(browser_checks, dict):
        browser_checks = {}
    alignment = static_checks.get("commercial_cockpit_alignment", {})
    if not isinstance(alignment, dict):
        alignment = {}
    blockers = [
        *(["workstation_delivery_viewer_smoke_missing"] if not path.exists() else []),
        *(["workstation_delivery_viewer_smoke_not_green"] if path.exists() and not payload.get("contract_pass", False) else []),
        *(["workstation_delivery_viewer_static_failed"] if path.exists() and not static_checks.get("pass", False) else []),
        *(["workstation_delivery_viewer_browser_failed"] if path.exists() and not browser_checks.get("pass", False) else []),
        *(
            ["workstation_delivery_viewer_not_current_commercial_cockpit"]
            if path.exists() and str(alignment.get("status", "")) != "current_cockpit_delivery"
            else []
        ),
    ]
    return _gate(
        "Customer-open delivery viewer smoke",
        not blockers,
        blockers,
        path=str(path),
        summary_line=str(payload.get("summary_line", "")),
        package_path=str(payload.get("package_path", "")),
        static_smoke_pass=bool(static_checks.get("pass", False)),
        browser_smoke_pass=bool(browser_checks.get("pass", False)),
        browser_skipped=bool(payload.get("browser_skipped", False)),
        commercial_cockpit_alignment_status=str(alignment.get("status", "")),
        warnings=payload.get("warnings", []) if isinstance(payload.get("warnings", []), list) else [],
    )


def _client_input_gate(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status", "missing") if payload else "missing")
    blockers = [
        *(["client_input_validation_report_missing"] if not path.exists() else []),
        *(["client_input_validation_blocked"] if status == "blocked" else []),
    ]
    return _gate(
        "Client input validation report",
        not blockers,
        blockers,
        path=str(path),
        validation_status=status,
        missing_data_report=payload.get("missing_data_report", []) if payload else [],
    )


def _job_reproducibility_gate(job_record_path: Path, package_payload: dict[str, Any]) -> dict[str, Any]:
    job_record = _load_json(job_record_path)
    folder = package_payload.get("job_folder_contract", {})
    if not isinstance(folder, dict):
        folder = {}
    required_paths = folder.get("required_paths", {})
    if not isinstance(required_paths, dict):
        required_paths = {}
    checksum = folder.get("checksum_self_test", {})
    if not isinstance(checksum, dict):
        checksum = {}
    blockers = [
        *(["workstation_job_record_missing"] if not job_record_path.exists() else []),
        *(
            ["workstation_job_record_schema_invalid"]
            if job_record_path.exists() and job_record.get("schema_version") != "workstation-job-record.v1"
            else []
        ),
        *(["job_folder_contract_missing"] if not folder else []),
        *(["job_folder_contract_failed"] if folder and not folder.get("pass", False) else []),
        *(f"job_required_path_missing:{name}" for name, ok in required_paths.items() if not bool(ok)),
        *(["job_folder_checksum_self_test_failed"] if folder and not checksum.get("pass", False) else []),
    ]
    return _gate(
        "Job reproducibility contract",
        not blockers,
        blockers,
        job_record_path=str(job_record_path),
        job_id=str(job_record.get("job_id", "")),
        job_dir=str(folder.get("job_dir", "")),
        checksum_self_test_pass=bool(checksum.get("pass", False)),
        required_paths=required_paths,
    )


def _job_retention_gate(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    policy = payload.get("policy", {})
    if not isinstance(policy, dict):
        policy = {}
    cleanup_preview = payload.get("cleanup_preview", {})
    if not isinstance(cleanup_preview, dict):
        cleanup_preview = {}
    blockers = [
        *(["workstation_job_retention_policy_missing"] if not path.exists() else []),
        *(["workstation_job_retention_policy_not_green"] if path.exists() and not payload.get("contract_pass", False) else []),
        *(["job_retention_delete_confirmation_missing"] if path.exists() and not policy.get("delete_requires_explicit_confirmation", False) else []),
        *(["job_retention_dry_run_missing"] if path.exists() and not policy.get("cleanup_dry_run_required", False) else []),
        *(["job_retention_cleanup_preview_missing"] if path.exists() and not cleanup_preview else []),
        *(
            ["job_retention_cleanup_preview_not_dry_run"]
            if path.exists() and cleanup_preview and cleanup_preview.get("mode") != "dry_run_only"
            else []
        ),
        *(
            ["job_retention_cleanup_deleted_files"]
            if path.exists() and cleanup_preview.get("delete_operation_executed", False)
            else []
        ),
    ]
    return _gate(
        "Job retention and cleanup policy",
        not blockers,
        blockers,
        path=str(path),
        retention_days=int(policy.get("retention_days", 0) or 0),
        max_completed_jobs=int(policy.get("max_completed_jobs", 0) or 0),
        latest_job_id=str(payload.get("latest_job_id", "")),
        cleanup_preview_candidate_count=int(cleanup_preview.get("candidate_count", 0) or 0),
        cleanup_preview_mode=str(cleanup_preview.get("mode", "")),
    )


def check_workstation_delivery_readiness(
    *,
    hardware_profile: Path = DEFAULT_HARDWARE_PROFILE,
    service_budget: Path = DEFAULT_SERVICE_BUDGET,
    delivery_package_manifest: Path = DEFAULT_DELIVERY_PACKAGE_MANIFEST,
    client_input_validation_report: Path = DEFAULT_CLIENT_INPUT_VALIDATION_REPORT,
    job_record: Path = DEFAULT_JOB_RECORD,
    job_retention_policy: Path = DEFAULT_JOB_RETENTION_POLICY,
    viewer_browser_performance_probe: Path = DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE,
    viewer_visual_regression_baseline: Path = DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE,
    delivery_viewer_smoke: Path = DEFAULT_DELIVERY_VIEWER_SMOKE,
) -> dict[str, Any]:
    hardware = _load_json(hardware_profile)
    budget = _load_json(service_budget)
    package = _load_json(delivery_package_manifest)
    client = _load_json(client_input_validation_report)
    retention = _load_json(job_retention_policy)
    viewer = _load_json(viewer_browser_performance_probe)
    visual = _load_json(viewer_visual_regression_baseline)
    delivery_viewer = _load_json(delivery_viewer_smoke)

    gates = [
        _hardware_gate(hardware_profile, hardware),
        _service_budget_gate(service_budget, budget),
        _package_gate(delivery_package_manifest, package),
        _delivery_viewer_smoke_gate(delivery_viewer_smoke, delivery_viewer),
        _viewer_gate(viewer_browser_performance_probe, viewer_visual_regression_baseline, viewer, visual),
        _client_input_gate(client_input_validation_report, client),
        _job_reproducibility_gate(job_record, package),
        _job_retention_gate(job_retention_policy, retention),
    ]
    blockers = [
        f"{gate['label']}::{blocker}"
        for gate in gates
        for blocker in gate.get("blockers", [])
    ]
    contract_pass = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "reused_evidence": False,
        "contract_pass": contract_pass,
        "workstation_delivery_service_ready": contract_pass,
        "independent_commercial_product_ready": False,
        "reason_code": "PASS" if contract_pass else "ERR_WORKSTATION_DELIVERY_READINESS_BLOCKED",
        "status": "ready" if contract_pass else "blocked",
        "summary_line": (
            f"Workstation delivery readiness: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"gates={sum(1 for gate in gates if gate['ok'])}/{len(gates)}"
        ),
        "claim_boundary": {
            "allowed": "workstation-based structural analysis/optimization deliverable preparation with engineer review",
            "forbidden": [
                "independent commercial structural analysis product",
                "structural engineer replacement",
                "full autonomous replacement",
                "customer-device FPS claim",
                "multi-tenant SaaS throughput claim",
            ],
        },
        "gates": gates,
        "blockers": blockers,
        "artifacts": {
            "hardware_profile": str(hardware_profile),
            "service_budget": str(service_budget),
            "delivery_package_manifest": str(delivery_package_manifest),
            "client_input_validation_report": str(client_input_validation_report),
            "job_record": str(job_record),
            "job_retention_policy": str(job_retention_policy),
            "viewer_browser_performance_probe": str(viewer_browser_performance_probe),
            "viewer_visual_regression_baseline": str(viewer_visual_regression_baseline),
            "delivery_viewer_smoke": str(delivery_viewer_smoke),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hardware-profile", type=Path, default=DEFAULT_HARDWARE_PROFILE)
    parser.add_argument("--service-budget", type=Path, default=DEFAULT_SERVICE_BUDGET)
    parser.add_argument("--delivery-package-manifest", type=Path, default=DEFAULT_DELIVERY_PACKAGE_MANIFEST)
    parser.add_argument("--client-input-validation-report", type=Path, default=DEFAULT_CLIENT_INPUT_VALIDATION_REPORT)
    parser.add_argument("--job-record", type=Path, default=DEFAULT_JOB_RECORD)
    parser.add_argument("--job-retention-policy", type=Path, default=DEFAULT_JOB_RETENTION_POLICY)
    parser.add_argument("--viewer-browser-performance-probe", type=Path, default=DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE)
    parser.add_argument("--viewer-visual-regression-baseline", type=Path, default=DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE)
    parser.add_argument("--delivery-viewer-smoke", type=Path, default=DEFAULT_DELIVERY_VIEWER_SMOKE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = check_workstation_delivery_readiness(
        hardware_profile=args.hardware_profile,
        service_budget=args.service_budget,
        delivery_package_manifest=args.delivery_package_manifest,
        client_input_validation_report=args.client_input_validation_report,
        job_record=args.job_record,
        job_retention_policy=args.job_retention_policy,
        viewer_browser_performance_probe=args.viewer_browser_performance_probe,
        viewer_visual_regression_baseline=args.viewer_visual_regression_baseline,
        delivery_viewer_smoke=args.delivery_viewer_smoke,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
