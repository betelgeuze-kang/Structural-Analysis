#!/usr/bin/env python3
"""Aggregate PM release milestones into a single evidence-backed gate report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import check_github_development_sync_preflight  # noqa: E402


SCHEMA_VERSION = "pm-release-gate-report.v1"
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"

DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/pm_release_gate_report.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_NDTHA_RESIDUAL = Path("implementation/phase1/release_evidence/productization/ndtha_residual_gate_report.json")
DEFAULT_RESIDUAL_LEVEL3_STATUS = Path("implementation/phase1/release_evidence/productization/residual_level3_status.json")
DEFAULT_ELEMENT_MATERIAL_BREADTH = Path("implementation/phase1/element_material_breadth_gate_report.json")
DEFAULT_NDTHA_LONG_PROFILE = Path("implementation/phase1/ndtha_long_profile_report.json")
DEFAULT_SOLVER_HIP_E2E = Path("implementation/phase1/solver_hip_e2e_contract_report.json")
DEFAULT_RUNTIME_POLICY = Path("implementation/phase1/release_evidence/productization/solver_runtime_backend_policy.json")
DEFAULT_CI_PR = Path("implementation/phase1/ci_gate_report.pr.json")
DEFAULT_CI_NIGHTLY = Path("implementation/phase1/ci_gate_report.nightly.json")
DEFAULT_CI_STREAK_MANIFEST = Path("implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json")
DEFAULT_CI_STREAK_INTAKE_PACKET = Path(
    "implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json"
)
DEFAULT_CI_REQUIRE_NDTHA = Path("implementation/phase1/release_evidence/productization/pm_strict_ci_require_ndtha_report.json")
DEFAULT_CI_REQUIRE_HIP = Path("implementation/phase1/release_evidence/productization/pm_strict_ci_require_hip_report.json")
DEFAULT_ZERO_COPY_STRICT = Path("implementation/phase1/zero_copy_real_probe_report_strict.json")
DEFAULT_MEASURED_BREADTH = Path(
    "implementation/phase1/release_evidence/productization/measured_benchmark_breadth_report.json"
)
DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_READINESS = Path(
    "implementation/phase1/release/external_benchmark_submission_readiness.json"
)
DEFAULT_PUBLIC_BENCHMARK_SOURCE_OF_TRUTH = Path(
    "implementation/phase1/release_evidence/productization/public_benchmark_source_of_truth.json"
)
DEFAULT_EVIDENCE_SURFACE_DIR = Path("implementation/phase1/release_evidence/surface")
DEFAULT_WORST_CASE_REPORT = Path("implementation/phase1/release_evidence/productization/worst_case_report.json")
DEFAULT_WORKFLOW_PRODUCTIZATION = Path("implementation/phase1/workflow_productization_gate_report.json")
DEFAULT_RELEASE_REGISTRY = Path("implementation/phase1/release/release_registry.json")
DEFAULT_SUPPORT_BUNDLE = Path("implementation/phase1/support_bundle_manifest.json")
DEFAULT_PM_RELEASE_BLOCKER_ACTION_REGISTER = Path(
    "implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json"
)
DEFAULT_PM_RELEASE_BLOCKER_CLOSURE_BOARD = Path(
    "implementation/phase1/release_evidence/productization/pm_release_blocker_closure_board.json"
)
DEFAULT_PM_RELEASE_GATE_COMPLETION_AUDIT = Path(
    "implementation/phase1/release_evidence/productization/pm_release_gate_completion_audit.json"
)
DEFAULT_PM_RELEASE_GATE_REVIEWER_HANDOFF = Path(
    "implementation/phase1/release_evidence/productization/pm_release_gate_reviewer_handoff.json"
)
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
DEFAULT_UX_NEW_USER_OBSERVATION = Path(
    "implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json"
)
DEFAULT_SECURITY_RUNBOOK = Path("docs/production-ops-security.md")
DEFAULT_LICENSE_STATUS = Path("implementation/phase1/release/support_bundle/license_status.json")
DEFAULT_LICENSE_STATUS_CLOSURE = Path(
    "implementation/phase1/release_evidence/productization/license_status_closure_report.json"
)
DEFAULT_AI_ORCHESTRATION_PREFLIGHT = Path(
    "implementation/phase1/release_evidence/productization/ai_orchestration_preflight_report.json"
)
DEFAULT_GITHUB_DEVELOPMENT_SYNC_PREFLIGHT: Path | None = None
DEFAULT_COMMERCIAL_GAP_LEDGER_STATUS = Path(
    "implementation/phase1/release_evidence/productization/commercial_gap_ledger_status.json"
)
DEFAULT_GAP_CLOSURE_STATUS = Path("implementation/phase1/release_evidence/productization/gap_closure_status.json")
DEFAULT_GA_ENTERPRISE_READINESS = Path(
    "implementation/phase1/release_evidence/productization/ga_enterprise_readiness_report.json"
)
DEFAULT_GA_ENTERPRISE_SIGNOFF_INTAKE = Path(
    "implementation/phase1/release_evidence/productization/ga_enterprise_signoff_intake_packet.json"
)
DEFAULT_PAID_PILOT_SCOPE_GUARD = Path(
    "implementation/phase1/release_evidence/productization/paid_pilot_scope_guard_report.json"
)
DEFAULT_TEMPLATE_EVIDENCE_SAFETY = Path(
    "implementation/phase1/release_evidence/productization/template_evidence_safety_report.json"
)
DEFAULT_PM_RELEASE_REPRODUCTION_COMMAND_AUDIT = Path(
    "implementation/phase1/release_evidence/productization/pm_release_reproduction_command_audit.json"
)
DEFAULT_RELEASE_EVIDENCE_FRESHNESS = Path(
    "implementation/phase1/release_evidence/productization/release_evidence_freshness_report.json"
)
DEFAULT_CUSTOMER_SHADOW_EVIDENCE_STATUS = Path("implementation/phase1/customer_shadow_evidence_status.json")
DEFAULT_FRESH_FULL_VALIDATION_LANE_STATUS = Path(
    "implementation/phase1/release_evidence/productization/fresh_full_validation_lane_status.json"
)
DEFAULT_VALIDATION_MANUAL = Path("docs/release-validation-manual.md")
DEFAULT_LIMITATION_MANUAL = Path("docs/release-limitation-manual.md")
VALIDATION_MANUAL_REQUIRED_TERMS = (
    "pm release gate",
    "validation family",
    "p95 error",
    "residual",
    "benchmark breadth",
    "interop",
    "reproduction commands",
)
LIMITATION_MANUAL_REQUIRED_TERMS = (
    "claim boundary",
    "paid pilot",
    "limited commercial",
    "ga/enterprise",
    "known issues",
    "support bundle",
    "rollback",
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _input_checksums(paths: list[Path]) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in paths:
        checksums[str(path)] = _sha256(path) if path.exists() else "missing"
    return checksums


def _artifact_paths_from_rows(rows: list[dict[str, Any]]) -> list[Path]:
    paths: list[Path] = []
    for row in rows:
        artifacts = row.get("artifacts")
        if not isinstance(artifacts, dict):
            continue
        for value in artifacts.values():
            text = str(value or "")
            if text and not (text.startswith("<") and text.endswith(">")):
                paths.append(Path(text))
    return paths


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


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


def _evidence_surface_json_paths(evidence_surface_dir: Path) -> list[Path]:
    if not evidence_surface_dir.exists() or not evidence_surface_dir.is_dir():
        return []
    return sorted(path for path in evidence_surface_dir.glob("*.json") if path.is_file())


def _failed_criteria(gate: dict[str, Any]) -> list[str]:
    return [str(row) for row in _as_list(gate.get("failed_criteria"))]


def _surface_signal_payload(payload: dict[str, Any]) -> dict[str, Any]:
    signals = {
        "status": payload.get("status"),
        "reason_code": payload.get("reason_code"),
        "reason": payload.get("reason"),
        "blockers": payload.get("blockers"),
        "claim_boundary": payload.get("claim_boundary"),
        "claim_status": payload.get("claim_status"),
        "claim_locked": payload.get("claim_locked"),
        "locked": payload.get("locked"),
        "missing": payload.get("missing"),
    }
    return {
        key: value
        for key, value in signals.items()
        if value not in (None, False, "", [], {})
    }


def _contains_locked_signal(payload: dict[str, Any]) -> bool:
    if payload.get("locked") is True or payload.get("claim_locked") is True:
        return True
    try:
        text = json.dumps(_surface_signal_payload(payload), ensure_ascii=False, sort_keys=True).lower()
    except Exception:
        text = str(payload).lower()
    return "locked" in text or "claim_lock" in text


def _contains_missing_signal(payload: dict[str, Any]) -> bool:
    if payload.get("missing") is True:
        return True
    try:
        text = json.dumps(_surface_signal_payload(payload), ensure_ascii=False, sort_keys=True).lower()
    except Exception:
        text = str(payload).lower()
    return "missing" in text or "not_found" in text


def _evidence_surface_rows(evidence_surface_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _evidence_surface_json_paths(evidence_surface_dir):
        payload = _load_json(path)
        summary = _summary(payload)
        status = str(payload.get("status") or payload.get("reason_code") or "").strip()
        if not status:
            status = "ready" if _truthy_contract(payload) else "blocked"
        phase3_exit_gate = _as_dict(payload.get("phase3_exit_gate"))
        phase4_exit_gate = _as_dict(payload.get("phase4_exit_gate"))
        surface_id = path.stem
        rows.append(
            {
                "surface_id": surface_id,
                "path": str(path),
                "present": bool(payload),
                "contract_pass": _truthy_contract(payload),
                "status": status,
                "reason_code": str(payload.get("reason_code", "")),
                "blocker_count": len(_as_list(payload.get("blockers"))),
                "locked": _contains_locked_signal(payload),
                "missing": not payload or _contains_missing_signal(payload),
                "summary_line": str(payload.get("summary_line") or summary.get("summary_line") or ""),
                "first_blocked_target": str(
                    payload.get("first_blocked_target")
                    or summary.get("first_blocked_target")
                    or ""
                ),
                "root_cause_tags": [
                    str(row)
                    for row in _as_list(
                        payload.get("root_cause_tags") or summary.get("root_cause_tags")
                    )
                ],
                "blocked_criteria": [
                    *(_failed_criteria(phase3_exit_gate)),
                    *(_failed_criteria(phase4_exit_gate)),
                ],
            }
        )
    return rows


def _operator_action_count(pm_blocker_register: dict[str, Any]) -> int:
    rows = _rows(pm_blocker_register)
    if rows:
        return len(rows)
    summary = _summary(pm_blocker_register)
    for key in ("operator_action_count", "open_blocker_count", "owner_input_required_count"):
        if key in summary:
            return _as_int(summary.get(key), 0)
    return 0


def _approval_token_count(
    *,
    full_release_blockers: list[str],
    pm_blocker_register: dict[str, Any],
) -> int:
    approval_tokens: set[str] = {
        item for item in full_release_blockers if "approval" in item.lower()
    }
    for row in _rows(pm_blocker_register):
        signals = [
            str(row.get(key, ""))
            for key in (
                "blocker_id",
                "blocker_code",
                "owner_action",
                "next_action",
                "resolution_type",
                "claim_boundary",
            )
        ]
        if any("approval" in item.lower() for item in signals):
            approval_tokens.add(str(row.get("blocker_id") or row.get("blocker_code") or len(approval_tokens)))
    return len(approval_tokens)


def _stale_artifact_count(release_evidence_freshness_payload: dict[str, Any]) -> int:
    summary = _summary(release_evidence_freshness_payload)
    if "stale_artifact_count" in summary:
        return _as_int(summary.get("stale_artifact_count"), 0)
    return _as_int(summary.get("blocker_count"), 0)


def _public_benchmark_ready(
    measured_benchmark_breadth_payload: dict[str, Any],
    external_benchmark_submission_readiness_payload: dict[str, Any],
    public_benchmark_source_of_truth_payload: dict[str, Any],
) -> bool:
    external_summary = _summary(external_benchmark_submission_readiness_payload)
    external_ready = bool(
        external_summary.get("ready_to_start_full_submission_now")
        or external_summary.get("ready_to_start_now")
        or external_summary.get("ready_to_submit")
    )
    source_summary = _summary(public_benchmark_source_of_truth_payload)
    source_ready = bool(
        public_benchmark_source_of_truth_payload.get("public_benchmark_ready")
        or source_summary.get("public_benchmark_ready")
    )
    return bool(
        _truthy_contract(measured_benchmark_breadth_payload)
        and _truthy_contract(external_benchmark_submission_readiness_payload)
        and external_ready
        and _truthy_contract(public_benchmark_source_of_truth_payload)
        and source_ready
    )


def _science_surface_status(
    *,
    surface_family: str,
    surfaces: list[dict[str, Any]],
    missing_bottleneck: str,
    locked_bottleneck: str,
    contract_bottleneck: str,
) -> dict[str, Any]:
    locked_count = sum(1 for row in surfaces if row["locked"])
    contract_pass_count = sum(1 for row in surfaces if row["contract_pass"])
    if not surfaces:
        status = "missing"
        bottleneck = missing_bottleneck
    elif locked_count:
        status = "locked"
        bottleneck = locked_bottleneck
    elif contract_pass_count != len(surfaces):
        status = "blocked"
        bottleneck = contract_bottleneck
    else:
        status = "ready"
        bottleneck = ""
    return {
        "surface_family": surface_family,
        "present": bool(surfaces),
        "status": status,
        "surface_count": len(surfaces),
        "contract_pass_count": contract_pass_count,
        "locked_count": locked_count,
        "surface_ids": [str(row["surface_id"]) for row in surfaces],
        "first_blocked_target": next(
            (str(row["first_blocked_target"]) for row in surfaces if row["first_blocked_target"]),
            "",
        ),
        "root_cause_tags": list(
            dict.fromkeys(
                str(tag)
                for row in surfaces
                for tag in _as_list(row.get("root_cause_tags"))
            )
        ),
        "blocked_criteria": list(
            dict.fromkeys(
                str(criterion)
                for row in surfaces
                for criterion in _as_list(row.get("blocked_criteria"))
            )
        ),
        "bottleneck": bottleneck,
    }


def _science_surface_operator_actions(
    science_evidence_surface_status: dict[str, dict[str, Any]],
    *,
    evidence_surface_dir: Path,
) -> list[dict[str, Any]]:
    action_hints = {
        "h_bond": {
            "operator_intake_artifact": (
                "implementation/phase1/release_evidence/productization/"
                "h_bond_backmap_operator_intake_packet.json"
            ),
            "operator_intake_route": "/product/capabilities",
            "next_actions": [
                "fill_h_bond_backmap_operator_intake_packet",
                "attach_h_bond_backmap_operator_receipts",
                "materialize_h_bond_backmap_evidence_rows",
                "regenerate_product_capabilities_surface",
                "regenerate_goal_bottleneck_roadmap_surface",
                "regenerate_pm_release_gate_report",
            ],
        },
        "gpcr": {
            "operator_intake_artifact": (
                "implementation/phase1/release_evidence/productization/"
                "gpcr_hard_decoy_operator_intake_packet.json"
            ),
            "operator_intake_route": (
                "/product/gpcr-hard-decoy-suite-report/operator-intake"
            ),
            "next_actions": [
                "fill_gpcr_hard_decoy_operator_intake_packet",
                "fill_drd2_htr2a_oprm1_operator_template_values",
                "run_gpcr_hard_decoy_materializer",
                "refresh_gpcr_hard_decoy_product_report",
                "regenerate_product_capabilities_surface",
                "regenerate_goal_bottleneck_roadmap_surface",
            ],
        },
        "pocketmd_lite": {
            "operator_intake_artifact": (
                "implementation/phase1/release_evidence/productization/"
                "pocketmd_lite_operator_intake_packet.json"
            ),
            "operator_intake_route": "/product/pocketmd-lite/operator-intake",
            "next_actions": [
                "fill_pocketmd_lite_operator_intake_packet",
                "attach_top_k_candidate_refinement_rows",
                "run_pocketmd_lite_topk_survival_materializer",
                "regenerate_product_capabilities_surface",
                "regenerate_goal_bottleneck_roadmap_surface",
            ],
        },
    }
    actions: list[dict[str, Any]] = []
    for family, status in science_evidence_surface_status.items():
        bottleneck = str(status.get("bottleneck") or "")
        if not bottleneck:
            continue
        first_blocked_target = str(status.get("first_blocked_target") or "")
        root_cause_tags = [str(row) for row in _as_list(status.get("root_cause_tags"))]
        blocked_criteria = [
            str(row) for row in _as_list(status.get("blocked_criteria"))
        ]
        if family == "pocketmd_lite":
            action_id = "resolve_pocketmd_lite_science_product_surface"
            action_status = "science_product_surface_required"
            surface_label = "science product surface"
        else:
            action_id = f"resolve_{family}_evidence_surface"
            action_status = "science_evidence_required"
            surface_label = "evidence surface"
        reason = f"{family} {surface_label} is {status.get('status')}; bottleneck={bottleneck}"
        if first_blocked_target:
            reason += f"; first_blocked_target={first_blocked_target}"
        if root_cause_tags:
            reason += f"; root_cause_tags={','.join(root_cause_tags)}"
        surface_ids = [str(row) for row in _as_list(status.get("surface_ids"))]
        hint = action_hints.get(family, {})
        actions.append(
            {
                "action_id": action_id,
                "status": action_status,
                "surface_family": family,
                "bottleneck": bottleneck,
                "first_blocked_target": first_blocked_target,
                "root_cause_tags": root_cause_tags,
                "blocked_criteria": blocked_criteria,
                "blocked_criteria_count": len(blocked_criteria),
                "reason": reason,
                "artifact": ", ".join(surface_ids) if surface_ids else str(evidence_surface_dir),
                "operator_intake_artifact": str(hint.get("operator_intake_artifact") or ""),
                "operator_intake_route": str(hint.get("operator_intake_route") or ""),
                "next_actions": [str(row) for row in _as_list(hint.get("next_actions"))],
            }
        )
    return actions


def _public_benchmark_operator_actions(
    public_benchmark_source_of_truth_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    source_summary = _summary(public_benchmark_source_of_truth_payload)
    source_ready = bool(
        public_benchmark_source_of_truth_payload.get("public_benchmark_ready")
        or source_summary.get("public_benchmark_ready")
    )
    if source_ready:
        return []

    status = str(
        public_benchmark_source_of_truth_payload.get("status")
        or source_summary.get("status")
        or "missing"
    )
    blockers = [
        str(row)
        for row in (
            _as_list(public_benchmark_source_of_truth_payload.get("blockers"))
            or _as_list(source_summary.get("blockers"))
        )
    ]
    if not blockers:
        blockers = ["public_benchmark_source_of_truth_missing_or_not_ready"]
    next_actions = [
        str(row)
        for row in (
            _as_list(public_benchmark_source_of_truth_payload.get("next_actions"))
            or _as_list(source_summary.get("next_actions"))
        )
    ]
    first_blocked_target = str(
        public_benchmark_source_of_truth_payload.get("first_blocked_target")
        or source_summary.get("first_blocked_target")
        or _as_dict(
            public_benchmark_source_of_truth_payload.get("first_operator_evidence_gap")
        ).get("slot_id")
        or ""
    )
    root_cause_tags = [
        str(row)
        for row in _as_list(
            public_benchmark_source_of_truth_payload.get("root_cause_tags")
            or source_summary.get("root_cause_tags")
        )
    ]
    tier_beta_gate = _as_dict(
        public_benchmark_source_of_truth_payload.get("tier_beta_gate")
        or source_summary.get("tier_beta_gate")
    )
    blocked_criteria = _failed_criteria(tier_beta_gate)
    first_blocker = blockers[0] if blockers else ""
    reason = f"public benchmark source-of-truth is {status}; first_blocker={first_blocker}"
    if first_blocked_target:
        reason += f"; first_blocked_target={first_blocked_target}"
    if root_cause_tags:
        reason += f"; root_cause_tags={','.join(root_cause_tags)}"
    if next_actions:
        reason += f"; next_action={next_actions[0]}"
    return [
        {
            "action_id": "materialize_public_benchmark_source_of_truth",
            "status": "public_benchmark_evidence_required",
            "bottleneck": "public_benchmark_source_of_truth_not_ready",
            "first_blocker": first_blocker,
            "first_blocked_target": first_blocked_target,
            "root_cause_tags": root_cause_tags,
            "blocked_criteria": blocked_criteria,
            "blocked_criteria_count": len(blocked_criteria),
            "blockers": blockers,
            "next_actions": next_actions,
            "reason": reason,
            "artifact": str(DEFAULT_PUBLIC_BENCHMARK_SOURCE_OF_TRUTH),
        }
    ]


def _release_decision(
    *,
    release_allowed: bool,
    blockers: list[str],
    release_area_blockers: list[str],
    measured_benchmark_breadth_payload: dict[str, Any],
    external_benchmark_submission_readiness_payload: dict[str, Any],
    public_benchmark_source_of_truth_payload: dict[str, Any],
    release_evidence_freshness_payload: dict[str, Any],
    pm_blocker_register: dict[str, Any],
    evidence_surface_dir: Path,
) -> dict[str, Any]:
    full_release_blockers = [*blockers, *release_area_blockers]
    evidence_surfaces = _evidence_surface_rows(evidence_surface_dir)
    missing_surface_count = sum(1 for row in evidence_surfaces if row["missing"])
    if not evidence_surface_dir.exists() or not evidence_surface_dir.is_dir():
        missing_surface_count += 1
    locked_surface_count = sum(1 for row in evidence_surfaces if row["locked"])
    gpcr_surfaces = [
        row
        for row in evidence_surfaces
        if "gpcr" in row["surface_id"].lower()
    ]
    h_bond_surfaces = [
        row
        for row in evidence_surfaces
        if "h_bond" in row["surface_id"].lower() or "hbond" in row["surface_id"].lower()
    ]
    pocketmd_lite_surfaces = [
        row
        for row in evidence_surfaces
        if "pocketmd" in row["surface_id"].lower()
    ]
    broad_gpcr_family_claim_safe = bool(
        gpcr_surfaces
        and all(bool(row["contract_pass"]) for row in gpcr_surfaces)
        and not any(bool(row["locked"]) for row in gpcr_surfaces)
    )
    pocketmd_lite_product_surface_ready = bool(
        pocketmd_lite_surfaces
        and all(bool(row["contract_pass"]) for row in pocketmd_lite_surfaces)
        and not any(bool(row["locked"]) for row in pocketmd_lite_surfaces)
    )
    science_evidence_surface_status = {
        "h_bond": _science_surface_status(
            surface_family="h_bond",
            surfaces=h_bond_surfaces,
            missing_bottleneck="h_bond_evidence_surface_missing",
            locked_bottleneck="h_bond_evidence_surface_locked",
            contract_bottleneck="h_bond_evidence_surface_contract_not_passing",
        ),
        "gpcr": _science_surface_status(
            surface_family="gpcr",
            surfaces=gpcr_surfaces,
            missing_bottleneck="gpcr_evidence_surface_missing",
            locked_bottleneck="broad_gpcr_family_claim_locked",
            contract_bottleneck="gpcr_evidence_surface_contract_not_passing",
        ),
        "pocketmd_lite": _science_surface_status(
            surface_family="pocketmd_lite",
            surfaces=pocketmd_lite_surfaces,
            missing_bottleneck="pocketmd_lite_science_product_surface_missing",
            locked_bottleneck="pocketmd_lite_science_product_surface_locked",
            contract_bottleneck="pocketmd_lite_science_product_surface_contract_not_passing",
        ),
    }
    science_evidence_surface_status["gpcr"][
        "broad_family_claim_safe"
    ] = broad_gpcr_family_claim_safe
    science_evidence_surface_status["pocketmd_lite"][
        "product_surface_ready"
    ] = pocketmd_lite_product_surface_ready
    science_surface_bottlenecks = [
        str(row["bottleneck"])
        for row in science_evidence_surface_status.values()
        if row["bottleneck"]
    ]
    stale_count = _stale_artifact_count(release_evidence_freshness_payload)
    operator_actions: list[dict[str, Any]] = []
    if stale_count:
        operator_actions.append(
            {
                "action_id": "refresh_release_evidence_freshness",
                "status": "refresh_required",
                "reason": "release_evidence_freshness_report has stale or incomplete source-of-truth blockers",
                "artifact": "release_evidence_freshness_report",
            }
        )
    if missing_surface_count:
        operator_actions.append(
            {
                "action_id": "attach_missing_evidence_surfaces",
                "status": "evidence_required",
                "reason": "one or more expected evidence surface inputs are missing",
                "artifact": str(evidence_surface_dir),
            }
        )
    operator_actions.extend(
        _science_surface_operator_actions(
            science_evidence_surface_status,
            evidence_surface_dir=evidence_surface_dir,
        )
    )
    operator_actions.extend(
        _public_benchmark_operator_actions(public_benchmark_source_of_truth_payload)
    )
    operator_action_count = max(
        _operator_action_count(pm_blocker_register),
        len(full_release_blockers),
    ) + len(operator_actions)
    return {
        "release_allowed": bool(release_allowed),
        "blocked_release_count": len(full_release_blockers),
        "first_blocker": full_release_blockers[0] if full_release_blockers else "",
        "operator_action_count": operator_action_count,
        "approval_token_count": _approval_token_count(
            full_release_blockers=full_release_blockers,
            pm_blocker_register=pm_blocker_register,
        ),
        "stale_artifact_count": stale_count,
        "stale_artifact_refresh_required": bool(stale_count),
        "evidence_surface_count": len(evidence_surfaces),
        "missing_evidence_surface_count": missing_surface_count,
        "locked_evidence_surface_count": locked_surface_count,
        "public_benchmark_ready": _public_benchmark_ready(
            measured_benchmark_breadth_payload,
            external_benchmark_submission_readiness_payload,
            public_benchmark_source_of_truth_payload,
        ),
        "public_benchmark_source_of_truth_ready": bool(
            public_benchmark_source_of_truth_payload.get("public_benchmark_ready")
            or _summary(public_benchmark_source_of_truth_payload).get("public_benchmark_ready")
        ),
        "public_benchmark_source_of_truth_status": str(
            public_benchmark_source_of_truth_payload.get("status")
            or _summary(public_benchmark_source_of_truth_payload).get("status")
            or ""
        ),
        "public_benchmark_source_of_truth_blockers": [
            str(row) for row in _as_list(public_benchmark_source_of_truth_payload.get("blockers"))
        ],
        "broad_gpcr_family_claim_safe": broad_gpcr_family_claim_safe,
        "pocketmd_lite_product_surface_ready": pocketmd_lite_product_surface_ready,
        "h_bond_evidence_surface_present": bool(h_bond_surfaces),
        "gpcr_evidence_surface_present": bool(gpcr_surfaces),
        "pocketmd_lite_science_product_surface_present": bool(pocketmd_lite_surfaces),
        "science_evidence_surface_status": science_evidence_surface_status,
        "science_evidence_surface_bottlenecks": science_surface_bottlenecks,
        "evidence_surface_dir": str(evidence_surface_dir),
        "evidence_surfaces": evidence_surfaces,
        "operator_actions": operator_actions,
        "claim_boundary": (
            "Evidence surface counts reflect local JSON files under evidence_surface_dir. Broad GPCR family "
            "claims remain unsafe unless GPCR evidence surfaces are present, contract-passing, and unlocked. "
            "PocketMD Lite is a bounded top-k science product surface; broad all-atom MD and FEP claims "
            "remain locked unless separately evidenced."
        ),
    }


def _handoff_ready_pass(payload: dict[str, Any]) -> bool:
    summary = _summary(payload)
    return bool(
        _truthy_contract(payload)
        or (
            bool(summary.get("all_open_blockers_have_handoff", False))
            and _as_int(summary.get("handoff_not_ready_count"), 1) == 0
        )
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


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _lane_row_by_id(payload: dict[str, Any], lane: str) -> dict[str, Any]:
    for row in _as_list(payload.get("lane_rows")):
        if isinstance(row, dict) and str(row.get("lane", "")) == lane:
            return row
    return {}


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


def _manifest_lane_value(payload: dict[str, Any], lane: str, key: str) -> Any:
    lanes = payload.get("lanes")
    if not isinstance(lanes, dict):
        return None
    lane_payload = lanes.get(lane)
    if not isinstance(lane_payload, dict):
        return None
    return lane_payload.get(key)


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


def _contains_terms(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return all(term in lowered for term in terms)


def _support_section_present(sections: dict[str, Any], key: str) -> bool:
    value = str(sections.get(key, "") or "")
    return bool(value and value != "missing")


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


def _github_sync_payload(github_sync_preflight_path: Path | None) -> tuple[dict[str, Any], str]:
    if github_sync_preflight_path is not None:
        return _load_json(github_sync_preflight_path), str(github_sync_preflight_path)
    try:
        payload = check_github_development_sync_preflight.build_report(
            check_github_development_sync_preflight.collect_git_state(),
            remote_fetch_attempted=False,
            remote_fetch_ok=None,
        )
    except Exception as exc:  # pragma: no cover - defensive release gate boundary
        payload = {
            "schema_version": "github-development-sync-preflight.v1",
            "status": "blocked",
            "contract_pass": False,
            "preflight_pass": False,
            "remote_sync_needed": False,
            "reason_code": "ERR_GITHUB_SYNC_LIVE_PREFLIGHT_FAILED",
            "blockers": ["github_sync_live_preflight_failed"],
            "checks": {},
            "state": {},
            "pending_remote_updates": [],
            "r4_disclosure": {},
            "error": str(exc),
        }
    return payload, "<live-git-state>"


def _github_sync_area(github_sync_preflight_path: Path | None) -> dict[str, Any]:
    payload, artifact_label = _github_sync_payload(github_sync_preflight_path)
    checks = _as_dict(payload.get("checks"))
    state = _as_dict(payload.get("state"))
    preflight_blockers = [
        str(item) for item in _as_list(payload.get("blockers")) if str(item).strip()
    ]
    remote_mutation_approval_required = "remote_mutation_approval_required" in preflight_blockers
    artifact_present = bool(payload)
    status = str(payload.get("status", "")).strip().lower() if artifact_present else ""
    worktree_clean = bool(checks.get("worktree_clean", False))
    remote_safety_ok = bool(checks.get("remote_safety_ok", False))
    feature_ff = bool(checks.get("feature_fast_forward_possible", False))
    main_ff = bool(checks.get("main_fast_forward_possible", False))
    remote_sync_needed = bool(payload.get("remote_sync_needed", False)) if artifact_present else False
    preflight_clean = bool(
        artifact_present
        and not preflight_blockers
        and worktree_clean
        and remote_safety_ok
        and feature_ff
        and main_ff
        and not remote_sync_needed
        and status == "synced"
    )
    area_checks = {
        "github_sync_preflight_artifact_present": artifact_present,
        "github_sync_preflight_status": status or "missing",
        "github_sync_preflight_clean": preflight_clean,
        "github_sync_worktree_clean": worktree_clean,
        "github_sync_remote_safety_ok": remote_safety_ok,
        "github_sync_feature_fast_forward_possible": feature_ff,
        "github_sync_main_fast_forward_possible": main_ff,
        "github_sync_remote_mutation_approval_pending": remote_mutation_approval_required,
        "github_sync_remote_sync_needed": remote_sync_needed,
    }
    area_blockers = [
        *(["github_sync_preflight_report_missing"] if not artifact_present else []),
        *(f"github_sync_preflight::{blocker}" for blocker in preflight_blockers),
        *(["github_sync_remote_sync_pending"] if artifact_present and remote_sync_needed else []),
        *(["github_sync_preflight_not_synced"] if artifact_present and status and status != "synced" else []),
    ]
    pending_remote_updates = _as_list(payload.get("pending_remote_updates"))
    return _area(
        "github_sync",
        "GitHub Development Sync",
        ok=not area_blockers,
        blockers=area_blockers,
        checks=area_checks,
        summary={
            "status": status or "missing",
            "remote_sync_needed": remote_sync_needed,
            "remote_mutation_approval_pending": remote_mutation_approval_required,
            "remote_mutation_approved": bool(payload.get("remote_mutation_approved", False)) if artifact_present else False,
            "feature_ahead_count": _as_int(state.get("feature_ahead_count"), 0),
            "main_ahead_count": _as_int(state.get("main_ahead_count"), 0),
            "pending_remote_update_count": len(pending_remote_updates),
            "reason_code": str(payload.get("reason_code", "")),
            "r4_risk": str(
                _as_dict(payload.get("r4_disclosure")).get("risk", "")
            ) if artifact_present else "",
        },
        artifacts={"github_development_sync_preflight": artifact_label},
        claim_boundary=(
            "The GitHub development sync preflight is read-only. It does not push, merge, publish, "
            "or mutate GitHub. A remote update still requires explicit human R4 approval."
        ),
    )


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
    pm_blocker_action_register_path: Path,
    pm_blocker_closure_board_path: Path,
    template_evidence_safety_path: Path,
    pm_release_reproduction_command_audit_path: Path,
    release_evidence_freshness_path: Path,
    validation_manual_path: Path,
    limitation_manual_path: Path,
) -> dict[str, Any]:
    workflow = _load_json(workflow_path)
    registry = _load_json(release_registry_path)
    support = _load_json(support_bundle_path)
    pm_blocker_register = _load_json(pm_blocker_action_register_path)
    pm_blocker_closure_board = _load_json(pm_blocker_closure_board_path)
    template_evidence_safety = _load_json(template_evidence_safety_path)
    pm_release_reproduction_command_audit = _load_json(pm_release_reproduction_command_audit_path)
    release_evidence_freshness = _load_json(release_evidence_freshness_path)
    workflow_summary = _summary(workflow)
    registry_summary = _summary(registry)
    support_checks = _checks(support)
    support_pm_failure_bundle_coverage = _as_dict(support.get("pm_failure_bundle_coverage"))
    pm_blocker_summary = _summary(pm_blocker_register)
    pm_blocker_closure_summary = _summary(pm_blocker_closure_board)
    pm_blocker_register_open_count = _as_int(pm_blocker_summary.get("open_blocker_count"), 0)
    pm_blocker_register_release_area_count = _as_int(
        pm_blocker_summary.get("release_area_blocker_count"),
        pm_blocker_register_open_count,
    )
    pm_blocker_closure_open_count = _as_int(pm_blocker_closure_summary.get("open_blocker_count"), -1)
    support_export_archive = _as_dict(support.get("export_archive"))
    support_optional_sections = _as_dict(support.get("optional_sections"))
    summary_line = str(workflow.get("summary_line", "") or "")
    validation_manual_text = _read_text_or_empty(validation_manual_path)
    limitation_manual_text = _read_text_or_empty(limitation_manual_path)
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
            and support_checks.get("archive_roundtrip_test_pass", False)
        ),
        "support_bundle_one_click_archive_present": bool(
            support_export_archive.get("available") and support_export_archive.get("sha256")
        ),
        "support_bundle_pm_blocker_register_present": _support_section_present(
            support_optional_sections,
            "pm_release_blocker_action_register",
        ),
        "support_bundle_pm_blocker_closure_board_present": _support_section_present(
            support_optional_sections,
            "pm_release_blocker_closure_board",
        ),
        "support_bundle_pm_release_gate_completion_audit_present": _support_section_present(
            support_optional_sections,
            "pm_release_gate_completion_audit",
        ),
        "support_bundle_pm_release_gate_reviewer_handoff_present": _support_section_present(
            support_optional_sections,
            "pm_release_gate_reviewer_handoff",
        ),
        "support_bundle_pm_owner_evidence_request_packet_present": _support_section_present(
            support_optional_sections,
            "pm_owner_evidence_request_packet",
        ),
        "support_bundle_pm_failure_bundle_coverage_pass": bool(
            support_checks.get("pm_failure_bundle_coverage_pass", False)
            and support_pm_failure_bundle_coverage.get("coverage_pass", False)
        ),
        "pm_blocker_register_handoff_ready_pass": _handoff_ready_pass(pm_blocker_register),
        "pm_blocker_closure_board_handoff_ready_pass": _handoff_ready_pass(pm_blocker_closure_board),
        "pm_blocker_closure_board_register_count_match": (
            pm_blocker_closure_open_count == pm_blocker_register_open_count
        ),
        "support_bundle_ci_streak_intake_packet_present": _support_section_present(
            support_optional_sections,
            "ci_streak_intake_packet",
        ),
        "support_bundle_ci_streak_manifest_present": _support_section_present(
            support_optional_sections,
            "ci_streak_manifest",
        ),
        "support_bundle_github_actions_ci_streak_evidence_present": _support_section_present(
            support_optional_sections,
            "github_actions_ci_streak_evidence",
        ),
        "support_bundle_license_intake_packet_present": _support_section_present(
            support_optional_sections,
            "license_status_intake_packet",
        ),
        "support_bundle_license_status_closure_present": _support_section_present(
            support_optional_sections,
            "license_status_closure_report",
        ),
        "support_bundle_license_status_template_present": _support_section_present(
            support_optional_sections,
            "license_status_template",
        ),
        "support_bundle_frontend_dependency_audit_present": _support_section_present(
            support_optional_sections,
            "frontend_dependency_audit_report",
        ),
        "support_bundle_validation_manual_present": _support_section_present(
            support_optional_sections,
            "release_validation_manual",
        ),
        "support_bundle_limitation_manual_present": _support_section_present(
            support_optional_sections,
            "release_limitation_manual",
        ),
        "support_bundle_ux_new_user_observation_present": _support_section_present(
            support_optional_sections,
            "ux_new_user_observation_report",
        ),
        "support_bundle_ux_new_user_observation_intake_present": _support_section_present(
            support_optional_sections,
            "ux_new_user_observation_intake_packet",
        ),
        "template_evidence_safety_report_present": template_evidence_safety_path.exists(),
        "template_evidence_safety_pass": _truthy_contract(template_evidence_safety),
        "support_bundle_template_evidence_safety_report_present": _support_section_present(
            support_optional_sections,
            "template_evidence_safety_report",
        ),
        "pm_release_reproduction_command_audit_present": pm_release_reproduction_command_audit_path.exists(),
        "pm_release_reproduction_command_audit_pass": _truthy_contract(pm_release_reproduction_command_audit),
        "support_bundle_pm_release_reproduction_command_audit_present": _support_section_present(
            support_optional_sections,
            "pm_release_reproduction_command_audit",
        ),
        "support_bundle_commercial_gap_ledger_status_present": _support_section_present(
            support_optional_sections,
            "commercial_gap_ledger_status",
        ),
        "support_bundle_gap_closure_status_present": _support_section_present(
            support_optional_sections,
            "gap_closure_status",
        ),
        "validation_manual_present": validation_manual_path.exists(),
        "limitation_manual_present": limitation_manual_path.exists(),
        "validation_manual_content_pass": _contains_terms(
            validation_manual_text,
            VALIDATION_MANUAL_REQUIRED_TERMS,
        ),
        "limitation_manual_content_pass": _contains_terms(
            limitation_manual_text,
            LIMITATION_MANUAL_REQUIRED_TERMS,
        ),
    }
    blockers = [
        *(["workflow_productization_gate_not_green"] if not gate_checks["workflow_productization_pass"] else []),
        *(["viewer_reviewer_customer_preset_missing"] if not gate_checks["viewer_reviewer_customer_surface_pass"] else []),
        *(["pdf_report_or_reviewer_package_missing"] if not gate_checks["pdf_report_or_reviewer_package_pass"] else []),
        *(["audit_trail_action_source_trace_missing"] if not gate_checks["audit_trail_action_source_trace_pass"] else []),
        *(["signed_release_registry_missing_or_failed"] if not gate_checks["signed_release_registry_pass"] else []),
        *(["support_bundle_export_missing_or_failed"] if not gate_checks["support_bundle_export_pass"] else []),
        *(
            ["support_bundle_one_click_archive_missing"]
            if not gate_checks["support_bundle_one_click_archive_present"]
            else []
        ),
        *(
            ["support_bundle_pm_blocker_register_missing"]
            if not gate_checks["support_bundle_pm_blocker_register_present"]
            else []
        ),
        *(
            ["support_bundle_pm_blocker_closure_board_missing"]
            if not gate_checks["support_bundle_pm_blocker_closure_board_present"]
            else []
        ),
        *(
            ["support_bundle_pm_release_gate_completion_audit_missing"]
            if not gate_checks["support_bundle_pm_release_gate_completion_audit_present"]
            else []
        ),
        *(
            ["support_bundle_pm_release_gate_reviewer_handoff_missing"]
            if not gate_checks["support_bundle_pm_release_gate_reviewer_handoff_present"]
            else []
        ),
        *(
            ["support_bundle_pm_failure_bundle_coverage_incomplete"]
            if not gate_checks["support_bundle_pm_failure_bundle_coverage_pass"]
            else []
        ),
        *(
            ["pm_blocker_action_register_handoff_not_ready"]
            if not gate_checks["pm_blocker_register_handoff_ready_pass"]
            else []
        ),
        *(
            ["pm_blocker_closure_board_handoff_not_ready"]
            if not gate_checks["pm_blocker_closure_board_handoff_ready_pass"]
            else []
        ),
        *(
            ["pm_blocker_closure_board_count_mismatch"]
            if not gate_checks["pm_blocker_closure_board_register_count_match"]
            else []
        ),
        *(
            ["support_bundle_ci_streak_intake_packet_missing"]
            if not gate_checks["support_bundle_ci_streak_intake_packet_present"]
            else []
        ),
        *(
            ["support_bundle_ci_streak_manifest_missing"]
            if not gate_checks["support_bundle_ci_streak_manifest_present"]
            else []
        ),
        *(
            ["support_bundle_github_actions_ci_streak_evidence_missing"]
            if not gate_checks["support_bundle_github_actions_ci_streak_evidence_present"]
            else []
        ),
        *(
            ["support_bundle_license_intake_packet_missing"]
            if not gate_checks["support_bundle_license_intake_packet_present"]
            else []
        ),
        *(
            ["support_bundle_license_status_closure_missing"]
            if not gate_checks["support_bundle_license_status_closure_present"]
            else []
        ),
        *(
            ["support_bundle_license_status_template_missing"]
            if not gate_checks["support_bundle_license_status_template_present"]
            else []
        ),
        *(
            ["support_bundle_frontend_dependency_audit_missing"]
            if not gate_checks["support_bundle_frontend_dependency_audit_present"]
            else []
        ),
        *(
            ["support_bundle_validation_manual_missing"]
            if not gate_checks["support_bundle_validation_manual_present"]
            else []
        ),
        *(
            ["support_bundle_limitation_manual_missing"]
            if not gate_checks["support_bundle_limitation_manual_present"]
            else []
        ),
        *(
            ["support_bundle_ux_new_user_observation_missing"]
            if not gate_checks["support_bundle_ux_new_user_observation_present"]
            else []
        ),
        *(
            ["support_bundle_ux_new_user_observation_intake_missing"]
            if not gate_checks["support_bundle_ux_new_user_observation_intake_present"]
            else []
        ),
        *(
            ["template_evidence_safety_report_missing"]
            if not gate_checks["template_evidence_safety_report_present"]
            else []
        ),
        *(["template_evidence_safety_not_green"] if not gate_checks["template_evidence_safety_pass"] else []),
        *(
            ["support_bundle_template_evidence_safety_report_missing"]
            if not gate_checks["support_bundle_template_evidence_safety_report_present"]
            else []
        ),
        *(
            ["pm_release_reproduction_command_audit_missing"]
            if not gate_checks["pm_release_reproduction_command_audit_present"]
            else []
        ),
        *(
            ["pm_release_reproduction_command_audit_not_green"]
            if not gate_checks["pm_release_reproduction_command_audit_pass"]
            else []
        ),
        *(
            ["support_bundle_pm_release_reproduction_command_audit_missing"]
            if not gate_checks["support_bundle_pm_release_reproduction_command_audit_present"]
            else []
        ),
        *(
            ["support_bundle_commercial_gap_ledger_status_missing"]
            if not gate_checks["support_bundle_commercial_gap_ledger_status_present"]
            else []
        ),
        *(
            ["support_bundle_gap_closure_status_missing"]
            if not gate_checks["support_bundle_gap_closure_status_present"]
            else []
        ),
        *(["validation_manual_missing"] if not gate_checks["validation_manual_present"] else []),
        *(["limitation_manual_missing"] if not gate_checks["limitation_manual_present"] else []),
        *(["validation_manual_incomplete"] if not gate_checks["validation_manual_content_pass"] else []),
        *(["limitation_manual_incomplete"] if not gate_checks["limitation_manual_content_pass"] else []),
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
            "support_bundle_export_archive": str(support_export_archive.get("path", "")),
            "support_bundle_export_archive_sha256": str(support_export_archive.get("sha256", "")),
            "support_bundle_pm_blocker_register": str(
                support_optional_sections.get("pm_release_blocker_action_register", "")
            ),
            "support_bundle_pm_blocker_closure_board": str(
                support_optional_sections.get("pm_release_blocker_closure_board", "")
            ),
            "support_bundle_pm_release_gate_completion_audit": str(
                support_optional_sections.get("pm_release_gate_completion_audit", "")
            ),
            "support_bundle_pm_release_gate_reviewer_handoff": str(
                support_optional_sections.get("pm_release_gate_reviewer_handoff", "")
            ),
            "support_bundle_pm_owner_evidence_request_packet": str(
                support_optional_sections.get("pm_owner_evidence_request_packet", "")
            ),
            "support_bundle_pm_failure_bundle_coverage": str(
                support_pm_failure_bundle_coverage.get("bundle_path", "")
            ),
            "support_bundle_pm_failure_bundle_coverage_sha256": str(
                support_pm_failure_bundle_coverage.get("sha256", "")
            ),
            "pm_blocker_register_open_blocker_count": pm_blocker_register_open_count,
            "pm_blocker_register_release_area_blocker_count": pm_blocker_register_release_area_count,
            "pm_blocker_register_handoff_ready_count": _as_int(
                pm_blocker_summary.get("handoff_ready_count"), 0
            ),
            "pm_blocker_register_handoff_not_ready_count": _as_int(
                pm_blocker_summary.get("handoff_not_ready_count"), 0
            ),
            "pm_blocker_register_external_owner_input_ready_count": _as_int(
                pm_blocker_summary.get("external_owner_input_ready_count"), 0
            ),
            "pm_blocker_closure_board_open_blocker_count": pm_blocker_closure_open_count,
            "pm_blocker_closure_board_handoff_ready_count": _as_int(
                pm_blocker_closure_summary.get("handoff_ready_count"), 0
            ),
            "pm_blocker_closure_board_handoff_not_ready_count": _as_int(
                pm_blocker_closure_summary.get("handoff_not_ready_count"), 0
            ),
            "pm_blocker_closure_board_external_owner_input_ready_count": _as_int(
                pm_blocker_closure_summary.get("external_owner_input_ready_count"), 0
            ),
            "support_bundle_ci_streak_intake_packet": str(
                support_optional_sections.get("ci_streak_intake_packet", "")
            ),
            "support_bundle_ci_streak_manifest": str(
                support_optional_sections.get("ci_streak_manifest", "")
            ),
            "support_bundle_github_actions_ci_streak_evidence": str(
                support_optional_sections.get("github_actions_ci_streak_evidence", "")
            ),
            "support_bundle_license_status_intake_packet": str(
                support_optional_sections.get("license_status_intake_packet", "")
            ),
            "support_bundle_license_status_closure": str(
                support_optional_sections.get("license_status_closure_report", "")
            ),
            "support_bundle_license_status_template": str(
                support_optional_sections.get("license_status_template", "")
            ),
            "support_bundle_frontend_dependency_audit": str(
                support_optional_sections.get("frontend_dependency_audit_report", "")
            ),
            "support_bundle_validation_manual": str(
                support_optional_sections.get("release_validation_manual", "")
            ),
            "support_bundle_limitation_manual": str(
                support_optional_sections.get("release_limitation_manual", "")
            ),
            "support_bundle_ux_new_user_observation": str(
                support_optional_sections.get("ux_new_user_observation_report", "")
            ),
            "support_bundle_ux_new_user_observation_intake": str(
                support_optional_sections.get("ux_new_user_observation_intake_packet", "")
            ),
            "template_evidence_safety_report": str(template_evidence_safety_path),
            "template_evidence_safety_summary_line": str(template_evidence_safety.get("summary_line", "")),
            "support_bundle_template_evidence_safety_report": str(
                support_optional_sections.get("template_evidence_safety_report", "")
            ),
            "pm_release_reproduction_command_audit": str(pm_release_reproduction_command_audit_path),
            "pm_release_reproduction_command_audit_summary_line": str(
                pm_release_reproduction_command_audit.get("summary_line", "")
            ),
            "pm_release_reproduction_command_audit_command_count": _as_int(
                _summary(pm_release_reproduction_command_audit).get("command_count"), 0
            ),
            "pm_release_reproduction_command_audit_violation_count": _as_int(
                _summary(pm_release_reproduction_command_audit).get("violation_count"), 0
            ),
            "support_bundle_pm_release_reproduction_command_audit": str(
                support_optional_sections.get("pm_release_reproduction_command_audit", "")
            ),
            "release_evidence_freshness": str(release_evidence_freshness_path),
            "release_evidence_freshness_contract_pass": _truthy_contract(release_evidence_freshness),
            "release_evidence_freshness_blocker_count": _as_int(
                _summary(release_evidence_freshness).get("blocker_count"), 0
            ),
            "support_bundle_commercial_gap_ledger_status": str(
                support_optional_sections.get("commercial_gap_ledger_status", "")
            ),
            "support_bundle_gap_closure_status": str(support_optional_sections.get("gap_closure_status", "")),
            "validation_manual_required_terms": list(VALIDATION_MANUAL_REQUIRED_TERMS),
            "limitation_manual_required_terms": list(LIMITATION_MANUAL_REQUIRED_TERMS),
        },
        artifacts={
            "workflow_productization": str(workflow_path),
            "release_registry": str(release_registry_path),
            "support_bundle": str(support_bundle_path),
            "pm_release_blocker_action_register": str(pm_blocker_action_register_path),
            "pm_release_blocker_closure_board": str(pm_blocker_closure_board_path),
            "template_evidence_safety": str(template_evidence_safety_path),
            "pm_release_reproduction_command_audit": str(pm_release_reproduction_command_audit_path),
            "release_evidence_freshness": str(release_evidence_freshness_path),
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
    ci_streak_intake_packet_path: Path,
    ci_require_ndtha_path: Path,
    ci_require_hip_path: Path,
    commercial_readiness_path: Path,
    core_family_p95_report_path: Path,
    ndtha_residual_path: Path,
    residual_level3_status_path: Path,
    ndtha_long_profile_path: Path,
    solver_hip_e2e_path: Path,
    runtime_policy_path: Path,
    measured_benchmark_breadth_path: Path,
    workflow_productization_path: Path,
    release_registry_path: Path,
    support_bundle_path: Path,
    pm_blocker_action_register_path: Path,
    pm_blocker_closure_board_path: Path,
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
    ux_new_user_observation_path: Path,
    security_runbook_path: Path,
    license_status_path: Path,
    license_status_closure_path: Path,
    template_evidence_safety_path: Path,
    pm_release_reproduction_command_audit_path: Path,
    release_evidence_freshness_path: Path,
    validation_manual_path: Path,
    limitation_manual_path: Path,
    github_sync_preflight_path: Path | None,
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
    residual_level3 = _load_json(residual_level3_status_path)
    ndtha_long = _load_json(ndtha_long_profile_path)
    runtime_policy = _load_json(runtime_policy_path)
    measured_breadth = _load_json(measured_benchmark_breadth_path)
    workflow = _load_json(workflow_productization_path)
    support = _load_json(support_bundle_path)
    pm_blocker_register = _load_json(pm_blocker_action_register_path)
    pm_blocker_closure_board = _load_json(pm_blocker_closure_board_path)
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
    ux_new_user = _load_json(ux_new_user_observation_path)
    license_status = _load_json(license_status_path)
    license_status_closure = _load_json(license_status_closure_path)
    template_evidence_safety = _load_json(template_evidence_safety_path)
    pm_release_reproduction_command_audit = _load_json(pm_release_reproduction_command_audit_path)
    release_evidence_freshness = _load_json(release_evidence_freshness_path)

    rows: list[dict[str, Any]] = []

    ci_streak_intake = _load_json(ci_streak_intake_packet_path)
    ci_streak_source_evidence = _as_dict(ci_streak_intake.get("source_evidence"))
    ci_streak_source_lanes = _as_dict(ci_streak_source_evidence.get("lanes"))
    pr_intake_lane = _lane_row_by_id(ci_streak_intake, "pr")
    nightly_intake_lane = _lane_row_by_id(ci_streak_intake, "nightly")
    pr_streak = (
        _as_int(pr_intake_lane.get("consecutive_pass_count"))
        if pr_intake_lane
        else _manifest_lane_streak(ci_streak_manifest, "pr")
    )
    nightly_streak = (
        _as_int(nightly_intake_lane.get("consecutive_pass_count"))
        if nightly_intake_lane
        else _manifest_lane_streak(ci_streak_manifest, "nightly")
    )
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
        "ci_streak_intake_contract_pass": _truthy_contract(ci_streak_intake),
        "ci_streak_source_evidence_pass": ci_streak_source_evidence.get("contract_pass") is True,
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
                "pr_streak_source": _manifest_lane_text(ci_streak_manifest, "pr", "streak_source"),
                "nightly_streak_source": _manifest_lane_text(ci_streak_manifest, "nightly", "streak_source"),
                "pr_github_actions_job_start_blocker_count": _manifest_lane_int(
                    ci_streak_manifest, "pr", "github_actions_job_start_blocker_count"
                ),
                "nightly_github_actions_job_start_blocker_count": _manifest_lane_int(
                    ci_streak_manifest, "nightly", "github_actions_job_start_blocker_count"
                ),
                "ci_streak_source_evidence_generated_at": str(
                    ci_streak_source_evidence.get("generated_at", "")
                ),
                "ci_streak_source_evidence_age_hours": ci_streak_source_evidence.get("age_hours"),
                "ci_streak_source_evidence_freshness_pass": ci_streak_source_evidence.get("freshness_pass"),
                "pr_source_evidence_release_credit_pass": _as_dict(
                    ci_streak_source_lanes.get("pr")
                ).get("source_release_credit_pass"),
                "nightly_source_evidence_release_credit_pass": _as_dict(
                    ci_streak_source_lanes.get("nightly")
                ).get("source_release_credit_pass"),
                "pr_github_actions_workflow_state": _as_dict(ci_streak_source_lanes.get("pr")).get(
                    "workflow_state"
                ),
                "nightly_github_actions_workflow_state": _as_dict(ci_streak_source_lanes.get("nightly")).get(
                    "workflow_state"
                ),
                "pr_local_workflow_trigger_events": _as_dict(ci_streak_source_lanes.get("pr")).get(
                    "local_workflow_trigger_events", []
                ),
                "nightly_local_workflow_trigger_events": _as_dict(ci_streak_source_lanes.get("nightly")).get(
                    "local_workflow_trigger_events", []
                ),
                "pr_local_required_trigger_present": _as_dict(ci_streak_source_lanes.get("pr")).get(
                    "local_required_trigger_present"
                ),
                "nightly_local_required_trigger_present": _as_dict(ci_streak_source_lanes.get("nightly")).get(
                    "local_required_trigger_present"
                ),
                "pr_missing_consecutive_pass_count": max(0, ci_pass_streak_threshold - pr_streak),
                "nightly_missing_consecutive_pass_count": max(0, ci_pass_streak_threshold - nightly_streak),
                "pr_pull_request_run_source_present": _manifest_lane_value(
                    ci_streak_manifest, "pr", "pull_request_run_source_present"
                ),
                "pr_owner_action": pr_owner_action,
                "nightly_owner_action": nightly_owner_action,
                "pr_claim_boundary": pr_claim_boundary,
                "nightly_claim_boundary": nightly_claim_boundary,
            },
            artifacts={
                "pr_ci": str(ci_pr_path),
                "nightly_ci": str(ci_nightly_path),
                "ci_streak_manifest": str(ci_streak_manifest_path),
                "ci_streak_intake_packet": str(ci_streak_intake_packet_path),
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

    freshness_summary = _summary(release_evidence_freshness)
    freshness_checks = {
        "release_evidence_freshness_report_present": bool(release_evidence_freshness),
        "release_evidence_freshness_contract_pass": _reason_pass(release_evidence_freshness),
        "source_commit_rows_match": _as_int(freshness_summary.get("source_commit_match_count"), 0)
        >= _as_int(freshness_summary.get("artifact_count"), 1),
        "engine_version_rows_present": _as_int(freshness_summary.get("engine_version_present_count"), 0)
        >= _as_int(freshness_summary.get("artifact_count"), 1),
        "input_checksum_rows_present": _as_int(freshness_summary.get("input_checksum_present_count"), 0)
        >= _as_int(freshness_summary.get("artifact_count"), 1),
        "reuse_marker_rows_present": _as_int(freshness_summary.get("reuse_marker_present_count"), 0)
        >= _as_int(freshness_summary.get("artifact_count"), 1),
        "dependency_mtime_rows_pass": _as_int(freshness_summary.get("dependency_mtime_pass_count"), 0)
        >= _as_int(freshness_summary.get("artifact_count"), 1),
    }
    freshness_blockers = (
        [str(row) for row in _as_list(release_evidence_freshness.get("blockers"))]
        if release_evidence_freshness
        else ["release_evidence_freshness_report_missing"]
    )
    rows.append(
        _area(
            "evidence_freshness",
            "Evidence Freshness",
            ok=bool(release_evidence_freshness and _reason_pass(release_evidence_freshness)),
            blockers=freshness_blockers,
            checks=freshness_checks,
            summary={
                "artifact_count": freshness_summary.get("artifact_count"),
                "pass_count": freshness_summary.get("pass_count"),
                "blocker_count": freshness_summary.get("blocker_count"),
                "current_source_commit_sha": release_evidence_freshness.get("current_source_commit_sha", ""),
                "max_age_days": release_evidence_freshness.get("max_age_days"),
            },
            artifacts={"release_evidence_freshness": str(release_evidence_freshness_path)},
            claim_boundary=(
                "Release evidence freshness is a metadata and dependency-recency audit. It does not rerun "
                "heavy validation; fresh full-validation lanes remain required for Level 3 promotion."
            ),
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
    residual_level3_contract_pass = bool(residual_level3.get("contract_pass", False))
    residual_level3_status = str(residual_level3.get("status", "")).strip().lower()
    residual_level3_reason_code = str(residual_level3.get("reason_code", "")).strip().upper()
    residual_level3_blockers = [
        str(item) for item in _as_list(residual_level3.get("blockers")) if str(item).strip()
    ]
    residual_level3_green = bool(
        residual_level3_contract_pass
        and residual_level3_status == "ready"
        and residual_level3_reason_code == "PASS"
    )
    residual_level3_artifact_present = residual_level3_status_path.exists()
    residual_area_checks = {
        "hard_residual_pass": bool(
            residual_checks.get("residual_top_hard_pass", False)
            and residual_checks.get("residual_drift_hard_pass", False)
        ),
        "recommended_residual_pass": bool(residual_checks.get("recommended_residual_pass", False)),
        "fallback_rate_limited_pass": fallback_rate <= max_residual_fallback_rate,
        "fallback_rate_ga_pass": fallback_rate <= ga_residual_fallback_rate,
        "residual_level3_status_present": residual_level3_artifact_present,
        "residual_level3_status_green": residual_level3_green,
    }
    residual_area_blockers = [
        *(["hard_residual_not_green"] if not residual_area_checks["hard_residual_pass"] else []),
        *(["recommended_residual_not_green"] if not residual_area_checks["recommended_residual_pass"] else []),
        *(["fallback_rate_gt_5pct"] if not residual_area_checks["fallback_rate_limited_pass"] else []),
        *(
            ["residual_level3_status_missing"]
            if not residual_area_checks["residual_level3_status_present"]
            else []
        ),
        *(
            ["residual_level3_status_not_green"] + residual_level3_blockers
            if residual_level3_artifact_present and not residual_level3_green
            else []
        ),
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
                "residual_level3_status": residual_level3_status,
                "residual_level3_reason_code": residual_level3_reason_code,
                "residual_level3_blocker_count": len(residual_level3_blockers),
            },
            artifacts={
                "ndtha_residual": str(ndtha_residual_path),
                "residual_level3_status": str(residual_level3_status_path),
            },
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
    ux_new_user_summary = _summary(ux_new_user)
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
    human_completion_minutes = _first_float(
        ux_new_user,
        "completion_minutes",
        "sample_completion_minutes",
        "new_user_sample_completion_minutes",
    )
    ux_release_available = _reason_pass(ux_release)
    human_observation_pass = _reason_pass(ux_new_user)
    blocking_review_item_count = _as_int(
        ux_release_summary.get("blocking_review_item_count"),
        _as_int(viewer_quality_summary.get("review_item_count"), 1),
    )
    ux_checks = {
        "viewer_quality_gate_pass": _reason_pass(viewer_quality),
        "ux_release_readiness_report_pass": ux_release_available,
        "blocking_review_queue_zero_pass": blocking_review_item_count == 0,
        "automated_sample_rehearsal_30min_evidence_present": sample_completion_minutes is not None,
        "automated_sample_rehearsal_30min_pass": bool(
            sample_completion_minutes is not None and sample_completion_minutes <= 30.0
        ),
        "human_new_user_observation_pass": human_observation_pass,
        "human_new_user_sample_30min_evidence_present": human_completion_minutes is not None,
        "human_new_user_sample_30min_pass": bool(
            human_completion_minutes is not None and human_completion_minutes <= 30.0
        ),
        "viewer_performance_static_budget_pass": _reason_pass(viewer_perf),
    }
    ux_blockers = [
        *(["viewer_quality_gate_not_green"] if not ux_checks["viewer_quality_gate_pass"] else []),
        *(["ux_release_readiness_report_missing_or_failed"] if not ux_checks["ux_release_readiness_report_pass"] else []),
        *(["viewer_blocking_review_queue_not_empty"] if not ux_checks["blocking_review_queue_zero_pass"] else []),
        *(
            ["automated_sample_rehearsal_30min_missing"]
            if not ux_checks["automated_sample_rehearsal_30min_evidence_present"]
            else []
        ),
        *(
            ["automated_sample_rehearsal_gt_30min"]
            if sample_completion_minutes is not None and sample_completion_minutes > 30.0
            else []
        ),
        *(["human_new_user_observation_missing_or_failed"] if not ux_checks["human_new_user_observation_pass"] else []),
        *(
            ["human_new_user_30min_sample_evidence_missing"]
            if not ux_checks["human_new_user_sample_30min_evidence_present"]
            else []
        ),
        *(
            ["human_new_user_sample_gt_30min"]
            if human_completion_minutes is not None and human_completion_minutes > 30.0
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
                "sample_completion_minutes": human_completion_minutes,
                "automated_sample_completion_minutes": sample_completion_minutes,
                "human_sample_completion_minutes": human_completion_minutes,
                "human_observation_reason_code": str(ux_new_user.get("reason_code", "")),
                "human_observation_owner_action": str(ux_new_user_summary.get("owner_action", "")),
                "viewer_review_item_count": _as_int(viewer_quality_summary.get("review_item_count"), -1),
                "blocking_review_item_count": blocking_review_item_count,
                "ux_evidence_source": "ux_release_readiness_report" if ux_release else "viewer_quality_fallback",
            },
            artifacts={
                "viewer_quality": str(viewer_quality_path),
                "viewer_performance_budget": str(viewer_performance_budget_path),
                "ux_release_readiness": str(ux_release_readiness_path),
                "ux_new_user_observation": str(ux_new_user_observation_path),
            },
            claim_boundary=(
                "Automated browser rehearsal proves workflow operability only. PM UX release-area pass requires "
                "human new-user sample workflow observation evidence."
            ),
        )
    )

    runtime_packaging_checks = _checks(runtime_packaging)
    support_checks = _checks(support)
    support_pm_failure_bundle_coverage = _as_dict(support.get("pm_failure_bundle_coverage"))
    pm_blocker_summary = _summary(pm_blocker_register)
    pm_blocker_closure_summary = _summary(pm_blocker_closure_board)
    pm_blocker_register_open_count = _as_int(pm_blocker_summary.get("open_blocker_count"), 0)
    pm_blocker_register_release_area_count = _as_int(
        pm_blocker_summary.get("release_area_blocker_count"),
        pm_blocker_register_open_count,
    )
    pm_blocker_closure_open_count = _as_int(pm_blocker_closure_summary.get("open_blocker_count"), -1)
    support_export_archive = _as_dict(support.get("export_archive"))
    support_optional_sections = _as_dict(support.get("optional_sections"))
    limitation_manual_text = _read_text_or_empty(limitation_manual_path)
    support_area_checks = {
        "known_issue_or_limitation_register_present": limitation_manual_path.exists(),
        "known_issue_or_limitation_register_content_pass": _contains_terms(
            limitation_manual_text,
            LIMITATION_MANUAL_REQUIRED_TERMS,
        ),
        "pm_blocker_action_register_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "pm_release_blocker_action_register",
        ),
        "pm_blocker_closure_board_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "pm_release_blocker_closure_board",
        ),
        "pm_release_gate_completion_audit_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "pm_release_gate_completion_audit",
        ),
        "pm_release_gate_reviewer_handoff_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "pm_release_gate_reviewer_handoff",
        ),
        "pm_owner_evidence_request_packet_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "pm_owner_evidence_request_packet",
        ),
        "pm_failure_bundle_coverage_index_pass": bool(
            support_checks.get("pm_failure_bundle_coverage_pass", False)
            and support_pm_failure_bundle_coverage.get("coverage_pass", False)
        ),
        "pm_blocker_action_register_handoff_ready_pass": _handoff_ready_pass(pm_blocker_register),
        "pm_blocker_closure_board_handoff_ready_pass": _handoff_ready_pass(pm_blocker_closure_board),
        "pm_blocker_closure_board_register_count_match": (
            pm_blocker_closure_open_count == pm_blocker_register_open_count
        ),
        "ci_streak_intake_packet_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "ci_streak_intake_packet",
        ),
        "ci_streak_manifest_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "ci_streak_manifest",
        ),
        "github_actions_ci_streak_evidence_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "github_actions_ci_streak_evidence",
        ),
        "license_status_intake_packet_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "license_status_intake_packet",
        ),
        "license_status_closure_report_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "license_status_closure_report",
        ),
        "license_status_template_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "license_status_template",
        ),
        "frontend_dependency_audit_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "frontend_dependency_audit_report",
        ),
        "validation_manual_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "release_validation_manual",
        ),
        "limitation_manual_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "release_limitation_manual",
        ),
        "ux_new_user_observation_report_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "ux_new_user_observation_report",
        ),
        "ux_new_user_observation_intake_packet_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "ux_new_user_observation_intake_packet",
        ),
        "template_evidence_safety_report_present": template_evidence_safety_path.exists(),
        "template_evidence_safety_pass": _truthy_contract(template_evidence_safety),
        "template_evidence_safety_report_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "template_evidence_safety_report",
        ),
        "pm_release_reproduction_command_audit_present": pm_release_reproduction_command_audit_path.exists(),
        "pm_release_reproduction_command_audit_pass": _truthy_contract(pm_release_reproduction_command_audit),
        "pm_release_reproduction_command_audit_in_failure_bundle": _support_section_present(
            support_optional_sections,
            "pm_release_reproduction_command_audit",
        ),
        "one_click_failure_bundle_archive_present": bool(
            support_export_archive.get("available") and support_export_archive.get("sha256")
        ),
        "failure_bundle_archive_roundtrip_pass": bool(
            support_checks.get("archive_roundtrip_test_pass", False)
        ),
        "failure_bundle_export_pass": bool(
            _reason_pass(support)
            and support_checks.get("redaction_self_test_pass", False)
            and support_checks.get("bundle_roundtrip_test_pass", False)
            and support_checks.get("archive_roundtrip_test_pass", False)
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
            ["known_issue_or_limitation_register_incomplete"]
            if not support_area_checks["known_issue_or_limitation_register_content_pass"]
            else []
        ),
        *(
            ["pm_blocker_action_register_missing_from_failure_bundle"]
            if not support_area_checks["pm_blocker_action_register_in_failure_bundle"]
            else []
        ),
        *(
            ["pm_blocker_closure_board_missing_from_failure_bundle"]
            if not support_area_checks["pm_blocker_closure_board_in_failure_bundle"]
            else []
        ),
        *(
            ["pm_release_gate_completion_audit_missing_from_failure_bundle"]
            if not support_area_checks["pm_release_gate_completion_audit_in_failure_bundle"]
            else []
        ),
        *(
            ["pm_release_gate_reviewer_handoff_missing_from_failure_bundle"]
            if not support_area_checks["pm_release_gate_reviewer_handoff_in_failure_bundle"]
            else []
        ),
        *(
            ["pm_failure_bundle_coverage_index_incomplete"]
            if not support_area_checks["pm_failure_bundle_coverage_index_pass"]
            else []
        ),
        *(
            ["pm_blocker_action_register_handoff_not_ready"]
            if not support_area_checks["pm_blocker_action_register_handoff_ready_pass"]
            else []
        ),
        *(
            ["pm_blocker_closure_board_handoff_not_ready"]
            if not support_area_checks["pm_blocker_closure_board_handoff_ready_pass"]
            else []
        ),
        *(
            ["pm_blocker_closure_board_count_mismatch"]
            if not support_area_checks["pm_blocker_closure_board_register_count_match"]
            else []
        ),
        *(
            ["ci_streak_intake_packet_missing_from_failure_bundle"]
            if not support_area_checks["ci_streak_intake_packet_in_failure_bundle"]
            else []
        ),
        *(
            ["ci_streak_manifest_missing_from_failure_bundle"]
            if not support_area_checks["ci_streak_manifest_in_failure_bundle"]
            else []
        ),
        *(
            ["github_actions_ci_streak_evidence_missing_from_failure_bundle"]
            if not support_area_checks["github_actions_ci_streak_evidence_in_failure_bundle"]
            else []
        ),
        *(
            ["license_status_intake_packet_missing_from_failure_bundle"]
            if not support_area_checks["license_status_intake_packet_in_failure_bundle"]
            else []
        ),
        *(
            ["license_status_closure_report_missing_from_failure_bundle"]
            if not support_area_checks["license_status_closure_report_in_failure_bundle"]
            else []
        ),
        *(
            ["license_status_template_missing_from_failure_bundle"]
            if not support_area_checks["license_status_template_in_failure_bundle"]
            else []
        ),
        *(
            ["frontend_dependency_audit_missing_from_failure_bundle"]
            if not support_area_checks["frontend_dependency_audit_in_failure_bundle"]
            else []
        ),
        *(
            ["validation_manual_missing_from_failure_bundle"]
            if not support_area_checks["validation_manual_in_failure_bundle"]
            else []
        ),
        *(
            ["limitation_manual_missing_from_failure_bundle"]
            if not support_area_checks["limitation_manual_in_failure_bundle"]
            else []
        ),
        *(
            ["ux_new_user_observation_report_missing_from_failure_bundle"]
            if not support_area_checks["ux_new_user_observation_report_in_failure_bundle"]
            else []
        ),
        *(
            ["ux_new_user_observation_intake_packet_missing_from_failure_bundle"]
            if not support_area_checks["ux_new_user_observation_intake_packet_in_failure_bundle"]
            else []
        ),
        *(
            ["template_evidence_safety_report_missing"]
            if not support_area_checks["template_evidence_safety_report_present"]
            else []
        ),
        *(["template_evidence_safety_not_green"] if not support_area_checks["template_evidence_safety_pass"] else []),
        *(
            ["template_evidence_safety_report_missing_from_failure_bundle"]
            if not support_area_checks["template_evidence_safety_report_in_failure_bundle"]
            else []
        ),
        *(
            ["pm_release_reproduction_command_audit_missing"]
            if not support_area_checks["pm_release_reproduction_command_audit_present"]
            else []
        ),
        *(
            ["pm_release_reproduction_command_audit_not_green"]
            if not support_area_checks["pm_release_reproduction_command_audit_pass"]
            else []
        ),
        *(
            ["pm_release_reproduction_command_audit_missing_from_failure_bundle"]
            if not support_area_checks["pm_release_reproduction_command_audit_in_failure_bundle"]
            else []
        ),
        *(
            ["one_click_failure_bundle_archive_missing"]
            if not support_area_checks["one_click_failure_bundle_archive_present"]
            else []
        ),
        *(
            ["failure_bundle_archive_roundtrip_not_green"]
            if not support_area_checks["failure_bundle_archive_roundtrip_pass"]
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
                "pm_release_blocker_closure_board": str(
                    support_optional_sections.get("pm_release_blocker_closure_board", "")
                ),
                "pm_release_gate_completion_audit": str(
                    support_optional_sections.get("pm_release_gate_completion_audit", "")
                ),
                "pm_release_gate_reviewer_handoff": str(
                    support_optional_sections.get("pm_release_gate_reviewer_handoff", "")
                ),
                "pm_owner_evidence_request_packet": str(
                    support_optional_sections.get("pm_owner_evidence_request_packet", "")
                ),
                "pm_failure_bundle_coverage_index": str(
                    support_pm_failure_bundle_coverage.get("bundle_path", "")
                ),
                "pm_failure_bundle_coverage_index_sha256": str(
                    support_pm_failure_bundle_coverage.get("sha256", "")
                ),
                "pm_blocker_register_open_blocker_count": pm_blocker_register_open_count,
                "pm_blocker_register_release_area_blocker_count": pm_blocker_register_release_area_count,
                "pm_blocker_register_handoff_ready_count": _as_int(
                    pm_blocker_summary.get("handoff_ready_count"), 0
                ),
                "pm_blocker_register_handoff_not_ready_count": _as_int(
                    pm_blocker_summary.get("handoff_not_ready_count"), 0
                ),
                "pm_blocker_register_external_owner_input_ready_count": _as_int(
                    pm_blocker_summary.get("external_owner_input_ready_count"), 0
                ),
                "pm_blocker_closure_board_open_blocker_count": pm_blocker_closure_open_count,
                "pm_blocker_closure_board_handoff_ready_count": _as_int(
                    pm_blocker_closure_summary.get("handoff_ready_count"), 0
                ),
                "pm_blocker_closure_board_handoff_not_ready_count": _as_int(
                    pm_blocker_closure_summary.get("handoff_not_ready_count"), 0
                ),
                "pm_blocker_closure_board_external_owner_input_ready_count": _as_int(
                    pm_blocker_closure_summary.get("external_owner_input_ready_count"), 0
                ),
                "ci_streak_intake_packet": str(
                    support_optional_sections.get("ci_streak_intake_packet", "")
                ),
                "ci_streak_manifest": str(
                    support_optional_sections.get("ci_streak_manifest", "")
                ),
                "github_actions_ci_streak_evidence": str(
                    support_optional_sections.get("github_actions_ci_streak_evidence", "")
                ),
                "license_status_intake_packet": str(
                    support_optional_sections.get("license_status_intake_packet", "")
                ),
                "license_status_closure_report": str(
                    support_optional_sections.get("license_status_closure_report", "")
                ),
                "license_status_template": str(
                    support_optional_sections.get("license_status_template", "")
                ),
                "frontend_dependency_audit_report": str(
                    support_optional_sections.get("frontend_dependency_audit_report", "")
                ),
                "release_validation_manual": str(
                    support_optional_sections.get("release_validation_manual", "")
                ),
                "release_limitation_manual": str(
                    support_optional_sections.get("release_limitation_manual", "")
                ),
                "ux_new_user_observation_report": str(
                    support_optional_sections.get("ux_new_user_observation_report", "")
                ),
                "ux_new_user_observation_intake_packet": str(
                    support_optional_sections.get("ux_new_user_observation_intake_packet", "")
                ),
                "template_evidence_safety_report": str(template_evidence_safety_path),
                "template_evidence_safety_summary_line": str(template_evidence_safety.get("summary_line", "")),
                "template_evidence_safety_report_bundle_path": str(
                    support_optional_sections.get("template_evidence_safety_report", "")
                ),
                "pm_release_reproduction_command_audit": str(pm_release_reproduction_command_audit_path),
                "pm_release_reproduction_command_audit_summary_line": str(
                    pm_release_reproduction_command_audit.get("summary_line", "")
                ),
                "pm_release_reproduction_command_audit_command_count": _as_int(
                    _summary(pm_release_reproduction_command_audit).get("command_count"), 0
                ),
                "pm_release_reproduction_command_audit_violation_count": _as_int(
                    _summary(pm_release_reproduction_command_audit).get("violation_count"), 0
                ),
                "pm_release_reproduction_command_audit_bundle_path": str(
                    support_optional_sections.get("pm_release_reproduction_command_audit", "")
                ),
                "one_click_failure_bundle_archive": str(support_export_archive.get("path", "")),
                "one_click_failure_bundle_archive_sha256": str(support_export_archive.get("sha256", "")),
            },
            artifacts={
                "support_bundle": str(support_bundle_path),
                "pm_release_blocker_action_register": str(pm_blocker_action_register_path),
                "pm_release_blocker_closure_board": str(pm_blocker_closure_board_path),
                "template_evidence_safety": str(template_evidence_safety_path),
                "pm_release_reproduction_command_audit": str(pm_release_reproduction_command_audit_path),
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

    rows.append(_github_sync_area(github_sync_preflight_path))

    return rows


def build_report(
    *,
    ndtha_residual: Path = DEFAULT_NDTHA_RESIDUAL,
    residual_level3_status: Path = DEFAULT_RESIDUAL_LEVEL3_STATUS,
    element_material_breadth: Path = DEFAULT_ELEMENT_MATERIAL_BREADTH,
    ndtha_long_profile: Path = DEFAULT_NDTHA_LONG_PROFILE,
    solver_hip_e2e: Path = DEFAULT_SOLVER_HIP_E2E,
    runtime_policy: Path = DEFAULT_RUNTIME_POLICY,
    ci_pr: Path = DEFAULT_CI_PR,
    ci_nightly: Path = DEFAULT_CI_NIGHTLY,
    ci_streak_manifest: Path = DEFAULT_CI_STREAK_MANIFEST,
    ci_streak_intake_packet: Path = DEFAULT_CI_STREAK_INTAKE_PACKET,
    ci_require_ndtha: Path = DEFAULT_CI_REQUIRE_NDTHA,
    ci_require_hip: Path = DEFAULT_CI_REQUIRE_HIP,
    zero_copy_strict: Path = DEFAULT_ZERO_COPY_STRICT,
    measured_benchmark_breadth: Path = DEFAULT_MEASURED_BREADTH,
    external_benchmark_submission_readiness: Path = DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_READINESS,
    public_benchmark_source_of_truth: Path = DEFAULT_PUBLIC_BENCHMARK_SOURCE_OF_TRUTH,
    evidence_surface_dir: Path = DEFAULT_EVIDENCE_SURFACE_DIR,
    worst_case_report: Path = DEFAULT_WORST_CASE_REPORT,
    workflow_productization: Path = DEFAULT_WORKFLOW_PRODUCTIZATION,
    release_registry: Path = DEFAULT_RELEASE_REGISTRY,
    support_bundle: Path = DEFAULT_SUPPORT_BUNDLE,
    pm_release_blocker_action_register: Path = DEFAULT_PM_RELEASE_BLOCKER_ACTION_REGISTER,
    pm_release_blocker_closure_board: Path = DEFAULT_PM_RELEASE_BLOCKER_CLOSURE_BOARD,
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
    ux_new_user_observation: Path = DEFAULT_UX_NEW_USER_OBSERVATION,
    security_runbook: Path = DEFAULT_SECURITY_RUNBOOK,
    license_status: Path = DEFAULT_LICENSE_STATUS,
    license_status_closure: Path = DEFAULT_LICENSE_STATUS_CLOSURE,
    ai_orchestration_preflight: Path = DEFAULT_AI_ORCHESTRATION_PREFLIGHT,
    commercial_gap_ledger_status: Path = DEFAULT_COMMERCIAL_GAP_LEDGER_STATUS,
    gap_closure_status: Path = DEFAULT_GAP_CLOSURE_STATUS,
    ga_enterprise_readiness: Path = DEFAULT_GA_ENTERPRISE_READINESS,
    ga_enterprise_signoff_intake: Path = DEFAULT_GA_ENTERPRISE_SIGNOFF_INTAKE,
    paid_pilot_scope_guard: Path = DEFAULT_PAID_PILOT_SCOPE_GUARD,
    template_evidence_safety: Path = DEFAULT_TEMPLATE_EVIDENCE_SAFETY,
    pm_release_reproduction_command_audit: Path = DEFAULT_PM_RELEASE_REPRODUCTION_COMMAND_AUDIT,
    release_evidence_freshness: Path = DEFAULT_RELEASE_EVIDENCE_FRESHNESS,
    customer_shadow_evidence_status: Path = DEFAULT_CUSTOMER_SHADOW_EVIDENCE_STATUS,
    fresh_full_validation_lane_status: Path = DEFAULT_FRESH_FULL_VALIDATION_LANE_STATUS,
    validation_manual: Path = DEFAULT_VALIDATION_MANUAL,
    limitation_manual: Path = DEFAULT_LIMITATION_MANUAL,
    github_sync_preflight: Path | None = DEFAULT_GITHUB_DEVELOPMENT_SYNC_PREFLIGHT,
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
            pm_blocker_action_register_path=pm_release_blocker_action_register,
            pm_blocker_closure_board_path=pm_release_blocker_closure_board,
            template_evidence_safety_path=template_evidence_safety,
            pm_release_reproduction_command_audit_path=pm_release_reproduction_command_audit,
            release_evidence_freshness_path=release_evidence_freshness,
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
    paid_pilot_scope = _load_json(paid_pilot_scope_guard)
    paid_pilot_scope_pass = _reason_pass(paid_pilot_scope)
    limited_ready = all(bool(row["ok"]) for row in milestones)
    technical_paid_pilot_candidate = bool(
        residual_basic_ok
        and core_basic_ok
        and runtime_ok
        and packaging_ok
        and measured_cases >= 20
    )
    paid_pilot_candidate = bool(technical_paid_pilot_candidate and paid_pilot_scope_pass)
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
        ci_streak_intake_packet_path=ci_streak_intake_packet,
        ci_require_ndtha_path=ci_require_ndtha,
        ci_require_hip_path=ci_require_hip,
        commercial_readiness_path=commercial_readiness,
        core_family_p95_report_path=core_family_p95_report,
        ndtha_residual_path=ndtha_residual,
        residual_level3_status_path=residual_level3_status,
        ndtha_long_profile_path=ndtha_long_profile,
        solver_hip_e2e_path=solver_hip_e2e,
        runtime_policy_path=runtime_policy,
        measured_benchmark_breadth_path=measured_benchmark_breadth,
        workflow_productization_path=workflow_productization,
        release_registry_path=release_registry,
        support_bundle_path=support_bundle,
        pm_blocker_action_register_path=pm_release_blocker_action_register,
        pm_blocker_closure_board_path=pm_release_blocker_closure_board,
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
        ux_new_user_observation_path=ux_new_user_observation,
        security_runbook_path=security_runbook,
        license_status_path=license_status,
        license_status_closure_path=license_status_closure,
        template_evidence_safety_path=template_evidence_safety,
        pm_release_reproduction_command_audit_path=pm_release_reproduction_command_audit,
        release_evidence_freshness_path=release_evidence_freshness,
        validation_manual_path=validation_manual,
        limitation_manual_path=limitation_manual,
        github_sync_preflight_path=github_sync_preflight,
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
    measured_benchmark_breadth_payload = _load_json(measured_benchmark_breadth)
    external_benchmark_submission_readiness_payload = _load_json(external_benchmark_submission_readiness)
    public_benchmark_source_of_truth_payload = _load_json(public_benchmark_source_of_truth)
    release_evidence_freshness_payload = _load_json(release_evidence_freshness)
    pm_blocker_register_payload = _load_json(pm_release_blocker_action_register)
    release_decision = _release_decision(
        release_allowed=full_release_gate_ready,
        blockers=blockers,
        release_area_blockers=release_area_blockers,
        measured_benchmark_breadth_payload=measured_benchmark_breadth_payload,
        external_benchmark_submission_readiness_payload=external_benchmark_submission_readiness_payload,
        public_benchmark_source_of_truth_payload=public_benchmark_source_of_truth_payload,
        release_evidence_freshness_payload=release_evidence_freshness_payload,
        pm_blocker_register=pm_blocker_register_payload,
        evidence_surface_dir=evidence_surface_dir,
    )
    ga_readiness = _load_json(ga_enterprise_readiness)
    customer_shadow = _load_json(customer_shadow_evidence_status)
    customer_shadow_summary = _summary(customer_shadow)
    customer_shadow_blockers = (
        [str(row) for row in _as_list(customer_shadow.get("blockers"))]
        if customer_shadow
        else ["customer_shadow_evidence_status_missing"]
    )
    fresh_full_validation = _load_json(fresh_full_validation_lane_status)
    fresh_full_validation_summary = _summary(fresh_full_validation)
    fresh_full_validation_blockers = (
        [str(row) for row in _as_list(fresh_full_validation.get("blockers"))]
        if fresh_full_validation
        else ["fresh_full_validation_lane_status_missing"]
    )
    ga_readiness_blockers = [str(row) for row in _as_list(ga_readiness.get("blockers"))]
    if not ga_readiness:
        ga_readiness_blockers = [
            "independent_vv_missing",
            "family_validation_manual_signoff_missing",
            "customer_audit_failure_bundle_sla_missing",
            *(["ga_validation_case_count_lt_300"] if measured_cases < ga_validation_cases else []),
        ]
    ga_blockers = [
        *ga_readiness_blockers,
        *(f"customer_shadow::{item}" for item in customer_shadow_blockers),
        *(f"fresh_full_validation::{item}" for item in fresh_full_validation_blockers),
        *release_area_blockers,
    ]
    ga_enterprise_ready = bool(
        full_release_gate_ready
        and _reason_pass(ga_readiness)
        and not ga_readiness_blockers
        and _reason_pass(customer_shadow)
        and _reason_pass(fresh_full_validation)
    )
    ai_orchestration = _load_json(ai_orchestration_preflight)
    ai_orchestration_summary = _summary(ai_orchestration)
    commercial_gap_status = _load_json(commercial_gap_ledger_status)
    gap_closure = _load_json(gap_closure_status)
    commercial_gap_summary = _summary(commercial_gap_status)
    gap_closure_summary = _as_dict(gap_closure.get("full_gap_ledger_summary"))
    ga_readiness_summary = _summary(ga_readiness)
    ga_signoff_intake = _load_json(ga_enterprise_signoff_intake)
    if full_release_gate_ready:
        release_status = "LIMITED_RELEASE_READY"
    elif limited_ready:
        release_status = "LIMITED_MILESTONE_READY"
    else:
        release_status = "BLOCKED"
    if full_release_gate_ready:
        recommended_scope = "Limited Commercial release candidate"
    elif limited_ready:
        recommended_scope = (
            "Limited milestone evidence is green, but the broader PM release-area gate is still blocked; "
            "keep any use constrained to the paid-pilot scope guard until release-area blockers are closed."
        )
    elif technical_paid_pilot_candidate and paid_pilot_scope_pass:
        recommended_scope = (
            "Paid pilot / constrained customer PoC only: review-assist, specified structure families, "
            "specified workflow, and engine/reviewer evidence package required."
        )
    elif technical_paid_pilot_candidate:
        recommended_scope = (
            "Technical paid-pilot evidence is present, but paid-pilot scope guard evidence is missing or blocked; "
            "do not start a customer pilot until scoped product/contract language is attached."
        )
    else:
        recommended_scope = "Release blocked until core PM gates have green evidence."

    report_input_paths = _unique_paths(
        [
            *_artifact_paths_from_rows(milestones),
            *_artifact_paths_from_rows(release_area_matrix),
            ga_enterprise_readiness,
            fresh_full_validation_lane_status,
            ai_orchestration_preflight,
            commercial_gap_ledger_status,
            gap_closure_status,
            ga_enterprise_signoff_intake,
            paid_pilot_scope_guard,
            customer_shadow_evidence_status,
            external_benchmark_submission_readiness,
            public_benchmark_source_of_truth,
            *_evidence_surface_json_paths(evidence_surface_dir),
        ]
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "input_checksums": _input_checksums(report_input_paths),
        "reused_evidence": True,
        "reuse_policy": "status_rebuilt_from_pm_release_gate_input_receipts",
        "contract_pass": limited_ready,
        "milestone_gate_pass": limited_ready,
        "release_area_gate_ready": release_area_ready,
        "full_release_gate_ready": full_release_gate_ready,
        "paid_pilot_candidate": paid_pilot_candidate,
        "limited_commercial_milestone_ready": limited_ready,
        "limited_commercial_release_ready": full_release_gate_ready,
        "limited_commercial_ready": full_release_gate_ready,
        "ga_enterprise_ready": ga_enterprise_ready,
        "recommended_scope": recommended_scope,
        "summary_line": (
            f"PM release gate: {release_status} | "
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
        "release_decision": release_decision,
        "implementation_orchestration": {
            "cursor_opencode_worker_preflight_pass": _reason_pass(ai_orchestration),
            "artifacts": {"ai_orchestration_preflight": str(ai_orchestration_preflight)},
            "summary": {
                "cursor_worker_cli": str(ai_orchestration_summary.get("cursor_worker_cli", "")),
                "opencode_worker_cli": str(ai_orchestration_summary.get("opencode_worker_cli", "")),
                "opencode_version": str(ai_orchestration_summary.get("opencode_version", "")),
                "opencode_configured_model": str(ai_orchestration_summary.get("opencode_configured_model", "")),
                "opencode_configured_model_available": bool(
                    ai_orchestration_summary.get("opencode_configured_model_available", False)
                ),
                "opencode_assignment_routed_to_cursor": bool(
                    ai_orchestration_summary.get("opencode_assignment_routed_to_cursor", False)
                ),
                "opencode_assignment_cursor_model": str(
                    ai_orchestration_summary.get("opencode_assignment_cursor_model", "")
                ),
            },
            "claim_boundary": (
                "Cursor/OpenCode are implementation workers for scoped slices. Current OpenCode assignment may be "
                "routed to Cursor; model availability is local provider-registry evidence only, not proof of remote "
                "credentials, successful inference, worker execution, or release readiness. Codex still owns PM gate "
                "review, verification, and final acceptance."
            ),
        },
        "gap_ledger_status": {
            "full_gap_ledger_ready": bool(gap_closure.get("full_gap_ledger_ready")),
            "full_gap_ledger_status": str(gap_closure.get("full_gap_ledger_status", "")),
            "commercial_gap_status": str(commercial_gap_status.get("status", "")),
            "commercial_solver_gap_ready": bool(commercial_gap_status.get("commercial_solver_gap_ready", False)),
            "ai_engine_gap_ready": bool(commercial_gap_status.get("ai_engine_gap_ready", False)),
            "summary": {
                "total_count": _as_int(commercial_gap_summary.get("total_count"), 0),
                "closed_count": _as_int(commercial_gap_summary.get("closed_count"), 0),
                "partial_count": _as_int(commercial_gap_summary.get("partial_count"), 0),
                "open_count": _as_int(commercial_gap_summary.get("open_count"), 0),
                "external_blocked_count": _as_int(commercial_gap_summary.get("external_blocked_count"), 0),
                "gap_closure_closed_count": _as_int(gap_closure_summary.get("closed_count"), 0),
                "gap_closure_partial_count": _as_int(gap_closure_summary.get("partial_count"), 0),
                "gap_closure_external_blocked_count": _as_int(
                    gap_closure_summary.get("external_blocked_count"),
                    0,
                ),
            },
            "next_locally_closable_gaps": [
                str(item) for item in _as_list(commercial_gap_status.get("next_locally_closable_gaps"))
            ],
            "blockers": [str(item) for item in _as_list(commercial_gap_status.get("blockers"))],
            "artifacts": {
                "commercial_gap_ledger_status": str(commercial_gap_ledger_status),
                "gap_closure_status": str(gap_closure_status),
            },
            "claim_boundary": (
                "G1-G10 and AI-G1-AI-G10 ledger status is reported separately from PM M1-M5 milestone "
                "readiness. Partial, external-blocked, benchmark-bridge, and diagnostic frontier evidence "
                "must remain non-closing until the ledger status artifact marks the row closed."
            ),
        },
        "release_tiers": {
            "paid_pilot": paid_pilot_candidate,
            "technical_paid_pilot_candidate": technical_paid_pilot_candidate,
            "paid_pilot_scope_guard_pass": paid_pilot_scope_pass,
            "paid_pilot_scope_guard_report": str(paid_pilot_scope_guard),
            "paid_pilot_scope_guard_summary_line": str(paid_pilot_scope.get("summary_line", "")),
            "limited_commercial_milestone_ready": limited_ready,
            "limited_commercial_full_gate_ready": full_release_gate_ready,
            "ga_enterprise": ga_enterprise_ready,
            "ga_enterprise_evidence_gate_pass": _reason_pass(ga_readiness),
            "ga_enterprise_readiness_report": str(ga_enterprise_readiness),
            "ga_enterprise_readiness_summary_line": str(ga_readiness.get("summary_line", "")),
            "ga_enterprise_signoff_intake_packet": str(ga_enterprise_signoff_intake),
            "ga_enterprise_signoff_intake_summary_line": str(ga_signoff_intake.get("summary_line", "")),
            "customer_shadow_evidence_status": str(customer_shadow_evidence_status),
            "customer_shadow_completed_project_ready": _reason_pass(customer_shadow),
            "customer_shadow_summary": {
                "completed_shadow_case_count": customer_shadow_summary.get("completed_shadow_case_count"),
                "min_completed_shadow_cases": customer_shadow_summary.get("min_completed_shadow_cases"),
                "target_completed_shadow_cases": customer_shadow_summary.get("target_completed_shadow_cases"),
                "evidence_file_count": customer_shadow_summary.get("evidence_file_count"),
                "valid_evidence_file_count": customer_shadow_summary.get("valid_evidence_file_count"),
                "blocker_count": len(customer_shadow_blockers),
            },
            "fresh_full_validation_lane_status": str(fresh_full_validation_lane_status),
            "fresh_full_validation_ready": _reason_pass(fresh_full_validation),
            "fresh_full_validation_summary": {
                "lane_count": fresh_full_validation_summary.get("lane_count"),
                "lane_contract_pass_count": fresh_full_validation_summary.get("lane_contract_pass_count"),
                "fresh_validation_receipt_pass_count": fresh_full_validation_summary.get(
                    "fresh_validation_receipt_pass_count"
                ),
                "fresh_validation_receipt_present_count": fresh_full_validation_summary.get(
                    "fresh_validation_receipt_present_count"
                ),
                "blocker_count": fresh_full_validation_summary.get("blocker_count"),
            },
            "ga_validation_case_threshold": ga_validation_cases,
            "ga_validation_case_threshold_met": measured_cases >= ga_validation_cases,
            "ga_enterprise_blockers": ga_blockers,
            "ga_enterprise_owner_action": str(ga_readiness_summary.get("owner_action", "")),
            "ga_enterprise_note": (
                "GA still requires independent V&V, family validation manuals, signed release registry, "
                "customer audit/failure bundles, and support SLA; this report only verifies local evidence inputs."
            ),
        },
    }


def _markdown(payload: dict[str, Any]) -> str:
    release_decision = _as_dict(payload.get("release_decision"))
    science_surface_bottlenecks = _as_list(
        release_decision.get("science_evidence_surface_bottlenecks")
    )
    lines = [
        "# PM Release Gate",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `recommended_scope`: {payload['recommended_scope']}",
        f"- `paid_pilot_candidate`: `{payload['paid_pilot_candidate']}`",
        f"- `limited_commercial_milestone_ready`: `{payload['limited_commercial_milestone_ready']}`",
        f"- `limited_commercial_ready`: `{payload['limited_commercial_ready']}`",
        f"- `limited_commercial_release_ready`: `{payload['limited_commercial_release_ready']}`",
        f"- `release_area_gate_ready`: `{payload['release_area_gate_ready']}`",
        f"- `full_release_gate_ready`: `{payload['full_release_gate_ready']}`",
        f"- `ga_enterprise_ready`: `{payload['ga_enterprise_ready']}`",
        f"- `cursor_opencode_worker_preflight_pass`: "
        f"`{payload['implementation_orchestration']['cursor_opencode_worker_preflight_pass']}`",
        f"- `full_gap_ledger_status`: `{payload['gap_ledger_status']['full_gap_ledger_status']}`",
        f"- `commercial_gap_status`: `{payload['gap_ledger_status']['commercial_gap_status']}`",
        f"- `commercial_solver_gap_ready`: `{payload['gap_ledger_status']['commercial_solver_gap_ready']}`",
        f"- `ai_engine_gap_ready`: `{payload['gap_ledger_status']['ai_engine_gap_ready']}`",
        f"- `release_allowed`: `{release_decision.get('release_allowed', False)}`",
        f"- `blocked_release_count`: `{release_decision.get('blocked_release_count', 0)}`",
        f"- `first_blocker`: `{release_decision.get('first_blocker', '') or 'none'}`",
        f"- `operator_action_count`: `{release_decision.get('operator_action_count', 0)}`",
        f"- `approval_token_count`: `{release_decision.get('approval_token_count', 0)}`",
        f"- `stale_artifact_count`: `{release_decision.get('stale_artifact_count', 0)}`",
        f"- `evidence_surface_count`: `{release_decision.get('evidence_surface_count', 0)}`",
        f"- `missing_evidence_surface_count`: "
        f"`{release_decision.get('missing_evidence_surface_count', 0)}`",
        f"- `locked_evidence_surface_count`: `{release_decision.get('locked_evidence_surface_count', 0)}`",
        f"- `h_bond_evidence_surface_present`: "
        f"`{release_decision.get('h_bond_evidence_surface_present', False)}`",
        f"- `gpcr_evidence_surface_present`: "
        f"`{release_decision.get('gpcr_evidence_surface_present', False)}`",
        f"- `pocketmd_lite_science_product_surface_present`: "
        f"`{release_decision.get('pocketmd_lite_science_product_surface_present', False)}`",
        f"- `pocketmd_lite_product_surface_ready`: "
        f"`{release_decision.get('pocketmd_lite_product_surface_ready', False)}`",
        f"- `public_benchmark_ready`: `{release_decision.get('public_benchmark_ready', False)}`",
        f"- `public_benchmark_source_of_truth_ready`: "
        f"`{release_decision.get('public_benchmark_source_of_truth_ready', False)}`",
        f"- `public_benchmark_source_of_truth_status`: "
        f"`{release_decision.get('public_benchmark_source_of_truth_status', '') or 'unknown'}`",
        f"- `public_benchmark_source_of_truth_blockers`: "
        f"`{', '.join(release_decision.get('public_benchmark_source_of_truth_blockers', [])) or 'none'}`",
        f"- `broad_gpcr_family_claim_safe`: `{release_decision.get('broad_gpcr_family_claim_safe', False)}`",
        f"- `science_evidence_surface_bottlenecks`: "
        f"`{', '.join(str(item) for item in science_surface_bottlenecks) or 'none'}`",
        f"- `next_locally_closable_gaps`: "
        f"`{', '.join(payload['gap_ledger_status'].get('next_locally_closable_gaps', [])) or 'none'}`",
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
    parser.add_argument(
        "--residual-level3-status", type=Path, default=DEFAULT_RESIDUAL_LEVEL3_STATUS
    )
    parser.add_argument("--element-material-breadth", type=Path, default=DEFAULT_ELEMENT_MATERIAL_BREADTH)
    parser.add_argument("--ndtha-long-profile", type=Path, default=DEFAULT_NDTHA_LONG_PROFILE)
    parser.add_argument("--solver-hip-e2e", type=Path, default=DEFAULT_SOLVER_HIP_E2E)
    parser.add_argument("--runtime-policy", type=Path, default=DEFAULT_RUNTIME_POLICY)
    parser.add_argument("--ci-pr", type=Path, default=DEFAULT_CI_PR)
    parser.add_argument("--ci-nightly", type=Path, default=DEFAULT_CI_NIGHTLY)
    parser.add_argument("--ci-streak-manifest", type=Path, default=DEFAULT_CI_STREAK_MANIFEST)
    parser.add_argument("--ci-streak-intake-packet", type=Path, default=DEFAULT_CI_STREAK_INTAKE_PACKET)
    parser.add_argument("--ci-require-ndtha", type=Path, default=DEFAULT_CI_REQUIRE_NDTHA)
    parser.add_argument("--ci-require-hip", type=Path, default=DEFAULT_CI_REQUIRE_HIP)
    parser.add_argument("--zero-copy-strict", type=Path, default=DEFAULT_ZERO_COPY_STRICT)
    parser.add_argument("--measured-benchmark-breadth", type=Path, default=DEFAULT_MEASURED_BREADTH)
    parser.add_argument(
        "--external-benchmark-submission-readiness",
        type=Path,
        default=DEFAULT_EXTERNAL_BENCHMARK_SUBMISSION_READINESS,
    )
    parser.add_argument(
        "--public-benchmark-source-of-truth",
        type=Path,
        default=DEFAULT_PUBLIC_BENCHMARK_SOURCE_OF_TRUTH,
    )
    parser.add_argument("--evidence-surface-dir", type=Path, default=DEFAULT_EVIDENCE_SURFACE_DIR)
    parser.add_argument("--worst-case-report", type=Path, default=DEFAULT_WORST_CASE_REPORT)
    parser.add_argument("--workflow-productization", type=Path, default=DEFAULT_WORKFLOW_PRODUCTIZATION)
    parser.add_argument("--release-registry", type=Path, default=DEFAULT_RELEASE_REGISTRY)
    parser.add_argument("--support-bundle", type=Path, default=DEFAULT_SUPPORT_BUNDLE)
    parser.add_argument(
        "--pm-release-blocker-action-register",
        type=Path,
        default=DEFAULT_PM_RELEASE_BLOCKER_ACTION_REGISTER,
    )
    parser.add_argument(
        "--pm-release-blocker-closure-board",
        type=Path,
        default=DEFAULT_PM_RELEASE_BLOCKER_CLOSURE_BOARD,
    )
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
    parser.add_argument("--ux-new-user-observation", type=Path, default=DEFAULT_UX_NEW_USER_OBSERVATION)
    parser.add_argument("--security-runbook", type=Path, default=DEFAULT_SECURITY_RUNBOOK)
    parser.add_argument("--license-status", type=Path, default=DEFAULT_LICENSE_STATUS)
    parser.add_argument("--license-status-closure", type=Path, default=DEFAULT_LICENSE_STATUS_CLOSURE)
    parser.add_argument("--ai-orchestration-preflight", type=Path, default=DEFAULT_AI_ORCHESTRATION_PREFLIGHT)
    parser.add_argument("--commercial-gap-ledger-status", type=Path, default=DEFAULT_COMMERCIAL_GAP_LEDGER_STATUS)
    parser.add_argument("--gap-closure-status", type=Path, default=DEFAULT_GAP_CLOSURE_STATUS)
    parser.add_argument("--ga-enterprise-readiness", type=Path, default=DEFAULT_GA_ENTERPRISE_READINESS)
    parser.add_argument("--ga-enterprise-signoff-intake", type=Path, default=DEFAULT_GA_ENTERPRISE_SIGNOFF_INTAKE)
    parser.add_argument("--paid-pilot-scope-guard", type=Path, default=DEFAULT_PAID_PILOT_SCOPE_GUARD)
    parser.add_argument("--template-evidence-safety", type=Path, default=DEFAULT_TEMPLATE_EVIDENCE_SAFETY)
    parser.add_argument(
        "--pm-release-reproduction-command-audit",
        type=Path,
        default=DEFAULT_PM_RELEASE_REPRODUCTION_COMMAND_AUDIT,
    )
    parser.add_argument("--release-evidence-freshness", type=Path, default=DEFAULT_RELEASE_EVIDENCE_FRESHNESS)
    parser.add_argument(
        "--fresh-full-validation-lane-status",
        type=Path,
        default=DEFAULT_FRESH_FULL_VALIDATION_LANE_STATUS,
    )
    parser.add_argument(
        "--customer-shadow-evidence-status",
        type=Path,
        default=DEFAULT_CUSTOMER_SHADOW_EVIDENCE_STATUS,
    )
    parser.add_argument("--validation-manual", type=Path, default=DEFAULT_VALIDATION_MANUAL)
    parser.add_argument("--limitation-manual", type=Path, default=DEFAULT_LIMITATION_MANUAL)
    parser.add_argument(
        "--github-sync-preflight",
        type=Path,
        default=DEFAULT_GITHUB_DEVELOPMENT_SYNC_PREFLIGHT,
        help=(
            "Optional pre-generated GitHub development sync preflight JSON. "
            "Defaults to live local git-state evaluation without fetch or remote mutation."
        ),
    )
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
        residual_level3_status=args.residual_level3_status,
        element_material_breadth=args.element_material_breadth,
        ndtha_long_profile=args.ndtha_long_profile,
        solver_hip_e2e=args.solver_hip_e2e,
        runtime_policy=args.runtime_policy,
        ci_pr=args.ci_pr,
        ci_nightly=args.ci_nightly,
        ci_streak_manifest=args.ci_streak_manifest,
        ci_streak_intake_packet=args.ci_streak_intake_packet,
        ci_require_ndtha=args.ci_require_ndtha,
        ci_require_hip=args.ci_require_hip,
        zero_copy_strict=args.zero_copy_strict,
        measured_benchmark_breadth=args.measured_benchmark_breadth,
        external_benchmark_submission_readiness=args.external_benchmark_submission_readiness,
        public_benchmark_source_of_truth=args.public_benchmark_source_of_truth,
        evidence_surface_dir=args.evidence_surface_dir,
        worst_case_report=args.worst_case_report,
        workflow_productization=args.workflow_productization,
        release_registry=args.release_registry,
        support_bundle=args.support_bundle,
        pm_release_blocker_action_register=args.pm_release_blocker_action_register,
        pm_release_blocker_closure_board=args.pm_release_blocker_closure_board,
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
        ux_new_user_observation=args.ux_new_user_observation,
        security_runbook=args.security_runbook,
        license_status=args.license_status,
        license_status_closure=args.license_status_closure,
        ai_orchestration_preflight=args.ai_orchestration_preflight,
        commercial_gap_ledger_status=args.commercial_gap_ledger_status,
        gap_closure_status=args.gap_closure_status,
        ga_enterprise_readiness=args.ga_enterprise_readiness,
        ga_enterprise_signoff_intake=args.ga_enterprise_signoff_intake,
        paid_pilot_scope_guard=args.paid_pilot_scope_guard,
        template_evidence_safety=args.template_evidence_safety,
        pm_release_reproduction_command_audit=args.pm_release_reproduction_command_audit,
        release_evidence_freshness=args.release_evidence_freshness,
        customer_shadow_evidence_status=args.customer_shadow_evidence_status,
        fresh_full_validation_lane_status=args.fresh_full_validation_lane_status,
        validation_manual=args.validation_manual,
        limitation_manual=args.limitation_manual,
        github_sync_preflight=args.github_sync_preflight,
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
