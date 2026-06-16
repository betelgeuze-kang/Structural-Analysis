#!/usr/bin/env python3
"""Aggregate PM release milestones into a single evidence-backed gate report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "pm-release-gate-report.v1"

DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/pm_release_gate_report.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_NDTHA_RESIDUAL = Path("implementation/phase1/release_evidence/productization/ndtha_residual_gate_report.json")
DEFAULT_ELEMENT_MATERIAL_BREADTH = Path("implementation/phase1/element_material_breadth_gate_report.json")
DEFAULT_NDTHA_LONG_PROFILE = Path("implementation/phase1/ndtha_long_profile_report.json")
DEFAULT_SOLVER_HIP_E2E = Path("implementation/phase1/solver_hip_e2e_contract_report.json")
DEFAULT_RUNTIME_POLICY = Path("implementation/phase1/release_evidence/productization/solver_runtime_backend_policy.json")
DEFAULT_CI_PR = Path("implementation/phase1/ci_gate_report.pr.json")
DEFAULT_CI_NIGHTLY = Path("implementation/phase1/ci_gate_report.nightly.json")
DEFAULT_CI_STREAK_MANIFEST = Path("implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json")
DEFAULT_CI_REQUIRE_NDTHA = Path("implementation/phase1/release_evidence/productization/pm_strict_ci_require_ndtha_report.json")
DEFAULT_CI_REQUIRE_HIP = Path("implementation/phase1/release_evidence/productization/pm_strict_ci_require_hip_report.json")
DEFAULT_ZERO_COPY_STRICT = Path("implementation/phase1/zero_copy_real_probe_report_strict.json")
DEFAULT_MEASURED_BREADTH = Path(
    "implementation/phase1/release_evidence/productization/measured_benchmark_breadth_report.json"
)
DEFAULT_WORST_CASE_REPORT = Path("implementation/phase1/release_evidence/productization/worst_case_report.json")
DEFAULT_WORKFLOW_PRODUCTIZATION = Path("implementation/phase1/workflow_productization_gate_report.json")
DEFAULT_RELEASE_REGISTRY = Path("implementation/phase1/release/release_registry.json")
DEFAULT_SUPPORT_BUNDLE = Path("implementation/phase1/support_bundle_manifest.json")
DEFAULT_COMMERCIAL_READINESS = Path("implementation/phase1/commercial_readiness_report.strict_breadth.json")
DEFAULT_CORE_FAMILY_P95_REPORT = Path(
    "implementation/phase1/release_evidence/productization/core_family_p95_accuracy_report.json"
)
DEFAULT_RUNTIME_PACKAGING = Path("implementation/phase1/production_runtime_packaging_manifest.json")
DEFAULT_RUNTIME_MEMORY_BUDGET = Path(
    "implementation/phase1/release_evidence/productization/runtime_memory_release_budget_report.json"
)
DEFAULT_RUNTIME_SBOM = Path("implementation/phase1/runtime_sbom.json")
DEFAULT_FRONTEND_DEPENDENCY_AUDIT = Path(
    "implementation/phase1/release_evidence/productization/frontend_dependency_audit_report.json"
)
DEFAULT_REPRO_LOCK = Path("implementation/phase1/reproducibility_version_lock_report.json")
DEFAULT_WORKSTATION_BUDGET = Path("implementation/phase1/workstation_service_budget.json")
DEFAULT_VIEWER_PERFORMANCE_BUDGET = Path("implementation/phase1/structure_viewer_performance_budget_manifest.json")
DEFAULT_MIDAS_INTEROP = Path("implementation/phase1/midas_interoperability_gate_report.json")
DEFAULT_MIDAS_NATIVE_ROUNDTRIP = Path("implementation/phase1/midas_native_roundtrip_gate_report.json")
DEFAULT_MIDAS_EXACT_ROUNDTRIP = Path("implementation/phase1/midas_exact_roundtrip_closure_gate_report.json")
DEFAULT_MIDAS_KDS_GEOMETRY = Path("implementation/phase1/midas_kds_geometry_bridge_validation_report.json")
DEFAULT_OPENSEES_TOPOLOGY = Path("implementation/phase1/opensees_topology_report.json")
DEFAULT_OPENSEES_ROUNDTRIP_TRACE = Path(
    "implementation/phase1/release_evidence/productization/opensees_roundtrip_trace_report.json"
)
DEFAULT_VIEWER_QUALITY = Path("implementation/phase1/commercialization_status/real_drawing_viewer_quality_gate.json")
DEFAULT_UX_RELEASE_READINESS = Path("implementation/phase1/release_evidence/productization/ux_release_readiness_report.json")
DEFAULT_SECURITY_RUNBOOK = Path("docs/production-ops-security.md")
DEFAULT_LICENSE_STATUS = Path("implementation/phase1/release/support_bundle/license_status.json")
DEFAULT_LICENSE_STATUS_CLOSURE = Path(
    "implementation/phase1/release_evidence/productization/license_status_closure_report.json"
)
DEFAULT_AI_ORCHESTRATION_PREFLIGHT = Path(
    "implementation/phase1/release_evidence/productization/ai_orchestration_preflight_report.json"
)
DEFAULT_VALIDATION_MANUAL = Path("docs/commercial-structural-solver-product-gap-ledger.md")
DEFAULT_LIMITATION_MANUAL = Path("docs/structural-analysis-ai-engine-gap-ledger.md")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("summary")
    return value if isinstance(value, dict) else {}


def _checks(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("checks")
    return value if isinstance(value, dict) else {}


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("rows")
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _truthy_contract(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass", False)
        or payload.get("pass", False)
        or str(payload.get("status", "")).strip().lower() == "ready"
    )


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _in_release_evidence(path: Path) -> bool:
    return "release_evidence" in path.parts and path.name == "ndtha_residual_gate_report.json"


def _gate(
    milestone: str,
    title: str,
    *,
    ok: bool,
    blockers: list[str],
    checks: dict[str, Any],
    summary: dict[str, Any],
    artifacts: dict[str, str],
) -> dict[str, Any]:
    return {
        "milestone": milestone,
        "title": title,
        "status": "pass" if ok else "blocked",
        "ok": bool(ok),
        "blockers": blockers,
        "checks": checks,
        "summary": summary,
        "artifacts": artifacts,
    }


def _area(
    area_id: str,
    title: str,
    *,
    ok: bool,
    blockers: list[str],
    checks: dict[str, Any],
    summary: dict[str, Any],
    artifacts: dict[str, str],
    claim_boundary: str = "",
) -> dict[str, Any]:
    return {
        "area": area_id,
        "title": title,
        "status": "pass" if ok else "blocked",
        "ok": bool(ok),
        "blockers": blockers,
        "checks": checks,
        "summary": summary,
        "artifacts": artifacts,
        "claim_boundary": claim_boundary,
    }


def _reason_pass(payload: dict[str, Any]) -> bool:
    return bool(_truthy_contract(payload) or str(payload.get("reason_code", "")).strip().upper() == "PASS")


def _pass_streak(payload: dict[str, Any]) -> int:
    candidates: list[Any] = []
    for source in (payload, _summary(payload), _checks(payload)):
        for key in (
            "consecutive_pass_count",
            "pass_streak_count",
            "ci_consecutive_pass_count",
            "success_streak_count",
            "nightly_pass_streak_count",
            "pr_pass_streak_count",
        ):
            if key in source:
                candidates.append(source.get(key))
    return max([_as_int(value, 0) for value in candidates] or [0])


def _manifest_lane_streak(payload: dict[str, Any], lane: str) -> int:
    lanes = payload.get("lanes")
    if not isinstance(lanes, dict):
        return 0
    lane_payload = lanes.get(lane)
    if not isinstance(lane_payload, dict):
        return 0
    return _as_int(lane_payload.get("consecutive_pass_count"), 0)


def _manifest_lane_int(payload: dict[str, Any], lane: str, key: str) -> int:
    lanes = payload.get("lanes")
    if not isinstance(lanes, dict):
        return 0
    lane_payload = lanes.get(lane)
    if not isinstance(lane_payload, dict):
        return 0
    return _as_int(lane_payload.get(key), 0)


def _manifest_lane_text(payload: dict[str, Any], lane: str, key: str) -> str:
    lanes = payload.get("lanes")
    if not isinstance(lanes, dict):
        return ""
    lane_payload = lanes.get(lane)
    if not isinstance(lane_payload, dict):
        return ""
    return str(lane_payload.get(key, "") or "")


def _ci_lane_owner_action(lane: str, threshold: int, consecutive: int) -> str:
    if consecutive >= threshold:
        return "No release action required; consecutive pass threshold is satisfied."
    missing = max(0, threshold - consecutive)
    if lane == "pr":
        return (
            f"Collect {missing} additional consecutive successful PR CI run(s); keep the pull_request CI lane "
            "green and refresh github_actions_ci_streak_evidence before release signoff."
        )
    if lane == "nightly":
        return (
            f"Collect {missing} additional consecutive successful nightly CI run(s); keep the scheduled/nightly "
            "lane green and refresh github_actions_ci_streak_evidence before release signoff."
        )
    return f"Collect {missing} additional consecutive successful CI run(s) before release signoff."


def _ci_lane_claim_boundary(lane: str) -> str:
    if lane == "pr":
        return (
            "Local PR gate reports prove command-level readiness; release streak credit requires tracked PR CI "
            "evidence for the consecutive-pass window."
        )
    if lane == "nightly":
        return (
            "Local nightly artifacts prove command-level readiness; release streak credit requires tracked "
            "nightly CI evidence for the consecutive-pass window."
        )
    return "Local CI artifacts prove command-level readiness; release streak credit requires tracked CI evidence."


def _read_text_or_empty(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _first_float(payload: dict[str, Any], *keys: str) -> float | None:
    for source in (payload, _summary(payload), _checks(payload)):
        for key in keys:
            if key in source:
                try:
                    return float(source[key])
                except Exception:
                    continue
    return None


def _max_family_p95_error_pct(payload: dict[str, Any]) -> tuple[float | None, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for row in payload.get("model_rows", []):
        if not isinstance(row, dict):
            continue
        model_id = str(row.get("model_id", row.get("family", "")))
        metric_sources = [row]
        metrics = row.get("metrics")
        if isinstance(metrics, dict):
            metric_sources.append(metrics)
        for metrics_payload in metric_sources:
            for key, value in metrics_payload.items():
                if not isinstance(value, (int, float)):
                    continue
                key_text = str(key).lower()
                if "p95" not in key_text or "error" not in key_text:
                    continue
                rows.append({"model_id": model_id, "metric": str(key), "value": float(value)})
    if not rows:
        return None, []
    return max(row["value"] for row in rows), rows


def _core_family_p95_evidence(
    core_family_p95_report: dict[str, Any],
    commercial_readiness: dict[str, Any],
) -> tuple[float | None, list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    for row in core_family_p95_report.get("rows", []):
        if not isinstance(row, dict):
            continue
        value = row.get("p95_error_pct")
        if not isinstance(value, (int, float)):
            continue
        rows.append(
            {
                "model_id": str(row.get("model_id", "")),
                "family": str(row.get("family", "")),
                "metric": str(row.get("metric", "")),
                "value": float(value),
            }
        )
    summary = _summary(core_family_p95_report)
    summary_value = summary.get("max_family_p95_error_pct")
    if isinstance(summary_value, (int, float)) and rows:
        return float(summary_value), rows, "core_family_p95_accuracy_report"
    fallback_max, fallback_rows = _max_family_p95_error_pct(commercial_readiness)
    return fallback_max, fallback_rows, "legacy_commercial_readiness_p95_scan"


def _release_area_blockers(rows: list[dict[str, Any]]) -> list[str]:
    return [
        f"{row['area']}::{blocker}"
        for row in rows
        for blocker in row.get("blockers", [])
    ]


def _residual_milestone(path: Path, *, max_fallback_rate: float) -> dict[str, Any]:
    payload = _load_json(path)
    checks = _checks(payload)
    summary = _summary(payload)
    rows = _rows(payload)
    case_count = _as_int(summary.get("case_count"), len(rows))
    strict_enabled = bool(
        checks.get("strict_recommended_residual_hard_fail_enabled")
        or summary.get("strict_recommended_residual_hard_fail")
    )
    strict_recommended_pass = bool(checks.get("strict_recommended_residual_pass", False))
    fallback_rate = _as_float(summary.get("fallback_rate"), 1.0)
    solver_raw_ratio_present = "solver_raw_ratio" in summary
    solver_raw_ratio = _as_float(summary.get("solver_raw_ratio"), 0.0)
    normalized_rows_pass = bool(rows and all(isinstance(row.get("normalized_residual"), dict) for row in rows))
    corrected_report_required = bool(summary.get("corrected_state_recompute_required"))
    corrected_pass = bool(corrected_report_required and checks.get("corrected_state_recompute_pass", False))

    gate_checks = {
        "release_evidence_path_fixed": bool(path.exists() and _in_release_evidence(path)),
        "ndtha_residual_contract_pass": _truthy_contract(payload),
        "strict_recommended_residual_hard_fail_enabled": strict_enabled,
        "strict_recommended_residual_pass": strict_recommended_pass,
        "fallback_rate_pass": bool(fallback_rate <= max_fallback_rate),
        "residual_source_solver_raw_ratio_present": solver_raw_ratio_present,
        "normalized_residual_rows_pass": normalized_rows_pass,
        "corrected_state_recompute_release_required": True,
        "corrected_state_recompute_report_required": corrected_report_required,
        "corrected_state_recompute_pass": corrected_pass,
    }
    blockers = [
        *(["ndtha_residual_gate_report_not_fixed_in_release_evidence"] if not gate_checks["release_evidence_path_fixed"] else []),
        *(["ndtha_residual_gate_not_green"] if not gate_checks["ndtha_residual_contract_pass"] else []),
        *(["strict_recommended_residual_not_hard_fail"] if not strict_enabled else []),
        *(["recommended_residual_strict_fail"] if strict_enabled and not strict_recommended_pass else []),
        *(["fallback_rate_gt_5pct"] if not gate_checks["fallback_rate_pass"] else []),
        *(["residual_source_solver_raw_ratio_missing"] if not solver_raw_ratio_present else []),
        *(["normalized_residual_missing"] if not normalized_rows_pass else []),
        *(["corrected_state_recompute_missing_or_failed"] if not corrected_pass else []),
    ]
    return _gate(
        "M1",
        "Residual Release Hardening",
        ok=not blockers,
        blockers=blockers,
        checks=gate_checks,
        summary={
            "case_count": case_count,
            "fallback_rate": fallback_rate,
            "max_fallback_rate": max_fallback_rate,
            "solver_raw_ratio": solver_raw_ratio,
            "corrected_state_recompute_present_count": _as_int(
                summary.get("corrected_state_recompute_present_count"), 0
            ),
            "corrected_state_recompute_pass_count": _as_int(summary.get("corrected_state_recompute_pass_count"), 0),
        },
        artifacts={"ndtha_residual_gate_report": str(path)},
    )


def _core_depth_milestone(path: Path, *, min_contact_material_cases: int) -> dict[str, Any]:
    payload = _load_json(path)
    checks = _checks(payload)
    summary = _summary(payload)
    material_models = [str(item) for item in summary.get("material_model_types", []) if str(item).strip()]
    material_blob = " ".join(material_models).lower()
    coupled_case_count = _as_int(
        summary.get("contact_material_coupled_case_count", summary.get("beam_shell_contact_coupling_case_count")),
        -1,
    )
    coupled_signal_count = _as_int(summary.get("beam_shell_contact_coupling_signal_count"), 0)
    reason_code_split_pass = bool(
        checks.get("panel_contact_failure_mode_reason_code_pass")
        or summary.get("panel_contact_failure_mode_reason_code_count", 0)
    )
    nonlinear_residual_case_count = _as_int(summary.get("nonlinear_residual_integrated_case_count"), 0)
    gate_checks = {
        "element_material_breadth_contract_pass": _truthy_contract(payload),
        "contact_material_coupled_case_count_pass": coupled_case_count >= min_contact_material_cases,
        "rc_material_present": "rc" in material_blob,
        "steel_material_present": "steel" in material_blob,
        "composite_material_present": "composite" in material_blob,
        "structural_contact_pass": bool(checks.get("structural_contact_direct_contract_pass")),
        "ssi_foundation_link_pass": bool(checks.get("foundation_soil_link_direct_contract_pass")),
        "panel_contact_failure_reason_code_pass": reason_code_split_pass,
        "nonlinear_residual_same_case_pass": nonlinear_residual_case_count >= 1,
    }
    blockers = [
        *(["element_material_breadth_gate_not_green"] if not gate_checks["element_material_breadth_contract_pass"] else []),
        *(
            ["contact_material_coupled_case_count_lt_10_or_missing"]
            if not gate_checks["contact_material_coupled_case_count_pass"]
            else []
        ),
        *(["rc_steel_composite_material_family_missing"] if not all(gate_checks[key] for key in ("rc_material_present", "steel_material_present", "composite_material_present")) else []),
        *(["structural_contact_contract_missing"] if not gate_checks["structural_contact_pass"] else []),
        *(["ssi_foundation_link_missing_from_core_summary"] if not gate_checks["ssi_foundation_link_pass"] else []),
        *(["panel_contact_failure_reason_code_missing"] if not gate_checks["panel_contact_failure_reason_code_pass"] else []),
        *(["nonlinear_residual_integrated_case_missing"] if not gate_checks["nonlinear_residual_same_case_pass"] else []),
    ]
    return _gate(
        "M2",
        "Core Engine Depth Closure",
        ok=not blockers,
        blockers=blockers,
        checks=gate_checks,
        summary={
            "contact_material_coupled_case_count": max(coupled_case_count, 0),
            "beam_shell_contact_coupling_signal_count": coupled_signal_count,
            "material_model_types": material_models,
            "nonlinear_residual_integrated_case_count": nonlinear_residual_case_count,
        },
        artifacts={"element_material_breadth_report": str(path)},
    )


def _host_copy_share(ci_payload: dict[str, Any], strict_probe: dict[str, Any]) -> float:
    for key in ("host_copy_share", "host_copy_share_ratio"):
        if key in ci_payload:
            return _as_float(ci_payload.get(key), 1.0)
    summary = _summary(ci_payload)
    for key in ("host_copy_share", "host_copy_share_ratio"):
        if key in summary:
            return _as_float(summary.get(key), 1.0)
    for key in ("host_copy_share", "host_copy_share_ratio"):
        if key in strict_probe:
            return _as_float(strict_probe.get(key), 1.0)
    strict_summary = _summary(strict_probe)
    for key in ("host_copy_share", "host_copy_share_ratio"):
        if key in strict_summary:
            return _as_float(strict_summary.get(key), 1.0)
    host_bytes = _as_float(strict_probe.get("host_copy_bytes"), -1.0)
    tensor_bytes = _as_float(strict_probe.get("tensor_bytes"), 0.0)
    if host_bytes >= 0.0 and tensor_bytes > 0.0:
        return host_bytes / tensor_bytes
    return 1.0


def _runtime_milestone(
    *,
    ndtha_long_profile_path: Path,
    solver_hip_e2e_path: Path,
    runtime_policy_path: Path,
    ci_require_ndtha_path: Path,
    zero_copy_strict_path: Path,
    min_device_residency: float,
    max_host_copy_share: float,
    cpu_only_product_mode: bool,
) -> dict[str, Any]:
    ndtha = _load_json(ndtha_long_profile_path)
    hip = _load_json(solver_hip_e2e_path)
    policy = _load_json(runtime_policy_path)
    ci = _load_json(ci_require_ndtha_path)
    strict_probe = _load_json(zero_copy_strict_path)
    hip_checks = _checks(hip)
    hip_summary = _summary(hip)
    host_copy_share = _host_copy_share(ci, strict_probe)
    ndtha_checks = _checks(ndtha)
    ndtha_long_pass = bool(_truthy_contract(ndtha) and ndtha_checks.get("all_runs_pass", True))
    hip_strict_pass = bool(
        _truthy_contract(hip)
        and hip_checks.get("all_main_loops_gpu_pass", False)
        and hip_checks.get("no_cpu_backend_pass", False)
        and hip_checks.get("no_cpu_required_pass", False)
        and hip_checks.get("no_cpu_fallback_pass", False)
    )
    device_residency_min = _as_float(hip_summary.get("device_residency_ratio_min"), 0.0)
    gate_checks = {
        "require_ndtha_pass": ndtha_long_pass,
        "require_hip_pass": hip_strict_pass,
        "cpu_only_product_mode_declared": bool(cpu_only_product_mode),
        "runtime_backend_policy_ready": str(policy.get("status", "")).strip().lower() == "ready",
        "official_backend_rocm_hip": str(policy.get("official_solver_backend_family", "")) == "rocm_hip",
        "cpu_fallback_release_forbidden_pass": bool(
            not policy.get("cpu_solver_fallback_detected", True)
            and not policy.get("cpu_fallback_allowed_for_official_solver_closure", True)
        ),
        "device_residency_target_pass": bool(cpu_only_product_mode or device_residency_min >= min_device_residency),
        "host_copy_share_pass": host_copy_share <= max_host_copy_share,
    }
    blockers = [
        *(["require_ndtha_long_profile_failed"] if not gate_checks["require_ndtha_pass"] else []),
        *(["require_hip_failed_without_cpu_only_product_mode"] if not (hip_strict_pass or cpu_only_product_mode) else []),
        *(["runtime_backend_policy_not_ready"] if not gate_checks["runtime_backend_policy_ready"] else []),
        *(["official_backend_not_rocm_hip"] if not gate_checks["official_backend_rocm_hip"] and not cpu_only_product_mode else []),
        *(["cpu_fallback_allowed_or_detected"] if not gate_checks["cpu_fallback_release_forbidden_pass"] else []),
        *(["device_residency_below_target"] if not gate_checks["device_residency_target_pass"] else []),
        *(["host_copy_share_gt_5pct"] if not gate_checks["host_copy_share_pass"] else []),
    ]
    return _gate(
        "M3",
        "Strict Runtime Closure",
        ok=not blockers,
        blockers=blockers,
        checks=gate_checks,
        summary={
            "device_residency_ratio_min": device_residency_min,
            "min_device_residency_ratio": min_device_residency,
            "host_copy_share": host_copy_share,
            "max_host_copy_share": max_host_copy_share,
            "official_solver_backend": str(policy.get("official_solver_backend", "")),
            "rocm_sparse_solver_probe_ready": bool(policy.get("rocm_sparse_solver_probe_ready", False)),
        },
        artifacts={
            "ndtha_long_profile": str(ndtha_long_profile_path),
            "solver_hip_e2e": str(solver_hip_e2e_path),
            "runtime_policy": str(runtime_policy_path),
            "ci_require_ndtha": str(ci_require_ndtha_path),
            "zero_copy_strict": str(zero_copy_strict_path),
        },
    )


def _benchmark_milestone(
    path: Path,
    *,
    worst_case_report_path: Path,
    min_validation_cases: int,
    min_structure_families: int,
) -> dict[str, Any]:
    payload = _load_json(path)
    summary = _summary(payload)
    worst_case = _load_json(worst_case_report_path)
    case_count = _as_int(summary.get("measured_case_count"), 0)
    family_count = _as_int(summary.get("measured_family_count"), 0)
    holdout_family_count = _as_int(summary.get("holdout_family_count"), 0)
    source_split_pass = bool(
        summary.get("baseline_measured_case_count", 0)
        and (
            summary.get("opensees_incremental_case_count", 0)
            or summary.get("external_incremental_case_count", 0)
            or summary.get("canton_incremental_case_count", 0)
        )
    )
    gate_checks = {
        "measured_benchmark_breadth_contract_pass": _truthy_contract(payload),
        "validation_case_count_pass": case_count >= min_validation_cases,
        "structure_family_count_pass": family_count >= min_structure_families,
        "holdout_cases_per_family_present": holdout_family_count >= min_structure_families,
        "worst_case_report_pass": _truthy_contract(worst_case),
        "measured_open_data_split_pass": source_split_pass,
    }
    blockers = [
        *(["measured_benchmark_breadth_not_green"] if not gate_checks["measured_benchmark_breadth_contract_pass"] else []),
        *(["validation_case_count_lt_100"] if not gate_checks["validation_case_count_pass"] else []),
        *(["structure_family_count_lt_5"] if not gate_checks["structure_family_count_pass"] else []),
        *(["holdout_cases_per_family_missing"] if not gate_checks["holdout_cases_per_family_present"] else []),
        *(["worst_case_report_missing_or_failed"] if not gate_checks["worst_case_report_pass"] else []),
        *(["measured_open_data_split_missing"] if not gate_checks["measured_open_data_split_pass"] else []),
    ]
    return _gate(
        "M4",
        "Benchmark Breadth Expansion",
        ok=not blockers,
        blockers=blockers,
        checks=gate_checks,
        summary={
            "measured_case_count": case_count,
            "measured_family_count": family_count,
            "holdout_family_count": holdout_family_count,
            "min_validation_cases": min_validation_cases,
            "min_structure_families": min_structure_families,
        },
        artifacts={"measured_benchmark_breadth_report": str(path), "worst_case_report": str(worst_case_report_path)},
    )


def _packaging_milestone(
    *,
    workflow_path: Path,
    release_registry_path: Path,
    support_bundle_path: Path,
    validation_manual_path: Path,
    limitation_manual_path: Path,
) -> dict[str, Any]:
    workflow = _load_json(workflow_path)
    registry = _load_json(release_registry_path)
    support = _load_json(support_bundle_path)
    workflow_summary = _summary(workflow)
    registry_summary = _summary(registry)
    support_checks = _checks(support)
    support_optional_sections = _as_dict(support.get("optional_sections"))
    summary_line = str(workflow.get("summary_line", "") or "")
    gate_checks = {
        "workflow_productization_pass": _truthy_contract(workflow),
        "viewer_reviewer_customer_surface_pass": bool(
            "viewer=yes" in summary_line
            or str(workflow_summary.get("viewer_mode", "")).strip()
        ),
        "pdf_report_or_reviewer_package_pass": bool(
            workflow_summary.get("results_explorer_traceability_pass")
            or "results+review" in summary_line
        ),
        "audit_trail_action_source_trace_pass": bool(
            workflow_summary.get("results_explorer_traceability_pass")
            and workflow_summary.get("zero_touch_no_open_decision_items_pass", False)
        ),
        "signed_release_registry_pass": bool(
            _truthy_contract(registry)
            and str(registry_summary.get("signing_algorithm", "")).lower() == "ed25519"
        ),
        "support_bundle_export_pass": bool(
            _truthy_contract(support)
            and support_checks.get("redaction_self_test_pass", False)
            and support_checks.get("bundle_roundtrip_test_pass", False)
        ),
        "support_bundle_pm_blocker_register_present": bool(
            support_optional_sections.get("pm_release_blocker_action_register")
        ),
        "support_bundle_license_intake_packet_present": bool(
            support_optional_sections.get("license_status_intake_packet")
        ),
        "support_bundle_frontend_dependency_audit_present": bool(
            support_optional_sections.get("frontend_dependency_audit_report")
        ),
        "validation_manual_present": validation_manual_path.exists(),
        "limitation_manual_present": limitation_manual_path.exists(),
    }
    blockers = [
        *(["workflow_productization_gate_not_green"] if not gate_checks["workflow_productization_pass"] else []),
        *(["viewer_reviewer_customer_preset_missing"] if not gate_checks["viewer_reviewer_customer_surface_pass"] else []),
        *(["pdf_report_or_reviewer_package_missing"] if not gate_checks["pdf_report_or_reviewer_package_pass"] else []),
        *(["audit_trail_action_source_trace_missing"] if not gate_checks["audit_trail_action_source_trace_pass"] else []),
        *(["signed_release_registry_missing_or_failed"] if not gate_checks["signed_release_registry_pass"] else []),
        *(["support_bundle_export_missing_or_failed"] if not gate_checks["support_bundle_export_pass"] else []),
        *(
            ["support_bundle_pm_blocker_register_missing"]
            if not gate_checks["support_bundle_pm_blocker_register_present"]
            else []
        ),
        *(
            ["support_bundle_license_intake_packet_missing"]
            if not gate_checks["support_bundle_license_intake_packet_present"]
            else []
        ),
        *(
            ["support_bundle_frontend_dependency_audit_missing"]
            if not gate_checks["support_bundle_frontend_dependency_audit_present"]
            else []
        ),
        *(["validation_manual_missing"] if not gate_checks["validation_manual_present"] else []),
        *(["limitation_manual_missing"] if not gate_checks["limitation_manual_present"] else []),
    ]
    return _gate(
        "M5",
        "Commercial Packaging",
        ok=not blockers,
        blockers=blockers,
        checks=gate_checks,
        summary={
            "viewer_mode": str(workflow_summary.get("viewer_mode", "")),
            "release_registry_artifact_count": _as_int(registry_summary.get("artifact_count"), 0),
            "support_bundle_missing_required_count": _as_int(support_checks.get("missing_required_count"), -1),
            "support_bundle_pm_blocker_register": str(
                support_optional_sections.get("pm_release_blocker_action_register", "")
            ),
            "support_bundle_license_status_intake_packet": str(
                support_optional_sections.get("license_status_intake_packet", "")
            ),
            "support_bundle_frontend_dependency_audit": str(
                support_optional_sections.get("frontend_dependency_audit_report", "")
            ),
        },
        artifacts={
            "workflow_productization": str(workflow_path),
            "release_registry": str(release_registry_path),
            "support_bundle": str(support_bundle_path),
            "validation_manual": str(validation_manual_path),
            "limitation_manual": str(limitation_manual_path),
        },
    )


def _build_release_area_matrix(
    *,
    milestones: list[dict[str, Any]],
    ci_pr_path: Path,
    ci_nightly_path: Path,
    ci_streak_manifest_path: Path,
    ci_require_ndtha_path: Path,
    ci_require_hip_path: Path,
    commercial_readiness_path: Path,
    core_family_p95_report_path: Path,
    ndtha_residual_path: Path,
    ndtha_long_profile_path: Path,
    solver_hip_e2e_path: Path,
    runtime_policy_path: Path,
    measured_benchmark_breadth_path: Path,
    workflow_productization_path: Path,
    release_registry_path: Path,
    support_bundle_path: Path,
    runtime_packaging_path: Path,
    runtime_memory_budget_path: Path,
    runtime_sbom_path: Path,
    frontend_dependency_audit_path: Path,
    repro_lock_path: Path,
    workstation_budget_path: Path,
    viewer_performance_budget_path: Path,
    midas_interop_path: Path,
    midas_native_roundtrip_path: Path,
    midas_exact_roundtrip_path: Path,
    midas_kds_geometry_path: Path,
    opensees_topology_path: Path,
    opensees_roundtrip_trace_path: Path,
    viewer_quality_path: Path,
    ux_release_readiness_path: Path,
    security_runbook_path: Path,
    license_status_path: Path,
    license_status_closure_path: Path,
    validation_manual_path: Path,
    limitation_manual_path: Path,
    cpu_only_product_mode: bool,
    ci_pass_streak_threshold: int,
    core_p95_error_pct_limit: float,
    max_residual_fallback_rate: float,
    ga_residual_fallback_rate: float,
    min_validation_cases: int,
    ga_validation_cases: int,
    max_runtime_budget_exceed_rate: float,
) -> list[dict[str, Any]]:
    by_id = {row["milestone"]: row for row in milestones}
    ci_pr = _load_json(ci_pr_path)
    ci_nightly = _load_json(ci_nightly_path)
    ci_streak_manifest = _load_json(ci_streak_manifest_path)
    ci_ndtha = _load_json(ci_require_ndtha_path)
    ci_hip = _load_json(ci_require_hip_path)
    commercial = _load_json(commercial_readiness_path)
    core_family_p95 = _load_json(core_family_p95_report_path)
    residual = _load_json(ndtha_residual_path)
    ndtha_long = _load_json(ndtha_long_profile_path)
    runtime_policy = _load_json(runtime_policy_path)
    measured_breadth = _load_json(measured_benchmark_breadth_path)
    workflow = _load_json(workflow_productization_path)
    support = _load_json(support_bundle_path)
    runtime_packaging = _load_json(runtime_packaging_path)
    runtime_memory_budget = _load_json(runtime_memory_budget_path)
    sbom = _load_json(runtime_sbom_path)
    frontend_dependency_audit = _load_json(frontend_dependency_audit_path)
    repro = _load_json(repro_lock_path)
    workstation = _load_json(workstation_budget_path)
    viewer_perf = _load_json(viewer_performance_budget_path)
    midas_interop = _load_json(midas_interop_path)
    midas_native = _load_json(midas_native_roundtrip_path)
    midas_exact = _load_json(midas_exact_roundtrip_path)
    kds = _load_json(midas_kds_geometry_path)
    opensees = _load_json(opensees_topology_path)
    opensees_roundtrip_report = _load_json(opensees_roundtrip_trace_path)
    viewer_quality = _load_json(viewer_quality_path)
    ux_release = _load_json(ux_release_readiness_path)
    license_status = _load_json(license_status_path)
    license_status_closure = _load_json(license_status_closure_path)

    rows: list[dict[str, Any]] = []

    pr_streak = max(_pass_streak(ci_pr), _manifest_lane_streak(ci_streak_manifest, "pr"))
    nightly_streak = max(_pass_streak(ci_nightly), _manifest_lane_streak(ci_streak_manifest, "nightly"))
    ci_streak_evidence_sources = ci_streak_manifest.get("evidence_sources")
    if not isinstance(ci_streak_evidence_sources, dict):
        ci_streak_evidence_sources = {}
    pr_owner_action = _manifest_lane_text(ci_streak_manifest, "pr", "owner_action") or _ci_lane_owner_action(
        "pr",
        ci_pass_streak_threshold,
        pr_streak,
    )
    nightly_owner_action = _manifest_lane_text(
        ci_streak_manifest,
        "nightly",
        "owner_action",
    ) or _ci_lane_owner_action("nightly", ci_pass_streak_threshold, nightly_streak)
    pr_claim_boundary = _manifest_lane_text(ci_streak_manifest, "pr", "claim_boundary") or _ci_lane_claim_boundary(
        "pr"
    )
    nightly_claim_boundary = _manifest_lane_text(
        ci_streak_manifest,
        "nightly",
        "claim_boundary",
    ) or _ci_lane_claim_boundary("nightly")
    basic_ci_checks = {
        "pr_ci_pass": _reason_pass(ci_pr),
        "nightly_ci_pass": _reason_pass(ci_nightly),
        "pr_ci_30_run_streak_pass": pr_streak >= ci_pass_streak_threshold,
        "nightly_ci_30_run_streak_pass": nightly_streak >= ci_pass_streak_threshold,
    }
    basic_ci_blockers = [
        *(["pr_ci_not_pass"] if not basic_ci_checks["pr_ci_pass"] else []),
        *(["nightly_ci_not_pass"] if not basic_ci_checks["nightly_ci_pass"] else []),
        *(["pr_ci_30_consecutive_pass_evidence_missing"] if not basic_ci_checks["pr_ci_30_run_streak_pass"] else []),
        *(
            ["nightly_ci_30_consecutive_pass_evidence_missing"]
            if not basic_ci_checks["nightly_ci_30_run_streak_pass"]
            else []
        ),
    ]
    rows.append(
        _area(
            "basic_ci",
            "Basic CI",
            ok=not basic_ci_blockers,
            blockers=basic_ci_blockers,
            checks=basic_ci_checks,
            summary={
                "required_consecutive_pass_count": ci_pass_streak_threshold,
                "pr_pass_streak_count": pr_streak,
                "nightly_pass_streak_count": nightly_streak,
                "pr_local_pass_streak_count": _manifest_lane_int(
                    ci_streak_manifest, "pr", "local_consecutive_pass_count"
                ),
                "nightly_local_pass_streak_count": _manifest_lane_int(
                    ci_streak_manifest, "nightly", "local_consecutive_pass_count"
                ),
                "pr_github_actions_pass_streak_count": _manifest_lane_int(
                    ci_streak_manifest, "pr", "github_actions_consecutive_pass_count"
                ),
                "nightly_github_actions_pass_streak_count": _manifest_lane_int(
                    ci_streak_manifest, "nightly", "github_actions_consecutive_pass_count"
                ),
                "pr_missing_consecutive_pass_count": max(0, ci_pass_streak_threshold - pr_streak),
                "nightly_missing_consecutive_pass_count": max(0, ci_pass_streak_threshold - nightly_streak),
                "pr_owner_action": pr_owner_action,
                "nightly_owner_action": nightly_owner_action,
                "pr_claim_boundary": pr_claim_boundary,
                "nightly_claim_boundary": nightly_claim_boundary,
            },
            artifacts={
                "pr_ci": str(ci_pr_path),
                "nightly_ci": str(ci_nightly_path),
                "ci_streak_manifest": str(ci_streak_manifest_path),
                "github_actions_ci_streak_evidence": str(
                    ci_streak_evidence_sources.get("github_actions_evidence_path", "")
                ),
            },
            claim_boundary=" ".join(
                boundary
                for boundary in (pr_claim_boundary, nightly_claim_boundary)
                if boundary
            ),
        )
    )

    m3_checks = by_id["M3"]["checks"]
    strict_ci_checks = {
        "direct_require_ndtha_pass": bool(m3_checks.get("require_ndtha_pass")),
        "direct_require_hip_or_cpu_scope_pass": bool(m3_checks.get("require_hip_pass") or cpu_only_product_mode),
        "strict_ci_require_ndtha_artifact_pass": _reason_pass(ci_ndtha),
        "strict_ci_require_hip_artifact_or_cpu_scope_pass": bool(_reason_pass(ci_hip) or cpu_only_product_mode),
        "cpu_only_product_mode_declared": bool(cpu_only_product_mode),
    }
    strict_ci_blockers = [
        *(["direct_require_ndtha_failed"] if not strict_ci_checks["direct_require_ndtha_pass"] else []),
        *(
            ["direct_require_hip_failed_without_cpu_only_scope"]
            if not strict_ci_checks["direct_require_hip_or_cpu_scope_pass"]
            else []
        ),
        *(
            ["strict_ci_require_ndtha_artifact_failed_or_stale"]
            if not strict_ci_checks["strict_ci_require_ndtha_artifact_pass"]
            else []
        ),
        *(
            ["strict_ci_require_hip_artifact_failed_or_stale"]
            if not strict_ci_checks["strict_ci_require_hip_artifact_or_cpu_scope_pass"]
            else []
        ),
    ]
    rows.append(
        _area(
            "strict_ci",
            "Strict CI",
            ok=not strict_ci_blockers,
            blockers=strict_ci_blockers,
            checks=strict_ci_checks,
            summary={
                "ci_require_ndtha_reason_code": str(ci_ndtha.get("reason_code", "")),
                "ci_require_hip_reason_code": str(ci_hip.get("reason_code", "")),
            },
            artifacts={
                "ci_require_ndtha": str(ci_require_ndtha_path),
                "ci_require_hip": str(ci_require_hip_path),
                "ndtha_long_profile": str(ndtha_long_profile_path),
                "solver_hip_e2e": str(solver_hip_e2e_path),
            },
        )
    )

    max_p95_error, p95_rows, p95_evidence_source = _core_family_p95_evidence(core_family_p95, commercial)
    commercial_checks = _checks(commercial)
    core_checks = {
        "core_depth_milestone_pass": bool(by_id["M2"]["ok"]),
        "commercial_readiness_contract_pass": _reason_pass(commercial),
        "commercial_accuracy_contract_pass": bool(commercial_checks.get("accuracy_pass", False)),
        "core_family_p95_accuracy_report_pass": _reason_pass(core_family_p95),
        "family_p95_error_evidence_present": max_p95_error is not None,
        "family_p95_error_limited_pass": bool(max_p95_error is not None and max_p95_error <= core_p95_error_pct_limit),
    }
    core_blockers = [
        *(["core_depth_milestone_not_green"] if not core_checks["core_depth_milestone_pass"] else []),
        *(["commercial_readiness_contract_not_green"] if not core_checks["commercial_readiness_contract_pass"] else []),
        *(["commercial_accuracy_contract_not_green"] if not core_checks["commercial_accuracy_contract_pass"] else []),
        *(["core_family_p95_accuracy_report_not_green"] if not core_checks["core_family_p95_accuracy_report_pass"] else []),
        *(["family_p95_error_evidence_missing"] if not core_checks["family_p95_error_evidence_present"] else []),
        *(["family_p95_error_gt_5pct"] if max_p95_error is not None and max_p95_error > core_p95_error_pct_limit else []),
    ]
    rows.append(
        _area(
            "core_engine",
            "Core Engine",
            ok=not core_blockers,
            blockers=core_blockers,
            checks=core_checks,
            summary={
                "max_family_p95_error_pct": max_p95_error,
                "max_family_p95_error_pct_limit": core_p95_error_pct_limit,
                "p95_metric_row_count": len(p95_rows),
                "p95_evidence_source": p95_evidence_source,
            },
            artifacts={
                "commercial_readiness": str(commercial_readiness_path),
                "core_family_p95_accuracy": str(core_family_p95_report_path),
                "core_depth": str(by_id["M2"]["artifacts"].get("element_material_breadth_report", "")),
            },
            claim_boundary=(
                "Core p95 uses HF-vs-topk comparison accuracy evidence; high-noise robustness p95 is tracked "
                "separately and is not counted as core engine family p95."
            ),
        )
    )

    residual_checks = _checks(residual)
    residual_summary = _summary(residual)
    ndtha_long_checks = _checks(ndtha_long)
    all_converged = bool(
        residual_checks.get("solver_control_rollup_pass", False)
        and _as_int(residual_summary.get("solver_control_nonconverged_step_total"), -1) == 0
    )
    ndtha_checks = {
        "no_collapse_false_pass": bool(residual_checks.get("ndtha_no_collapse_pass", False)),
        "all_converged_pass": all_converged,
        "long_profile_pass": bool(_reason_pass(ndtha_long) and ndtha_long_checks.get("all_runs_pass", False)),
    }
    ndtha_blockers = [
        *(["ndtha_no_collapse_false_pass_not_proven"] if not ndtha_checks["no_collapse_false_pass"] else []),
        *(["ndtha_all_converged_not_proven"] if not ndtha_checks["all_converged_pass"] else []),
        *(["ndtha_long_profile_not_green"] if not ndtha_checks["long_profile_pass"] else []),
    ]
    rows.append(
        _area(
            "ndtha",
            "NDTHA",
            ok=not ndtha_blockers,
            blockers=ndtha_blockers,
            checks=ndtha_checks,
            summary={
                "solver_control_nonconverged_step_total": _as_int(
                    residual_summary.get("solver_control_nonconverged_step_total"), -1
                ),
                "ndtha_long_profile_reason_code": str(ndtha_long.get("reason_code", "")),
            },
            artifacts={"ndtha_residual": str(ndtha_residual_path), "ndtha_long_profile": str(ndtha_long_profile_path)},
        )
    )

    fallback_rate = _as_float(residual_summary.get("fallback_rate"), 1.0)
    residual_area_checks = {
        "hard_residual_pass": bool(
            residual_checks.get("residual_top_hard_pass", False)
            and residual_checks.get("residual_drift_hard_pass", False)
        ),
        "recommended_residual_pass": bool(residual_checks.get("recommended_residual_pass", False)),
        "fallback_rate_limited_pass": fallback_rate <= max_residual_fallback_rate,
        "fallback_rate_ga_pass": fallback_rate <= ga_residual_fallback_rate,
    }
    residual_area_blockers = [
        *(["hard_residual_not_green"] if not residual_area_checks["hard_residual_pass"] else []),
        *(["recommended_residual_not_green"] if not residual_area_checks["recommended_residual_pass"] else []),
        *(["fallback_rate_gt_5pct"] if not residual_area_checks["fallback_rate_limited_pass"] else []),
    ]
    rows.append(
        _area(
            "residual",
            "Residual",
            ok=not residual_area_blockers,
            blockers=residual_area_blockers,
            checks=residual_area_checks,
            summary={
                "fallback_rate": fallback_rate,
                "limited_fallback_rate_limit": max_residual_fallback_rate,
                "ga_fallback_rate_limit": ga_residual_fallback_rate,
            },
            artifacts={"ndtha_residual": str(ndtha_residual_path)},
        )
    )

    breadth_summary = _summary(measured_breadth)
    measured_cases = _as_int(breadth_summary.get("measured_case_count"), 0)
    benchmark_checks = {
        "paid_pilot_case_threshold_pass": measured_cases >= 20,
        "limited_case_threshold_pass": measured_cases >= min_validation_cases,
        "ga_case_threshold_pass": measured_cases >= ga_validation_cases,
        "benchmark_breadth_milestone_pass": bool(by_id["M4"]["ok"]),
    }
    benchmark_blockers = [
        *(["paid_pilot_case_threshold_lt_20"] if not benchmark_checks["paid_pilot_case_threshold_pass"] else []),
        *(["limited_case_threshold_lt_100"] if not benchmark_checks["limited_case_threshold_pass"] else []),
        *(["benchmark_breadth_milestone_not_green"] if not benchmark_checks["benchmark_breadth_milestone_pass"] else []),
    ]
    rows.append(
        _area(
            "benchmark_breadth",
            "Benchmark Breadth",
            ok=not benchmark_blockers,
            blockers=benchmark_blockers,
            checks=benchmark_checks,
            summary={
                "measured_case_count": measured_cases,
                "limited_validation_case_threshold": min_validation_cases,
                "ga_validation_case_threshold": ga_validation_cases,
            },
            artifacts={"measured_benchmark_breadth": str(measured_benchmark_breadth_path)},
        )
    )

    runtime_budget_exceed_rate = _first_float(
        runtime_memory_budget,
        "p95_runtime_budget_exceed_rate",
        "runtime_budget_exceed_rate",
        "budget_exceed_rate",
    )
    if runtime_budget_exceed_rate is None:
        runtime_budget_exceed_rate = _first_float(
            workstation,
            "p95_runtime_budget_exceed_rate",
            "runtime_budget_exceed_rate",
            "budget_exceed_rate",
        )
    runtime_checks = {
        "strict_runtime_milestone_pass": bool(by_id["M3"]["ok"]),
        "runtime_packaging_pass": _reason_pass(runtime_packaging),
        "workstation_budget_contract_pass": _reason_pass(workstation),
        "runtime_memory_budget_report_pass": _reason_pass(runtime_memory_budget),
        "p95_runtime_budget_exceed_rate_present": runtime_budget_exceed_rate is not None,
        "p95_runtime_budget_exceed_rate_pass": bool(
            runtime_budget_exceed_rate is not None and runtime_budget_exceed_rate <= max_runtime_budget_exceed_rate
        ),
    }
    runtime_blockers = [
        *(["strict_runtime_milestone_not_green"] if not runtime_checks["strict_runtime_milestone_pass"] else []),
        *(["runtime_packaging_not_green"] if not runtime_checks["runtime_packaging_pass"] else []),
        *(["workstation_budget_not_green"] if not runtime_checks["workstation_budget_contract_pass"] else []),
        *(["runtime_memory_budget_report_not_green"] if not runtime_checks["runtime_memory_budget_report_pass"] else []),
        *(["runtime_p95_budget_exceed_rate_evidence_missing"] if not runtime_checks["p95_runtime_budget_exceed_rate_present"] else []),
        *(
            ["runtime_p95_budget_exceed_rate_gt_5pct"]
            if runtime_budget_exceed_rate is not None and runtime_budget_exceed_rate > max_runtime_budget_exceed_rate
            else []
        ),
    ]
    rows.append(
        _area(
            "runtime",
            "Runtime",
            ok=not runtime_blockers,
            blockers=runtime_blockers,
            checks=runtime_checks,
            summary={
                "p95_runtime_budget_exceed_rate": runtime_budget_exceed_rate,
                "max_runtime_budget_exceed_rate": max_runtime_budget_exceed_rate,
            },
            artifacts={
                "runtime_packaging": str(runtime_packaging_path),
                "runtime_memory_budget": str(runtime_memory_budget_path),
                "workstation_budget": str(workstation_budget_path),
            },
            claim_boundary="Existing workstation budgets pass, but PM p95 exceed-rate requires explicit release evidence.",
        )
    )

    memory_budget = workstation.get("performance_budget", {}).get("memory_budget_gib", {})
    oom_count = _first_float(runtime_memory_budget, "oom_count", "runtime_oom_count", "out_of_memory_count")
    if oom_count is None:
        oom_count = _first_float(workstation, "oom_count", "runtime_oom_count", "out_of_memory_count")
    ndtha_peak_vram = _first_float(ndtha_long, "peak_vram_mb_mean")
    memory_checks = {
        "oom_zero_explicit_evidence_present": oom_count is not None,
        "oom_zero_pass": bool(oom_count == 0),
        "runtime_memory_budget_report_pass": _reason_pass(runtime_memory_budget),
        "peak_memory_budget_report_present": bool(isinstance(memory_budget, dict) and memory_budget),
        "ndtha_peak_vram_report_present": ndtha_peak_vram is not None,
    }
    memory_blockers = [
        *(["oom_zero_explicit_evidence_missing"] if not memory_checks["oom_zero_explicit_evidence_present"] else []),
        *(["oom_count_nonzero"] if oom_count is not None and oom_count != 0 else []),
        *(["runtime_memory_budget_report_not_green"] if not memory_checks["runtime_memory_budget_report_pass"] else []),
        *(["peak_memory_budget_report_missing"] if not memory_checks["peak_memory_budget_report_present"] else []),
        *(["ndtha_peak_vram_report_missing"] if not memory_checks["ndtha_peak_vram_report_present"] else []),
    ]
    rows.append(
        _area(
            "memory",
            "Memory",
            ok=not memory_blockers,
            blockers=memory_blockers,
            checks=memory_checks,
            summary={"oom_count": oom_count, "ndtha_peak_vram_mb_mean": ndtha_peak_vram},
            artifacts={
                "runtime_memory_budget": str(runtime_memory_budget_path),
                "workstation_budget": str(workstation_budget_path),
                "ndtha_long_profile": str(ndtha_long_profile_path),
            },
        )
    )

    gpu_checks = {
        "cpu_only_product_mode_declared": bool(cpu_only_product_mode),
        "gpu_strict_pass": bool(m3_checks.get("require_hip_pass") or cpu_only_product_mode),
        "cpu_fallback_release_forbidden_pass": bool(
            m3_checks.get("cpu_fallback_release_forbidden_pass", False)
            and not runtime_policy.get("cpu_solver_fallback_detected", True)
        ),
        "device_residency_target_pass": bool(m3_checks.get("device_residency_target_pass", False) or cpu_only_product_mode),
    }
    gpu_blockers = [
        *(["gpu_strict_failed_without_cpu_only_scope"] if not gpu_checks["gpu_strict_pass"] else []),
        *(["cpu_fallback_allowed_or_detected"] if not gpu_checks["cpu_fallback_release_forbidden_pass"] else []),
        *(["device_residency_target_not_met"] if not gpu_checks["device_residency_target_pass"] else []),
    ]
    rows.append(
        _area(
            "gpu_device",
            "GPU / Device",
            ok=not gpu_blockers,
            blockers=gpu_blockers,
            checks=gpu_checks,
            summary={
                "official_solver_backend": str(runtime_policy.get("official_solver_backend", "")),
                "device_residency_ratio_min": by_id["M3"]["summary"].get("device_residency_ratio_min"),
            },
            artifacts={"runtime_policy": str(runtime_policy_path), "solver_hip_e2e": str(solver_hip_e2e_path)},
        )
    )

    kds_checks = _checks(kds)
    opensees_checks = _checks(opensees)
    opensees_summary = _summary(opensees)
    opensees_roundtrip = bool(
        opensees_checks.get("roundtrip_pass", False)
        or opensees_checks.get("roundtrip_trace_pass", False)
        or _as_float(opensees_summary.get("roundtrip_exact_entry_row_coverage_min"), 0.0) >= 1.0
        or _reason_pass(opensees_roundtrip_report)
    )
    interop_checks = {
        "midas_interop_pass": _reason_pass(midas_interop),
        "midas_native_roundtrip_pass": _reason_pass(midas_native),
        "midas_exact_roundtrip_pass": _reason_pass(midas_exact),
        "kds_full_crosswalk_pass": bool(_reason_pass(kds) and kds_checks.get("full_crosswalk_pass", False)),
        "opensees_trace_pass": _reason_pass(opensees),
        "opensees_roundtrip_trace_pass": opensees_roundtrip,
        "opensees_roundtrip_trace_report_pass": _reason_pass(opensees_roundtrip_report),
    }
    interop_blockers = [
        *(["midas_interop_not_green"] if not interop_checks["midas_interop_pass"] else []),
        *(["midas_native_roundtrip_not_green"] if not interop_checks["midas_native_roundtrip_pass"] else []),
        *(["midas_exact_roundtrip_not_green"] if not interop_checks["midas_exact_roundtrip_pass"] else []),
        *(["kds_full_crosswalk_not_green"] if not interop_checks["kds_full_crosswalk_pass"] else []),
        *(["opensees_trace_not_green"] if not interop_checks["opensees_trace_pass"] else []),
        *(["opensees_roundtrip_trace_evidence_missing"] if not interop_checks["opensees_roundtrip_trace_pass"] else []),
    ]
    rows.append(
        _area(
            "interop",
            "Interop",
            ok=not interop_blockers,
            blockers=interop_blockers,
            checks=interop_checks,
            summary={
                "midas_exact_case_ratio": _summary(midas_exact).get("exact_case_ratio"),
                "opensees_schema_version": str(opensees.get("schema_version", "")),
            },
            artifacts={
                "midas_interop": str(midas_interop_path),
                "midas_native_roundtrip": str(midas_native_roundtrip_path),
                "midas_exact_roundtrip": str(midas_exact_roundtrip_path),
                "midas_kds_geometry": str(midas_kds_geometry_path),
                "opensees_topology": str(opensees_topology_path),
                "opensees_roundtrip_trace": str(opensees_roundtrip_trace_path),
            },
            claim_boundary="OpenSees evidence is a topology canonicalization/reload trace, not a full solver execution roundtrip.",
        )
    )

    workflow_blob = json.dumps(workflow, ensure_ascii=False, sort_keys=True).lower()
    report_checks = {
        "commercial_packaging_milestone_pass": bool(by_id["M5"]["ok"]),
        "reviewer_package_auto_pass": _reason_pass(workflow),
        "repro_command_present": bool("command" in workflow_blob or "repro" in workflow_blob),
        "reproducibility_lock_pass": _reason_pass(repro),
    }
    report_blockers = [
        *(["commercial_packaging_milestone_not_green"] if not report_checks["commercial_packaging_milestone_pass"] else []),
        *(["reviewer_package_auto_not_green"] if not report_checks["reviewer_package_auto_pass"] else []),
        *(["repro_command_missing_from_report_evidence"] if not report_checks["repro_command_present"] else []),
        *(["reproducibility_lock_not_green"] if not report_checks["reproducibility_lock_pass"] else []),
    ]
    rows.append(
        _area(
            "report",
            "Report",
            ok=not report_blockers,
            blockers=report_blockers,
            checks=report_checks,
            summary={"release_registry_signed": by_id["M5"]["checks"].get("signed_release_registry_pass")},
            artifacts={
                "workflow_productization": str(workflow_productization_path),
                "release_registry": str(release_registry_path),
                "reproducibility_lock": str(repro_lock_path),
            },
        )
    )

    viewer_quality_summary = _summary(viewer_quality)
    ux_release_summary = _summary(ux_release)
    sample_completion_minutes = _first_float(
        ux_release,
        "sample_completion_minutes",
        "new_user_sample_completion_minutes",
        "sample_project_completion_minutes",
        "new_user_sample_project_completion_minutes",
    )
    if sample_completion_minutes is None:
        sample_completion_minutes = _first_float(
            viewer_quality,
            "new_user_sample_completion_minutes",
            "sample_project_completion_minutes",
            "new_user_sample_project_completion_minutes",
        )
    ux_release_available = _reason_pass(ux_release)
    blocking_review_item_count = _as_int(
        ux_release_summary.get("blocking_review_item_count"),
        _as_int(viewer_quality_summary.get("review_item_count"), 1),
    )
    ux_checks = {
        "viewer_quality_gate_pass": _reason_pass(viewer_quality),
        "ux_release_readiness_report_pass": ux_release_available,
        "blocking_review_queue_zero_pass": blocking_review_item_count == 0,
        "new_user_sample_30min_evidence_present": sample_completion_minutes is not None,
        "new_user_sample_30min_pass": bool(sample_completion_minutes is not None and sample_completion_minutes <= 30.0),
        "viewer_performance_static_budget_pass": _reason_pass(viewer_perf),
    }
    ux_blockers = [
        *(["viewer_quality_gate_not_green"] if not ux_checks["viewer_quality_gate_pass"] else []),
        *(["ux_release_readiness_report_missing_or_failed"] if not ux_checks["ux_release_readiness_report_pass"] else []),
        *(["viewer_blocking_review_queue_not_empty"] if not ux_checks["blocking_review_queue_zero_pass"] else []),
        *(["new_user_30min_sample_evidence_missing"] if not ux_checks["new_user_sample_30min_evidence_present"] else []),
        *(
            ["new_user_sample_gt_30min"]
            if sample_completion_minutes is not None and sample_completion_minutes > 30.0
            else []
        ),
        *(["viewer_performance_static_budget_not_green"] if not ux_checks["viewer_performance_static_budget_pass"] else []),
    ]
    rows.append(
        _area(
            "ux",
            "UX",
            ok=not ux_blockers,
            blockers=ux_blockers,
            checks=ux_checks,
            summary={
                "sample_completion_minutes": sample_completion_minutes,
                "viewer_review_item_count": _as_int(viewer_quality_summary.get("review_item_count"), -1),
                "blocking_review_item_count": blocking_review_item_count,
                "ux_evidence_source": "ux_release_readiness_report" if ux_release else "viewer_quality_fallback",
            },
            artifacts={
                "viewer_quality": str(viewer_quality_path),
                "viewer_performance_budget": str(viewer_performance_budget_path),
                "ux_release_readiness": str(ux_release_readiness_path),
            },
            claim_boundary=(
                "UX sample completion is currently automated browser rehearsal evidence; human new-user "
                "usability observation remains a GA-strength evidence upgrade."
            ),
        )
    )

    runtime_packaging_checks = _checks(runtime_packaging)
    support_checks = _checks(support)
    support_optional_sections = _as_dict(support.get("optional_sections"))
    support_area_checks = {
        "known_issue_or_limitation_register_present": limitation_manual_path.exists(),
        "pm_blocker_action_register_in_failure_bundle": bool(
            support_optional_sections.get("pm_release_blocker_action_register")
        ),
        "license_status_intake_packet_in_failure_bundle": bool(
            support_optional_sections.get("license_status_intake_packet")
        ),
        "frontend_dependency_audit_in_failure_bundle": bool(
            support_optional_sections.get("frontend_dependency_audit_report")
        ),
        "failure_bundle_export_pass": bool(
            _reason_pass(support)
            and support_checks.get("redaction_self_test_pass", False)
            and support_checks.get("bundle_roundtrip_test_pass", False)
        ),
        "rollback_runbook_present": bool(runtime_packaging_checks.get("rollback_runbook_present", False)),
    }
    support_blockers = [
        *(
            ["known_issue_or_limitation_register_missing"]
            if not support_area_checks["known_issue_or_limitation_register_present"]
            else []
        ),
        *(
            ["pm_blocker_action_register_missing_from_failure_bundle"]
            if not support_area_checks["pm_blocker_action_register_in_failure_bundle"]
            else []
        ),
        *(
            ["license_status_intake_packet_missing_from_failure_bundle"]
            if not support_area_checks["license_status_intake_packet_in_failure_bundle"]
            else []
        ),
        *(
            ["frontend_dependency_audit_missing_from_failure_bundle"]
            if not support_area_checks["frontend_dependency_audit_in_failure_bundle"]
            else []
        ),
        *(["failure_bundle_export_not_green"] if not support_area_checks["failure_bundle_export_pass"] else []),
        *(["rollback_runbook_missing"] if not support_area_checks["rollback_runbook_present"] else []),
    ]
    rows.append(
        _area(
            "support",
            "Support",
            ok=not support_blockers,
            blockers=support_blockers,
            checks=support_area_checks,
            summary={
                "support_bundle_missing_required_count": support_checks.get("missing_required_count"),
                "pm_release_blocker_action_register": str(
                    support_optional_sections.get("pm_release_blocker_action_register", "")
                ),
                "license_status_intake_packet": str(
                    support_optional_sections.get("license_status_intake_packet", "")
                ),
                "frontend_dependency_audit_report": str(
                    support_optional_sections.get("frontend_dependency_audit_report", "")
                ),
            },
            artifacts={
                "support_bundle": str(support_bundle_path),
                "runtime_packaging": str(runtime_packaging_path),
                "limitation_manual": str(limitation_manual_path),
            },
        )
    )

    security_text = _read_text_or_empty(security_runbook_path).lower()
    license_state = str(license_status.get("status", "")).strip().lower()
    license_closure_summary = _summary(license_status_closure)
    license_closure_blockers = license_status_closure.get("blockers", [])
    if not isinstance(license_closure_blockers, list):
        license_closure_blockers = []
    frontend_dependency_audit_summary = _summary(frontend_dependency_audit)
    frontend_dependency_audit_checks = _checks(frontend_dependency_audit)
    security_checks = {
        "secrets_negative_start_or_no_default_secret_pass": bool(
            "no production default secret" in security_text and "negative" in security_text
        ),
        "license_status_configured_pass": _reason_pass(license_status_closure),
        "license_status_closure_report_present": license_status_closure_path.exists(),
        "sbom_present_pass": bool(sbom.get("component_count", 0)),
        "frontend_dependency_audit_report_present": frontend_dependency_audit_path.exists(),
        "frontend_dependency_audit_pass": _reason_pass(frontend_dependency_audit),
        "frontend_dependency_high_or_critical_zero_pass": bool(
            frontend_dependency_audit_checks.get("dependency_high_or_critical_zero_pass", False)
        ),
        "repro_build_pass": _reason_pass(repro),
    }
    security_blockers = [
        *(
            ["secrets_negative_start_or_no_default_secret_evidence_missing"]
            if not security_checks["secrets_negative_start_or_no_default_secret_pass"]
            else []
        ),
        *(["license_status_not_configured"] if not security_checks["license_status_configured_pass"] else []),
        *(["license_status_closure_report_missing"] if not security_checks["license_status_closure_report_present"] else []),
        *(["sbom_missing"] if not security_checks["sbom_present_pass"] else []),
        *(
            ["frontend_dependency_audit_missing_or_failed"]
            if not security_checks["frontend_dependency_audit_pass"]
            else []
        ),
        *(["repro_build_not_green"] if not security_checks["repro_build_pass"] else []),
    ]
    rows.append(
        _area(
            "security",
            "Security",
            ok=not security_blockers,
            blockers=security_blockers,
            checks=security_checks,
            summary={
                "license_status": str(license_closure_summary.get("status", license_state or "missing")),
                "license_status_closure_blockers": license_closure_blockers,
                "license_status_owner_action": str(license_closure_summary.get("owner_action", "")),
                "license_status_template_path": str(license_closure_summary.get("template_path", "")),
                "sbom_component_count": _as_int(sbom.get("component_count"), 0),
                "frontend_dependency_vulnerability_total": _as_int(
                    frontend_dependency_audit_summary.get("vulnerability_total"), 0
                ),
                "frontend_dependency_high_or_critical_vulnerability_count": _as_int(
                    frontend_dependency_audit_summary.get("high_or_critical_vulnerability_count"), 0
                ),
            },
            artifacts={
                "security_runbook": str(security_runbook_path),
                "license_status": str(license_status_path),
                "license_status_closure": str(license_status_closure_path),
                "runtime_sbom": str(runtime_sbom_path),
                "frontend_dependency_audit": str(frontend_dependency_audit_path),
                "reproducibility_lock": str(repro_lock_path),
            },
            claim_boundary=(
                "Security area is release-gate evidence only; live deployment hardening remains governed "
                "by the runbook."
            ),
        )
    )

    return rows


def build_report(
    *,
    ndtha_residual: Path = DEFAULT_NDTHA_RESIDUAL,
    element_material_breadth: Path = DEFAULT_ELEMENT_MATERIAL_BREADTH,
    ndtha_long_profile: Path = DEFAULT_NDTHA_LONG_PROFILE,
    solver_hip_e2e: Path = DEFAULT_SOLVER_HIP_E2E,
    runtime_policy: Path = DEFAULT_RUNTIME_POLICY,
    ci_pr: Path = DEFAULT_CI_PR,
    ci_nightly: Path = DEFAULT_CI_NIGHTLY,
    ci_streak_manifest: Path = DEFAULT_CI_STREAK_MANIFEST,
    ci_require_ndtha: Path = DEFAULT_CI_REQUIRE_NDTHA,
    ci_require_hip: Path = DEFAULT_CI_REQUIRE_HIP,
    zero_copy_strict: Path = DEFAULT_ZERO_COPY_STRICT,
    measured_benchmark_breadth: Path = DEFAULT_MEASURED_BREADTH,
    worst_case_report: Path = DEFAULT_WORST_CASE_REPORT,
    workflow_productization: Path = DEFAULT_WORKFLOW_PRODUCTIZATION,
    release_registry: Path = DEFAULT_RELEASE_REGISTRY,
    support_bundle: Path = DEFAULT_SUPPORT_BUNDLE,
    commercial_readiness: Path = DEFAULT_COMMERCIAL_READINESS,
    core_family_p95_report: Path = DEFAULT_CORE_FAMILY_P95_REPORT,
    runtime_packaging: Path = DEFAULT_RUNTIME_PACKAGING,
    runtime_memory_budget: Path = DEFAULT_RUNTIME_MEMORY_BUDGET,
    runtime_sbom: Path = DEFAULT_RUNTIME_SBOM,
    frontend_dependency_audit: Path = DEFAULT_FRONTEND_DEPENDENCY_AUDIT,
    repro_lock: Path = DEFAULT_REPRO_LOCK,
    workstation_budget: Path = DEFAULT_WORKSTATION_BUDGET,
    viewer_performance_budget: Path = DEFAULT_VIEWER_PERFORMANCE_BUDGET,
    midas_interop: Path = DEFAULT_MIDAS_INTEROP,
    midas_native_roundtrip: Path = DEFAULT_MIDAS_NATIVE_ROUNDTRIP,
    midas_exact_roundtrip: Path = DEFAULT_MIDAS_EXACT_ROUNDTRIP,
    midas_kds_geometry: Path = DEFAULT_MIDAS_KDS_GEOMETRY,
    opensees_topology: Path = DEFAULT_OPENSEES_TOPOLOGY,
    opensees_roundtrip_trace: Path = DEFAULT_OPENSEES_ROUNDTRIP_TRACE,
    viewer_quality: Path = DEFAULT_VIEWER_QUALITY,
    ux_release_readiness: Path = DEFAULT_UX_RELEASE_READINESS,
    security_runbook: Path = DEFAULT_SECURITY_RUNBOOK,
    license_status: Path = DEFAULT_LICENSE_STATUS,
    license_status_closure: Path = DEFAULT_LICENSE_STATUS_CLOSURE,
    ai_orchestration_preflight: Path = DEFAULT_AI_ORCHESTRATION_PREFLIGHT,
    validation_manual: Path = DEFAULT_VALIDATION_MANUAL,
    limitation_manual: Path = DEFAULT_LIMITATION_MANUAL,
    cpu_only_product_mode: bool = False,
    ci_pass_streak_threshold: int = 30,
    core_p95_error_pct_limit: float = 5.0,
    max_residual_fallback_rate: float = 0.05,
    ga_residual_fallback_rate: float = 0.01,
    min_contact_material_cases: int = 10,
    min_device_residency: float = 0.99,
    max_host_copy_share: float = 0.05,
    min_validation_cases: int = 100,
    min_structure_families: int = 5,
    ga_validation_cases: int = 300,
    max_runtime_budget_exceed_rate: float = 0.05,
) -> dict[str, Any]:
    milestones = [
        _residual_milestone(ndtha_residual, max_fallback_rate=max_residual_fallback_rate),
        _core_depth_milestone(element_material_breadth, min_contact_material_cases=min_contact_material_cases),
        _runtime_milestone(
            ndtha_long_profile_path=ndtha_long_profile,
            solver_hip_e2e_path=solver_hip_e2e,
            runtime_policy_path=runtime_policy,
            ci_require_ndtha_path=ci_require_ndtha,
            zero_copy_strict_path=zero_copy_strict,
            min_device_residency=min_device_residency,
            max_host_copy_share=max_host_copy_share,
            cpu_only_product_mode=cpu_only_product_mode,
        ),
        _benchmark_milestone(
            measured_benchmark_breadth,
            worst_case_report_path=worst_case_report,
            min_validation_cases=min_validation_cases,
            min_structure_families=min_structure_families,
        ),
        _packaging_milestone(
            workflow_path=workflow_productization,
            release_registry_path=release_registry,
            support_bundle_path=support_bundle,
            validation_manual_path=validation_manual,
            limitation_manual_path=limitation_manual,
        ),
    ]

    by_id = {row["milestone"]: row for row in milestones}
    residual_basic_ok = bool(by_id["M1"]["checks"]["ndtha_residual_contract_pass"])
    core_basic_ok = bool(by_id["M2"]["checks"]["element_material_breadth_contract_pass"])
    runtime_ok = bool(by_id["M3"]["ok"])
    packaging_ok = bool(by_id["M5"]["ok"])
    measured_cases = _as_int(by_id["M4"]["summary"].get("measured_case_count"), 0)
    limited_ready = all(bool(row["ok"]) for row in milestones)
    paid_pilot_candidate = bool(
        residual_basic_ok
        and core_basic_ok
        and runtime_ok
        and packaging_ok
        and measured_cases >= 20
    )
    ga_enterprise_ready = False
    blockers = [
        f"{row['milestone']}::{blocker}"
        for row in milestones
        for blocker in row.get("blockers", [])
    ]
    release_area_matrix = _build_release_area_matrix(
        milestones=milestones,
        ci_pr_path=ci_pr,
        ci_nightly_path=ci_nightly,
        ci_streak_manifest_path=ci_streak_manifest,
        ci_require_ndtha_path=ci_require_ndtha,
        ci_require_hip_path=ci_require_hip,
        commercial_readiness_path=commercial_readiness,
        core_family_p95_report_path=core_family_p95_report,
        ndtha_residual_path=ndtha_residual,
        ndtha_long_profile_path=ndtha_long_profile,
        solver_hip_e2e_path=solver_hip_e2e,
        runtime_policy_path=runtime_policy,
        measured_benchmark_breadth_path=measured_benchmark_breadth,
        workflow_productization_path=workflow_productization,
        release_registry_path=release_registry,
        support_bundle_path=support_bundle,
        runtime_packaging_path=runtime_packaging,
        runtime_memory_budget_path=runtime_memory_budget,
        runtime_sbom_path=runtime_sbom,
        frontend_dependency_audit_path=frontend_dependency_audit,
        repro_lock_path=repro_lock,
        workstation_budget_path=workstation_budget,
        viewer_performance_budget_path=viewer_performance_budget,
        midas_interop_path=midas_interop,
        midas_native_roundtrip_path=midas_native_roundtrip,
        midas_exact_roundtrip_path=midas_exact_roundtrip,
        midas_kds_geometry_path=midas_kds_geometry,
        opensees_topology_path=opensees_topology,
        opensees_roundtrip_trace_path=opensees_roundtrip_trace,
        viewer_quality_path=viewer_quality,
        ux_release_readiness_path=ux_release_readiness,
        security_runbook_path=security_runbook,
        license_status_path=license_status,
        license_status_closure_path=license_status_closure,
        validation_manual_path=validation_manual,
        limitation_manual_path=limitation_manual,
        cpu_only_product_mode=cpu_only_product_mode,
        ci_pass_streak_threshold=ci_pass_streak_threshold,
        core_p95_error_pct_limit=core_p95_error_pct_limit,
        max_residual_fallback_rate=max_residual_fallback_rate,
        ga_residual_fallback_rate=ga_residual_fallback_rate,
        min_validation_cases=min_validation_cases,
        ga_validation_cases=ga_validation_cases,
        max_runtime_budget_exceed_rate=max_runtime_budget_exceed_rate,
    )
    release_area_blockers = _release_area_blockers(release_area_matrix)
    release_area_ready = all(bool(row["ok"]) for row in release_area_matrix)
    full_release_gate_ready = bool(limited_ready and release_area_ready)
    ga_blockers = [
        "independent_vv_missing",
        "family_validation_manual_signoff_missing",
        "customer_audit_failure_bundle_sla_missing",
        *(["ga_validation_case_count_lt_300"] if measured_cases < ga_validation_cases else []),
        *release_area_blockers,
    ]
    ai_orchestration = _load_json(ai_orchestration_preflight)
    ai_orchestration_summary = _summary(ai_orchestration)
    if full_release_gate_ready:
        recommended_scope = "Limited Commercial release candidate"
    elif limited_ready:
        recommended_scope = (
            "Limited milestone evidence is green, but the broader PM release-area gate is still blocked; "
            "keep commercial use constrained until release-area blockers are closed."
        )
    elif paid_pilot_candidate:
        recommended_scope = (
            "Paid pilot / constrained customer PoC only: review-assist, specified structure families, "
            "specified workflow, and engine/reviewer evidence package required."
        )
    else:
        recommended_scope = "Release blocked until core PM gates have green evidence."

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": limited_ready,
        "milestone_gate_pass": limited_ready,
        "release_area_gate_ready": release_area_ready,
        "full_release_gate_ready": full_release_gate_ready,
        "paid_pilot_candidate": paid_pilot_candidate,
        "limited_commercial_ready": limited_ready,
        "ga_enterprise_ready": ga_enterprise_ready,
        "recommended_scope": recommended_scope,
        "summary_line": (
            f"PM release gate: {'LIMITED_READY' if limited_ready else 'BLOCKED'} | "
            f"release_areas={'READY' if release_area_ready else 'BLOCKED'} | "
            f"paid_pilot_candidate={paid_pilot_candidate} | "
            f"milestones={sum(1 for row in milestones if row['ok'])}/{len(milestones)} | "
            f"release_areas_green={sum(1 for row in release_area_matrix if row['ok'])}/{len(release_area_matrix)} | "
            f"measured_cases={measured_cases}"
        ),
        "milestones": milestones,
        "blockers": blockers,
        "release_area_matrix": release_area_matrix,
        "release_area_blockers": release_area_blockers,
        "full_release_blockers": [*blockers, *release_area_blockers],
        "implementation_orchestration": {
            "cursor_opencode_worker_preflight_pass": _reason_pass(ai_orchestration),
            "artifacts": {"ai_orchestration_preflight": str(ai_orchestration_preflight)},
            "summary": {
                "cursor_worker_cli": str(ai_orchestration_summary.get("cursor_worker_cli", "")),
                "opencode_worker_cli": str(ai_orchestration_summary.get("opencode_worker_cli", "")),
                "opencode_version": str(ai_orchestration_summary.get("opencode_version", "")),
            },
            "claim_boundary": (
                "Cursor/OpenCode are implementation workers for scoped slices; Codex still owns PM gate "
                "review, verification, and final acceptance."
            ),
        },
        "release_tiers": {
            "paid_pilot": paid_pilot_candidate,
            "limited_commercial_milestone_ready": limited_ready,
            "limited_commercial_full_gate_ready": full_release_gate_ready,
            "ga_enterprise": ga_enterprise_ready,
            "ga_validation_case_threshold": ga_validation_cases,
            "ga_validation_case_threshold_met": measured_cases >= ga_validation_cases,
            "ga_enterprise_blockers": ga_blockers,
            "ga_enterprise_note": (
                "GA still requires independent V&V, family validation manuals, signed release registry, "
                "customer audit/failure bundles, and support SLA; this report only verifies local evidence inputs."
            ),
        },
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PM Release Gate",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `recommended_scope`: {payload['recommended_scope']}",
        f"- `paid_pilot_candidate`: `{payload['paid_pilot_candidate']}`",
        f"- `limited_commercial_ready`: `{payload['limited_commercial_ready']}`",
        f"- `release_area_gate_ready`: `{payload['release_area_gate_ready']}`",
        f"- `full_release_gate_ready`: `{payload['full_release_gate_ready']}`",
        f"- `ga_enterprise_ready`: `{payload['ga_enterprise_ready']}`",
        f"- `cursor_opencode_worker_preflight_pass`: "
        f"`{payload['implementation_orchestration']['cursor_opencode_worker_preflight_pass']}`",
        "",
        "| Milestone | Status | Blockers |",
        "|---|---|---|",
    ]
    for row in payload["milestones"]:
        lines.append(
            f"| {row['milestone']} {row['title']} | {row['status']} | "
            f"{', '.join(row.get('blockers', [])) or 'none'} |"
        )
    lines.extend(["", "| Release Area | Status | Blockers |", "|---|---|---|"])
    for row in payload["release_area_matrix"]:
        lines.append(
            f"| {row['area']} {row['title']} | {row['status']} | "
            f"{', '.join(row.get('blockers', [])) or 'none'} |"
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ndtha-residual", type=Path, default=DEFAULT_NDTHA_RESIDUAL)
    parser.add_argument("--element-material-breadth", type=Path, default=DEFAULT_ELEMENT_MATERIAL_BREADTH)
    parser.add_argument("--ndtha-long-profile", type=Path, default=DEFAULT_NDTHA_LONG_PROFILE)
    parser.add_argument("--solver-hip-e2e", type=Path, default=DEFAULT_SOLVER_HIP_E2E)
    parser.add_argument("--runtime-policy", type=Path, default=DEFAULT_RUNTIME_POLICY)
    parser.add_argument("--ci-pr", type=Path, default=DEFAULT_CI_PR)
    parser.add_argument("--ci-nightly", type=Path, default=DEFAULT_CI_NIGHTLY)
    parser.add_argument("--ci-streak-manifest", type=Path, default=DEFAULT_CI_STREAK_MANIFEST)
    parser.add_argument("--ci-require-ndtha", type=Path, default=DEFAULT_CI_REQUIRE_NDTHA)
    parser.add_argument("--ci-require-hip", type=Path, default=DEFAULT_CI_REQUIRE_HIP)
    parser.add_argument("--zero-copy-strict", type=Path, default=DEFAULT_ZERO_COPY_STRICT)
    parser.add_argument("--measured-benchmark-breadth", type=Path, default=DEFAULT_MEASURED_BREADTH)
    parser.add_argument("--worst-case-report", type=Path, default=DEFAULT_WORST_CASE_REPORT)
    parser.add_argument("--workflow-productization", type=Path, default=DEFAULT_WORKFLOW_PRODUCTIZATION)
    parser.add_argument("--release-registry", type=Path, default=DEFAULT_RELEASE_REGISTRY)
    parser.add_argument("--support-bundle", type=Path, default=DEFAULT_SUPPORT_BUNDLE)
    parser.add_argument("--commercial-readiness", type=Path, default=DEFAULT_COMMERCIAL_READINESS)
    parser.add_argument("--core-family-p95-report", type=Path, default=DEFAULT_CORE_FAMILY_P95_REPORT)
    parser.add_argument("--runtime-packaging", type=Path, default=DEFAULT_RUNTIME_PACKAGING)
    parser.add_argument("--runtime-memory-budget", type=Path, default=DEFAULT_RUNTIME_MEMORY_BUDGET)
    parser.add_argument("--runtime-sbom", type=Path, default=DEFAULT_RUNTIME_SBOM)
    parser.add_argument("--frontend-dependency-audit", type=Path, default=DEFAULT_FRONTEND_DEPENDENCY_AUDIT)
    parser.add_argument("--repro-lock", type=Path, default=DEFAULT_REPRO_LOCK)
    parser.add_argument("--workstation-budget", type=Path, default=DEFAULT_WORKSTATION_BUDGET)
    parser.add_argument("--viewer-performance-budget", type=Path, default=DEFAULT_VIEWER_PERFORMANCE_BUDGET)
    parser.add_argument("--midas-interop", type=Path, default=DEFAULT_MIDAS_INTEROP)
    parser.add_argument("--midas-native-roundtrip", type=Path, default=DEFAULT_MIDAS_NATIVE_ROUNDTRIP)
    parser.add_argument("--midas-exact-roundtrip", type=Path, default=DEFAULT_MIDAS_EXACT_ROUNDTRIP)
    parser.add_argument("--midas-kds-geometry", type=Path, default=DEFAULT_MIDAS_KDS_GEOMETRY)
    parser.add_argument("--opensees-topology", type=Path, default=DEFAULT_OPENSEES_TOPOLOGY)
    parser.add_argument("--opensees-roundtrip-trace", type=Path, default=DEFAULT_OPENSEES_ROUNDTRIP_TRACE)
    parser.add_argument("--viewer-quality", type=Path, default=DEFAULT_VIEWER_QUALITY)
    parser.add_argument("--ux-release-readiness", type=Path, default=DEFAULT_UX_RELEASE_READINESS)
    parser.add_argument("--security-runbook", type=Path, default=DEFAULT_SECURITY_RUNBOOK)
    parser.add_argument("--license-status", type=Path, default=DEFAULT_LICENSE_STATUS)
    parser.add_argument("--license-status-closure", type=Path, default=DEFAULT_LICENSE_STATUS_CLOSURE)
    parser.add_argument("--ai-orchestration-preflight", type=Path, default=DEFAULT_AI_ORCHESTRATION_PREFLIGHT)
    parser.add_argument("--validation-manual", type=Path, default=DEFAULT_VALIDATION_MANUAL)
    parser.add_argument("--limitation-manual", type=Path, default=DEFAULT_LIMITATION_MANUAL)
    parser.add_argument("--cpu-only-product-mode", action="store_true")
    parser.add_argument("--ci-pass-streak-threshold", type=int, default=30)
    parser.add_argument("--core-p95-error-pct-limit", type=float, default=5.0)
    parser.add_argument("--max-residual-fallback-rate", type=float, default=0.05)
    parser.add_argument("--ga-residual-fallback-rate", type=float, default=0.01)
    parser.add_argument("--min-contact-material-cases", type=int, default=10)
    parser.add_argument("--min-device-residency", type=float, default=0.99)
    parser.add_argument("--max-host-copy-share", type=float, default=0.05)
    parser.add_argument("--min-validation-cases", type=int, default=100)
    parser.add_argument("--min-structure-families", type=int, default=5)
    parser.add_argument("--ga-validation-cases", type=int, default=300)
    parser.add_argument("--max-runtime-budget-exceed-rate", type=float, default=0.05)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(
        ndtha_residual=args.ndtha_residual,
        element_material_breadth=args.element_material_breadth,
        ndtha_long_profile=args.ndtha_long_profile,
        solver_hip_e2e=args.solver_hip_e2e,
        runtime_policy=args.runtime_policy,
        ci_pr=args.ci_pr,
        ci_nightly=args.ci_nightly,
        ci_streak_manifest=args.ci_streak_manifest,
        ci_require_ndtha=args.ci_require_ndtha,
        ci_require_hip=args.ci_require_hip,
        zero_copy_strict=args.zero_copy_strict,
        measured_benchmark_breadth=args.measured_benchmark_breadth,
        worst_case_report=args.worst_case_report,
        workflow_productization=args.workflow_productization,
        release_registry=args.release_registry,
        support_bundle=args.support_bundle,
        commercial_readiness=args.commercial_readiness,
        core_family_p95_report=args.core_family_p95_report,
        runtime_packaging=args.runtime_packaging,
        runtime_memory_budget=args.runtime_memory_budget,
        runtime_sbom=args.runtime_sbom,
        frontend_dependency_audit=args.frontend_dependency_audit,
        repro_lock=args.repro_lock,
        workstation_budget=args.workstation_budget,
        viewer_performance_budget=args.viewer_performance_budget,
        midas_interop=args.midas_interop,
        midas_native_roundtrip=args.midas_native_roundtrip,
        midas_exact_roundtrip=args.midas_exact_roundtrip,
        midas_kds_geometry=args.midas_kds_geometry,
        opensees_topology=args.opensees_topology,
        opensees_roundtrip_trace=args.opensees_roundtrip_trace,
        viewer_quality=args.viewer_quality,
        ux_release_readiness=args.ux_release_readiness,
        security_runbook=args.security_runbook,
        license_status=args.license_status,
        license_status_closure=args.license_status_closure,
        ai_orchestration_preflight=args.ai_orchestration_preflight,
        validation_manual=args.validation_manual,
        limitation_manual=args.limitation_manual,
        cpu_only_product_mode=args.cpu_only_product_mode,
        ci_pass_streak_threshold=args.ci_pass_streak_threshold,
        core_p95_error_pct_limit=args.core_p95_error_pct_limit,
        max_residual_fallback_rate=args.max_residual_fallback_rate,
        ga_residual_fallback_rate=args.ga_residual_fallback_rate,
        min_contact_material_cases=args.min_contact_material_cases,
        min_device_residency=args.min_device_residency,
        max_host_copy_share=args.max_host_copy_share,
        min_validation_cases=args.min_validation_cases,
        min_structure_families=args.min_structure_families,
        ga_validation_cases=args.ga_validation_cases,
        max_runtime_budget_exceed_rate=args.max_runtime_budget_exceed_rate,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        out_md = args.out_md
    elif args.out == DEFAULT_OUT:
        out_md = DEFAULT_OUT_MD
    else:
        out_md = args.out.with_suffix(".md")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
