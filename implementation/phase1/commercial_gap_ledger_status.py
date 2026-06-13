#!/usr/bin/env python3
"""Status matrix for the commercial solver and AI-engine gap ledgers."""

from __future__ import annotations

import re
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "commercial-gap-ledger-status.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
KOREA_OPEN_DATA = REPO_ROOT / "implementation/phase1/open_data/korea"
RELEASE = REPO_ROOT / "implementation/phase1/release"

COMMERCIAL_DOC = DOCS / "commercial-structural-solver-product-gap-ledger.md"
AI_DOC = DOCS / "structural-analysis-ai-engine-gap-ledger.md"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _get(payload: dict[str, Any], *path: str, default: Any = None) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def _doc_ids(path: Path, prefix: str) -> list[str]:
    if not path.is_file():
        return []
    pattern = re.compile(rf"^###\s+({re.escape(prefix)}\d+)\.", re.MULTILINE)
    return pattern.findall(path.read_text(encoding="utf-8", errors="replace"))


def _status(ok: bool, partial: bool = False, *, external: bool = False) -> str:
    if ok:
        return "closed"
    if external:
        return "external_blocked"
    return "partial" if partial else "open"


def _positive_int(value: Any) -> bool:
    try:
        return int(value or 0) > 0
    except (TypeError, ValueError):
        return False


def inference_runtime_contract_closed(inference_receipt: dict[str, Any]) -> bool:
    runtime_budget = inference_receipt.get("runtime_budget_contract")
    if not isinstance(runtime_budget, dict):
        return False
    runtime_status = str(inference_receipt.get("status") or "").strip()
    parity_policy = str(runtime_budget.get("cpu_gpu_parity_policy") or "").strip()
    fallback_required = bool(inference_receipt.get("fallback_required")) or runtime_status in {
        "fallback",
        "fallback_required",
        "solver_fallback_required",
    }
    fallback_reason = str(inference_receipt.get("fallback_reason") or "").strip()
    return bool(
        inference_receipt.get("schema_version") == "ai-inference-runtime-receipt.v1"
        and runtime_status == "ready"
        and _positive_int(runtime_budget.get("latency_budget_ms"))
        and _positive_int(runtime_budget.get("memory_budget_mb"))
        and parity_policy
        in {"explicitly_blocked_until_validated_checkpoint", "required_before_production_promotion"}
        and (not fallback_required or bool(fallback_reason))
    )


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _direct_residual_probe_summary(payload: dict[str, Any]) -> dict[str, Any]:
    correction = payload.get("current_tangent_residual_row_correction")
    correction = correction if isinstance(correction, dict) else {}
    global_krylov = payload.get("matrix_free_global_krylov")
    global_krylov = global_krylov if isinstance(global_krylov, dict) else {}
    trust = payload.get("trust_region_line_search")
    trust = trust if isinstance(trust, dict) else {}
    hotspot_diagonal = payload.get("frame_hotspot_diagonal_newton_sweep")
    hotspot_diagonal = hotspot_diagonal if isinstance(hotspot_diagonal, dict) else {}
    hotspot_block = payload.get("frame_hotspot_block_lstsq_sweep")
    hotspot_block = hotspot_block if isinstance(hotspot_block, dict) else {}
    promotion_candidate = payload.get("promotion_candidate")
    promotion_candidate = promotion_candidate if isinstance(promotion_candidate, dict) else {}
    best_candidate = correction.get("best_candidate")
    best_candidate = best_candidate if isinstance(best_candidate, dict) else {}
    trust_best_candidate = trust.get("best_candidate")
    trust_best_candidate = (
        trust_best_candidate if isinstance(trust_best_candidate, dict) else {}
    )
    trust_iterations = trust.get("iterations")
    trust_iterations = trust_iterations if isinstance(trust_iterations, list) else []
    trust_last_iteration = (
        trust_iterations[-1] if trust_iterations and isinstance(trust_iterations[-1], dict) else {}
    )
    trust_gate_candidate = trust_last_iteration.get("best_gate_eligible_candidate")
    trust_gate_candidate = (
        trust_gate_candidate if isinstance(trust_gate_candidate, dict) else {}
    )
    global_best_candidate = global_krylov.get("best_candidate")
    global_best_candidate = (
        global_best_candidate if isinstance(global_best_candidate, dict) else {}
    )
    base = payload.get("base_direct_residual")
    base = base if isinstance(base, dict) else {}
    final = payload.get("final_direct_residual")
    final = final if isinstance(final, dict) else {}
    output_checkpoint = payload.get("output_final_checkpoint")
    output_checkpoint = output_checkpoint if isinstance(output_checkpoint, dict) else {}
    promotion_passes = payload.get("promotion_passes")
    promotion_passes = promotion_passes if isinstance(promotion_passes, list) else []
    return {
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "ready": payload.get("direct_residual_newton_ready"),
        "base_direct_residual_inf_n": _float_or_none(base.get("direct_residual_inf_n")),
        "final_direct_residual_inf_n": _float_or_none(final.get("direct_residual_inf_n")),
        "promoted_to_final_state": payload.get("promoted_to_final_state"),
        "promotion_mode": payload.get("promotion_mode"),
        "promotion_count": payload.get("promotion_count"),
        "max_promotions": payload.get("max_promotions"),
        "stop_reason": payload.get("stop_reason"),
        "promotion_candidate_direct_residual_inf_n": _float_or_none(
            promotion_candidate.get("direct_residual_inf_n")
        ),
        "promotion_candidate_alpha": _float_or_none(promotion_candidate.get("alpha")),
        "promotion_candidate_step_m": _float_or_none(
            promotion_candidate.get("step_m")
        ),
        "promotion_candidate_relative_increment": _float_or_none(
            promotion_candidate.get("relative_increment")
        ),
        "promotion_candidate_residual_gate_passed": (
            promotion_candidate.get("residual_gate_passed")
        ),
        "promotion_candidate_relative_increment_gate_passed": (
            promotion_candidate.get("relative_increment_gate_passed")
        ),
        "promotion_pass_base_direct_residual_inf_n": [
            _float_or_none(row.get("base_direct_residual_inf_n"))
            for row in promotion_passes
            if isinstance(row, dict)
        ],
        "promotion_pass_actual_direct_residual_inf_n": [
            _float_or_none(row.get("actual_direct_residual_inf_n"))
            for row in promotion_passes
            if isinstance(row, dict)
        ],
        "promotion_pass_relative_increment_gate_passed": [
            row.get("relative_increment_gate_passed")
            for row in promotion_passes
            if isinstance(row, dict)
        ],
        "frame_hotspot_diagonal_newton_selected_count": hotspot_diagonal.get(
            "selected_hotspot_row_count"
        ),
        "frame_hotspot_diagonal_newton_correction_inf_m": _float_or_none(
            hotspot_diagonal.get("correction_inf_m")
        ),
        "frame_hotspot_block_lstsq_selected_count": hotspot_block.get(
            "selected_hotspot_row_count"
        ),
        "frame_hotspot_block_lstsq_component_filter": hotspot_block.get(
            "component_filter"
        ),
        "frame_hotspot_block_lstsq_selected_component_counts": hotspot_block.get(
            "selected_hotspot_dominant_component_counts"
        ),
        "frame_hotspot_block_lstsq_support_size": hotspot_block.get("support_size"),
        "frame_hotspot_block_lstsq_correction_inf_m": _float_or_none(
            hotspot_block.get("correction_inf_m")
        ),
        "trust_region_accepted": trust.get("accepted"),
        "trust_region_accepted_iteration_count": trust.get("accepted_iteration_count"),
        "trust_region_best_candidate_direct_residual_inf_n": _float_or_none(
            trust_best_candidate.get("direct_residual_inf_n")
        ),
        "trust_region_best_candidate_relative_increment": _float_or_none(
            trust_best_candidate.get("relative_increment")
        ),
        "trust_region_best_candidate_residual_gate_passed": (
            trust_best_candidate.get("residual_gate_passed")
        ),
        "trust_region_best_candidate_relative_increment_gate_passed": (
            trust_best_candidate.get("relative_increment_gate_passed")
        ),
        "trust_region_gate_limited_alpha": _float_or_none(
            trust_last_iteration.get("gate_limited_alpha")
        ),
        "trust_region_best_gate_eligible_candidate_direct_residual_inf_n": (
            _float_or_none(trust_gate_candidate.get("direct_residual_inf_n"))
        ),
        "trust_region_best_gate_eligible_candidate_alpha": _float_or_none(
            trust_gate_candidate.get("alpha")
        ),
        "trust_region_best_gate_eligible_candidate_alpha_source": (
            trust_gate_candidate.get("alpha_source")
        ),
        "trust_region_best_gate_eligible_candidate_relative_increment": _float_or_none(
            trust_gate_candidate.get("relative_increment")
        ),
        "trust_region_best_gate_eligible_candidate_residual_gate_passed": (
            trust_gate_candidate.get("residual_gate_passed")
        ),
        "trust_region_best_gate_eligible_candidate_relative_increment_gate_passed": (
            trust_gate_candidate.get("relative_increment_gate_passed")
        ),
        "trust_region_best_gate_eligible_candidate_free_dof_set_stable": (
            trust_gate_candidate.get("free_dof_set_stable")
        ),
        "current_tangent_residual_row_correction_enabled": correction.get("enabled"),
        "current_tangent_residual_row_correction_accepted": correction.get("accepted"),
        "current_tangent_residual_row_promotion_count": correction.get("promotion_count"),
        "current_tangent_residual_row_stop_reason": correction.get("stop_reason"),
        "current_tangent_residual_row_target_mode": correction.get("target_mode"),
        "current_tangent_residual_row_element_neighbor_depth": correction.get(
            "element_neighbor_depth"
        ),
        "current_tangent_residual_row_jacobian_mode": correction.get("jacobian_mode"),
        "current_tangent_residual_row_fd_max_support_columns": correction.get(
            "finite_difference_max_support_columns"
        ),
        "current_tangent_residual_row_svd_max_condition": correction.get(
            "svd_max_condition"
        ),
        "matrix_free_global_krylov_enabled": global_krylov.get("enabled"),
        "matrix_free_global_krylov_attempted": global_krylov.get("attempted"),
        "matrix_free_global_krylov_accepted": global_krylov.get("accepted"),
        "matrix_free_global_krylov_stop_reason": global_krylov.get("stop_reason"),
        "matrix_free_global_krylov_scaling_mode": global_krylov.get("scaling_mode"),
        "matrix_free_global_krylov_preconditioner_mode": global_krylov.get(
            "preconditioner_mode"
        ),
        "matrix_free_global_krylov_preconditioner_regularization": _float_or_none(
            global_krylov.get("preconditioner_regularization")
        ),
        "matrix_free_global_krylov_preconditioner_solve_count": global_krylov.get(
            "preconditioner_solve_count"
        ),
        "matrix_free_global_krylov_preconditioner_solve_seconds": _float_or_none(
            global_krylov.get("preconditioner_solve_seconds")
        ),
        "matrix_free_global_krylov_column_scale_units": global_krylov.get(
            "column_scale_units"
        ),
        "matrix_free_global_krylov_minimum_relative_improvement": _float_or_none(
            global_krylov.get("minimum_relative_improvement")
        ),
        "matrix_free_global_krylov_allow_negative_alphas": global_krylov.get(
            "allow_negative_alphas"
        ),
        "matrix_free_global_krylov_max_alpha": _float_or_none(global_krylov.get("max_alpha")),
        "matrix_free_global_krylov_row_scale_inf": _float_or_none(
            global_krylov.get("row_scale_inf")
        ),
        "matrix_free_global_krylov_column_scale_inf_m": _float_or_none(
            global_krylov.get("column_scale_inf_m")
        ),
        "matrix_free_global_krylov_matvec_count": global_krylov.get("matvec_count"),
        "matrix_free_global_krylov_unstable_free_dof_probe_count": global_krylov.get(
            "unstable_free_dof_probe_count"
        ),
        "matrix_free_global_krylov_correction_inf_m": _float_or_none(
            global_krylov.get("correction_inf_m")
        ),
        "matrix_free_global_krylov_best_candidate_direct_residual_inf_n": _float_or_none(
            global_best_candidate.get("direct_residual_inf_n")
        ),
        "matrix_free_global_krylov_best_candidate_relative_improvement": _float_or_none(
            global_best_candidate.get("relative_improvement")
        ),
        "best_candidate_direct_residual_inf_n": _float_or_none(
            best_candidate.get("direct_residual_inf_n")
        ),
        "best_candidate_improvement_inf_n": _float_or_none(
            best_candidate.get("improvement_inf_n")
        ),
        "best_candidate_relative_improvement": _float_or_none(
            best_candidate.get("relative_improvement")
        ),
        "best_candidate_target_row_count": best_candidate.get("target_row_count"),
        "best_candidate_configured_target_count": best_candidate.get(
            "configured_target_count"
        ),
        "best_candidate_support_column_count": best_candidate.get(
            "support_column_count"
        ),
        "best_candidate_support_size": best_candidate.get("support_size"),
        "best_candidate_alpha": _float_or_none(best_candidate.get("alpha")),
        "best_candidate_residual_gate_passed": best_candidate.get("residual_gate_passed"),
        "best_candidate_relative_increment_gate_passed": best_candidate.get(
            "relative_increment_gate_passed"
        ),
        "output_final_checkpoint_written": output_checkpoint.get("written"),
        "output_final_checkpoint_path": output_checkpoint.get("path"),
        "output_final_checkpoint_reason": output_checkpoint.get("reason"),
        "blockers": payload.get("blockers"),
    }


def _translation_frontier_followup_series(productization: Path) -> dict[str, Any]:
    pattern = re.compile(
        r"mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup(\d+)_probe\.json$"
    )
    rows: list[dict[str, Any]] = []
    for path in sorted(
        productization.glob(
            "mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup*_probe.json"
        )
    ):
        match = pattern.match(path.name)
        if not match:
            continue
        followup_index = int(match.group(1))
        payload = _load(path)
        summary = _direct_residual_probe_summary(payload)
        component_path = (
            productization
            / f"mgt_residual_jacobian_post_block_rows21_support32_translation_followup{followup_index}_component_probe.json"
        )
        component = _load(component_path)
        breakdown = component.get("residual_component_breakdown")
        breakdown = breakdown if isinstance(breakdown, dict) else {}
        rows.append(
            {
                "followup_index": followup_index,
                "probe_file": path.name,
                "component_probe_file": component_path.name if component_path.is_file() else None,
                "status": summary.get("status"),
                "ready": summary.get("ready"),
                "base_direct_residual_inf_n": summary.get("base_direct_residual_inf_n"),
                "final_direct_residual_inf_n": summary.get("final_direct_residual_inf_n"),
                "promotion_count": summary.get("promotion_count"),
                "promotion_pass_actual_direct_residual_inf_n": summary.get(
                    "promotion_pass_actual_direct_residual_inf_n"
                ),
                "promotion_pass_relative_increment_gate_passed": summary.get(
                    "promotion_pass_relative_increment_gate_passed"
                ),
                "promotion_candidate_alpha": summary.get("promotion_candidate_alpha"),
                "promotion_candidate_relative_increment": summary.get(
                    "promotion_candidate_relative_increment"
                ),
                "promotion_candidate_relative_increment_gate_passed": summary.get(
                    "promotion_candidate_relative_increment_gate_passed"
                ),
                "frame_hotspot_block_lstsq_support_size": summary.get(
                    "frame_hotspot_block_lstsq_support_size"
                ),
                "frame_hotspot_block_lstsq_selected_component_counts": summary.get(
                    "frame_hotspot_block_lstsq_selected_component_counts"
                ),
                "output_final_checkpoint_path": summary.get("output_final_checkpoint_path"),
                "component_status": component.get("status"),
                "component_only": component.get("component_only"),
                "component_base_residual_inf_n": component.get("base_residual_inf_n"),
                "component_inf_n": breakdown.get("component_inf_n"),
                "top_row_dominant_component_counts": breakdown.get(
                    "top_row_dominant_component_counts"
                ),
            }
        )
    rows.sort(key=lambda row: int(row["followup_index"]))
    finals = [
        _float_or_none(row.get("final_direct_residual_inf_n"))
        for row in rows
        if _float_or_none(row.get("final_direct_residual_inf_n")) is not None
    ]
    strictly_decreasing = all(
        later < earlier for earlier, later in zip(finals, finals[1:], strict=False)
    )
    latest = rows[-1] if rows else {}
    return {
        "series_schema": "mgt-translation-frontier-followup-series.v1",
        "count": int(len(rows)),
        "strictly_decreasing_final_residual": bool(strictly_decreasing),
        "latest_followup_index": latest.get("followup_index"),
        "latest_final_direct_residual_inf_n": latest.get("final_direct_residual_inf_n"),
        "latest_component_inf_n": latest.get("component_inf_n"),
        "rows": rows,
    }


def _hotspot_jvp_summary(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("residual_hotspot_tangent_fd_jvp_rows")
    rows = rows if isinstance(rows, list) else []
    evaluated = [
        row for row in rows if isinstance(row, dict) and bool(row.get("evaluated"))
    ]
    return {
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "base_residual_inf_n": _float_or_none(payload.get("base_residual_inf_n")),
        "fd_step": _float_or_none(payload.get("fd_step")),
        "evaluated_row_count": int(len(evaluated)),
        "max_relative_inf_error": max(
            (
                _float_or_none(row.get("relative_inf_error")) or 0.0
                for row in evaluated
            ),
            default=None,
        ),
        "max_relative_l2_error": max(
            (
                _float_or_none(row.get("relative_l2_error")) or 0.0
                for row in evaluated
            ),
            default=None,
        ),
        "min_action_cosine": min(
            (_float_or_none(row.get("action_cosine")) or 0.0 for row in evaluated),
            default=None,
        ),
        "max_selected_row_relative_error": max(
            (
                _float_or_none(row.get("selected_row_relative_error")) or 0.0
                for row in evaluated
            ),
            default=None,
        ),
        "first_evaluated_row": evaluated[0] if evaluated else {},
    }


def _adaptive_preconditioned_global_newton_summary(payload: dict[str, Any]) -> dict[str, Any]:
    controller = payload.get("controller")
    controller = controller if isinstance(controller, dict) else {}
    rows = payload.get("rows")
    candidate_rows = rows if isinstance(rows, list) else []
    best_row = min(
        (
            row
            for row in candidate_rows
            if _float_or_none(row.get("best_candidate_direct_residual_inf_n")) is not None
        ),
        key=lambda row: float(row["best_candidate_direct_residual_inf_n"]),
        default={},
    )
    return {
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "ready": payload.get("adaptive_preconditioned_global_newton_ready"),
        "promotion_count": controller.get("promotion_count"),
        "max_controller_steps": controller.get("max_controller_steps"),
        "stop_reason": controller.get("stop_reason"),
        "minimum_relative_improvement": _float_or_none(
            controller.get("minimum_relative_improvement")
        ),
        "runtime_budget_seconds": _float_or_none(
            controller.get("runtime_budget_seconds")
        ),
        "runtime_budget_exceeded": controller.get("runtime_budget_exceeded"),
        "secant_family_seed_enabled": controller.get("secant_family_seed_enabled"),
        "final_direct_residual_inf_n": _float_or_none(
            payload.get("final_direct_residual_inf_n")
        ),
        "row_count": len(candidate_rows),
        "best_candidate_direct_residual_inf_n": _float_or_none(
            best_row.get("best_candidate_direct_residual_inf_n")
        ),
        "best_candidate_relative_improvement": _float_or_none(
            best_row.get("best_candidate_relative_improvement")
        ),
        "best_candidate_tangent_regularization_factor": _float_or_none(
            best_row.get("tangent_regularization_factor")
        ),
        "rows": [
            {
                "step_index": row.get("step_index"),
                "tangent_regularization_factor": _float_or_none(
                    row.get("tangent_regularization_factor")
                ),
                "accepted": row.get("accepted"),
                "stop_reason": row.get("stop_reason"),
                "base_direct_residual_inf_n": _float_or_none(
                    row.get("base_direct_residual_inf_n")
                ),
                "final_direct_residual_inf_n": _float_or_none(
                    row.get("final_direct_residual_inf_n")
                ),
                "final_relative_improvement": _float_or_none(
                    row.get("final_relative_improvement")
                ),
                "component_acceptance": row.get("component_acceptance"),
                "best_candidate_direct_residual_inf_n": _float_or_none(
                    row.get("best_candidate_direct_residual_inf_n")
                ),
                "best_candidate_relative_improvement": _float_or_none(
                    row.get("best_candidate_relative_improvement")
                ),
                "best_candidate_alpha": _float_or_none(row.get("best_candidate_alpha")),
                "best_candidate_alpha_source": row.get("best_candidate_alpha_source"),
                "relative_increment_gate_passed": row.get(
                    "relative_increment_gate_passed"
                ),
                "preconditioner_regularization": _float_or_none(
                    row.get("preconditioner_regularization")
                ),
                "child_runtime_seconds": _float_or_none(
                    row.get("child_runtime_seconds")
                ),
                "runtime_budget_seconds": _float_or_none(
                    row.get("runtime_budget_seconds")
                ),
            }
            for row in candidate_rows
        ],
    }


def _rocalution_focused_sweep_summary(payload: dict[str, Any]) -> dict[str, Any]:
    sweep = payload.get("rocalution_preconditioned_krylov")
    if not isinstance(sweep, dict):
        return {}
    rows = sweep.get("candidate_rows")
    candidate_rows = rows if isinstance(rows, list) else []
    return {
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "ready": payload.get("ready"),
        "include_saamg": payload.get("include_saamg"),
        "selected_solver": sweep.get("solver"),
        "selected_preconditioner": sweep.get("preconditioner"),
        "selected_residual_inf_n": sweep.get("residual_inf_n"),
        "selected_threshold_n": sweep.get("threshold_n"),
        "candidate_count": len(candidate_rows),
        "candidate_rows": [
            {
                "solver": row.get("solver"),
                "preconditioner": row.get("preconditioner"),
                "ilu_p": row.get("ilu_p"),
                "ilu_q": row.get("ilu_q"),
                "amg_coarse_size": row.get("amg_coarse_size"),
                "amg_manual_smoothers": row.get("amg_manual_smoothers"),
                "residual_inf_n": row.get("residual_inf_n"),
                "threshold_n": row.get("threshold_n"),
                "breakdown": row.get("breakdown"),
                "iteration_count": _get(row, "rocalution_stats", "iteration_count"),
                "solver_status": _get(row, "rocalution_stats", "solver_status"),
                "amg_num_levels": _get(row, "rocalution_stats", "amg_num_levels"),
                "setup_mode": _get(row, "rocalution_stats", "setup_mode"),
            }
            for row in candidate_rows
        ],
    }


def _dof_block_schur_focused_summary(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows")
    candidate_rows = rows if isinstance(rows, list) else []
    residual_rows = [
        row
        for row in candidate_rows
        if _float_or_none(row.get("residual_inf_n")) is not None
    ]
    best_row = min(
        residual_rows,
        key=lambda row: float(row.get("residual_inf_n")),
        default={},
    )
    zero_weight_residuals = [
        float(row["residual_inf_n"])
        for row in residual_rows
        if _float_or_none(row.get("node_block_subdomain_smoother_weight")) == 0.0
    ]
    nonzero_weight_residuals = [
        float(row["residual_inf_n"])
        for row in residual_rows
        if (_float_or_none(row.get("node_block_subdomain_smoother_weight")) or 0.0) > 0.0
    ]
    zero_coarse_weight_residuals = [
        float(row["residual_inf_n"])
        for row in residual_rows
        if _float_or_none(row.get("node_block_coarse_weight")) == 0.0
    ]
    nonzero_coarse_weight_residuals = [
        float(row["residual_inf_n"])
        for row in residual_rows
        if (_float_or_none(row.get("node_block_coarse_weight")) or 0.0) > 0.0
    ]
    return {
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "row_count": len(candidate_rows),
        "best_residual_inf_n": _float_or_none(best_row.get("residual_inf_n")),
        "best_threshold_n": _float_or_none(best_row.get("threshold_n")),
        "best_node_block_subdomain_smoother_weight": _float_or_none(
            best_row.get("node_block_subdomain_smoother_weight")
        ),
        "best_node_block_subdomain_smoother_update_mode": best_row.get(
            "node_block_subdomain_smoother_update_mode"
        ),
        "best_node_block_subdomain_smoother_max_dof_count": best_row.get(
            "node_block_subdomain_smoother_max_dof_count"
        ),
        "best_node_block_subdomain_smoother_storage_mode": best_row.get(
            "node_block_subdomain_smoother_storage_mode"
        ),
        "best_node_block_subdomain_smoother_block_count": best_row.get(
            "node_block_subdomain_smoother_block_count"
        ),
        "best_node_block_subdomain_smoother_max_width": best_row.get(
            "node_block_subdomain_smoother_max_width"
        ),
        "best_node_block_subdomain_smoother_truncated_count": best_row.get(
            "node_block_subdomain_smoother_truncated_count"
        ),
        "best_node_block_interface_pair_smoother_weight": _float_or_none(
            best_row.get("node_block_interface_pair_smoother_weight")
        ),
        "best_node_block_interface_pair_smoother_halo_depth_used": best_row.get(
            "node_block_interface_pair_smoother_halo_depth_used"
        ),
        "best_node_block_interface_pair_smoother_update_mode": best_row.get(
            "node_block_interface_pair_smoother_update_mode"
        ),
        "best_node_block_interface_pair_smoother_block_count": best_row.get(
            "node_block_interface_pair_smoother_block_count"
        ),
        "best_node_block_interface_pair_smoother_max_width": best_row.get(
            "node_block_interface_pair_smoother_max_width"
        ),
        "best_node_block_interface_pair_smoother_truncated_count": best_row.get(
            "node_block_interface_pair_smoother_truncated_count"
        ),
        "best_node_block_interface_pair_smoother_storage_mode": best_row.get(
            "node_block_interface_pair_smoother_storage_mode"
        ),
        "best_node_block_interface_pair_coarse_rebalance_passes": best_row.get(
            "node_block_interface_pair_coarse_rebalance_passes"
        ),
        "best_node_block_interface_pair_coarse_rebalance_weight": _float_or_none(
            best_row.get("node_block_interface_pair_coarse_rebalance_weight")
        ),
        "best_node_block_coarse_mode": best_row.get("node_block_coarse_mode"),
        "best_node_block_coarse_local_dof_filter": best_row.get(
            "node_block_coarse_local_dof_filter"
        ),
        "best_node_block_coarse_local_dof_filter_used": best_row.get(
            "node_block_coarse_local_dof_filter_used"
        ),
        "best_node_block_coarse_energy_modes_per_dof": best_row.get(
            "node_block_coarse_energy_modes_per_dof"
        ),
        "best_node_block_coarse_energy_mode_selection": best_row.get(
            "node_block_coarse_energy_mode_selection"
        ),
        "best_node_block_coarse_operator": best_row.get("node_block_coarse_operator"),
        "best_node_block_coarse_weight": _float_or_none(best_row.get("node_block_coarse_weight")),
        "best_node_block_coarse_load_restriction_target": best_row.get(
            "node_block_coarse_load_restriction_target"
        ),
        "best_node_block_coarse_basis_orthogonalization": best_row.get(
            "node_block_coarse_basis_orthogonalization"
        ),
        "best_node_block_coarse_basis_orthogonalization_used": best_row.get(
            "node_block_coarse_basis_orthogonalization_used"
        ),
        "best_node_block_coarse_basis_orthogonalization_dropped_column_count": best_row.get(
            "node_block_coarse_basis_orthogonalization_dropped_column_count"
        ),
        "best_node_block_coarse_harmonic_extension_weight": _float_or_none(
            best_row.get("node_block_coarse_harmonic_extension_weight")
        ),
        "best_node_block_coarse_harmonic_extension_steps": best_row.get(
            "node_block_coarse_harmonic_extension_steps"
        ),
        "best_node_block_coarse_harmonic_extension_dof_count": best_row.get(
            "node_block_coarse_harmonic_extension_dof_count"
        ),
        "best_node_block_coarse_schur_cycle_passes": best_row.get(
            "node_block_coarse_schur_cycle_passes"
        ),
        "best_node_block_coarse_schur_cycle_weight": _float_or_none(
            best_row.get("node_block_coarse_schur_cycle_weight")
        ),
        "best_node_block_coarse_correction_passes": best_row.get(
            "node_block_coarse_correction_passes"
        ),
        "best_node_block_coarse_smoothing_weight": _float_or_none(
            best_row.get("node_block_coarse_smoothing_weight")
        ),
        "best_node_block_coarse_smoothing_applied_steps": best_row.get(
            "node_block_coarse_smoothing_applied_steps"
        ),
        "best_node_block_coarse_column_count": best_row.get("node_block_coarse_column_count"),
        "best_node_block_coarse_load_restriction_applied": best_row.get(
            "node_block_coarse_load_restriction_applied"
        ),
        "best_node_block_coarse_load_restriction_column_count": best_row.get(
            "node_block_coarse_load_restriction_column_count"
        ),
        "best_node_block_coarse_secondary_mode": best_row.get(
            "node_block_coarse_secondary_mode"
        ),
        "best_node_block_coarse_secondary_weight": _float_or_none(
            best_row.get("node_block_coarse_secondary_weight")
        ),
        "best_node_block_coarse_secondary_correction_passes": best_row.get(
            "node_block_coarse_secondary_correction_passes"
        ),
        "best_node_block_coarse_secondary_column_count": best_row.get(
            "node_block_coarse_secondary_column_count"
        ),
        "best_node_block_coarse_secondary_load_restriction_applied": best_row.get(
            "node_block_coarse_secondary_load_restriction_applied"
        ),
        "best_node_block_coarse_secondary_load_restriction_column_count": best_row.get(
            "node_block_coarse_secondary_load_restriction_column_count"
        ),
        "best_node_block_coarse_boundary_node_count": best_row.get(
            "node_block_coarse_boundary_node_count"
        ),
        "best_node_block_coarse_interface_pair_count": best_row.get(
            "node_block_coarse_interface_pair_count"
        ),
        "best_node_block_coarse_energy_mode_count": best_row.get(
            "node_block_coarse_energy_mode_count"
        ),
        "best_node_block_coarse_energy_eigenvalue_head": best_row.get(
            "node_block_coarse_energy_eigenvalue_head"
        ),
        "best_residual_region_summary": best_row.get("residual_region_summary"),
        "zero_weight_best_residual_inf_n": min(zero_weight_residuals)
        if zero_weight_residuals
        else None,
        "nonzero_weight_best_residual_inf_n": min(nonzero_weight_residuals)
        if nonzero_weight_residuals
        else None,
        "nonzero_subdomain_smoother_worsened_zero_weight": bool(
            zero_weight_residuals
            and nonzero_weight_residuals
            and min(nonzero_weight_residuals) > min(zero_weight_residuals)
        ),
        "zero_coarse_weight_best_residual_inf_n": min(zero_coarse_weight_residuals)
        if zero_coarse_weight_residuals
        else None,
        "nonzero_coarse_weight_best_residual_inf_n": min(nonzero_coarse_weight_residuals)
        if nonzero_coarse_weight_residuals
        else None,
        "nonzero_coarse_worsened_zero_weight": bool(
            zero_coarse_weight_residuals
            and nonzero_coarse_weight_residuals
            and min(nonzero_coarse_weight_residuals) > min(zero_coarse_weight_residuals)
        ),
        "candidate_rows": [
            {
                "node_block_coarse_mode": row.get("node_block_coarse_mode"),
                "node_block_coarse_local_dof_filter": row.get(
                    "node_block_coarse_local_dof_filter"
                ),
                "node_block_coarse_local_dof_filter_used": row.get(
                    "node_block_coarse_local_dof_filter_used"
                ),
                "node_block_interface_pair_smoother_weight": row.get(
                    "node_block_interface_pair_smoother_weight"
                ),
                "node_block_interface_pair_smoother_halo_depth_used": row.get(
                    "node_block_interface_pair_smoother_halo_depth_used"
                ),
                "node_block_interface_pair_smoother_update_mode": row.get(
                    "node_block_interface_pair_smoother_update_mode"
                ),
                "node_block_interface_pair_smoother_block_count": row.get(
                    "node_block_interface_pair_smoother_block_count"
                ),
                "node_block_interface_pair_smoother_max_width": row.get(
                    "node_block_interface_pair_smoother_max_width"
                ),
                "node_block_interface_pair_smoother_truncated_count": row.get(
                    "node_block_interface_pair_smoother_truncated_count"
                ),
                "node_block_interface_pair_smoother_storage_mode": row.get(
                    "node_block_interface_pair_smoother_storage_mode"
                ),
                "node_block_interface_pair_coarse_rebalance_passes": row.get(
                    "node_block_interface_pair_coarse_rebalance_passes"
                ),
                "node_block_interface_pair_coarse_rebalance_weight": row.get(
                    "node_block_interface_pair_coarse_rebalance_weight"
                ),
                "node_block_coarse_energy_modes_per_dof": row.get(
                    "node_block_coarse_energy_modes_per_dof"
                ),
                "node_block_coarse_energy_mode_selection": row.get(
                    "node_block_coarse_energy_mode_selection"
                ),
                "node_block_coarse_operator": row.get("node_block_coarse_operator"),
                "node_block_coarse_weight": row.get("node_block_coarse_weight"),
                "node_block_coarse_load_restriction_target": row.get(
                    "node_block_coarse_load_restriction_target"
                ),
                "node_block_coarse_basis_orthogonalization": row.get(
                    "node_block_coarse_basis_orthogonalization"
                ),
                "node_block_coarse_basis_orthogonalization_used": row.get(
                    "node_block_coarse_basis_orthogonalization_used"
                ),
                "node_block_coarse_basis_orthogonalization_dropped_column_count": row.get(
                    "node_block_coarse_basis_orthogonalization_dropped_column_count"
                ),
                "node_block_coarse_harmonic_extension_weight": row.get(
                    "node_block_coarse_harmonic_extension_weight"
                ),
                "node_block_coarse_harmonic_extension_steps": row.get(
                    "node_block_coarse_harmonic_extension_steps"
                ),
                "node_block_coarse_harmonic_extension_dof_count": row.get(
                    "node_block_coarse_harmonic_extension_dof_count"
                ),
                "node_block_coarse_schur_cycle_passes": row.get(
                    "node_block_coarse_schur_cycle_passes"
                ),
                "node_block_coarse_schur_cycle_weight": row.get(
                    "node_block_coarse_schur_cycle_weight"
                ),
                "node_block_coarse_correction_passes": row.get(
                    "node_block_coarse_correction_passes"
                ),
                "node_block_coarse_smoothing_weight": row.get(
                    "node_block_coarse_smoothing_weight"
                ),
                "node_block_coarse_smoothing_applied_steps": row.get(
                    "node_block_coarse_smoothing_applied_steps"
                ),
                "node_block_coarse_column_count": row.get("node_block_coarse_column_count"),
                "node_block_coarse_load_restriction_applied": row.get(
                    "node_block_coarse_load_restriction_applied"
                ),
                "node_block_coarse_load_restriction_column_count": row.get(
                    "node_block_coarse_load_restriction_column_count"
                ),
                "node_block_coarse_secondary_mode": row.get(
                    "node_block_coarse_secondary_mode"
                ),
                "node_block_coarse_secondary_weight": row.get(
                    "node_block_coarse_secondary_weight"
                ),
                "node_block_coarse_secondary_correction_passes": row.get(
                    "node_block_coarse_secondary_correction_passes"
                ),
                "node_block_coarse_secondary_column_count": row.get(
                    "node_block_coarse_secondary_column_count"
                ),
                "node_block_coarse_secondary_load_restriction_applied": row.get(
                    "node_block_coarse_secondary_load_restriction_applied"
                ),
                "node_block_coarse_secondary_load_restriction_column_count": row.get(
                    "node_block_coarse_secondary_load_restriction_column_count"
                ),
                "node_block_coarse_boundary_node_count": row.get(
                    "node_block_coarse_boundary_node_count"
                ),
                "node_block_coarse_interface_pair_count": row.get(
                    "node_block_coarse_interface_pair_count"
                ),
                "node_block_coarse_energy_mode_count": row.get(
                    "node_block_coarse_energy_mode_count"
                ),
                "node_block_coarse_energy_eigenvalue_head": row.get(
                    "node_block_coarse_energy_eigenvalue_head"
                ),
                "node_block_subdomain_smoother_weight": row.get(
                    "node_block_subdomain_smoother_weight"
                ),
                "node_block_subdomain_smoother_update_mode": row.get(
                    "node_block_subdomain_smoother_update_mode"
                ),
                "node_block_subdomain_smoother_max_dof_count": row.get(
                    "node_block_subdomain_smoother_max_dof_count"
                ),
                "node_block_subdomain_smoother_storage_mode": row.get(
                    "node_block_subdomain_smoother_storage_mode"
                ),
                "node_block_subdomain_smoother_block_count": row.get(
                    "node_block_subdomain_smoother_block_count"
                ),
                "node_block_subdomain_smoother_max_width": row.get(
                    "node_block_subdomain_smoother_max_width"
                ),
                "node_block_subdomain_smoother_truncated_count": row.get(
                    "node_block_subdomain_smoother_truncated_count"
                ),
                "residual_inf_n": row.get("residual_inf_n"),
                "threshold_n": row.get("threshold_n"),
                "host_dense_solve_fallback_count": row.get("host_dense_solve_fallback_count"),
                "device_residency_ratio": row.get("device_residency_ratio"),
                "residual_region_summary": row.get("residual_region_summary"),
            }
            for row in candidate_rows
        ],
    }


def _pdelta_row_gate(row: dict[str, Any], value_key: str, gate_key: str, tolerance_key: str, default: float) -> bool | None:
    if gate_key in row:
        return bool(row.get(gate_key))
    value = _float_or_none(row.get(value_key))
    tolerance = _float_or_none(row.get(tolerance_key)) or default
    return bool(value is not None and value <= tolerance)


def _pdelta_row_summary(source: str, row: dict[str, Any]) -> dict[str, Any]:
    target = _float_or_none(row.get("target_load_scale"))
    residual = _float_or_none(row.get("best_residual_inf_n"))
    if residual is None:
        residual = _float_or_none(row.get("residual_inf_n"))
    relative_increment = _float_or_none(row.get("best_relative_increment"))
    if relative_increment is None:
        relative_increment = _float_or_none(row.get("relative_increment"))
    residual_gate = _pdelta_row_gate(
        row,
        "residual_inf_n",
        "residual_gate_passed_by_any",
        "residual_tolerance_n",
        1.0e-3,
    )
    if "best_residual_inf_n" in row and "residual_gate_passed_by_any" not in row:
        residual_gate = bool(residual is not None and residual <= 1.0e-3)
    increment_gate = _pdelta_row_gate(
        row,
        "relative_increment",
        "relative_increment_gate_passed_by_any",
        "relative_increment_tolerance",
        1.0e-4,
    )
    if "best_relative_increment" in row and "relative_increment_gate_passed_by_any" not in row:
        increment_gate = bool(relative_increment is not None and relative_increment <= 1.0e-4)
    return {
        "source": source,
        "attempt_index": row.get("attempt_index"),
        "target_load_scale": target,
        "micro_increment": _float_or_none(row.get("micro_increment")),
        "ready": bool(row.get("ready")),
        "accepted_as_path_state": bool(row.get("accepted_as_path_state") or row.get("ready")),
        "residual_inf_n": residual,
        "relative_increment": relative_increment,
        "residual_gate_passed": residual_gate,
        "relative_increment_gate_passed": increment_gate,
    }


def _pdelta_failure_mode(row: dict[str, Any] | None) -> str:
    if not row:
        return "not_observed"
    residual_gate = bool(row.get("residual_gate_passed"))
    increment_gate = bool(row.get("relative_increment_gate_passed"))
    if residual_gate and increment_gate:
        return "ready_row_not_accepted"
    if residual_gate and not increment_gate:
        return "fixed_point_increment_gate_failed"
    if increment_gate and not residual_gate:
        return "residual_gate_failed"
    return "residual_and_fixed_point_increment_gates_failed"


def _pdelta_frontier_diagnostic(pdelta_continuation: dict[str, Any]) -> dict[str, Any]:
    max_converged = _float_or_none(pdelta_continuation.get("max_converged_load_scale"))
    first_failed = _float_or_none(pdelta_continuation.get("first_failed_load_scale"))
    full_load_ready = bool(pdelta_continuation.get("full_load_pdelta_continuation_ready"))
    source_rows: list[dict[str, Any]] = []
    for source_key in (
        "adaptive_micro_continuation_probe",
        "secant_micro_continuation_probe",
        "fine_secant_micro_continuation_probe",
    ):
        probe = pdelta_continuation.get(source_key)
        if not isinstance(probe, dict):
            continue
        for row in probe.get("rows") or []:
            if isinstance(row, dict):
                summary = _pdelta_row_summary(source_key, row)
                if summary["target_load_scale"] is not None:
                    source_rows.append(summary)

    accepted = [
        row
        for row in source_rows
        if bool(row.get("accepted_as_path_state")) and row.get("target_load_scale") is not None
    ]
    failed_above_frontier = [
        row
        for row in source_rows
        if (
            not bool(row.get("accepted_as_path_state"))
            and row.get("target_load_scale") is not None
            and max_converged is not None
            and float(row["target_load_scale"]) > max_converged + 1.0e-12
        )
    ]
    last_accepted = (
        max(accepted, key=lambda row: float(row["target_load_scale"])) if accepted else None
    )
    next_failed = (
        min(failed_above_frontier, key=lambda row: float(row["target_load_scale"]))
        if failed_above_frontier
        else None
    )
    next_failed_load = _float_or_none((next_failed or {}).get("target_load_scale"))
    frontier_to_next_failed = (
        next_failed_load - max_converged
        if next_failed_load is not None and max_converged is not None
        else None
    )
    frontier_to_first_failed = (
        first_failed - max_converged
        if first_failed is not None and max_converged is not None
        else None
    )
    frontier_to_full_load = 1.0 - max_converged if max_converged is not None else None
    return {
        "ready": full_load_ready,
        "frontier_load_scale": max_converged,
        "first_direct_failed_load_scale": first_failed,
        "next_failed_load_scale_after_frontier": next_failed_load,
        "frontier_to_next_failed_increment": frontier_to_next_failed,
        "frontier_to_first_direct_failed_increment": frontier_to_first_failed,
        "frontier_to_full_load_increment": frontier_to_full_load,
        "frontier_fraction_of_full_load": max_converged,
        "frontier_fraction_of_first_direct_failed_load": (
            max_converged / first_failed
            if max_converged is not None and first_failed not in {None, 0.0}
            else None
        ),
        "last_accepted_micro_row": last_accepted,
        "next_failed_micro_row": next_failed,
        "next_failed_gate_mode": _pdelta_failure_mode(next_failed),
        "accepted_micro_row_count": len(accepted),
        "failed_micro_row_count": len(failed_above_frontier),
        "diagnosis": (
            "full_load_closed"
            if full_load_ready
            else "frontier_limited_before_full_load_consistent_newton_jacobian_required"
        ),
        "claim_boundary": (
            "Derived from existing P-Delta continuation rows. This clarifies the accepted frontier and "
            "the next failed gate, but it is not new nonlinear equilibrium closure evidence."
        ),
    }


def _pdelta_residual_jacobian_summary(pdelta_continuation: dict[str, Any]) -> dict[str, Any]:
    probe = pdelta_continuation.get("frontier_residual_jacobian_probe")
    if not isinstance(probe, dict):
        return {
            "ready": False,
            "observed": False,
            "diagnosis": "frontier_residual_jacobian_probe_missing",
        }
    base_residual = _float_or_none(probe.get("base_residual_inf_n"))
    best_residual = _float_or_none(probe.get("best_residual_inf_n"))
    residual_tolerance = _float_or_none(probe.get("residual_tolerance_n")) or 1.0e-3
    best_increment = _float_or_none(probe.get("best_fixed_point_relative_increment"))
    increment_tolerance = _float_or_none(probe.get("relative_increment_tolerance")) or 1.0e-4
    residual_gap_ratio = (
        best_residual / residual_tolerance
        if best_residual is not None and residual_tolerance > 0.0
        else None
    )
    residual_reduction_factor = _float_or_none(probe.get("best_residual_reduction_factor"))
    if residual_reduction_factor is None and base_residual not in {None, 0.0} and best_residual is not None:
        residual_reduction_factor = best_residual / max(float(base_residual), 1.0e-30)
    increment_gate_passed = bool(
        best_increment is not None and best_increment <= increment_tolerance
    )
    residual_gate_passed = bool(
        best_residual is not None and best_residual <= residual_tolerance
    )
    pass_rows = [row for row in (probe.get("pass_rows") or []) if isinstance(row, dict)]
    accepted_passes = [row for row in pass_rows if bool(row.get("accepted"))]
    return {
        "ready": bool(probe.get("ready")),
        "observed": True,
        "target_load_scale": _float_or_none(probe.get("target_load_scale")),
        "base_residual_inf_n": base_residual,
        "best_residual_inf_n": best_residual,
        "residual_tolerance_n": residual_tolerance,
        "residual_gap_ratio_to_tolerance": residual_gap_ratio,
        "residual_reduction_factor": residual_reduction_factor,
        "residual_gate_passed": residual_gate_passed,
        "best_fixed_point_relative_increment": best_increment,
        "relative_increment_tolerance": increment_tolerance,
        "relative_increment_gate_passed": increment_gate_passed,
        "requested_correction_passes": int(probe.get("requested_correction_passes") or 0),
        "correction_pass_count": int(probe.get("correction_pass_count") or 0),
        "accepted_correction_count": int(probe.get("accepted_correction_count") or len(accepted_passes)),
        "diagnosis": (
            "frontier_residual_jacobian_closed"
            if bool(probe.get("ready"))
            else "fixed_point_increment_small_but_direct_residual_gate_far_from_tolerance"
            if increment_gate_passed and not residual_gate_passed
            else "frontier_residual_jacobian_not_closed"
        ),
        "claim_boundary": (
            "Summarizes the existing frontier residual-Jacobian receipt. It is a compact gate-distance "
            "view only; it does not add new nonlinear equilibrium closure evidence."
        ),
    }


def _row(
    gap_id: str,
    title: str,
    *,
    ledger: str,
    status: str,
    blockers: list[str],
    evidence: dict[str, Any] | None = None,
    locally_closable: bool = True,
    next_gate: str = "",
) -> dict[str, Any]:
    return {
        "id": gap_id,
        "title": title,
        "ledger": ledger,
        "status": status,
        "closed": status == "closed",
        "locally_closable": locally_closable,
        "blockers": blockers,
        "evidence": evidence or {},
        "next_gate": next_gate,
    }


def _commercial_rows(productization_dir: Path | None = None) -> list[dict[str, Any]]:
    productization = Path(productization_dir or PRODUCTIZATION)
    native_3d = _load(productization / "mgt_global_fea_3d_native_solve.json")
    mesh = _get(native_3d, "mesh_3d_global_solve", default={})
    fingerprint = _get(mesh, "mesh_fingerprint", default={})
    full_line_sparse = _load(productization / "mgt_full_line_mesh_sparse_equilibrium.json")
    full_frame_6dof = _load(productization / "mgt_full_frame_6dof_sparse_equilibrium.json")
    pdelta_continuation = _load(productization / "mgt_pdelta_continuation_probe.json")
    coarsened_authored_support_pdelta = _load(
        productization / "mgt_coarsened_authored_support_pdelta_probe.json"
    )
    uncoarsened_boundary_pdelta = _load(
        productization / "mgt_uncoarsened_boundary_pdelta_probe.json"
    )
    uncoarsened_boundary_pdelta_checkpoint_resume = _load(
        productization / "mgt_uncoarsened_boundary_pdelta_checkpoint_resume_probe.json"
    )
    uncoarsened_boundary_pdelta_checkpoint_continuation = _load(
        productization / "mgt_uncoarsened_boundary_pdelta_checkpoint_continuation.json"
    )
    uncoarsened_boundary_pdelta_secant_seed = _load(
        productization / "mgt_uncoarsened_boundary_pdelta_secant_seed_probe.json"
    )
    equilibrium_newton_focused = _load(
        productization / "mgt_equilibrium_newton_focused_probe.json"
    )
    equilibrium_newton_state_scale = _load(
        productization / "mgt_equilibrium_newton_focused_state_scale_probe.json"
    )
    translation_frontier_followup57_timeout_diagnostic = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup57_timeout_diagnostic_probe.json"
    )
    residual_jacobian_consistency = _load(
        productization / "mgt_residual_jacobian_consistency_probe.json"
    )
    residual_jacobian_current_frontier_component = _load(
        productization / "mgt_residual_jacobian_current_frontier_component_probe.json"
    )
    residual_jacobian_current_frontier_frame_hotspot_sweep = _load(
        productization
        / "mgt_residual_jacobian_current_frontier_frame_hotspot_sweep_probe.json"
    )
    residual_jacobian_current_frontier_frame_hotspot_large_sweep = _load(
        productization
        / "mgt_residual_jacobian_current_frontier_frame_hotspot_large_sweep_probe.json"
    )
    residual_jacobian_current_frontier_frame_hotspot_jvp = _load(
        productization
        / "mgt_residual_jacobian_current_frontier_frame_hotspot_jvp_probe.json"
    )
    residual_jacobian_support128_followup11_component = _load(
        productization / "mgt_residual_jacobian_support128_followup11_component_probe.json"
    )
    residual_jacobian_support128_followup11_hotspot_jvp = _load(
        productization
        / "mgt_residual_jacobian_support128_followup11_hotspot_jvp_probe.json"
    )
    preconditioned_zero = _load(
        productization / "mgt_equilibrium_preconditioned_zero_probe.json"
    )
    preconditioned_continuation = _load(
        productization / "mgt_equilibrium_preconditioned_continuation_probe.json"
    )
    preconditioned_continuation_standardization = _load(
        productization
        / "mgt_equilibrium_preconditioned_continuation_checkpoint_standardization.json"
    )
    direct_residual_preconditioned_zero_seed = _load(
        productization / "mgt_direct_residual_preconditioned_zero_seed_base.json"
    )
    direct_residual_preconditioned_continuation_seed = _load(
        productization / "mgt_direct_residual_preconditioned_continuation_seed_base.json"
    )
    direct_residual_preconditioned_continuation_standard_seed = _load(
        productization
        / "mgt_direct_residual_preconditioned_continuation_standard_seed_base.json"
    )
    direct_residual_preconditioned_continuation_standard_rowcorr = _load(
        productization
        / "mgt_direct_residual_preconditioned_continuation_standard_rowcorr_probe.json"
    )
    pdelta_frontier_diagnostic = _pdelta_frontier_diagnostic(pdelta_continuation)
    pdelta_residual_jacobian_summary = _pdelta_residual_jacobian_summary(pdelta_continuation)
    surface_membrane = _load(productization / "mgt_surface_membrane_tangent.json")
    surface_shell_bending = _load(productization / "mgt_surface_shell_bending_tangent.json")
    shell_calibration = _load(productization / "mgt_shell_calibration_benchmarks.json")
    coupled_frame_surface = _load(productization / "mgt_coupled_frame_surface_sparse_equilibrium.json")
    coupled_frame_shell = _load(productization / "mgt_coupled_frame_shell_sparse_equilibrium.json")
    rocm_sparse_probe = _load(productization / "mgt_rocm_sparse_solver_probe.json")
    rocalution_shell_sweep = _load(productization / "mgt_rocalution_shell_preconditioner_sweep.json")
    rocalution_saamg_debug = _load(productization / "mgt_rocalution_shell_saamg_debug_sweep.json")
    dof_block_schur_large_ras_current_shell = _load(
        productization / "mgt_dof_block_schur_large_ras_current_shell_recycled_order_probe.json"
    )
    dof_block_schur_streamed_large_ras_shell = _load(
        productization / "mgt_dof_block_schur_streamed_large_ras_shell_probe.json"
    )
    dof_block_schur_multiplicative_ras_shell = _load(
        productization / "mgt_dof_block_schur_multiplicative_ras_shell_smoke.json"
    )
    dof_block_schur_interface_edge_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_coarse_shell_smoke.json"
    )
    dof_block_schur_interface_edge_shell_probe = _load(
        productization / "mgt_dof_block_schur_interface_edge_coarse_shell_probe.json"
    )
    dof_block_schur_interface_edge_smoothed_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_smoothed_shell_smoke.json"
    )
    dof_block_schur_interface_edge_smoothed_shell_probe = _load(
        productization / "mgt_dof_block_schur_interface_edge_smoothed_shell_probe.json"
    )
    dof_block_schur_interface_edge_repeated_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_repeated_coarse_shell_smoke.json"
    )
    dof_block_schur_interface_edge_repeated_shell_probe = _load(
        productization / "mgt_dof_block_schur_interface_edge_repeated_coarse_shell_probe.json"
    )
    dof_block_schur_interface_edge_rhs_weighted_shell_weight_sweep = _load(
        productization / "mgt_dof_block_schur_interface_edge_rhs_weighted_shell_weight_sweep_probe.json"
    )
    dof_block_schur_interface_edge_rhs_signed_shell_weight_sweep = _load(
        productization / "mgt_dof_block_schur_interface_edge_rhs_signed_shell_weight_sweep_probe.json"
    )
    dof_block_schur_interface_edge_rhs_enriched_shell_weight_sweep = _load(
        productization / "mgt_dof_block_schur_interface_edge_rhs_enriched_shell_weight_sweep_probe.json"
    )
    dof_block_schur_interface_edge_rhs_enriched_restricted_shell_weight_sweep = _load(
        productization / "mgt_dof_block_schur_interface_edge_rhs_enriched_restricted_shell_weight_sweep_probe.json"
    )
    dof_block_schur_interface_edge_rhs_enriched_restricted_shell_fine_weight = _load(
        productization / "mgt_dof_block_schur_interface_edge_rhs_enriched_restricted_shell_fine_weight_probe.json"
    )
    dof_block_schur_interface_edge_rhs_enriched_restricted_coupled_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_rhs_enriched_restricted_coupled_smoke.json"
    )
    dof_block_schur_interface_edge_rhs_enriched_restricted_coupled_current_single = _load(
        productization / "mgt_dof_block_schur_interface_edge_rhs_enriched_restricted_coupled_current_single_probe.json"
    )
    dof_block_schur_interface_edge_rhs_enriched_orthogonalized_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_rhs_enriched_orthogonalized_shell_smoke.json"
    )
    dof_block_schur_interface_edge_rhs_enriched_orthogonalized_coupled_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_rhs_enriched_orthogonalized_coupled_smoke.json"
    )
    dof_block_schur_interface_edge_energy_restricted_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_energy_restricted_shell_smoke.json"
    )
    dof_block_schur_interface_edge_geneo_restricted_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_geneo_restricted_shell_smoke.json"
    )
    dof_block_schur_interface_edge_geneo_mode_count_sweep_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_geneo_mode_count_sweep_shell_smoke.json"
    )
    dof_block_schur_interface_edge_geneo_selection_sweep_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_geneo_selection_sweep_shell_smoke.json"
    )
    dof_block_schur_interface_edge_geneo_weight_pass_sweep_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_geneo_weight_pass_sweep_shell_smoke.json"
    )
    dof_block_schur_interface_edge_geneo_schur_cycle_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_geneo_schur_cycle_shell_smoke.json"
    )
    dof_block_schur_interface_edge_geneo_harmonic_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_geneo_harmonic_shell_smoke.json"
    )
    dof_block_schur_interface_edge_geneo_harmonic_depth_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_geneo_harmonic_depth_shell_smoke.json"
    )
    dof_block_schur_interface_edge_geneo_harmonic_qr_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_geneo_harmonic_qr_shell_smoke.json"
    )
    dof_block_schur_interface_edge_geneo_harmonic_residual_restriction_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_geneo_harmonic_residual_restriction_shell_smoke.json"
    )
    dof_block_schur_interface_edge_geneo_harmonic_dof_filter_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_geneo_harmonic_dof_filter_shell_smoke.json"
    )
    dof_block_schur_interface_edge_geneo_harmonic_energy_orthogonalization_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_edge_geneo_harmonic_energy_orthogonalization_shell_smoke.json"
    )
    dof_block_schur_interface_pair_dd_smoother_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_pair_dd_smoother_shell_smoke.json"
    )
    dof_block_schur_interface_pair_dd_swept_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_pair_dd_swept_shell_smoke.json"
    )
    dof_block_schur_interface_pair_dd_coarse_rebalance_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_pair_dd_coarse_rebalance_shell_smoke.json"
    )
    dof_block_schur_interface_pair_dd_coarse_rebalance_weight_sweep_shell_smoke = _load(
        productization / "mgt_dof_block_schur_interface_pair_dd_coarse_rebalance_weight_sweep_shell_smoke.json"
    )
    dof_block_schur_rigid_body_current_coupled_smoke_baseline = _load(
        productization / "mgt_dof_block_schur_rigid_body_current_coupled_smoke_baseline.json"
    )
    dof_block_schur_rigid_body_restricted_interface_hybrid_coupled_smoke = _load(
        productization / "mgt_dof_block_schur_rigid_body_restricted_interface_hybrid_coupled_smoke.json"
    )
    dof_block_schur_rigid_body_restricted_interface_hybrid_coupled_tiny_smoke = _load(
        productization / "mgt_dof_block_schur_rigid_body_restricted_interface_hybrid_coupled_tiny_smoke.json"
    )
    dof_block_schur_residual_region_diagnostic_shell = _load(
        productization / "mgt_dof_block_schur_residual_region_diagnostic_shell_smoke.json"
    )
    crossval = _load(productization / "commercial_solver_cross_validation.json")
    native_modal = _load(productization / "mgt_native_modal_buckling_solver.json")
    bundle = _load(productization / "delivery_evidence_bundle.json")
    load_stage = _load(productization / "load_stage_semantics_contract.json")
    load_stage_runtime = _load(productization / "load_stage_runtime_flow_receipt.json")
    material_element_tangent = _load(productization / "material_element_tangent_support_matrix.json")
    frame_material_nonlinear = _load(productization / "mgt_frame_material_nonlinear_tangent.json")
    beam_offset_support = _load(productization / "mgt_beam_offset_support_receipt.json")
    local_axis_opening = _load(productization / "mgt_element_local_axis_opening_semantics_receipt.json")
    boundary_entity_support = _load(productization / "mgt_boundary_entity_support_receipt.json")
    boundary_spring_tangent = _load(productization / "mgt_boundary_spring_tangent_receipt.json")
    boundary_global = _load(productization / "mgt_uncoarsened_boundary_global_equilibrium.json")
    direct_residual_newton = _load(productization / "mgt_direct_residual_newton_probe.json")
    direct_residual_newton_followup48_replay = _load(
        productization / "mgt_direct_residual_newton_followup48_replay_probe.json"
    )
    direct_residual_newton_followup48_rowcorr_narrow = _load(
        productization / "mgt_direct_residual_newton_followup48_rowcorr_narrow_probe.json"
    )
    direct_residual_newton_followup48_rowcorr_largest_rows_support4 = _load(
        productization
        / "mgt_direct_residual_newton_followup48_rowcorr_largest_rows_support4_probe.json"
    )
    direct_residual_newton_followup48_rowcorr_largest_rows_support4_followup2 = _load(
        productization
        / "mgt_direct_residual_newton_followup48_rowcorr_largest_rows_support4_followup2_probe.json"
    )
    direct_residual_newton_followup48_rowcorr_largest_rows_fd_support4_timeout = _load(
        productization
        / "mgt_direct_residual_newton_followup48_rowcorr_largest_rows_fd_support4_timeout_diagnostic.json"
    )
    direct_residual_newton_followup56_external_checkpoint_replay = _load(
        productization
        / "mgt_direct_residual_newton_followup56_external_checkpoint_replay_probe.json"
    )
    direct_residual_newton_followup56_rowcorr_largest_rows_support4 = _load(
        productization
        / "mgt_direct_residual_newton_followup56_rowcorr_largest_rows_support4_probe.json"
    )
    direct_residual_newton_followup56_rowcorr_largest_rows_support4_followup2 = _load(
        productization
        / "mgt_direct_residual_newton_followup56_rowcorr_largest_rows_support4_followup2_probe.json"
    )
    direct_residual_newton_followup56_rowcorr_largest_rows_support8 = _load(
        productization
        / "mgt_direct_residual_newton_followup56_rowcorr_largest_rows_support8_probe.json"
    )
    direct_residual_newton_followup56_rowcorr_largest_rows_support4_directional_timeout = _load(
        productization
        / "mgt_direct_residual_newton_followup56_rowcorr_largest_rows_support4_directional_timeout_diagnostic.json"
    )
    direct_residual_newton_followup56_post_rowcorr_block_lstsq_translation_support32 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_followup56_rowcorr_support32_probe.json"
    )
    direct_residual_newton_followup56_post_rowcorr_block_lstsq_translation_support32_followup2 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_followup56_rowcorr_support32_followup2_probe.json"
    )
    direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support32 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_frame_frontier_post_followup56_rowcorr_support32_probe.json"
    )
    direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support32_followup2 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_frame_frontier_post_followup56_rowcorr_support32_followup2_probe.json"
    )
    direct_residual_post_frame_block_lstsq_translation_support32 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_frame_support32_probe.json"
    )
    direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support64 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_frame_frontier_post_followup56_rowcorr_support64_probe.json"
    )
    direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support64_followup2 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_frame_frontier_post_followup56_rowcorr_support64_followup2_probe.json"
    )
    direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support64_followup3 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_frame_frontier_post_followup56_rowcorr_support64_followup3_probe.json"
    )
    direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support64_followup4 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_frame_frontier_post_followup56_rowcorr_support64_followup4_probe.json"
    )
    direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support64_followup5 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_frame_frontier_post_followup56_rowcorr_support64_followup5_probe.json"
    )
    direct_residual_post_frame_support64_block_lstsq_translation_followup4 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_frame_support64_followup4_probe.json"
    )
    direct_residual_post_translation_support64_block_lstsq_frame_followup4 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_frame_frontier_post_translation_support64_followup4_probe.json"
    )
    direct_residual_post_frame_support64_block_lstsq_translation_support128 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_frame_support64_followup4_support128_probe.json"
    )
    direct_residual_post_frame_support64_block_lstsq_translation_support128_followup2 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_frame_support64_followup4_support128_followup2_probe.json"
    )
    direct_residual_post_frame_support64_block_lstsq_translation_support128_followup3 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_frame_support64_followup4_support128_followup3_probe.json"
    )
    direct_residual_post_frame_support64_block_lstsq_translation_support128_followup4 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_frame_support64_followup4_support128_followup4_probe.json"
    )
    direct_residual_post_frame_support64_block_lstsq_translation_support128_followup5 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_frame_support64_followup4_support128_followup5_probe.json"
    )
    direct_residual_post_frame_support64_block_lstsq_translation_support128_followup6 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_frame_support64_followup4_support128_followup6_probe.json"
    )
    direct_residual_post_frame_support64_block_lstsq_translation_support128_followup7 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_frame_support64_followup4_support128_followup7_probe.json"
    )
    direct_residual_post_frame_support64_block_lstsq_translation_support128_followup8 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_frame_support64_followup4_support128_followup8_probe.json"
    )
    direct_residual_post_frame_support64_block_lstsq_translation_support128_followup9 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_frame_support64_followup4_support128_followup9_probe.json"
    )
    direct_residual_post_frame_support64_block_lstsq_translation_support128_followup10 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_frame_support64_followup4_support128_followup10_probe.json"
    )
    direct_residual_post_frame_support64_block_lstsq_translation_support128_followup11 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_frame_support64_followup4_support128_followup11_probe.json"
    )
    direct_residual_post_frame_support64_block_lstsq_translation_support128_followup12 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_frame_support64_followup4_support128_followup12_probe.json"
    )
    direct_residual_post_frame_support64_block_lstsq_translation_support128_followup13 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_frame_support64_followup4_support128_followup13_probe.json"
    )
    direct_residual_row_element_block_target = _load(
        productization / "mgt_direct_residual_row_element_block_target_smoke.json"
    )
    direct_residual_row_element_patch_target = _load(
        productization / "mgt_direct_residual_row_element_patch_target_smoke.json"
    )
    direct_residual_row_element_patch_fd32 = _load(
        productization / "mgt_direct_residual_row_element_patch_fd32_smoke.json"
    )
    direct_residual_row_element_block_fd32_followup = _load(
        productization / "mgt_direct_residual_row_element_block_fd32_followup_smoke.json"
    )
    direct_residual_global_matrix_free_krylov = _load(
        productization / "mgt_direct_residual_global_matrix_free_krylov_smoke.json"
    )
    direct_residual_global_matrix_free_scaled_krylov = _load(
        productization / "mgt_direct_residual_global_matrix_free_scaled_krylov_smoke.json"
    )
    direct_residual_global_matrix_free_scaled_signed_krylov = _load(
        productization / "mgt_direct_residual_global_matrix_free_scaled_signed_krylov_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_floor = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_floor_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_2 = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_2_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_3 = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_3_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_4 = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_4_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_broader_basis = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_broader_basis_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e9 = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e9_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e7 = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e7_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e7_followup = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e7_followup_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg3e7 = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg3e7_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6 = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_2 = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_2_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_3 = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_3_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_4 = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_4_smoke.json"
    )
    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg3e6 = _load(
        productization
        / "mgt_direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg3e6_smoke.json"
    )
    direct_residual_adaptive_preconditioned_global_newton = _load(
        productization
        / "mgt_direct_residual_adaptive_preconditioned_global_newton_smoke.json"
    )
    direct_residual_adaptive_preconditioned_global_newton_secant_seed = _load(
        productization
        / "mgt_direct_residual_adaptive_preconditioned_global_newton_secant_seed_smoke.json"
    )
    direct_residual_adaptive_preconditioned_global_newton_secant_seed_followup = _load(
        productization
        / "mgt_direct_residual_adaptive_preconditioned_global_newton_secant_seed_followup_smoke.json"
    )
    direct_residual_adaptive_preconditioned_global_newton_secant_seed_followup_2 = _load(
        productization
        / "mgt_direct_residual_adaptive_preconditioned_global_newton_secant_seed_followup_2_smoke.json"
    )
    direct_residual_adaptive_preconditioned_global_newton_runtime_budget = _load(
        productization
        / "mgt_direct_residual_adaptive_preconditioned_global_newton_runtime_budget_smoke.json"
    )
    direct_residual_current_checkpoint_single_largest_row_current_tangent = _load(
        productization
        / "mgt_direct_residual_current_checkpoint_single_largest_row_current_tangent.json"
    )
    direct_residual_current_checkpoint_single_largest_row_current_tangent_replay = _load(
        productization
        / "mgt_direct_residual_current_checkpoint_single_largest_row_current_tangent_replay.json"
    )
    direct_residual_current_checkpoint_single_largest_row_current_tangent_followup = _load(
        productization
        / "mgt_direct_residual_current_checkpoint_single_largest_row_current_tangent_followup.json"
    )
    direct_residual_current_checkpoint_single_largest_row_fd_jacobian = _load(
        productization
        / "mgt_direct_residual_current_checkpoint_single_largest_row_fd_jacobian.json"
    )
    direct_residual_current_checkpoint_frame_element_block_current_tangent = _load(
        productization
        / "mgt_direct_residual_current_checkpoint_frame_element_block_current_tangent.json"
    )
    direct_residual_current_checkpoint_frame_element_block_fd_jacobian = _load(
        productization
        / "mgt_direct_residual_current_checkpoint_frame_element_block_fd_jacobian.json"
    )
    direct_residual_current_checkpoint_trust_iteration_strict_gate_probe = _load(
        productization
        / "mgt_direct_residual_current_checkpoint_trust_iteration_strict_gate_probe.json"
    )
    direct_residual_current_checkpoint_trust_iteration_strict_gate_probe_replay = _load(
        productization
        / "mgt_direct_residual_current_checkpoint_trust_iteration_strict_gate_probe_replay.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier = _load(
        productization / "mgt_frame_hotspot_diagonal_newton_current_frontier_probe.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_replay = _load(
        productization / "mgt_frame_hotspot_diagonal_newton_current_frontier_probe_replay.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_followup = _load(
        productization / "mgt_frame_hotspot_diagonal_newton_current_frontier_followup_probe.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_followup_replay = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_followup_probe_replay.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass = _load(
        productization / "mgt_frame_hotspot_diagonal_newton_current_frontier_multipass_probe.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass_replay = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_multipass_probe_replay.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass_followup = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_multipass_followup_probe.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass_followup_replay = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_multipass_followup_probe_replay.json"
    )
    direct_residual_frame_hotspot_signed_displacement_current_frontier = _load(
        productization / "mgt_frame_hotspot_signed_displacement_current_frontier_probe.json"
    )
    direct_residual_frame_hotspot_signed_displacement_current_frontier_replay = _load(
        productization
        / "mgt_frame_hotspot_signed_displacement_current_frontier_probe_replay.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_post_signed_probe.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_replay = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_post_signed_probe_replay.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup_probe.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup_replay = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup_probe_replay.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2 = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_probe.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_replay = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_probe_replay.json"
    )
    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_followup2 = _load(
        productization
        / "mgt_frame_hotspot_signed_displacement_current_frontier_post_followup2_probe.json"
    )
    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_followup2_replay = _load(
        productization
        / "mgt_frame_hotspot_signed_displacement_current_frontier_post_followup2_probe_replay.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_signed_followup = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_signed_followup_probe.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_signed_followup_replay = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_signed_followup_probe_replay.json"
    )
    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup = _load(
        productization
        / "mgt_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup_probe.json"
    )
    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup_replay = _load(
        productization
        / "mgt_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup_probe_replay.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_diagonal_signed_followup2 = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_post_diagonal_signed_followup2_probe.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_diagonal_signed_followup2_replay = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_post_diagonal_signed_followup2_probe_replay.json"
    )
    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup2 = _load(
        productization
        / "mgt_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup2_probe.json"
    )
    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup2_replay = _load(
        productization
        / "mgt_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup2_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_tiny_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_tiny_followup_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_batch = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_batch_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_batch_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_batch_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_wide8_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_wide8_followup_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_wide8_followup_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup2 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_wide8_followup2_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup2_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_wide8_followup2_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_followup = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_followup_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_followup_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_followup_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_gate_alpha_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_gate_alpha_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup2 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup2_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup2_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup2_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup3 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup3_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup3_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup3_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_support16 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_support16_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_support32 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_support32_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_rows4 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_rows4_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_rows4_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_rows4_probe_replay.json"
    )
    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_rows4 = _load(
        productization
        / "mgt_frame_hotspot_signed_displacement_current_frontier_post_rows4_probe.json"
    )
    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_rows4_replay = _load(
        productization
        / "mgt_frame_hotspot_signed_displacement_current_frontier_post_rows4_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_signed_rows4 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_signed_rows4_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_signed_rows4_rows4 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_signed_rows4_rows4_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_signed_rows4_rows4_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_signed_rows4_rows4_probe_replay.json"
    )
    direct_residual_current_frontier_frame_block_current_tangent_narrow_post_signed_rows4_rows4 = _load(
        productization
        / "mgt_direct_residual_current_frontier_frame_block_current_tangent_narrow_post_signed_rows4_rows4_probe.json"
    )
    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_tangent_narrow = _load(
        productization
        / "mgt_frame_hotspot_signed_displacement_current_frontier_post_tangent_narrow_probe.json"
    )
    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_tangent_narrow_replay = _load(
        productization
        / "mgt_frame_hotspot_signed_displacement_current_frontier_post_tangent_narrow_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_rows4 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_rows4_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_rows4_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_rows4_probe_replay.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_tangent_signed_rows4 = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_post_tangent_signed_rows4_probe.json"
    )
    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_tangent_signed_rows4_followup = _load(
        productization
        / "mgt_frame_hotspot_diagonal_newton_current_frontier_post_tangent_signed_rows4_followup_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_diagonal_followup_rows4 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_diagonal_followup_rows4_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_followup_rows4 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_followup_rows4_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_followup_rows4_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_followup_rows4_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows8_followup2 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows8_followup2_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows12_followup3 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows12_followup3_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows16_followup4 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows16_followup4_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup5 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup5_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup6 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup6_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup6_replay = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup6_probe_replay.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup7 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup7_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_followup7 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_followup7_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup7 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup7_probe.json"
    )
    residual_jacobian_post_block_rows21_support16_followup7_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support16_followup7_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup8 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup8_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup9 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup9_probe.json"
    )
    residual_jacobian_post_block_rows21_support16_followup9_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support16_followup9_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup10 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup10_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup11 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup11_probe.json"
    )
    residual_jacobian_post_block_rows21_support16_followup11_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support16_followup11_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup12 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup12_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup13 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup13_probe.json"
    )
    residual_jacobian_post_block_rows21_support16_followup13_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support16_followup13_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup16 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup16_probe.json"
    )
    residual_jacobian_post_block_rows21_support16_followup16_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support16_followup16_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup21 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup21_probe.json"
    )
    residual_jacobian_post_block_rows21_support16_followup21_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support16_followup21_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup31 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup31_probe.json"
    )
    residual_jacobian_post_block_rows21_support16_followup31_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support16_followup31_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support16_followup34 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support16_followup34_probe.json"
    )
    residual_jacobian_post_block_rows21_support16_translation_followup34_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support16_translation_followup34_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup35 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup35_probe.json"
    )
    residual_jacobian_post_block_rows21_support32_translation_followup35_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support32_translation_followup35_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support64_followup36 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support64_followup36_probe.json"
    )
    residual_jacobian_post_block_rows21_support64_translation_followup36_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support64_translation_followup36_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup37 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup37_probe.json"
    )
    residual_jacobian_post_block_rows21_support32_translation_followup37_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support32_translation_followup37_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup42 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup42_probe.json"
    )
    residual_jacobian_post_block_rows21_support32_translation_followup42_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support32_translation_followup42_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup47 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup47_probe.json"
    )
    residual_jacobian_post_block_rows21_support32_translation_followup47_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support32_translation_followup47_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup48 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup48_probe.json"
    )
    residual_jacobian_post_block_rows21_support32_translation_followup48_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support32_translation_followup48_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup49 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup49_probe.json"
    )
    residual_jacobian_post_block_rows21_support32_translation_followup49_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support32_translation_followup49_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup50 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup50_probe.json"
    )
    residual_jacobian_post_block_rows21_support32_translation_followup50_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support32_translation_followup50_component_probe.json"
    )
    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup51 = _load(
        productization
        / "mgt_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup51_probe.json"
    )
    residual_jacobian_post_block_rows21_support32_translation_followup51_component = _load(
        productization
        / "mgt_residual_jacobian_post_block_rows21_support32_translation_followup51_component_probe.json"
    )
    direct_residual_current_frontier_frame_block_current_tangent_narrow = _load(
        productization
        / "mgt_direct_residual_current_frontier_frame_block_current_tangent_narrow_probe.json"
    )
    direct_residual_current_frontier_frame_block_fd16_residual_weighted = _load(
        productization
        / "mgt_direct_residual_current_frontier_frame_block_fd16_residual_weighted_probe.json"
    )
    direct_residual_historical_adaptive_checkpoint_current_residual_replay_audit = _load(
        productization
        / "mgt_direct_residual_historical_adaptive_checkpoint_current_residual_replay_audit.json"
    )
    story_eccentricity_load = _load(productization / "mgt_story_eccentricity_load_receipt.json")
    coupled_story_eccentricity = _load(productization / "mgt_coupled_frame_shell_story_eccentricity_equilibrium.json")
    korea = _load(KOREA_OPEN_DATA / "korean_medium_large_ingest_receipt.json")
    korea_operator_attachment_queue = _load(
        KOREA_OPEN_DATA / "operator_attachment_manifest.queue.json"
    )
    korea_operator_attachment_queue_validation = _load(
        KOREA_OPEN_DATA / "operator_attachment_manifest.queue.validation_report.json"
    )
    independent = _load(RELEASE / "independent_product_readiness.json")
    workstation = _load(REPO_ROOT / "implementation/phase1/workstation_delivery_readiness.json")
    governance = _load(productization / "solver_governance_support_contract.json")
    ml = _load(productization / "ml_multi_objective_status.json")
    optimization_audit = _load(productization / "optimization_productization_audit.json")
    gpu = _load(productization / "gpu_solver_claim_receipt.json")
    rocm_gpu = _load(productization / "gpu_rocm_workstation_receipt.json")
    solver_runtime_backend_policy = _load(productization / "solver_runtime_backend_policy.json")
    kds_detailing = _load(productization / "kds_detailing_support_matrix.json")
    kds_rule = REPO_ROOT / "implementation/phase1/kds_rc_rule_engine.py"

    raw_beams = int(fingerprint.get("raw_beam_elements_available") or 0)
    solved_beams = int(fingerprint.get("beam_elements_solved") or 0)
    full_3d_closed = (
        bool(mesh.get("nonlinear_equilibrium"))
        and not bool(mesh.get("partial_connected_component_mesh"))
        and not bool(mesh.get("fell_back_to_linear_tangent"))
        and raw_beams > 0
        and solved_beams >= raw_beams
    )
    full_line_sparse_ready = (
        full_line_sparse.get("status") == "ready"
        and bool(full_line_sparse.get("full_line_mesh_sparse_elastic_equilibrium_ready"))
    )
    full_frame_6dof_ready = (
        full_frame_6dof.get("status") == "ready"
        and bool(full_frame_6dof.get("full_frame_6dof_sparse_elastic_equilibrium_ready"))
    )
    surface_membrane_ready = (
        surface_membrane.get("status") == "ready"
        and bool(surface_membrane.get("surface_membrane_tangent_ready"))
        and bool(surface_membrane.get("surface_membrane_smoke_solve_ready"))
    )
    coupled_frame_surface_ready = (
        coupled_frame_surface.get("status") == "ready"
        and bool(coupled_frame_surface.get("coupled_frame_surface_sparse_equilibrium_ready"))
    )
    coupled_frame_shell_ready = (
        coupled_frame_shell.get("status") == "ready"
        and bool(coupled_frame_shell.get("coupled_frame_shell_sparse_equilibrium_ready"))
        and bool(coupled_frame_shell.get("surface_shell_bending_drilling_coupled_ready"))
    )
    surface_shell_bending_ready = (
        surface_shell_bending.get("status") == "ready"
        and bool(surface_shell_bending.get("surface_shell_bending_drilling_smoke_ready"))
        and bool(surface_shell_bending.get("surface_shell_transverse_pressure_smoke_ready"))
    )
    shell_calibration_ready = (
        shell_calibration.get("status") == "ready"
        and bool(shell_calibration.get("shell_calibration_benchmarks_ready"))
    )
    frame_material_nonlinear_ready = (
        frame_material_nonlinear.get("status") == "ready"
        and bool(frame_material_nonlinear.get("frame_material_nonlinear_tangent_ready"))
        and bool(frame_material_nonlinear.get("bounded_material_tangent_global_smoke_ready"))
    )
    frame_local_axis_ready = bool(
        local_axis_opening.get("status") in {"ready", "partial"}
        and _get(local_axis_opening, "support", "frame_angle_parser_ready", default=False)
        and _get(local_axis_opening, "support", "frame_angle_solver_consumption_ready", default=False)
    )
    opening_runtime_ready = bool(
        _get(local_axis_opening, "support", "opening_runtime_semantics_ready", default=False)
    )
    generic_opening_cutout_ready = bool(
        _get(local_axis_opening, "support", "generic_opening_cutout_runtime_semantics_ready", default=False)
    )
    surface_membrane_material = (
        surface_membrane.get("surface_material_coverage")
        if isinstance(surface_membrane.get("surface_material_coverage"), dict)
        else {}
    )
    surface_shell_material = (
        surface_shell_bending.get("surface_material_coverage")
        if isinstance(surface_shell_bending.get("surface_material_coverage"), dict)
        else {}
    )
    surface_source_thickness_coverage_pct = max(
        float(surface_membrane_material.get("source_plate_thickness_coverage_pct") or 0.0),
        float(surface_shell_material.get("source_plate_thickness_coverage_pct") or 0.0),
    )
    surface_source_thickness_ready = bool(surface_source_thickness_coverage_pct >= 99.0)
    full_3d_partial = (
        bool(mesh.get("representative_component_nonlinear_equilibrium"))
        or solved_beams > 0
        or full_line_sparse_ready
        or full_frame_6dof_ready
        or surface_membrane_ready
        or coupled_frame_surface_ready
        or coupled_frame_shell_ready
        or surface_shell_bending_ready
        or shell_calibration_ready
        or frame_material_nonlinear_ready
    )

    modal_summary = crossval.get("modal_buckling_summary")
    modal_partial = isinstance(modal_summary, dict) and bool(modal_summary)
    native_modal_modes = int(_get(native_modal, "modal_solve", "mode_count", default=0) or 0)
    native_buckling_factor = float(_get(native_modal, "buckling_solve", "critical_load_factor", default=0.0) or 0.0)
    native_modal_buckling_closed = (
        native_modal.get("status") == "ready"
        and bool(native_modal.get("native_solver_ready"))
        and bool(native_modal.get("benchmark_contract_pass"))
        and native_modal_modes >= 3
        and native_buckling_factor > 1.0
    )

    ingest_summary = korea.get("summary") if isinstance(korea.get("summary"), dict) else {}
    per_source = korea.get("per_source") if isinstance(korea.get("per_source"), list) else []
    bridge_count = sum(1 for row in per_source if isinstance(row, dict) and row.get("attach_provenance") == "repo_benchmark_bridge")
    metadata_only = int(ingest_summary.get("metadata_only_count") or 0)
    real_mgt_ok = sum(
        1
        for row in per_source
        if isinstance(row, dict)
        and row.get("mgt_header_ok")
        and row.get("attach_provenance") == "operator_attached"
        and not row.get("blockers")
    )

    strict_gate = next(
        (
            gate
            for gate in independent.get("gates", [])
            if isinstance(gate, dict) and gate.get("label") == "Strict external and residual holdout evidence"
        ),
        {},
    )
    external_receipts = int(strict_gate.get("external_receipt_attached_count") or 0)
    residual_closed = int(strict_gate.get("residual_closed_count") or 0)

    runtime_gate = next(
        (
            gate
            for gate in independent.get("gates", [])
            if isinstance(gate, dict) and gate.get("label") == "Runtime production path"
        ),
        {},
    )
    rocm_sparse_closure_ready = bool(rocm_sparse_probe.get("rocm_sparse_solver_probe_ready"))
    g9_runtime_ready = bool(runtime_gate.get("ok")) and bool(
        gpu.get("gpu_newton_terminal_proven")
    )

    return [
        _row(
            "G1",
            "Full 3D Global FEA Core",
            ledger="commercial_solver",
            status=_status(full_3d_closed, full_3d_partial),
            blockers=[]
            if full_3d_closed
            else [
                "full_mesh_nonlinear_equilibrium_not_closed",
                *(
                    ["direct_residual_newton_not_closed"]
                    if direct_residual_newton.get("status") == "partial"
                    else []
                ),
                *(
                    ["equilibrium_newton_not_closed"]
                    if equilibrium_newton_focused.get("status") == "partial"
                    else []
                ),
            ],
            evidence={
                "native_status": native_3d.get("status"),
                "solve_mode": native_3d.get("solve_mode"),
                "nonlinear_equilibrium": mesh.get("nonlinear_equilibrium"),
                "representative_component_nonlinear_equilibrium": mesh.get(
                    "representative_component_nonlinear_equilibrium"
                ),
                "partial_connected_component_mesh": mesh.get("partial_connected_component_mesh"),
                "fell_back_to_linear_tangent": mesh.get("fell_back_to_linear_tangent"),
                "raw_beam_elements_available": raw_beams,
                "beam_elements_solved": solved_beams,
                "full_line_sparse_status": full_line_sparse.get("status"),
                "full_line_mesh_sparse_elastic_equilibrium_ready": full_line_sparse.get(
                    "full_line_mesh_sparse_elastic_equilibrium_ready"
                ),
                "full_line_mesh_linearized_geometric_equilibrium_ready": full_line_sparse.get(
                    "full_line_mesh_linearized_geometric_equilibrium_ready"
                ),
                "full_line_mesh_nonlinear_equilibrium": full_line_sparse.get(
                    "full_line_mesh_nonlinear_equilibrium"
                ),
                "full_line_mesh_fingerprint": full_line_sparse.get("mesh_fingerprint"),
                "full_line_elastic_equilibrium_metrics": full_line_sparse.get("equilibrium_metrics"),
                "full_line_geometric_equilibrium_metrics": full_line_sparse.get("geometric_equilibrium_metrics"),
                "full_line_linearized_geometric_tangent": full_line_sparse.get("linearized_geometric_tangent"),
                "full_line_runtime_metrics": full_line_sparse.get("runtime_metrics"),
                "full_frame_6dof_sparse_status": full_frame_6dof.get("status"),
                "full_frame_6dof_sparse_elastic_equilibrium_ready": full_frame_6dof.get(
                    "full_frame_6dof_sparse_elastic_equilibrium_ready"
                ),
                "full_frame_6dof_linearized_geometric_equilibrium_ready": full_frame_6dof.get(
                    "full_frame_6dof_linearized_geometric_equilibrium_ready"
                ),
                "full_frame_6dof_deformed_state_pdelta_equilibrium_ready": full_frame_6dof.get(
                    "full_frame_6dof_deformed_state_pdelta_equilibrium_ready"
                ),
                "full_frame_6dof_nonlinear_equilibrium": full_frame_6dof.get(
                    "full_frame_6dof_nonlinear_equilibrium"
                ),
                "full_frame_6dof_mesh_fingerprint": full_frame_6dof.get("mesh_fingerprint"),
                "full_frame_6dof_equilibrium_metrics": full_frame_6dof.get("equilibrium_metrics"),
                "full_frame_6dof_geometric_equilibrium_metrics": full_frame_6dof.get(
                    "geometric_equilibrium_metrics"
                ),
                "full_frame_6dof_linearized_geometric_tangent": full_frame_6dof.get(
                    "linearized_geometric_tangent"
                ),
                "full_frame_6dof_deformed_state_pdelta_path": full_frame_6dof.get(
                    "deformed_state_pdelta_path"
                ),
                "full_frame_6dof_linear_solver_refinement": full_frame_6dof.get(
                    "linear_solver_refinement"
                ),
                "pdelta_continuation_status": pdelta_continuation.get("status"),
                "full_load_pdelta_continuation_ready": pdelta_continuation.get(
                    "full_load_pdelta_continuation_ready"
                ),
                "pdelta_continuation_max_converged_load_scale": pdelta_continuation.get(
                    "max_converged_load_scale"
                ),
                "pdelta_direct_load_step_max_converged_load_scale": pdelta_continuation.get(
                    "direct_load_step_max_converged_load_scale"
                ),
                "pdelta_continuation_first_failed_load_scale": pdelta_continuation.get(
                    "first_failed_load_scale"
                ),
                "pdelta_continuation_step_results": pdelta_continuation.get("step_results"),
                "pdelta_post_converged_micro_step_probe": pdelta_continuation.get(
                    "post_converged_micro_step_probe"
                ),
                "pdelta_adaptive_micro_continuation_probe": pdelta_continuation.get(
                    "adaptive_micro_continuation_probe"
                ),
                "pdelta_post_failed_relaxation_sensitivity_probe": pdelta_continuation.get(
                    "post_failed_relaxation_sensitivity_probe"
                ),
                "pdelta_secant_predictor_probe": pdelta_continuation.get("secant_predictor_probe"),
                "pdelta_secant_micro_continuation_probe": pdelta_continuation.get(
                    "secant_micro_continuation_probe"
                ),
                "pdelta_fine_secant_micro_continuation_probe": pdelta_continuation.get(
                    "fine_secant_micro_continuation_probe"
                ),
                "pdelta_frontier_diagnostic": pdelta_frontier_diagnostic,
                "pdelta_frontier_residual_jacobian_summary": pdelta_residual_jacobian_summary,
                "pdelta_frontier_residual_jacobian_probe": pdelta_continuation.get(
                    "frontier_residual_jacobian_probe"
                ),
                "pdelta_first_failed_one_step_line_search_probe": pdelta_continuation.get(
                    "first_failed_one_step_line_search_probe"
                ),
                "pdelta_first_failed_anderson_acceleration_probe": pdelta_continuation.get(
                    "first_failed_anderson_acceleration_probe"
                ),
                "pdelta_first_failed_coefficient_bounded_anderson_probe": pdelta_continuation.get(
                    "first_failed_coefficient_bounded_anderson_probe"
                ),
                "pdelta_first_failed_residual_trust_region_anderson_probe": pdelta_continuation.get(
                    "first_failed_residual_trust_region_anderson_probe"
                ),
                "pdelta_continuation_blockers": pdelta_continuation.get("blockers"),
                "direct_residual_newton_status": direct_residual_newton.get("status"),
                "direct_residual_newton_ready": direct_residual_newton.get(
                    "direct_residual_newton_ready"
                ),
                "direct_residual_contract": direct_residual_newton.get("residual_contract"),
                "direct_residual_base": direct_residual_newton.get("base_direct_residual"),
                "direct_residual_final": direct_residual_newton.get("final_direct_residual"),
                "direct_residual_newton_direction": direct_residual_newton.get("newton_direction"),
                "direct_residual_trust_region": direct_residual_newton.get(
                    "trust_region_line_search"
                ),
                "direct_residual_secant_subspace_globalization": direct_residual_newton.get(
                    "secant_subspace_globalization"
                ),
                "direct_residual_matrix_free_consistent_jacobian_subspace": direct_residual_newton.get(
                    "matrix_free_consistent_jacobian_subspace"
                ),
                "direct_residual_current_tangent_residual_row_correction": direct_residual_newton.get(
                    "current_tangent_residual_row_correction"
                ),
                "direct_residual_newton_followup48_replay": _direct_residual_probe_summary(
                    direct_residual_newton_followup48_replay
                ),
                "direct_residual_newton_followup48_rowcorr_narrow": _direct_residual_probe_summary(
                    direct_residual_newton_followup48_rowcorr_narrow
                ),
                "direct_residual_newton_followup48_rowcorr_largest_rows_support4": (
                    _direct_residual_probe_summary(
                        direct_residual_newton_followup48_rowcorr_largest_rows_support4
                    )
                ),
                "direct_residual_newton_followup48_rowcorr_largest_rows_support4_followup2": (
                    _direct_residual_probe_summary(
                        direct_residual_newton_followup48_rowcorr_largest_rows_support4_followup2
                    )
                ),
                "direct_residual_newton_followup48_rowcorr_largest_rows_fd_support4_timeout": (
                    direct_residual_newton_followup48_rowcorr_largest_rows_fd_support4_timeout
                ),
                "direct_residual_newton_followup56_external_checkpoint_replay": (
                    _direct_residual_probe_summary(
                        direct_residual_newton_followup56_external_checkpoint_replay
                    )
                ),
                "direct_residual_newton_followup56_rowcorr_largest_rows_support4": (
                    _direct_residual_probe_summary(
                        direct_residual_newton_followup56_rowcorr_largest_rows_support4
                    )
                ),
                "direct_residual_newton_followup56_rowcorr_largest_rows_support4_followup2": (
                    _direct_residual_probe_summary(
                        direct_residual_newton_followup56_rowcorr_largest_rows_support4_followup2
                    )
                ),
                "direct_residual_newton_followup56_rowcorr_largest_rows_support8": (
                    _direct_residual_probe_summary(
                        direct_residual_newton_followup56_rowcorr_largest_rows_support8
                    )
                ),
                "direct_residual_newton_followup56_rowcorr_largest_rows_support4_directional_timeout": (
                    direct_residual_newton_followup56_rowcorr_largest_rows_support4_directional_timeout
                ),
                "direct_residual_newton_followup56_post_rowcorr_block_lstsq_translation_support32": (
                    _direct_residual_probe_summary(
                        direct_residual_newton_followup56_post_rowcorr_block_lstsq_translation_support32
                    )
                ),
                "direct_residual_newton_followup56_post_rowcorr_block_lstsq_translation_support32_followup2": (
                    _direct_residual_probe_summary(
                        direct_residual_newton_followup56_post_rowcorr_block_lstsq_translation_support32_followup2
                    )
                ),
                "direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support32": (
                    _direct_residual_probe_summary(
                        direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support32
                    )
                ),
                "direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support32_followup2": (
                    _direct_residual_probe_summary(
                        direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support32_followup2
                    )
                ),
                "direct_residual_post_frame_block_lstsq_translation_support32": (
                    _direct_residual_probe_summary(
                        direct_residual_post_frame_block_lstsq_translation_support32
                    )
                ),
                "direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support64": (
                    _direct_residual_probe_summary(
                        direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support64
                    )
                ),
                "direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support64_followup2": (
                    _direct_residual_probe_summary(
                        direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support64_followup2
                    )
                ),
                "direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support64_followup3": (
                    _direct_residual_probe_summary(
                        direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support64_followup3
                    )
                ),
                "direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support64_followup4": (
                    _direct_residual_probe_summary(
                        direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support64_followup4
                    )
                ),
                "direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support64_followup5": (
                    _direct_residual_probe_summary(
                        direct_residual_newton_followup56_post_rowcorr_block_lstsq_frame_support64_followup5
                    )
                ),
                "direct_residual_post_frame_support64_block_lstsq_translation_followup4": (
                    _direct_residual_probe_summary(
                        direct_residual_post_frame_support64_block_lstsq_translation_followup4
                    )
                ),
                "direct_residual_post_translation_support64_block_lstsq_frame_followup4": (
                    _direct_residual_probe_summary(
                        direct_residual_post_translation_support64_block_lstsq_frame_followup4
                    )
                ),
                "direct_residual_post_frame_support64_block_lstsq_translation_support128": (
                    _direct_residual_probe_summary(
                        direct_residual_post_frame_support64_block_lstsq_translation_support128
                    )
                ),
                "direct_residual_post_frame_support64_block_lstsq_translation_support128_followup2": (
                    _direct_residual_probe_summary(
                        direct_residual_post_frame_support64_block_lstsq_translation_support128_followup2
                    )
                ),
                "direct_residual_post_frame_support64_block_lstsq_translation_support128_followup3": (
                    _direct_residual_probe_summary(
                        direct_residual_post_frame_support64_block_lstsq_translation_support128_followup3
                    )
                ),
                "direct_residual_post_frame_support64_block_lstsq_translation_support128_followup4": (
                    _direct_residual_probe_summary(
                        direct_residual_post_frame_support64_block_lstsq_translation_support128_followup4
                    )
                ),
                "direct_residual_post_frame_support64_block_lstsq_translation_support128_followup5": (
                    _direct_residual_probe_summary(
                        direct_residual_post_frame_support64_block_lstsq_translation_support128_followup5
                    )
                ),
                "direct_residual_post_frame_support64_block_lstsq_translation_support128_followup6": (
                    _direct_residual_probe_summary(
                        direct_residual_post_frame_support64_block_lstsq_translation_support128_followup6
                    )
                ),
                "direct_residual_post_frame_support64_block_lstsq_translation_support128_followup7": (
                    _direct_residual_probe_summary(
                        direct_residual_post_frame_support64_block_lstsq_translation_support128_followup7
                    )
                ),
                "direct_residual_post_frame_support64_block_lstsq_translation_support128_followup8": (
                    _direct_residual_probe_summary(
                        direct_residual_post_frame_support64_block_lstsq_translation_support128_followup8
                    )
                ),
                "direct_residual_post_frame_support64_block_lstsq_translation_support128_followup9": (
                    _direct_residual_probe_summary(
                        direct_residual_post_frame_support64_block_lstsq_translation_support128_followup9
                    )
                ),
                "direct_residual_post_frame_support64_block_lstsq_translation_support128_followup10": (
                    _direct_residual_probe_summary(
                        direct_residual_post_frame_support64_block_lstsq_translation_support128_followup10
                    )
                ),
                "direct_residual_post_frame_support64_block_lstsq_translation_support128_followup11": (
                    _direct_residual_probe_summary(
                        direct_residual_post_frame_support64_block_lstsq_translation_support128_followup11
                    )
                ),
                "direct_residual_post_frame_support64_block_lstsq_translation_support128_followup12": (
                    _direct_residual_probe_summary(
                        direct_residual_post_frame_support64_block_lstsq_translation_support128_followup12
                    )
                ),
                "direct_residual_post_frame_support64_block_lstsq_translation_support128_followup13": (
                    _direct_residual_probe_summary(
                        direct_residual_post_frame_support64_block_lstsq_translation_support128_followup13
                    )
                ),
                "residual_jacobian_consistency_status": residual_jacobian_consistency.get(
                    "status"
                ),
                "residual_jacobian_consistency_ready": residual_jacobian_consistency.get(
                    "residual_jacobian_consistency_ready"
                ),
                "residual_jacobian_consistency_base_residual_inf_n": (
                    residual_jacobian_consistency.get("base_residual_inf_n")
                ),
                "residual_jacobian_consistency_base_relative_residual_inf": (
                    residual_jacobian_consistency.get("base_relative_residual_inf")
                ),
                "residual_jacobian_consistency_direction_rows": (
                    residual_jacobian_consistency.get("direction_rows")
                ),
                "residual_jacobian_consistency_component_breakdown": (
                    residual_jacobian_consistency.get("residual_component_breakdown")
                ),
                "residual_jacobian_consistency_hotspot_shell_membrane_diagnostics": (
                    residual_jacobian_consistency.get(
                        "residual_hotspot_shell_membrane_diagnostics"
                    )
                ),
                "residual_jacobian_consistency_hotspot_frame_diagnostics": (
                    residual_jacobian_consistency.get("residual_hotspot_frame_diagnostics")
                ),
                "residual_jacobian_consistency_state_scale_sweep": (
                    residual_jacobian_consistency.get("state_scale_sweep")
                ),
                "residual_jacobian_consistency_blockers": residual_jacobian_consistency.get(
                    "blockers"
                ),
                "residual_jacobian_current_frontier_component_status": (
                    residual_jacobian_current_frontier_component.get("status")
                ),
                "residual_jacobian_current_frontier_component_only": (
                    residual_jacobian_current_frontier_component.get("component_only")
                ),
                "residual_jacobian_current_frontier_base_residual_inf_n": (
                    residual_jacobian_current_frontier_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_current_frontier_base_relative_residual_inf": (
                    residual_jacobian_current_frontier_component.get(
                        "base_relative_residual_inf"
                    )
                ),
                "residual_jacobian_current_frontier_component_breakdown": (
                    residual_jacobian_current_frontier_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "residual_jacobian_current_frontier_hotspot_shell_membrane_diagnostics": (
                    residual_jacobian_current_frontier_component.get(
                        "residual_hotspot_shell_membrane_diagnostics"
                    )
                ),
                "residual_jacobian_current_frontier_hotspot_frame_diagnostics": (
                    residual_jacobian_current_frontier_component.get(
                        "residual_hotspot_frame_diagnostics"
                    )
                ),
                "residual_jacobian_current_frontier_frame_hotspot_signed_sweep": (
                    residual_jacobian_current_frontier_frame_hotspot_sweep.get(
                        "residual_hotspot_signed_displacement_sweep"
                    )
                ),
                "residual_jacobian_current_frontier_frame_hotspot_large_signed_sweep": (
                    residual_jacobian_current_frontier_frame_hotspot_large_sweep.get(
                        "residual_hotspot_signed_displacement_sweep"
                    )
                ),
                "residual_jacobian_current_frontier_frame_hotspot_jvp": _hotspot_jvp_summary(
                    residual_jacobian_current_frontier_frame_hotspot_jvp
                ),
                "residual_jacobian_current_frontier_component_blockers": (
                    residual_jacobian_current_frontier_component.get("blockers")
                ),
                "residual_jacobian_support128_followup11_component_status": (
                    residual_jacobian_support128_followup11_component.get("status")
                ),
                "residual_jacobian_support128_followup11_component_only": (
                    residual_jacobian_support128_followup11_component.get("component_only")
                ),
                "residual_jacobian_support128_followup11_base_residual_inf_n": (
                    residual_jacobian_support128_followup11_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_support128_followup11_base_relative_residual_inf": (
                    residual_jacobian_support128_followup11_component.get(
                        "base_relative_residual_inf"
                    )
                ),
                "residual_jacobian_support128_followup11_component_breakdown": (
                    residual_jacobian_support128_followup11_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "residual_jacobian_support128_followup11_hotspot_frame_diagnostics": (
                    residual_jacobian_support128_followup11_component.get(
                        "residual_hotspot_frame_diagnostics"
                    )
                ),
                "residual_jacobian_support128_followup11_hotspot_jvp": _hotspot_jvp_summary(
                    residual_jacobian_support128_followup11_hotspot_jvp
                ),
                "residual_jacobian_support128_followup11_component_blockers": (
                    residual_jacobian_support128_followup11_component.get("blockers")
                ),
                "direct_residual_row_element_block_target_smoke": _direct_residual_probe_summary(
                    direct_residual_row_element_block_target
                ),
                "direct_residual_row_element_patch_target_smoke": _direct_residual_probe_summary(
                    direct_residual_row_element_patch_target
                ),
                "direct_residual_row_element_patch_fd32_smoke": _direct_residual_probe_summary(
                    direct_residual_row_element_patch_fd32
                ),
                "direct_residual_row_element_block_fd32_followup_smoke": _direct_residual_probe_summary(
                    direct_residual_row_element_block_fd32_followup
                ),
                "direct_residual_global_matrix_free_krylov_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_krylov
                ),
                "direct_residual_global_matrix_free_scaled_krylov_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_scaled_krylov
                ),
                "direct_residual_global_matrix_free_scaled_signed_krylov_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_scaled_signed_krylov
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_floor_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_floor
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_2_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_2
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_3_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_3
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_4_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_followup_4
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_broader_basis_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_broader_basis
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e9_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e9
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e7_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e7
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e7_followup_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e7_followup
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg3e7_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg3e7
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_2_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_2
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_3_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_3
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_4_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg1e6_followup_4
                ),
                "direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg3e6_smoke": _direct_residual_probe_summary(
                    direct_residual_global_matrix_free_tangent_preconditioned_krylov_alpha8_reg3e6
                ),
                "direct_residual_adaptive_preconditioned_global_newton_smoke": _adaptive_preconditioned_global_newton_summary(
                    direct_residual_adaptive_preconditioned_global_newton
                ),
                "direct_residual_adaptive_preconditioned_global_newton_secant_seed_smoke": _adaptive_preconditioned_global_newton_summary(
                    direct_residual_adaptive_preconditioned_global_newton_secant_seed
                ),
                "direct_residual_adaptive_preconditioned_global_newton_secant_seed_followup_smoke": _adaptive_preconditioned_global_newton_summary(
                    direct_residual_adaptive_preconditioned_global_newton_secant_seed_followup
                ),
                "direct_residual_adaptive_preconditioned_global_newton_secant_seed_followup_2_smoke": _adaptive_preconditioned_global_newton_summary(
                    direct_residual_adaptive_preconditioned_global_newton_secant_seed_followup_2
                ),
                "direct_residual_adaptive_preconditioned_global_newton_runtime_budget_smoke": _adaptive_preconditioned_global_newton_summary(
                    direct_residual_adaptive_preconditioned_global_newton_runtime_budget
                ),
                "direct_residual_current_checkpoint_single_largest_row_current_tangent": _direct_residual_probe_summary(
                    direct_residual_current_checkpoint_single_largest_row_current_tangent
                ),
                "direct_residual_current_checkpoint_single_largest_row_current_tangent_replay": _direct_residual_probe_summary(
                    direct_residual_current_checkpoint_single_largest_row_current_tangent_replay
                ),
                "direct_residual_current_checkpoint_single_largest_row_current_tangent_followup": _direct_residual_probe_summary(
                    direct_residual_current_checkpoint_single_largest_row_current_tangent_followup
                ),
                "direct_residual_current_checkpoint_single_largest_row_fd_jacobian": _direct_residual_probe_summary(
                    direct_residual_current_checkpoint_single_largest_row_fd_jacobian
                ),
                "direct_residual_current_checkpoint_frame_element_block_current_tangent": _direct_residual_probe_summary(
                    direct_residual_current_checkpoint_frame_element_block_current_tangent
                ),
                "direct_residual_current_checkpoint_frame_element_block_fd_jacobian": _direct_residual_probe_summary(
                    direct_residual_current_checkpoint_frame_element_block_fd_jacobian
                ),
                "direct_residual_current_checkpoint_trust_iteration_strict_gate_probe": _direct_residual_probe_summary(
                    direct_residual_current_checkpoint_trust_iteration_strict_gate_probe
                ),
                "direct_residual_current_checkpoint_trust_iteration_strict_gate_probe_replay": _direct_residual_probe_summary(
                    direct_residual_current_checkpoint_trust_iteration_strict_gate_probe_replay
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_replay
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_followup": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_followup
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_followup_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_followup_replay
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass_replay
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass_followup": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass_followup
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass_followup_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_multipass_followup_replay
                ),
                "direct_residual_frame_hotspot_signed_displacement_current_frontier": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_signed_displacement_current_frontier
                ),
                "direct_residual_frame_hotspot_signed_displacement_current_frontier_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_signed_displacement_current_frontier_replay
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_replay
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup_replay
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_replay
                ),
                "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_followup2": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_followup2
                ),
                "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_followup2_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_followup2_replay
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_signed_followup": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_signed_followup
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_signed_followup_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_signed_followup2_signed_followup_replay
                ),
                "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup
                ),
                "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup_replay
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_diagonal_signed_followup2": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_diagonal_signed_followup2
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_diagonal_signed_followup2_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_diagonal_signed_followup2_replay
                ),
                "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup2": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup2
                ),
                "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup2_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_diagonal_signed_followup2_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_batch": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_batch
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_batch_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_tiny_followup2_next_batch_fine_followup2_batch_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup2": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup2
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup2_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_followup2_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_followup": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_followup
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_followup_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_wide8_alpha_followup_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup2": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup2
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup2_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup2_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup3": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup3
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup3_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup3_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_support16": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_support16
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_support32": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_support32
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_rows4": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_rows4
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_rows4_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_gate_alpha_followup4_rows4_replay
                ),
                "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_rows4": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_rows4
                ),
                "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_rows4_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_rows4_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_signed_rows4": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_signed_rows4
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_signed_rows4_rows4": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_signed_rows4_rows4
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_signed_rows4_rows4_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_signed_rows4_rows4_replay
                ),
                "direct_residual_current_frontier_frame_block_current_tangent_narrow_post_signed_rows4_rows4": _direct_residual_probe_summary(
                    direct_residual_current_frontier_frame_block_current_tangent_narrow_post_signed_rows4_rows4
                ),
                "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_tangent_narrow": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_tangent_narrow
                ),
                "direct_residual_frame_hotspot_signed_displacement_current_frontier_post_tangent_narrow_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_signed_displacement_current_frontier_post_tangent_narrow_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_rows4": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_rows4
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_rows4_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_tangent_signed_rows4_replay
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_tangent_signed_rows4": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_tangent_signed_rows4
                ),
                "direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_tangent_signed_rows4_followup": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_diagonal_newton_current_frontier_post_tangent_signed_rows4_followup
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_diagonal_followup_rows4": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_diagonal_followup_rows4
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_followup_rows4": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_followup_rows4
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_followup_rows4_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_followup_rows4_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows8_followup2": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows8_followup2
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows12_followup3": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows12_followup3
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows16_followup4": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows16_followup4
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup5": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup5
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup6": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup6
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup6_replay": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup6_replay
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup7": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows20_followup7
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_followup7": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_followup7
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup7": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup7
                ),
                "residual_jacobian_post_block_rows21_support16_followup7_component_status": (
                    residual_jacobian_post_block_rows21_support16_followup7_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support16_followup7_component_only": (
                    residual_jacobian_post_block_rows21_support16_followup7_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support16_followup7_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support16_followup7_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support16_followup7_component_breakdown": (
                    residual_jacobian_post_block_rows21_support16_followup7_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup8": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup8
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup9": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup9
                ),
                "residual_jacobian_post_block_rows21_support16_followup9_component_status": (
                    residual_jacobian_post_block_rows21_support16_followup9_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support16_followup9_component_only": (
                    residual_jacobian_post_block_rows21_support16_followup9_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support16_followup9_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support16_followup9_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support16_followup9_component_breakdown": (
                    residual_jacobian_post_block_rows21_support16_followup9_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup10": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup10
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup11": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup11
                ),
                "residual_jacobian_post_block_rows21_support16_followup11_component_status": (
                    residual_jacobian_post_block_rows21_support16_followup11_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support16_followup11_component_only": (
                    residual_jacobian_post_block_rows21_support16_followup11_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support16_followup11_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support16_followup11_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support16_followup11_component_breakdown": (
                    residual_jacobian_post_block_rows21_support16_followup11_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup12": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup12
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup13": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup13
                ),
                "residual_jacobian_post_block_rows21_support16_followup13_component_status": (
                    residual_jacobian_post_block_rows21_support16_followup13_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support16_followup13_component_only": (
                    residual_jacobian_post_block_rows21_support16_followup13_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support16_followup13_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support16_followup13_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support16_followup13_component_breakdown": (
                    residual_jacobian_post_block_rows21_support16_followup13_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup16": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup16
                ),
                "residual_jacobian_post_block_rows21_support16_followup16_component_status": (
                    residual_jacobian_post_block_rows21_support16_followup16_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support16_followup16_component_only": (
                    residual_jacobian_post_block_rows21_support16_followup16_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support16_followup16_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support16_followup16_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support16_followup16_component_breakdown": (
                    residual_jacobian_post_block_rows21_support16_followup16_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup21": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup21
                ),
                "residual_jacobian_post_block_rows21_support16_followup21_component_status": (
                    residual_jacobian_post_block_rows21_support16_followup21_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support16_followup21_component_only": (
                    residual_jacobian_post_block_rows21_support16_followup21_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support16_followup21_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support16_followup21_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support16_followup21_component_breakdown": (
                    residual_jacobian_post_block_rows21_support16_followup21_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup31": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_current_frontier_post_block_rows21_support16_followup31
                ),
                "residual_jacobian_post_block_rows21_support16_followup31_component_status": (
                    residual_jacobian_post_block_rows21_support16_followup31_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support16_followup31_component_only": (
                    residual_jacobian_post_block_rows21_support16_followup31_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support16_followup31_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support16_followup31_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support16_followup31_component_breakdown": (
                    residual_jacobian_post_block_rows21_support16_followup31_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support16_followup34": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support16_followup34
                ),
                "residual_jacobian_post_block_rows21_support16_translation_followup34_component_status": (
                    residual_jacobian_post_block_rows21_support16_translation_followup34_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support16_translation_followup34_component_only": (
                    residual_jacobian_post_block_rows21_support16_translation_followup34_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support16_translation_followup34_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support16_translation_followup34_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support16_translation_followup34_component_breakdown": (
                    residual_jacobian_post_block_rows21_support16_translation_followup34_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup35": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup35
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup35_component_status": (
                    residual_jacobian_post_block_rows21_support32_translation_followup35_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup35_component_only": (
                    residual_jacobian_post_block_rows21_support32_translation_followup35_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup35_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support32_translation_followup35_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup35_component_breakdown": (
                    residual_jacobian_post_block_rows21_support32_translation_followup35_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support64_followup36": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support64_followup36
                ),
                "residual_jacobian_post_block_rows21_support64_translation_followup36_component_status": (
                    residual_jacobian_post_block_rows21_support64_translation_followup36_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support64_translation_followup36_component_only": (
                    residual_jacobian_post_block_rows21_support64_translation_followup36_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support64_translation_followup36_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support64_translation_followup36_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support64_translation_followup36_component_breakdown": (
                    residual_jacobian_post_block_rows21_support64_translation_followup36_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup37": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup37
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup37_component_status": (
                    residual_jacobian_post_block_rows21_support32_translation_followup37_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup37_component_only": (
                    residual_jacobian_post_block_rows21_support32_translation_followup37_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup37_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support32_translation_followup37_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup37_component_breakdown": (
                    residual_jacobian_post_block_rows21_support32_translation_followup37_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup42": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup42
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup42_component_status": (
                    residual_jacobian_post_block_rows21_support32_translation_followup42_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup42_component_only": (
                    residual_jacobian_post_block_rows21_support32_translation_followup42_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup42_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support32_translation_followup42_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup42_component_breakdown": (
                    residual_jacobian_post_block_rows21_support32_translation_followup42_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup47": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup47
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup47_component_status": (
                    residual_jacobian_post_block_rows21_support32_translation_followup47_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup47_component_only": (
                    residual_jacobian_post_block_rows21_support32_translation_followup47_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup47_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support32_translation_followup47_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup47_component_breakdown": (
                    residual_jacobian_post_block_rows21_support32_translation_followup47_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup48": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup48
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup48_component_status": (
                    residual_jacobian_post_block_rows21_support32_translation_followup48_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup48_component_only": (
                    residual_jacobian_post_block_rows21_support32_translation_followup48_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup48_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support32_translation_followup48_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup48_component_breakdown": (
                    residual_jacobian_post_block_rows21_support32_translation_followup48_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup49": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup49
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup49_component_status": (
                    residual_jacobian_post_block_rows21_support32_translation_followup49_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup49_component_only": (
                    residual_jacobian_post_block_rows21_support32_translation_followup49_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup49_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support32_translation_followup49_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup49_component_breakdown": (
                    residual_jacobian_post_block_rows21_support32_translation_followup49_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup50": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup50
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup50_component_status": (
                    residual_jacobian_post_block_rows21_support32_translation_followup50_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup50_component_only": (
                    residual_jacobian_post_block_rows21_support32_translation_followup50_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup50_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support32_translation_followup50_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup50_component_breakdown": (
                    residual_jacobian_post_block_rows21_support32_translation_followup50_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup51": _direct_residual_probe_summary(
                    direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup51
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup51_component_status": (
                    residual_jacobian_post_block_rows21_support32_translation_followup51_component.get("status")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup51_component_only": (
                    residual_jacobian_post_block_rows21_support32_translation_followup51_component.get("component_only")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup51_base_residual_inf_n": (
                    residual_jacobian_post_block_rows21_support32_translation_followup51_component.get("base_residual_inf_n")
                ),
                "residual_jacobian_post_block_rows21_support32_translation_followup51_component_breakdown": (
                    residual_jacobian_post_block_rows21_support32_translation_followup51_component.get(
                        "residual_component_breakdown"
                    )
                ),
                "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup_series": _translation_frontier_followup_series(
                    productization
                ),
                "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup57_timeout_diagnostic": _direct_residual_probe_summary(
                    translation_frontier_followup57_timeout_diagnostic
                ),
                "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup57_timeout_runtime": (
                    translation_frontier_followup57_timeout_diagnostic.get("runtime_metrics")
                ),
                "direct_residual_frame_hotspot_block_lstsq_translation_frontier_post_block_rows21_support32_followup57_timeout_blockers": (
                    translation_frontier_followup57_timeout_diagnostic.get("blockers")
                ),
                "direct_residual_current_frontier_frame_block_current_tangent_narrow": _direct_residual_probe_summary(
                    direct_residual_current_frontier_frame_block_current_tangent_narrow
                ),
                "direct_residual_current_frontier_frame_block_fd16_residual_weighted": _direct_residual_probe_summary(
                    direct_residual_current_frontier_frame_block_fd16_residual_weighted
                ),
                "direct_residual_historical_adaptive_checkpoint_current_residual_replay_audit": _direct_residual_probe_summary(
                    direct_residual_historical_adaptive_checkpoint_current_residual_replay_audit
                ),
                "direct_residual_newton_blockers": direct_residual_newton.get("blockers"),
                "coarsened_authored_support_pdelta_status": coarsened_authored_support_pdelta.get(
                    "status"
                ),
                "coarsened_authored_support_pdelta_ready": coarsened_authored_support_pdelta.get(
                    "coarsened_authored_support_pdelta_ready"
                ),
                "coarsened_authored_support_pdelta_boundary_policy": coarsened_authored_support_pdelta.get(
                    "boundary_condition_policy"
                ),
                "coarsened_authored_support_pdelta_max_converged_load_scale": coarsened_authored_support_pdelta.get(
                    "max_converged_load_scale"
                ),
                "coarsened_authored_support_pdelta_first_failed_load_scale": coarsened_authored_support_pdelta.get(
                    "first_failed_load_scale"
                ),
                "coarsened_authored_support_pdelta_step_results": coarsened_authored_support_pdelta.get(
                    "step_results"
                ),
                "coarsened_authored_support_pdelta_support_mapping": coarsened_authored_support_pdelta.get(
                    "support_mapping"
                ),
                "coarsened_authored_support_pdelta_elastic_link_mapping": coarsened_authored_support_pdelta.get(
                    "elastic_link_mapping"
                ),
                "coarsened_authored_support_pdelta_blockers": coarsened_authored_support_pdelta.get(
                    "blockers"
                ),
                "uncoarsened_boundary_pdelta_status": uncoarsened_boundary_pdelta.get(
                    "status"
                ),
                "uncoarsened_boundary_pdelta_ready": uncoarsened_boundary_pdelta.get(
                    "uncoarsened_boundary_pdelta_ready"
                ),
                "uncoarsened_boundary_pdelta_max_converged_load_scale": uncoarsened_boundary_pdelta.get(
                    "max_converged_load_scale"
                ),
                "uncoarsened_boundary_pdelta_first_failed_load_scale": uncoarsened_boundary_pdelta.get(
                    "first_failed_load_scale"
                ),
                "uncoarsened_boundary_pdelta_step_results": uncoarsened_boundary_pdelta.get(
                    "step_results"
                ),
                "uncoarsened_boundary_pdelta_boundary_summary": uncoarsened_boundary_pdelta.get(
                    "boundary_summary"
                ),
                "uncoarsened_boundary_pdelta_checkpoint_resume": uncoarsened_boundary_pdelta.get(
                    "checkpoint_resume"
                ),
                "uncoarsened_boundary_pdelta_checkpoint_resume_probe": (
                    uncoarsened_boundary_pdelta_checkpoint_resume or None
                ),
                "uncoarsened_boundary_pdelta_checkpoint_resume_probe_status": (
                    uncoarsened_boundary_pdelta_checkpoint_resume.get("status")
                ),
                "uncoarsened_boundary_pdelta_checkpoint_resume_probe_max_converged_load_scale": (
                    uncoarsened_boundary_pdelta_checkpoint_resume.get("max_converged_load_scale")
                ),
                "uncoarsened_boundary_pdelta_checkpoint_resume_probe_first_failed_load_scale": (
                    uncoarsened_boundary_pdelta_checkpoint_resume.get("first_failed_load_scale")
                ),
                "uncoarsened_boundary_pdelta_checkpoint_continuation": (
                    uncoarsened_boundary_pdelta_checkpoint_continuation or None
                ),
                "uncoarsened_boundary_pdelta_checkpoint_continuation_status": (
                    uncoarsened_boundary_pdelta_checkpoint_continuation.get("status")
                ),
                "uncoarsened_boundary_pdelta_checkpoint_continuation_max_converged_load_scale": (
                    uncoarsened_boundary_pdelta_checkpoint_continuation.get("max_converged_load_scale")
                ),
                "uncoarsened_boundary_pdelta_checkpoint_continuation_first_failed_load_scale": (
                    uncoarsened_boundary_pdelta_checkpoint_continuation.get("first_failed_load_scale")
                ),
                "uncoarsened_boundary_pdelta_secant_seed_probe": (
                    uncoarsened_boundary_pdelta_secant_seed or None
                ),
                "uncoarsened_boundary_pdelta_secant_seed_probe_status": (
                    uncoarsened_boundary_pdelta_secant_seed.get("status")
                ),
                "uncoarsened_boundary_pdelta_secant_seed_probe_max_converged_load_scale": (
                    uncoarsened_boundary_pdelta_secant_seed.get("max_converged_load_scale")
                ),
                "uncoarsened_boundary_pdelta_secant_seed_probe_first_failed_load_scale": (
                    uncoarsened_boundary_pdelta_secant_seed.get("first_failed_load_scale")
                ),
                "uncoarsened_boundary_pdelta_blockers": uncoarsened_boundary_pdelta.get(
                    "blockers"
                ),
                "equilibrium_newton_focused_status": equilibrium_newton_focused.get("status"),
                "equilibrium_newton_focused_ready": equilibrium_newton_focused.get(
                    "equilibrium_newton_ready"
                ),
                "equilibrium_newton_focused_initial_residual_inf_n": equilibrium_newton_focused.get(
                    "initial_residual_inf_n"
                ),
                "equilibrium_newton_focused_final_residual_inf_n": equilibrium_newton_focused.get(
                    "final_residual_inf_n"
                ),
                "equilibrium_newton_focused_accept_gate": (
                    "equilibrium_replay_residual_inf_only_no_solver_receipt_accept"
                ),
                "equilibrium_newton_focused_blockers": equilibrium_newton_focused.get("blockers"),
                "equilibrium_newton_state_scale_status": equilibrium_newton_state_scale.get(
                    "status"
                ),
                "equilibrium_newton_state_scale_initial_residual_inf_n": (
                    equilibrium_newton_state_scale.get("initial_residual_inf_n")
                ),
                "equilibrium_newton_state_scale_final_residual_inf_n": (
                    equilibrium_newton_state_scale.get("final_residual_inf_n")
                ),
                "equilibrium_newton_state_scale_iterations": (
                    equilibrium_newton_state_scale.get("newton_iterations")
                ),
                "equilibrium_newton_state_scale_blockers": equilibrium_newton_state_scale.get(
                    "blockers"
                ),
                "equilibrium_preconditioned_zero_status": preconditioned_zero.get(
                    "status"
                ),
                "equilibrium_preconditioned_zero_residual_gate_passed": (
                    preconditioned_zero.get("residual_gate_passed")
                ),
                "equilibrium_preconditioned_zero_zero_state_residual_inf_n": (
                    preconditioned_zero.get("zero_state_residual_inf_n")
                ),
                "equilibrium_preconditioned_zero_best_residual_inf_n": (
                    preconditioned_zero.get("best_residual_inf_n")
                ),
                "equilibrium_preconditioned_zero_overall_best_residual_inf_n": (
                    preconditioned_zero.get("overall_best_residual_inf_n")
                ),
                "equilibrium_preconditioned_zero_best_correction_mode": (
                    preconditioned_zero.get("best_correction_mode")
                ),
                "equilibrium_preconditioned_zero_best_relative_improvement": (
                    preconditioned_zero.get("best_relative_improvement")
                ),
                "equilibrium_preconditioned_zero_iterative_search": (
                    preconditioned_zero.get("iterative_search")
                ),
                "equilibrium_preconditioned_zero_output_final_checkpoint": (
                    preconditioned_zero.get("output_final_checkpoint")
                ),
                "equilibrium_preconditioned_zero_blockers": preconditioned_zero.get(
                    "blockers"
                ),
                "direct_residual_preconditioned_zero_seed_status": (
                    direct_residual_preconditioned_zero_seed.get("status")
                ),
                "direct_residual_preconditioned_zero_seed_base_residual_inf_n": (
                    _get(
                        direct_residual_preconditioned_zero_seed,
                        "base_direct_residual",
                        "direct_residual_inf_n",
                    )
                ),
                "direct_residual_preconditioned_zero_seed_blockers": (
                    direct_residual_preconditioned_zero_seed.get("blockers")
                ),
                "equilibrium_preconditioned_continuation_status": (
                    preconditioned_continuation.get("status")
                ),
                "equilibrium_preconditioned_continuation_start_residual_inf_n": (
                    preconditioned_continuation.get("start_state_residual_inf_n")
                ),
                "equilibrium_preconditioned_continuation_overall_best_residual_inf_n": (
                    preconditioned_continuation.get("overall_best_residual_inf_n")
                ),
                "equilibrium_preconditioned_continuation_iterative_search": (
                    preconditioned_continuation.get("iterative_search")
                ),
                "equilibrium_preconditioned_continuation_output_final_checkpoint": (
                    preconditioned_continuation.get("output_final_checkpoint")
                ),
                "equilibrium_preconditioned_continuation_checkpoint_standardization_status": (
                    preconditioned_continuation_standardization.get("status")
                ),
                "equilibrium_preconditioned_continuation_standard_checkpoint_ready": (
                    preconditioned_continuation_standardization.get("ready")
                ),
                "equilibrium_preconditioned_continuation_standard_checkpoint": (
                    preconditioned_continuation_standardization.get("output_checkpoint")
                ),
                "equilibrium_preconditioned_continuation_standard_reloaded_checkpoint": (
                    preconditioned_continuation_standardization.get("reloaded_checkpoint")
                ),
                "direct_residual_preconditioned_continuation_seed_status": (
                    direct_residual_preconditioned_continuation_seed.get("status")
                ),
                "direct_residual_preconditioned_continuation_seed_base_residual_inf_n": (
                    _get(
                        direct_residual_preconditioned_continuation_seed,
                        "base_direct_residual",
                        "direct_residual_inf_n",
                    )
                ),
                "direct_residual_preconditioned_continuation_standard_seed_status": (
                    direct_residual_preconditioned_continuation_standard_seed.get("status")
                ),
                "direct_residual_preconditioned_continuation_standard_seed_checkpoint_schema": (
                    _get(
                        direct_residual_preconditioned_continuation_standard_seed,
                        "checkpoint",
                        "checkpoint_schema",
                    )
                ),
                "direct_residual_preconditioned_continuation_standard_seed_base_residual_inf_n": (
                    _get(
                        direct_residual_preconditioned_continuation_standard_seed,
                        "base_direct_residual",
                        "direct_residual_inf_n",
                    )
                ),
                "direct_residual_preconditioned_continuation_standard_rowcorr_status": (
                    direct_residual_preconditioned_continuation_standard_rowcorr.get("status")
                ),
                "direct_residual_preconditioned_continuation_standard_rowcorr_accepted": (
                    _get(
                        direct_residual_preconditioned_continuation_standard_rowcorr,
                        "current_tangent_residual_row_correction",
                        "accepted",
                    )
                ),
                "direct_residual_preconditioned_continuation_standard_rowcorr_base_residual_inf_n": (
                    _get(
                        direct_residual_preconditioned_continuation_standard_rowcorr,
                        "base_direct_residual",
                        "direct_residual_inf_n",
                    )
                ),
                "direct_residual_preconditioned_continuation_standard_rowcorr_final_residual_inf_n": (
                    _get(
                        direct_residual_preconditioned_continuation_standard_rowcorr,
                        "final_direct_residual",
                        "direct_residual_inf_n",
                    )
                ),
                "direct_residual_preconditioned_continuation_standard_rowcorr_improvement_factor": (
                    _get(
                        direct_residual_preconditioned_continuation_standard_rowcorr,
                        "final_direct_residual",
                        "improvement_factor",
                    )
                ),
                "direct_residual_preconditioned_continuation_standard_rowcorr_final_checkpoint": (
                    direct_residual_preconditioned_continuation_standard_rowcorr.get(
                        "output_final_checkpoint"
                    )
                ),
                "full_load_nonlinear_newton_ready": pdelta_continuation.get(
                    "full_load_nonlinear_newton_ready"
                ),
                "full_frame_6dof_runtime_metrics": full_frame_6dof.get("runtime_metrics"),
                "frame_material_nonlinear_tangent_status": frame_material_nonlinear.get("status"),
                "frame_material_nonlinear_tangent_ready": frame_material_nonlinear.get(
                    "frame_material_nonlinear_tangent_ready"
                ),
                "service_load_material_state_ready": frame_material_nonlinear.get(
                    "service_load_material_state_ready"
                ),
                "controlled_probe_material_state_ready": frame_material_nonlinear.get(
                    "controlled_probe_material_state_ready"
                ),
                "bounded_material_tangent_global_smoke_ready": frame_material_nonlinear.get(
                    "bounded_material_tangent_global_smoke_ready"
                ),
                "global_smoke_solver_uses_per_element_material_tangent": frame_material_nonlinear.get(
                    "global_smoke_solver_uses_per_element_material_tangent"
                ),
                "full_material_nonlinear_newton_equilibrium": frame_material_nonlinear.get(
                    "full_material_nonlinear_newton_equilibrium"
                ),
                "frame_material_probe_summary": frame_material_nonlinear.get(
                    "controlled_probe_material_state_summary"
                ),
                "frame_material_tangent_smoke_equilibrium": frame_material_nonlinear.get(
                    "material_tangent_smoke_equilibrium"
                ),
                "surface_membrane_tangent_status": surface_membrane.get("status"),
                "surface_membrane_tangent_ready": surface_membrane.get(
                    "surface_membrane_tangent_ready"
                ),
                "surface_membrane_smoke_solve_ready": surface_membrane.get(
                    "surface_membrane_smoke_solve_ready"
                ),
                "surface_shell_full_bending_tangent_ready": surface_membrane.get(
                    "surface_shell_full_bending_tangent_ready"
                ),
                "surface_shell_bending_tangent_status": surface_shell_bending.get("status"),
                "surface_shell_bending_drilling_smoke_ready": surface_shell_bending.get(
                    "surface_shell_bending_drilling_smoke_ready"
                ),
                "surface_shell_transverse_pressure_smoke_ready": surface_shell_bending.get(
                    "surface_shell_transverse_pressure_smoke_ready"
                ),
                "surface_shell_bending_mesh_fingerprint": surface_shell_bending.get("mesh_fingerprint"),
                "surface_shell_bending_material_coverage": surface_shell_bending.get(
                    "surface_material_coverage"
                ),
                "surface_shell_bending_equilibrium_metrics": surface_shell_bending.get(
                    "equilibrium_metrics"
                ),
                "surface_shell_bending_runtime_metrics": surface_shell_bending.get("runtime_metrics"),
                "shell_calibration_benchmarks_status": shell_calibration.get("status"),
                "shell_calibration_benchmarks_ready": shell_calibration.get(
                    "shell_calibration_benchmarks_ready"
                ),
                "shell_calibration_case_count": shell_calibration.get("case_count"),
                "shell_calibration_ready_case_count": shell_calibration.get("ready_case_count"),
                "shell_calibration_cases": shell_calibration.get("cases"),
                "surface_membrane_mesh_fingerprint": surface_membrane.get("mesh_fingerprint"),
                "surface_membrane_material_coverage": surface_membrane.get(
                    "surface_material_coverage"
                ),
                "surface_membrane_equilibrium_metrics": surface_membrane.get("equilibrium_metrics"),
                "surface_membrane_runtime_metrics": surface_membrane.get("runtime_metrics"),
                "coupled_frame_surface_status": coupled_frame_surface.get("status"),
                "coupled_frame_surface_sparse_equilibrium_ready": coupled_frame_surface.get(
                    "coupled_frame_surface_sparse_equilibrium_ready"
                ),
                "coupled_frame_surface_nonlinear_equilibrium": coupled_frame_surface.get(
                    "coupled_frame_surface_nonlinear_equilibrium"
                ),
                "coupled_frame_surface_mesh_fingerprint": coupled_frame_surface.get("mesh_fingerprint"),
                "coupled_frame_surface_material_coverage": coupled_frame_surface.get(
                    "surface_material_coverage"
                ),
                "coupled_frame_surface_equilibrium_metrics": coupled_frame_surface.get(
                    "equilibrium_metrics"
                ),
                "coupled_frame_surface_runtime_metrics": coupled_frame_surface.get("runtime_metrics"),
                "coupled_frame_shell_status": coupled_frame_shell.get("status"),
                "coupled_frame_shell_sparse_equilibrium_ready": coupled_frame_shell.get(
                    "coupled_frame_shell_sparse_equilibrium_ready"
                ),
                "coupled_frame_shell_nonlinear_equilibrium": coupled_frame_shell.get(
                    "coupled_frame_shell_nonlinear_equilibrium"
                ),
                "coupled_frame_shell_mesh_fingerprint": coupled_frame_shell.get("mesh_fingerprint"),
                "coupled_frame_shell_material_coverage": coupled_frame_shell.get(
                    "surface_material_coverage"
                ),
                "coupled_frame_shell_equilibrium_metrics": coupled_frame_shell.get(
                    "equilibrium_metrics"
                ),
                "coupled_frame_shell_runtime_metrics": coupled_frame_shell.get("runtime_metrics"),
                "beam_offset_support_status": beam_offset_support.get("status"),
                "beam_offset_row_count": _get(
                    beam_offset_support, "summary", "offset_row_count", default=0
                ),
                "beam_offset_distinct_element_count": _get(
                    beam_offset_support, "summary", "distinct_offset_element_count", default=0
                ),
                "beam_offset_max_abs_m": _get(
                    beam_offset_support, "summary", "max_abs_offset_m", default=0.0
                ),
                "typed_mgt_offset_parser_ready": _get(
                    beam_offset_support, "support", "typed_mgt_offset_parser_ready", default=False
                ),
                "offset_element_refs_match_mgt_elements": _get(
                    beam_offset_support,
                    "support",
                    "offset_element_refs_match_mgt_elements",
                    default=False,
                ),
                "solver_rigid_end_offset_tangent_ready": _get(
                    full_frame_6dof,
                    "beam_end_offset_support",
                    "rigid_end_offset_tangent_ready",
                    default=False,
                ),
                "frame_rigid_end_offset_transform_applied": _get(
                    full_frame_6dof,
                    "beam_end_offset_support",
                    "rigid_end_offset_transform_applied",
                    default=False,
                ),
                "frame_offset_applied_element_count": _get(
                    full_frame_6dof,
                    "beam_end_offset_support",
                    "applied_element_count",
                    default=0,
                ),
                "coupled_frame_surface_offset_transform_applied": _get(
                    coupled_frame_surface,
                    "beam_end_offset_support",
                    "rigid_end_offset_transform_applied",
                    default=False,
                ),
                "coupled_frame_shell_offset_transform_applied": _get(
                    coupled_frame_shell,
                    "beam_end_offset_support",
                    "rigid_end_offset_transform_applied",
                    default=False,
                ),
                "local_axis_opening_status": local_axis_opening.get("status"),
                "frame_angle_parser_ready": _get(
                    local_axis_opening, "support", "frame_angle_parser_ready", default=False
                ),
                "frame_angle_source_has_nonzero_rows": _get(
                    local_axis_opening, "support", "frame_angle_source_has_nonzero_rows", default=False
                ),
                "frame_angle_solver_consumption_ready": _get(
                    local_axis_opening, "support", "frame_angle_solver_consumption_ready", default=False
                ),
                "frame_angle_nonzero_row_count": _get(
                    local_axis_opening, "summary", "line_nonzero_angle_row_count", default=0
                ),
                "frame_angle_max_abs_deg": _get(
                    local_axis_opening, "summary", "line_max_abs_angle_deg", default=0.0
                ),
                "surface_lcaxis_parser_ready": _get(
                    local_axis_opening, "support", "surface_lcaxis_parser_ready", default=False
                ),
                "surface_lcaxis_source_all_default": _get(
                    local_axis_opening, "support", "surface_lcaxis_source_all_default", default=False
                ),
                "opening_source_inventory_ready": _get(
                    local_axis_opening, "support", "opening_source_inventory_ready", default=False
                ),
                "opening_source_rows_present": _get(
                    local_axis_opening, "support", "opening_source_rows_present", default=False
                ),
                "current_source_opening_absence_policy_ready": _get(
                    local_axis_opening,
                    "support",
                    "current_source_opening_absence_policy_ready",
                    default=False,
                ),
                "current_source_opening_noop_runtime_ready": _get(
                    local_axis_opening,
                    "support",
                    "current_source_opening_noop_runtime_ready",
                    default=False,
                ),
                "opening_runtime_semantics_ready": opening_runtime_ready,
                "generic_opening_cutout_runtime_semantics_ready": generic_opening_cutout_ready,
                "boundary_entity_support_status": boundary_entity_support.get("status"),
                "support_constraint_row_count": _get(
                    boundary_entity_support,
                    "summary",
                    "support_constraint_row_count",
                    default=0,
                ),
                "distinct_support_constraint_node_count": _get(
                    boundary_entity_support,
                    "summary",
                    "distinct_support_constraint_node_count",
                    default=0,
                ),
                "elastic_link_row_count": _get(
                    boundary_entity_support,
                    "summary",
                    "elastic_link_row_count",
                    default=0,
                ),
                "typed_mgt_support_constraint_parser_ready": _get(
                    boundary_entity_support,
                    "support",
                    "typed_mgt_support_constraint_parser_ready",
                    default=False,
                ),
                "typed_mgt_elastic_link_parser_ready": _get(
                    boundary_entity_support,
                    "support",
                    "typed_mgt_elastic_link_parser_ready",
                    default=False,
                ),
                "typed_mgt_story_eccentricity_parser_ready": _get(
                    boundary_entity_support,
                    "support",
                    "typed_mgt_story_eccentricity_parser_ready",
                    default=False,
                ),
                "roundtrip_rigid_like_elastic_link_coarsening_ready": _get(
                    boundary_entity_support,
                    "support",
                    "roundtrip_rigid_like_elastic_link_coarsening_ready",
                    default=False,
                ),
                "solver_uses_authored_support_restraint_masks": _get(
                    boundary_entity_support,
                    "support",
                    "solver_uses_authored_support_restraint_masks",
                    default=False,
                ),
                "solver_assembles_finite_elastic_link_springs": _get(
                    boundary_entity_support,
                    "support",
                    "solver_assembles_finite_elastic_link_springs",
                    default=False,
                ),
                "boundary_spring_tangent_status": boundary_spring_tangent.get("status"),
                "boundary_finite_spring_component_count": _get(
                    boundary_spring_tangent,
                    "summary",
                    "finite_spring_component_count",
                    default=0,
                ),
                "boundary_authored_support_restrained_dof_count": _get(
                    boundary_spring_tangent,
                    "summary",
                    "authored_support_restrained_dof_count",
                    default=0,
                ),
                "boundary_tangent_nnz": _get(
                    boundary_spring_tangent,
                    "summary",
                    "tangent_nnz",
                    default=0,
                ),
                "boundary_direct_support_link_node_intersection_count": _get(
                    boundary_spring_tangent,
                    "summary",
                    "direct_support_link_node_intersection_count",
                    default=0,
                ),
                "boundary_subsystem_authored_support_mask_application_ready": _get(
                    boundary_spring_tangent,
                    "support",
                    "authored_support_mask_application_ready",
                    default=False,
                ),
                "boundary_subsystem_finite_elastic_link_spring_tangent_ready": _get(
                    boundary_spring_tangent,
                    "support",
                    "finite_elastic_link_spring_tangent_ready",
                    default=False,
                ),
                "boundary_subsystem_probe_solve_ready": _get(
                    boundary_spring_tangent,
                    "support",
                    "boundary_subsystem_probe_solve_ready",
                    default=False,
                ),
                "boundary_subsystem_relative_residual_inf": _get(
                    boundary_spring_tangent,
                    "probe_solve",
                    "relative_residual_inf",
                    default=None,
                ),
                "boundary_subsystem_global_frame_shell_tangent_integration_ready": _get(
                    boundary_spring_tangent,
                    "support",
                    "global_frame_shell_tangent_integration_ready",
                    default=False,
                ),
                "uncoarsened_boundary_global_status": boundary_global.get("status"),
                "uncoarsened_boundary_global_equilibrium_ready": boundary_global.get(
                    "uncoarsened_boundary_global_equilibrium_ready"
                ),
                "global_frame_shell_boundary_tangent_integration_ready": boundary_global.get(
                    "global_frame_shell_tangent_integration_ready"
                ),
                "global_boundary_solver_uses_authored_support_restraint_masks": _get(
                    boundary_global,
                    "support",
                    "solver_uses_authored_support_restraint_masks",
                    default=False,
                ),
                "global_boundary_solver_assembles_finite_elastic_link_springs": _get(
                    boundary_global,
                    "support",
                    "solver_assembles_finite_elastic_link_springs",
                    default=False,
                ),
                "global_boundary_uncoarsened_elastic_link_endpoints_preserved": _get(
                    boundary_global,
                    "support",
                    "uncoarsened_elastic_link_endpoints_preserved",
                    default=False,
                ),
                "global_boundary_finite_spring_component_count": _get(
                    boundary_global,
                    "boundary_summary",
                    "finite_spring_component_count",
                    default=0,
                ),
                "global_boundary_authored_support_restrained_dof_count": _get(
                    boundary_global,
                    "boundary_summary",
                    "authored_support_restrained_dof_count",
                    default=0,
                ),
                "global_boundary_mesh_fingerprint": boundary_global.get("mesh_fingerprint"),
                "global_boundary_equilibrium_metrics": boundary_global.get("equilibrium_metrics"),
                "story_eccentricity_load_status": story_eccentricity_load.get("status"),
                "story_eccentricity_story_count": _get(
                    story_eccentricity_load,
                    "summary",
                    "story_count",
                    default=0,
                ),
                "story_eccentricity_generated_case_count": _get(
                    story_eccentricity_load,
                    "summary",
                    "generated_case_count",
                    default=0,
                ),
                "story_eccentricity_generated_seismic_case_count": _get(
                    story_eccentricity_load,
                    "summary",
                    "generated_seismic_case_count",
                    default=0,
                ),
                "story_eccentricity_max_abs_torsional_moment_nm": _get(
                    story_eccentricity_load,
                    "summary",
                    "max_abs_torsional_moment_nm",
                    default=0.0,
                ),
                "story_eccentricity_load_generation_ready": _get(
                    story_eccentricity_load,
                    "support",
                    "story_eccentricity_load_generation_ready",
                    default=False,
                ),
                "seismic_story_eccentricity_load_generation_ready": _get(
                    story_eccentricity_load,
                    "support",
                    "seismic_story_eccentricity_load_generation_ready",
                    default=False,
                ),
                "global_solver_consumes_story_eccentricity_loads": _get(
                    story_eccentricity_load,
                    "support",
                    "global_solver_consumes_story_eccentricity_loads",
                    default=False,
                ),
                "coupled_frame_shell_story_eccentricity_status": coupled_story_eccentricity.get("status"),
                "coupled_frame_shell_story_eccentricity_ready": _get(
                    coupled_story_eccentricity,
                    "coupled_frame_shell_story_eccentricity_equilibrium_ready",
                    default=False,
                ),
                "coupled_story_eccentricity_case_count": _get(
                    coupled_story_eccentricity,
                    "equilibrium_summary",
                    "case_count",
                    default=0,
                ),
                "coupled_story_eccentricity_ready_case_count": _get(
                    coupled_story_eccentricity,
                    "equilibrium_summary",
                    "ready_case_count",
                    default=0,
                ),
                "coupled_story_eccentricity_max_relative_residual_inf": _get(
                    coupled_story_eccentricity,
                    "equilibrium_summary",
                    "max_relative_residual_inf",
                    default=None,
                ),
                "coupled_story_eccentricity_max_translation_m": _get(
                    coupled_story_eccentricity,
                    "equilibrium_summary",
                    "max_translation_m",
                    default=None,
                ),
                "coupled_global_solver_consumes_story_eccentricity_loads": _get(
                    coupled_story_eccentricity,
                    "support",
                    "global_solver_consumes_story_eccentricity_loads",
                    default=False,
                ),
            },
            next_gate=(
                "consistent full-load Newton/Jacobian plus material Newton closure"
                if surface_source_thickness_ready
                and shell_calibration_ready
                and frame_local_axis_ready
                and opening_runtime_ready
                else
                "apply source opening semantics and consistent full-load Newton/Jacobian plus material Newton closure"
                if surface_source_thickness_ready and shell_calibration_ready and frame_local_axis_ready and not opening_runtime_ready
                else "apply parsed local axes/openings and consistent full-load Newton/Jacobian plus material Newton closure"
                if surface_source_thickness_ready and shell_calibration_ready
                else "calibrate full shell benchmarks, apply parsed local axes/openings, and consistent full-load Newton/Jacobian plus material Newton closure"
                if surface_source_thickness_ready
                else "source-thickness full shell benchmarks and consistent full-load Newton/Jacobian plus material Newton closure"
            ),
        ),
        _row(
            "G2",
            "Modal, Buckling, Stability",
            ledger="commercial_solver",
            status=_status(native_modal_buckling_closed, modal_partial or native_modal.get("status") == "partial"),
            blockers=[] if native_modal_buckling_closed else ["native_modal_buckling_solver_not_attached"],
            evidence={
                "native_modal_buckling_status": native_modal.get("status"),
                "native_solver_ready": native_modal.get("native_solver_ready"),
                "benchmark_contract_pass": native_modal.get("benchmark_contract_pass"),
                "mode_count": native_modal_modes,
                "critical_load_factor": native_buckling_factor,
                "solve_scope": native_modal.get("solve_scope"),
                "modal_buckling_summary": modal_summary or {},
                "crossval_status": crossval.get("status"),
            },
            next_gate="full-building native modal/buckling solve after G1 expands beyond representative component",
        ),
        _row(
            "G3",
            "Loads, Combinations, Staged Construction Semantics",
            ledger="commercial_solver",
            status=_status(
                load_stage_runtime.get("status") == "ready"
                and bool(load_stage_runtime.get("typed_load_stage_flow_ready"))
                and bool(load_stage_runtime.get("solve_flow_ready"))
                and bool(load_stage_runtime.get("viewer_flow_ready"))
                and bool(load_stage_runtime.get("export_flow_ready"))
                and bool(load_stage_runtime.get("audit_flow_ready"))
                and bool(load_stage_runtime.get("unsupported_hazard_queue_ready")),
                bool(bundle.get("summary", {}).get("mgt_roundtrip_parsed"))
                and load_stage.get("status") == "ready",
            ),
            blockers=[] if load_stage_runtime.get("status") == "ready" else [
                "typed_load_stage_contract_ready_but_full_hazard_editor_breadth_not_closed"
            ],
            evidence={
                "mgt_roundtrip_parsed": _get(bundle, "summary", "mgt_roundtrip_parsed"),
                "roundtrip_sync_status": _get(bundle, "summary", "mgt_roundtrip_sync_status"),
                "load_stage_semantics_status": load_stage.get("status"),
                "typed_runtime_entities_ready": load_stage.get("typed_runtime_entities_ready"),
                "stage_semantics_ready": load_stage.get("stage_semantics_ready"),
                "load_stage_runtime_flow_status": load_stage_runtime.get("status"),
                "solve_flow_ready": load_stage_runtime.get("solve_flow_ready"),
                "viewer_flow_ready": load_stage_runtime.get("viewer_flow_ready"),
                "export_flow_ready": load_stage_runtime.get("export_flow_ready"),
                "audit_flow_ready": load_stage_runtime.get("audit_flow_ready"),
                "unsupported_hazard_queue_ready": load_stage_runtime.get("unsupported_hazard_queue_ready"),
                "load_family_inventory": load_stage_runtime.get("load_family_inventory"),
            },
            next_gate="attach source rows for currently unsupported hazard families before making those hazard-specific solver claims",
        ),
        _row(
            "G4",
            "Material, Section, Element Breadth",
            ledger="commercial_solver",
            status=_status(
                material_element_tangent.get("status") == "ready"
                and bool(material_element_tangent.get("line_beam_tangent_ready"))
                and bool(material_element_tangent.get("unsupported_queue_ready")),
                bool(mesh.get("used_real_section_properties")),
            ),
            blockers=[] if material_element_tangent.get("status") == "ready" else [
                "material_element_breadth_not_fully_coupled_to_global_tangent"
            ],
            evidence={
                "used_real_section_properties": mesh.get("used_real_section_properties"),
                "real_section_property_coverage_pct": mesh.get("real_section_property_coverage_pct"),
                "solve_mode": mesh.get("solve_mode"),
                "material_element_tangent_status": material_element_tangent.get("status"),
                "line_beam_tangent_ready": material_element_tangent.get("line_beam_tangent_ready"),
                "unsupported_queue_ready": material_element_tangent.get("unsupported_queue_ready"),
                "element_inventory": material_element_tangent.get("element_inventory"),
                "section_material_inventory": material_element_tangent.get("section_material_inventory"),
                "surface_membrane_tangent_ready": surface_membrane_ready,
                "surface_shell_full_bending_tangent_ready": surface_membrane.get(
                    "surface_shell_full_bending_tangent_ready"
                ),
                "surface_shell_bending_drilling_smoke_ready": surface_shell_bending_ready,
                "shell_calibration_benchmarks_ready": shell_calibration_ready,
                "shell_calibration_ready_case_count": shell_calibration.get("ready_case_count"),
                "shell_calibration_cases": shell_calibration.get("cases"),
                "coupled_frame_surface_sparse_equilibrium_ready": coupled_frame_surface_ready,
                "coupled_frame_shell_sparse_equilibrium_ready": coupled_frame_shell_ready,
                "surface_source_thickness_coverage_pct": surface_source_thickness_coverage_pct,
                "frame_material_nonlinear_tangent_ready": frame_material_nonlinear_ready,
                "frame_material_nonlinear_tangent_status": frame_material_nonlinear.get("status"),
                "frame_material_service_state_summary": frame_material_nonlinear.get(
                    "service_material_state_summary"
                ),
                "frame_material_probe_state_summary": frame_material_nonlinear.get(
                    "controlled_probe_material_state_summary"
                ),
                "frame_material_tangent_smoke_equilibrium": frame_material_nonlinear.get(
                    "material_tangent_smoke_equilibrium"
                ),
                "support_matrix": material_element_tangent.get("support_matrix"),
            },
            next_gate="promote full shell/plate/contact and path-dependent material Newton families only after tangent benchmarks",
        ),
        _row(
            "G5",
            "Design Code And Detailing Automation",
            ledger="commercial_solver",
            status=_status(
                kds_detailing.get("status") == "ready"
                and bool(kds_detailing.get("clause_breadth_ready"))
                and bool(kds_detailing.get("optimization_rows_guarded"))
                and bool(kds_detailing.get("trace_ready"))
                and bool(kds_detailing.get("unsupported_queue_ready")),
                kds_rule.is_file(),
            ),
            blockers=[] if kds_detailing.get("status") == "ready" else [
                "full_kds_member_detailing_clause_breadth_not_closed"
            ],
            evidence={
                "kds_rule_engine_present": kds_rule.is_file(),
                "kds_detailing_support_status": kds_detailing.get("status"),
                "clause_breadth_ready": kds_detailing.get("clause_breadth_ready"),
                "optimization_rows_guarded": kds_detailing.get("optimization_rows_guarded"),
                "trace_ready": kds_detailing.get("trace_ready"),
                "unsupported_queue_ready": kds_detailing.get("unsupported_queue_ready"),
                "clause_inventory": kds_detailing.get("clause_inventory"),
            },
            next_gate="promote unsupported steel/composite/seismic/project-specific detailing only after clause/source/review evidence",
        ),
        _row(
            "G6",
            "V&V, External Benchmarks, Residual Holdouts",
            ledger="commercial_solver",
            status=_status(external_receipts >= 4 and residual_closed >= 3, external=True),
            blockers=[] if external_receipts >= 4 and residual_closed >= 3 else list(strict_gate.get("blockers") or []),
            evidence={
                "external_receipt_attached_count": external_receipts,
                "external_expected_queue_count": strict_gate.get("external_expected_queue_count"),
                "residual_closed_count": residual_closed,
                "residual_expected_work_item_count": strict_gate.get("residual_expected_work_item_count"),
            },
            locally_closable=False,
            next_gate="attach EB receipts 4/4 and strict RH closures 3/3",
        ),
        _row(
            "G7",
            "Korean Medium/Large Real-Project Corpus",
            ledger="commercial_solver",
            status=_status(bridge_count == 0 and metadata_only == 0 and real_mgt_ok >= 4, bool(per_source)),
            blockers=[
                *(["repo_benchmark_bridge_mgt_present"] if bridge_count else []),
                *(["metadata_only_sources_present"] if metadata_only else []),
                *(["operator_attached_real_mgt_header_ok_below_target"] if real_mgt_ok < 4 else []),
            ],
            evidence={
                "medium_large_source_count": ingest_summary.get("medium_large_source_count"),
                "attached_count": ingest_summary.get("attached_count"),
                "metadata_only_count": metadata_only,
                "mgt_attached_count": ingest_summary.get("mgt_attached_count"),
                "mgt_header_ok_count": ingest_summary.get("mgt_header_ok_count"),
                "operator_attached_mgt_header_ok_count": ingest_summary.get(
                    "operator_attached_mgt_header_ok_count"
                ),
                "repo_benchmark_bridge_mgt_header_ok_count": ingest_summary.get(
                    "repo_benchmark_bridge_mgt_header_ok_count"
                ),
                "placeholder_mgt_count": ingest_summary.get("placeholder_mgt_count"),
                "ifc_attached_count": ingest_summary.get("ifc_attached_count"),
                "operator_attached_ifc_count": ingest_summary.get("operator_attached_ifc_count"),
                "curated_local_ifc_attached_count": ingest_summary.get(
                    "curated_local_ifc_attached_count"
                ),
                "curated_local_ifc_missing_count": ingest_summary.get(
                    "curated_local_ifc_missing_count"
                ),
                "pdf_derived_attached_count": ingest_summary.get("pdf_derived_attached_count"),
                "operator_attached_pdf_derived_count": ingest_summary.get(
                    "operator_attached_pdf_derived_count"
                ),
                "operator_attached_real_artifact_count": ingest_summary.get(
                    "operator_attached_real_artifact_count"
                ),
                "metadata_only_source_ids": ingest_summary.get("metadata_only_source_ids"),
                "repo_benchmark_bridge_source_ids": ingest_summary.get(
                    "repo_benchmark_bridge_source_ids"
                ),
                "operator_attach_required_source_ids": ingest_summary.get(
                    "operator_attach_required_source_ids"
                ),
                "operator_action_queue_count": ingest_summary.get(
                    "operator_action_queue_count"
                ),
                "operator_action_queue_source_ids": ingest_summary.get(
                    "operator_action_queue_source_ids"
                ),
                "operator_action_type_counts": ingest_summary.get(
                    "operator_action_type_counts"
                ),
                "operator_action_queue": korea.get("operator_action_queue"),
                "operator_action_packet": korea.get("operator_action_packet"),
                "operator_attachment_manifest_queue_status": (
                    korea_operator_attachment_queue.get("status")
                ),
                "operator_attachment_manifest_queue_attachment_count": (
                    korea_operator_attachment_queue.get("attachment_count")
                ),
                "operator_attachment_manifest_queue_autofill_candidate_status": (
                    korea_operator_attachment_queue.get("autofill_candidate_status")
                ),
                "operator_attachment_manifest_queue_auto_promotable_repo_candidate_count": (
                    korea_operator_attachment_queue.get(
                        "auto_promotable_repo_candidate_count"
                    )
                ),
                "operator_attachment_manifest_queue_minimum_operator_real_mgt_needed": (
                    korea_operator_attachment_queue.get("minimum_operator_real_mgt_needed")
                ),
                "operator_attachment_manifest_queue_source_mapping_blocked_action_count": (
                    korea_operator_attachment_queue.get(
                        "source_mapping_blocked_action_count"
                    )
                ),
                "operator_attachment_manifest_queue_rights_blocked_private_candidate_action_count": (
                    korea_operator_attachment_queue.get(
                        "rights_blocked_private_candidate_action_count"
                    )
                ),
                "operator_attachment_manifest_queue_priority_batches": (
                    korea_operator_attachment_queue.get("priority_batches")
                ),
                "operator_attachment_manifest_queue": korea_operator_attachment_queue,
                "operator_attachment_manifest_validation_ready_for_collection_overlay": (
                    korea_operator_attachment_queue_validation.get(
                        "ready_for_collection_overlay"
                    )
                ),
                "operator_attachment_manifest_validation_accepted_source_count": (
                    korea_operator_attachment_queue_validation.get("accepted_source_count")
                ),
                "operator_attachment_manifest_validation_rejected_source_count": (
                    korea_operator_attachment_queue_validation.get("rejected_source_count")
                ),
                "operator_attached_real_mgt_header_ok_target": ingest_summary.get(
                    "operator_attached_real_mgt_header_ok_target"
                ),
                "operator_attached_real_mgt_header_ok_remaining": ingest_summary.get(
                    "operator_attached_real_mgt_header_ok_remaining"
                ),
                "local_private_candidate_count": ingest_summary.get(
                    "local_private_candidate_count"
                ),
                "existing_local_private_candidate_count": ingest_summary.get(
                    "existing_local_private_candidate_count"
                ),
                "kr_local_private_candidate_count": ingest_summary.get(
                    "kr_local_private_candidate_count"
                ),
                "mgt_local_private_candidate_count": ingest_summary.get(
                    "mgt_local_private_candidate_count"
                ),
                "mgt_header_ok_local_private_candidate_count": ingest_summary.get(
                    "mgt_header_ok_local_private_candidate_count"
                ),
                "g7_counted_local_private_candidate_count": ingest_summary.get(
                    "g7_counted_local_private_candidate_count"
                ),
                "raw_redistribution_blocked_candidate_count": ingest_summary.get(
                    "raw_redistribution_blocked_candidate_count"
                ),
                "non_kr_candidate_count": ingest_summary.get("non_kr_candidate_count"),
                "catalog_source_unmatched_candidate_count": ingest_summary.get(
                    "catalog_source_unmatched_candidate_count"
                ),
                "operator_action_private_candidate_match_count": ingest_summary.get(
                    "operator_action_private_candidate_match_count"
                ),
                "operator_action_private_candidate_source_count": ingest_summary.get(
                    "operator_action_private_candidate_source_count"
                ),
                "operator_action_private_candidate_file_count": ingest_summary.get(
                    "operator_action_private_candidate_file_count"
                ),
                "operator_action_private_candidate_requires_rights_count": (
                    ingest_summary.get(
                        "operator_action_private_candidate_requires_rights_count"
                    )
                ),
                "repo_public_candidate_count": ingest_summary.get(
                    "repo_public_candidate_count"
                ),
                "repo_public_candidate_mgt_count": ingest_summary.get(
                    "repo_public_candidate_mgt_count"
                ),
                "repo_public_candidate_ifc_count": ingest_summary.get(
                    "repo_public_candidate_ifc_count"
                ),
                "repo_public_candidate_benchmark_bridge_count": ingest_summary.get(
                    "repo_public_candidate_benchmark_bridge_count"
                ),
                "g7_counted_repo_public_candidate_count": ingest_summary.get(
                    "g7_counted_repo_public_candidate_count"
                ),
                "operator_action_repo_candidate_match_count": ingest_summary.get(
                    "operator_action_repo_candidate_match_count"
                ),
                "operator_action_repo_candidate_source_count": ingest_summary.get(
                    "operator_action_repo_candidate_source_count"
                ),
                "operator_action_repo_candidate_file_count": ingest_summary.get(
                    "operator_action_repo_candidate_file_count"
                ),
                "operator_action_repo_candidate_exact_source_match_count": (
                    ingest_summary.get(
                        "operator_action_repo_candidate_exact_source_match_count"
                    )
                ),
                "operator_action_repo_candidate_exact_clean_count": (
                    ingest_summary.get(
                        "operator_action_repo_candidate_exact_clean_count"
                    )
                ),
                "operator_action_repo_candidate_exact_blocker_counts": (
                    ingest_summary.get(
                        "operator_action_repo_candidate_exact_blocker_counts"
                    )
                ),
                "operator_action_repo_candidate_requires_source_mapping_count": (
                    ingest_summary.get(
                        "operator_action_repo_candidate_requires_source_mapping_count"
                    )
                ),
                "operator_action_repo_candidate_ifc_source_mapping_candidate_count": (
                    ingest_summary.get(
                        "operator_action_repo_candidate_ifc_source_mapping_candidate_count"
                    )
                ),
                "operator_action_repo_candidate_ifc_source_mapping_candidate_source_count": (
                    ingest_summary.get(
                        "operator_action_repo_candidate_ifc_source_mapping_candidate_source_count"
                    )
                ),
                "operator_action_repo_candidate_ifc_source_mapping_candidate_file_count": (
                    ingest_summary.get(
                        "operator_action_repo_candidate_ifc_source_mapping_candidate_file_count"
                    )
                ),
                "operator_action_repo_candidate_benchmark_bridge_count": (
                    ingest_summary.get(
                        "operator_action_repo_candidate_benchmark_bridge_count"
                    )
                ),
                "local_private_candidate_artifacts": korea.get(
                    "local_private_candidate_artifacts"
                ),
                "operator_action_private_candidate_matches": korea.get(
                    "operator_action_private_candidate_matches"
                ),
                "repo_public_candidate_artifacts": korea.get(
                    "repo_public_candidate_artifacts"
                ),
                "operator_action_repo_candidate_matches": korea.get(
                    "operator_action_repo_candidate_matches"
                ),
                "operator_action_repo_candidate_ifc_source_mapping_candidates": (
                    korea.get(
                        "operator_action_repo_candidate_ifc_source_mapping_candidates"
                    )
                ),
                "operator_action_queue": korea.get("operator_action_queue"),
                "repo_benchmark_bridge_count": bridge_count,
                "operator_attached_real_mgt_header_ok_count": real_mgt_ok,
            },
            locally_closable=False,
            next_gate="replace bridge lanes with permitted real operator-attached MGT/IFC/PDF-derived artifacts",
        ),
        _row(
            "G8",
            "Optimization And AI Productization",
            ledger="commercial_solver",
            status=_status(optimization_audit.get("status") == "ready", True),
            blockers=[] if optimization_audit.get("status") == "ready" else [
                *(["production_ml_not_wired"] if not ml.get("production_ml_wired") else []),
                *(["production_pareto_not_wired"] if not ml.get("multi_objective_pareto_wired") else []),
            ],
            evidence={
                "ml_status": ml.get("status"),
                "production_ml_wired": ml.get("production_ml_wired"),
                "multi_objective_pareto_wired": ml.get("multi_objective_pareto_wired"),
                "research_pareto_archive_ready": ml.get("research_pareto_archive_ready"),
                "optimization_productization_audit_status": optimization_audit.get("status"),
                "production_pareto_wired_by_audit": optimization_audit.get("production_pareto_wired"),
                "ml_bypass_prevented": optimization_audit.get("ml_bypass_prevented"),
            },
            next_gate="production optimization proposals replay through solver/code/cost gates with governed ML/Pareto promotion",
        ),
        _row(
            "G9",
            "Runtime, GPU, Performance, And Scale",
            ledger="commercial_solver",
            status=_status(g9_runtime_ready and rocm_sparse_closure_ready, g9_runtime_ready),
            blockers=(
                []
                if rocm_sparse_closure_ready
                else ["full_solver_gpu_evidence_not_closed"]
            ),
            evidence={
                "runtime_gate_ok": runtime_gate.get("ok"),
                "gpu_newton_terminal_proven": gpu.get("gpu_newton_terminal_proven"),
                "gpu_mainloop_residency_observed": gpu.get("gpu_mainloop_residency_observed"),
                "rocm_workstation_status": rocm_gpu.get("status"),
                "rocm_hardware_ready": rocm_gpu.get("rocm_hardware_ready"),
                "torch_rocm_runtime_ready": rocm_gpu.get("torch_rocm_runtime_ready"),
                "rocm_target_hardware_match": rocm_gpu.get("target_hardware_match"),
                "nvidia_smi_not_required_for_amd_rocm": rocm_gpu.get(
                    "nvidia_smi_not_required_for_amd_rocm"
                ),
                "rocm_tool_paths": rocm_gpu.get("tool_paths"),
                "rocm_device_nodes": rocm_gpu.get("device_nodes"),
                "rocm_device_names": rocm_gpu.get("device_names"),
                "rocm_gfx_targets": rocm_gpu.get("gfx_targets"),
                "torch_version_hip": _get(rocm_gpu, "torch_rocm_probe", "torch_version_hip"),
                "pytorch_device_label_policy": rocm_gpu.get("pytorch_device_label_policy"),
                "solver_runtime_backend_policy_status": solver_runtime_backend_policy.get("status"),
                "official_solver_compute_backend": solver_runtime_backend_policy.get(
                    "official_solver_compute_backend"
                ),
                "official_solver_backend": solver_runtime_backend_policy.get(
                    "official_solver_backend"
                ),
                "official_solver_backend_family": solver_runtime_backend_policy.get(
                    "official_solver_backend_family"
                ),
                "gpu_required_for_commercial_solver_closure": solver_runtime_backend_policy.get(
                    "gpu_required_for_commercial_solver_closure"
                ),
                "torch_device_label_is_pytorch_rocm_compat_alias": solver_runtime_backend_policy.get(
                    "torch_device_label_is_pytorch_rocm_compat_alias"
                ),
                "cpu_diagnostic_promotes_solver_closure": solver_runtime_backend_policy.get(
                    "cpu_diagnostic_promotes_solver_closure"
                ),
                "cpu_solver_fallback_detected": solver_runtime_backend_policy.get(
                    "cpu_solver_fallback_detected"
                ),
                "cpu_fallback_allowed_for_official_solver_closure": solver_runtime_backend_policy.get(
                    "cpu_fallback_allowed_for_official_solver_closure"
                ),
                "cpu_reference_allowed_for_validation_replay": solver_runtime_backend_policy.get(
                    "cpu_reference_allowed_for_validation_replay"
                ),
                "mgt_rocm_sparse_probe_status": rocm_sparse_probe.get("status"),
                "rocm_sparse_solver_probe_ready": rocm_sparse_probe.get("rocm_sparse_solver_probe_ready"),
                "line_frame_rocm_sparse_solver_ready": rocm_sparse_probe.get(
                    "line_frame_rocm_sparse_solver_ready"
                ),
                "full_line_rocm_sparse_equilibrium_ready": rocm_sparse_probe.get(
                    "full_line_rocm_sparse_equilibrium_ready"
                ),
                "full_frame_6dof_rocm_sparse_equilibrium_ready": rocm_sparse_probe.get(
                    "full_frame_6dof_rocm_sparse_equilibrium_ready"
                ),
                "full_frame_6dof_rocm_sparse_cg_equilibrium_ready": rocm_sparse_probe.get(
                    "full_frame_6dof_rocm_sparse_cg_equilibrium_ready"
                ),
                "full_frame_6dof_rocm_component_direct_equilibrium_ready": rocm_sparse_probe.get(
                    "full_frame_6dof_rocm_component_direct_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_cg_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_cg_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_bicgstab_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_bicgstab_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_block_bicgstab_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_block_bicgstab_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_block_gmres_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_block_gmres_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_node_block_gmres_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_node_block_gmres_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_solution_fusion_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_solution_fusion_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_hotspot_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_hotspot_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_dof_hotspot_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_dof_hotspot_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_wide_dof_hotspot_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_wide_dof_hotspot_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_column_lstsq_hotspot_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_column_lstsq_hotspot_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_direct_column_lstsq_hotspot_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_direct_column_lstsq_hotspot_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_compressed_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_compressed_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_hotspot_solution_fusion_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_hotspot_solution_fusion_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_post_hotspot_node_block_gmres_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_post_hotspot_node_block_gmres_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_post_hotspot_solution_fusion_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_post_hotspot_solution_fusion_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_small_component_direct_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_small_component_direct_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_post_hotspot_block_gmres_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_post_hotspot_block_gmres_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_post_small_component_solution_fusion_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_post_small_component_solution_fusion_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_post_fusion_row_neighborhood_lstsq_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_post_fusion_row_neighborhood_lstsq_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_residual_row_kaczmarz_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_residual_row_kaczmarz_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_residual_polishing_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_residual_polishing_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_large_component_coarse_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_large_component_coarse_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_micro_residual_row_kaczmarz_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_micro_residual_row_kaczmarz_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_residual_row_block_lstsq_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_residual_row_block_lstsq_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_post_block_lstsq_residual_row_kaczmarz_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_post_block_lstsq_residual_row_kaczmarz_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_post_kaczmarz_residual_row_block_lstsq_refinement_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_post_kaczmarz_residual_row_block_lstsq_refinement_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_post_refinement_residual_row_kaczmarz_polish_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_post_refinement_residual_row_kaczmarz_polish_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_post_polish_residual_row_block_lstsq_refinement_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_post_polish_residual_row_block_lstsq_refinement_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_post_block_lstsq_solution_fusion_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_post_block_lstsq_solution_fusion_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_post_fusion_residual_row_block_lstsq_refinement_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_post_fusion_residual_row_block_lstsq_refinement_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_overlapping_schwarz_patch_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_overlapping_schwarz_patch_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_additive_schwarz_krylov_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_additive_schwarz_krylov_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_deflated_jacobi_krylov_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_deflated_jacobi_krylov_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_structural_node_coarse_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_structural_node_coarse_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_enriched_structural_node_coarse_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_enriched_structural_node_coarse_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_schur_interface_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_schur_interface_correction_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_post_schur_residual_row_block_lstsq_refinement_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_post_schur_residual_row_block_lstsq_refinement_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_rocalution_preconditioned_krylov_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_rocalution_preconditioned_krylov_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_host_ilu_device_gmres_equilibrium_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_host_ilu_device_gmres_equilibrium_ready"
                ),
                "surface_shell_rocm_sparse_spsolve_supported": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_spsolve_supported"
                ),
                "surface_shell_rocm_sparse_residual_replay_ready": rocm_sparse_probe.get(
                    "surface_shell_rocm_sparse_residual_replay_ready"
                ),
                "coupled_frame_shell_rocm_sparse_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_cg_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_cg_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_bicgstab_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_bicgstab_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_block_bicgstab_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_block_bicgstab_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_restarted_block_bicgstab_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_restarted_block_bicgstab_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_restarted_defect_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_restarted_defect_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_block_gmres_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_block_gmres_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_node_block_gmres_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_node_block_gmres_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_solution_fusion_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_solution_fusion_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_hotspot_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_hotspot_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_dof_hotspot_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_dof_hotspot_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_wide_dof_hotspot_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_wide_dof_hotspot_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_column_lstsq_hotspot_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_column_lstsq_hotspot_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_direct_column_lstsq_hotspot_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_direct_column_lstsq_hotspot_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_compressed_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_compressed_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_hotspot_solution_fusion_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_hotspot_solution_fusion_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_post_hotspot_node_block_gmres_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_post_hotspot_node_block_gmres_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_post_hotspot_solution_fusion_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_post_hotspot_solution_fusion_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_small_component_direct_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_small_component_direct_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_post_hotspot_block_gmres_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_post_hotspot_block_gmres_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_post_small_component_solution_fusion_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_post_small_component_solution_fusion_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_post_fusion_row_neighborhood_lstsq_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_post_fusion_row_neighborhood_lstsq_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_residual_row_kaczmarz_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_residual_row_kaczmarz_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_residual_polishing_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_residual_polishing_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_large_component_coarse_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_large_component_coarse_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_micro_residual_row_kaczmarz_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_micro_residual_row_kaczmarz_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_residual_row_block_lstsq_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_residual_row_block_lstsq_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_post_block_lstsq_residual_row_kaczmarz_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_post_block_lstsq_residual_row_kaczmarz_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_post_kaczmarz_residual_row_block_lstsq_refinement_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_post_kaczmarz_residual_row_block_lstsq_refinement_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_post_refinement_residual_row_kaczmarz_polish_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_post_refinement_residual_row_kaczmarz_polish_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_post_polish_residual_row_block_lstsq_refinement_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_post_polish_residual_row_block_lstsq_refinement_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_post_block_lstsq_solution_fusion_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_post_block_lstsq_solution_fusion_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_post_fusion_residual_row_block_lstsq_refinement_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_post_fusion_residual_row_block_lstsq_refinement_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_overlapping_schwarz_patch_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_overlapping_schwarz_patch_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_additive_schwarz_krylov_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_additive_schwarz_krylov_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_deflated_jacobi_krylov_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_deflated_jacobi_krylov_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_structural_node_coarse_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_structural_node_coarse_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_enriched_structural_node_coarse_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_enriched_structural_node_coarse_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_schur_interface_correction_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_schur_interface_correction_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_post_schur_residual_row_block_lstsq_refinement_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_post_schur_residual_row_block_lstsq_refinement_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_rocalution_preconditioned_krylov_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_rocalution_preconditioned_krylov_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_host_ilu_device_gmres_equilibrium_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_host_ilu_device_gmres_equilibrium_ready"
                ),
                "coupled_frame_shell_rocm_sparse_spsolve_supported": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_spsolve_supported"
                ),
                "coupled_frame_shell_rocm_sparse_residual_replay_ready": rocm_sparse_probe.get(
                    "coupled_frame_shell_rocm_sparse_residual_replay_ready"
                ),
                "full_3d_rocm_nonlinear_equilibrium_ready": rocm_sparse_probe.get(
                    "full_3d_rocm_nonlinear_equilibrium_ready"
                ),
                "mgt_rocm_sparse_probe_rows": rocm_sparse_probe.get("probe_rows"),
                "rocalution_shell_preconditioner_sweep": _rocalution_focused_sweep_summary(
                    rocalution_shell_sweep
                ),
                "rocalution_shell_saamg_debug_sweep": _rocalution_focused_sweep_summary(
                    rocalution_saamg_debug
                ),
                "dof_block_schur_large_ras_current_shell_probe": _dof_block_schur_focused_summary(
                    dof_block_schur_large_ras_current_shell
                ),
                "dof_block_schur_streamed_large_ras_shell_probe": _dof_block_schur_focused_summary(
                    dof_block_schur_streamed_large_ras_shell
                ),
                "dof_block_schur_multiplicative_ras_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_multiplicative_ras_shell
                ),
                "dof_block_schur_interface_edge_coarse_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_shell_smoke
                ),
                "dof_block_schur_interface_edge_coarse_shell_probe": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_shell_probe
                ),
                "dof_block_schur_interface_edge_smoothed_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_smoothed_shell_smoke
                ),
                "dof_block_schur_interface_edge_smoothed_shell_probe": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_smoothed_shell_probe
                ),
                "dof_block_schur_interface_edge_repeated_coarse_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_repeated_shell_smoke
                ),
                "dof_block_schur_interface_edge_repeated_coarse_shell_probe": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_repeated_shell_probe
                ),
                "dof_block_schur_interface_edge_rhs_weighted_shell_weight_sweep_probe": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_rhs_weighted_shell_weight_sweep
                ),
                "dof_block_schur_interface_edge_rhs_signed_shell_weight_sweep_probe": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_rhs_signed_shell_weight_sweep
                ),
                "dof_block_schur_interface_edge_rhs_enriched_shell_weight_sweep_probe": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_rhs_enriched_shell_weight_sweep
                ),
                "dof_block_schur_interface_edge_rhs_enriched_restricted_shell_weight_sweep_probe": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_rhs_enriched_restricted_shell_weight_sweep
                ),
                "dof_block_schur_interface_edge_rhs_enriched_restricted_shell_fine_weight_probe": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_rhs_enriched_restricted_shell_fine_weight
                ),
                "dof_block_schur_interface_edge_rhs_enriched_restricted_coupled_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_rhs_enriched_restricted_coupled_smoke
                ),
                "dof_block_schur_interface_edge_rhs_enriched_restricted_coupled_current_single_probe": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_rhs_enriched_restricted_coupled_current_single
                ),
                "dof_block_schur_interface_edge_rhs_enriched_orthogonalized_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_rhs_enriched_orthogonalized_shell_smoke
                ),
                "dof_block_schur_interface_edge_rhs_enriched_orthogonalized_coupled_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_rhs_enriched_orthogonalized_coupled_smoke
                ),
                "dof_block_schur_interface_edge_energy_restricted_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_energy_restricted_shell_smoke
                ),
                "dof_block_schur_interface_edge_geneo_restricted_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_geneo_restricted_shell_smoke
                ),
                "dof_block_schur_interface_edge_geneo_mode_count_sweep_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_geneo_mode_count_sweep_shell_smoke
                ),
                "dof_block_schur_interface_edge_geneo_selection_sweep_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_geneo_selection_sweep_shell_smoke
                ),
                "dof_block_schur_interface_edge_geneo_weight_pass_sweep_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_geneo_weight_pass_sweep_shell_smoke
                ),
                "dof_block_schur_interface_edge_geneo_schur_cycle_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_geneo_schur_cycle_shell_smoke
                ),
                "dof_block_schur_interface_edge_geneo_harmonic_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_geneo_harmonic_shell_smoke
                ),
                "dof_block_schur_interface_edge_geneo_harmonic_depth_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_geneo_harmonic_depth_shell_smoke
                ),
                "dof_block_schur_interface_edge_geneo_harmonic_qr_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_geneo_harmonic_qr_shell_smoke
                ),
                "dof_block_schur_interface_edge_geneo_harmonic_residual_restriction_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_geneo_harmonic_residual_restriction_shell_smoke
                ),
                "dof_block_schur_interface_edge_geneo_harmonic_dof_filter_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_geneo_harmonic_dof_filter_shell_smoke
                ),
                "dof_block_schur_interface_edge_geneo_harmonic_energy_orthogonalization_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_edge_geneo_harmonic_energy_orthogonalization_shell_smoke
                ),
                "dof_block_schur_interface_pair_dd_smoother_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_pair_dd_smoother_shell_smoke
                ),
                "dof_block_schur_interface_pair_dd_swept_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_pair_dd_swept_shell_smoke
                ),
                "dof_block_schur_interface_pair_dd_coarse_rebalance_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_pair_dd_coarse_rebalance_shell_smoke
                ),
                "dof_block_schur_interface_pair_dd_coarse_rebalance_weight_sweep_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_interface_pair_dd_coarse_rebalance_weight_sweep_shell_smoke
                ),
                "dof_block_schur_rigid_body_current_coupled_smoke_baseline": _dof_block_schur_focused_summary(
                    dof_block_schur_rigid_body_current_coupled_smoke_baseline
                ),
                "dof_block_schur_rigid_body_restricted_interface_hybrid_coupled_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_rigid_body_restricted_interface_hybrid_coupled_smoke
                ),
                "dof_block_schur_rigid_body_restricted_interface_hybrid_coupled_tiny_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_rigid_body_restricted_interface_hybrid_coupled_tiny_smoke
                ),
                "dof_block_schur_residual_region_diagnostic_shell_smoke": _dof_block_schur_focused_summary(
                    dof_block_schur_residual_region_diagnostic_shell
                ),
                "full_3d_closed": full_3d_closed,
                "full_line_sparse_cpu_backend": _get(full_line_sparse, "runtime_metrics", "backend"),
                "full_line_sparse_total_seconds": _get(full_line_sparse, "runtime_metrics", "total_seconds"),
                "full_line_sparse_elastic_equilibrium_ready": full_line_sparse_ready,
                "full_line_sparse_geometric_equilibrium_ready": full_line_sparse.get(
                    "full_line_mesh_linearized_geometric_equilibrium_ready"
                ),
                "full_line_sparse_geometric_equilibrium_metrics": full_line_sparse.get(
                    "geometric_equilibrium_metrics"
                ),
                "full_line_sparse_linearized_geometric_tangent": full_line_sparse.get(
                    "linearized_geometric_tangent"
                ),
                "full_frame_6dof_cpu_backend": _get(full_frame_6dof, "runtime_metrics", "backend"),
                "full_frame_6dof_total_seconds": _get(full_frame_6dof, "runtime_metrics", "total_seconds"),
                "full_frame_6dof_sparse_elastic_equilibrium_ready": full_frame_6dof_ready,
                "full_frame_6dof_linearized_geometric_equilibrium_ready": full_frame_6dof.get(
                    "full_frame_6dof_linearized_geometric_equilibrium_ready"
                ),
                "full_frame_6dof_deformed_state_pdelta_equilibrium_ready": full_frame_6dof.get(
                    "full_frame_6dof_deformed_state_pdelta_equilibrium_ready"
                ),
                "full_frame_6dof_equilibrium_metrics": full_frame_6dof.get("equilibrium_metrics"),
                "full_frame_6dof_geometric_equilibrium_metrics": full_frame_6dof.get(
                    "geometric_equilibrium_metrics"
                ),
                "full_frame_6dof_deformed_state_pdelta_path": full_frame_6dof.get(
                    "deformed_state_pdelta_path"
                ),
                "full_frame_6dof_linear_solver_refinement": full_frame_6dof.get(
                    "linear_solver_refinement"
                ),
                "pdelta_continuation_status": pdelta_continuation.get("status"),
                "full_load_pdelta_continuation_ready": pdelta_continuation.get(
                    "full_load_pdelta_continuation_ready"
                ),
                "pdelta_continuation_max_converged_load_scale": pdelta_continuation.get(
                    "max_converged_load_scale"
                ),
                "pdelta_direct_load_step_max_converged_load_scale": pdelta_continuation.get(
                    "direct_load_step_max_converged_load_scale"
                ),
                "pdelta_continuation_first_failed_load_scale": pdelta_continuation.get(
                    "first_failed_load_scale"
                ),
                "pdelta_post_converged_micro_step_probe": pdelta_continuation.get(
                    "post_converged_micro_step_probe"
                ),
                "pdelta_adaptive_micro_continuation_probe": pdelta_continuation.get(
                    "adaptive_micro_continuation_probe"
                ),
                "pdelta_post_failed_relaxation_sensitivity_probe": pdelta_continuation.get(
                    "post_failed_relaxation_sensitivity_probe"
                ),
                "pdelta_secant_predictor_probe": pdelta_continuation.get("secant_predictor_probe"),
                "pdelta_secant_micro_continuation_probe": pdelta_continuation.get(
                    "secant_micro_continuation_probe"
                ),
                "pdelta_fine_secant_micro_continuation_probe": pdelta_continuation.get(
                    "fine_secant_micro_continuation_probe"
                ),
                "pdelta_frontier_diagnostic": pdelta_frontier_diagnostic,
                "pdelta_frontier_residual_jacobian_summary": pdelta_residual_jacobian_summary,
                "pdelta_frontier_residual_jacobian_probe": pdelta_continuation.get(
                    "frontier_residual_jacobian_probe"
                ),
                "pdelta_first_failed_one_step_line_search_probe": pdelta_continuation.get(
                    "first_failed_one_step_line_search_probe"
                ),
                "pdelta_first_failed_anderson_acceleration_probe": pdelta_continuation.get(
                    "first_failed_anderson_acceleration_probe"
                ),
                "pdelta_first_failed_coefficient_bounded_anderson_probe": pdelta_continuation.get(
                    "first_failed_coefficient_bounded_anderson_probe"
                ),
                "pdelta_first_failed_residual_trust_region_anderson_probe": pdelta_continuation.get(
                    "first_failed_residual_trust_region_anderson_probe"
                ),
                "surface_membrane_cpu_backend": _get(surface_membrane, "runtime_metrics", "backend"),
                "surface_membrane_total_seconds": _get(surface_membrane, "runtime_metrics", "total_seconds"),
                "surface_membrane_smoke_solve_ready": surface_membrane_ready,
                "surface_shell_bending_cpu_backend": _get(
                    surface_shell_bending, "runtime_metrics", "backend"
                ),
                "surface_shell_bending_total_seconds": _get(
                    surface_shell_bending, "runtime_metrics", "total_seconds"
                ),
                "surface_shell_bending_drilling_smoke_ready": surface_shell_bending_ready,
                "surface_source_thickness_coverage_pct": surface_source_thickness_coverage_pct,
                "coupled_frame_surface_cpu_backend": _get(
                    coupled_frame_surface, "runtime_metrics", "backend"
                ),
                "coupled_frame_surface_total_seconds": _get(
                    coupled_frame_surface, "runtime_metrics", "total_seconds"
                ),
                "coupled_frame_surface_sparse_equilibrium_ready": coupled_frame_surface_ready,
                "coupled_frame_shell_cpu_backend": _get(
                    coupled_frame_shell, "runtime_metrics", "backend"
                ),
                "coupled_frame_shell_total_seconds": _get(
                    coupled_frame_shell, "runtime_metrics", "total_seconds"
                ),
                "coupled_frame_shell_sparse_equilibrium_ready": coupled_frame_shell_ready,
            },
            next_gate=(
                "promote nonlinear/full-load GPU paths, pure-device preconditioners, and scale evidence beyond shell/coupled smoke probes"
            ),
        ),
        _row(
            "G10",
            "Product UX, Reports, Governance, Support",
            ledger="commercial_solver",
            status=_status(governance.get("status") == "ready", workstation.get("status") == "ready"),
            blockers=[] if governance.get("status") == "ready" else ["independent_solver_governance_and_support_workflow_not_closed"],
            evidence={
                "workstation_delivery_status": workstation.get("status"),
                "workstation_gates": workstation.get("gates_passed") or workstation.get("summary_line"),
                "solver_governance_support_status": governance.get("status"),
                "unsupported_state_first_report_policy": governance.get("unsupported_state_first_report_policy"),
            },
            next_gate="customer report separates solver/proxy/unsupported states and signed engineer review workflow",
        ),
    ]


def _ai_rows(productization_dir: Path | None = None) -> list[dict[str, Any]]:
    productization = Path(productization_dir or PRODUCTIZATION)
    ml = _load(productization / "ml_multi_objective_status.json")
    gate = ml.get("ml_surrogate_production_gate") if isinstance(ml.get("ml_surrogate_production_gate"), dict) else {}
    ai_contracts = _load(productization / "ai_engine_productization_contracts.json")
    physics_contract = _load(productization / "ai_physics_guard_contract.json")
    physics_execution = _load(productization / "ai_physics_guard_execution.json")
    inference_receipt = _load(productization / "ai_inference_runtime_receipt.json")
    model_registry = _load(productization / "ai_model_registry.json")
    safety_contract = _load(productization / "ai_safety_governance_contract.json")
    decision_trace = _load(productization / "ai_decision_trace_contract.json")
    review_queue = _load(productization / "ai_review_queue_contract.json")
    decision_review = _load(productization / "ai_decision_review_artifacts.json")
    decision_trace_ledger = _load(productization / "ai_decision_trace_ledger.json")
    review_queue_runtime = _load(productization / "ai_review_queue.json")
    input_receipt = _load(productization / "ai_input_semantic_normalization_receipt.json")
    code_guard = _load(productization / "ai_code_reasoning_guard.json")
    pdelta_continuation = _load(productization / "mgt_pdelta_continuation_probe.json")
    pdelta_residual_jacobian_summary = _pdelta_residual_jacobian_summary(pdelta_continuation)
    korea = _load(KOREA_OPEN_DATA / "korean_medium_large_ingest_receipt.json")
    bundle = _load(productization / "delivery_evidence_bundle.json")
    workstation = _load(REPO_ROOT / "implementation/phase1/workstation_delivery_readiness.json")
    kds_rule = REPO_ROOT / "implementation/phase1/kds_rc_rule_engine.py"
    env = REPO_ROOT / "implementation/phase1/design_optimization_env.py"

    ingest_summary = korea.get("summary") if isinstance(korea.get("summary"), dict) else {}
    runner_scan = ml.get("runner_static_scan") if isinstance(ml.get("runner_static_scan"), dict) else {}
    runner_has_ml = any(bool(rows) for rows in runner_scan.values() if isinstance(rows, list))
    policy_replay_ready = bool(decision_review.get("policy_replay_contract_ready"))
    decision_trace_ready = decision_trace_ledger.get("status") == "ready"
    review_queue_ready = review_queue_runtime.get("status") == "ready"
    registry_states = set(model_registry.get("registry_states") or [])
    registry_contract_closed = (
        model_registry.get("schema_version") == "ai-model-registry.v1"
        and {"candidate", "shadow", "production", "deprecated"} <= registry_states
        and isinstance(model_registry.get("promotion_requirements"), list)
        and bool(model_registry.get("rollback_contract", {}).get("required"))
        and bool(model_registry.get("drift_monitoring_contract", {}).get("required"))
        and bool(model_registry.get("release_note_contract", {}).get("required"))
    )
    safety_states = set(safety_contract.get("allowed_result_states") or [])
    promotion_requirements = set(safety_contract.get("final_report_promotion_requires") or [])
    safety_contract_closed = (
        safety_contract.get("schema_version") == "ai-safety-governance-contract.v1"
        and safety_contract.get("status") == "contract_ready"
        and {
            "auto_applied",
            "suggested_only",
            "blocked",
            "engineer_review_required",
            "unsupported",
        }
        <= safety_states
        and {"solver_replay_passed", "code_check_replay_passed", "human_review_recorded"}
        <= promotion_requirements
        and isinstance(safety_contract.get("data_use_contract"), dict)
    )
    inference_runtime_closed = inference_runtime_contract_closed(inference_receipt)

    return [
        _row(
            "AI-G1",
            "Input Model Understanding And Semantic Normalization",
            ledger="ai_engine",
            status=_status(input_receipt.get("status") == "ready", bool(ingest_summary)),
            blockers=[] if input_receipt.get("status") == "ready" else ["ai_semantic_parser_confidence_repair_queue_not_closed"],
            evidence={
                "medium_large_source_count": ingest_summary.get("medium_large_source_count"),
                "metadata_only_count": ingest_summary.get("metadata_only_count"),
                "mgt_header_ok_count": ingest_summary.get("mgt_header_ok_count"),
                "input_semantic_normalization_status": input_receipt.get("status"),
                "unsupported_queue_count": len(input_receipt.get("unsupported_queue") or []),
            },
            next_gate="AI-generated typed structure entities include source provenance, confidence, repair diff, and unsupported queue",
        ),
        _row(
            "AI-G2",
            "Structural Response Surrogate And Residual Learning",
            ledger="ai_engine",
            status=_status(
                bool(ml.get("production_ml_wired"))
                and bool(gate.get("checkpoint_ready"))
                and bool(gate.get("checkpoint_validated"))
                and bool(gate.get("ood_gate_ready"))
                and bool(gate.get("solver_fallback_ready"))
            ),
            blockers=[
                *(["production_ml_not_wired"] if not ml.get("production_ml_wired") else []),
                *(["validated_checkpoint_missing"] if not gate.get("checkpoint_ready") else []),
                *(["checkpoint_validation_missing"] if not gate.get("checkpoint_validated") else []),
                *(["ood_gate_missing"] if not gate.get("ood_gate_ready") else []),
                *(["solver_fallback_missing"] if not gate.get("solver_fallback_ready") else []),
            ],
            evidence={
                "production_ml_wired": ml.get("production_ml_wired"),
                "checkpoint_ready": gate.get("checkpoint_ready"),
                "checkpoint_validated": gate.get("checkpoint_validated"),
                "ood_gate_ready": gate.get("ood_gate_ready"),
                "solver_fallback_ready": gate.get("solver_fallback_ready"),
                "gate_status": gate.get("status"),
                "pdelta_frontier_residual_jacobian_summary": pdelta_residual_jacobian_summary,
            },
            next_gate="validated checkpoint plus dataset/model card, OOD gate, uncertainty, and solver fallback",
        ),
        _row(
            "AI-G3",
            "Optimization Policy And Design Action Space",
            ledger="ai_engine",
            status=_status(policy_replay_ready, env.is_file() and not runner_has_ml),
            blockers=[] if policy_replay_ready else ["production_policy_replay_contract_not_closed"],
            evidence={
                "deterministic_env_present": env.is_file(),
                "runner_static_scan": runner_scan,
                "production_ml_refs_in_runner": runner_has_ml,
                "proxy_divergence_count": _get(bundle, "summary", "proxy_divergence_count"),
                "policy_replay_contract_ready": policy_replay_ready,
                "decision_review_status": decision_review.get("status"),
            },
            next_gate="action/state/reward/constraint vector with hard action mask and solver/code replay evidence",
        ),
        _row(
            "AI-G4",
            "Physics-Informed Hybrid AI",
            ledger="ai_engine",
            status=_status(
                physics_execution.get("status") == "ready",
                physics_contract.get("status") == "contract_ready_model_not_promoted",
            ),
            blockers=[] if physics_execution.get("status") == "ready" else ["physics_residual_energy_bc_ai_gate_not_executed"],
            evidence={
                "physics_guard_contract_status": physics_contract.get("status"),
                "required_gate_count": len(physics_contract.get("required_gates") or []),
                "physics_guard_execution_status": physics_execution.get("status"),
                "correction_promotion_blocked": physics_execution.get("correction_promotion_blocked"),
            },
            next_gate="equilibrium, energy monotonicity, BC violation, and OOD unsupported gates for AI corrections",
        ),
        _row(
            "AI-G5",
            "Design Code And Regulation Reasoning AI",
            ledger="ai_engine",
            status=_status(code_guard.get("status") == "ready", kds_rule.is_file()),
            blockers=[] if code_guard.get("status") == "ready" else ["code_reasoning_citation_hallucination_guard_not_closed"],
            evidence={
                "kds_rule_engine_present": kds_rule.is_file(),
                "code_reasoning_guard_status": code_guard.get("status"),
                "governing_clause_count": code_guard.get("governing_clause_count"),
            },
            next_gate="clause citation, edition, governing-combo trace, unsupported queue, and engineer review workflow",
        ),
        _row(
            "AI-G6",
            "Explainability, Audit, Reproducibility",
            ledger="ai_engine",
            status=_status(decision_trace_ready, bundle.get("status") == "ready" and decision_trace.get("status") == "contract_ready"),
            blockers=[] if decision_trace_ready else ["ai_decision_causality_sensitivity_trace_not_closed"],
            evidence={
                "delivery_bundle_status": bundle.get("status"),
                "bundle_blockers": bundle.get("blockers"),
                "decision_trace_contract_status": decision_trace.get("status"),
                "decision_trace_ledger_status": decision_trace_ledger.get("status"),
                "proposal_count": decision_trace_ledger.get("proposal_count"),
            },
            next_gate="AI suggestion traces include alternatives, sensitivity, solver/code replay, and human decision log",
        ),
        _row(
            "AI-G7",
            "Dataset, ModelOps, ReleaseOps",
            ledger="ai_engine",
            status=_status(registry_contract_closed, model_registry.get("schema_version") == "ai-model-registry.v1"),
            blockers=[] if registry_contract_closed else ["checkpoint_registry_promotion_rollback_drift_monitoring_missing"],
            evidence={
                "ml_status": ml.get("status"),
                "checkpoint_path": gate.get("checkpoint_path"),
                "model_registry_status": model_registry.get("status"),
                "contracts_status": ai_contracts.get("status"),
                "registry_contract_closed": registry_contract_closed,
            },
            next_gate="checkpoint registry with candidate/shadow/production states, dataset/model cards, drift monitoring",
        ),
        _row(
            "AI-G8",
            "Safety, Responsibility, Product Governance",
            ledger="ai_engine",
            status=_status(safety_contract_closed, workstation.get("status") == "ready" and safety_contract.get("status") == "contract_ready"),
            blockers=[] if safety_contract_closed else ["ai_auto_suggest_blocked_review_state_contract_not_closed"],
            evidence={
                "workstation_delivery_status": workstation.get("status"),
                "safety_governance_contract_status": safety_contract.get("status"),
                "safety_contract_closed": safety_contract_closed,
            },
            next_gate="AI result state contract distinguishes auto_applied, suggested_only, blocked, review_required, unsupported",
        ),
        _row(
            "AI-G9",
            "Deployment Performance And Runtime",
            ledger="ai_engine",
            status=_status(inference_runtime_closed, inference_receipt.get("schema_version") == "ai-inference-runtime-receipt.v1"),
            blockers=[] if inference_runtime_closed else ["ai_inference_receipt_backend_latency_memory_fallback_missing"],
            evidence={
                "ml_gate_status": gate.get("status"),
                "inference_receipt_status": inference_receipt.get("status"),
                "fallback_reason": inference_receipt.get("fallback_reason"),
                "fallback_reason_required": bool(inference_receipt.get("fallback_required"))
                or str(inference_receipt.get("status") or "").strip()
                in {"fallback", "fallback_required", "solver_fallback_required"},
                "inference_runtime_closed": inference_runtime_closed,
            },
            next_gate="AI inference receipt records backend, checkpoint hash, latency, memory, OOD/confidence, and fallback reason when fallback is required",
        ),
        _row(
            "AI-G10",
            "User Workflow And AI Interface",
            ledger="ai_engine",
            status=_status(review_queue_ready, workstation.get("status") == "ready" and review_queue.get("status") == "contract_ready"),
            blockers=[] if review_queue_ready else ["ai_review_queue_grounded_qa_not_closed"],
            evidence={
                "workstation_delivery_status": workstation.get("status"),
                "review_queue_contract_status": review_queue.get("status"),
                "review_queue_status": review_queue_runtime.get("status"),
                "queue_item_count": review_queue_runtime.get("queue_item_count"),
            },
            next_gate="review queue and grounded assistant answers link to evidence, confidence, caveat, and next review action",
        ),
    ]


def build_commercial_gap_ledger_status(productization_dir: Path | None = None) -> dict[str, Any]:
    productization = Path(productization_dir or PRODUCTIZATION)
    commercial_doc_ids = _doc_ids(COMMERCIAL_DOC, "G")
    ai_doc_ids = _doc_ids(AI_DOC, "AI-G")
    rows = [*_commercial_rows(productization), *_ai_rows(productization)]
    by_id = {row["id"]: row for row in rows}
    commercial_status_ids = [row["id"] for row in rows if row.get("ledger") == "commercial_solver"]
    ai_status_ids = [row["id"] for row in rows if row.get("ledger") == "ai_engine"]
    expected_commercial = commercial_doc_ids or commercial_status_ids
    expected_ai = ai_doc_ids or ai_status_ids
    missing_doc_ids = [
        *[gap_id for gap_id in commercial_status_ids if commercial_doc_ids and gap_id not in commercial_doc_ids],
        *[gap_id for gap_id in ai_status_ids if ai_doc_ids and gap_id not in ai_doc_ids],
    ]
    missing_status_ids = [
        *[gap_id for gap_id in expected_commercial if gap_id not in by_id],
        *[gap_id for gap_id in expected_ai if gap_id not in by_id],
    ]
    closed_count = sum(1 for row in rows if row["status"] == "closed")
    partial_count = sum(1 for row in rows if row["status"] == "partial")
    external_count = sum(1 for row in rows if row["status"] == "external_blocked")
    open_count = sum(1 for row in rows if row["status"] == "open")
    locally_closable_open_count = sum(
        1 for row in rows if row["locally_closable"] and row["status"] in {"open", "partial"}
    )
    blockers = [
        f"{row['id']}:{blocker}"
        for row in rows
        if row["status"] != "closed"
        for blocker in row.get("blockers", [])
    ]
    blockers.extend([f"doc_gap_id_missing:{gap_id}" for gap_id in missing_doc_ids])
    blockers.extend([f"status_gap_id_missing:{gap_id}" for gap_id in missing_status_ids])

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "closed" if not blockers else "open",
        "commercial_solver_gap_ready": all(
            gap_id in by_id and by_id[gap_id]["status"] == "closed" for gap_id in expected_commercial
        ),
        "ai_engine_gap_ready": all(
            gap_id in by_id and by_id[gap_id]["status"] == "closed" for gap_id in expected_ai
        ),
        "full_gap_ledger_ready": not blockers,
        "summary": {
            "total_count": len(rows),
            "closed_count": closed_count,
            "partial_count": partial_count,
            "open_count": open_count,
            "external_blocked_count": external_count,
            "locally_closable_open_count": locally_closable_open_count,
            "missing_doc_id_count": len(missing_doc_ids),
            "missing_status_id_count": len(missing_status_ids),
        },
        "doc_requirements": {
            "commercial_doc": str(COMMERCIAL_DOC),
            "commercial_doc_ids": commercial_doc_ids,
            "ai_doc": str(AI_DOC),
            "ai_doc_ids": ai_doc_ids,
            "missing_doc_ids": missing_doc_ids,
            "missing_status_ids": missing_status_ids,
        },
        "rows": rows,
        "blockers": blockers,
        "next_locally_closable_gaps": [
            row["id"]
            for row in rows
            if row["locally_closable"] and row["status"] in {"open", "partial"}
        ][:8],
    }
