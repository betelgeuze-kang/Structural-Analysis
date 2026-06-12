#!/usr/bin/env python3
"""Validate productization delivery evidence artifact contracts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "validate-productization-delivery-evidence.v1"

REQUIRED_FILES = (
    "delivery_evidence_bundle.json",
    "gap_closure_status.json",
    "commercial_solver_cross_validation.json",
    "proxy_solver_divergence_gate.json",
    "post_optimization_reanalysis_gate.json",
    "story_model_reanalysis.json",
    "mgt_native_reanalysis_pipeline.json",
    "mgt_global_fea_readiness_gate.json",
    "mgt_full_line_mesh_sparse_equilibrium.json",
    "mgt_full_frame_6dof_sparse_equilibrium.json",
    "mgt_pdelta_continuation_probe.json",
    "mgt_coarsened_authored_support_pdelta_probe.json",
    "mgt_uncoarsened_boundary_pdelta_probe.json",
    "mgt_uncoarsened_boundary_pdelta_secant_seed_probe.json",
    "mgt_direct_residual_newton_probe.json",
    "mgt_surface_membrane_tangent.json",
    "mgt_surface_shell_bending_tangent.json",
    "mgt_shell_calibration_benchmarks.json",
    "mgt_coupled_frame_surface_sparse_equilibrium.json",
    "mgt_coupled_frame_shell_sparse_equilibrium.json",
    "mgt_native_modal_buckling_solver.json",
    "mgt_beam_offset_support_receipt.json",
    "mgt_boundary_entity_support_receipt.json",
    "mgt_boundary_spring_tangent_receipt.json",
    "mgt_uncoarsened_boundary_global_equilibrium.json",
    "mgt_story_eccentricity_load_receipt.json",
    "mgt_coupled_frame_shell_story_eccentricity_equilibrium.json",
    "mgt_frame_material_nonlinear_tangent.json",
    "material_element_tangent_support_matrix.json",
    "mgt_element_local_axis_opening_semantics_receipt.json",
    "gpu_solver_claim_receipt.json",
    "gpu_rocm_workstation_receipt.json",
    "solver_runtime_backend_policy.json",
    "mgt_rocm_sparse_solver_probe.json",
    "gpu_newton_certification_checklist.json",
    "rh_closure_checklist.json",
    "rh_signed_closure_packet_template.json",
    "residual_holdout_closure_updates.json",
    "mgt_roundtrip_assembly_fingerprint.json",
    "ml_surrogate_checkpoint_manifest.json",
    "ml_multi_objective_status.json",
    "mgt_global_fea_mesh_contract_gate.json",
    "load_stage_semantics_contract.json",
    "load_stage_runtime_flow_receipt.json",
    "ai_engine_productization_contracts.json",
    "ai_physics_guard_execution.json",
    "optimization_productization_audit.json",
    "ai_input_code_guard_artifacts.json",
    "ai_input_semantic_normalization_receipt.json",
    "ai_code_reasoning_guard.json",
    "ai_decision_review_artifacts.json",
    "ai_decision_trace_ledger.json",
    "ai_review_queue.json",
    "kds_detailing_support_matrix.json",
    "solver_governance_support_contract.json",
    "commercial_gap_ledger_status.json",
    "rh_engineer_review_packet_template.html",
)


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _has_schema_version(payload: dict[str, Any]) -> bool:
    if str(payload.get("schema_version") or "").strip():
        return True
    for key in ("story_model_reanalysis", "mgt_provenance", "gpu_solver_claim"):
        inner = payload.get(key)
        if isinstance(inner, dict) and str(inner.get("schema_version") or "").strip():
            return True
    return False


def solver_runtime_backend_policy_errors(policy: dict[str, Any]) -> list[str]:
    """Return hard errors for the official commercial solver compute lane."""
    errors: list[str] = []
    if policy.get("schema_version") != "solver-runtime-backend-policy.v1":
        errors.append("solver_runtime_backend_policy_schema_invalid")
    if policy.get("status") != "ready":
        errors.append("solver_runtime_backend_policy_not_ready")
    if policy.get("official_solver_compute_backend") != "amd_rocm_hip":
        errors.append("solver_runtime_backend_policy_official_backend_not_amd_rocm_hip")
    if policy.get("official_solver_backend") != "amd_rocm_hip":
        errors.append("solver_runtime_backend_policy_official_backend_alias_not_amd_rocm_hip")
    if policy.get("official_solver_backend_family") != "rocm_hip":
        errors.append("solver_runtime_backend_policy_backend_family_not_rocm_hip")
    if policy.get("gpu_required_for_commercial_solver_closure") is not True:
        errors.append("solver_runtime_backend_policy_gpu_not_required_for_closure")
    if policy.get("nvidia_smi_required") is not False:
        errors.append("solver_runtime_backend_policy_nvidia_smi_required_for_amd_rocm")
    if policy.get("rocm_sparse_probe_present") is not True:
        errors.append("solver_runtime_backend_policy_rocm_sparse_probe_missing")
    if policy.get("cpu_diagnostic_promotes_solver_closure") is not False:
        errors.append("solver_runtime_backend_policy_cpu_diagnostic_can_promote_closure")
    if policy.get("cpu_solver_fallback_detected") is not False:
        errors.append("solver_runtime_backend_policy_cpu_solver_fallback_detected")
    if policy.get("cpu_fallback_allowed_for_official_solver_closure") is not False:
        errors.append("solver_runtime_backend_policy_cpu_fallback_can_promote_closure")
    if policy.get("cpu_reference_allowed_for_validation_replay") is not True:
        errors.append("solver_runtime_backend_policy_cpu_reference_replay_not_documented")
    return errors


def validate_productization_delivery_evidence(
    *,
    productization_dir: Path,
    require_bundle_ready: bool = True,
) -> dict[str, Any]:
    errors: list[str] = []
    missing: list[str] = []
    checked: dict[str, str] = {}

    for name in REQUIRED_FILES:
        path = productization_dir / name
        if not path.is_file():
            missing.append(name)
            continue
        if path.suffix.lower() == ".html":
            checked[name] = "present"
            continue
        payload = _load(path)
        if not _has_schema_version(payload):
            errors.append(f"{name}:missing_schema_version")
        checked[name] = str(payload.get("status") or payload.get("delivery_status") or "present")

    bundle = _load(productization_dir / "delivery_evidence_bundle.json")
    gap = _load(productization_dir / "gap_closure_status.json")
    commercial_gap = _load(productization_dir / "commercial_gap_ledger_status.json")
    solver_backend_policy = _load(productization_dir / "solver_runtime_backend_policy.json")
    if require_bundle_ready and bundle.get("status") != "ready":
        errors.append("delivery_evidence_bundle_not_ready")
    if gap.get("delivery_status") not in {"ready", "review_required"}:
        errors.append("gap_closure_status_invalid_delivery_status")
    if commercial_gap.get("status") not in {"open", "closed"}:
        errors.append("commercial_gap_ledger_status_invalid")
    errors.extend(solver_runtime_backend_policy_errors(solver_backend_policy))

    ok = not missing and not errors
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if ok else "fail",
        "productization_dir": str(productization_dir),
        "files_checked": len(checked),
        "files_missing": missing,
        "file_status": checked,
        "errors": errors,
        "bundle_status": bundle.get("status"),
        "delivery_status": gap.get("delivery_status"),
        "authority_holdout_status": gap.get("authority_holdout_status"),
        "full_gap_ledger_status": commercial_gap.get("status"),
        "full_gap_ledger_ready": bool(commercial_gap.get("full_gap_ledger_ready")),
        "solver_runtime_backend_policy": {
            "status": solver_backend_policy.get("status"),
            "official_solver_compute_backend": solver_backend_policy.get(
                "official_solver_compute_backend"
            ),
            "official_solver_backend": solver_backend_policy.get("official_solver_backend"),
            "official_solver_backend_family": solver_backend_policy.get(
                "official_solver_backend_family"
            ),
            "gpu_required_for_commercial_solver_closure": solver_backend_policy.get(
                "gpu_required_for_commercial_solver_closure"
            ),
            "torch_device_label_is_pytorch_rocm_compat_alias": solver_backend_policy.get(
                "torch_device_label_is_pytorch_rocm_compat_alias"
            ),
            "cpu_diagnostic_promotes_solver_closure": solver_backend_policy.get(
                "cpu_diagnostic_promotes_solver_closure"
            ),
            "cpu_solver_fallback_detected": solver_backend_policy.get(
                "cpu_solver_fallback_detected"
            ),
            "cpu_fallback_allowed_for_official_solver_closure": solver_backend_policy.get(
                "cpu_fallback_allowed_for_official_solver_closure"
            ),
        },
    }
