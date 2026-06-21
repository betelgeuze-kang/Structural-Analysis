#!/usr/bin/env python3
"""Aggregate the gates required before claiming an independent commercial product."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_p0_closure_status import build_status as build_p0_status  # noqa: E402
from check_p1_benchmark_breadth_status import build_status as build_p1_benchmark_status  # noqa: E402
from check_p1_readiness_status import build_status as build_p1_readiness_status  # noqa: E402
from preflight_p1_evidence_sidecar_intake import (  # noqa: E402
    DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_UPDATES,
    DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES,
    build_preflight as build_p1_evidence_preflight,
)
from report_commercialization_level import (  # noqa: E402
    STRICT_CLOSURE_MODE,
    build_report as build_commercialization_report,
)
from report_source_boundary_footprint import build_footprint_report  # noqa: E402
from plan_source_boundary_cleanup import DEFAULT_ALLOWLIST_MANIFEST, _git_files  # noqa: E402


SCHEMA_VERSION = "independent-commercial-product-readiness.v1"
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"
DEFAULT_COMMERCIALIZATION_STATUS = Path("implementation/phase1/release/independent_product_readiness.json")
DEFAULT_INDEPENDENT_PLAN = Path("docs/independent-commercial-productization-plan.md")
DEFAULT_PRODUCTION_SECURITY_DOC = Path("docs/production-ops-security.md")
DEFAULT_RUNTIME_PACKAGING_DOC = Path("docs/runtime-production-packaging.md")
DEFAULT_PROJECT_OPS_API = Path("implementation/phase1/project_ops_api_service.py")
DEFAULT_PROJECT_OPS_DEPLOYMENT_DRILL = Path("implementation/phase1/project_ops_deployment_drill_manifest.json")
DEFAULT_RUNTIME_STRICT_PROBE = Path("implementation/phase1/zero_copy_real_probe_report_strict.json")
DEFAULT_RUNTIME_PACKAGING_MANIFEST = Path("implementation/phase1/production_runtime_packaging_manifest.json")
DEFAULT_SUPPORT_BUNDLE_MANIFEST = Path("implementation/phase1/support_bundle_manifest.json")
DEFAULT_ONPREM_DEPLOYMENT_PACKAGING_MANIFEST = Path("implementation/phase1/onprem_deployment_packaging_manifest.json")
DEFAULT_VIEWER_PERFORMANCE_BUDGET_MANIFEST = Path(
    "implementation/phase1/structure_viewer_performance_budget_manifest.json"
)
DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE = Path("implementation/phase1/structure_viewer_browser_performance_probe.json")
DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE = Path(
    "implementation/phase1/structure_viewer_visual_regression_baseline.json"
)
DEFAULT_WORKSTATION_DELIVERY_READINESS = Path("implementation/phase1/workstation_delivery_readiness.json")
DEFAULT_CLAIM_DOCS = (
    Path("README.md"),
    Path("docs/commercialization-gap-current-state.md"),
    Path("docs/commercialization-improvement-priority-assessment.md"),
    Path("docs/structure-viewer-product-workspace.md"),
    Path("docs/release-publication-runbook.md"),
    Path("docs/architecture-definition-document.md"),
)


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=SCRIPT_DIR.parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _status(ok: bool) -> str:
    return "ready" if ok else "blocked"


def _gate(label: str, ok: bool, *, blockers: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "label": label,
        "status": _status(ok),
        "ok": bool(ok),
        "blockers": blockers or [],
        **extra,
    }


def _load_or_build(path: Path | None, builder: Any) -> dict[str, Any]:
    return _load_json(path) if path else builder()


def _p0_gate(payload: dict[str, Any]) -> dict[str, Any]:
    blockers = [
        *(["p0_release_publication_open"] if not payload.get("release_publication_closed") else []),
        *(["p0_core_evidence_open"] if not payload.get("core_evidence_closed") else []),
    ]
    return _gate(
        "P0 release and core evidence",
        bool(payload.get("p0_closed", False)),
        blockers=blockers,
        p0_closed=bool(payload.get("p0_closed", False)),
        release_publication_closed=bool(payload.get("release_publication_closed", False)),
        core_evidence_closed=bool(payload.get("core_evidence_closed", False)),
    )


def _p1_gate(readiness: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    blockers = [
        *(["p1_inputs_not_ready"] if not readiness.get("p1_inputs_ready") else []),
        *(["p1_execution_blocked"] if not readiness.get("p1_execution_unblocked") else []),
        *(["p1_benchmark_breadth_not_ready"] if not benchmark.get("benchmark_breadth_inputs_ready") else []),
        *(["p1_benchmark_execution_blocked"] if not benchmark.get("p1_benchmark_execution_unblocked") else []),
    ]
    return _gate(
        "P1 validation and benchmark breadth",
        not blockers,
        blockers=blockers,
        p1_inputs_ready=bool(readiness.get("p1_inputs_ready", False)),
        p1_execution_unblocked=bool(readiness.get("p1_execution_unblocked", False)),
        benchmark_breadth_inputs_ready=bool(benchmark.get("benchmark_breadth_inputs_ready", False)),
        p1_benchmark_execution_unblocked=bool(benchmark.get("p1_benchmark_execution_unblocked", False)),
    )


def _strict_evidence_gate(preflight: dict[str, Any], commercialization: dict[str, Any]) -> dict[str, Any]:
    blockers = list(preflight.get("blockers", []))
    if not commercialization.get("strict_evidence_closed"):
        blockers.extend(str(item) for item in commercialization.get("strict_evidence_blockers", []))
    return _gate(
        "Strict external and residual holdout evidence",
        bool(preflight.get("contract_pass")) and bool(commercialization.get("strict_evidence_closed")),
        blockers=sorted(set(blockers)),
        preflight_reason_code=str(preflight.get("reason_code", "")),
        external_receipt_attached_count=int(
            preflight.get("summary", {}).get("external_receipt_attached_count", 0) or 0
        ),
        external_expected_queue_count=int(
            preflight.get("summary", {}).get("external_expected_queue_count", 0) or 0
        ),
        residual_closed_count=int(preflight.get("summary", {}).get("residual_closed_count", 0) or 0),
        residual_expected_work_item_count=int(
            preflight.get("summary", {}).get("residual_expected_work_item_count", 0) or 0
        ),
    )


def _commercial_claim_gate(commercialization: dict[str, Any], claim_docs: tuple[Path, ...]) -> dict[str, Any]:
    blockers: list[str] = []
    stale_docs: list[str] = []
    recommended_claim = str(commercialization.get("recommended_claim", "") or "")
    for path in claim_docs:
        text = _read_text(path)
        if not text:
            blockers.append(f"claim_doc_missing:{path}")
            continue
        if path.name == "commercialization-improvement-priority-assessment.md":
            has_legacy_75 = "75%" in text or "**75%**" in text
            has_legacy_92 = "92%" in text or "9.2/10" in text
            if has_legacy_75 and has_legacy_92:
                stale_docs.append(str(path))
        if "full_commercial_replacement_ready=true" in text and not commercialization.get("strict_evidence_closed"):
            blockers.append(f"premature_full_replacement_claim:{path}")
    if stale_docs:
        blockers.append("commercialization_percentage_claims_conflict")
    if "engineer-in-loop" not in recommended_claim and not commercialization.get("strict_evidence_closed"):
        blockers.append("recommended_claim_missing_engineer_in_loop_boundary")
    return _gate(
        "Commercial claim governance",
        not blockers,
        blockers=blockers,
        recommended_claim=recommended_claim,
        stale_claim_docs=stale_docs,
    )


def _source_boundary_gate(files: list[str] | None, allowlist_manifest: Path) -> dict[str, Any]:
    tracked_files = files if files is not None else _git_files()
    footprint = build_footprint_report(
        files=tracked_files,
        allowlist_manifest=allowlist_manifest,
        large_file_threshold_mib=10.0,
    )
    blockers = []
    if not footprint.get("contract_pass"):
        blockers.append("source_boundary_footprint_contract_failed")
    if int(footprint.get("candidate_files", 0) or 0):
        blockers.append("source_boundary_cleanup_candidates_present")
    return _gate(
        "Source boundary and artifact footprint",
        not blockers,
        blockers=blockers,
        candidate_files=int(footprint.get("candidate_files", 0) or 0),
        allowlisted_files=int(footprint.get("allowlisted_files", 0) or 0),
        allowlisted_mib=float(footprint.get("allowlisted_mib", 0.0) or 0.0),
    )


def _runtime_gate(runtime_strict_probe: Path, runtime_packaging_manifest: Path) -> dict[str, Any]:
    probe = _load_json(runtime_strict_probe)
    packaging = _load_json(runtime_packaging_manifest)
    strict_rust_hip_pass = bool(
        probe.get("strict_rust_hip_pass")
        or probe.get("contract_pass")
        and not probe.get("cpu_fallback_used", False)
    )
    packaging_pass = bool(packaging.get("contract_pass", False))
    blockers = [
        *(["runtime_strict_probe_missing"] if not runtime_strict_probe.exists() else []),
        *(["runtime_strict_rust_hip_not_closed"] if not strict_rust_hip_pass else []),
        *(["runtime_packaging_manifest_missing"] if not runtime_packaging_manifest.exists() else []),
        *(["runtime_packaging_manifest_not_green"] if runtime_packaging_manifest.exists() and not packaging_pass else []),
    ]
    return _gate(
        "Runtime production path",
        not blockers,
        blockers=blockers,
        runtime_strict_probe=str(runtime_strict_probe),
        runtime_packaging_manifest=str(runtime_packaging_manifest),
        strict_rust_hip_pass=strict_rust_hip_pass,
        runtime_packaging_manifest_pass=packaging_pass,
    )


def _ops_security_gate(
    project_ops_api: Path,
    production_security_doc: Path,
    project_ops_deployment_drill: Path,
) -> dict[str, Any]:
    api_text = _read_text(project_ops_api)
    drill = _load_json(project_ops_deployment_drill)
    has_auth = "Authorization" in api_text and "Bearer " in api_text and "X-Tenant-ID" in api_text
    has_audit = "write_audit_event" in api_text and "/audit/events" in api_text
    has_rate_limit = "rate_limit" in api_text and "rate_limited" in api_text and "TOO_MANY_REQUESTS" in api_text
    has_request_limit = "request_metadata_byte_limit" in api_text and "request_metadata_too_large" in api_text
    has_audit_digest = "/audit/digest" in api_text and "audit_log_sha256" in api_text
    has_policy_manifest = "/ops/policy" in api_text and "project-ops-policy.v1" in api_text
    has_lifecycle_policy = (
        "audit_retention_days" in api_text and "backup_policy" in api_text and "tenant_delete_policy" in api_text
    )
    has_default_dev_secret = "project-ops-dev-secret" in api_text
    drill_pass = bool(drill.get("contract_pass"))
    drill_mode = str(drill.get("drill_mode", ""))
    blockers = [
        *(["project_ops_api_missing"] if not project_ops_api.exists() else []),
        *(["project_ops_auth_contract_missing"] if not has_auth else []),
        *(["project_ops_audit_contract_missing"] if not has_audit else []),
        *(["project_ops_rate_limit_missing"] if not has_rate_limit else []),
        *(["project_ops_request_limit_missing"] if not has_request_limit else []),
        *(["project_ops_audit_digest_missing"] if not has_audit_digest else []),
        *(["project_ops_policy_manifest_missing"] if not has_policy_manifest else []),
        *(["project_ops_lifecycle_policy_missing"] if not has_lifecycle_policy else []),
        *(["project_ops_dev_secret_default_present"] if has_default_dev_secret else []),
        *(["project_ops_deployment_drill_manifest_missing"] if not project_ops_deployment_drill.exists() else []),
        *(
            ["project_ops_deployment_drill_manifest_not_green"]
            if project_ops_deployment_drill.exists() and not drill_pass
            else []
        ),
        *(["production_ops_security_doc_missing"] if not production_security_doc.exists() else []),
    ]
    return _gate(
        "Production API security and operations",
        not blockers,
        blockers=blockers,
        project_ops_api=str(project_ops_api),
        production_security_doc=str(production_security_doc),
        project_ops_deployment_drill=str(project_ops_deployment_drill),
        auth_contract_present=has_auth,
        audit_contract_present=has_audit,
        rate_limit_present=has_rate_limit,
        request_limit_present=has_request_limit,
        audit_digest_present=has_audit_digest,
        policy_manifest_present=has_policy_manifest,
        lifecycle_policy_present=has_lifecycle_policy,
        dev_secret_default_present=has_default_dev_secret,
        deployment_drill_manifest_pass=drill_pass,
        deployment_drill_mode=drill_mode,
    )


def _packaging_gate(
    *,
    independent_plan: Path,
    runtime_packaging_doc: Path,
    support_bundle_manifest: Path,
    onprem_deployment_packaging_manifest: Path,
    viewer_performance_budget_manifest: Path,
    viewer_browser_performance_probe: Path,
    viewer_visual_regression_baseline: Path,
) -> dict[str, Any]:
    support_bundle = _load_json(support_bundle_manifest)
    onprem_packaging = _load_json(onprem_deployment_packaging_manifest)
    viewer_performance_budget = _load_json(viewer_performance_budget_manifest)
    viewer_browser_performance = _load_json(viewer_browser_performance_probe)
    viewer_visual_regression = _load_json(viewer_visual_regression_baseline)
    support_bundle_pass = bool(support_bundle.get("contract_pass", False))
    onprem_packaging_pass = bool(onprem_packaging.get("contract_pass", False))
    viewer_performance_budget_pass = bool(viewer_performance_budget.get("contract_pass", False))
    viewer_browser_performance_pass = bool(viewer_browser_performance.get("contract_pass", False))
    viewer_visual_regression_pass = bool(viewer_visual_regression.get("contract_pass", False))
    blockers = [
        *(["independent_productization_plan_missing"] if not independent_plan.exists() else []),
        *(["runtime_packaging_doc_missing"] if not runtime_packaging_doc.exists() else []),
        *(["support_bundle_manifest_missing"] if not support_bundle_manifest.exists() else []),
        *(["support_bundle_manifest_not_green"] if support_bundle_manifest.exists() and not support_bundle_pass else []),
        *(
            ["onprem_deployment_packaging_manifest_missing"]
            if not onprem_deployment_packaging_manifest.exists()
            else []
        ),
        *(
            ["onprem_deployment_packaging_manifest_not_green"]
            if onprem_deployment_packaging_manifest.exists() and not onprem_packaging_pass
            else []
        ),
        *(
            ["viewer_performance_budget_manifest_missing"]
            if not viewer_performance_budget_manifest.exists()
            else []
        ),
        *(
            ["viewer_performance_budget_manifest_not_green"]
            if viewer_performance_budget_manifest.exists() and not viewer_performance_budget_pass
            else []
        ),
        *(["viewer_browser_performance_probe_missing"] if not viewer_browser_performance_probe.exists() else []),
        *(
            ["viewer_browser_performance_probe_not_green"]
            if viewer_browser_performance_probe.exists() and not viewer_browser_performance_pass
            else []
        ),
        *(["viewer_visual_regression_baseline_missing"] if not viewer_visual_regression_baseline.exists() else []),
        *(
            ["viewer_visual_regression_baseline_not_green"]
            if viewer_visual_regression_baseline.exists() and not viewer_visual_regression_pass
            else []
        ),
    ]
    return _gate(
        "Deployment packaging and support bundle",
        not blockers,
        blockers=blockers,
        independent_productization_plan=str(independent_plan),
        runtime_packaging_doc=str(runtime_packaging_doc),
        support_bundle_manifest=str(support_bundle_manifest),
        support_bundle_manifest_pass=support_bundle_pass,
        onprem_deployment_packaging_manifest=str(onprem_deployment_packaging_manifest),
        onprem_deployment_packaging_manifest_pass=onprem_packaging_pass,
        viewer_performance_budget_manifest=str(viewer_performance_budget_manifest),
        viewer_performance_budget_manifest_pass=viewer_performance_budget_pass,
        viewer_browser_performance_probe=str(viewer_browser_performance_probe),
        viewer_browser_performance_probe_pass=viewer_browser_performance_pass,
        viewer_visual_regression_baseline=str(viewer_visual_regression_baseline),
        viewer_visual_regression_baseline_pass=viewer_visual_regression_pass,
    )


def _workstation_delivery_service_status(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    ok = bool(payload.get("contract_pass", False))
    return {
        "label": "Workstation delivery service readiness",
        "status": "ready" if ok else "blocked",
        "ok": ok,
        "path": str(path),
        "summary_line": str(payload.get("summary_line", "")),
        "claim_boundary": payload.get("claim_boundary", {}),
        "blockers": list(payload.get("blockers", [])) if isinstance(payload.get("blockers"), list) else [],
        "note": (
            "This is a separate local workstation delivery-service gate and does not change "
            "independent commercial product EB/RH readiness."
        ),
    }


def _score(gates: list[dict[str, Any]]) -> float:
    weights = {
        "P0 release and core evidence": 15.0,
        "P1 validation and benchmark breadth": 15.0,
        "Strict external and residual holdout evidence": 20.0,
        "Runtime production path": 15.0,
        "Production API security and operations": 15.0,
        "Deployment packaging and support bundle": 10.0,
        "Commercial claim governance": 5.0,
        "Source boundary and artifact footprint": 5.0,
    }
    total = 0.0
    for gate in gates:
        weight = weights.get(str(gate.get("label", "")), 0.0)
        if gate.get("ok"):
            total += weight
    return round(total, 1)


def _next_actions(gates: list[dict[str, Any]]) -> list[str]:
    actions_by_blocker = {
        "external_receipt_or_closure_pending": "Fill and validate the P1 evidence intake manifest before building EB sidecars.",
        "external_submission_receipts_pending": "Attach real EB receipt URL/path for all four external benchmark lanes.",
        "residual_closure_pending": "Fill and validate RH closure evidence in the P1 evidence intake manifest.",
        "residual_holdout_closure_pending": "Attach signed RH closure packets for RH-001/RH-002/RH-003.",
        "runtime_strict_probe_missing": "Run a strict Rust/HIP zero-copy producer probe and save the report.",
        "runtime_strict_rust_hip_not_closed": "Close the real producer -> runtime -> verifier path without CPU fallback.",
        "runtime_packaging_manifest_missing": "Add a production runtime packaging manifest with version compatibility.",
        "runtime_packaging_manifest_not_green": "Complete runtime package version, SBOM, native artifact, and compatibility evidence.",
        "project_ops_dev_secret_default_present": "Split local dev auth from production secret injection and remove production defaults.",
        "project_ops_rate_limit_missing": "Add tenant/actor rate limiting to the project ops API.",
        "project_ops_request_limit_missing": "Add request metadata or body size limits to the project ops API.",
        "project_ops_audit_digest_missing": "Add audit tamper-evidence digest generation and an admin digest endpoint.",
        "project_ops_policy_manifest_missing": "Expose the production ops policy manifest from the project ops API.",
        "project_ops_lifecycle_policy_missing": "Document retention, backup, restore, and tenant deletion policy in the API policy surface.",
        "project_ops_deployment_drill_manifest_missing": "Build the project ops deployment drill manifest for secret rotation, backup/restore, tenant delete, audit, and incident response dry-runs.",
        "project_ops_deployment_drill_manifest_not_green": "Fix blocked rows in the project ops deployment drill manifest.",
        "production_ops_security_doc_missing": "Write the production API security/threat-model/runbook.",
        "runtime_packaging_doc_missing": "Write the runtime packaging and deployment compatibility runbook.",
        "support_bundle_manifest_missing": "Add a support bundle manifest for audit logs, receipts, versions, and diagnostics.",
        "support_bundle_manifest_not_green": "Implement support bundle builder, redaction test, digest, and roundtrip evidence.",
        "onprem_deployment_packaging_manifest_missing": "Build the on-prem and air-gapped deployment packaging manifest.",
        "onprem_deployment_packaging_manifest_not_green": "Fix blocked rows in the on-prem and air-gapped deployment packaging manifest.",
        "viewer_performance_budget_manifest_missing": "Build the structure viewer performance budget manifest.",
        "viewer_performance_budget_manifest_not_green": "Fix blocked rows in the structure viewer performance budget manifest.",
        "viewer_browser_performance_probe_missing": "Run the structure viewer browser performance probe.",
        "viewer_browser_performance_probe_not_green": "Fix blocked rows in the structure viewer browser performance probe.",
        "viewer_visual_regression_baseline_missing": "Build the structure viewer visual regression baseline.",
        "viewer_visual_regression_baseline_not_green": "Fix blocked rows in the structure viewer visual regression baseline.",
        "commercialization_percentage_claims_conflict": "Normalize commercialization claim documents to one source of truth.",
    }
    ordered: list[str] = []
    seen: set[str] = set()
    for gate in gates:
        for blocker in gate.get("blockers", []):
            key = str(blocker).split(":", 1)[0]
            action = actions_by_blocker.get(key)
            if action and action not in seen:
                seen.add(action)
                ordered.append(action)
    return ordered


def build_report(
    *,
    p0_status: Path | None = None,
    p1_readiness_status: Path | None = None,
    p1_benchmark_breadth_status: Path | None = None,
    commercialization_status: Path | None = None,
    strict_evidence_preflight: Path | None = None,
    repo_root: Path = Path.cwd(),
    claim_docs: tuple[Path, ...] = DEFAULT_CLAIM_DOCS,
    independent_plan: Path = DEFAULT_INDEPENDENT_PLAN,
    production_security_doc: Path = DEFAULT_PRODUCTION_SECURITY_DOC,
    runtime_packaging_doc: Path = DEFAULT_RUNTIME_PACKAGING_DOC,
    project_ops_api: Path = DEFAULT_PROJECT_OPS_API,
    project_ops_deployment_drill: Path = DEFAULT_PROJECT_OPS_DEPLOYMENT_DRILL,
    runtime_strict_probe: Path = DEFAULT_RUNTIME_STRICT_PROBE,
    runtime_packaging_manifest: Path = DEFAULT_RUNTIME_PACKAGING_MANIFEST,
    support_bundle_manifest: Path = DEFAULT_SUPPORT_BUNDLE_MANIFEST,
    onprem_deployment_packaging_manifest: Path = DEFAULT_ONPREM_DEPLOYMENT_PACKAGING_MANIFEST,
    viewer_performance_budget_manifest: Path = DEFAULT_VIEWER_PERFORMANCE_BUDGET_MANIFEST,
    viewer_browser_performance_probe: Path = DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE,
    viewer_visual_regression_baseline: Path = DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE,
    workstation_delivery_readiness: Path = DEFAULT_WORKSTATION_DELIVERY_READINESS,
    source_boundary_allowlist: Path = DEFAULT_ALLOWLIST_MANIFEST,
    tracked_files: list[str] | None = None,
) -> dict[str, Any]:
    p0_payload = _load_or_build(p0_status, build_p0_status)
    p1_payload = _load_or_build(p1_readiness_status, build_p1_readiness_status)
    p1_benchmark_payload = _load_or_build(p1_benchmark_breadth_status, build_p1_benchmark_status)
    commercialization_payload = _load_or_build(
        commercialization_status,
        lambda: build_commercialization_report(closure_mode=STRICT_CLOSURE_MODE),
    )
    strict_preflight_payload = _load_or_build(
        strict_evidence_preflight,
        lambda: build_p1_evidence_preflight(
            external_benchmark_submission_updates=DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_UPDATES,
            residual_holdout_closure_updates=DEFAULT_RESIDUAL_HOLDOUT_CLOSURE_UPDATES,
            repo_root=repo_root,
            structure_only=False,
        ),
    )

    gates = [
        _p0_gate(p0_payload),
        _p1_gate(p1_payload, p1_benchmark_payload),
        _strict_evidence_gate(strict_preflight_payload, commercialization_payload),
        _runtime_gate(runtime_strict_probe, runtime_packaging_manifest),
        _ops_security_gate(project_ops_api, production_security_doc, project_ops_deployment_drill),
        _packaging_gate(
            independent_plan=independent_plan,
            runtime_packaging_doc=runtime_packaging_doc,
            support_bundle_manifest=support_bundle_manifest,
            onprem_deployment_packaging_manifest=onprem_deployment_packaging_manifest,
            viewer_performance_budget_manifest=viewer_performance_budget_manifest,
            viewer_browser_performance_probe=viewer_browser_performance_probe,
            viewer_visual_regression_baseline=viewer_visual_regression_baseline,
        ),
        _commercial_claim_gate(commercialization_payload, claim_docs),
        _source_boundary_gate(tracked_files, source_boundary_allowlist),
    ]
    readiness_score = _score(gates)
    independent_ready = all(bool(gate.get("ok", False)) for gate in gates)
    workstation_delivery_service = _workstation_delivery_service_status(workstation_delivery_readiness)
    full_autonomous_ready = bool(
        independent_ready
        and commercialization_payload.get("commercial_scope", {}).get("full_commercial_replacement_ready", False)
    )
    blockers = [
        f"{gate['label']}::{blocker}"
        for gate in gates
        for blocker in gate.get("blockers", [])
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "reused_evidence": False,
        "contract_pass": independent_ready,
        "independent_commercial_product_ready": independent_ready,
        "full_autonomous_replacement_ready": full_autonomous_ready,
        "readiness_score": readiness_score,
        "status": "ready" if independent_ready else "blocked",
        "summary_line": (
            f"Independent commercial product readiness: {'READY' if independent_ready else 'BLOCKED'} | "
            f"score={readiness_score:.1f}/100 | "
            f"full_autonomous_replacement_ready={full_autonomous_ready}"
        ),
        "recommended_claim": commercialization_payload.get("recommended_claim", ""),
        "claim_boundary": (
            "Independent commercial product readiness requires strict external benchmark receipts, "
            "residual holdout closure, production/runtime/ops packaging, and claim governance. "
            "The separate workstation delivery-service gate does not close these independent-product "
            "requirements by itself."
        ),
        "gates": gates,
        "workstation_delivery_service": workstation_delivery_service,
        "blockers": blockers,
        "next_actions": _next_actions(gates),
        "artifacts": {
            "p0_status": str(p0_status or "build_current"),
            "p1_readiness_status": str(p1_readiness_status or "build_current"),
            "p1_benchmark_breadth_status": str(p1_benchmark_breadth_status or "build_current"),
            "commercialization_status": str(commercialization_status or "build_current"),
            "strict_evidence_preflight": str(strict_evidence_preflight or "build_current"),
            "project_ops_deployment_drill": str(project_ops_deployment_drill),
            "runtime_strict_probe": str(runtime_strict_probe),
            "runtime_packaging_manifest": str(runtime_packaging_manifest),
            "support_bundle_manifest": str(support_bundle_manifest),
            "onprem_deployment_packaging_manifest": str(onprem_deployment_packaging_manifest),
            "viewer_performance_budget_manifest": str(viewer_performance_budget_manifest),
            "viewer_browser_performance_probe": str(viewer_browser_performance_probe),
            "viewer_visual_regression_baseline": str(viewer_visual_regression_baseline),
            "workstation_delivery_readiness": str(workstation_delivery_readiness),
        },
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Independent Commercial Product Readiness",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `recommended_claim`: `{payload.get('recommended_claim', '')}`",
        f"- `contract_pass`: `{bool(payload['contract_pass'])}`",
        f"- `independent_commercial_product_ready`: `{bool(payload['independent_commercial_product_ready'])}`",
        f"- `full_autonomous_replacement_ready`: `{bool(payload['full_autonomous_replacement_ready'])}`",
        "",
        "| Gate | Status | Blockers |",
        "|---|---|---|",
    ]
    for gate in payload["gates"]:
        lines.append(
            f"| {gate['label']} | {gate['status']} | {', '.join(gate.get('blockers', [])) or 'none'} |"
        )
    workstation = payload.get("workstation_delivery_service", {})
    lines.extend(
        [
            "",
            "## Separate Workstation Delivery Track",
            "",
            f"- `status`: `{workstation.get('status', 'unknown')}`",
            f"- `summary_line`: `{workstation.get('summary_line', '')}`",
            "- This local delivery-service gate does not close EB/RH independent-product evidence.",
        ]
    )
    lines.extend(["", "## Next Actions", ""])
    for index, action in enumerate(payload.get("next_actions", []), start=1):
        lines.append(f"{index}. {action}")
    if not payload.get("next_actions"):
        lines.append("No blocked actions.")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p0-status", type=Path)
    parser.add_argument("--p1-readiness-status", type=Path)
    parser.add_argument("--p1-benchmark-breadth-status", type=Path)
    parser.add_argument("--commercialization-status", type=Path)
    parser.add_argument("--strict-evidence-preflight", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--independent-plan", type=Path, default=DEFAULT_INDEPENDENT_PLAN)
    parser.add_argument("--production-security-doc", type=Path, default=DEFAULT_PRODUCTION_SECURITY_DOC)
    parser.add_argument("--runtime-packaging-doc", type=Path, default=DEFAULT_RUNTIME_PACKAGING_DOC)
    parser.add_argument("--project-ops-api", type=Path, default=DEFAULT_PROJECT_OPS_API)
    parser.add_argument("--project-ops-deployment-drill", type=Path, default=DEFAULT_PROJECT_OPS_DEPLOYMENT_DRILL)
    parser.add_argument("--runtime-strict-probe", type=Path, default=DEFAULT_RUNTIME_STRICT_PROBE)
    parser.add_argument("--runtime-packaging-manifest", type=Path, default=DEFAULT_RUNTIME_PACKAGING_MANIFEST)
    parser.add_argument("--support-bundle-manifest", type=Path, default=DEFAULT_SUPPORT_BUNDLE_MANIFEST)
    parser.add_argument(
        "--onprem-deployment-packaging-manifest",
        type=Path,
        default=DEFAULT_ONPREM_DEPLOYMENT_PACKAGING_MANIFEST,
    )
    parser.add_argument(
        "--viewer-performance-budget-manifest",
        type=Path,
        default=DEFAULT_VIEWER_PERFORMANCE_BUDGET_MANIFEST,
    )
    parser.add_argument(
        "--viewer-browser-performance-probe",
        type=Path,
        default=DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE,
    )
    parser.add_argument(
        "--viewer-visual-regression-baseline",
        type=Path,
        default=DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE,
    )
    parser.add_argument("--workstation-delivery-readiness", type=Path, default=DEFAULT_WORKSTATION_DELIVERY_READINESS)
    parser.add_argument("--source-boundary-allowlist", type=Path, default=DEFAULT_ALLOWLIST_MANIFEST)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(
        p0_status=args.p0_status,
        p1_readiness_status=args.p1_readiness_status,
        p1_benchmark_breadth_status=args.p1_benchmark_breadth_status,
        commercialization_status=args.commercialization_status,
        strict_evidence_preflight=args.strict_evidence_preflight,
        repo_root=args.repo_root,
        independent_plan=args.independent_plan,
        production_security_doc=args.production_security_doc,
        runtime_packaging_doc=args.runtime_packaging_doc,
        project_ops_api=args.project_ops_api,
        project_ops_deployment_drill=args.project_ops_deployment_drill,
        runtime_strict_probe=args.runtime_strict_probe,
        runtime_packaging_manifest=args.runtime_packaging_manifest,
        support_bundle_manifest=args.support_bundle_manifest,
        onprem_deployment_packaging_manifest=args.onprem_deployment_packaging_manifest,
        viewer_performance_budget_manifest=args.viewer_performance_budget_manifest,
        viewer_browser_performance_probe=args.viewer_browser_performance_probe,
        viewer_visual_regression_baseline=args.viewer_visual_regression_baseline,
        workstation_delivery_readiness=args.workstation_delivery_readiness,
        source_boundary_allowlist=args.source_boundary_allowlist,
    )
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(text if args.json else _markdown(payload))
    return 1 if args.fail_blocked and not bool(payload["contract_pass"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
