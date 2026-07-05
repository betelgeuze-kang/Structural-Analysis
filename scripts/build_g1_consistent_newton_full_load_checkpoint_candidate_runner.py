#!/usr/bin/env python3
"""Build the G1 consistent-Newton full-load checkpoint runner contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "g1-consistent-newton-full-load-checkpoint-candidate-runner.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_G1_LANE = PRODUCTIZATION / "g1_full_load_hip_newton_lane_report.json"
DEFAULT_CAUSE_NARROWING = PRODUCTIZATION / "g1_f2g_f2h_cause_narrowing_status.json"
DEFAULT_HIP_PROBE = PRODUCTIZATION / "mgt_residual_jacobian_consistency_hip_required_probe.json"
DEFAULT_GLOBAL_CONNECTIVITY = PRODUCTIZATION / "g1_global_connectivity_load_path_audit.json"
DEFAULT_ASSEMBLY_CONTRACT_SEED = PRODUCTIZATION / "g1_assembly_contract_seed_report.json"
DEFAULT_CPU_LIVE_ASSEMBLY_CONTRACT_PROBE = (
    PRODUCTIZATION / "g1_full_load_cpu_live_assembly_contract_probe.json"
)
DEFAULT_TRUE_NEWTON_LOAD_SWEEP = PRODUCTIZATION / "g1_true_newton_load_sweep_status.json"
DEFAULT_TRUE_NEWTON_FULL_LOAD_CHECKPOINT_CANDIDATE = (
    PRODUCTIZATION / "g1_true_newton_full_load_checkpoint_candidate_status.json"
)
DEFAULT_TRUE_NEWTON_FROM_ACTIVE_SET_LS_TRUST_CANDIDATE = (
    PRODUCTIZATION / "g1_true_newton_from_active_set_ls_trust_mu_0p03_candidate.json"
)
DEFAULT_TRUE_NEWTON_FROM_ACTIVE_SET_SERVICE_TANGENT_LS_TRUST_CANDIDATE = (
    PRODUCTIZATION
    / "g1_true_newton_from_active_set_ls_trust_service_tangent_mu_0p03_candidate.json"
)
DEFAULT_ADAPTIVE_ALL_COMPONENTS_FRONTIER = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_60step_diagnostic.json"
)
DEFAULT_SHELL_HOTSPOT_TANGENT_FD_JVP_PROBE = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_shell_jvp_probe.json"
)
DEFAULT_SHELL_HOTSPOT_DIAGONAL_SWEEP_PROBE = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_shell_diag_sweep_probe.json"
)
DEFAULT_GLOBAL_TANGENT_SCALED_SWEEP_PROBE = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_global_tangent_scaled_sweep_probe.json"
)
DEFAULT_RESIDUAL_NORM_GRADIENT_TINY_SWEEP_PROBE = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_residual_gradient_tiny_sweep_probe.json"
)
DEFAULT_ACTIVE_SET_LS_SWEEP_PROBE = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_sweep_probe.json"
)
DEFAULT_ACTIVE_SET_LS_TRUST_CANDIDATE = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_candidate.json"
)
DEFAULT_ACTIVE_SET_LS_TRUST_SCHEDULE_CANDIDATE = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_schedule_from_frontier_candidate.json"
)
DEFAULT_ACTIVE_SET_LS_TRUST_TANGENT_FD_JVP_PROBE = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_tangent_jvp_probe.json"
)
DEFAULT_ACTIVE_SET_MINIMAX_TRUST_CANDIDATE = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_active_set_minimax_trust_candidate.json"
)
DEFAULT_FRAME_TANGENT_FD_EPSILON_SWEEP_PROBE = (
    PRODUCTIZATION / "g1_frame_tangent_fd_epsilon_sweep_probe.json"
)
DEFAULT_TRUE_NEWTON_FROM_ACTIVE_SET_MU_SWEEP_PROBE = (
    PRODUCTIZATION / "g1_true_newton_from_active_set_mu_sweep_probe.json"
)
DEFAULT_ACTIVE_SET_LOAD_PARAMETER_PROBE = (
    PRODUCTIZATION / "g1_active_set_load_parameter_probe.json"
)
DEFAULT_ACTIVE_SET_LOAD_PARAMETER_TINY_TRUST_PROBE = (
    PRODUCTIZATION / "g1_active_set_load_parameter_tiny_trust_probe.json"
)
DEFAULT_ACTIVE_FRONTIER_RESIDUAL_OWNERSHIP_PROBE = (
    PRODUCTIZATION / "g1_active_frontier_residual_ownership_probe.json"
)
DEFAULT_ACTIVE_FRONTIER_SHELL_LOAD_NEIGHBORHOOD_PROBE = (
    PRODUCTIZATION / "g1_active_frontier_shell_load_neighborhood_probe.json"
)
DEFAULT_ACTIVE_FRONTIER_SHELL_POLICY_REPLAY_PROBE = (
    PRODUCTIZATION / "g1_active_frontier_shell_policy_replay_probe.json"
)
DEFAULT_ACTIVE_FRONTIER_SHELL_POLICY_LINEARIZED_ACTIVE_SET_PROBE = (
    PRODUCTIZATION / "g1_active_frontier_shell_policy_linearized_active_set_probe.json"
)
DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_LS_TRUST_CANDIDATE = (
    PRODUCTIZATION
    / "g1_active_frontier_structural_policy_active_set_ls_trust_two_step_candidate.json"
)
DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_LS_TRUST_ALPHA_SWEEP = (
    PRODUCTIZATION
    / "g1_active_frontier_structural_policy_active_set_ls_trust_two_step_alpha_sweep_candidate.json"
)
DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_DIRECT_MATERIAL_REPLAY_PROBE = (
    PRODUCTIZATION
    / "g1_active_frontier_structural_policy_active_set_ls_trust_third_step_direct_probe.json"
)
DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_CURRENT_COMPONENT_ROW_CORRECTION_PROBE = (
    PRODUCTIZATION
    / "g1_active_frontier_structural_policy_active_set_current_component_row_correction_probe.json"
)
DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_CURRENT_COMPONENT_ROW_CORRECTION_STEP2_PROBE = (
    PRODUCTIZATION
    / "g1_active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe.json"
)
DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_CURRENT_COMPONENT_ROW_CORRECTION_STEP3_PROBE = (
    PRODUCTIZATION
    / "g1_active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe.json"
)
DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_RESIDUAL_OWNERSHIP_PROBE = (
    PRODUCTIZATION / "g1_active_frontier_structural_policy_residual_ownership_probe.json"
)
DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_LINEARIZED_ACTIVE_SET_AFTER_TWO_STEP_PROBE = (
    PRODUCTIZATION
    / "g1_active_frontier_structural_policy_linearized_active_set_after_two_step_probe.json"
)
DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_SHELL_ROTATION_ROW_CANDIDATE = (
    PRODUCTIZATION / "g1_active_frontier_structural_policy_shell_rotation_row_second_probe.json"
)
DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_SHELL_ROTATION_ROW_NO_DESCENT_PROBE = (
    PRODUCTIZATION / "g1_active_frontier_structural_policy_shell_rotation_row_third_probe.json"
)
DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_SHELL_ROTATION_CANDIDATE_OWNERSHIP_PROBE = (
    PRODUCTIZATION
    / "g1_active_frontier_structural_policy_shell_rotation_second_candidate_residual_ownership_probe.json"
)
DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FRONTIER_PROBE = (
    PRODUCTIZATION
    / "g1_mgt_sparse_direct_scaled_lsmr_from_shell_rotation_frontier_probe.json"
)
DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FRONTIER_CANDIDATE = (
    PRODUCTIZATION
    / "g1_mgt_sparse_direct_scaled_lsmr_from_shell_rotation_frontier_candidate.npz"
)
DEFAULT_SPARSE_DIRECT_SCALED_LSMR_SECOND_PROBE = (
    PRODUCTIZATION
    / "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_second_probe.json"
)
DEFAULT_SPARSE_DIRECT_SCALED_LSMR_SECOND_CANDIDATE = (
    PRODUCTIZATION
    / "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_second_candidate.npz"
)
DEFAULT_SPARSE_DIRECT_SCALED_LSMR_THIRD_PROBE = (
    PRODUCTIZATION
    / "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_third_probe.json"
)
DEFAULT_SPARSE_DIRECT_SCALED_LSMR_THIRD_CANDIDATE = (
    PRODUCTIZATION
    / "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_third_candidate.npz"
)
DEFAULT_SPARSE_DIRECT_SCALED_LSMR_CHAIN_PROBE = (
    PRODUCTIZATION / "g1_mgt_sparse_direct_scaled_lsmr_chain_probe.json"
)
DEFAULT_SPARSE_DIRECT_SCALED_LSMR_LONG_CHAIN_PROBE = (
    PRODUCTIZATION / "g1_mgt_sparse_direct_scaled_lsmr_long_chain_probe.json"
)
DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FROM_INCOMPLETE_PREVIEW_PROBE = (
    PRODUCTIZATION / "g1_mgt_sparse_direct_scaled_lsmr_from_incomplete_preview_probe.json"
)
DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FROM_INCOMPLETE_PREVIEW_CANDIDATE = (
    PRODUCTIZATION / "g1_mgt_sparse_direct_scaled_lsmr_from_incomplete_preview_candidate.npz"
)
DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FROM_INCOMPLETE_PREVIEW_CHAIN_PROBE = (
    PRODUCTIZATION
    / "g1_mgt_sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe.json"
)
DEFAULT_SPARSE_DIRECT_SHIFTED_SPLU_FROM_INCOMPLETE_PREVIEW_CHAIN_PROBE = (
    PRODUCTIZATION
    / "g1_mgt_sparse_direct_shifted_splu_mu_1e_4_from_incomplete_preview_chain_probe.json"
)
DEFAULT_SPARSE_DIRECT_SHIFTED_SPLU_FROM_GATE_CANDIDATE_STEP2_PROBE = (
    PRODUCTIZATION
    / "g1_mgt_sparse_direct_shifted_splu_mu_1e_4_from_gate_candidate_step2_probe.json"
)
DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_ILU_PROBE = (
    PRODUCTIZATION / "g1_mgt_sparse_direct_adaptive_jvp_eps_gmres_ilu_probe.json"
)
DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_MATRIX_FREE_PROBE = (
    PRODUCTIZATION
    / "g1_mgt_sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe.json"
)
DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_SHIFTED_ILU_PROBE = (
    PRODUCTIZATION
    / "g1_mgt_sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_mu_1e_4_probe.json"
)
DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_SHIFTED_ILU_INCOMPLETE_PREVIEW_PROBE = (
    PRODUCTIZATION
    / "g1_mgt_sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_mu_1e_4_incomplete_preview_probe.json"
)
DEFAULT_HIP_REQUIRED_FULL_LOAD_RESIDUAL_JVP_FRONTIER_PROBE = (
    PRODUCTIZATION
    / "mgt_residual_jacobian_step14_material_active_set_ls_rows32_child_direct_saved_probe.json"
)
DEFAULT_HIP_REQUIRED_FULL_LOAD_RESIDUAL_JVP_FRONTIER_CANDIDATE = (
    PRODUCTIZATION
    / "mgt_residual_jacobian_step14_material_active_set_ls_rows32_child_direct_candidate.npz"
)
DEFAULT_HIP_REQUIRED_CONSISTENCY_DIRECT_FRONTIER_CANDIDATE = (
    PRODUCTIZATION
    / "mgt_residual_jacobian_step15_material_active_set_ls_rows32_child_direct_candidate.npz"
)
DEFAULT_HIP_REQUIRED_CONSISTENCY_NO_DESCENT_PROBE = (
    PRODUCTIZATION
    / "mgt_residual_jacobian_step16_material_active_set_ls_rows32_child_direct_no_descent_probe.json"
)
DEFAULT_HIP_REQUIRED_SCALED_GLOBAL_KRYLOV_NO_DESCENT_PROBE = (
    PRODUCTIZATION
    / "mgt_residual_jacobian_step16_scaled_global_krylov_direct_probe.json"
)
DEFAULT_CURRENT_FRONTIER_OPERATOR_MISMATCH_AUDIT = (
    PRODUCTIZATION / "g1_current_frontier_operator_mismatch_audit.json"
)
DEFAULT_PHASE2_MATERIAL_NEWTON_BREADTH_SUMMARY = (
    PRODUCTIZATION / "phase2_material_newton_breadth_summary.json"
)
DEFAULT_PHASE2_MATERIAL_NEWTON_BREADTH_STATE_UPDATED_SEEDS = (
    PRODUCTIZATION / "phase2_material_newton_breadth_state_updated_seeds.json"
)
DEFAULT_OUT = PRODUCTIZATION / "g1_consistent_newton_full_load_checkpoint_candidate_runner.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_SOLVER_HIP_E2E = Path(
    "implementation/phase1/release_evidence/gpu/solver_hip_e2e_contract_report.json"
)

RUNNER_ID = "build_consistent_newton_full_load_checkpoint_candidate_runner"
PREFERRED_GENERATOR = "consistent_residual_jacobian_newton_rocm_full_load_candidate"
PRIMARY_NEXT_LANE = "consistent_residual_jacobian_newton_rocm_worker"
LIVE_ASSEMBLY_CONTRACT_SCHEMA = "g1-assembly-result.v1"
LIVE_ASSEMBLY_RESIDUAL_SOURCE = "physical_direct_residual"
LIVE_ASSEMBLY_TANGENT_DEFINITION = "dR_du_consistent"
LIVE_ASSEMBLY_REQUIRED_FIELDS = (
    "residual_free",
    "tangent_free",
    "internal_forces",
    "external_forces",
    "material_state_next",
    "metrics",
)
DISALLOWED_RETRY_ACTION_IDS = [
    "repeat_largest_rows_target128_support8_row_only_retuning",
]
CHECKPOINT_SCHEMA = "mgt-direct-residual-newton-state.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _strings(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item)]


def _find_runner_action(g1_lane: dict[str, Any]) -> dict[str, Any]:
    for row in _as_list(g1_lane.get("lane_next_actions")):
        if isinstance(row, dict) and row.get("id") == RUNNER_ID:
            return row
    return {}


def _cause_primary_next_lane(cause_narrowing: dict[str, Any], action: dict[str, Any]) -> str:
    decision = _as_dict(cause_narrowing.get("decision_record"))
    signals = _as_dict(cause_narrowing.get("evidence_signals"))
    return str(
        action.get("cause_narrowing_primary_next_lane")
        or decision.get("primary_next_lane")
        or signals.get("global_connectivity_primary_next_lane")
        or ""
    )


def _row_only_loop_stopped(cause_narrowing: dict[str, Any], action: dict[str, Any]) -> bool:
    decision = _as_dict(cause_narrowing.get("decision_record"))
    signals = _as_dict(cause_narrowing.get("evidence_signals"))
    return bool(
        action.get("cause_narrowing_row_only_correction_loop_stopped") is True
        or decision.get("stop_row_only_support_or_elastic_link_correction_loop") is True
        or signals.get("row_only_correction_loop_stopped_by_global_connectivity") is True
    )


def _support_or_link_gap_disfavored(
    cause_narrowing: dict[str, Any],
    action: dict[str, Any],
) -> bool:
    signals = _as_dict(cause_narrowing.get("evidence_signals"))
    return bool(
        action.get("cause_narrowing_support_or_link_gap_disfavored") is True
        or signals.get("support_or_link_row_gap_disfavored") is True
    )


def _missing_artifact_blockers(
    *,
    g1_lane: dict[str, Any],
    cause_narrowing: dict[str, Any],
    hip_probe: dict[str, Any],
    assembly_contract_seed: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not g1_lane:
        blockers.append("g1_full_load_hip_newton_lane_report_missing")
    if not cause_narrowing:
        blockers.append("g1_f2g_f2h_cause_narrowing_status_missing")
    if not hip_probe:
        blockers.append("mgt_residual_jacobian_consistency_hip_required_probe_missing")
    if not assembly_contract_seed:
        blockers.append("g1_assembly_contract_seed_report_missing")
    return blockers


def _assembly_contract_seed_blockers(assembly_contract_seed: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not assembly_contract_seed:
        return blockers
    if assembly_contract_seed.get("contract_pass") is not True:
        blockers.append("g1_assembly_contract_seed_contract_not_passed")
    if assembly_contract_seed.get("promotes_g1_closure") is not False:
        blockers.append("g1_assembly_contract_seed_promotes_g1_closure")
    if assembly_contract_seed.get("residual_formula") != "F_internal_minus_F_external":
        blockers.append("g1_assembly_contract_seed_residual_formula_mismatch")
    if assembly_contract_seed.get("fixed_point_residual_promoted_to_physical") is not False:
        blockers.append("g1_assembly_contract_seed_fixed_point_residual_promoted")
    if assembly_contract_seed.get("regularized_fixed_point_substitute") is not False:
        blockers.append("g1_assembly_contract_seed_regularized_fixed_point_substitute")
    if assembly_contract_seed.get("cpu_seed_consistent_newton_gate_passed") is not True:
        blockers.append("g1_assembly_contract_seed_cpu_newton_parity_not_passed")
    if assembly_contract_seed.get("consistent_residual_jacobian_newton_gate_passed") is not False:
        blockers.append("g1_assembly_contract_seed_claims_full_consistent_newton_gate")
    return blockers


def _live_assembly_contract_from_hip_probe(hip_probe: dict[str, Any]) -> dict[str, Any]:
    live_contract = _as_dict(hip_probe.get("live_g1_assembly_contract"))
    if live_contract:
        return live_contract
    return _as_dict(hip_probe.get("assembly_contract"))


def _live_assembly_contract_blockers(hip_probe: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not hip_probe:
        return blockers
    live_contract = _live_assembly_contract_from_hip_probe(hip_probe)
    if not live_contract:
        return ["live_g1_assembly_contract_receipt_missing"]
    if live_contract.get("uses_assembly_result_contract") is not True:
        blockers.append("live_g1_assembly_contract_not_used")
    schema = str(
        live_contract.get("assembly_result_schema")
        or live_contract.get("schema_version")
        or ""
    )
    if schema != LIVE_ASSEMBLY_CONTRACT_SCHEMA:
        blockers.append("live_g1_assembly_contract_schema_mismatch")
    if live_contract.get("residual_formula") != "F_internal_minus_F_external":
        blockers.append("live_g1_assembly_contract_residual_formula_mismatch")
    if (
        str(live_contract.get("residual_source") or "")
        != LIVE_ASSEMBLY_RESIDUAL_SOURCE
    ):
        blockers.append("live_g1_assembly_contract_residual_source_mismatch")
    if (
        str(live_contract.get("tangent_definition") or "")
        != LIVE_ASSEMBLY_TANGENT_DEFINITION
    ):
        blockers.append("live_g1_assembly_contract_tangent_definition_mismatch")
    if live_contract.get("required_fields_present") is not True:
        required_fields = set(_strings(live_contract.get("required_fields")))
        missing_fields = [
            field
            for field in LIVE_ASSEMBLY_REQUIRED_FIELDS
            if field not in required_fields
        ]
        if missing_fields:
            blockers.append("live_g1_assembly_contract_required_fields_missing")
    if live_contract.get("fixed_point_residual_promoted_to_physical") is not False:
        blockers.append("live_g1_assembly_contract_fixed_point_residual_promoted")
    if live_contract.get("regularized_fixed_point_substitute") is not False:
        blockers.append("live_g1_assembly_contract_regularized_fixed_point_substitute")
    return blockers


def _live_assembly_contract_summary(hip_probe: dict[str, Any]) -> dict[str, Any]:
    live_contract = _live_assembly_contract_from_hip_probe(hip_probe)
    blockers = _live_assembly_contract_blockers(hip_probe)
    return {
        "present": bool(live_contract),
        "contract_pass": bool(live_contract) and not blockers,
        "blockers": blockers,
        "uses_assembly_result_contract": live_contract.get(
            "uses_assembly_result_contract"
        )
        is True,
        "assembly_result_schema": str(
            live_contract.get("assembly_result_schema")
            or live_contract.get("schema_version")
            or ""
        ),
        "residual_formula": str(live_contract.get("residual_formula") or ""),
        "residual_source": str(live_contract.get("residual_source") or ""),
        "tangent_definition": str(live_contract.get("tangent_definition") or ""),
        "required_fields_present": live_contract.get("required_fields_present")
        is True,
        "required_fields": _strings(live_contract.get("required_fields")),
        "fixed_point_residual_promoted_to_physical": live_contract.get(
            "fixed_point_residual_promoted_to_physical"
        )
        is True,
        "regularized_fixed_point_substitute": live_contract.get(
            "regularized_fixed_point_substitute"
        )
        is True,
        "claim_boundary": (
            "The seed AssemblyResult contract is not enough for G1 closure. "
            "The HIP/full-load residual-Jacobian proof must also report that "
            "the live G1 runner used the same residual_free/tangent_free/"
            "internal_forces/external_forces/material_state_next contract."
        ),
    }


def _cpu_live_assembly_contract_probe_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    live_contract = _as_dict(payload.get("live_g1_assembly_contract"))
    checkpoint = _as_dict(payload.get("checkpoint"))
    final_residual = _as_dict(payload.get("final_direct_residual"))
    gate = _as_dict(payload.get("gate_assessment"))
    blockers = _strings(live_contract.get("blockers"))
    contract_pass = bool(
        live_contract.get("contract_pass") is True
        and live_contract.get("uses_assembly_result_contract") is True
        and str(live_contract.get("assembly_result_schema") or "")
        == LIVE_ASSEMBLY_CONTRACT_SCHEMA
        and str(live_contract.get("residual_formula") or "")
        == "F_internal_minus_F_external"
        and str(live_contract.get("residual_source") or "")
        == LIVE_ASSEMBLY_RESIDUAL_SOURCE
        and str(live_contract.get("tangent_definition") or "")
        == LIVE_ASSEMBLY_TANGENT_DEFINITION
        and live_contract.get("required_fields_present") is True
        and live_contract.get("fixed_point_residual_promoted_to_physical") is False
        and live_contract.get("regularized_fixed_point_substitute") is False
        and not blockers
    )
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "source_commit_sha": str(payload.get("source_commit_sha") or ""),
        "contract_pass": contract_pass,
        "promotes_g1_closure": False,
        "cpu_diagnostic_assembler_used": True,
        "load_scale": _as_float(checkpoint.get("load_scale")),
        "direct_residual_newton_ready": payload.get("direct_residual_newton_ready")
        is True,
        "direct_residual_gate_passed": gate.get("direct_residual_gate_passed")
        is True
        or final_residual.get("residual_gate_passed") is True,
        "relative_increment_gate_passed": gate.get("relative_increment_gate_passed")
        is True,
        "material_newton_breadth_passed": gate.get("material_newton_breadth_passed")
        is True,
        "fallback_zero_passed": gate.get("fallback_zero_passed") is True,
        "residual_inf_n": _as_float(
            final_residual.get("direct_residual_inf_n")
            if final_residual
            else live_contract.get("residual_inf_norm")
        ),
        "assembly_result_schema": str(
            live_contract.get("assembly_result_schema") or ""
        ),
        "residual_formula": str(live_contract.get("residual_formula") or ""),
        "residual_source": str(live_contract.get("residual_source") or ""),
        "tangent_definition": str(live_contract.get("tangent_definition") or ""),
        "free_dof_count": _as_int(live_contract.get("free_dof_count")),
        "blockers": blockers,
        "claim_boundary": (
            "CPU diagnostic full-load live AssemblyResult contract evidence only. "
            "This does not satisfy the HIP-required live G1 assembly contract, "
            "production ROCm/HIP residual/JVP residency, residual convergence, "
            "or material Newton breadth closure gates."
        ),
    }


def _routing_blockers(
    *,
    action: dict[str, Any],
    cause_narrowing: dict[str, Any],
    checkpoint_gate: dict[str, Any] | None = None,
) -> list[str]:
    blockers: list[str] = []
    checkpoint_gate = checkpoint_gate if isinstance(checkpoint_gate, dict) else {}
    checkpoint_ready = bool(checkpoint_gate.get("passed") is True)
    if not action:
        if not checkpoint_ready:
            blockers.append("consistent_newton_runner_next_action_missing")
            return blockers
        action = {}
    if action.get("preferred_candidate_generator") != PREFERRED_GENERATOR:
        if not checkpoint_ready:
            blockers.append("consistent_newton_preferred_candidate_generator_missing")
    if _cause_primary_next_lane(cause_narrowing, action) != PRIMARY_NEXT_LANE:
        blockers.append("cause_narrowing_primary_next_lane_not_consistent_newton_rocm")
    if not _row_only_loop_stopped(cause_narrowing, action):
        blockers.append("row_only_correction_loop_not_stopped_by_cause_narrowing")
    if not _support_or_link_gap_disfavored(cause_narrowing, action):
        blockers.append("support_or_link_row_gap_not_disfavored")
    suppressed = set(_strings(action.get("suppressed_retry_action_ids")))
    for retry_id in DISALLOWED_RETRY_ACTION_IDS:
        if retry_id not in suppressed and not checkpoint_ready:
            blockers.append(f"disallowed_retry_not_suppressed:{retry_id}")
    return blockers


def _worker_path_blocker_category(blocker: str) -> str:
    if blocker.startswith("runtime::") or blocker == "rocm_hip_runtime_unavailable":
        return "runtime_device_interface"
    if blocker == "direct_probe_not_executed_preflight_only":
        return "hip_required_direct_probe"
    if blocker == "production_hip_residual_jacobian_path_not_proven":
        return "production_hip_residual_jacobian_path"
    if blocker.startswith("global_krylov_"):
        return "matrix_free_global_krylov"
    if blocker.startswith("current_tangent_residual_row_"):
        return "current_tangent_residual_row_replay"
    return "other"


def _worker_path_repair_plan(
    *,
    worker: dict[str, Any],
    hip_probe_path: Path,
) -> dict[str, Any]:
    blockers = _strings(worker.get("residual_jvp_worker_path_blockers"))
    if not blockers and worker.get("residual_jvp_worker_path_ready") is not True:
        blockers = _strings(worker.get("blockers"))
    categories: dict[str, dict[str, Any]] = {}
    for blocker in blockers:
        category = _worker_path_blocker_category(blocker)
        row = categories.setdefault(
            category,
            {
                "blocker_count": 0,
                "blockers": [],
                "required_receipts": [],
                "acceptance": [],
            },
        )
        row["blockers"].append(blocker)
        row["blocker_count"] += 1
    category_contracts = {
        "runtime_device_interface": {
            "required_receipts": [DEFAULT_SOLVER_HIP_E2E.as_posix()],
            "acceptance": [
                "ROCm/HIP runtime device nodes are present",
                "solver_hip_e2e_contract_report.json contract_pass == true",
            ],
        },
        "hip_required_direct_probe": {
            "required_receipts": [hip_probe_path.as_posix()],
            "acceptance": [
                "HIP-required direct probe executed, not preflight-only",
                "cpu_diagnostic_assembler_used == false",
            ],
        },
        "production_hip_residual_jacobian_path": {
            "required_receipts": [hip_probe_path.as_posix()],
            "acceptance": [
                "production_hip_residual_jacobian_path == true",
                "no CPU fallback path is counted as production HIP",
            ],
        },
        "matrix_free_global_krylov": {
            "required_receipts": [hip_probe_path.as_posix()],
            "acceptance": [
                "matrix_free_global_krylov.proof.hip_krylov_solver_used == true",
                "matrix_free_global_krylov.proof.jvp_rows_retained == true",
                "accepted-state tangent refresh uses HIP, not CPU",
            ],
        },
        "current_tangent_residual_row_replay": {
            "required_receipts": [hip_probe_path.as_posix()],
            "acceptance": [
                "current tangent residual row correction attempted with HIP batch replay",
                "accepted-state tangent refresh CPU fallback remains false",
            ],
        },
        "other": {
            "required_receipts": [hip_probe_path.as_posix()],
            "acceptance": ["unclassified worker-path blocker is resolved or reclassified"],
        },
    }
    for category, row in categories.items():
        contract = category_contracts[category]
        row["required_receipts"] = contract["required_receipts"]
        row["acceptance"] = contract["acceptance"]
    ordered_categories = [
        category
        for category in (
            "runtime_device_interface",
            "hip_required_direct_probe",
            "production_hip_residual_jacobian_path",
            "matrix_free_global_krylov",
            "current_tangent_residual_row_replay",
            "other",
        )
        if category in categories
    ]
    return {
        "schema_version": "g1-production-rocm-hip-worker-path-repair-plan.v1",
        "status": "blocked" if blockers else "ready",
        "next_action_id": (
            "repair_production_rocm_hip_residual_jvp_worker_path"
            if blockers
            else "rerun_g1_full_load_hip_newton_lane"
        ),
        "blocker_count": len(blockers),
        "blockers": blockers,
        "category_count": len(categories),
        "category_order": ordered_categories,
        "category_counts": {
            category: int(categories[category]["blocker_count"])
            for category in ordered_categories
        },
        "categories": {category: categories[category] for category in ordered_categories},
        "runtime_blockers": _strings(_as_dict(worker.get("runtime")).get("runtime_blockers")),
        "required_receipts": [
            hip_probe_path.as_posix(),
            DEFAULT_SOLVER_HIP_E2E.as_posix(),
        ],
        "claim_boundary": (
            "This repair plan classifies the missing production ROCm/HIP residual/JVP "
            "worker path. It does not execute HIP, prove device residency, create a "
            "full-load checkpoint, or promote G1 closure."
        ),
    }


def _worker_path_operator_sequence(
    *,
    worker_path_repair_plan: dict[str, Any],
    hip_probe_path: Path,
    g1_lane_path: Path,
) -> list[dict[str, Any]]:
    category_order = [
        str(item) for item in _as_list(worker_path_repair_plan.get("category_order"))
    ]
    blocked_categories = set(category_order)

    def step_status(*categories: str) -> str:
        return "required" if blocked_categories.intersection(categories) else "ready"

    return [
        {
            "step_id": "verify_rocm_runtime_device_interface",
            "owner": "runtime_rocm_owner",
            "status": step_status("runtime_device_interface"),
            "clears_categories": ["runtime_device_interface"],
            "command": (
                "python3 implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py "
                "--require-hip-residual-engine --hip-runtime-preflight-only "
                f"--output-json {hip_probe_path.as_posix()}"
            ),
            "required_receipts": [
                hip_probe_path.as_posix(),
                DEFAULT_SOLVER_HIP_E2E.as_posix(),
            ],
            "acceptance": [
                "/dev/kfd and /dev/dri are available to the runner",
                "ROCm/HIP runtime preflight reports hip_available == true",
                "no CPU diagnostic assembler is used as a substitute",
            ],
        },
        {
            "step_id": "run_hip_required_direct_probe",
            "owner": "runtime_rocm_owner",
            "status": step_status(
                "hip_required_direct_probe",
                "production_hip_residual_jacobian_path",
                "matrix_free_global_krylov",
                "current_tangent_residual_row_replay",
            ),
            "clears_categories": [
                "hip_required_direct_probe",
                "production_hip_residual_jacobian_path",
                "matrix_free_global_krylov",
                "current_tangent_residual_row_replay",
            ],
            "command": (
                "python3 implementation/phase1/run_mgt_residual_jacobian_consistency_probe.py "
                "--require-hip-residual-engine "
                f"--output-json {hip_probe_path.as_posix()}"
            ),
            "required_receipts": [hip_probe_path.as_posix()],
            "acceptance": [
                "child HIP direct probe is executed, not preflight-only",
                "production_hip_residual_jacobian_path == true",
                "matrix-free global Krylov retains HIP JVP rows",
                "current tangent residual-row correction uses HIP batch replay",
            ],
        },
        {
            "step_id": "refresh_runner_contract_after_hip_probe",
            "owner": "g1_solver_owner",
            "status": "required" if worker_path_repair_plan.get("blocker_count") else "ready",
            "clears_categories": [],
            "command": (
                "python3 scripts/build_g1_consistent_newton_full_load_checkpoint_candidate_runner.py "
                "--fail-blocked"
            ),
            "required_receipts": [
                hip_probe_path.as_posix(),
                DEFAULT_OUT.as_posix(),
            ],
            "acceptance": [
                "worker_path_repair_plan.blocker_count == 0",
                "hip_worker_contract.residual_jvp_worker_path_ready == true",
            ],
        },
        {
            "step_id": "rerun_g1_full_load_lane_with_full_load_checkpoint",
            "owner": "g1_solver_owner",
            "status": "required",
            "clears_categories": [],
            "command": (
                "python3 scripts/run_g1_full_load_hip_newton_lane.py "
                "--checkpoint-npz <full-load-checkpoint.npz> --fail-blocked"
            ),
            "required_receipts": [
                "<full-load-checkpoint.npz>",
                g1_lane_path.as_posix(),
            ],
            "acceptance": [
                "checkpoint load_scale >= 1.0",
                "checkpoint schema is mgt-direct-residual-newton-state.v1",
                "g1_full_load_hip_newton_lane_report contract passes",
            ],
        },
    ]


def _closure_blockers(
    *,
    g1_lane: dict[str, Any],
    hip_probe: dict[str, Any],
    worker: dict[str, Any],
) -> list[str]:
    checkpoint_gate = _as_dict(g1_lane.get("checkpoint_resolution_gate"))
    closure_blockers = [
        str(item) for item in _as_list(g1_lane.get("blockers")) if str(item)
    ]
    closure_blockers.extend(str(item) for item in _as_list(hip_probe.get("blockers")) if str(item))
    if checkpoint_gate.get("passed") is not True:
        closure_blockers.append("full_load_checkpoint_1p0_not_available")
    if hip_probe.get("consistent_residual_jacobian_newton_gate_passed") is not True:
        closure_blockers.append("consistent_residual_jacobian_newton_gate_not_passed")
    if worker.get("g1_closure_gate_ready") is not True:
        closure_blockers.append("production_rocm_hip_worker_g1_closure_gate_not_ready")
    seen: set[str] = set()
    unique: list[str] = []
    for blocker in closure_blockers:
        if blocker and blocker not in seen:
            seen.add(blocker)
            unique.append(blocker)
    return unique


def _true_newton_load_sweep_summary(
    *,
    payload: dict[str, Any],
    path: Path,
    required_load_scale: float,
) -> dict[str, Any]:
    rows = [
        row for row in _as_list(payload.get("rows")) if isinstance(row, dict)
    ]
    full_load_row: dict[str, Any] = {}
    for row in rows:
        load_scale = _as_float(row.get("load_scale"), -1.0)
        if abs(load_scale - required_load_scale) <= 1.0e-12:
            full_load_row = row
            break
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "contract_pass": payload.get("contract_pass") is True,
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "max_attempted_load_scale": _as_float(
            payload.get("max_attempted_load_scale")
        ),
        "full_load_attempted": bool(payload.get("full_load_attempted") is True),
        "full_load_true_newton_residual_descent_observed": bool(
            payload.get("full_load_true_newton_residual_descent_observed") is True
        ),
        "full_load_true_newton_residual_gate_passed": bool(
            payload.get("full_load_true_newton_residual_gate_passed") is True
        ),
        "full_load_true_newton_final_residual_n": _as_float(
            payload.get("full_load_true_newton_final_residual_n")
        ),
        "full_load_true_newton_total_reduction_ratio": _as_float(
            payload.get("full_load_true_newton_total_reduction_ratio")
        ),
        "row_count": len(rows),
        "full_load_row": full_load_row,
        "blockers": _strings(payload.get("blockers")),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _true_newton_full_load_checkpoint_candidate_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    checkpoint = _as_dict(payload.get("checkpoint_candidate"))
    candidate = _as_dict(payload.get("true_newton_candidate"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "contract_pass": payload.get("contract_pass") is True,
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "checkpoint_written": payload.get("checkpoint_written") is True,
        "checkpoint_path": str(checkpoint.get("path") or ""),
        "checkpoint_schema": str(checkpoint.get("schema") or ""),
        "checkpoint_load_scale": _as_float(checkpoint.get("load_scale")),
        "checkpoint_direct_residual_inf_n": _as_float(
            checkpoint.get("direct_residual_inf_n")
        ),
        "true_newton_steps": _as_int(candidate.get("steps")),
        "true_newton_final_residual_n": _as_float(
            candidate.get("final_residual_n")
        ),
        "true_newton_residual_gate_passed": bool(
            candidate.get("residual_gate_passed") is True
        ),
        "blockers": _strings(payload.get("blockers")),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _true_newton_from_active_set_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    candidate = _as_dict(payload.get("true_newton_candidate"))
    modified = _as_dict(payload.get("modified_newton_baseline"))
    summary = _as_dict(payload.get("summary"))
    output_checkpoint = _as_dict(payload.get("output_final_checkpoint"))
    contracts = _as_dict(
        _as_dict(summary.get("directional_residual_jvp_contract")).get(
            "direction_solve_contracts"
        )
    )
    dominant_gap = _as_dict(contracts.get("dominant_jvp_gap_row_set"))
    rows = [
        row
        for row in _as_list(
            dominant_gap.get("dominant_jvp_minus_unregularized_tangent_action_rows")
        )
        if isinstance(row, dict)
    ]
    top_row = rows[0] if rows else {}
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "reason_code": str(payload.get("reason_code") or ""),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "initial_checkpoint_npz": str(payload.get("initial_checkpoint_npz") or ""),
        "regularization_mu": _as_float(_as_dict(payload.get("regularization")).get("mu")),
        "frame_tangent_source": str(payload.get("frame_tangent_source") or ""),
        "true_steps": _as_int(candidate.get("steps")),
        "true_final_residual_n": _as_float(candidate.get("final_residual_n")),
        "true_residual_gate_passed": candidate.get("residual_gate_passed") is True,
        "true_stop_reason": str(candidate.get("stop_reason") or ""),
        "modified_final_residual_n": _as_float(modified.get("final_residual_n")),
        "true_newton_faster_than_modified": payload.get(
            "true_newton_faster_than_modified"
        )
        is True,
        "line_search_no_descent": str(candidate.get("stop_reason") or "")
        == "line_search_no_descent",
        "max_regularized_linear_solve_relative_inf": _as_float(
            contracts.get("max_regularized_linear_solve_relative_inf")
        ),
        "max_unregularized_tangent_plus_residual_relative_inf": _as_float(
            contracts.get("max_unregularized_tangent_plus_residual_relative_inf")
        ),
        "max_regularization_action_vs_residual_inf": _as_float(
            contracts.get("max_regularization_action_vs_residual_inf")
        ),
        "max_jvp_minus_unregularized_tangent_action_relative_inf": _as_float(
            contracts.get("max_jvp_minus_unregularized_tangent_action_relative_inf")
        ),
        "dominant_jvp_gap_component": str(
            _as_dict(
                _as_list(
                    _as_dict(dominant_gap.get("dominant_jvp_gap_component_breakdown"))
                    .get("rows")
                )[0]
                if _as_list(
                    _as_dict(dominant_gap.get("dominant_jvp_gap_component_breakdown"))
                    .get("rows")
                )
                else {}
            ).get("dominant_component_tangent_gap")
            or ""
        ),
        "dominant_jvp_gap_top_global_dof": _as_int(top_row.get("global_dof")),
        "dominant_jvp_gap_top_node_id": _as_int(top_row.get("node_id")),
        "dominant_jvp_gap_top_dof_label": str(top_row.get("dof_label") or ""),
        "checkpoint_written": output_checkpoint.get("written") is True,
        "checkpoint_path": str(output_checkpoint.get("path") or ""),
        "checkpoint_direct_residual_inf_n": _as_float(
            output_checkpoint.get("direct_residual_inf_n")
        ),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _true_newton_frame_tangent_source_comparison(
    *,
    force_based: dict[str, Any],
    service_tangent: dict[str, Any],
) -> dict[str, Any]:
    force_gap = _as_float(
        force_based.get("max_jvp_minus_unregularized_tangent_action_relative_inf")
    )
    service_gap = _as_float(
        service_tangent.get(
            "max_jvp_minus_unregularized_tangent_action_relative_inf"
        )
    )
    candidates = [
        row
        for row in (force_based, service_tangent)
        if row.get("present") is True
    ]
    best = min(
        candidates,
        key=lambda row: _as_float(
            row.get("max_jvp_minus_unregularized_tangent_action_relative_inf")
        ),
        default={},
    )
    return {
        "present": bool(force_based.get("present") and service_tangent.get("present")),
        "source_count": len(candidates),
        "force_based_source": str(force_based.get("frame_tangent_source") or ""),
        "service_tangent_source": str(service_tangent.get("frame_tangent_source") or ""),
        "force_based_stop_reason": str(force_based.get("true_stop_reason") or ""),
        "service_tangent_stop_reason": str(service_tangent.get("true_stop_reason") or ""),
        "force_based_final_residual_n": force_based.get("true_final_residual_n"),
        "service_tangent_final_residual_n": service_tangent.get("true_final_residual_n"),
        "force_based_max_jvp_gap_relative_inf": force_gap,
        "service_tangent_max_jvp_gap_relative_inf": service_gap,
        "service_minus_force_max_jvp_gap_relative_inf": service_gap - force_gap,
        "force_based_dominant_gap_component": str(
            force_based.get("dominant_jvp_gap_component") or ""
        ),
        "service_tangent_dominant_gap_component": str(
            service_tangent.get("dominant_jvp_gap_component") or ""
        ),
        "both_line_search_no_descent": (
            force_based.get("true_stop_reason") == "line_search_no_descent"
            and service_tangent.get("true_stop_reason") == "line_search_no_descent"
        ),
        "both_dominant_gap_component_frame": (
            force_based.get("dominant_jvp_gap_component") == "frame"
            and service_tangent.get("dominant_jvp_gap_component") == "frame"
        ),
        "lowest_gap_source": str(best.get("frame_tangent_source") or ""),
        "claim_boundary": (
            "Frame tangent source comparison evidence only. This identifies that "
            "both active-set true-Newton candidates retain a frame-dominant JVP "
            "gap and does not promote G1 closure."
        ),
    }


def _frame_tangent_fd_epsilon_sweep_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    summary = _as_dict(payload.get("summary"))
    default_row = _as_dict(summary.get("default_eps_row"))
    best_row = _as_dict(summary.get("best_eps_row"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "frame_tangent_source": str(payload.get("frame_tangent_source") or ""),
        "residual_inf_n": _as_float(summary.get("residual_inf_n")),
        "direction_inf_m": _as_float(summary.get("direction_inf_m")),
        "frame_force_inf_n": _as_float(summary.get("frame_force_inf_n")),
        "frame_tangent_action_inf_n": _as_float(
            summary.get("frame_tangent_action_inf_n")
        ),
        "default_jvp_eps": _as_float(summary.get("default_jvp_eps")),
        "default_eps_gap_inf_n": _as_float(
            default_row.get("max_frame_jvp_minus_tangent_action_inf_n")
        ),
        "default_eps_gap_relative_inf": _as_float(
            default_row.get("max_frame_jvp_minus_tangent_action_relative_inf")
        ),
        "best_eps": _as_float(best_row.get("eps")),
        "best_eps_gap_inf_n": _as_float(
            best_row.get("max_frame_jvp_minus_tangent_action_inf_n")
        ),
        "best_eps_gap_relative_inf": _as_float(
            best_row.get("max_frame_jvp_minus_tangent_action_relative_inf")
        ),
        "fd_step_sensitivity_observed": (
            summary.get("fd_step_sensitivity_observed") is True
        ),
        "default_eps_artifact_likely": (
            summary.get("default_eps_artifact_likely") is True
        ),
        "default_to_best_gap_ratio": _as_float(
            summary.get("default_to_best_gap_ratio")
        ),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _true_newton_from_active_set_mu_sweep_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    summary = _as_dict(payload.get("summary"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "frame_tangent_source": str(payload.get("frame_tangent_source") or ""),
        "regularization_mode": str(payload.get("regularization_mode") or ""),
        "initial_residual_inf_n": _as_float(
            summary.get("initial_residual_inf_n")
        ),
        "evaluated_mu_count": _as_int(summary.get("evaluated_mu_count")),
        "factorable_mu_count": _as_int(summary.get("factorable_mu_count")),
        "descent_observed": summary.get("descent_observed") is True,
        "best_mu": _as_float(summary.get("best_mu")),
        "best_effective_shift": _as_float(summary.get("best_effective_shift")),
        "best_direction_sign": str(summary.get("best_direction_sign") or ""),
        "best_residual_inf_n": _as_float(summary.get("best_residual_inf_n")),
        "best_improvement_inf_n": _as_float(
            summary.get("best_improvement_inf_n")
        ),
        "best_reduction_ratio": _as_float(summary.get("best_reduction_ratio")),
        "best_direction_inf_m": _as_float(summary.get("best_direction_inf_m")),
        "best_unregularized_tangent_plus_residual_relative_inf": _as_float(
            summary.get("best_unregularized_tangent_plus_residual_relative_inf")
        ),
        "best_regularization_action_vs_residual_inf": _as_float(
            summary.get("best_regularization_action_vs_residual_inf")
        ),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _active_set_load_parameter_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    summary = _as_dict(payload.get("summary"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "load_scale": _as_float(payload.get("load_scale")),
        "load_trust_radius": _as_float(payload.get("load_trust_radius")),
        "displacement_trust_radius_m": _as_float(
            payload.get("displacement_trust_radius_m")
        ),
        "initial_residual_inf_n": _as_float(
            summary.get("initial_residual_inf_n")
        ),
        "load_derivative_inf_n_per_load": _as_float(
            summary.get("load_derivative_inf_n_per_load")
        ),
        "best_linear_active_row_count": _as_int(
            summary.get("best_linear_active_row_count")
        ),
        "best_linear_delta_load_scale": _as_float(
            summary.get("best_linear_delta_load_scale")
        ),
        "best_linear_active_improvement_inf_n": _as_float(
            summary.get("best_linear_active_improvement_inf_n")
        ),
        "actual_replay_attempted": summary.get("actual_replay_attempted") is True,
        "actual_replay_descent_observed": (
            summary.get("actual_replay_descent_observed") is True
        ),
        "best_actual_replay_load_scale": _as_float(
            summary.get("best_actual_replay_load_scale")
        ),
        "best_actual_replay_residual_inf_n": _as_float(
            summary.get("best_actual_replay_residual_inf_n")
        ),
        "best_actual_replay_improvement_inf_n": _as_float(
            summary.get("best_actual_replay_improvement_inf_n")
        ),
        "best_actual_replay_residual_gate_passed": (
            summary.get("best_actual_replay_residual_gate_passed") is True
        ),
        "restored_full_load_replay_attempted": (
            summary.get("restored_full_load_replay_attempted") is True
        ),
        "restored_full_load_descent_observed": (
            summary.get("restored_full_load_descent_observed") is True
        ),
        "best_restored_full_load_residual_inf_n": _as_float(
            summary.get("best_restored_full_load_residual_inf_n")
        ),
        "best_restored_full_load_improvement_inf_n": _as_float(
            summary.get("best_restored_full_load_improvement_inf_n")
        ),
        "best_restored_full_load_residual_gate_passed": (
            summary.get("best_restored_full_load_residual_gate_passed") is True
        ),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _active_frontier_residual_ownership_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    summary = _as_dict(payload.get("summary"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "load_scale": _as_float(payload.get("load_scale")),
        "frame_tangent_source": str(payload.get("frame_tangent_source") or ""),
        "shell_pressure_load_path_policy": str(
            payload.get("shell_pressure_load_path_policy") or ""
        ),
        "top_residual_inf_n": _as_float(summary.get("top_residual_inf_n")),
        "residual_gate_passed": summary.get("residual_gate_passed") is True,
        "top_row_global_dof": _as_int(summary.get("top_row_global_dof")),
        "top_row_node_id": _as_int(summary.get("top_row_node_id")),
        "top_row_node_index": _as_int(summary.get("top_row_node_index")),
        "top_row_dof_label": str(summary.get("top_row_dof_label") or ""),
        "top_row_residual_n": _as_float(summary.get("top_row_residual_n")),
        "top_row_internal_sum_n": _as_float(
            summary.get("top_row_internal_sum_n")
        ),
        "top_row_inferred_external_load_n": _as_float(
            summary.get("top_row_inferred_external_load_n")
        ),
        "top_row_dominant_internal_component": str(
            summary.get("top_row_dominant_internal_component") or ""
        ),
        "top_row_balance_driver": str(summary.get("top_row_balance_driver") or ""),
        "top_row_load_derivative_n_per_load": _as_float(
            summary.get("top_row_load_derivative_n_per_load")
        ),
        "dominant_internal_component_counts": _as_dict(
            summary.get("dominant_internal_component_counts")
        ),
        "balance_driver_counts": _as_dict(summary.get("balance_driver_counts")),
        "load_derivative_inf_n_per_load": _as_float(
            summary.get("load_derivative_inf_n_per_load")
        ),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _active_frontier_shell_load_neighborhood_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    summary = _as_dict(payload.get("summary"))
    top_element = _as_dict(summary.get("top_incident_element"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "load_scale": _as_float(payload.get("load_scale")),
        "frame_tangent_source": str(payload.get("frame_tangent_source") or ""),
        "shell_pressure_load_path_policy": str(
            payload.get("shell_pressure_load_path_policy") or ""
        ),
        "top_residual_inf_n": _as_float(summary.get("top_residual_inf_n")),
        "shell_helper_row_count": _as_int(summary.get("shell_helper_row_count")),
        "surface_load_diagnostics_evaluated": (
            summary.get("surface_load_diagnostics_evaluated") is True
        ),
        "internal_element_diagnostics_evaluated": (
            summary.get("internal_element_diagnostics_evaluated") is True
        ),
        "external_minus_reference_shell_load_inf_n": _as_float(
            summary.get("external_minus_reference_shell_load_inf_n")
        ),
        "component_minus_reconstructed_shell_inf_n": _as_float(
            summary.get("component_minus_reconstructed_shell_inf_n")
        ),
        "component_minus_reconstructed_bending_inf_n": _as_float(
            summary.get("component_minus_reconstructed_bending_inf_n")
        ),
        "top_row_node_id": _as_int(summary.get("top_row_node_id")),
        "top_row_dof": str(summary.get("top_row_dof") or ""),
        "top_row_external_load_n": _as_float(
            summary.get("top_row_external_load_n")
        ),
        "top_row_reference_shell_load_reconstructed_n": _as_float(
            summary.get("top_row_reference_shell_load_reconstructed_n")
        ),
        "top_row_required_reference_shell_load_scale_for_zero_row_residual": _as_float(
            summary.get(
                "top_row_required_reference_shell_load_scale_for_zero_row_residual"
            )
        ),
        "top_row_shell_internal_to_reference_load_scale": _as_float(
            summary.get("top_row_shell_internal_to_reference_load_scale")
        ),
        "top_row_incident_surface_element_count": _as_int(
            summary.get("top_row_incident_surface_element_count")
        ),
        "top_row_surface_component_element_count": _as_int(
            summary.get("top_row_surface_component_element_count")
        ),
        "top_row_surface_component_frame_connected_node_count": _as_int(
            summary.get("top_row_surface_component_frame_connected_node_count")
        ),
        "top_row_surface_component_restrained_translation_dof_count": _as_int(
            summary.get("top_row_surface_component_restrained_translation_dof_count")
        ),
        "top_row_surface_component_free_pressure_resultant": (
            summary.get("top_row_surface_component_free_pressure_resultant") is True
        ),
        "top_incident_element_id": _as_int(top_element.get("elem_id")),
        "top_incident_element_reference_shell_load_n": _as_float(
            top_element.get("target_dof_reference_shell_load_n")
        ),
        "top_incident_element_bending_internal_force_n": _as_float(
            top_element.get("target_dof_bending_internal_force_n")
        ),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _active_frontier_shell_policy_replay_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    summary = _as_dict(payload.get("summary"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "load_scale": _as_float(payload.get("load_scale")),
        "frame_tangent_source": str(payload.get("frame_tangent_source") or ""),
        "baseline_policy": str(summary.get("baseline_policy") or ""),
        "baseline_residual_inf_n": _as_float(
            summary.get("baseline_residual_inf_n")
        ),
        "best_policy": str(summary.get("best_policy") or ""),
        "best_residual_inf_n": _as_float(summary.get("best_residual_inf_n")),
        "best_improvement_inf_n": _as_float(
            summary.get("best_improvement_inf_n")
        ),
        "best_reduction_ratio": _as_float(summary.get("best_reduction_ratio")),
        "best_residual_gate_passed": (
            summary.get("best_residual_gate_passed") is True
        ),
        "structural_or_attached_policy_descent_observed": (
            summary.get("structural_or_attached_policy_descent_observed") is True
        ),
        "best_policy_pressure_filter_enabled": (
            summary.get("best_policy_pressure_filter_enabled") is True
        ),
        "best_policy_pressure_suppressed_surface_element_count": _as_int(
            summary.get("best_policy_pressure_suppressed_surface_element_count")
        ),
        "ready_policy_count": _as_int(summary.get("ready_policy_count")),
        "anchor_global_dof": _as_int(summary.get("anchor_global_dof")),
        "anchor_reduced_index": _as_int(summary.get("anchor_reduced_index")),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _active_frontier_shell_policy_linearized_active_set_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    summary = _as_dict(payload.get("summary"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "load_scale": _as_float(payload.get("load_scale")),
        "frame_tangent_source": str(payload.get("frame_tangent_source") or ""),
        "shell_pressure_load_path_policy": str(
            payload.get("shell_pressure_load_path_policy") or ""
        ),
        "base_residual_inf_n": _as_float(summary.get("base_residual_inf_n")),
        "base_relative_residual_inf": _as_float(
            summary.get("base_relative_residual_inf")
        ),
        "base_residual_gate_passed": (
            summary.get("base_residual_gate_passed") is True
        ),
        "evaluated_active_row_count_schedule": [
            _as_int(value) for value in _as_list(summary.get("evaluated_active_row_count_schedule"))
        ],
        "best_active_row_count": _as_int(summary.get("best_active_row_count")),
        "best_linear_active_residual_before_inf_n": _as_float(
            summary.get("best_linear_active_residual_before_inf_n")
        ),
        "best_linear_active_residual_after_inf_n": _as_float(
            summary.get("best_linear_active_residual_after_inf_n")
        ),
        "best_linear_active_improvement_inf_n": _as_float(
            summary.get("best_linear_active_improvement_inf_n")
        ),
        "best_linear_active_reduction_ratio": _as_float(
            summary.get("best_linear_active_reduction_ratio")
        ),
        "linearized_active_descent_observed": (
            summary.get("linearized_active_descent_observed") is True
        ),
        "direct_replay_attempted": summary.get("direct_replay_attempted") is True,
        "direct_replay_required_for_candidate": (
            summary.get("direct_replay_required_for_candidate") is True
        ),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _active_frontier_shell_rotation_row_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    summary = _as_dict(payload.get("summary"))
    checkpoint = _as_dict(payload.get("output_final_checkpoint"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "load_scale": _as_float(payload.get("load_scale")),
        "shell_pressure_load_path_policy": str(
            payload.get("shell_pressure_load_path_policy") or ""
        ),
        "base_residual_inf_n": _as_float(summary.get("base_residual_inf_n")),
        "base_relative_residual_inf": _as_float(
            summary.get("base_relative_residual_inf")
        ),
        "selected_rotation_row_count": _as_int(
            summary.get("selected_rotation_row_count")
        ),
        "evaluated_jvp_row_count": _as_int(summary.get("evaluated_jvp_row_count")),
        "fd_consistent": summary.get("fd_consistent") is True,
        "max_selected_row_relative_error": _as_float(
            summary.get("max_selected_row_relative_error")
        ),
        "max_relative_inf_error": _as_float(
            summary.get("max_relative_inf_error")
        ),
        "min_action_cosine": _as_float(summary.get("min_action_cosine")),
        "correction_inf_rad": _as_float(summary.get("correction_inf_rad")),
        "best_direct_residual_inf_n": _as_float(
            summary.get("best_direct_residual_inf_n")
        ),
        "best_improvement_inf_n": _as_float(
            summary.get("best_improvement_inf_n")
        ),
        "direct_descent_observed": summary.get("direct_descent_observed") is True,
        "best_residual_gate_passed": (
            summary.get("best_residual_gate_passed") is True
        ),
        "checkpoint_written": checkpoint.get("written") is True,
        "checkpoint_path": str(checkpoint.get("path") or ""),
        "checkpoint_direct_residual_inf_n": _as_float(
            checkpoint.get("direct_residual_inf_n")
        ),
        "checkpoint_residual_gate_passed": (
            checkpoint.get("residual_gate_passed") is True
        ),
        "checkpoint_best_alpha": _as_float(checkpoint.get("best_alpha")),
        "checkpoint_accepted_iteration_count": _as_int(
            checkpoint.get("accepted_iteration_count")
        ),
        "claim_boundary": str(
            checkpoint.get("claim_boundary") or payload.get("claim_boundary") or ""
        ),
    }


def _sparse_direct_scaled_lsmr_frontier_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    direction = _as_dict(
        _as_dict(payload.get("direction_solve_comparison")).get("scaled_lsmr")
    )
    line_search = _as_dict(payload.get("line_search_preview"))
    resource = _as_dict(payload.get("resource_usage"))
    checkpoint = _as_dict(resource.get("checkpoint"))
    output_checkpoint = _as_dict(payload.get("output_final_checkpoint"))
    jvp = _as_dict(payload.get("jvp_parity"))
    tangent = _as_dict(payload.get("assembled_tangent_parity"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "reason_code": str(payload.get("reason_code") or ""),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "load_scale": _as_float(payload.get("load_scale")),
        "checkpoint_applied": checkpoint.get("checkpoint_applied") is True,
        "checkpoint_path": str(checkpoint.get("checkpoint_npz") or ""),
        "checkpoint_direct_residual_inf_n": _as_float(
            checkpoint.get("checkpoint_direct_residual_inf_n")
        ),
        "jvp_parity_pass": jvp.get("pass") is True,
        "assembled_tangent_parity_pass": tangent.get("pass") is True,
        "assembled_tangent_parity_max_relative_error": _as_float(
            tangent.get("max_relative_error")
        ),
        "direction_status": str(direction.get("status") or ""),
        "direction_reason_code": str(direction.get("reason_code") or ""),
        "direction_iterations": _as_int(direction.get("iterations")),
        "direction_residual_before_n": _as_float(
            direction.get("residual_norm_before")
        ),
        "direction_residual_after_linear_solve_n": _as_float(
            direction.get("residual_norm_after_linear_solve")
        ),
        "direction_condition_estimate": _as_float(
            direction.get("condition_estimate")
        ),
        "line_search_status": str(line_search.get("status") or ""),
        "line_search_accepted_alpha": _as_float(
            line_search.get("accepted_alpha")
        ),
        "line_search_residual_before_n": _as_float(
            line_search.get("residual_before_n")
        ),
        "line_search_residual_after_n": _as_float(
            line_search.get("residual_after_n")
        ),
        "line_search_residual_reduction_ratio": _as_float(
            line_search.get("residual_reduction_ratio")
        ),
        "output_checkpoint_written": output_checkpoint.get("written") is True,
        "output_checkpoint_path": str(output_checkpoint.get("path") or ""),
        "output_checkpoint_direct_residual_inf_n": _as_float(
            output_checkpoint.get("direct_residual_inf_n")
        ),
        "output_checkpoint_direct_relative_residual_inf": _as_float(
            output_checkpoint.get("direct_relative_residual_inf")
        ),
        "output_checkpoint_accepted_alpha": _as_float(
            output_checkpoint.get("accepted_alpha")
        ),
        "output_checkpoint_residual_gate_passed": (
            output_checkpoint.get("residual_gate_passed") is True
        ),
        "output_checkpoint_promotes_g1_closure": (
            output_checkpoint.get("promotes_g1_closure") is True
        ),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _sparse_direct_scaled_lsmr_chain_summary(
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    residual_pairs = [
        (
            _as_float(step.get("line_search_residual_before_n")),
            _as_float(step.get("line_search_residual_after_n")),
        )
        for step in steps
    ]
    ready_steps = [
        step
        for step in steps
        if step.get("status") == "ready"
        and step.get("line_search_status") == "ready"
    ]
    written_steps = [
        step for step in steps if step.get("output_checkpoint_written") is True
    ]
    finite_pairs = [
        (before, after)
        for before, after in residual_pairs
        if before is not None and after is not None
    ]
    step_descents = [after < before for before, after in finite_pairs]
    after_values = [after for _before, after in finite_pairs]
    monotonic_after = all(
        later <= earlier
        for earlier, later in zip(after_values, after_values[1:])
    )
    initial_residual = finite_pairs[0][0] if finite_pairs else None
    final_residual = (
        _as_float(steps[-1].get("output_checkpoint_direct_residual_inf_n"))
        if steps
        else None
    )
    if final_residual is None and finite_pairs:
        final_residual = finite_pairs[-1][1]
    total_reduction = (
        initial_residual - final_residual
        if initial_residual is not None and final_residual is not None
        else None
    )
    return {
        "present": bool(steps),
        "step_count": len(steps),
        "ready_step_count": len(ready_steps),
        "checkpoint_written_step_count": len(written_steps),
        "all_steps_ready": len(ready_steps) == len(steps) and bool(steps),
        "all_output_checkpoints_written": (
            len(written_steps) == len(steps) and bool(steps)
        ),
        "monotonic_residual_descent": (
            bool(finite_pairs) and all(step_descents) and monotonic_after
        ),
        "initial_residual_n": initial_residual,
        "final_residual_n": final_residual,
        "total_reduction_n": total_reduction,
        "total_reduction_ratio": (
            total_reduction / max(initial_residual, 1.0e-30)
            if total_reduction is not None and initial_residual is not None
            else None
        ),
        "latest_checkpoint_path": (
            str(steps[-1].get("output_checkpoint_path") or "") if steps else ""
        ),
        "latest_checkpoint_residual_gate_passed": (
            steps[-1].get("output_checkpoint_residual_gate_passed") is True
            if steps
            else False
        ),
        "promotes_g1_closure": False,
        "claim_boundary": (
            "Non-promoting scaled-LSMR accepted-step chain only; residual gate, "
            "material Newton breadth, full-mesh nonlinear equilibrium, and "
            "production ROCm/HIP closure remain open."
        ),
    }


def _sparse_direct_scaled_lsmr_chain_probe_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "reason_code": str(payload.get("reason_code") or ""),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "jvp_eps": _as_float(payload.get("jvp_eps")),
        "step_count": _as_int(payload.get("step_count")),
        "ready_step_count": _as_int(payload.get("ready_step_count")),
        "checkpoint_written_step_count": _as_int(
            payload.get("checkpoint_written_step_count")
        ),
        "monotonic_residual_descent": (
            payload.get("monotonic_residual_descent") is True
        ),
        "initial_residual_n": _as_float(payload.get("initial_residual_n")),
        "final_residual_n": _as_float(payload.get("final_residual_n")),
        "residual_gate_n": _as_float(payload.get("residual_gate_n")),
        "final_residual_gate_passed": (
            payload.get("final_residual_gate_passed") is True
        ),
        "final_residual_gate_gap_n": _as_float(
            payload.get("final_residual_gate_gap_n")
        ),
        "final_residual_over_gate": _as_float(
            payload.get("final_residual_over_gate")
        ),
        "total_reduction_n": _as_float(payload.get("total_reduction_n")),
        "total_reduction_ratio": _as_float(payload.get("total_reduction_ratio")),
        "last_step_reduction_n": _as_float(payload.get("last_step_reduction_n")),
        "estimated_steps_to_gate_at_last_reduction": _as_int(
            payload.get("estimated_steps_to_gate_at_last_reduction")
        ),
        "gate_convergence_assessment": str(
            payload.get("gate_convergence_assessment") or ""
        ),
        "recommended_next_action": str(payload.get("recommended_next_action") or ""),
        "latest_checkpoint_path": str(payload.get("latest_checkpoint_path") or ""),
        "latest_checkpoint_residual_gate_passed": (
            payload.get("latest_checkpoint_residual_gate_passed") is True
        ),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _sparse_direct_adaptive_jvp_eps_probe_summary(
    *,
    payload: dict[str, Any],
    path: Path,
    direction_solver: str,
) -> dict[str, Any]:
    direction = _as_dict(
        _as_dict(payload.get("direction_solve_comparison")).get(direction_solver)
    )
    preconditioner = _as_dict(direction.get("preconditioner"))
    baseline = _as_dict(
        _as_dict(payload.get("direction_solve_comparison")).get(
            "gmres_matrix_free_none"
        )
    )
    line_search = _as_dict(payload.get("line_search_preview"))
    output_checkpoint = _as_dict(payload.get("output_final_checkpoint"))
    jvp = _as_dict(payload.get("jvp_parity"))
    tangent = _as_dict(payload.get("assembled_tangent_parity"))
    resource = _as_dict(payload.get("resource_usage"))
    checkpoint = _as_dict(resource.get("checkpoint"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "reason_code": str(payload.get("reason_code") or ""),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "direction_solver": direction_solver,
        "jvp_eps": _as_float(payload.get("jvp_eps")),
        "checkpoint_path": str(checkpoint.get("checkpoint_npz") or ""),
        "checkpoint_direct_residual_inf_n": _as_float(
            checkpoint.get("checkpoint_direct_residual_inf_n")
        ),
        "jvp_parity_pass": jvp.get("pass") is True,
        "jvp_parity_max_absolute_error_n": _as_float(
            jvp.get("max_absolute_error_n")
        ),
        "jvp_parity_max_relative_error": _as_float(jvp.get("max_relative_error")),
        "assembled_tangent_parity_pass": tangent.get("pass") is True,
        "assembled_tangent_parity_max_absolute_error": _as_float(
            tangent.get("max_absolute_error")
        ),
        "assembled_tangent_parity_max_relative_error": _as_float(
            tangent.get("max_relative_error")
        ),
        "baseline_direction_status": str(baseline.get("status") or ""),
        "baseline_direction_reason_code": str(baseline.get("reason_code") or ""),
        "baseline_direction_iterations": _as_int(baseline.get("iterations")),
        "baseline_direction_residual_after_n": _as_float(
            baseline.get("residual_norm_after")
        ),
        "direction_status": str(direction.get("status") or ""),
        "direction_reason_code": str(direction.get("reason_code") or ""),
        "direction_iterations": _as_int(direction.get("iterations")),
        "direction_residual_after_n": _as_float(
            direction.get("residual_norm_after")
        ),
        "direction_residual_reduction_ratio": (
            (
                _as_float(direction.get("residual_norm_before"))
                - _as_float(direction.get("residual_norm_after"))
            )
            / max(_as_float(direction.get("residual_norm_before")) or 0.0, 1.0e-30)
            if _as_float(direction.get("residual_norm_before")) is not None
            and _as_float(direction.get("residual_norm_after")) is not None
            else None
        ),
        "preconditioner_mode": str(preconditioner.get("mode") or ""),
        "preconditioner_shift_mode": str(preconditioner.get("shift_mode") or ""),
        "preconditioner_shift_mu": _as_float(preconditioner.get("shift_mu")),
        "preconditioner_effective_shift": _as_float(
            preconditioner.get("effective_shift")
        ),
        "line_search_status": str(line_search.get("status") or ""),
        "line_search_reason_code": str(line_search.get("reason_code") or ""),
        "line_search_accepted_alpha": _as_float(line_search.get("accepted_alpha")),
        "line_search_residual_after_n": _as_float(line_search.get("residual_after_n")),
        "line_search_residual_reduction_ratio": _as_float(
            line_search.get("residual_reduction_ratio")
        ),
        "incomplete_direction_preview": (
            direction.get("incomplete_direction_preview") is True
            or line_search.get("incomplete_gmres_direction_preview") is True
        ),
        "preview_reason_code": str(direction.get("preview_reason_code") or ""),
        "incomplete_gmres_relative_tolerance": _as_float(
            direction.get("incomplete_gmres_relative_tolerance")
        ),
        "output_checkpoint_written": (
            output_checkpoint.get("written") is True
        ),
        "output_checkpoint_path": str(output_checkpoint.get("path") or ""),
        "output_checkpoint_direct_residual_inf_n": _as_float(
            output_checkpoint.get("direct_residual_inf_n")
        ),
        "output_checkpoint_residual_gate_passed": (
            output_checkpoint.get("residual_gate_passed") is True
        ),
        "output_checkpoint_incomplete_gmres_direction_preview": (
            output_checkpoint.get("incomplete_gmres_direction_preview") is True
        ),
        "recommended_next_action": (
            "replace_or_shift_preconditioner_family_before_more_gmres_iterations"
            if str(payload.get("reason_code") or "") == "ERR_ILU_FACTOR_FAILED"
            else "tune_shift_or_multilevel_preconditioner_before_accepting_shifted_ilu_direction"
            if direction_solver == "gmres_shifted_ilu"
            else "avoid_matrix_free_only_retry_until_operator_preconditioner_changes"
        ),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _sparse_direct_shifted_splu_probe_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    direction = _as_dict(
        _as_dict(payload.get("direction_solve_comparison")).get(
            "shifted_sparse_direct_splu"
        )
    )
    shifted = _as_dict(direction.get("shifted_operator"))
    line_search = _as_dict(payload.get("line_search_preview"))
    output_checkpoint = _as_dict(payload.get("output_final_checkpoint"))
    resource = _as_dict(payload.get("resource_usage"))
    checkpoint = _as_dict(resource.get("checkpoint"))
    jvp = _as_dict(payload.get("jvp_parity"))
    tangent = _as_dict(payload.get("assembled_tangent_parity"))
    gate_passed = output_checkpoint.get("residual_gate_passed") is True
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "reason_code": str(payload.get("reason_code") or ""),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "direction_solver": "shifted_sparse_direct_splu",
        "jvp_eps": _as_float(payload.get("jvp_eps")),
        "checkpoint_path": str(checkpoint.get("checkpoint_npz") or ""),
        "checkpoint_direct_residual_inf_n": _as_float(
            checkpoint.get("checkpoint_direct_residual_inf_n")
        ),
        "checkpoint_residual_gate_passed": (
            checkpoint.get("checkpoint_residual_gate_passed") is True
        ),
        "jvp_parity_pass": jvp.get("pass") is True,
        "assembled_tangent_parity_pass": tangent.get("pass") is True,
        "direction_status": str(direction.get("status") or ""),
        "direction_residual_before_n": _as_float(
            direction.get("residual_norm_before")
        ),
        "direction_residual_after_linear_solve_n": _as_float(
            direction.get("residual_norm_after_linear_solve")
        ),
        "direction_residual_after_shifted_linear_solve_n": _as_float(
            direction.get("residual_norm_after_shifted_linear_solve")
        ),
        "shifted_operator_mode": str(shifted.get("mode") or ""),
        "shifted_operator_shift_mode": str(shifted.get("shift_mode") or ""),
        "shifted_operator_shift_mu": _as_float(shifted.get("shift_mu")),
        "shifted_operator_effective_shift": _as_float(
            shifted.get("effective_shift")
        ),
        "line_search_status": str(line_search.get("status") or ""),
        "line_search_accepted_alpha": _as_float(line_search.get("accepted_alpha")),
        "line_search_residual_before_n": _as_float(
            line_search.get("residual_before_n")
        ),
        "line_search_residual_after_n": _as_float(
            line_search.get("residual_after_n")
        ),
        "line_search_residual_reduction_ratio": _as_float(
            line_search.get("residual_reduction_ratio")
        ),
        "output_checkpoint_written": output_checkpoint.get("written") is True,
        "output_checkpoint_path": str(output_checkpoint.get("path") or ""),
        "output_checkpoint_direct_residual_inf_n": _as_float(
            output_checkpoint.get("direct_residual_inf_n")
        ),
        "output_checkpoint_direct_relative_residual_inf": _as_float(
            output_checkpoint.get("direct_relative_residual_inf")
        ),
        "output_checkpoint_residual_gate_passed": gate_passed,
        "recommended_next_action": (
            "run_full_load_lane_material_mesh_hip_proofs_from_shifted_splu_gate_checkpoint"
            if gate_passed
            else "tune_shifted_direct_tangent_model_before_more_lsmr_iterations"
        ),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _adaptive_all_components_frontier_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    summary = _as_dict(payload.get("summary"))
    checkpoint = _as_dict(payload.get("output_final_checkpoint"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "reason_code": str(payload.get("reason_code") or ""),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "shell_pressure_load_path_policy": str(
            payload.get("shell_pressure_load_path_policy")
            or checkpoint.get("shell_pressure_load_path_policy")
            or ""
        ),
        "frame_tangent_source": str(
            payload.get("frame_tangent_source")
            or checkpoint.get("frame_tangent_source")
            or ""
        ),
        "initial_residual_n": _as_float(summary.get("initial_residual_n")),
        "final_residual_n": _as_float(summary.get("final_residual_n")),
        "total_reduction_ratio": _as_float(summary.get("total_reduction_ratio")),
        "residual_gate_passed": summary.get("residual_gate_passed") is True,
        "stop_reason": str(summary.get("stop_reason") or ""),
        "steps_taken": _as_int(summary.get("steps_taken")),
        "checkpoint_written": checkpoint.get("written") is True,
        "checkpoint_path": str(checkpoint.get("path") or ""),
        "checkpoint_load_scale": _as_float(checkpoint.get("load_scale")),
        "checkpoint_direct_residual_inf_n": _as_float(
            checkpoint.get("direct_residual_inf_n")
        ),
        "checkpoint_residual_gate_passed": (
            checkpoint.get("residual_gate_passed") is True
        ),
        "claim_boundary": str(
            checkpoint.get("claim_boundary") or payload.get("claim_boundary") or ""
        ),
    }


def _shell_hotspot_tangent_fd_jvp_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    rows = [
        row
        for row in _as_list(payload.get("residual_hotspot_tangent_fd_jvp_rows"))
        if isinstance(row, dict)
    ]
    evaluated_rows = [row for row in rows if row.get("evaluated") is True]
    max_relative_inf_error = max(
        (_as_float(row.get("relative_inf_error")) for row in evaluated_rows),
        default=0.0,
    )
    max_selected_row_relative_error = max(
        (_as_float(row.get("selected_row_relative_error")) for row in evaluated_rows),
        default=0.0,
    )
    min_action_cosine = min(
        (_as_float(row.get("action_cosine"), 1.0) for row in evaluated_rows),
        default=0.0,
    )
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "base_residual_inf_n": _as_float(payload.get("base_residual_inf_n")),
        "component_filter": str(
            payload.get("residual_hotspot_tangent_fd_jvp_component_filter")
            or ""
        ),
        "row_count": len(rows),
        "evaluated_row_count": len(evaluated_rows),
        "max_relative_inf_error": max_relative_inf_error,
        "max_selected_row_relative_error": max_selected_row_relative_error,
        "min_action_cosine": min_action_cosine,
        "fd_consistent": bool(
            evaluated_rows
            and max_relative_inf_error <= 1.0e-8
            and max_selected_row_relative_error <= 1.0e-8
        ),
        "claim_boundary": (
            "Shell hotspot tangent FD consistency evidence only; this does not "
            "close the residual gate or prove full G1 equilibrium."
        ),
    }


def _shell_hotspot_diagonal_sweep_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    sweep = _as_dict(payload.get("residual_hotspot_diagonal_newton_sweep"))
    best = _as_dict(sweep.get("best_candidate"))
    best_gate_eligible = _as_dict(sweep.get("best_gate_eligible_candidate"))
    base_residual = _as_float(
        sweep.get("base_direct_residual_inf_n")
        or payload.get("base_residual_inf_n")
    )
    best_residual = _as_float(best.get("direct_residual_inf_n"))
    best_improvement = _as_float(best.get("improvement_inf_n"))
    descent_observed = bool(
        best
        and best.get("free_dof_set_stable") is True
        and best_residual < base_residual
        and best_improvement > 0.0
    )
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "base_residual_inf_n": base_residual,
        "component_filter": str(sweep.get("component_filter") or ""),
        "evaluated": sweep.get("evaluated") is True,
        "selected_hotspot_row_count": _as_int(
            sweep.get("selected_hotspot_row_count")
        ),
        "correction_inf_m": _as_float(sweep.get("correction_inf_m")),
        "best_alpha": _as_float(best.get("alpha")),
        "best_direct_residual_inf_n": best_residual,
        "best_improvement_inf_n": best_improvement,
        "best_relative_increment": _as_float(best.get("relative_increment")),
        "best_residual_gate_passed": best.get("residual_gate_passed") is True,
        "best_relative_increment_gate_passed": (
            best.get("relative_increment_gate_passed") is True
        ),
        "best_gate_eligible_direct_residual_inf_n": _as_float(
            best_gate_eligible.get("direct_residual_inf_n")
        ),
        "descent_observed": descent_observed,
        "claim_boundary": (
            "Shell hotspot diagonal Newton sweep evidence only; diagonal/local "
            "correction is not a G1 closure substitute."
        ),
    }


def _global_tangent_scaled_sweep_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    sweep = _as_dict(payload.get("residual_global_tangent_newton_sweep"))
    best = _as_dict(sweep.get("best_candidate"))
    best_gate_eligible = _as_dict(sweep.get("best_gate_eligible_candidate"))
    solver_stats = _as_dict(sweep.get("solver_stats"))
    scaling = _as_dict(sweep.get("scaling"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "base_residual_inf_n": _as_float(
            sweep.get("base_direct_residual_inf_n")
            or payload.get("base_residual_inf_n")
        ),
        "evaluated": sweep.get("evaluated") is True,
        "solver": str(sweep.get("solver") or ""),
        "scaling_mode": str(scaling.get("mode") or ""),
        "descent_observed": sweep.get("descent_observed") is True,
        "direction_inf_m": _as_float(sweep.get("direction_inf_m")),
        "linear_residual_inf_n": _as_float(sweep.get("linear_residual_inf_n")),
        "linear_relative_residual_inf": _as_float(
            sweep.get("linear_relative_residual_inf")
        ),
        "solver_iteration_count": _as_int(solver_stats.get("iteration_count")),
        "solver_condition_estimate": _as_float(
            solver_stats.get("condition_estimate")
        ),
        "best_alpha": _as_float(best.get("alpha")),
        "best_direct_residual_inf_n": _as_float(
            best.get("direct_residual_inf_n")
        ),
        "best_improvement_inf_n": _as_float(best.get("improvement_inf_n")),
        "best_relative_increment": _as_float(best.get("relative_increment")),
        "best_residual_gate_passed": best.get("residual_gate_passed") is True,
        "best_relative_increment_gate_passed": (
            best.get("relative_increment_gate_passed") is True
        ),
        "best_gate_eligible_direct_residual_inf_n": _as_float(
            best_gate_eligible.get("direct_residual_inf_n")
        ),
        "claim_boundary": (
            "CPU diagnostic global tangent Newton sweep only; this is not a "
            "production ROCm/HIP or G1 closure receipt."
        ),
    }


def _residual_norm_gradient_tiny_sweep_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    sweep = _as_dict(payload.get("residual_norm_gradient_sweep"))
    best_inf = _as_dict(sweep.get("best_inf_candidate"))
    best_l2 = _as_dict(sweep.get("best_l2_candidate"))
    best_gate_eligible = _as_dict(sweep.get("best_gate_eligible_inf_candidate"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "evaluated": sweep.get("evaluated") is True,
        "direction": str(sweep.get("direction") or ""),
        "base_residual_inf_n": _as_float(
            sweep.get("base_direct_residual_inf_n")
            or payload.get("base_residual_inf_n")
        ),
        "base_residual_l2_n": _as_float(sweep.get("base_direct_residual_l2_n")),
        "trust_radius_m": _as_float(sweep.get("trust_radius_m")),
        "gradient_inf": _as_float(sweep.get("gradient_inf")),
        "gradient_l2": _as_float(sweep.get("gradient_l2")),
        "inf_descent_observed": sweep.get("inf_descent_observed") is True,
        "l2_descent_observed": sweep.get("l2_descent_observed") is True,
        "best_inf_direct_residual_inf_n": _as_float(
            best_inf.get("direct_residual_inf_n")
        ),
        "best_inf_improvement_inf_n": _as_float(best_inf.get("improvement_inf_n")),
        "best_l2_direct_residual_l2_n": _as_float(
            best_l2.get("direct_residual_l2_n")
        ),
        "best_l2_improvement_l2_n": _as_float(best_l2.get("improvement_l2_n")),
        "best_l2_relative_improvement_l2": _as_float(
            best_l2.get("relative_improvement_l2")
        ),
        "best_gate_eligible_direct_residual_inf_n": _as_float(
            best_gate_eligible.get("direct_residual_inf_n")
        ),
        "best_residual_gate_passed": best_inf.get("residual_gate_passed") is True,
        "best_relative_increment_gate_passed": (
            best_inf.get("relative_increment_gate_passed") is True
        ),
        "claim_boundary": (
            "CPU diagnostic residual-norm gradient sweep only; L2 descent is not "
            "a substitute for the G1 direct residual infinity-norm gate."
        ),
    }


def _active_set_ls_sweep_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    sweep = _as_dict(payload.get("residual_active_set_least_squares_sweep"))
    best_full = _as_dict(sweep.get("best_full_inf_candidate"))
    best_active = _as_dict(sweep.get("best_active_inf_candidate"))
    best_gate_eligible = _as_dict(
        sweep.get("best_gate_eligible_full_inf_candidate")
    )
    solver_stats = _as_dict(sweep.get("solver_stats"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "evaluated": sweep.get("evaluated") is True,
        "direction": str(sweep.get("direction") or ""),
        "selected_hotspot_row_count": _as_int(
            sweep.get("selected_hotspot_row_count")
        ),
        "base_residual_inf_n": _as_float(
            sweep.get("base_direct_residual_inf_n")
            or payload.get("base_residual_inf_n")
        ),
        "base_active_residual_inf_n": _as_float(
            sweep.get("base_active_residual_inf_n")
        ),
        "full_inf_descent_observed": sweep.get("full_inf_descent_observed")
        is True,
        "active_inf_descent_observed": sweep.get("active_inf_descent_observed")
        is True,
        "best_full_direct_residual_inf_n": _as_float(
            best_full.get("direct_residual_inf_n")
        ),
        "best_full_improvement_inf_n": _as_float(
            best_full.get("improvement_inf_n")
        ),
        "best_full_relative_increment": _as_float(
            best_full.get("relative_increment")
        ),
        "best_active_residual_inf_n": _as_float(
            best_active.get("active_residual_inf_n")
        ),
        "best_active_improvement_inf_n": _as_float(
            best_active.get("active_improvement_inf_n")
        ),
        "best_gate_eligible_direct_residual_inf_n": _as_float(
            best_gate_eligible.get("direct_residual_inf_n")
        ),
        "best_residual_gate_passed": best_full.get("residual_gate_passed")
        is True,
        "best_relative_increment_gate_passed": (
            best_full.get("relative_increment_gate_passed") is True
        ),
        "direction_inf_m": _as_float(sweep.get("direction_inf_m")),
        "active_linear_residual_inf_n": _as_float(
            sweep.get("active_linear_residual_inf_n")
        ),
        "solver_iteration_count": _as_int(solver_stats.get("iteration_count")),
        "solver_condition_estimate": _as_float(
            solver_stats.get("condition_estimate")
        ),
        "claim_boundary": (
            "CPU diagnostic active-set LS sweep only; one-step inf residual "
            "descent is not a G1 closure."
        ),
    }


def _active_set_ls_trust_candidate_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    summary = _as_dict(payload.get("summary"))
    checkpoint = _as_dict(payload.get("output_final_checkpoint"))
    runtime = _as_dict(payload.get("runtime_metrics"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "shell_pressure_load_path_policy": str(
            payload.get("shell_pressure_load_path_policy")
            or checkpoint.get("shell_pressure_load_path_policy")
            or ""
        ),
        "initial_residual_n": _as_float(summary.get("initial_residual_n")),
        "final_residual_n": _as_float(summary.get("final_residual_n")),
        "total_reduction_n": _as_float(summary.get("total_reduction_n")),
        "total_reduction_ratio": _as_float(summary.get("total_reduction_ratio")),
        "residual_gate_passed": summary.get("residual_gate_passed") is True,
        "steps_taken": _as_int(summary.get("steps_taken")),
        "stop_reason": str(summary.get("stop_reason") or ""),
        "active_row_count_schedule": [
            _as_int(item) for item in _as_list(summary.get("active_row_count_schedule"))
        ],
        "checkpoint_written": checkpoint.get("written") is True,
        "checkpoint_path": str(checkpoint.get("path") or ""),
        "checkpoint_load_scale": _as_float(checkpoint.get("load_scale")),
        "checkpoint_direct_residual_inf_n": _as_float(
            checkpoint.get("direct_residual_inf_n")
        ),
        "checkpoint_residual_gate_passed": (
            checkpoint.get("residual_gate_passed") is True
        ),
        "runtime_total_seconds": _as_float(runtime.get("total_seconds")),
        "claim_boundary": str(
            checkpoint.get("claim_boundary") or payload.get("claim_boundary") or ""
        ),
    }


def _active_frontier_direct_material_replay_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    base = _as_dict(payload.get("base_direct_residual"))
    final = _as_dict(payload.get("final_direct_residual"))
    live_contract = _as_dict(payload.get("live_g1_assembly_contract"))
    gate = _as_dict(payload.get("gate_assessment"))
    residual_contract = _as_dict(payload.get("residual_contract"))
    blockers = _as_list(gate.get("consistent_residual_jacobian_newton_blockers"))
    material_blockers = _as_list(gate.get("material_newton_breadth_blockers"))
    base_breakdown = _as_dict(base.get("residual_component_breakdown"))
    final_breakdown = _as_dict(final.get("residual_component_breakdown"))
    breakdown = final_breakdown or base_breakdown
    top_rows = [
        row for row in _as_list(breakdown.get("top_rows")) if isinstance(row, dict)
    ]
    top_row = _as_dict(top_rows[0] if top_rows else {})
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "source_commit_sha": str(payload.get("source_commit_sha") or ""),
        "load_scale": _as_float(base.get("load_scale") or live_contract.get("load_scale")),
        "state_updated_material_direct_residual_inf_n": _as_float(
            base.get("direct_residual_inf_n")
        ),
        "final_direct_residual_inf_n": _as_float(
            final.get("direct_residual_inf_n")
        ),
        "direct_residual_gate_passed": (
            final.get("residual_gate_passed") is True
            or gate.get("direct_residual_gate_passed") is True
        ),
        "live_g1_assembly_contract_passed": (
            live_contract.get("contract_pass") is True
        ),
        "live_g1_assembly_contract_residual_inf_n": _as_float(
            live_contract.get("residual_inf_norm")
        ),
        "consistent_residual_jacobian_newton_passed": (
            gate.get("consistent_residual_jacobian_newton_passed") is True
            or residual_contract.get("consistent_residual_jacobian_newton_gate_passed")
            is True
        ),
        "consistent_residual_jacobian_newton_blockers": [
            str(item) for item in blockers
        ],
        "material_newton_breadth_blockers": [
            str(item) for item in material_blockers
        ],
        "residual_component_breakdown_included": (
            residual_contract.get("residual_component_breakdown_included") is True
            or bool(breakdown)
        ),
        "residual_component_inf_n": _as_dict(breakdown.get("component_inf_n")),
        "top_row_dominant_component_counts": _as_dict(
            breakdown.get("top_row_dominant_component_counts")
        ),
        "top_row_global_dof": _as_int(top_row.get("global_dof")),
        "top_row_node_index": _as_int(top_row.get("node_index")),
        "top_row_dof": str(top_row.get("dof") or ""),
        "top_row_residual_n": _as_float(top_row.get("residual_n")),
        "top_row_external_load_n": _as_float(top_row.get("external_load_n")),
        "top_row_internal_sum_n": _as_float(top_row.get("internal_sum_n")),
        "top_row_dominant_component": str(top_row.get("dominant_component") or ""),
        "top_row_component_values_n": _as_dict(top_row.get("component_values_n")),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _active_frontier_current_component_row_correction_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    base = _as_dict(payload.get("base_direct_residual"))
    final = _as_dict(payload.get("final_direct_residual"))
    row_correction = _as_dict(payload.get("current_tangent_residual_row_correction"))
    best = _as_dict(row_correction.get("best_gate_eligible_candidate"))
    if not best:
        best = _as_dict(row_correction.get("best_candidate"))
    output = _as_dict(payload.get("output_final_checkpoint"))
    final_breakdown = _as_dict(final.get("residual_component_breakdown"))
    top_rows = [
        row for row in _as_list(final_breakdown.get("top_rows")) if isinstance(row, dict)
    ]
    top_row = _as_dict(top_rows[0] if top_rows else {})
    base_residual = _as_float(base.get("direct_residual_inf_n"))
    final_residual = _as_float(final.get("direct_residual_inf_n"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "source_commit_sha": str(payload.get("source_commit_sha") or ""),
        "base_direct_residual_inf_n": base_residual,
        "final_direct_residual_inf_n": final_residual,
        "improvement_inf_n": base_residual - final_residual,
        "direct_residual_gate_passed": final.get("residual_gate_passed") is True,
        "row_correction_enabled": row_correction.get("enabled") is True,
        "row_correction_attempted": row_correction.get("attempted") is True,
        "row_correction_accepted": row_correction.get("accepted") is True,
        "row_correction_promoted_to_final_state": (
            row_correction.get("promoted_to_final_state") is True
        ),
        "row_correction_stop_reason": str(row_correction.get("stop_reason") or ""),
        "target_mode": str(best.get("target_mode") or ""),
        "target_row_count": _as_int(best.get("target_row_count")),
        "support_column_count": _as_int(best.get("support_column_count")),
        "alpha": _as_float(best.get("alpha")),
        "best_candidate_direct_residual_inf_n": _as_float(
            best.get("direct_residual_inf_n")
        ),
        "best_candidate_improvement_inf_n": _as_float(best.get("improvement_inf_n")),
        "best_relative_improvement": _as_float(best.get("relative_improvement")),
        "best_relative_increment": _as_float(best.get("relative_increment")),
        "best_residual_gate_passed": best.get("residual_gate_passed") is True,
        "best_relative_increment_gate_passed": (
            best.get("relative_increment_gate_passed") is True
        ),
        "best_residual_only_assembly": best.get("residual_only_assembly") is True,
        "best_batch_alpha_replay": best.get("batch_alpha_replay") is True,
        "best_residual_batch_backend": str(best.get("residual_batch_backend") or ""),
        "accepted_state_refresh_cpu_used": any(
            _as_dict(row).get("accepted_state_refresh_cpu_used") is True
            for row in _as_list(row_correction.get("passes"))
            if isinstance(row, dict)
        ),
        "output_checkpoint_written": output.get("written") is True,
        "output_checkpoint_path": str(output.get("path") or ""),
        "output_checkpoint_direct_residual_inf_n": _as_float(
            output.get("direct_residual_inf_n")
        ),
        "top_row_global_dof": _as_int(top_row.get("global_dof")),
        "top_row_dof": str(top_row.get("dof") or ""),
        "top_row_residual_n": _as_float(top_row.get("residual_n")),
        "top_row_dominant_component": str(top_row.get("dominant_component") or ""),
        "claim_boundary": str(payload.get("claim_boundary") or ""),
    }


def _active_frontier_current_component_row_correction_chain_summary(
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    present_steps = [step for step in steps if step.get("present") is True]
    accepted_steps = [
        step for step in present_steps if step.get("row_correction_accepted") is True
    ]
    no_descent_steps = [
        step
        for step in present_steps
        if step.get("row_correction_attempted") is True
        and step.get("row_correction_accepted") is not True
    ]
    latest_accepted = accepted_steps[-1] if accepted_steps else {}
    final_values = [
        _as_float(step.get("final_direct_residual_inf_n"))
        for step in accepted_steps
    ]
    monotonic = all(
        final_values[index] <= final_values[index - 1]
        for index in range(1, len(final_values))
    )
    return {
        "present": bool(present_steps),
        "present_step_count": len(present_steps),
        "accepted_step_count": len(accepted_steps),
        "no_descent_step_count": len(no_descent_steps),
        "monotonic_accepted_descent": bool(monotonic),
        "base_direct_residual_inf_n": _as_float(
            present_steps[0].get("base_direct_residual_inf_n")
        )
        if present_steps
        else 0.0,
        "latest_accepted_final_residual_inf_n": _as_float(
            latest_accepted.get("final_direct_residual_inf_n")
        ),
        "latest_accepted_improvement_inf_n": _as_float(
            latest_accepted.get("improvement_inf_n")
        ),
        "latest_accepted_checkpoint_path": str(
            latest_accepted.get("output_checkpoint_path") or ""
        ),
        "first_no_descent_step_path": str(
            no_descent_steps[0].get("path") if no_descent_steps else ""
        ),
        "first_no_descent_stop_reason": str(
            no_descent_steps[0].get("row_correction_stop_reason")
            if no_descent_steps
            else ""
        ),
        "first_no_descent_best_residual_inf_n": _as_float(
            no_descent_steps[0].get("best_candidate_direct_residual_inf_n")
            if no_descent_steps
            else 0.0
        ),
        "direct_residual_gate_passed": any(
            step.get("direct_residual_gate_passed") is True for step in present_steps
        ),
        "uses_cpu_refresh": any(
            step.get("accepted_state_refresh_cpu_used") is True
            for step in present_steps
        ),
        "claim_boundary": (
            "Non-promoting current-component row-correction chain. It records "
            "state-updated physical direct-residual descent attempts and the "
            "first no-descent boundary; it does not close G1 without residual "
            "gate, material Newton breadth, and production ROCm/HIP residency."
        ),
    }


def _hip_required_full_load_residual_jvp_frontier_summary(
    *,
    payload: dict[str, Any],
    path: Path,
    candidate_path: Path,
) -> dict[str, Any]:
    base = _as_dict(payload.get("base_direct_residual"))
    final = _as_dict(payload.get("final_direct_residual"))
    gate = _as_dict(payload.get("gate_assessment"))
    residual_contract = _as_dict(payload.get("residual_contract"))
    output = _as_dict(payload.get("output_final_checkpoint"))
    global_krylov = _as_dict(payload.get("matrix_free_global_krylov"))
    global_best = _as_dict(global_krylov.get("best_gate_eligible_candidate"))
    if not global_best:
        global_best = _as_dict(global_krylov.get("best_candidate"))
    row_correction = _as_dict(payload.get("current_tangent_residual_row_correction"))
    row_best = _as_dict(row_correction.get("best_gate_eligible_candidate"))
    if not row_best:
        row_best = _as_dict(row_correction.get("best_candidate"))
    hip_rows = [
        row
        for row in _as_list(residual_contract.get("hip_residual_engine_rows"))
        if isinstance(row, dict)
    ]
    hip_required_count = _as_int(residual_contract.get("hip_residual_engine_required_lane_count"))
    hip_passed_count = _as_int(residual_contract.get("hip_residual_engine_passed_lane_count"))
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "source_commit_sha": str(payload.get("source_commit_sha") or ""),
        "load_scale": _as_float(base.get("load_scale") or output.get("load_scale")),
        "base_direct_residual_inf_n": _as_float(base.get("direct_residual_inf_n")),
        "final_direct_residual_inf_n": _as_float(final.get("direct_residual_inf_n")),
        "improvement_inf_n": (
            _as_float(base.get("direct_residual_inf_n"))
            - _as_float(final.get("direct_residual_inf_n"))
        ),
        "direct_relative_residual_inf": _as_float(final.get("direct_relative_residual_inf")),
        "direct_residual_gate_passed": (
            final.get("residual_gate_passed") is True
            or gate.get("direct_residual_gate_passed") is True
        ),
        "relative_increment_gate_passed": (
            gate.get("relative_increment_gate_passed") is True
        ),
        "full_load_closure_passed": gate.get("full_load_closure_passed") is True,
        "material_newton_breadth_passed": (
            gate.get("material_newton_breadth_passed") is True
        ),
        "consistent_residual_jacobian_newton_passed": (
            gate.get("consistent_residual_jacobian_newton_passed") is True
        ),
        "hip_residual_engine_gate_passed": (
            gate.get("hip_residual_engine_gate_passed") is True
            or residual_contract.get("hip_residual_engine_contract_passed") is True
        ),
        "hip_residual_engine_required_lane_count": hip_required_count,
        "hip_residual_engine_passed_lane_count": hip_passed_count,
        "hip_required_components_passed": bool(
            hip_required_count > 0 and hip_required_count == hip_passed_count
        ),
        "hip_residual_engine_backends": _strings(
            residual_contract.get("hip_residual_engine_backends")
        ),
        "hip_residual_engine_row_count": len(hip_rows),
        "matrix_free_global_krylov_accepted": (
            global_krylov.get("promoted_to_final_state") is True
        ),
        "matrix_free_global_krylov_best_residual_inf_n": _as_float(
            global_best.get("direct_residual_inf_n")
        ),
        "matrix_free_global_krylov_improvement_inf_n": _as_float(
            global_best.get("improvement_inf_n")
        ),
        "matrix_free_global_krylov_hip_solver_used": (
            global_krylov.get("hip_krylov_solver_used") is True
        ),
        "matrix_free_global_krylov_accepted_state_refresh_hip_used": (
            global_krylov.get("accepted_state_refresh_hip_used") is True
        ),
        "matrix_free_global_krylov_accepted_state_refresh_cpu_used": (
            global_krylov.get("accepted_state_refresh_cpu_used") is True
        ),
        "current_tangent_residual_row_correction_accepted": (
            row_correction.get("promoted_to_final_state") is True
        ),
        "current_tangent_residual_row_correction_best_residual_inf_n": _as_float(
            row_best.get("direct_residual_inf_n")
        ),
        "current_tangent_residual_row_correction_improvement_inf_n": _as_float(
            row_best.get("improvement_inf_n")
        ),
        "current_tangent_residual_row_correction_residual_batch_backend": str(
            row_best.get("residual_batch_backend") or ""
        ),
        "current_tangent_residual_row_correction_accepted_state_refresh_hip_used": (
            row_correction.get("accepted_state_refresh_hip_used") is True
        ),
        "current_tangent_residual_row_correction_accepted_state_refresh_cpu_used": (
            row_correction.get("accepted_state_refresh_cpu_used") is True
        ),
        "output_checkpoint_written": output.get("written") is True,
        "output_checkpoint_path": str(output.get("path") or candidate_path.as_posix()),
        "output_checkpoint_direct_residual_inf_n": _as_float(
            output.get("direct_residual_inf_n")
        ),
        "claim_boundary": (
            "Full-load HIP-required residual/JVP frontier evidence. It records "
            "HIP resident residual/JVP descent at load_scale 1.0, but it does not "
            "close G1 while the direct residual gate, consistent residual/Jacobian "
            "Newton gate, material Newton breadth, and full production residency "
            "remain open."
        ),
    }


def _hip_required_consistency_direct_probe_summary(
    *,
    payload: dict[str, Any],
) -> dict[str, Any]:
    hip_direct = _as_dict(payload.get("hip_direct_probe"))
    direct_summary = _as_dict(hip_direct.get("direct_residual_summary"))
    output_checkpoint = _as_dict(direct_summary.get("output_final_checkpoint"))
    gate = _as_dict(hip_direct.get("gate_assessment"))
    global_krylov = _as_dict(hip_direct.get("matrix_free_global_krylov"))
    row_correction = _as_dict(
        hip_direct.get("current_tangent_residual_row_correction")
    )
    worker = _as_dict(payload.get("production_rocm_hip_residual_jvp_worker"))
    base_residual = _as_float(direct_summary.get("base_direct_residual_inf_n"))
    final_residual = _as_float(direct_summary.get("final_direct_residual_inf_n"))
    return {
        "present": bool(hip_direct),
        "executed": hip_direct.get("executed") is True,
        "status": str(hip_direct.get("status") or payload.get("status") or "missing"),
        "source_commit_sha": str(payload.get("source_commit_sha") or ""),
        "load_scale": _as_float(
            payload.get("load_scale") or output_checkpoint.get("load_scale")
        ),
        "base_direct_residual_inf_n": base_residual,
        "final_direct_residual_inf_n": final_residual,
        "improvement_inf_n": base_residual - final_residual,
        "direct_relative_residual_inf": _as_float(
            direct_summary.get("final_direct_relative_residual_inf")
        ),
        "direct_residual_gate_passed": (
            gate.get("direct_residual_gate_passed") is True
        ),
        "relative_increment_gate_passed": (
            gate.get("relative_increment_gate_passed") is True
        ),
        "full_load_closure_passed": gate.get("full_load_closure_passed") is True,
        "consistent_residual_jacobian_newton_passed": (
            payload.get("consistent_residual_jacobian_newton_gate_passed") is True
            or gate.get("consistent_residual_jacobian_newton_passed") is True
        ),
        "material_newton_breadth_passed": (
            gate.get("material_newton_breadth_passed") is True
        ),
        "fallback_zero_passed": gate.get("fallback_zero_passed") is True,
        "production_hip_residual_jacobian_path": (
            payload.get("production_hip_residual_jacobian_path") is True
        ),
        "residual_jvp_worker_path_ready": (
            worker.get("residual_jvp_worker_path_ready") is True
        ),
        "g1_closure_gate_ready": worker.get("g1_closure_gate_ready") is True,
        "matrix_free_global_krylov_hip_solver_used": (
            global_krylov.get("hip_krylov_solver_used") is True
        ),
        "matrix_free_global_krylov_jvp_rows_retained": (
            global_krylov.get("jvp_rows_retained") is True
        ),
        "matrix_free_global_krylov_jvp_row_count": _as_int(
            global_krylov.get("jvp_row_count")
        ),
        "matrix_free_global_krylov_accepted_state_refresh_cpu_used": (
            global_krylov.get("accepted_state_refresh_cpu_used") is True
        ),
        "matrix_free_global_krylov_accepted_state_tangent_refresh_hip_used": (
            global_krylov.get("accepted_state_tangent_refresh_hip_used") is True
        ),
        "current_tangent_residual_row_correction_attempted": (
            row_correction.get("attempted") is True
        ),
        "current_tangent_residual_row_correction_promoted": (
            row_correction.get("promoted_to_final_state") is True
        ),
        "current_tangent_residual_row_correction_batch_replay_backend": str(
            row_correction.get("batch_replay_backend") or ""
        ),
        "current_tangent_residual_row_correction_accepted_state_refresh_cpu_used": (
            row_correction.get("accepted_state_refresh_cpu_used") is True
        ),
        "current_tangent_residual_row_correction_accepted_state_tangent_refresh_hip_used": (
            row_correction.get("accepted_state_tangent_refresh_hip_used") is True
        ),
        "output_checkpoint_written": output_checkpoint.get("written") is True,
        "output_checkpoint_path": str(output_checkpoint.get("path") or ""),
        "output_checkpoint_direct_residual_inf_n": _as_float(
            output_checkpoint.get("direct_residual_inf_n")
        ),
        "blocker_count": len(_strings(payload.get("blockers"))),
        "blockers": _strings(payload.get("blockers")),
        "claim_boundary": (
            "HIP-required consistency proof child summary. It proves the production "
            "HIP residual/JVP worker path progressed on a full-load checkpoint, but "
            "it does not close G1 while direct residual, material breadth, and "
            "consistent residual/Jacobian Newton gates remain open."
        ),
    }


def _hip_required_consistency_no_descent_summary(
    *,
    payload: dict[str, Any],
    path: Path,
    variant: str,
) -> dict[str, Any]:
    summary = _hip_required_consistency_direct_probe_summary(payload=payload)
    return {
        **summary,
        "path": path.as_posix(),
        "variant": variant,
        "no_descent": (
            summary["output_checkpoint_written"] is False
            and summary["final_direct_residual_inf_n"]
            >= summary["base_direct_residual_inf_n"]
        ),
        "receipt_kind": "hip_required_consistency_wrapper",
    }


def _hip_required_direct_no_descent_summary(
    *,
    payload: dict[str, Any],
    path: Path,
    variant: str,
) -> dict[str, Any]:
    base = _as_dict(payload.get("base_direct_residual"))
    final = _as_dict(payload.get("final_direct_residual"))
    output = _as_dict(payload.get("output_final_checkpoint"))
    gate = _as_dict(payload.get("gate_assessment"))
    global_krylov = _as_dict(payload.get("matrix_free_global_krylov"))
    global_best = _as_dict(global_krylov.get("best_gate_eligible_candidate"))
    if not global_best:
        global_best = _as_dict(global_krylov.get("best_candidate"))
    row_correction = _as_dict(payload.get("current_tangent_residual_row_correction"))
    row_best = _as_dict(row_correction.get("best_gate_eligible_candidate"))
    if not row_best:
        row_best = _as_dict(row_correction.get("best_candidate"))
    base_residual = _as_float(base.get("direct_residual_inf_n"))
    final_residual = _as_float(final.get("direct_residual_inf_n"))
    return {
        "path": path.as_posix(),
        "variant": variant,
        "receipt_kind": "direct_residual_probe",
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "source_commit_sha": str(payload.get("source_commit_sha") or ""),
        "load_scale": _as_float(base.get("load_scale") or output.get("load_scale")),
        "base_direct_residual_inf_n": base_residual,
        "final_direct_residual_inf_n": final_residual,
        "improvement_inf_n": base_residual - final_residual,
        "direct_residual_gate_passed": (
            final.get("residual_gate_passed") is True
            or gate.get("direct_residual_gate_passed") is True
        ),
        "relative_increment_gate_passed": (
            gate.get("relative_increment_gate_passed") is True
        ),
        "full_load_closure_passed": gate.get("full_load_closure_passed") is True,
        "material_newton_breadth_passed": (
            gate.get("material_newton_breadth_passed") is True
        ),
        "consistent_residual_jacobian_newton_passed": (
            gate.get("consistent_residual_jacobian_newton_passed") is True
        ),
        "output_checkpoint_written": output.get("written") is True,
        "output_checkpoint_reason": str(output.get("reason") or ""),
        "output_checkpoint_path": str(output.get("path") or ""),
        "no_descent": (
            output.get("written") is not True
            and (
                str(output.get("reason") or "") == "no_residual_descent"
                or final_residual >= base_residual
            )
        ),
        "matrix_free_global_krylov_attempted": global_krylov.get("attempted") is True,
        "matrix_free_global_krylov_promoted": (
            global_krylov.get("promoted_to_final_state") is True
        ),
        "matrix_free_global_krylov_scaling_mode": str(
            global_krylov.get("scaling_mode") or ""
        ),
        "matrix_free_global_krylov_best_residual_inf_n": _as_float(
            global_best.get("direct_residual_inf_n")
        ),
        "matrix_free_global_krylov_best_improvement_inf_n": _as_float(
            global_best.get("improvement_inf_n")
        ),
        "matrix_free_global_krylov_trial_count": len(
            _as_list(global_krylov.get("trial_rows"))
        ),
        "matrix_free_global_krylov_hip_solver_used": (
            global_krylov.get("hip_krylov_solver_used") is True
        ),
        "matrix_free_global_krylov_jvp_row_count": len(
            _as_list(global_krylov.get("jvp_rows"))
        ),
        "current_tangent_residual_row_attempted": (
            row_correction.get("attempted") is True
        ),
        "current_tangent_residual_row_promoted": (
            row_correction.get("promoted_to_final_state") is True
        ),
        "current_tangent_residual_row_best_residual_inf_n": _as_float(
            row_best.get("direct_residual_inf_n")
        ),
        "current_tangent_residual_row_best_improvement_inf_n": _as_float(
            row_best.get("improvement_inf_n")
        ),
        "current_tangent_residual_row_trial_count": len(
            _as_list(row_correction.get("trial_rows"))
        ),
        "claim_boundary": (
            "Non-promoting HIP direct no-descent receipt. It records that this "
            "full-load residual/JVP operator variant did not improve the physical "
            "direct residual, so it must not be promoted as G1 closure."
        ),
    }


def _directional_tangent_fd_jvp_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    rows = [row for row in _as_list(payload.get("direction_rows")) if isinstance(row, dict)]
    evaluated_rows = [row for row in rows if row.get("evaluated") is True]
    blocked_rows = [row for row in rows if row.get("evaluated") is not True]
    max_relative_inf_error = max(
        (_as_float(row.get("relative_inf_error")) for row in evaluated_rows),
        default=0.0,
    )
    max_relative_l2_error = max(
        (_as_float(row.get("relative_l2_error")) for row in evaluated_rows),
        default=0.0,
    )
    min_action_cosine = min(
        (_as_float(row.get("action_cosine"), 1.0) for row in evaluated_rows),
        default=0.0,
    )
    relative_error_threshold = _as_float(
        payload.get("relative_error_threshold"),
        0.25,
    )
    cosine_threshold = _as_float(payload.get("cosine_threshold"), 0.80)
    fd_consistent = bool(
        evaluated_rows
        and len(blocked_rows) == 0
        and max_relative_inf_error <= relative_error_threshold
        and max_relative_l2_error <= relative_error_threshold
        and min_action_cosine >= cosine_threshold
    )
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "checkpoint_path": str(_as_dict(payload.get("checkpoint")).get("path") or ""),
        "load_scale": _as_float(payload.get("load_scale")),
        "base_residual_inf_n": _as_float(payload.get("base_residual_inf_n")),
        "base_relative_residual_inf": _as_float(
            payload.get("base_relative_residual_inf")
        ),
        "row_count": len(rows),
        "evaluated_row_count": len(evaluated_rows),
        "blocked_row_count": len(blocked_rows),
        "max_relative_inf_error": max_relative_inf_error,
        "max_relative_l2_error": max_relative_l2_error,
        "min_action_cosine": min_action_cosine,
        "relative_error_threshold": relative_error_threshold,
        "cosine_threshold": cosine_threshold,
        "fd_consistent": fd_consistent,
        "residual_jacobian_consistency_ready": (
            payload.get("residual_jacobian_consistency_ready") is True
        ),
        "consistent_residual_jacobian_newton_gate_passed": (
            payload.get("consistent_residual_jacobian_newton_gate_passed") is True
        ),
        "claim_boundary": (
            "Active-set trust frontier directional tangent FD JVP evidence only; "
            "this validates local residual/Jacobian consistency but does not close "
            "the nonlinear residual gate, material breadth, or production HIP gate."
        ),
    }


def _active_set_minimax_trust_candidate_summary(
    *,
    payload: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    summary = _as_dict(payload.get("summary"))
    checkpoint = _as_dict(payload.get("output_final_checkpoint"))
    history = [row for row in _as_list(payload.get("history")) if isinstance(row, dict)]
    first_blocked = history[0] if history else {}
    attempts = [
        row
        for row in _as_list(_as_dict(first_blocked).get("direction_attempts"))
        if isinstance(row, dict)
    ]
    ready_attempts = [
        row for row in attempts if row.get("direction_status") == "ready"
    ]
    best_linear_improvement = max(
        (
            _as_float(_as_dict(row.get("direction")).get("active_linear_improvement_inf_n"))
            for row in ready_attempts
        ),
        default=0.0,
    )
    best_support_column_count = max(
        (
            _as_int(_as_dict(row.get("direction")).get("support_column_count"))
            for row in ready_attempts
        ),
        default=0,
    )
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "status": str(payload.get("status") or "missing"),
        "promotes_g1_closure": payload.get("promotes_g1_closure") is True,
        "initial_residual_n": _as_float(summary.get("initial_residual_n")),
        "final_residual_n": _as_float(summary.get("final_residual_n")),
        "total_reduction_n": _as_float(summary.get("total_reduction_n")),
        "total_reduction_ratio": _as_float(summary.get("total_reduction_ratio")),
        "residual_gate_passed": summary.get("residual_gate_passed") is True,
        "steps_taken": _as_int(summary.get("steps_taken")),
        "stop_reason": str(summary.get("stop_reason") or ""),
        "active_row_count_schedule": [
            _as_int(item) for item in _as_list(summary.get("active_row_count_schedule"))
        ],
        "support_strongest_per_row": _as_int(
            summary.get("support_strongest_per_row")
        ),
        "direction_attempt_count": len(attempts),
        "ready_direction_attempt_count": len(ready_attempts),
        "best_linear_active_inf_improvement_n": best_linear_improvement,
        "best_support_column_count": best_support_column_count,
        "checkpoint_written": checkpoint.get("written") is True,
        "checkpoint_path": str(checkpoint.get("path") or ""),
        "checkpoint_load_scale": _as_float(checkpoint.get("load_scale")),
        "checkpoint_direct_residual_inf_n": _as_float(
            checkpoint.get("direct_residual_inf_n")
        ),
        "checkpoint_residual_gate_passed": (
            checkpoint.get("residual_gate_passed") is True
        ),
        "claim_boundary": str(
            checkpoint.get("claim_boundary") or payload.get("claim_boundary") or ""
        ),
    }


def _next_actions(
    *,
    required_load_scale: float,
    highest_observed: float,
    g1_lane_path: Path,
    hip_probe_path: Path,
    assembly_contract_seed_path: Path,
) -> list[dict[str, Any]]:
    return [
        {
            "id": "promote_g1_assembly_contract_to_live_runner",
            "owner": "solver_numerics_owner",
            "status": "required",
            "required_receipts": [
                assembly_contract_seed_path.as_posix(),
                hip_probe_path.as_posix(),
            ],
            "acceptance": [
                "g1_assembly_contract_seed_report.contract_pass == true",
                "cpu seed direct residual/Newton residual parity passes",
                "live G1 residual/Jacobian proof keeps the same AssemblyResult contract",
                "fixed-point, map, and regularized residuals remain non-physical metrics",
            ],
        },
        {
            "id": "generate_full_load_1p0_checkpoint_candidate",
            "owner": "g1_solver_owner",
            "status": "required",
            "current_observed_load_scale": highest_observed,
            "required_load_scale": required_load_scale,
            "gap_to_required_load_scale": max(
                required_load_scale - highest_observed,
                0.0,
            ),
            "required_receipts": [
                "<full-load-checkpoint.npz>",
                g1_lane_path.as_posix(),
            ],
            "acceptance": [
                "checkpoint schema is mgt-direct-residual-newton-state.v1",
                "checkpoint load_scale >= 1.0",
                "g1_full_load_hip_newton_lane_report checkpoint_resolution_gate.passed == true",
            ],
        },
        {
            "id": "close_consistent_residual_jacobian_newton_gate",
            "owner": "solver_numerics_owner",
            "status": "required",
            "required_receipts": [
                assembly_contract_seed_path.as_posix(),
                hip_probe_path.as_posix(),
            ],
            "acceptance": [
                "AssemblyResult residual_free/tangent_free/Fint/Fext/material_state contract is live on the G1 runner",
                "consistent_residual_jacobian_newton_gate_passed == true",
                "regularized fixed-point residual is not used as the physical residual",
                "direct residual gate closes without CPU diagnostic assembler substitution",
            ],
        },
        {
            "id": "prove_production_rocm_hip_residual_jvp_worker",
            "owner": "runtime_rocm_owner",
            "status": "required",
            "required_receipts": [
                hip_probe_path.as_posix(),
                g1_lane_path.as_posix(),
            ],
            "acceptance": [
                "production ROCm/HIP residual-JVP worker path is ready",
                "worker has no CPU fallback in the claimed production path",
                "device-resident residual/JVP rows are retained through terminal gate replay",
            ],
        },
    ]


def build_runner_packet(
    *,
    repo_root: Path = ROOT,
    g1_lane_path: Path = DEFAULT_G1_LANE,
    cause_narrowing_path: Path = DEFAULT_CAUSE_NARROWING,
    hip_probe_path: Path = DEFAULT_HIP_PROBE,
    global_connectivity_path: Path = DEFAULT_GLOBAL_CONNECTIVITY,
    assembly_contract_seed_path: Path = DEFAULT_ASSEMBLY_CONTRACT_SEED,
    cpu_live_assembly_contract_probe_path: Path = (
        DEFAULT_CPU_LIVE_ASSEMBLY_CONTRACT_PROBE
    ),
    true_newton_load_sweep_path: Path = DEFAULT_TRUE_NEWTON_LOAD_SWEEP,
    true_newton_full_load_checkpoint_candidate_path: Path = (
        DEFAULT_TRUE_NEWTON_FULL_LOAD_CHECKPOINT_CANDIDATE
    ),
    true_newton_from_active_set_ls_trust_candidate_path: Path = (
        DEFAULT_TRUE_NEWTON_FROM_ACTIVE_SET_LS_TRUST_CANDIDATE
    ),
    true_newton_from_active_set_service_tangent_ls_trust_candidate_path: Path = (
        DEFAULT_TRUE_NEWTON_FROM_ACTIVE_SET_SERVICE_TANGENT_LS_TRUST_CANDIDATE
    ),
    adaptive_all_components_frontier_path: Path = DEFAULT_ADAPTIVE_ALL_COMPONENTS_FRONTIER,
    shell_hotspot_tangent_fd_jvp_probe_path: Path = (
        DEFAULT_SHELL_HOTSPOT_TANGENT_FD_JVP_PROBE
    ),
    shell_hotspot_diagonal_sweep_probe_path: Path = (
        DEFAULT_SHELL_HOTSPOT_DIAGONAL_SWEEP_PROBE
    ),
    global_tangent_scaled_sweep_probe_path: Path = (
        DEFAULT_GLOBAL_TANGENT_SCALED_SWEEP_PROBE
    ),
    residual_norm_gradient_tiny_sweep_probe_path: Path = (
        DEFAULT_RESIDUAL_NORM_GRADIENT_TINY_SWEEP_PROBE
    ),
    active_set_ls_sweep_probe_path: Path = DEFAULT_ACTIVE_SET_LS_SWEEP_PROBE,
    active_set_ls_trust_candidate_path: Path = DEFAULT_ACTIVE_SET_LS_TRUST_CANDIDATE,
    active_set_ls_trust_schedule_candidate_path: Path = (
        DEFAULT_ACTIVE_SET_LS_TRUST_SCHEDULE_CANDIDATE
    ),
    active_set_ls_trust_tangent_fd_jvp_probe_path: Path = (
        DEFAULT_ACTIVE_SET_LS_TRUST_TANGENT_FD_JVP_PROBE
    ),
    active_set_minimax_trust_candidate_path: Path = (
        DEFAULT_ACTIVE_SET_MINIMAX_TRUST_CANDIDATE
    ),
    frame_tangent_fd_epsilon_sweep_probe_path: Path = (
        DEFAULT_FRAME_TANGENT_FD_EPSILON_SWEEP_PROBE
    ),
    true_newton_from_active_set_mu_sweep_probe_path: Path = (
        DEFAULT_TRUE_NEWTON_FROM_ACTIVE_SET_MU_SWEEP_PROBE
    ),
    active_set_load_parameter_probe_path: Path = (
        DEFAULT_ACTIVE_SET_LOAD_PARAMETER_PROBE
    ),
    active_set_load_parameter_tiny_trust_probe_path: Path = (
        DEFAULT_ACTIVE_SET_LOAD_PARAMETER_TINY_TRUST_PROBE
    ),
    active_frontier_residual_ownership_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_RESIDUAL_OWNERSHIP_PROBE
    ),
    active_frontier_shell_load_neighborhood_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_SHELL_LOAD_NEIGHBORHOOD_PROBE
    ),
    active_frontier_shell_policy_replay_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_SHELL_POLICY_REPLAY_PROBE
    ),
    active_frontier_shell_policy_linearized_active_set_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_SHELL_POLICY_LINEARIZED_ACTIVE_SET_PROBE
    ),
    active_frontier_structural_policy_active_set_ls_trust_candidate_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_LS_TRUST_CANDIDATE
    ),
    active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_LS_TRUST_ALPHA_SWEEP
    ),
    active_frontier_structural_policy_active_set_direct_material_replay_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_DIRECT_MATERIAL_REPLAY_PROBE
    ),
    active_frontier_structural_policy_active_set_current_component_row_correction_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_CURRENT_COMPONENT_ROW_CORRECTION_PROBE
    ),
    active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_CURRENT_COMPONENT_ROW_CORRECTION_STEP2_PROBE
    ),
    active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_CURRENT_COMPONENT_ROW_CORRECTION_STEP3_PROBE
    ),
    active_frontier_structural_policy_residual_ownership_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_RESIDUAL_OWNERSHIP_PROBE
    ),
    active_frontier_structural_policy_linearized_active_set_after_two_step_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_LINEARIZED_ACTIVE_SET_AFTER_TWO_STEP_PROBE
    ),
    active_frontier_structural_policy_shell_rotation_row_candidate_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_SHELL_ROTATION_ROW_CANDIDATE
    ),
    active_frontier_structural_policy_shell_rotation_row_no_descent_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_SHELL_ROTATION_ROW_NO_DESCENT_PROBE
    ),
    active_frontier_structural_policy_shell_rotation_candidate_ownership_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_SHELL_ROTATION_CANDIDATE_OWNERSHIP_PROBE
    ),
    sparse_direct_scaled_lsmr_frontier_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FRONTIER_PROBE
    ),
    sparse_direct_scaled_lsmr_second_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SCALED_LSMR_SECOND_PROBE
    ),
    sparse_direct_scaled_lsmr_third_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SCALED_LSMR_THIRD_PROBE
    ),
    sparse_direct_scaled_lsmr_chain_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SCALED_LSMR_CHAIN_PROBE
    ),
    sparse_direct_scaled_lsmr_long_chain_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SCALED_LSMR_LONG_CHAIN_PROBE
    ),
    sparse_direct_scaled_lsmr_from_incomplete_preview_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FROM_INCOMPLETE_PREVIEW_PROBE
    ),
    sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FROM_INCOMPLETE_PREVIEW_CHAIN_PROBE
    ),
    sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SHIFTED_SPLU_FROM_INCOMPLETE_PREVIEW_CHAIN_PROBE
    ),
    sparse_direct_shifted_splu_from_gate_candidate_step2_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SHIFTED_SPLU_FROM_GATE_CANDIDATE_STEP2_PROBE
    ),
    sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_ILU_PROBE
    ),
    sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_MATRIX_FREE_PROBE
    ),
    sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_SHIFTED_ILU_PROBE
    ),
    sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_SHIFTED_ILU_INCOMPLETE_PREVIEW_PROBE
    ),
    hip_required_full_load_residual_jvp_frontier_probe_path: Path = (
        DEFAULT_HIP_REQUIRED_FULL_LOAD_RESIDUAL_JVP_FRONTIER_PROBE
    ),
    hip_required_full_load_residual_jvp_frontier_candidate_path: Path = (
        DEFAULT_HIP_REQUIRED_FULL_LOAD_RESIDUAL_JVP_FRONTIER_CANDIDATE
    ),
    hip_required_consistency_no_descent_probe_path: Path = (
        DEFAULT_HIP_REQUIRED_CONSISTENCY_NO_DESCENT_PROBE
    ),
    hip_required_scaled_global_krylov_no_descent_probe_path: Path = (
        DEFAULT_HIP_REQUIRED_SCALED_GLOBAL_KRYLOV_NO_DESCENT_PROBE
    ),
    current_frontier_operator_mismatch_audit_path: Path = (
        DEFAULT_CURRENT_FRONTIER_OPERATOR_MISMATCH_AUDIT
    ),
    phase2_material_newton_breadth_summary_path: Path = (
        DEFAULT_PHASE2_MATERIAL_NEWTON_BREADTH_SUMMARY
    ),
    phase2_material_newton_breadth_state_updated_seeds_path: Path = (
        DEFAULT_PHASE2_MATERIAL_NEWTON_BREADTH_STATE_UPDATED_SEEDS
    ),
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    g1_lane = _load_json(repo_root, g1_lane_path)
    cause_narrowing = _load_json(repo_root, cause_narrowing_path)
    hip_probe = _load_json(repo_root, hip_probe_path)
    hip_required_consistency_no_descent_probe = _load_json(
        repo_root,
        hip_required_consistency_no_descent_probe_path,
    )
    hip_required_scaled_global_krylov_no_descent_probe = _load_json(
        repo_root,
        hip_required_scaled_global_krylov_no_descent_probe_path,
    )
    current_frontier_operator_mismatch_audit = _load_json(
        repo_root,
        current_frontier_operator_mismatch_audit_path,
    )
    phase2_material_newton_breadth_summary = _load_json(
        repo_root,
        phase2_material_newton_breadth_summary_path,
    )
    phase2_material_newton_breadth_state_updated_seeds = _load_json(
        repo_root,
        phase2_material_newton_breadth_state_updated_seeds_path,
    )
    global_connectivity = _load_json(repo_root, global_connectivity_path)
    assembly_contract_seed = _load_json(repo_root, assembly_contract_seed_path)
    cpu_live_assembly_contract_probe = _load_json(
        repo_root, cpu_live_assembly_contract_probe_path
    )
    true_newton_load_sweep = _load_json(repo_root, true_newton_load_sweep_path)
    true_newton_full_load_checkpoint_candidate = _load_json(
        repo_root, true_newton_full_load_checkpoint_candidate_path
    )
    true_newton_from_active_set_ls_trust_candidate = _load_json(
        repo_root, true_newton_from_active_set_ls_trust_candidate_path
    )
    true_newton_from_active_set_service_tangent_ls_trust_candidate = _load_json(
        repo_root,
        true_newton_from_active_set_service_tangent_ls_trust_candidate_path,
    )
    adaptive_all_components_frontier = _load_json(
        repo_root, adaptive_all_components_frontier_path
    )
    shell_hotspot_tangent_fd_jvp_probe = _load_json(
        repo_root, shell_hotspot_tangent_fd_jvp_probe_path
    )
    shell_hotspot_diagonal_sweep_probe = _load_json(
        repo_root, shell_hotspot_diagonal_sweep_probe_path
    )
    global_tangent_scaled_sweep_probe = _load_json(
        repo_root, global_tangent_scaled_sweep_probe_path
    )
    residual_norm_gradient_tiny_sweep_probe = _load_json(
        repo_root, residual_norm_gradient_tiny_sweep_probe_path
    )
    active_set_ls_sweep_probe = _load_json(
        repo_root, active_set_ls_sweep_probe_path
    )
    active_set_ls_trust_candidate = _load_json(
        repo_root, active_set_ls_trust_candidate_path
    )
    active_set_ls_trust_schedule_candidate = _load_json(
        repo_root, active_set_ls_trust_schedule_candidate_path
    )
    active_set_ls_trust_tangent_fd_jvp_probe = _load_json(
        repo_root, active_set_ls_trust_tangent_fd_jvp_probe_path
    )
    active_set_minimax_trust_candidate = _load_json(
        repo_root, active_set_minimax_trust_candidate_path
    )
    frame_tangent_fd_epsilon_sweep_probe = _load_json(
        repo_root, frame_tangent_fd_epsilon_sweep_probe_path
    )
    true_newton_from_active_set_mu_sweep_probe = _load_json(
        repo_root, true_newton_from_active_set_mu_sweep_probe_path
    )
    active_set_load_parameter_probe = _load_json(
        repo_root, active_set_load_parameter_probe_path
    )
    active_set_load_parameter_tiny_trust_probe = _load_json(
        repo_root, active_set_load_parameter_tiny_trust_probe_path
    )
    active_frontier_residual_ownership_probe = _load_json(
        repo_root, active_frontier_residual_ownership_probe_path
    )
    active_frontier_shell_load_neighborhood_probe = _load_json(
        repo_root, active_frontier_shell_load_neighborhood_probe_path
    )
    active_frontier_shell_policy_replay_probe = _load_json(
        repo_root, active_frontier_shell_policy_replay_probe_path
    )
    active_frontier_shell_policy_linearized_active_set_probe = _load_json(
        repo_root, active_frontier_shell_policy_linearized_active_set_probe_path
    )
    active_frontier_structural_policy_active_set_ls_trust_candidate = _load_json(
        repo_root,
        active_frontier_structural_policy_active_set_ls_trust_candidate_path,
    )
    active_frontier_structural_policy_active_set_ls_trust_alpha_sweep = _load_json(
        repo_root,
        active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_path,
    )
    active_frontier_structural_policy_active_set_direct_material_replay_probe = (
        _load_json(
            repo_root,
            active_frontier_structural_policy_active_set_direct_material_replay_probe_path,
        )
    )
    active_frontier_structural_policy_active_set_current_component_row_correction_probe = (
        _load_json(
            repo_root,
            active_frontier_structural_policy_active_set_current_component_row_correction_probe_path,
        )
    )
    active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe = (
        _load_json(
            repo_root,
            active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe_path,
        )
    )
    active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe = (
        _load_json(
            repo_root,
            active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe_path,
        )
    )
    active_frontier_structural_policy_residual_ownership_probe = _load_json(
        repo_root,
        active_frontier_structural_policy_residual_ownership_probe_path,
    )
    active_frontier_structural_policy_linearized_active_set_after_two_step_probe = (
        _load_json(
            repo_root,
            active_frontier_structural_policy_linearized_active_set_after_two_step_probe_path,
        )
    )
    active_frontier_structural_policy_shell_rotation_row_candidate = _load_json(
        repo_root,
        active_frontier_structural_policy_shell_rotation_row_candidate_path,
    )
    active_frontier_structural_policy_shell_rotation_row_no_descent_probe = _load_json(
        repo_root,
        active_frontier_structural_policy_shell_rotation_row_no_descent_probe_path,
    )
    active_frontier_structural_policy_shell_rotation_candidate_ownership_probe = (
        _load_json(
            repo_root,
            active_frontier_structural_policy_shell_rotation_candidate_ownership_probe_path,
        )
    )
    sparse_direct_scaled_lsmr_frontier_probe = _load_json(
        repo_root,
        sparse_direct_scaled_lsmr_frontier_probe_path,
    )
    sparse_direct_scaled_lsmr_second_probe = _load_json(
        repo_root,
        sparse_direct_scaled_lsmr_second_probe_path,
    )
    sparse_direct_scaled_lsmr_third_probe = _load_json(
        repo_root,
        sparse_direct_scaled_lsmr_third_probe_path,
    )
    sparse_direct_scaled_lsmr_chain_probe = _load_json(
        repo_root,
        sparse_direct_scaled_lsmr_chain_probe_path,
    )
    sparse_direct_scaled_lsmr_long_chain_probe = _load_json(
        repo_root,
        sparse_direct_scaled_lsmr_long_chain_probe_path,
    )
    sparse_direct_scaled_lsmr_from_incomplete_preview_probe = _load_json(
        repo_root,
        sparse_direct_scaled_lsmr_from_incomplete_preview_probe_path,
    )
    sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe = _load_json(
        repo_root,
        sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_path,
    )
    sparse_direct_shifted_splu_from_incomplete_preview_chain_probe = _load_json(
        repo_root,
        sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_path,
    )
    sparse_direct_shifted_splu_from_gate_candidate_step2_probe = _load_json(
        repo_root,
        sparse_direct_shifted_splu_from_gate_candidate_step2_probe_path,
    )
    sparse_direct_adaptive_jvp_eps_gmres_ilu_probe = _load_json(
        repo_root,
        sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_path,
    )
    sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe = _load_json(
        repo_root,
        sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_path,
    )
    sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe = _load_json(
        repo_root,
        sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_path,
    )
    sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe = (
        _load_json(
            repo_root,
            sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_path,
        )
    )
    hip_required_full_load_residual_jvp_frontier_probe = _load_json(
        repo_root,
        hip_required_full_load_residual_jvp_frontier_probe_path,
    )
    action = _find_runner_action(g1_lane)
    checkpoint_gate = _as_dict(g1_lane.get("checkpoint_resolution_gate"))
    worker = _as_dict(hip_probe.get("production_rocm_hip_residual_jvp_worker"))
    worker_path_repair_plan = _worker_path_repair_plan(
        worker=worker,
        hip_probe_path=hip_probe_path,
    )
    worker_path_operator_sequence = _worker_path_operator_sequence(
        worker_path_repair_plan=worker_path_repair_plan,
        hip_probe_path=hip_probe_path,
        g1_lane_path=g1_lane_path,
    )
    terminal_partition = _as_dict(worker.get("terminal_gate_partition"))
    routing_blockers = _routing_blockers(
        action=action,
        cause_narrowing=cause_narrowing,
        checkpoint_gate=checkpoint_gate,
    )
    contract_blockers = [
        *_missing_artifact_blockers(
            g1_lane=g1_lane,
            cause_narrowing=cause_narrowing,
            hip_probe=hip_probe,
            assembly_contract_seed=assembly_contract_seed,
        ),
        *routing_blockers,
        *_assembly_contract_seed_blockers(assembly_contract_seed),
        *_live_assembly_contract_blockers(hip_probe),
    ]
    if worker and worker.get("residual_jvp_worker_path_ready") is not True:
        contract_blockers.append("production_rocm_hip_residual_jvp_worker_path_not_ready")
    contract_pass = bool(not contract_blockers)
    closure_blockers = _closure_blockers(
        g1_lane=g1_lane,
        hip_probe=hip_probe,
        worker=worker,
    )
    evidence_closure_pass = bool(
        contract_pass
        and checkpoint_gate.get("passed") is True
        and hip_probe.get("consistent_residual_jacobian_newton_gate_passed") is True
        and worker.get("g1_closure_gate_ready") is True
        and not closure_blockers
    )
    status = (
        "complete"
        if evidence_closure_pass
        else "ready_for_runner_implementation"
        if contract_pass
        else "blocked_runner_contract"
    )
    required_load_scale = _as_float(
        checkpoint_gate.get("required_load_scale")
        or action.get("required_load_scale")
        or 1.0,
        1.0,
    )
    highest_observed = _as_float(
        checkpoint_gate.get("highest_observed_load_scale")
        or action.get("highest_observed_load_scale")
    )
    next_actions = _next_actions(
        required_load_scale=required_load_scale,
        highest_observed=highest_observed,
        g1_lane_path=g1_lane_path,
        hip_probe_path=hip_probe_path,
        assembly_contract_seed_path=assembly_contract_seed_path,
    )
    true_newton_load_sweep_summary = _true_newton_load_sweep_summary(
        payload=true_newton_load_sweep,
        path=true_newton_load_sweep_path,
        required_load_scale=required_load_scale,
    )
    true_newton_full_load_checkpoint_candidate_summary = (
        _true_newton_full_load_checkpoint_candidate_summary(
            payload=true_newton_full_load_checkpoint_candidate,
            path=true_newton_full_load_checkpoint_candidate_path,
        )
    )
    true_newton_from_active_set_ls_trust_candidate_summary = (
        _true_newton_from_active_set_summary(
            payload=true_newton_from_active_set_ls_trust_candidate,
            path=true_newton_from_active_set_ls_trust_candidate_path,
        )
    )
    true_newton_from_active_set_service_tangent_ls_trust_candidate_summary = (
        _true_newton_from_active_set_summary(
            payload=true_newton_from_active_set_service_tangent_ls_trust_candidate,
            path=true_newton_from_active_set_service_tangent_ls_trust_candidate_path,
        )
    )
    true_newton_frame_tangent_source_comparison = (
        _true_newton_frame_tangent_source_comparison(
            force_based=true_newton_from_active_set_ls_trust_candidate_summary,
            service_tangent=(
                true_newton_from_active_set_service_tangent_ls_trust_candidate_summary
            ),
        )
    )
    adaptive_all_components_frontier_summary = (
        _adaptive_all_components_frontier_summary(
            payload=adaptive_all_components_frontier,
            path=adaptive_all_components_frontier_path,
        )
    )
    shell_hotspot_tangent_fd_jvp_summary = (
        _shell_hotspot_tangent_fd_jvp_summary(
            payload=shell_hotspot_tangent_fd_jvp_probe,
            path=shell_hotspot_tangent_fd_jvp_probe_path,
        )
    )
    shell_hotspot_diagonal_sweep_summary = (
        _shell_hotspot_diagonal_sweep_summary(
            payload=shell_hotspot_diagonal_sweep_probe,
            path=shell_hotspot_diagonal_sweep_probe_path,
        )
    )
    global_tangent_scaled_sweep_summary = (
        _global_tangent_scaled_sweep_summary(
            payload=global_tangent_scaled_sweep_probe,
            path=global_tangent_scaled_sweep_probe_path,
        )
    )
    residual_norm_gradient_tiny_sweep_summary = (
        _residual_norm_gradient_tiny_sweep_summary(
            payload=residual_norm_gradient_tiny_sweep_probe,
            path=residual_norm_gradient_tiny_sweep_probe_path,
        )
    )
    active_set_ls_sweep_summary = (
        _active_set_ls_sweep_summary(
            payload=active_set_ls_sweep_probe,
            path=active_set_ls_sweep_probe_path,
        )
    )
    active_set_ls_trust_candidate_summary = (
        _active_set_ls_trust_candidate_summary(
            payload=active_set_ls_trust_candidate,
            path=active_set_ls_trust_candidate_path,
        )
    )
    active_set_ls_trust_schedule_candidate_summary = (
        _active_set_ls_trust_candidate_summary(
            payload=active_set_ls_trust_schedule_candidate,
            path=active_set_ls_trust_schedule_candidate_path,
        )
    )
    active_set_ls_trust_tangent_fd_jvp_summary = (
        _directional_tangent_fd_jvp_summary(
            payload=active_set_ls_trust_tangent_fd_jvp_probe,
            path=active_set_ls_trust_tangent_fd_jvp_probe_path,
        )
    )
    active_set_minimax_trust_candidate_summary = (
        _active_set_minimax_trust_candidate_summary(
            payload=active_set_minimax_trust_candidate,
            path=active_set_minimax_trust_candidate_path,
        )
    )
    frame_tangent_fd_epsilon_sweep_summary = (
        _frame_tangent_fd_epsilon_sweep_summary(
            payload=frame_tangent_fd_epsilon_sweep_probe,
            path=frame_tangent_fd_epsilon_sweep_probe_path,
        )
    )
    true_newton_from_active_set_mu_sweep_summary = (
        _true_newton_from_active_set_mu_sweep_summary(
            payload=true_newton_from_active_set_mu_sweep_probe,
            path=true_newton_from_active_set_mu_sweep_probe_path,
        )
    )
    active_set_load_parameter_summary = _active_set_load_parameter_summary(
        payload=active_set_load_parameter_probe,
        path=active_set_load_parameter_probe_path,
    )
    active_set_load_parameter_tiny_trust_summary = (
        _active_set_load_parameter_summary(
            payload=active_set_load_parameter_tiny_trust_probe,
            path=active_set_load_parameter_tiny_trust_probe_path,
        )
    )
    active_frontier_residual_ownership_summary = (
        _active_frontier_residual_ownership_summary(
            payload=active_frontier_residual_ownership_probe,
            path=active_frontier_residual_ownership_probe_path,
        )
    )
    active_frontier_shell_load_neighborhood_summary = (
        _active_frontier_shell_load_neighborhood_summary(
            payload=active_frontier_shell_load_neighborhood_probe,
            path=active_frontier_shell_load_neighborhood_probe_path,
        )
    )
    active_frontier_shell_policy_replay_summary = (
        _active_frontier_shell_policy_replay_summary(
            payload=active_frontier_shell_policy_replay_probe,
            path=active_frontier_shell_policy_replay_probe_path,
        )
    )
    active_frontier_shell_policy_linearized_active_set_summary = (
        _active_frontier_shell_policy_linearized_active_set_summary(
            payload=active_frontier_shell_policy_linearized_active_set_probe,
            path=active_frontier_shell_policy_linearized_active_set_probe_path,
        )
    )
    active_frontier_structural_policy_active_set_ls_trust_candidate_summary = (
        _active_set_ls_trust_candidate_summary(
            payload=active_frontier_structural_policy_active_set_ls_trust_candidate,
            path=active_frontier_structural_policy_active_set_ls_trust_candidate_path,
        )
    )
    active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_summary = (
        _active_set_ls_trust_candidate_summary(
            payload=active_frontier_structural_policy_active_set_ls_trust_alpha_sweep,
            path=active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_path,
        )
    )
    active_frontier_structural_policy_active_set_direct_material_replay_summary = (
        _active_frontier_direct_material_replay_summary(
            payload=(
                active_frontier_structural_policy_active_set_direct_material_replay_probe
            ),
            path=active_frontier_structural_policy_active_set_direct_material_replay_probe_path,
        )
    )
    active_frontier_structural_policy_active_set_current_component_row_correction_summary = (
        _active_frontier_current_component_row_correction_summary(
            payload=(
                active_frontier_structural_policy_active_set_current_component_row_correction_probe
            ),
            path=active_frontier_structural_policy_active_set_current_component_row_correction_probe_path,
        )
    )
    active_frontier_structural_policy_active_set_current_component_row_correction_step2_summary = (
        _active_frontier_current_component_row_correction_summary(
            payload=(
                active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe
            ),
            path=active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe_path,
        )
    )
    active_frontier_structural_policy_active_set_current_component_row_correction_step3_summary = (
        _active_frontier_current_component_row_correction_summary(
            payload=(
                active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe
            ),
            path=active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe_path,
        )
    )
    active_frontier_structural_policy_active_set_current_component_row_correction_chain_summary = (
        _active_frontier_current_component_row_correction_chain_summary(
            [
                active_frontier_structural_policy_active_set_current_component_row_correction_summary,
                active_frontier_structural_policy_active_set_current_component_row_correction_step2_summary,
                active_frontier_structural_policy_active_set_current_component_row_correction_step3_summary,
            ]
        )
    )
    active_frontier_structural_policy_residual_ownership_summary = (
        _active_frontier_residual_ownership_summary(
            payload=active_frontier_structural_policy_residual_ownership_probe,
            path=active_frontier_structural_policy_residual_ownership_probe_path,
        )
    )
    active_frontier_structural_policy_linearized_after_two_step_summary = (
        _active_frontier_shell_policy_linearized_active_set_summary(
            payload=active_frontier_structural_policy_linearized_active_set_after_two_step_probe,
            path=active_frontier_structural_policy_linearized_active_set_after_two_step_probe_path,
        )
    )
    active_frontier_structural_policy_shell_rotation_row_candidate_summary = (
        _active_frontier_shell_rotation_row_summary(
            payload=active_frontier_structural_policy_shell_rotation_row_candidate,
            path=active_frontier_structural_policy_shell_rotation_row_candidate_path,
        )
    )
    active_frontier_structural_policy_shell_rotation_row_no_descent_summary = (
        _active_frontier_shell_rotation_row_summary(
            payload=active_frontier_structural_policy_shell_rotation_row_no_descent_probe,
            path=active_frontier_structural_policy_shell_rotation_row_no_descent_probe_path,
        )
    )
    active_frontier_structural_policy_shell_rotation_candidate_ownership_summary = (
        _active_frontier_residual_ownership_summary(
            payload=active_frontier_structural_policy_shell_rotation_candidate_ownership_probe,
            path=active_frontier_structural_policy_shell_rotation_candidate_ownership_probe_path,
        )
    )
    sparse_direct_scaled_lsmr_frontier_summary = (
        _sparse_direct_scaled_lsmr_frontier_summary(
            payload=sparse_direct_scaled_lsmr_frontier_probe,
            path=sparse_direct_scaled_lsmr_frontier_probe_path,
        )
    )
    sparse_direct_scaled_lsmr_second_summary = (
        _sparse_direct_scaled_lsmr_frontier_summary(
            payload=sparse_direct_scaled_lsmr_second_probe,
            path=sparse_direct_scaled_lsmr_second_probe_path,
        )
    )
    sparse_direct_scaled_lsmr_third_summary = (
        _sparse_direct_scaled_lsmr_frontier_summary(
            payload=sparse_direct_scaled_lsmr_third_probe,
            path=sparse_direct_scaled_lsmr_third_probe_path,
        )
    )
    sparse_direct_scaled_lsmr_chain_summary = (
        _sparse_direct_scaled_lsmr_chain_summary(
            [
                sparse_direct_scaled_lsmr_frontier_summary,
                sparse_direct_scaled_lsmr_second_summary,
                sparse_direct_scaled_lsmr_third_summary,
            ]
        )
    )
    sparse_direct_scaled_lsmr_chain_probe_summary = (
        _sparse_direct_scaled_lsmr_chain_probe_summary(
            payload=sparse_direct_scaled_lsmr_chain_probe,
            path=sparse_direct_scaled_lsmr_chain_probe_path,
        )
    )
    sparse_direct_scaled_lsmr_long_chain_probe_summary = (
        _sparse_direct_scaled_lsmr_chain_probe_summary(
            payload=sparse_direct_scaled_lsmr_long_chain_probe,
            path=sparse_direct_scaled_lsmr_long_chain_probe_path,
        )
    )
    sparse_direct_scaled_lsmr_from_incomplete_preview_summary = (
        _sparse_direct_scaled_lsmr_frontier_summary(
            payload=sparse_direct_scaled_lsmr_from_incomplete_preview_probe,
            path=sparse_direct_scaled_lsmr_from_incomplete_preview_probe_path,
        )
    )
    sparse_direct_scaled_lsmr_from_incomplete_preview_chain_summary = (
        _sparse_direct_scaled_lsmr_chain_probe_summary(
            payload=sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe,
            path=sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_path,
        )
    )
    sparse_direct_shifted_splu_from_incomplete_preview_chain_summary = (
        _sparse_direct_shifted_splu_probe_summary(
            payload=sparse_direct_shifted_splu_from_incomplete_preview_chain_probe,
            path=sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_path,
        )
    )
    sparse_direct_shifted_splu_from_gate_candidate_step2_summary = (
        _sparse_direct_shifted_splu_probe_summary(
            payload=sparse_direct_shifted_splu_from_gate_candidate_step2_probe,
            path=sparse_direct_shifted_splu_from_gate_candidate_step2_probe_path,
        )
    )
    sparse_direct_adaptive_jvp_eps_gmres_ilu_summary = (
        _sparse_direct_adaptive_jvp_eps_probe_summary(
            payload=sparse_direct_adaptive_jvp_eps_gmres_ilu_probe,
            path=sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_path,
            direction_solver="gmres_ilu",
        )
    )
    sparse_direct_adaptive_jvp_eps_gmres_matrix_free_summary = (
        _sparse_direct_adaptive_jvp_eps_probe_summary(
            payload=sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe,
            path=sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_path,
            direction_solver="gmres_matrix_free",
        )
    )
    sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_summary = (
        _sparse_direct_adaptive_jvp_eps_probe_summary(
            payload=sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe,
            path=sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_path,
            direction_solver="gmres_shifted_ilu",
        )
    )
    sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_summary = (
        _sparse_direct_adaptive_jvp_eps_probe_summary(
            payload=(
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe
            ),
            path=(
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_path
            ),
            direction_solver="gmres_shifted_ilu",
        )
    )
    hip_required_full_load_residual_jvp_frontier_summary = (
        _hip_required_full_load_residual_jvp_frontier_summary(
            payload=hip_required_full_load_residual_jvp_frontier_probe,
            path=hip_required_full_load_residual_jvp_frontier_probe_path,
            candidate_path=hip_required_full_load_residual_jvp_frontier_candidate_path,
        )
    )
    hip_required_consistency_direct_probe_summary = (
        _hip_required_consistency_direct_probe_summary(payload=hip_probe)
    )
    cpu_live_assembly_contract_probe_summary = (
        _cpu_live_assembly_contract_probe_summary(
            payload=cpu_live_assembly_contract_probe,
            path=cpu_live_assembly_contract_probe_path,
        )
    )
    hip_required_frontier_no_descent_receipts = [
        _hip_required_consistency_no_descent_summary(
            payload=hip_required_consistency_no_descent_probe,
            path=hip_required_consistency_no_descent_probe_path,
            variant="unscaled_consistency_wrapper_step16",
        ),
        _hip_required_direct_no_descent_summary(
            payload=hip_required_scaled_global_krylov_no_descent_probe,
            path=hip_required_scaled_global_krylov_no_descent_probe_path,
            variant="scaled_global_krylov_step16",
        ),
    ]
    hip_required_consistency_direct_checkpoint_path = Path(
        hip_required_consistency_direct_probe_summary["output_checkpoint_path"]
        or DEFAULT_HIP_REQUIRED_CONSISTENCY_DIRECT_FRONTIER_CANDIDATE.as_posix()
    )
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_g1_consistent_newton_full_load_checkpoint_candidate_runner.py"),
                assembly_contract_seed_path,
                g1_lane_path,
                cause_narrowing_path,
                hip_probe_path,
                global_connectivity_path,
                true_newton_load_sweep_path,
                cpu_live_assembly_contract_probe_path,
                true_newton_full_load_checkpoint_candidate_path,
                adaptive_all_components_frontier_path,
                shell_hotspot_tangent_fd_jvp_probe_path,
                shell_hotspot_diagonal_sweep_probe_path,
                global_tangent_scaled_sweep_probe_path,
                residual_norm_gradient_tiny_sweep_probe_path,
                active_set_ls_sweep_probe_path,
                active_set_ls_trust_candidate_path,
                active_set_ls_trust_schedule_candidate_path,
                true_newton_from_active_set_ls_trust_candidate_path,
                true_newton_from_active_set_service_tangent_ls_trust_candidate_path,
                frame_tangent_fd_epsilon_sweep_probe_path,
                true_newton_from_active_set_mu_sweep_probe_path,
                active_set_load_parameter_probe_path,
                active_set_load_parameter_tiny_trust_probe_path,
                active_frontier_residual_ownership_probe_path,
                active_frontier_shell_load_neighborhood_probe_path,
                active_frontier_shell_policy_replay_probe_path,
                active_frontier_shell_policy_linearized_active_set_probe_path,
                active_frontier_structural_policy_active_set_ls_trust_candidate_path,
                active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_path,
                active_frontier_structural_policy_residual_ownership_probe_path,
                active_frontier_structural_policy_linearized_active_set_after_two_step_probe_path,
                active_frontier_structural_policy_shell_rotation_row_candidate_path,
                active_frontier_structural_policy_shell_rotation_row_no_descent_probe_path,
                active_frontier_structural_policy_shell_rotation_candidate_ownership_probe_path,
                sparse_direct_scaled_lsmr_frontier_probe_path,
                DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FRONTIER_CANDIDATE,
                sparse_direct_scaled_lsmr_second_probe_path,
                DEFAULT_SPARSE_DIRECT_SCALED_LSMR_SECOND_CANDIDATE,
                sparse_direct_scaled_lsmr_third_probe_path,
                DEFAULT_SPARSE_DIRECT_SCALED_LSMR_THIRD_CANDIDATE,
                sparse_direct_scaled_lsmr_chain_probe_path,
                sparse_direct_scaled_lsmr_long_chain_probe_path,
                sparse_direct_scaled_lsmr_from_incomplete_preview_probe_path,
                DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FROM_INCOMPLETE_PREVIEW_CANDIDATE,
                sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_path,
                sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_path,
                sparse_direct_shifted_splu_from_gate_candidate_step2_probe_path,
                sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_path,
                sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_path,
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_path,
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_path,
                hip_required_full_load_residual_jvp_frontier_probe_path,
                hip_required_full_load_residual_jvp_frontier_candidate_path,
                hip_required_consistency_direct_checkpoint_path,
                hip_required_consistency_no_descent_probe_path,
                hip_required_scaled_global_krylov_no_descent_probe_path,
                current_frontier_operator_mismatch_audit_path,
                phase2_material_newton_breadth_summary_path,
                phase2_material_newton_breadth_state_updated_seeds_path,
            ],
            reused_evidence=True,
            reuse_policy=(
                "consistent_newton_full_load_runner_contract_from_g1_lane_and_cause_narrowing"
            ),
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": contract_pass,
        "evidence_closure_pass": evidence_closure_pass,
        "promotes_g1_closure": False,
        "summary_line": (
            "G1 consistent Newton full-load runner contract: "
            f"{status.upper()} | contract_pass={contract_pass} | "
            f"observed_load={highest_observed:g}/{required_load_scale:g} | "
            f"closure_blockers={len(closure_blockers)}"
        ),
        "summary": {
            "contract_status": status,
            "contract_pass": contract_pass,
            "evidence_closure_pass": evidence_closure_pass,
            "promotes_g1_closure": False,
            "primary_next_lane": PRIMARY_NEXT_LANE,
            "required_load_scale": required_load_scale,
            "highest_observed_load_scale": highest_observed,
            "highest_observed_gap_to_required_load_scale": max(
                required_load_scale - highest_observed,
                0.0,
            ),
            "full_load_candidate_count": _as_int(
                checkpoint_gate.get("full_load_candidate_count")
                or action.get("workspace_full_load_candidate_count")
            ),
            "true_newton_load_sweep_present": bool(true_newton_load_sweep),
            "true_newton_full_load_checkpoint_candidate_present": bool(
                true_newton_full_load_checkpoint_candidate
            ),
            "true_newton_full_load_checkpoint_candidate_written": (
                true_newton_full_load_checkpoint_candidate_summary[
                    "checkpoint_written"
                ]
            ),
            "true_newton_full_load_checkpoint_candidate_path": (
                true_newton_full_load_checkpoint_candidate_summary[
                    "checkpoint_path"
                ]
            ),
            "true_newton_full_load_checkpoint_candidate_direct_residual_n": (
                true_newton_full_load_checkpoint_candidate_summary[
                    "checkpoint_direct_residual_inf_n"
                ]
            ),
            "true_newton_from_active_set_present": bool(
                true_newton_from_active_set_ls_trust_candidate
            ),
            "true_newton_from_active_set_final_residual_n": (
                true_newton_from_active_set_ls_trust_candidate_summary[
                    "true_final_residual_n"
                ]
            ),
            "true_newton_from_active_set_residual_gate_passed": (
                true_newton_from_active_set_ls_trust_candidate_summary[
                    "true_residual_gate_passed"
                ]
            ),
            "true_newton_from_active_set_stop_reason": (
                true_newton_from_active_set_ls_trust_candidate_summary[
                    "true_stop_reason"
                ]
            ),
            "true_newton_from_active_set_max_jvp_gap_relative_inf": (
                true_newton_from_active_set_ls_trust_candidate_summary[
                    "max_jvp_minus_unregularized_tangent_action_relative_inf"
                ]
            ),
            "true_newton_from_active_set_dominant_gap_component": (
                true_newton_from_active_set_ls_trust_candidate_summary[
                    "dominant_jvp_gap_component"
                ]
            ),
            "true_newton_from_active_set_service_tangent_present": bool(
                true_newton_from_active_set_service_tangent_ls_trust_candidate
            ),
            "true_newton_from_active_set_service_tangent_final_residual_n": (
                true_newton_from_active_set_service_tangent_ls_trust_candidate_summary[
                    "true_final_residual_n"
                ]
            ),
            "true_newton_from_active_set_service_tangent_stop_reason": (
                true_newton_from_active_set_service_tangent_ls_trust_candidate_summary[
                    "true_stop_reason"
                ]
            ),
            "true_newton_from_active_set_service_tangent_max_jvp_gap_relative_inf": (
                true_newton_from_active_set_service_tangent_ls_trust_candidate_summary[
                    "max_jvp_minus_unregularized_tangent_action_relative_inf"
                ]
            ),
            "true_newton_from_active_set_service_tangent_dominant_gap_component": (
                true_newton_from_active_set_service_tangent_ls_trust_candidate_summary[
                    "dominant_jvp_gap_component"
                ]
            ),
            "true_newton_frame_tangent_source_comparison_present": (
                true_newton_frame_tangent_source_comparison["present"]
            ),
            "true_newton_frame_tangent_source_comparison_both_line_search_no_descent": (
                true_newton_frame_tangent_source_comparison[
                    "both_line_search_no_descent"
                ]
            ),
            "true_newton_frame_tangent_source_comparison_both_dominant_gap_component_frame": (
                true_newton_frame_tangent_source_comparison[
                    "both_dominant_gap_component_frame"
                ]
            ),
            "true_newton_frame_tangent_source_comparison_service_minus_force_jvp_gap": (
                true_newton_frame_tangent_source_comparison[
                    "service_minus_force_max_jvp_gap_relative_inf"
                ]
            ),
            "frame_tangent_fd_epsilon_sweep_present": bool(
                frame_tangent_fd_epsilon_sweep_probe
            ),
            "frame_tangent_fd_epsilon_sweep_default_gap_relative_inf": (
                frame_tangent_fd_epsilon_sweep_summary[
                    "default_eps_gap_relative_inf"
                ]
            ),
            "frame_tangent_fd_epsilon_sweep_best_eps": (
                frame_tangent_fd_epsilon_sweep_summary["best_eps"]
            ),
            "frame_tangent_fd_epsilon_sweep_best_gap_relative_inf": (
                frame_tangent_fd_epsilon_sweep_summary[
                    "best_eps_gap_relative_inf"
                ]
            ),
            "frame_tangent_fd_epsilon_sweep_default_eps_artifact_likely": (
                frame_tangent_fd_epsilon_sweep_summary[
                    "default_eps_artifact_likely"
                ]
            ),
            "frame_tangent_fd_epsilon_sweep_default_to_best_gap_ratio": (
                frame_tangent_fd_epsilon_sweep_summary[
                    "default_to_best_gap_ratio"
                ]
            ),
            "true_newton_from_active_set_mu_sweep_present": bool(
                true_newton_from_active_set_mu_sweep_probe
            ),
            "true_newton_from_active_set_mu_sweep_evaluated_mu_count": (
                true_newton_from_active_set_mu_sweep_summary[
                    "evaluated_mu_count"
                ]
            ),
            "true_newton_from_active_set_mu_sweep_factorable_mu_count": (
                true_newton_from_active_set_mu_sweep_summary[
                    "factorable_mu_count"
                ]
            ),
            "true_newton_from_active_set_mu_sweep_descent_observed": (
                true_newton_from_active_set_mu_sweep_summary[
                    "descent_observed"
                ]
            ),
            "true_newton_from_active_set_mu_sweep_best_mu": (
                true_newton_from_active_set_mu_sweep_summary["best_mu"]
            ),
            "true_newton_from_active_set_mu_sweep_best_residual_inf_n": (
                true_newton_from_active_set_mu_sweep_summary[
                    "best_residual_inf_n"
                ]
            ),
            "true_newton_from_active_set_mu_sweep_best_improvement_inf_n": (
                true_newton_from_active_set_mu_sweep_summary[
                    "best_improvement_inf_n"
                ]
            ),
            "true_newton_from_active_set_mu_sweep_best_direction_inf_m": (
                true_newton_from_active_set_mu_sweep_summary[
                    "best_direction_inf_m"
                ]
            ),
            "active_set_load_parameter_probe_present": bool(
                active_set_load_parameter_probe
            ),
            "active_set_load_parameter_probe_descent_observed": (
                active_set_load_parameter_summary[
                    "actual_replay_descent_observed"
                ]
            ),
            "active_set_load_parameter_probe_best_load_scale": (
                active_set_load_parameter_summary[
                    "best_actual_replay_load_scale"
                ]
            ),
            "active_set_load_parameter_probe_best_residual_inf_n": (
                active_set_load_parameter_summary[
                    "best_actual_replay_residual_inf_n"
                ]
            ),
            "active_set_load_parameter_probe_best_improvement_inf_n": (
                active_set_load_parameter_summary[
                    "best_actual_replay_improvement_inf_n"
                ]
            ),
            "active_set_load_parameter_probe_restored_full_load_descent_observed": (
                active_set_load_parameter_summary[
                    "restored_full_load_descent_observed"
                ]
            ),
            "active_set_load_parameter_probe_best_restored_full_load_residual_inf_n": (
                active_set_load_parameter_summary[
                    "best_restored_full_load_residual_inf_n"
                ]
            ),
            "active_set_load_parameter_probe_best_restored_full_load_improvement_inf_n": (
                active_set_load_parameter_summary[
                    "best_restored_full_load_improvement_inf_n"
                ]
            ),
            "active_set_load_parameter_tiny_trust_present": bool(
                active_set_load_parameter_tiny_trust_probe
            ),
            "active_set_load_parameter_tiny_trust_descent_observed": (
                active_set_load_parameter_tiny_trust_summary[
                    "actual_replay_descent_observed"
                ]
            ),
            "active_set_load_parameter_tiny_trust_best_load_scale": (
                active_set_load_parameter_tiny_trust_summary[
                    "best_actual_replay_load_scale"
                ]
            ),
            "active_set_load_parameter_tiny_trust_best_residual_inf_n": (
                active_set_load_parameter_tiny_trust_summary[
                    "best_actual_replay_residual_inf_n"
                ]
            ),
            "active_set_load_parameter_tiny_trust_best_improvement_inf_n": (
                active_set_load_parameter_tiny_trust_summary[
                    "best_actual_replay_improvement_inf_n"
                ]
            ),
            "active_set_load_parameter_tiny_trust_restored_full_load_descent_observed": (
                active_set_load_parameter_tiny_trust_summary[
                    "restored_full_load_descent_observed"
                ]
            ),
            "active_set_load_parameter_tiny_trust_best_restored_full_load_residual_inf_n": (
                active_set_load_parameter_tiny_trust_summary[
                    "best_restored_full_load_residual_inf_n"
                ]
            ),
            "active_set_load_parameter_tiny_trust_best_restored_full_load_improvement_inf_n": (
                active_set_load_parameter_tiny_trust_summary[
                    "best_restored_full_load_improvement_inf_n"
                ]
            ),
            "active_frontier_residual_ownership_present": bool(
                active_frontier_residual_ownership_probe
            ),
            "active_frontier_residual_ownership_top_residual_inf_n": (
                active_frontier_residual_ownership_summary["top_residual_inf_n"]
            ),
            "active_frontier_residual_ownership_top_row_node_id": (
                active_frontier_residual_ownership_summary["top_row_node_id"]
            ),
            "active_frontier_residual_ownership_top_row_dof_label": (
                active_frontier_residual_ownership_summary["top_row_dof_label"]
            ),
            "active_frontier_residual_ownership_top_row_dominant_internal_component": (
                active_frontier_residual_ownership_summary[
                    "top_row_dominant_internal_component"
                ]
            ),
            "active_frontier_residual_ownership_top_row_balance_driver": (
                active_frontier_residual_ownership_summary["top_row_balance_driver"]
            ),
            "active_frontier_residual_ownership_top_row_inferred_external_load_n": (
                active_frontier_residual_ownership_summary[
                    "top_row_inferred_external_load_n"
                ]
            ),
            "active_frontier_residual_ownership_top_row_load_derivative_n_per_load": (
                active_frontier_residual_ownership_summary[
                    "top_row_load_derivative_n_per_load"
                ]
            ),
            "active_frontier_shell_load_neighborhood_present": bool(
                active_frontier_shell_load_neighborhood_probe
            ),
            "active_frontier_shell_load_neighborhood_top_required_shell_load_scale": (
                active_frontier_shell_load_neighborhood_summary[
                    "top_row_required_reference_shell_load_scale_for_zero_row_residual"
                ]
            ),
            "active_frontier_shell_load_neighborhood_top_internal_to_reference_load_scale": (
                active_frontier_shell_load_neighborhood_summary[
                    "top_row_shell_internal_to_reference_load_scale"
                ]
            ),
            "active_frontier_shell_load_neighborhood_top_free_pressure_resultant": (
                active_frontier_shell_load_neighborhood_summary[
                    "top_row_surface_component_free_pressure_resultant"
                ]
            ),
            "active_frontier_shell_load_neighborhood_top_incident_surface_element_count": (
                active_frontier_shell_load_neighborhood_summary[
                    "top_row_incident_surface_element_count"
                ]
            ),
            "active_frontier_shell_load_neighborhood_top_surface_component_frame_connected_node_count": (
                active_frontier_shell_load_neighborhood_summary[
                    "top_row_surface_component_frame_connected_node_count"
                ]
            ),
            "active_frontier_shell_load_neighborhood_top_surface_component_restrained_translation_dof_count": (
                active_frontier_shell_load_neighborhood_summary[
                    "top_row_surface_component_restrained_translation_dof_count"
                ]
            ),
            "active_frontier_shell_load_neighborhood_top_incident_element_id": (
                active_frontier_shell_load_neighborhood_summary[
                    "top_incident_element_id"
                ]
            ),
            "active_frontier_shell_load_neighborhood_component_reconstruction_error_inf_n": (
                active_frontier_shell_load_neighborhood_summary[
                    "component_minus_reconstructed_shell_inf_n"
                ]
            ),
            "active_frontier_shell_load_neighborhood_external_reconstruction_error_inf_n": (
                active_frontier_shell_load_neighborhood_summary[
                    "external_minus_reference_shell_load_inf_n"
                ]
            ),
            "active_frontier_shell_policy_replay_present": bool(
                active_frontier_shell_policy_replay_probe
            ),
            "active_frontier_shell_policy_replay_baseline_policy": (
                active_frontier_shell_policy_replay_summary["baseline_policy"]
            ),
            "active_frontier_shell_policy_replay_baseline_residual_inf_n": (
                active_frontier_shell_policy_replay_summary[
                    "baseline_residual_inf_n"
                ]
            ),
            "active_frontier_shell_policy_replay_best_policy": (
                active_frontier_shell_policy_replay_summary["best_policy"]
            ),
            "active_frontier_shell_policy_replay_best_residual_inf_n": (
                active_frontier_shell_policy_replay_summary[
                    "best_residual_inf_n"
                ]
            ),
            "active_frontier_shell_policy_replay_best_improvement_inf_n": (
                active_frontier_shell_policy_replay_summary[
                    "best_improvement_inf_n"
                ]
            ),
            "active_frontier_shell_policy_replay_best_reduction_ratio": (
                active_frontier_shell_policy_replay_summary[
                    "best_reduction_ratio"
                ]
            ),
            "active_frontier_shell_policy_replay_best_residual_gate_passed": (
                active_frontier_shell_policy_replay_summary[
                    "best_residual_gate_passed"
                ]
            ),
            "active_frontier_shell_policy_replay_descent_observed": (
                active_frontier_shell_policy_replay_summary[
                    "structural_or_attached_policy_descent_observed"
                ]
            ),
            "active_frontier_shell_policy_replay_pressure_suppressed_surface_element_count": (
                active_frontier_shell_policy_replay_summary[
                    "best_policy_pressure_suppressed_surface_element_count"
                ]
            ),
            "active_frontier_shell_policy_linearized_active_set_present": bool(
                active_frontier_shell_policy_linearized_active_set_probe
            ),
            "active_frontier_shell_policy_linearized_active_set_policy": (
                active_frontier_shell_policy_linearized_active_set_summary[
                    "shell_pressure_load_path_policy"
                ]
            ),
            "active_frontier_shell_policy_linearized_active_set_base_residual_inf_n": (
                active_frontier_shell_policy_linearized_active_set_summary[
                    "base_residual_inf_n"
                ]
            ),
            "active_frontier_shell_policy_linearized_active_set_best_active_row_count": (
                active_frontier_shell_policy_linearized_active_set_summary[
                    "best_active_row_count"
                ]
            ),
            "active_frontier_shell_policy_linearized_active_set_best_after_inf_n": (
                active_frontier_shell_policy_linearized_active_set_summary[
                    "best_linear_active_residual_after_inf_n"
                ]
            ),
            "active_frontier_shell_policy_linearized_active_set_best_improvement_inf_n": (
                active_frontier_shell_policy_linearized_active_set_summary[
                    "best_linear_active_improvement_inf_n"
                ]
            ),
            "active_frontier_shell_policy_linearized_active_set_descent_observed": (
                active_frontier_shell_policy_linearized_active_set_summary[
                    "linearized_active_descent_observed"
                ]
            ),
            "active_frontier_shell_policy_linearized_active_set_direct_replay_required": (
                active_frontier_shell_policy_linearized_active_set_summary[
                    "direct_replay_required_for_candidate"
                ]
            ),
            "active_frontier_structural_policy_active_set_ls_trust_present": bool(
                active_frontier_structural_policy_active_set_ls_trust_candidate
            ),
            "active_frontier_structural_policy_active_set_ls_trust_policy": (
                active_frontier_structural_policy_active_set_ls_trust_candidate_summary[
                    "shell_pressure_load_path_policy"
                ]
            ),
            "active_frontier_structural_policy_active_set_ls_trust_final_residual_n": (
                active_frontier_structural_policy_active_set_ls_trust_candidate_summary[
                    "final_residual_n"
                ]
            ),
            "active_frontier_structural_policy_active_set_ls_trust_total_reduction_n": (
                active_frontier_structural_policy_active_set_ls_trust_candidate_summary[
                    "total_reduction_n"
                ]
            ),
            "active_frontier_structural_policy_active_set_ls_trust_total_reduction_ratio": (
                active_frontier_structural_policy_active_set_ls_trust_candidate_summary[
                    "total_reduction_ratio"
                ]
            ),
            "active_frontier_structural_policy_active_set_ls_trust_residual_gate_passed": (
                active_frontier_structural_policy_active_set_ls_trust_candidate_summary[
                    "residual_gate_passed"
                ]
            ),
            "active_frontier_structural_policy_active_set_ls_trust_checkpoint_path": (
                active_frontier_structural_policy_active_set_ls_trust_candidate_summary[
                    "checkpoint_path"
                ]
            ),
            "active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_stop_reason": (
                active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_summary[
                    "stop_reason"
                ]
            ),
            "active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_final_residual_n": (
                active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_summary[
                    "final_residual_n"
                ]
            ),
            "active_frontier_structural_policy_active_set_state_updated_direct_replay_present": bool(
                active_frontier_structural_policy_active_set_direct_material_replay_probe
            ),
            "active_frontier_structural_policy_active_set_state_updated_direct_replay_residual_n": (
                active_frontier_structural_policy_active_set_direct_material_replay_summary[
                    "state_updated_material_direct_residual_inf_n"
                ]
            ),
            "active_frontier_structural_policy_active_set_state_updated_direct_replay_gate": (
                active_frontier_structural_policy_active_set_direct_material_replay_summary[
                    "direct_residual_gate_passed"
                ]
            ),
            "active_frontier_structural_policy_active_set_state_updated_direct_replay_gap_n": (
                _as_float(
                    active_frontier_structural_policy_active_set_direct_material_replay_summary[
                        "state_updated_material_direct_residual_inf_n"
                    ]
                )
                - _as_float(
                    active_frontier_structural_policy_active_set_ls_trust_candidate_summary[
                        "final_residual_n"
                    ]
                )
            ),
            "active_frontier_structural_policy_active_set_state_updated_direct_replay_top_row_component": (
                active_frontier_structural_policy_active_set_direct_material_replay_summary[
                    "top_row_dominant_component"
                ]
            ),
            "active_frontier_structural_policy_active_set_state_updated_direct_replay_top_row_residual_n": (
                active_frontier_structural_policy_active_set_direct_material_replay_summary[
                    "top_row_residual_n"
                ]
            ),
            "active_frontier_structural_policy_active_set_state_updated_direct_replay_top_row_global_dof": (
                active_frontier_structural_policy_active_set_direct_material_replay_summary[
                    "top_row_global_dof"
                ]
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_present": bool(
                active_frontier_structural_policy_active_set_current_component_row_correction_probe
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_accepted": (
                active_frontier_structural_policy_active_set_current_component_row_correction_summary[
                    "row_correction_accepted"
                ]
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_final_residual_n": (
                active_frontier_structural_policy_active_set_current_component_row_correction_summary[
                    "final_direct_residual_inf_n"
                ]
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_improvement_n": (
                active_frontier_structural_policy_active_set_current_component_row_correction_summary[
                    "improvement_inf_n"
                ]
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_gate": (
                active_frontier_structural_policy_active_set_current_component_row_correction_summary[
                    "direct_residual_gate_passed"
                ]
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_cpu_refresh": (
                active_frontier_structural_policy_active_set_current_component_row_correction_summary[
                    "accepted_state_refresh_cpu_used"
                ]
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_step2_present": bool(
                active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_step2_accepted": (
                active_frontier_structural_policy_active_set_current_component_row_correction_step2_summary[
                    "row_correction_accepted"
                ]
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_step2_final_residual_n": (
                active_frontier_structural_policy_active_set_current_component_row_correction_step2_summary[
                    "final_direct_residual_inf_n"
                ]
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_step2_improvement_n": (
                active_frontier_structural_policy_active_set_current_component_row_correction_step2_summary[
                    "improvement_inf_n"
                ]
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_step2_gate": (
                active_frontier_structural_policy_active_set_current_component_row_correction_step2_summary[
                    "direct_residual_gate_passed"
                ]
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_step2_cpu_refresh": (
                active_frontier_structural_policy_active_set_current_component_row_correction_step2_summary[
                    "accepted_state_refresh_cpu_used"
                ]
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_step3_present": bool(
                active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_step3_accepted": (
                active_frontier_structural_policy_active_set_current_component_row_correction_step3_summary[
                    "row_correction_accepted"
                ]
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_step3_stop_reason": (
                active_frontier_structural_policy_active_set_current_component_row_correction_step3_summary[
                    "row_correction_stop_reason"
                ]
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_step3_best_residual_n": (
                active_frontier_structural_policy_active_set_current_component_row_correction_step3_summary[
                    "best_candidate_direct_residual_inf_n"
                ]
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_chain_latest_residual_n": (
                active_frontier_structural_policy_active_set_current_component_row_correction_chain_summary[
                    "latest_accepted_final_residual_inf_n"
                ]
            ),
            "active_frontier_structural_policy_active_set_current_component_row_correction_chain_no_descent_stop": (
                active_frontier_structural_policy_active_set_current_component_row_correction_chain_summary[
                    "first_no_descent_stop_reason"
                ]
            ),
            "active_frontier_structural_policy_residual_ownership_present": bool(
                active_frontier_structural_policy_residual_ownership_probe
            ),
            "active_frontier_structural_policy_residual_ownership_top_residual_inf_n": (
                active_frontier_structural_policy_residual_ownership_summary[
                    "top_residual_inf_n"
                ]
            ),
            "active_frontier_structural_policy_residual_ownership_top_row_node_id": (
                active_frontier_structural_policy_residual_ownership_summary[
                    "top_row_node_id"
                ]
            ),
            "active_frontier_structural_policy_residual_ownership_top_row_dof_label": (
                active_frontier_structural_policy_residual_ownership_summary[
                    "top_row_dof_label"
                ]
            ),
            "active_frontier_structural_policy_residual_ownership_top_row_component": (
                active_frontier_structural_policy_residual_ownership_summary[
                    "top_row_dominant_internal_component"
                ]
            ),
            "active_frontier_structural_policy_residual_ownership_top_row_balance_driver": (
                active_frontier_structural_policy_residual_ownership_summary[
                    "top_row_balance_driver"
                ]
            ),
            "active_frontier_structural_policy_residual_ownership_top_row_external_load_n": (
                active_frontier_structural_policy_residual_ownership_summary[
                    "top_row_inferred_external_load_n"
                ]
            ),
            "active_frontier_structural_policy_residual_ownership_top_row_load_derivative_n_per_load": (
                active_frontier_structural_policy_residual_ownership_summary[
                    "top_row_load_derivative_n_per_load"
                ]
            ),
            "active_frontier_structural_policy_linearized_after_two_step_best_after_inf_n": (
                active_frontier_structural_policy_linearized_after_two_step_summary[
                    "best_linear_active_residual_after_inf_n"
                ]
            ),
            "active_frontier_structural_policy_linearized_after_two_step_descent_observed": (
                active_frontier_structural_policy_linearized_after_two_step_summary[
                    "linearized_active_descent_observed"
                ]
            ),
            "active_frontier_structural_policy_linearized_after_two_step_direct_replay_required": (
                active_frontier_structural_policy_linearized_after_two_step_summary[
                    "direct_replay_required_for_candidate"
                ]
            ),
            "active_frontier_structural_policy_shell_rotation_candidate_present": bool(
                active_frontier_structural_policy_shell_rotation_row_candidate
            ),
            "active_frontier_structural_policy_shell_rotation_candidate_fd_consistent": (
                active_frontier_structural_policy_shell_rotation_row_candidate_summary[
                    "fd_consistent"
                ]
            ),
            "active_frontier_structural_policy_shell_rotation_candidate_best_residual_inf_n": (
                active_frontier_structural_policy_shell_rotation_row_candidate_summary[
                    "best_direct_residual_inf_n"
                ]
            ),
            "active_frontier_structural_policy_shell_rotation_candidate_best_improvement_inf_n": (
                active_frontier_structural_policy_shell_rotation_row_candidate_summary[
                    "best_improvement_inf_n"
                ]
            ),
            "active_frontier_structural_policy_shell_rotation_candidate_checkpoint_path": (
                active_frontier_structural_policy_shell_rotation_row_candidate_summary[
                    "checkpoint_path"
                ]
            ),
            "active_frontier_structural_policy_shell_rotation_candidate_checkpoint_alpha": (
                active_frontier_structural_policy_shell_rotation_row_candidate_summary[
                    "checkpoint_best_alpha"
                ]
            ),
            "active_frontier_structural_policy_shell_rotation_no_descent_probe_best_improvement_inf_n": (
                active_frontier_structural_policy_shell_rotation_row_no_descent_summary[
                    "best_improvement_inf_n"
                ]
            ),
            "active_frontier_structural_policy_shell_rotation_no_descent_probe_descent_observed": (
                active_frontier_structural_policy_shell_rotation_row_no_descent_summary[
                    "direct_descent_observed"
                ]
            ),
            "active_frontier_structural_policy_shell_rotation_candidate_ownership_top_residual_inf_n": (
                active_frontier_structural_policy_shell_rotation_candidate_ownership_summary[
                    "top_residual_inf_n"
                ]
            ),
            "active_frontier_structural_policy_shell_rotation_candidate_ownership_top_row_dof_label": (
                active_frontier_structural_policy_shell_rotation_candidate_ownership_summary[
                    "top_row_dof_label"
                ]
            ),
            "active_frontier_structural_policy_shell_rotation_candidate_ownership_top_row_component": (
                active_frontier_structural_policy_shell_rotation_candidate_ownership_summary[
                    "top_row_dominant_internal_component"
                ]
            ),
            "active_frontier_structural_policy_shell_rotation_candidate_ownership_top_row_balance_driver": (
                active_frontier_structural_policy_shell_rotation_candidate_ownership_summary[
                    "top_row_balance_driver"
                ]
            ),
            "sparse_direct_scaled_lsmr_frontier_present": bool(
                sparse_direct_scaled_lsmr_frontier_probe
            ),
            "sparse_direct_scaled_lsmr_frontier_status": (
                sparse_direct_scaled_lsmr_frontier_summary["status"]
            ),
            "sparse_direct_scaled_lsmr_frontier_jvp_parity_pass": (
                sparse_direct_scaled_lsmr_frontier_summary["jvp_parity_pass"]
            ),
            "sparse_direct_scaled_lsmr_frontier_tangent_parity_pass": (
                sparse_direct_scaled_lsmr_frontier_summary[
                    "assembled_tangent_parity_pass"
                ]
            ),
            "sparse_direct_scaled_lsmr_frontier_direction_status": (
                sparse_direct_scaled_lsmr_frontier_summary["direction_status"]
            ),
            "sparse_direct_scaled_lsmr_frontier_direction_iterations": (
                sparse_direct_scaled_lsmr_frontier_summary["direction_iterations"]
            ),
            "sparse_direct_scaled_lsmr_frontier_line_search_status": (
                sparse_direct_scaled_lsmr_frontier_summary["line_search_status"]
            ),
            "sparse_direct_scaled_lsmr_frontier_line_search_residual_after_n": (
                sparse_direct_scaled_lsmr_frontier_summary[
                    "line_search_residual_after_n"
                ]
            ),
            "sparse_direct_scaled_lsmr_frontier_line_search_reduction_ratio": (
                sparse_direct_scaled_lsmr_frontier_summary[
                    "line_search_residual_reduction_ratio"
                ]
            ),
            "sparse_direct_scaled_lsmr_frontier_output_checkpoint_written": (
                sparse_direct_scaled_lsmr_frontier_summary[
                    "output_checkpoint_written"
                ]
            ),
            "sparse_direct_scaled_lsmr_frontier_output_checkpoint_path": (
                sparse_direct_scaled_lsmr_frontier_summary[
                    "output_checkpoint_path"
                ]
            ),
            "sparse_direct_scaled_lsmr_frontier_output_checkpoint_residual_n": (
                sparse_direct_scaled_lsmr_frontier_summary[
                    "output_checkpoint_direct_residual_inf_n"
                ]
            ),
            "sparse_direct_scaled_lsmr_frontier_output_checkpoint_residual_gate_passed": (
                sparse_direct_scaled_lsmr_frontier_summary[
                    "output_checkpoint_residual_gate_passed"
                ]
            ),
            "sparse_direct_scaled_lsmr_second_present": bool(
                sparse_direct_scaled_lsmr_second_probe
            ),
            "sparse_direct_scaled_lsmr_second_status": (
                sparse_direct_scaled_lsmr_second_summary["status"]
            ),
            "sparse_direct_scaled_lsmr_second_line_search_status": (
                sparse_direct_scaled_lsmr_second_summary["line_search_status"]
            ),
            "sparse_direct_scaled_lsmr_second_line_search_residual_after_n": (
                sparse_direct_scaled_lsmr_second_summary[
                    "line_search_residual_after_n"
                ]
            ),
            "sparse_direct_scaled_lsmr_second_line_search_reduction_ratio": (
                sparse_direct_scaled_lsmr_second_summary[
                    "line_search_residual_reduction_ratio"
                ]
            ),
            "sparse_direct_scaled_lsmr_second_output_checkpoint_written": (
                sparse_direct_scaled_lsmr_second_summary[
                    "output_checkpoint_written"
                ]
            ),
            "sparse_direct_scaled_lsmr_second_output_checkpoint_path": (
                sparse_direct_scaled_lsmr_second_summary["output_checkpoint_path"]
            ),
            "sparse_direct_scaled_lsmr_second_output_checkpoint_residual_n": (
                sparse_direct_scaled_lsmr_second_summary[
                    "output_checkpoint_direct_residual_inf_n"
                ]
            ),
            "sparse_direct_scaled_lsmr_second_output_checkpoint_residual_gate_passed": (
                sparse_direct_scaled_lsmr_second_summary[
                    "output_checkpoint_residual_gate_passed"
                ]
            ),
            "sparse_direct_scaled_lsmr_chain_step_count": (
                sparse_direct_scaled_lsmr_chain_summary["step_count"]
            ),
            "sparse_direct_scaled_lsmr_chain_ready_step_count": (
                sparse_direct_scaled_lsmr_chain_summary["ready_step_count"]
            ),
            "sparse_direct_scaled_lsmr_chain_monotonic_residual_descent": (
                sparse_direct_scaled_lsmr_chain_summary[
                    "monotonic_residual_descent"
                ]
            ),
            "sparse_direct_scaled_lsmr_chain_initial_residual_n": (
                sparse_direct_scaled_lsmr_chain_summary["initial_residual_n"]
            ),
            "sparse_direct_scaled_lsmr_chain_final_residual_n": (
                sparse_direct_scaled_lsmr_chain_summary["final_residual_n"]
            ),
            "sparse_direct_scaled_lsmr_chain_total_reduction_n": (
                sparse_direct_scaled_lsmr_chain_summary["total_reduction_n"]
            ),
            "sparse_direct_scaled_lsmr_chain_total_reduction_ratio": (
                sparse_direct_scaled_lsmr_chain_summary["total_reduction_ratio"]
            ),
            "sparse_direct_scaled_lsmr_chain_latest_checkpoint_path": (
                sparse_direct_scaled_lsmr_chain_summary["latest_checkpoint_path"]
            ),
            "sparse_direct_scaled_lsmr_chain_latest_checkpoint_residual_gate_passed": (
                sparse_direct_scaled_lsmr_chain_summary[
                    "latest_checkpoint_residual_gate_passed"
                ]
            ),
            "sparse_direct_scaled_lsmr_chain_probe_present": bool(
                sparse_direct_scaled_lsmr_chain_probe
            ),
            "sparse_direct_scaled_lsmr_chain_probe_status": (
                sparse_direct_scaled_lsmr_chain_probe_summary["status"]
            ),
            "sparse_direct_scaled_lsmr_chain_probe_step_count": (
                sparse_direct_scaled_lsmr_chain_probe_summary["step_count"]
            ),
            "sparse_direct_scaled_lsmr_chain_probe_monotonic_residual_descent": (
                sparse_direct_scaled_lsmr_chain_probe_summary[
                    "monotonic_residual_descent"
                ]
            ),
            "sparse_direct_scaled_lsmr_chain_probe_final_residual_n": (
                sparse_direct_scaled_lsmr_chain_probe_summary["final_residual_n"]
            ),
            "sparse_direct_scaled_lsmr_chain_probe_latest_checkpoint_path": (
                sparse_direct_scaled_lsmr_chain_probe_summary[
                    "latest_checkpoint_path"
                ]
            ),
            "sparse_direct_scaled_lsmr_long_chain_probe_present": bool(
                sparse_direct_scaled_lsmr_long_chain_probe
            ),
            "sparse_direct_scaled_lsmr_long_chain_probe_status": (
                sparse_direct_scaled_lsmr_long_chain_probe_summary["status"]
            ),
            "sparse_direct_scaled_lsmr_long_chain_probe_step_count": (
                sparse_direct_scaled_lsmr_long_chain_probe_summary["step_count"]
            ),
            "sparse_direct_scaled_lsmr_long_chain_probe_final_residual_n": (
                sparse_direct_scaled_lsmr_long_chain_probe_summary[
                    "final_residual_n"
                ]
            ),
            "sparse_direct_scaled_lsmr_long_chain_probe_total_reduction_ratio": (
                sparse_direct_scaled_lsmr_long_chain_probe_summary[
                    "total_reduction_ratio"
                ]
            ),
            "sparse_direct_scaled_lsmr_long_chain_probe_final_residual_over_gate": (
                sparse_direct_scaled_lsmr_long_chain_probe_summary[
                    "final_residual_over_gate"
                ]
            ),
            "sparse_direct_scaled_lsmr_long_chain_probe_estimated_steps_to_gate_at_last_reduction": (
                sparse_direct_scaled_lsmr_long_chain_probe_summary[
                    "estimated_steps_to_gate_at_last_reduction"
                ]
            ),
            "sparse_direct_scaled_lsmr_long_chain_probe_gate_convergence_assessment": (
                sparse_direct_scaled_lsmr_long_chain_probe_summary[
                    "gate_convergence_assessment"
                ]
            ),
            "sparse_direct_scaled_lsmr_long_chain_probe_recommended_next_action": (
                sparse_direct_scaled_lsmr_long_chain_probe_summary[
                    "recommended_next_action"
                ]
            ),
            "sparse_direct_scaled_lsmr_long_chain_probe_latest_checkpoint_path": (
                sparse_direct_scaled_lsmr_long_chain_probe_summary[
                    "latest_checkpoint_path"
                ]
            ),
            "sparse_direct_scaled_lsmr_long_chain_probe_latest_checkpoint_residual_gate_passed": (
                sparse_direct_scaled_lsmr_long_chain_probe_summary[
                    "latest_checkpoint_residual_gate_passed"
                ]
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_probe_present": bool(
                sparse_direct_scaled_lsmr_from_incomplete_preview_probe
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_probe_status": (
                sparse_direct_scaled_lsmr_from_incomplete_preview_summary["status"]
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_probe_line_search_residual_after_n": (
                sparse_direct_scaled_lsmr_from_incomplete_preview_summary[
                    "line_search_residual_after_n"
                ]
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_probe_line_search_reduction_ratio": (
                sparse_direct_scaled_lsmr_from_incomplete_preview_summary[
                    "line_search_residual_reduction_ratio"
                ]
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_probe_output_checkpoint_path": (
                sparse_direct_scaled_lsmr_from_incomplete_preview_summary[
                    "output_checkpoint_path"
                ]
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_probe_output_checkpoint_residual_n": (
                sparse_direct_scaled_lsmr_from_incomplete_preview_summary[
                    "output_checkpoint_direct_residual_inf_n"
                ]
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_probe_output_checkpoint_residual_gate_passed": (
                sparse_direct_scaled_lsmr_from_incomplete_preview_summary[
                    "output_checkpoint_residual_gate_passed"
                ]
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_present": bool(
                sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_status": (
                sparse_direct_scaled_lsmr_from_incomplete_preview_chain_summary[
                    "status"
                ]
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_step_count": (
                sparse_direct_scaled_lsmr_from_incomplete_preview_chain_summary[
                    "step_count"
                ]
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_final_residual_n": (
                sparse_direct_scaled_lsmr_from_incomplete_preview_chain_summary[
                    "final_residual_n"
                ]
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_total_reduction_ratio": (
                sparse_direct_scaled_lsmr_from_incomplete_preview_chain_summary[
                    "total_reduction_ratio"
                ]
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_final_residual_over_gate": (
                sparse_direct_scaled_lsmr_from_incomplete_preview_chain_summary[
                    "final_residual_over_gate"
                ]
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_estimated_steps_to_gate_at_last_reduction": (
                sparse_direct_scaled_lsmr_from_incomplete_preview_chain_summary[
                    "estimated_steps_to_gate_at_last_reduction"
                ]
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_gate_convergence_assessment": (
                sparse_direct_scaled_lsmr_from_incomplete_preview_chain_summary[
                    "gate_convergence_assessment"
                ]
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_recommended_next_action": (
                sparse_direct_scaled_lsmr_from_incomplete_preview_chain_summary[
                    "recommended_next_action"
                ]
            ),
            "sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_latest_checkpoint_path": (
                sparse_direct_scaled_lsmr_from_incomplete_preview_chain_summary[
                    "latest_checkpoint_path"
                ]
            ),
            "sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_present": bool(
                sparse_direct_shifted_splu_from_incomplete_preview_chain_probe
            ),
            "sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_status": (
                sparse_direct_shifted_splu_from_incomplete_preview_chain_summary[
                    "status"
                ]
            ),
            "sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_shift_mu": (
                sparse_direct_shifted_splu_from_incomplete_preview_chain_summary[
                    "shifted_operator_shift_mu"
                ]
            ),
            "sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_line_search_residual_after_n": (
                sparse_direct_shifted_splu_from_incomplete_preview_chain_summary[
                    "line_search_residual_after_n"
                ]
            ),
            "sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_output_checkpoint_residual_n": (
                sparse_direct_shifted_splu_from_incomplete_preview_chain_summary[
                    "output_checkpoint_direct_residual_inf_n"
                ]
            ),
            "sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_output_checkpoint_residual_gate_passed": (
                sparse_direct_shifted_splu_from_incomplete_preview_chain_summary[
                    "output_checkpoint_residual_gate_passed"
                ]
            ),
            "sparse_direct_shifted_splu_from_gate_candidate_step2_probe_present": bool(
                sparse_direct_shifted_splu_from_gate_candidate_step2_probe
            ),
            "sparse_direct_shifted_splu_from_gate_candidate_step2_probe_status": (
                sparse_direct_shifted_splu_from_gate_candidate_step2_summary[
                    "status"
                ]
            ),
            "sparse_direct_shifted_splu_from_gate_candidate_step2_probe_line_search_residual_after_n": (
                sparse_direct_shifted_splu_from_gate_candidate_step2_summary[
                    "line_search_residual_after_n"
                ]
            ),
            "sparse_direct_shifted_splu_from_gate_candidate_step2_probe_output_checkpoint_path": (
                sparse_direct_shifted_splu_from_gate_candidate_step2_summary[
                    "output_checkpoint_path"
                ]
            ),
            "sparse_direct_shifted_splu_from_gate_candidate_step2_probe_output_checkpoint_residual_n": (
                sparse_direct_shifted_splu_from_gate_candidate_step2_summary[
                    "output_checkpoint_direct_residual_inf_n"
                ]
            ),
            "sparse_direct_shifted_splu_from_gate_candidate_step2_probe_output_checkpoint_residual_gate_passed": (
                sparse_direct_shifted_splu_from_gate_candidate_step2_summary[
                    "output_checkpoint_residual_gate_passed"
                ]
            ),
            "sparse_direct_shifted_splu_from_gate_candidate_step2_probe_recommended_next_action": (
                sparse_direct_shifted_splu_from_gate_candidate_step2_summary[
                    "recommended_next_action"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_present": bool(
                sparse_direct_adaptive_jvp_eps_gmres_ilu_probe
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_status": (
                sparse_direct_adaptive_jvp_eps_gmres_ilu_summary["status"]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_reason_code": (
                sparse_direct_adaptive_jvp_eps_gmres_ilu_summary["reason_code"]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_jvp_eps": (
                sparse_direct_adaptive_jvp_eps_gmres_ilu_summary["jvp_eps"]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_jvp_parity_max_absolute_error_n": (
                sparse_direct_adaptive_jvp_eps_gmres_ilu_summary[
                    "jvp_parity_max_absolute_error_n"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_direction_status": (
                sparse_direct_adaptive_jvp_eps_gmres_ilu_summary[
                    "direction_status"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_recommended_next_action": (
                sparse_direct_adaptive_jvp_eps_gmres_ilu_summary[
                    "recommended_next_action"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_present": bool(
                sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_status": (
                sparse_direct_adaptive_jvp_eps_gmres_matrix_free_summary["status"]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_reason_code": (
                sparse_direct_adaptive_jvp_eps_gmres_matrix_free_summary[
                    "reason_code"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_jvp_eps": (
                sparse_direct_adaptive_jvp_eps_gmres_matrix_free_summary[
                    "jvp_eps"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_jvp_parity_max_absolute_error_n": (
                sparse_direct_adaptive_jvp_eps_gmres_matrix_free_summary[
                    "jvp_parity_max_absolute_error_n"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_direction_status": (
                sparse_direct_adaptive_jvp_eps_gmres_matrix_free_summary[
                    "direction_status"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_direction_residual_after_n": (
                sparse_direct_adaptive_jvp_eps_gmres_matrix_free_summary[
                    "direction_residual_after_n"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_present": bool(
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_status": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_summary["status"]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_reason_code": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_summary[
                    "reason_code"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_jvp_eps": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_summary[
                    "jvp_eps"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_preconditioner_shift_mu": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_summary[
                    "preconditioner_shift_mu"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_direction_residual_after_n": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_summary[
                    "direction_residual_after_n"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_direction_residual_reduction_ratio": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_summary[
                    "direction_residual_reduction_ratio"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_present": bool(
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_status": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_summary[
                    "status"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_reason_code": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_summary[
                    "reason_code"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_direction_status": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_summary[
                    "direction_status"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_direction_residual_after_n": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_summary[
                    "direction_residual_after_n"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_line_search_status": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_summary[
                    "line_search_status"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_line_search_residual_after_n": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_summary[
                    "line_search_residual_after_n"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_line_search_residual_reduction_ratio": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_summary[
                    "line_search_residual_reduction_ratio"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_incomplete_direction_preview": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_summary[
                    "incomplete_direction_preview"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_output_checkpoint_written": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_summary[
                    "output_checkpoint_written"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_output_checkpoint_path": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_summary[
                    "output_checkpoint_path"
                ]
            ),
            "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_output_checkpoint_residual_n": (
                sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_summary[
                    "output_checkpoint_direct_residual_inf_n"
                ]
            ),
            "adaptive_all_components_frontier_present": bool(
                adaptive_all_components_frontier
            ),
            "adaptive_all_components_frontier_final_residual_n": (
                adaptive_all_components_frontier_summary["final_residual_n"]
            ),
            "adaptive_all_components_frontier_residual_gate_passed": (
                adaptive_all_components_frontier_summary["residual_gate_passed"]
            ),
            "adaptive_all_components_frontier_checkpoint_path": (
                adaptive_all_components_frontier_summary["checkpoint_path"]
            ),
            "shell_hotspot_tangent_fd_jvp_present": bool(
                shell_hotspot_tangent_fd_jvp_probe
            ),
            "shell_hotspot_tangent_fd_jvp_fd_consistent": (
                shell_hotspot_tangent_fd_jvp_summary["fd_consistent"]
            ),
            "shell_hotspot_tangent_fd_jvp_max_relative_inf_error": (
                shell_hotspot_tangent_fd_jvp_summary["max_relative_inf_error"]
            ),
            "shell_hotspot_tangent_fd_jvp_evaluated_row_count": (
                shell_hotspot_tangent_fd_jvp_summary["evaluated_row_count"]
            ),
            "shell_hotspot_diagonal_sweep_present": bool(
                shell_hotspot_diagonal_sweep_probe
            ),
            "shell_hotspot_diagonal_sweep_descent_observed": (
                shell_hotspot_diagonal_sweep_summary["descent_observed"]
            ),
            "shell_hotspot_diagonal_sweep_best_residual_n": (
                shell_hotspot_diagonal_sweep_summary[
                    "best_direct_residual_inf_n"
                ]
            ),
            "shell_hotspot_diagonal_sweep_best_improvement_n": (
                shell_hotspot_diagonal_sweep_summary["best_improvement_inf_n"]
            ),
            "global_tangent_scaled_sweep_present": bool(
                global_tangent_scaled_sweep_probe
            ),
            "global_tangent_scaled_sweep_descent_observed": (
                global_tangent_scaled_sweep_summary["descent_observed"]
            ),
            "global_tangent_scaled_sweep_best_residual_n": (
                global_tangent_scaled_sweep_summary[
                    "best_direct_residual_inf_n"
                ]
            ),
            "global_tangent_scaled_sweep_best_improvement_n": (
                global_tangent_scaled_sweep_summary["best_improvement_inf_n"]
            ),
            "global_tangent_scaled_sweep_linear_relative_residual": (
                global_tangent_scaled_sweep_summary[
                    "linear_relative_residual_inf"
                ]
            ),
            "residual_norm_gradient_tiny_sweep_present": bool(
                residual_norm_gradient_tiny_sweep_probe
            ),
            "residual_norm_gradient_tiny_sweep_inf_descent_observed": (
                residual_norm_gradient_tiny_sweep_summary[
                    "inf_descent_observed"
                ]
            ),
            "residual_norm_gradient_tiny_sweep_l2_descent_observed": (
                residual_norm_gradient_tiny_sweep_summary["l2_descent_observed"]
            ),
            "residual_norm_gradient_tiny_sweep_best_l2_residual_n": (
                residual_norm_gradient_tiny_sweep_summary[
                    "best_l2_direct_residual_l2_n"
                ]
            ),
            "residual_norm_gradient_tiny_sweep_best_l2_improvement_n": (
                residual_norm_gradient_tiny_sweep_summary[
                    "best_l2_improvement_l2_n"
                ]
            ),
            "active_set_ls_sweep_present": bool(active_set_ls_sweep_probe),
            "active_set_ls_sweep_full_inf_descent_observed": (
                active_set_ls_sweep_summary["full_inf_descent_observed"]
            ),
            "active_set_ls_sweep_active_inf_descent_observed": (
                active_set_ls_sweep_summary["active_inf_descent_observed"]
            ),
            "active_set_ls_sweep_best_full_residual_n": (
                active_set_ls_sweep_summary["best_full_direct_residual_inf_n"]
            ),
            "active_set_ls_sweep_best_full_improvement_n": (
                active_set_ls_sweep_summary["best_full_improvement_inf_n"]
            ),
            "active_set_ls_trust_candidate_present": bool(
                active_set_ls_trust_candidate
            ),
            "active_set_ls_trust_candidate_checkpoint_written": (
                active_set_ls_trust_candidate_summary["checkpoint_written"]
            ),
            "active_set_ls_trust_candidate_final_residual_n": (
                active_set_ls_trust_candidate_summary["final_residual_n"]
            ),
            "active_set_ls_trust_candidate_total_reduction_n": (
                active_set_ls_trust_candidate_summary["total_reduction_n"]
            ),
            "active_set_ls_trust_candidate_residual_gate_passed": (
                active_set_ls_trust_candidate_summary["residual_gate_passed"]
            ),
            "active_set_ls_trust_candidate_checkpoint_path": (
                active_set_ls_trust_candidate_summary["checkpoint_path"]
            ),
            "active_set_ls_trust_schedule_candidate_present": bool(
                active_set_ls_trust_schedule_candidate
            ),
            "active_set_ls_trust_schedule_candidate_final_residual_n": (
                active_set_ls_trust_schedule_candidate_summary["final_residual_n"]
            ),
            "active_set_ls_trust_schedule_candidate_total_reduction_n": (
                active_set_ls_trust_schedule_candidate_summary["total_reduction_n"]
            ),
            "active_set_ls_trust_schedule_candidate_residual_gate_passed": (
                active_set_ls_trust_schedule_candidate_summary["residual_gate_passed"]
            ),
            "active_set_ls_trust_schedule_candidate_active_row_count_schedule": (
                active_set_ls_trust_schedule_candidate_summary[
                    "active_row_count_schedule"
                ]
            ),
            "active_set_ls_trust_tangent_fd_jvp_present": bool(
                active_set_ls_trust_tangent_fd_jvp_probe
            ),
            "active_set_ls_trust_tangent_fd_jvp_fd_consistent": (
                active_set_ls_trust_tangent_fd_jvp_summary["fd_consistent"]
            ),
            "active_set_ls_trust_tangent_fd_jvp_max_relative_inf_error": (
                active_set_ls_trust_tangent_fd_jvp_summary[
                    "max_relative_inf_error"
                ]
            ),
            "active_set_ls_trust_tangent_fd_jvp_max_relative_l2_error": (
                active_set_ls_trust_tangent_fd_jvp_summary["max_relative_l2_error"]
            ),
            "active_set_ls_trust_tangent_fd_jvp_evaluated_row_count": (
                active_set_ls_trust_tangent_fd_jvp_summary["evaluated_row_count"]
            ),
            "active_set_minimax_trust_candidate_present": bool(
                active_set_minimax_trust_candidate
            ),
            "active_set_minimax_trust_candidate_final_residual_n": (
                active_set_minimax_trust_candidate_summary["final_residual_n"]
            ),
            "active_set_minimax_trust_candidate_total_reduction_n": (
                active_set_minimax_trust_candidate_summary["total_reduction_n"]
            ),
            "active_set_minimax_trust_candidate_residual_gate_passed": (
                active_set_minimax_trust_candidate_summary["residual_gate_passed"]
            ),
            "active_set_minimax_trust_candidate_steps_taken": (
                active_set_minimax_trust_candidate_summary["steps_taken"]
            ),
            "active_set_minimax_trust_candidate_best_linear_active_inf_improvement_n": (
                active_set_minimax_trust_candidate_summary[
                    "best_linear_active_inf_improvement_n"
                ]
            ),
            "full_load_true_newton_attempted": true_newton_load_sweep_summary[
                "full_load_attempted"
            ],
            "full_load_true_newton_residual_descent_observed": (
                true_newton_load_sweep_summary[
                    "full_load_true_newton_residual_descent_observed"
                ]
            ),
            "full_load_true_newton_residual_gate_passed": (
                true_newton_load_sweep_summary[
                    "full_load_true_newton_residual_gate_passed"
                ]
            ),
            "full_load_true_newton_final_residual_n": (
                true_newton_load_sweep_summary[
                    "full_load_true_newton_final_residual_n"
                ]
            ),
            "assembly_contract_seed_ready": assembly_contract_seed.get("contract_pass")
            is True,
            "assembly_contract_cpu_seed_newton_gate_passed": assembly_contract_seed.get(
                "cpu_seed_consistent_newton_gate_passed"
            )
            is True,
            "cpu_live_g1_assembly_contract_present": (
                cpu_live_assembly_contract_probe_summary["present"]
            ),
            "cpu_live_g1_assembly_contract_passed": (
                cpu_live_assembly_contract_probe_summary["contract_pass"]
            ),
            "cpu_live_g1_assembly_contract_residual_inf_n": (
                cpu_live_assembly_contract_probe_summary["residual_inf_n"]
            ),
            "live_g1_assembly_contract_present": _live_assembly_contract_summary(
                hip_probe
            )["present"],
            "live_g1_assembly_contract_passed": _live_assembly_contract_summary(
                hip_probe
            )["contract_pass"],
            "contract_blocker_count": len(contract_blockers),
            "closure_blocker_count": len(closure_blockers),
            "residual_jvp_worker_path_ready": worker.get(
                "residual_jvp_worker_path_ready"
            )
            is True,
            "worker_path_repair_blocker_count": worker_path_repair_plan[
                "blocker_count"
            ],
            "worker_path_repair_category_count": worker_path_repair_plan[
                "category_count"
            ],
            "worker_path_repair_next_action_id": worker_path_repair_plan[
                "next_action_id"
            ],
            "worker_path_operator_sequence_count": len(worker_path_operator_sequence),
            "g1_closure_gate_ready": worker.get("g1_closure_gate_ready") is True,
            "consistent_residual_jacobian_newton_gate_passed": hip_probe.get(
                "consistent_residual_jacobian_newton_gate_passed"
            )
            is True,
            "hip_required_full_load_residual_jvp_frontier_present": bool(
                hip_required_full_load_residual_jvp_frontier_probe
            ),
            "hip_required_full_load_residual_jvp_frontier_final_residual_n": (
                hip_required_full_load_residual_jvp_frontier_summary[
                    "final_direct_residual_inf_n"
                ]
            ),
            "hip_required_full_load_residual_jvp_frontier_residual_gate": (
                hip_required_full_load_residual_jvp_frontier_summary[
                    "direct_residual_gate_passed"
                ]
            ),
            "hip_required_full_load_residual_jvp_frontier_global_krylov_hip_solver": (
                hip_required_full_load_residual_jvp_frontier_summary[
                    "matrix_free_global_krylov_hip_solver_used"
                ]
            ),
            "hip_required_full_load_residual_jvp_frontier_hip_components_passed": (
                hip_required_full_load_residual_jvp_frontier_summary[
                    "hip_required_components_passed"
                ]
            ),
            "hip_required_consistency_direct_probe_final_residual_n": (
                hip_required_consistency_direct_probe_summary[
                    "final_direct_residual_inf_n"
                ]
            ),
            "hip_required_consistency_direct_probe_residual_gate": (
                hip_required_consistency_direct_probe_summary[
                    "direct_residual_gate_passed"
                ]
            ),
            "hip_required_consistency_direct_probe_worker_path_ready": (
                hip_required_consistency_direct_probe_summary[
                    "residual_jvp_worker_path_ready"
                ]
            ),
            "hip_required_consistency_direct_probe_jvp_rows_retained": (
                hip_required_consistency_direct_probe_summary[
                    "matrix_free_global_krylov_jvp_rows_retained"
                ]
            ),
            "hip_required_consistency_direct_probe_output_checkpoint_written": (
                hip_required_consistency_direct_probe_summary[
                    "output_checkpoint_written"
                ]
            ),
            "hip_required_frontier_no_descent_receipt_count": sum(
                1
                for receipt in hip_required_frontier_no_descent_receipts
                if receipt.get("present") is True
            ),
            "hip_required_frontier_no_descent_all_no_descent": all(
                receipt.get("no_descent") is True
                for receipt in hip_required_frontier_no_descent_receipts
                if receipt.get("present") is True
            ),
            "hip_required_scaled_global_krylov_no_descent_final_residual_n": (
                hip_required_frontier_no_descent_receipts[1][
                    "final_direct_residual_inf_n"
                ]
            ),
            "hip_required_scaled_global_krylov_no_descent_best_residual_n": (
                hip_required_frontier_no_descent_receipts[1][
                    "matrix_free_global_krylov_best_residual_inf_n"
                ]
            ),
            "hip_required_scaled_global_krylov_no_descent_output_written": (
                hip_required_frontier_no_descent_receipts[1][
                    "output_checkpoint_written"
                ]
            ),
            "current_frontier_operator_mismatch_audit_complete": (
                current_frontier_operator_mismatch_audit.get("audit_complete") is True
            ),
            "current_frontier_full_load_no_descent": _as_dict(
                current_frontier_operator_mismatch_audit.get("frontier_probe")
            ).get("full_load_no_descent")
            is True,
            "current_frontier_operator_family_no_descent": _as_dict(
                current_frontier_operator_mismatch_audit.get("current_frontier_no_descent")
            ).get("global_and_row_operator_family_no_descent")
            is True,
            "current_frontier_scaled_global_krylov_best_residual_n": _as_float(
                _as_dict(
                    _as_dict(
                        current_frontier_operator_mismatch_audit.get(
                            "current_frontier_no_descent"
                        )
                    ).get("scaled_global_krylov")
                ).get("best_direct_residual_inf_n")
            ),
            "current_frontier_row_correction_best_residual_n": _as_float(
                _as_dict(
                    _as_dict(
                        current_frontier_operator_mismatch_audit.get(
                            "current_frontier_no_descent"
                        )
                    ).get("current_tangent_residual_row_correction")
                ).get("best_direct_residual_inf_n")
            ),
            "current_frontier_next_required_operator": str(
                _as_dict(
                    current_frontier_operator_mismatch_audit.get(
                        "operator_mismatch_summary"
                    )
                ).get("next_required_operator")
                or ""
            ),
            "phase2_material_newton_breadth_seed_coverage_ready": (
                phase2_material_newton_breadth_summary.get(
                    "state_updated_material_newton_breadth_seed_coverage_ready"
                )
                is True
            ),
            "phase2_state_updated_material_seed_case_count": int(
                _as_float(
                    phase2_material_newton_breadth_summary.get(
                        "state_updated_material_newton_seed_case_count"
                    )
                )
            ),
            "phase2_state_updated_material_jvp_pass": (
                phase2_material_newton_breadth_summary.get(
                    "material_jvp_relative_error_pass"
                )
                is True
            ),
            "phase2_state_updated_material_replay_pass": (
                phase2_material_newton_breadth_summary.get(
                    "material_state_persistence_replay_seed_passed"
                )
                is True
            ),
            "phase2_state_updated_material_breadth_closed": (
                phase2_material_newton_breadth_summary.get(
                    "state_updated_material_newton_breadth_closed"
                )
                is True
            ),
            "row_only_correction_loop_stopped": _row_only_loop_stopped(
                cause_narrowing,
                action,
            ),
            "support_or_link_row_gap_disfavored": _support_or_link_gap_disfavored(
                cause_narrowing,
                action,
            ),
            "next_action_ids": [str(row["id"]) for row in next_actions],
        },
        "runner_contract": {
            "runner_id": RUNNER_ID,
            "preferred_candidate_generator": PREFERRED_GENERATOR,
            "primary_next_lane": PRIMARY_NEXT_LANE,
            "required_checkpoint_schema": CHECKPOINT_SCHEMA,
            "required_load_scale": required_load_scale,
            "disallowed_retry_action_ids": list(DISALLOWED_RETRY_ACTION_IDS),
            "required_inputs": [
                g1_lane_path.as_posix(),
                cause_narrowing_path.as_posix(),
                hip_probe_path.as_posix(),
                global_connectivity_path.as_posix(),
                assembly_contract_seed_path.as_posix(),
                true_newton_load_sweep_path.as_posix(),
                true_newton_full_load_checkpoint_candidate_path.as_posix(),
                true_newton_from_active_set_ls_trust_candidate_path.as_posix(),
                (
                    true_newton_from_active_set_service_tangent_ls_trust_candidate_path
                    .as_posix()
                ),
                adaptive_all_components_frontier_path.as_posix(),
                shell_hotspot_tangent_fd_jvp_probe_path.as_posix(),
                shell_hotspot_diagonal_sweep_probe_path.as_posix(),
                global_tangent_scaled_sweep_probe_path.as_posix(),
                residual_norm_gradient_tiny_sweep_probe_path.as_posix(),
                active_set_ls_sweep_probe_path.as_posix(),
                active_set_ls_trust_candidate_path.as_posix(),
                active_set_ls_trust_schedule_candidate_path.as_posix(),
                active_set_ls_trust_tangent_fd_jvp_probe_path.as_posix(),
                active_set_minimax_trust_candidate_path.as_posix(),
                frame_tangent_fd_epsilon_sweep_probe_path.as_posix(),
                true_newton_from_active_set_mu_sweep_probe_path.as_posix(),
                active_set_load_parameter_probe_path.as_posix(),
                active_set_load_parameter_tiny_trust_probe_path.as_posix(),
                active_frontier_residual_ownership_probe_path.as_posix(),
                active_frontier_shell_load_neighborhood_probe_path.as_posix(),
                active_frontier_shell_policy_replay_probe_path.as_posix(),
                active_frontier_shell_policy_linearized_active_set_probe_path.as_posix(),
                (
                    active_frontier_structural_policy_active_set_ls_trust_candidate_path
                    .as_posix()
                ),
                (
                    active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_path
                    .as_posix()
                ),
                (
                    active_frontier_structural_policy_active_set_direct_material_replay_probe_path
                    .as_posix()
                ),
                (
                    active_frontier_structural_policy_active_set_current_component_row_correction_probe_path
                    .as_posix()
                ),
                (
                    active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe_path
                    .as_posix()
                ),
                (
                    active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe_path
                    .as_posix()
                ),
                active_frontier_structural_policy_residual_ownership_probe_path.as_posix(),
                (
                    active_frontier_structural_policy_linearized_active_set_after_two_step_probe_path
                    .as_posix()
                ),
                active_frontier_structural_policy_shell_rotation_row_candidate_path.as_posix(),
                active_frontier_structural_policy_shell_rotation_row_no_descent_probe_path.as_posix(),
                (
                    active_frontier_structural_policy_shell_rotation_candidate_ownership_probe_path
                    .as_posix()
                ),
                sparse_direct_scaled_lsmr_frontier_probe_path.as_posix(),
            ],
            "acceptance_criteria": [
                "g1_assembly_contract_seed_report_contract_passes",
                "cpu_seed_direct_residual_newton_parity_passes",
                "live_g1_runner_uses_assembly_result_residual_jacobian_contract",
                "loadable_checkpoint_schema_mgt_direct_residual_newton_state_v1",
                "checkpoint_load_scale_gte_1p0",
                "no_load_path_provenance_contradiction",
                "direct_residual_gate_passes_without_regularized_fixed_point_substitute",
                "consistent_residual_jacobian_newton_gate_passes",
                "production_rocm_hip_residual_jvp_worker_has_no_cpu_fallback",
                "device_resident_residual_jvp_rows_retained",
                "g1_full_load_hip_newton_lane_report_contract_passes_after_rerun",
            ],
            "prohibited_substitutes": [
                "row_only_largest_rows_retuning_replay",
                "support_or_elastic_link_pin_without_cause_receipt",
                "regularized_fixed_point_residual_used_as_physical_residual",
                "cpu_diagnostic_assembler_or_cpu_fallback_hip_claim",
                "full_load_claim_from_sub_full_load_checkpoint",
            ],
            "rerun_command": (
                action.get("rerun_command")
                or "python3 scripts/run_g1_full_load_hip_newton_lane.py "
                "--checkpoint-npz <full-load-checkpoint.npz> --fail-blocked"
            ),
        },
        "routing_evidence": {
            "runner_next_action_present": bool(action),
            "routing_reason": str(action.get("reason") or action.get("routing_reason") or ""),
            "preferred_candidate_generator": str(
                action.get("preferred_candidate_generator") or ""
            ),
            "cause_narrowing_primary_next_lane": _cause_primary_next_lane(
                cause_narrowing,
                action,
            ),
            "row_only_correction_loop_stopped": _row_only_loop_stopped(
                cause_narrowing,
                action,
            ),
            "support_or_link_row_gap_disfavored": _support_or_link_gap_disfavored(
                cause_narrowing,
                action,
            ),
            "suppressed_retry_action_ids": _strings(
                action.get("suppressed_retry_action_ids")
            ),
            "global_connectivity_status": str(global_connectivity.get("status") or ""),
            "cause_narrowing_status": str(cause_narrowing.get("status") or ""),
        },
        "checkpoint_gap": {
            "checkpoint_resolution_passed": checkpoint_gate.get("passed") is True,
            "required_load_scale": required_load_scale,
            "highest_observed_load_scale": highest_observed,
            "highest_observed_gap_to_required_load_scale": _as_float(
                checkpoint_gate.get("highest_observed_gap_to_required_load_scale")
                or action.get("highest_observed_gap_to_required_load_scale")
            ),
            "full_load_candidate_count": _as_int(
                checkpoint_gate.get("full_load_candidate_count")
                or action.get("workspace_full_load_candidate_count")
            ),
            "workspace_candidate_count": _as_int(action.get("workspace_candidate_count")),
            "workspace_scan_root": str(action.get("workspace_scan_root") or ""),
        },
        "true_newton_load_sweep": true_newton_load_sweep_summary,
        "true_newton_full_load_checkpoint_candidate": (
            true_newton_full_load_checkpoint_candidate_summary
        ),
        "true_newton_from_active_set_ls_trust_candidate": (
            true_newton_from_active_set_ls_trust_candidate_summary
        ),
        "true_newton_from_active_set_service_tangent_ls_trust_candidate": (
            true_newton_from_active_set_service_tangent_ls_trust_candidate_summary
        ),
        "true_newton_frame_tangent_source_comparison": (
            true_newton_frame_tangent_source_comparison
        ),
        "adaptive_all_components_frontier": adaptive_all_components_frontier_summary,
        "shell_hotspot_tangent_fd_jvp": shell_hotspot_tangent_fd_jvp_summary,
        "shell_hotspot_diagonal_sweep": shell_hotspot_diagonal_sweep_summary,
        "global_tangent_scaled_sweep": global_tangent_scaled_sweep_summary,
        "residual_norm_gradient_tiny_sweep": (
            residual_norm_gradient_tiny_sweep_summary
        ),
        "active_set_ls_sweep": active_set_ls_sweep_summary,
        "active_set_ls_trust_candidate": active_set_ls_trust_candidate_summary,
        "active_set_ls_trust_schedule_candidate": (
            active_set_ls_trust_schedule_candidate_summary
        ),
        "active_set_ls_trust_tangent_fd_jvp": (
            active_set_ls_trust_tangent_fd_jvp_summary
        ),
        "active_set_minimax_trust_candidate": (
            active_set_minimax_trust_candidate_summary
        ),
        "frame_tangent_fd_epsilon_sweep": (
            frame_tangent_fd_epsilon_sweep_summary
        ),
        "true_newton_from_active_set_mu_sweep": (
            true_newton_from_active_set_mu_sweep_summary
        ),
        "active_set_load_parameter_probe": active_set_load_parameter_summary,
        "active_set_load_parameter_tiny_trust_probe": (
            active_set_load_parameter_tiny_trust_summary
        ),
        "active_frontier_residual_ownership_probe": (
            active_frontier_residual_ownership_summary
        ),
        "active_frontier_shell_load_neighborhood_probe": (
            active_frontier_shell_load_neighborhood_summary
        ),
        "active_frontier_shell_policy_replay_probe": (
            active_frontier_shell_policy_replay_summary
        ),
        "active_frontier_shell_policy_linearized_active_set_probe": (
            active_frontier_shell_policy_linearized_active_set_summary
        ),
        "active_frontier_structural_policy_active_set_ls_trust_candidate": (
            active_frontier_structural_policy_active_set_ls_trust_candidate_summary
        ),
        "active_frontier_structural_policy_active_set_ls_trust_alpha_sweep": (
            active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_summary
        ),
        "active_frontier_structural_policy_active_set_state_updated_direct_replay_probe": (
            active_frontier_structural_policy_active_set_direct_material_replay_summary
        ),
        "active_frontier_structural_policy_active_set_current_component_row_correction_probe": (
            active_frontier_structural_policy_active_set_current_component_row_correction_summary
        ),
        "active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe": (
            active_frontier_structural_policy_active_set_current_component_row_correction_step2_summary
        ),
        "active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe": (
            active_frontier_structural_policy_active_set_current_component_row_correction_step3_summary
        ),
        "active_frontier_structural_policy_active_set_current_component_row_correction_chain": (
            active_frontier_structural_policy_active_set_current_component_row_correction_chain_summary
        ),
        "active_frontier_structural_policy_residual_ownership_probe": (
            active_frontier_structural_policy_residual_ownership_summary
        ),
        "active_frontier_structural_policy_linearized_active_set_after_two_step_probe": (
            active_frontier_structural_policy_linearized_after_two_step_summary
        ),
        "active_frontier_structural_policy_shell_rotation_row_candidate": (
            active_frontier_structural_policy_shell_rotation_row_candidate_summary
        ),
        "active_frontier_structural_policy_shell_rotation_row_no_descent_probe": (
            active_frontier_structural_policy_shell_rotation_row_no_descent_summary
        ),
        "active_frontier_structural_policy_shell_rotation_candidate_residual_ownership_probe": (
            active_frontier_structural_policy_shell_rotation_candidate_ownership_summary
        ),
        "sparse_direct_scaled_lsmr_frontier_probe": (
            sparse_direct_scaled_lsmr_frontier_summary
        ),
        "sparse_direct_scaled_lsmr_second_probe": (
            sparse_direct_scaled_lsmr_second_summary
        ),
        "sparse_direct_scaled_lsmr_third_probe": (
            sparse_direct_scaled_lsmr_third_summary
        ),
        "sparse_direct_scaled_lsmr_chain": (
            sparse_direct_scaled_lsmr_chain_summary
        ),
        "sparse_direct_scaled_lsmr_chain_probe": (
            sparse_direct_scaled_lsmr_chain_probe_summary
        ),
        "sparse_direct_scaled_lsmr_long_chain_probe": (
            sparse_direct_scaled_lsmr_long_chain_probe_summary
        ),
        "sparse_direct_scaled_lsmr_from_incomplete_preview_probe": (
            sparse_direct_scaled_lsmr_from_incomplete_preview_summary
        ),
        "sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe": (
            sparse_direct_scaled_lsmr_from_incomplete_preview_chain_summary
        ),
        "sparse_direct_shifted_splu_from_incomplete_preview_chain_probe": (
            sparse_direct_shifted_splu_from_incomplete_preview_chain_summary
        ),
        "sparse_direct_shifted_splu_from_gate_candidate_step2_probe": (
            sparse_direct_shifted_splu_from_gate_candidate_step2_summary
        ),
        "sparse_direct_adaptive_jvp_eps_gmres_ilu_probe": (
            sparse_direct_adaptive_jvp_eps_gmres_ilu_summary
        ),
        "sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe": (
            sparse_direct_adaptive_jvp_eps_gmres_matrix_free_summary
        ),
        "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe": (
            sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_summary
        ),
        "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe": (
            sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_summary
        ),
        "hip_required_full_load_residual_jvp_frontier": (
            hip_required_full_load_residual_jvp_frontier_summary
        ),
        "hip_required_consistency_direct_probe": (
            hip_required_consistency_direct_probe_summary
        ),
        "cpu_live_g1_assembly_contract_probe": (
            cpu_live_assembly_contract_probe_summary
        ),
        "hip_required_frontier_no_descent_receipts": (
            hip_required_frontier_no_descent_receipts
        ),
        "current_frontier_operator_mismatch_audit": (
            current_frontier_operator_mismatch_audit
        ),
        "phase2_material_newton_breadth_summary": (
            phase2_material_newton_breadth_summary
        ),
        "phase2_material_newton_breadth_state_updated_seeds": (
            phase2_material_newton_breadth_state_updated_seeds
        ),
        "hip_worker_contract": {
            "worker_id": str(worker.get("worker_id") or ""),
            "residual_jvp_worker_path_ready": worker.get(
                "residual_jvp_worker_path_ready"
            )
            is True,
            "g1_closure_gate_ready": worker.get("g1_closure_gate_ready") is True,
            "consistent_residual_jacobian_newton_gate_passed": hip_probe.get(
                "consistent_residual_jacobian_newton_gate_passed"
            )
            is True,
            "cpu_diagnostic_assembler_used": hip_probe.get(
                "cpu_diagnostic_assembler_used"
            )
            is True,
            "production_hip_residual_jacobian_path": hip_probe.get(
                "production_hip_residual_jacobian_path"
            )
            is True,
            "terminal_gate_partition": terminal_partition,
            "worker_blockers": _strings(worker.get("blockers")),
            "worker_path_blockers": _strings(
                worker.get("residual_jvp_worker_path_blockers")
            ),
            "worker_path_repair_plan": worker_path_repair_plan,
        },
        "assembly_contract_seed": {
            "path": assembly_contract_seed_path.as_posix(),
            "status": str(assembly_contract_seed.get("status") or ""),
            "contract_pass": assembly_contract_seed.get("contract_pass") is True,
            "promotes_g1_closure": assembly_contract_seed.get("promotes_g1_closure")
            is True,
            "phase_covered": str(assembly_contract_seed.get("phase_covered") or ""),
            "residual_formula": str(assembly_contract_seed.get("residual_formula") or ""),
            "fixed_point_residual_promoted_to_physical": assembly_contract_seed.get(
                "fixed_point_residual_promoted_to_physical"
            )
            is True,
            "regularized_fixed_point_substitute": assembly_contract_seed.get(
                "regularized_fixed_point_substitute"
            )
            is True,
            "cpu_seed_consistent_newton_gate_passed": assembly_contract_seed.get(
                "cpu_seed_consistent_newton_gate_passed"
            )
            is True,
            "consistent_residual_jacobian_newton_gate_passed": assembly_contract_seed.get(
                "consistent_residual_jacobian_newton_gate_passed"
            )
            is True,
            "case_count": _as_int(assembly_contract_seed.get("case_count")),
        },
        "live_g1_assembly_contract": _live_assembly_contract_summary(hip_probe),
        "worker_path_repair_plan": worker_path_repair_plan,
        "worker_path_operator_sequence": worker_path_operator_sequence,
        "verification_commands": [
            (
                "python3 scripts/build_g1_assembly_contract_seed_report.py --check"
            ),
            (
                "python3 scripts/run_g1_full_load_hip_newton_lane.py "
                "--checkpoint-npz <full-load-checkpoint.npz> --fail-blocked"
            ),
            (
                "python3 scripts/build_g1_consistent_newton_full_load_checkpoint_candidate_runner.py "
                "--fail-blocked"
            ),
            "python3 scripts/build_structural_product_development_roadmap.py",
        ],
        "next_actions": next_actions,
        "blockers": contract_blockers,
        "closure_blockers": closure_blockers,
        "artifacts": {
            "g1_full_load_hip_newton_lane_report": g1_lane_path.as_posix(),
            "g1_f2g_f2h_cause_narrowing_status": cause_narrowing_path.as_posix(),
            "mgt_residual_jacobian_consistency_hip_required_probe": hip_probe_path.as_posix(),
            "g1_global_connectivity_load_path_audit": global_connectivity_path.as_posix(),
            "g1_assembly_contract_seed_report": assembly_contract_seed_path.as_posix(),
            "g1_true_newton_load_sweep_status": true_newton_load_sweep_path.as_posix(),
            "g1_true_newton_full_load_checkpoint_candidate_status": (
                true_newton_full_load_checkpoint_candidate_path.as_posix()
            ),
            "g1_true_newton_from_active_set_ls_trust_candidate": (
                true_newton_from_active_set_ls_trust_candidate_path.as_posix()
            ),
            "g1_adaptive_all_components_frontier": (
                adaptive_all_components_frontier_path.as_posix()
            ),
            "g1_shell_hotspot_tangent_fd_jvp_probe": (
                shell_hotspot_tangent_fd_jvp_probe_path.as_posix()
            ),
            "g1_shell_hotspot_diagonal_sweep_probe": (
                shell_hotspot_diagonal_sweep_probe_path.as_posix()
            ),
            "g1_global_tangent_scaled_sweep_probe": (
                global_tangent_scaled_sweep_probe_path.as_posix()
            ),
            "g1_residual_norm_gradient_tiny_sweep_probe": (
                residual_norm_gradient_tiny_sweep_probe_path.as_posix()
            ),
            "g1_active_set_ls_sweep_probe": active_set_ls_sweep_probe_path.as_posix(),
            "g1_active_set_ls_trust_candidate": (
                active_set_ls_trust_candidate_path.as_posix()
            ),
            "g1_active_set_ls_trust_schedule_candidate": (
                active_set_ls_trust_schedule_candidate_path.as_posix()
            ),
            "g1_active_set_ls_trust_tangent_fd_jvp_probe": (
                active_set_ls_trust_tangent_fd_jvp_probe_path.as_posix()
            ),
            "g1_active_set_minimax_trust_candidate": (
                active_set_minimax_trust_candidate_path.as_posix()
            ),
            "g1_active_frontier_residual_ownership_probe": (
                active_frontier_residual_ownership_probe_path.as_posix()
            ),
            "g1_active_frontier_shell_load_neighborhood_probe": (
                active_frontier_shell_load_neighborhood_probe_path.as_posix()
            ),
            "g1_active_frontier_shell_policy_replay_probe": (
                active_frontier_shell_policy_replay_probe_path.as_posix()
            ),
            "g1_active_frontier_shell_policy_linearized_active_set_probe": (
                active_frontier_shell_policy_linearized_active_set_probe_path.as_posix()
            ),
            "g1_active_frontier_structural_policy_active_set_ls_trust_candidate": (
                active_frontier_structural_policy_active_set_ls_trust_candidate_path
                .as_posix()
            ),
            "g1_active_frontier_structural_policy_active_set_ls_trust_alpha_sweep": (
                active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_path
                .as_posix()
            ),
            "g1_active_frontier_structural_policy_active_set_state_updated_direct_replay_probe": (
                active_frontier_structural_policy_active_set_direct_material_replay_probe_path
                .as_posix()
            ),
            "g1_active_frontier_structural_policy_active_set_current_component_row_correction_probe": (
                active_frontier_structural_policy_active_set_current_component_row_correction_probe_path
                .as_posix()
            ),
            "g1_active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe": (
                active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe_path
                .as_posix()
            ),
            "g1_active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe": (
                active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe_path
                .as_posix()
            ),
            "g1_active_frontier_structural_policy_residual_ownership_probe": (
                active_frontier_structural_policy_residual_ownership_probe_path.as_posix()
            ),
            "g1_active_frontier_structural_policy_linearized_active_set_after_two_step_probe": (
                active_frontier_structural_policy_linearized_active_set_after_two_step_probe_path
                .as_posix()
            ),
            "g1_active_frontier_structural_policy_shell_rotation_row_candidate": (
                active_frontier_structural_policy_shell_rotation_row_candidate_path.as_posix()
            ),
            "g1_active_frontier_structural_policy_shell_rotation_row_no_descent_probe": (
                active_frontier_structural_policy_shell_rotation_row_no_descent_probe_path
                .as_posix()
            ),
            "g1_active_frontier_structural_policy_shell_rotation_candidate_residual_ownership_probe": (
                active_frontier_structural_policy_shell_rotation_candidate_ownership_probe_path
                .as_posix()
            ),
            "g1_mgt_sparse_direct_scaled_lsmr_from_shell_rotation_frontier_probe": (
                sparse_direct_scaled_lsmr_frontier_probe_path.as_posix()
            ),
            "g1_mgt_sparse_direct_scaled_lsmr_from_shell_rotation_frontier_candidate": (
                DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FRONTIER_CANDIDATE.as_posix()
            ),
            "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_second_probe": (
                sparse_direct_scaled_lsmr_second_probe_path.as_posix()
            ),
            "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_second_candidate": (
                DEFAULT_SPARSE_DIRECT_SCALED_LSMR_SECOND_CANDIDATE.as_posix()
            ),
            "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_third_probe": (
                sparse_direct_scaled_lsmr_third_probe_path.as_posix()
            ),
            "g1_mgt_sparse_direct_scaled_lsmr_from_sparse_frontier_third_candidate": (
                DEFAULT_SPARSE_DIRECT_SCALED_LSMR_THIRD_CANDIDATE.as_posix()
            ),
            "g1_mgt_sparse_direct_scaled_lsmr_chain_probe": (
                sparse_direct_scaled_lsmr_chain_probe_path.as_posix()
            ),
            "g1_mgt_sparse_direct_scaled_lsmr_long_chain_probe": (
                sparse_direct_scaled_lsmr_long_chain_probe_path.as_posix()
            ),
            "mgt_residual_jacobian_step14_material_active_set_ls_rows32_child_direct_saved_probe": (
                hip_required_full_load_residual_jvp_frontier_probe_path.as_posix()
            ),
            "mgt_residual_jacobian_step14_material_active_set_ls_rows32_child_direct_candidate": (
                hip_required_full_load_residual_jvp_frontier_candidate_path.as_posix()
            ),
            "mgt_residual_jacobian_step15_material_active_set_ls_rows32_child_direct_candidate": (
                hip_required_consistency_direct_checkpoint_path.as_posix()
            ),
            "mgt_residual_jacobian_step16_material_active_set_ls_rows32_child_direct_no_descent_probe": (
                hip_required_consistency_no_descent_probe_path.as_posix()
            ),
            "mgt_residual_jacobian_step16_scaled_global_krylov_direct_probe": (
                hip_required_scaled_global_krylov_no_descent_probe_path.as_posix()
            ),
            "g1_current_frontier_operator_mismatch_audit": (
                current_frontier_operator_mismatch_audit_path.as_posix()
            ),
            "phase2_material_newton_breadth_summary": (
                phase2_material_newton_breadth_summary_path.as_posix()
            ),
            "phase2_material_newton_breadth_state_updated_seeds": (
                phase2_material_newton_breadth_state_updated_seeds_path.as_posix()
            ),
        },
        "claim_boundary": (
            "This packet defines the next G1 runner contract for generating a "
            "consistent residual/Jacobian Newton full-load checkpoint candidate. "
            "It does not create the checkpoint, close the consistent Newton gate, "
            "prove full-load 1.0 equilibrium, promote G1 closure, or allow an "
            "exhausted row-only support/link retuning loop to count as progress."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    contract = _as_dict(payload.get("runner_contract"))
    checkpoint = _as_dict(payload.get("checkpoint_gap"))
    true_newton = _as_dict(payload.get("true_newton_load_sweep"))
    true_newton_checkpoint = _as_dict(
        payload.get("true_newton_full_load_checkpoint_candidate")
    )
    true_newton_from_active = _as_dict(
        payload.get("true_newton_from_active_set_ls_trust_candidate")
    )
    true_newton_service_tangent = _as_dict(
        payload.get("true_newton_from_active_set_service_tangent_ls_trust_candidate")
    )
    frame_tangent_comparison = _as_dict(
        payload.get("true_newton_frame_tangent_source_comparison")
    )
    adaptive_frontier = _as_dict(payload.get("adaptive_all_components_frontier"))
    shell_jvp = _as_dict(payload.get("shell_hotspot_tangent_fd_jvp"))
    shell_diag = _as_dict(payload.get("shell_hotspot_diagonal_sweep"))
    global_tangent = _as_dict(payload.get("global_tangent_scaled_sweep"))
    residual_gradient = _as_dict(payload.get("residual_norm_gradient_tiny_sweep"))
    active_set = _as_dict(payload.get("active_set_ls_sweep"))
    active_set_candidate = _as_dict(payload.get("active_set_ls_trust_candidate"))
    active_set_schedule = _as_dict(
        payload.get("active_set_ls_trust_schedule_candidate")
    )
    active_set_tangent_jvp = _as_dict(
        payload.get("active_set_ls_trust_tangent_fd_jvp")
    )
    active_set_minimax = _as_dict(
        payload.get("active_set_minimax_trust_candidate")
    )
    hip_required_frontier = _as_dict(
        payload.get("hip_required_full_load_residual_jvp_frontier")
    )
    hip_required_consistency_direct = _as_dict(
        payload.get("hip_required_consistency_direct_probe")
    )
    hip_required_no_descent_receipts = [
        _as_dict(item)
        for item in _as_list(payload.get("hip_required_frontier_no_descent_receipts"))
        if isinstance(item, dict)
    ]
    current_frontier_operator_mismatch = _as_dict(
        payload.get("current_frontier_operator_mismatch_audit")
    )
    material_breadth = _as_dict(payload.get("phase2_material_newton_breadth_summary"))
    material_seed_suite = _as_dict(
        payload.get("phase2_material_newton_breadth_state_updated_seeds")
    )
    frame_eps_sweep = _as_dict(payload.get("frame_tangent_fd_epsilon_sweep"))
    mu_sweep = _as_dict(payload.get("true_newton_from_active_set_mu_sweep"))
    load_param = _as_dict(payload.get("active_set_load_parameter_probe"))
    load_param_tiny = _as_dict(
        payload.get("active_set_load_parameter_tiny_trust_probe")
    )
    residual_ownership = _as_dict(
        payload.get("active_frontier_residual_ownership_probe")
    )
    shell_neighborhood = _as_dict(
        payload.get("active_frontier_shell_load_neighborhood_probe")
    )
    shell_policy = _as_dict(
        payload.get("active_frontier_shell_policy_replay_probe")
    )
    shell_policy_linearized = _as_dict(
        payload.get("active_frontier_shell_policy_linearized_active_set_probe")
    )
    structural_policy_active_set = _as_dict(
        payload.get("active_frontier_structural_policy_active_set_ls_trust_candidate")
    )
    structural_policy_alpha_sweep = _as_dict(
        payload.get("active_frontier_structural_policy_active_set_ls_trust_alpha_sweep")
    )
    structural_policy_direct_replay = _as_dict(
        payload.get(
            "active_frontier_structural_policy_active_set_state_updated_direct_replay_probe"
        )
    )
    structural_policy_component_row = _as_dict(
        payload.get(
            "active_frontier_structural_policy_active_set_current_component_row_correction_probe"
        )
    )
    structural_policy_component_row_step2 = _as_dict(
        payload.get(
            "active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe"
        )
    )
    structural_policy_component_row_step3 = _as_dict(
        payload.get(
            "active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe"
        )
    )
    structural_policy_component_row_chain = _as_dict(
        payload.get(
            "active_frontier_structural_policy_active_set_current_component_row_correction_chain"
        )
    )
    structural_policy_ownership = _as_dict(
        payload.get("active_frontier_structural_policy_residual_ownership_probe")
    )
    structural_policy_linearized_after = _as_dict(
        payload.get(
            "active_frontier_structural_policy_linearized_active_set_after_two_step_probe"
        )
    )
    shell_rotation_candidate = _as_dict(
        payload.get("active_frontier_structural_policy_shell_rotation_row_candidate")
    )
    shell_rotation_no_descent = _as_dict(
        payload.get("active_frontier_structural_policy_shell_rotation_row_no_descent_probe")
    )
    shell_rotation_candidate_ownership = _as_dict(
        payload.get(
            "active_frontier_structural_policy_shell_rotation_candidate_residual_ownership_probe"
        )
    )
    sparse_scaled_lsmr = _as_dict(
        payload.get("sparse_direct_scaled_lsmr_frontier_probe")
    )
    sparse_scaled_lsmr_second = _as_dict(
        payload.get("sparse_direct_scaled_lsmr_second_probe")
    )
    sparse_scaled_lsmr_chain = _as_dict(
        payload.get("sparse_direct_scaled_lsmr_chain")
    )
    sparse_scaled_lsmr_chain_probe = _as_dict(
        payload.get("sparse_direct_scaled_lsmr_chain_probe")
    )
    sparse_scaled_lsmr_long_chain_probe = _as_dict(
        payload.get("sparse_direct_scaled_lsmr_long_chain_probe")
    )
    sparse_scaled_lsmr_from_incomplete_preview = _as_dict(
        payload.get("sparse_direct_scaled_lsmr_from_incomplete_preview_probe")
    )
    sparse_scaled_lsmr_from_incomplete_preview_chain = _as_dict(
        payload.get("sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe")
    )
    shifted_splu_from_incomplete_preview_chain = _as_dict(
        payload.get("sparse_direct_shifted_splu_from_incomplete_preview_chain_probe")
    )
    shifted_splu_from_gate_step2 = _as_dict(
        payload.get("sparse_direct_shifted_splu_from_gate_candidate_step2_probe")
    )
    hip = _as_dict(payload.get("hip_worker_contract"))
    assembly = _as_dict(payload.get("assembly_contract_seed"))
    lines = [
        "# G1 Consistent Newton Full-Load Runner Contract",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `evidence_closure_pass`: `{payload['evidence_closure_pass']}`",
        f"- `runner_id`: `{contract.get('runner_id')}`",
        f"- `preferred_candidate_generator`: `{contract.get('preferred_candidate_generator')}`",
        f"- `observed_load`: `{checkpoint.get('highest_observed_load_scale')}`",
        f"- `required_load_scale`: `{checkpoint.get('required_load_scale')}`",
        f"- `true_newton_full_load_descent`: `{true_newton.get('full_load_true_newton_residual_descent_observed')}`",
        f"- `true_newton_full_load_gate`: `{true_newton.get('full_load_true_newton_residual_gate_passed')}`",
        f"- `true_newton_full_load_final_residual_n`: `{true_newton.get('full_load_true_newton_final_residual_n')}`",
        f"- `true_newton_checkpoint_candidate_written`: `{true_newton_checkpoint.get('checkpoint_written')}`",
        f"- `true_newton_checkpoint_candidate_residual_n`: `{true_newton_checkpoint.get('checkpoint_direct_residual_inf_n')}`",
        f"- `true_newton_from_active_set_final_residual_n`: `{true_newton_from_active.get('true_final_residual_n')}`",
        f"- `true_newton_from_active_set_stop_reason`: `{true_newton_from_active.get('true_stop_reason')}`",
        f"- `true_newton_from_active_set_max_jvp_gap_relative_inf`: `{true_newton_from_active.get('max_jvp_minus_unregularized_tangent_action_relative_inf')}`",
        f"- `true_newton_service_tangent_max_jvp_gap_relative_inf`: `{true_newton_service_tangent.get('max_jvp_minus_unregularized_tangent_action_relative_inf')}`",
        f"- `true_newton_frame_tangent_comparison_both_frame_gap`: `{frame_tangent_comparison.get('both_dominant_gap_component_frame')}`",
        f"- `frame_tangent_fd_epsilon_sweep_default_gap_relative_inf`: `{frame_eps_sweep.get('default_eps_gap_relative_inf')}`",
        f"- `frame_tangent_fd_epsilon_sweep_best_gap_relative_inf`: `{frame_eps_sweep.get('best_eps_gap_relative_inf')}`",
        f"- `frame_tangent_fd_epsilon_sweep_default_eps_artifact_likely`: `{frame_eps_sweep.get('default_eps_artifact_likely')}`",
        f"- `true_newton_mu_sweep_descent_observed`: `{mu_sweep.get('descent_observed')}`",
        f"- `true_newton_mu_sweep_best_mu`: `{mu_sweep.get('best_mu')}`",
        f"- `true_newton_mu_sweep_best_improvement_inf_n`: `{mu_sweep.get('best_improvement_inf_n')}`",
        f"- `load_parameter_probe_descent_observed`: `{load_param.get('actual_replay_descent_observed')}`",
        f"- `load_parameter_tiny_trust_descent_observed`: `{load_param_tiny.get('actual_replay_descent_observed')}`",
        f"- `load_parameter_tiny_trust_best_load_scale`: `{load_param_tiny.get('best_actual_replay_load_scale')}`",
        f"- `load_parameter_tiny_trust_restored_full_load_descent`: `{load_param_tiny.get('restored_full_load_descent_observed')}`",
        f"- `active_frontier_residual_ownership_top_row_balance_driver`: `{residual_ownership.get('top_row_balance_driver')}`",
        f"- `active_frontier_residual_ownership_top_row_component`: `{residual_ownership.get('top_row_dominant_internal_component')}`",
        f"- `active_frontier_residual_ownership_top_row_external_load_n`: `{residual_ownership.get('top_row_inferred_external_load_n')}`",
        f"- `active_frontier_shell_load_required_scale`: `{shell_neighborhood.get('top_row_required_reference_shell_load_scale_for_zero_row_residual')}`",
        f"- `active_frontier_shell_load_free_pressure_resultant`: `{shell_neighborhood.get('top_row_surface_component_free_pressure_resultant')}`",
        f"- `active_frontier_shell_load_top_element_id`: `{shell_neighborhood.get('top_incident_element_id')}`",
        f"- `active_frontier_shell_policy_best_policy`: `{shell_policy.get('best_policy')}`",
        f"- `active_frontier_shell_policy_best_residual_n`: `{shell_policy.get('best_residual_inf_n')}`",
        f"- `active_frontier_shell_policy_descent_observed`: `{shell_policy.get('structural_or_attached_policy_descent_observed')}`",
        f"- `active_frontier_shell_policy_linearized_best_after_n`: `{shell_policy_linearized.get('best_linear_active_residual_after_inf_n')}`",
        f"- `active_frontier_shell_policy_linearized_direct_replay_required`: `{shell_policy_linearized.get('direct_replay_required_for_candidate')}`",
        f"- `active_frontier_structural_policy_active_set_final_residual_n`: `{structural_policy_active_set.get('final_residual_n')}`",
        f"- `active_frontier_structural_policy_active_set_alpha_sweep_stop`: `{structural_policy_alpha_sweep.get('stop_reason')}`",
        f"- `active_frontier_structural_policy_active_set_state_updated_direct_replay_residual_n`: `{structural_policy_direct_replay.get('state_updated_material_direct_residual_inf_n')}`",
        f"- `active_frontier_structural_policy_active_set_state_updated_direct_replay_gate`: `{structural_policy_direct_replay.get('direct_residual_gate_passed')}`",
        f"- `active_frontier_structural_policy_active_set_state_updated_direct_replay_top_component`: `{structural_policy_direct_replay.get('top_row_dominant_component')}`",
        f"- `active_frontier_structural_policy_active_set_current_component_row_correction_final_residual_n`: `{structural_policy_component_row.get('final_direct_residual_inf_n')}`",
        f"- `active_frontier_structural_policy_active_set_current_component_row_correction_improvement_n`: `{structural_policy_component_row.get('improvement_inf_n')}`",
        f"- `active_frontier_structural_policy_active_set_current_component_row_correction_step2_final_residual_n`: `{structural_policy_component_row_step2.get('final_direct_residual_inf_n')}`",
        f"- `active_frontier_structural_policy_active_set_current_component_row_correction_step2_improvement_n`: `{structural_policy_component_row_step2.get('improvement_inf_n')}`",
        f"- `active_frontier_structural_policy_active_set_current_component_row_correction_chain_latest_residual_n`: `{structural_policy_component_row_chain.get('latest_accepted_final_residual_inf_n')}`",
        f"- `active_frontier_structural_policy_active_set_current_component_row_correction_chain_no_descent_stop`: `{structural_policy_component_row_chain.get('first_no_descent_stop_reason')}`",
        f"- `active_frontier_structural_policy_top_component`: `{structural_policy_ownership.get('top_row_dominant_internal_component')}`",
        f"- `active_frontier_structural_policy_top_balance_driver`: `{structural_policy_ownership.get('top_row_balance_driver')}`",
        f"- `active_frontier_shell_rotation_candidate_residual_n`: `{shell_rotation_candidate.get('best_direct_residual_inf_n')}`",
        f"- `active_frontier_shell_rotation_no_descent`: `{shell_rotation_no_descent.get('direct_descent_observed')}`",
        f"- `adaptive_all_components_frontier_final_residual_n`: `{adaptive_frontier.get('final_residual_n')}`",
        f"- `adaptive_all_components_frontier_gate`: `{adaptive_frontier.get('residual_gate_passed')}`",
        f"- `shell_hotspot_tangent_fd_jvp_consistent`: `{shell_jvp.get('fd_consistent')}`",
        f"- `shell_hotspot_diagonal_sweep_descent`: `{shell_diag.get('descent_observed')}`",
        f"- `global_tangent_scaled_sweep_descent`: `{global_tangent.get('descent_observed')}`",
        f"- `residual_norm_gradient_l2_descent`: `{residual_gradient.get('l2_descent_observed')}`",
        f"- `residual_norm_gradient_inf_descent`: `{residual_gradient.get('inf_descent_observed')}`",
        f"- `active_set_ls_full_inf_descent`: `{active_set.get('full_inf_descent_observed')}`",
        f"- `active_set_ls_best_full_residual_n`: `{active_set.get('best_full_direct_residual_inf_n')}`",
        f"- `active_set_ls_trust_candidate_final_residual_n`: `{active_set_candidate.get('final_residual_n')}`",
        f"- `active_set_ls_trust_candidate_gate`: `{active_set_candidate.get('residual_gate_passed')}`",
        f"- `active_set_ls_schedule_final_residual_n`: `{active_set_schedule.get('final_residual_n')}`",
        f"- `active_set_ls_tangent_fd_jvp_consistent`: `{active_set_tangent_jvp.get('fd_consistent')}`",
        f"- `active_set_ls_tangent_fd_jvp_max_relative_inf_error`: `{active_set_tangent_jvp.get('max_relative_inf_error')}`",
        f"- `active_set_minimax_final_residual_n`: `{active_set_minimax.get('final_residual_n')}`",
        f"- `active_set_minimax_steps_taken`: `{active_set_minimax.get('steps_taken')}`",
        f"- `hip_required_full_load_residual_jvp_frontier_final_residual_n`: `{hip_required_frontier.get('final_direct_residual_inf_n')}`",
        f"- `hip_required_full_load_residual_jvp_frontier_residual_gate`: `{hip_required_frontier.get('direct_residual_gate_passed')}`",
        f"- `hip_required_full_load_residual_jvp_frontier_global_krylov_hip_solver`: `{hip_required_frontier.get('matrix_free_global_krylov_hip_solver_used')}`",
        f"- `hip_required_full_load_residual_jvp_frontier_hip_components_passed`: `{hip_required_frontier.get('hip_required_components_passed')}`",
        f"- `hip_required_consistency_direct_probe_final_residual_n`: `{hip_required_consistency_direct.get('final_direct_residual_inf_n')}`",
        f"- `hip_required_consistency_direct_probe_worker_path_ready`: `{hip_required_consistency_direct.get('residual_jvp_worker_path_ready')}`",
        f"- `hip_required_consistency_direct_probe_jvp_rows_retained`: `{hip_required_consistency_direct.get('matrix_free_global_krylov_jvp_rows_retained')}`",
        f"- `hip_required_consistency_direct_probe_output_checkpoint_written`: `{hip_required_consistency_direct.get('output_checkpoint_written')}`",
        f"- `hip_required_frontier_no_descent_receipt_count`: `{sum(1 for receipt in hip_required_no_descent_receipts if receipt.get('present') is True)}`",
        f"- `hip_required_frontier_no_descent_all_no_descent`: `{all(receipt.get('no_descent') is True for receipt in hip_required_no_descent_receipts if receipt.get('present') is True) if hip_required_no_descent_receipts else False}`",
        f"- `current_frontier_operator_mismatch_audit_complete`: `{current_frontier_operator_mismatch.get('audit_complete')}`",
        f"- `current_frontier_full_load_no_descent`: `{_as_dict(current_frontier_operator_mismatch.get('frontier_probe')).get('full_load_no_descent')}`",
        f"- `current_frontier_operator_family_no_descent`: `{_as_dict(current_frontier_operator_mismatch.get('current_frontier_no_descent')).get('global_and_row_operator_family_no_descent')}`",
        "- `phase2_material_newton_breadth_seed_coverage_ready`: "
        f"`{material_breadth.get('state_updated_material_newton_breadth_seed_coverage_ready')}`",
        "- `phase2_state_updated_material_seed_case_count`: "
        f"`{material_breadth.get('state_updated_material_newton_seed_case_count')}`",
        "- `phase2_state_updated_material_breadth_closed`: "
        f"`{material_breadth.get('state_updated_material_newton_breadth_closed')}`",
        f"- `worker_path_ready`: `{hip.get('residual_jvp_worker_path_ready')}`",
        f"- `worker_g1_closure_gate_ready`: `{hip.get('g1_closure_gate_ready')}`",
        f"- `assembly_contract_seed_ready`: `{assembly.get('contract_pass')}`",
        f"- `cpu_seed_newton_parity`: `{assembly.get('cpu_seed_consistent_newton_gate_passed')}`",
        "",
        "## Acceptance Criteria",
        "",
    ]
    for item in _as_list(contract.get("acceptance_criteria")):
        lines.append(f"- `{item}`")
    if true_newton:
        lines.extend(["", "## True-Newton Load Sweep", ""])
        lines.append(f"- `present`: `{true_newton.get('present')}`")
        lines.append(f"- `status`: `{true_newton.get('status')}`")
        lines.append(
            f"- `max_attempted_load_scale`: `{true_newton.get('max_attempted_load_scale')}`"
        )
        lines.append(
            "- `full_load_true_newton_residual_descent_observed`: "
            f"`{true_newton.get('full_load_true_newton_residual_descent_observed')}`"
        )
        lines.append(
            "- `full_load_true_newton_residual_gate_passed`: "
            f"`{true_newton.get('full_load_true_newton_residual_gate_passed')}`"
        )
    if true_newton_checkpoint:
        lines.extend(["", "## True-Newton Checkpoint Candidate", ""])
        lines.append(f"- `present`: `{true_newton_checkpoint.get('present')}`")
        lines.append(f"- `status`: `{true_newton_checkpoint.get('status')}`")
        lines.append(
            f"- `checkpoint_written`: `{true_newton_checkpoint.get('checkpoint_written')}`"
        )
        lines.append(
            f"- `checkpoint_path`: `{true_newton_checkpoint.get('checkpoint_path')}`"
        )
        lines.append(
            "- `checkpoint_direct_residual_inf_n`: "
            f"`{true_newton_checkpoint.get('checkpoint_direct_residual_inf_n')}`"
        )
    if true_newton_from_active:
        lines.extend(["", "## True-Newton From Active-Set Frontier", ""])
        lines.append(f"- `present`: `{true_newton_from_active.get('present')}`")
        lines.append(f"- `status`: `{true_newton_from_active.get('status')}`")
        lines.append(
            f"- `stop_reason`: `{true_newton_from_active.get('true_stop_reason')}`"
        )
        lines.append(
            "- `true_final_residual_n`: "
            f"`{true_newton_from_active.get('true_final_residual_n')}`"
        )
        lines.append(
            "- `max_jvp_minus_unregularized_tangent_action_relative_inf`: "
            f"`{true_newton_from_active.get('max_jvp_minus_unregularized_tangent_action_relative_inf')}`"
        )
        lines.append(
            "- `dominant_jvp_gap_component`: "
            f"`{true_newton_from_active.get('dominant_jvp_gap_component')}`"
        )
    if true_newton_service_tangent:
        lines.extend(["", "## True-Newton Service-Tangent From Active-Set Frontier", ""])
        lines.append(f"- `present`: `{true_newton_service_tangent.get('present')}`")
        lines.append(f"- `status`: `{true_newton_service_tangent.get('status')}`")
        lines.append(
            f"- `stop_reason`: `{true_newton_service_tangent.get('true_stop_reason')}`"
        )
        lines.append(
            "- `true_final_residual_n`: "
            f"`{true_newton_service_tangent.get('true_final_residual_n')}`"
        )
        lines.append(
            "- `max_jvp_minus_unregularized_tangent_action_relative_inf`: "
            f"`{true_newton_service_tangent.get('max_jvp_minus_unregularized_tangent_action_relative_inf')}`"
        )
        lines.append(
            "- `dominant_jvp_gap_component`: "
            f"`{true_newton_service_tangent.get('dominant_jvp_gap_component')}`"
        )
    if frame_tangent_comparison:
        lines.extend(["", "## Frame Tangent Source Comparison", ""])
        lines.append(f"- `present`: `{frame_tangent_comparison.get('present')}`")
        lines.append(
            "- `both_line_search_no_descent`: "
            f"`{frame_tangent_comparison.get('both_line_search_no_descent')}`"
        )
        lines.append(
            "- `both_dominant_gap_component_frame`: "
            f"`{frame_tangent_comparison.get('both_dominant_gap_component_frame')}`"
        )
        lines.append(
            "- `service_minus_force_max_jvp_gap_relative_inf`: "
            f"`{frame_tangent_comparison.get('service_minus_force_max_jvp_gap_relative_inf')}`"
        )
    if frame_eps_sweep:
        lines.extend(["", "## Frame Tangent FD Epsilon Sweep", ""])
        lines.append(f"- `present`: `{frame_eps_sweep.get('present')}`")
        lines.append(f"- `default_jvp_eps`: `{frame_eps_sweep.get('default_jvp_eps')}`")
        lines.append(
            "- `default_eps_gap_relative_inf`: "
            f"`{frame_eps_sweep.get('default_eps_gap_relative_inf')}`"
        )
        lines.append(f"- `best_eps`: `{frame_eps_sweep.get('best_eps')}`")
        lines.append(
            "- `best_eps_gap_relative_inf`: "
            f"`{frame_eps_sweep.get('best_eps_gap_relative_inf')}`"
        )
        lines.append(
            "- `default_eps_artifact_likely`: "
            f"`{frame_eps_sweep.get('default_eps_artifact_likely')}`"
        )
    if mu_sweep:
        lines.extend(["", "## True-Newton Mu Sweep From Active-Set Frontier", ""])
        lines.append(f"- `present`: `{mu_sweep.get('present')}`")
        lines.append(
            f"- `evaluated_mu_count`: `{mu_sweep.get('evaluated_mu_count')}`"
        )
        lines.append(
            f"- `factorable_mu_count`: `{mu_sweep.get('factorable_mu_count')}`"
        )
        lines.append(f"- `descent_observed`: `{mu_sweep.get('descent_observed')}`")
        lines.append(f"- `best_mu`: `{mu_sweep.get('best_mu')}`")
        lines.append(
            f"- `best_residual_inf_n`: `{mu_sweep.get('best_residual_inf_n')}`"
        )
        lines.append(
            f"- `best_improvement_inf_n`: `{mu_sweep.get('best_improvement_inf_n')}`"
        )
    if load_param:
        lines.extend(["", "## Active-Set Load-Parameter Probe", ""])
        lines.append(f"- `present`: `{load_param.get('present')}`")
        lines.append(
            "- `actual_replay_descent_observed`: "
            f"`{load_param.get('actual_replay_descent_observed')}`"
        )
        lines.append(
            "- `best_actual_replay_load_scale`: "
            f"`{load_param.get('best_actual_replay_load_scale')}`"
        )
        lines.append(
            "- `best_actual_replay_residual_inf_n`: "
            f"`{load_param.get('best_actual_replay_residual_inf_n')}`"
        )
        lines.append(
            "- `best_actual_replay_improvement_inf_n`: "
            f"`{load_param.get('best_actual_replay_improvement_inf_n')}`"
        )
        lines.append(
            "- `restored_full_load_descent_observed`: "
            f"`{load_param.get('restored_full_load_descent_observed')}`"
        )
        lines.append(
            "- `best_restored_full_load_residual_inf_n`: "
            f"`{load_param.get('best_restored_full_load_residual_inf_n')}`"
        )
    if load_param_tiny:
        lines.extend(["", "## Active-Set Load-Parameter Tiny-Trust Probe", ""])
        lines.append(f"- `present`: `{load_param_tiny.get('present')}`")
        lines.append(
            "- `actual_replay_descent_observed`: "
            f"`{load_param_tiny.get('actual_replay_descent_observed')}`"
        )
        lines.append(
            "- `best_actual_replay_load_scale`: "
            f"`{load_param_tiny.get('best_actual_replay_load_scale')}`"
        )
        lines.append(
            "- `best_actual_replay_residual_inf_n`: "
            f"`{load_param_tiny.get('best_actual_replay_residual_inf_n')}`"
        )
        lines.append(
            "- `best_actual_replay_improvement_inf_n`: "
            f"`{load_param_tiny.get('best_actual_replay_improvement_inf_n')}`"
        )
        lines.append(
            "- `restored_full_load_descent_observed`: "
            f"`{load_param_tiny.get('restored_full_load_descent_observed')}`"
        )
        lines.append(
            "- `best_restored_full_load_residual_inf_n`: "
            f"`{load_param_tiny.get('best_restored_full_load_residual_inf_n')}`"
        )
    if residual_ownership:
        lines.extend(["", "## Active Frontier Residual Ownership", ""])
        lines.append(f"- `present`: `{residual_ownership.get('present')}`")
        lines.append(
            f"- `top_residual_inf_n`: `{residual_ownership.get('top_residual_inf_n')}`"
        )
        lines.append(
            f"- `top_row_node_id`: `{residual_ownership.get('top_row_node_id')}`"
        )
        lines.append(
            f"- `top_row_dof_label`: `{residual_ownership.get('top_row_dof_label')}`"
        )
        lines.append(
            "- `top_row_dominant_internal_component`: "
            f"`{residual_ownership.get('top_row_dominant_internal_component')}`"
        )
        lines.append(
            "- `top_row_balance_driver`: "
            f"`{residual_ownership.get('top_row_balance_driver')}`"
        )
        lines.append(
            "- `top_row_inferred_external_load_n`: "
            f"`{residual_ownership.get('top_row_inferred_external_load_n')}`"
        )
        lines.append(
            "- `top_row_load_derivative_n_per_load`: "
            f"`{residual_ownership.get('top_row_load_derivative_n_per_load')}`"
        )
    if shell_neighborhood:
        lines.extend(["", "## Active Frontier Shell Load Neighborhood", ""])
        lines.append(f"- `present`: `{shell_neighborhood.get('present')}`")
        lines.append(
            "- `top_row_required_reference_shell_load_scale_for_zero_row_residual`: "
            f"`{shell_neighborhood.get('top_row_required_reference_shell_load_scale_for_zero_row_residual')}`"
        )
        lines.append(
            "- `top_row_shell_internal_to_reference_load_scale`: "
            f"`{shell_neighborhood.get('top_row_shell_internal_to_reference_load_scale')}`"
        )
        lines.append(
            "- `top_row_surface_component_free_pressure_resultant`: "
            f"`{shell_neighborhood.get('top_row_surface_component_free_pressure_resultant')}`"
        )
        lines.append(
            "- `top_row_incident_surface_element_count`: "
            f"`{shell_neighborhood.get('top_row_incident_surface_element_count')}`"
        )
        lines.append(
            "- `top_row_surface_component_frame_connected_node_count`: "
            f"`{shell_neighborhood.get('top_row_surface_component_frame_connected_node_count')}`"
        )
        lines.append(
            "- `top_incident_element_id`: "
            f"`{shell_neighborhood.get('top_incident_element_id')}`"
        )
    if shell_policy:
        lines.extend(["", "## Active Frontier Shell Policy Replay", ""])
        lines.append(f"- `present`: `{shell_policy.get('present')}`")
        lines.append(f"- `baseline_policy`: `{shell_policy.get('baseline_policy')}`")
        lines.append(
            "- `baseline_residual_inf_n`: "
            f"`{shell_policy.get('baseline_residual_inf_n')}`"
        )
        lines.append(f"- `best_policy`: `{shell_policy.get('best_policy')}`")
        lines.append(
            "- `best_residual_inf_n`: "
            f"`{shell_policy.get('best_residual_inf_n')}`"
        )
        lines.append(
            "- `best_improvement_inf_n`: "
            f"`{shell_policy.get('best_improvement_inf_n')}`"
        )
        lines.append(
            "- `structural_or_attached_policy_descent_observed`: "
            f"`{shell_policy.get('structural_or_attached_policy_descent_observed')}`"
        )
        lines.append(
            "- `best_policy_pressure_suppressed_surface_element_count`: "
            f"`{shell_policy.get('best_policy_pressure_suppressed_surface_element_count')}`"
        )
        lines.append(
            "- `best_residual_gate_passed`: "
            f"`{shell_policy.get('best_residual_gate_passed')}`"
        )
    if shell_policy_linearized:
        lines.extend(["", "## Active Frontier Shell Policy Linearized Active-Set", ""])
        lines.append(f"- `present`: `{shell_policy_linearized.get('present')}`")
        lines.append(
            "- `shell_pressure_load_path_policy`: "
            f"`{shell_policy_linearized.get('shell_pressure_load_path_policy')}`"
        )
        lines.append(
            "- `base_residual_inf_n`: "
            f"`{shell_policy_linearized.get('base_residual_inf_n')}`"
        )
        lines.append(
            "- `best_active_row_count`: "
            f"`{shell_policy_linearized.get('best_active_row_count')}`"
        )
        lines.append(
            "- `best_linear_active_residual_after_inf_n`: "
            f"`{shell_policy_linearized.get('best_linear_active_residual_after_inf_n')}`"
        )
        lines.append(
            "- `best_linear_active_improvement_inf_n`: "
            f"`{shell_policy_linearized.get('best_linear_active_improvement_inf_n')}`"
        )
        lines.append(
            "- `linearized_active_descent_observed`: "
            f"`{shell_policy_linearized.get('linearized_active_descent_observed')}`"
        )
        lines.append(
            "- `direct_replay_required_for_candidate`: "
            f"`{shell_policy_linearized.get('direct_replay_required_for_candidate')}`"
        )
    if structural_policy_active_set:
        lines.extend(["", "## Active Frontier Structural Policy Active-Set LS Trust", ""])
        lines.append(f"- `present`: `{structural_policy_active_set.get('present')}`")
        lines.append(
            "- `shell_pressure_load_path_policy`: "
            f"`{structural_policy_active_set.get('shell_pressure_load_path_policy')}`"
        )
        lines.append(
            "- `initial_residual_n`: "
            f"`{structural_policy_active_set.get('initial_residual_n')}`"
        )
        lines.append(
            "- `final_residual_n`: "
            f"`{structural_policy_active_set.get('final_residual_n')}`"
        )
        lines.append(
            "- `total_reduction_n`: "
            f"`{structural_policy_active_set.get('total_reduction_n')}`"
        )
        lines.append(
            "- `total_reduction_ratio`: "
            f"`{structural_policy_active_set.get('total_reduction_ratio')}`"
        )
        lines.append(
            "- `residual_gate_passed`: "
            f"`{structural_policy_active_set.get('residual_gate_passed')}`"
        )
        lines.append(
            "- `checkpoint_path`: "
            f"`{structural_policy_active_set.get('checkpoint_path')}`"
        )
    if structural_policy_alpha_sweep:
        lines.extend(["", "## Active Frontier Structural Policy Alpha Sweep", ""])
        lines.append(f"- `present`: `{structural_policy_alpha_sweep.get('present')}`")
        lines.append(
            f"- `stop_reason`: `{structural_policy_alpha_sweep.get('stop_reason')}`"
        )
        lines.append(
            "- `final_residual_n`: "
            f"`{structural_policy_alpha_sweep.get('final_residual_n')}`"
        )
    if structural_policy_direct_replay:
        lines.extend(
            [
                "",
                "## Active Frontier Structural Policy State-Updated Direct Replay",
                "",
            ]
        )
        lines.append(
            f"- `present`: `{structural_policy_direct_replay.get('present')}`"
        )
        lines.append(f"- `status`: `{structural_policy_direct_replay.get('status')}`")
        lines.append(
            "- `state_updated_material_direct_residual_inf_n`: "
            f"`{structural_policy_direct_replay.get('state_updated_material_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `direct_residual_gate_passed`: "
            f"`{structural_policy_direct_replay.get('direct_residual_gate_passed')}`"
        )
        lines.append(
            "- `live_g1_assembly_contract_passed`: "
            f"`{structural_policy_direct_replay.get('live_g1_assembly_contract_passed')}`"
        )
        lines.append(
            "- `consistent_residual_jacobian_newton_passed`: "
            f"`{structural_policy_direct_replay.get('consistent_residual_jacobian_newton_passed')}`"
        )
        lines.append(
            "- `residual_component_breakdown_included`: "
            f"`{structural_policy_direct_replay.get('residual_component_breakdown_included')}`"
        )
        lines.append(
            "- `top_row_dominant_component`: "
            f"`{structural_policy_direct_replay.get('top_row_dominant_component')}`"
        )
        lines.append(
            "- `top_row_residual_n`: "
            f"`{structural_policy_direct_replay.get('top_row_residual_n')}`"
        )
        lines.append(
            "- `top_row_global_dof`: "
            f"`{structural_policy_direct_replay.get('top_row_global_dof')}`"
        )
        lines.append(
            "- `top_row_component_values_n`: "
            f"`{structural_policy_direct_replay.get('top_row_component_values_n')}`"
        )
    if structural_policy_component_row:
        lines.extend(
            [
                "",
                "## Active Frontier Structural Policy Current Component Row Correction",
                "",
            ]
        )
        lines.append(f"- `present`: `{structural_policy_component_row.get('present')}`")
        lines.append(f"- `status`: `{structural_policy_component_row.get('status')}`")
        lines.append(
            "- `base_direct_residual_inf_n`: "
            f"`{structural_policy_component_row.get('base_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `final_direct_residual_inf_n`: "
            f"`{structural_policy_component_row.get('final_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `improvement_inf_n`: "
            f"`{structural_policy_component_row.get('improvement_inf_n')}`"
        )
        lines.append(
            "- `row_correction_accepted`: "
            f"`{structural_policy_component_row.get('row_correction_accepted')}`"
        )
        lines.append(
            "- `accepted_state_refresh_cpu_used`: "
            f"`{structural_policy_component_row.get('accepted_state_refresh_cpu_used')}`"
        )
        lines.append(
            "- `output_checkpoint_path`: "
            f"`{structural_policy_component_row.get('output_checkpoint_path')}`"
        )
        lines.append(
            "- `top_row_dominant_component`: "
            f"`{structural_policy_component_row.get('top_row_dominant_component')}`"
        )
    if structural_policy_component_row_step2:
        lines.extend(
            [
                "",
                "## Active Frontier Structural Policy Current Component Row Correction Step 2",
                "",
            ]
        )
        lines.append(
            f"- `present`: `{structural_policy_component_row_step2.get('present')}`"
        )
        lines.append(
            f"- `status`: `{structural_policy_component_row_step2.get('status')}`"
        )
        lines.append(
            "- `base_direct_residual_inf_n`: "
            f"`{structural_policy_component_row_step2.get('base_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `final_direct_residual_inf_n`: "
            f"`{structural_policy_component_row_step2.get('final_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `improvement_inf_n`: "
            f"`{structural_policy_component_row_step2.get('improvement_inf_n')}`"
        )
        lines.append(
            "- `row_correction_accepted`: "
            f"`{structural_policy_component_row_step2.get('row_correction_accepted')}`"
        )
        lines.append(
            "- `accepted_state_refresh_cpu_used`: "
            f"`{structural_policy_component_row_step2.get('accepted_state_refresh_cpu_used')}`"
        )
        lines.append(
            "- `output_checkpoint_path`: "
            f"`{structural_policy_component_row_step2.get('output_checkpoint_path')}`"
        )
        lines.append(
            "- `top_row_dominant_component`: "
            f"`{structural_policy_component_row_step2.get('top_row_dominant_component')}`"
        )
    if structural_policy_component_row_step3:
        lines.extend(
            [
                "",
                "## Active Frontier Structural Policy Current Component Row Correction Step 3",
                "",
            ]
        )
        lines.append(
            f"- `present`: `{structural_policy_component_row_step3.get('present')}`"
        )
        lines.append(
            f"- `status`: `{structural_policy_component_row_step3.get('status')}`"
        )
        lines.append(
            "- `base_direct_residual_inf_n`: "
            f"`{structural_policy_component_row_step3.get('base_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `final_direct_residual_inf_n`: "
            f"`{structural_policy_component_row_step3.get('final_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `row_correction_accepted`: "
            f"`{structural_policy_component_row_step3.get('row_correction_accepted')}`"
        )
        lines.append(
            "- `row_correction_stop_reason`: "
            f"`{structural_policy_component_row_step3.get('row_correction_stop_reason')}`"
        )
        lines.append(
            "- `best_candidate_direct_residual_inf_n`: "
            f"`{structural_policy_component_row_step3.get('best_candidate_direct_residual_inf_n')}`"
        )
    if structural_policy_component_row_chain:
        lines.extend(
            [
                "",
                "## Active Frontier Structural Policy Current Component Row Correction Chain",
                "",
            ]
        )
        lines.append(
            "- `accepted_step_count`: "
            f"`{structural_policy_component_row_chain.get('accepted_step_count')}`"
        )
        lines.append(
            "- `latest_accepted_final_residual_inf_n`: "
            f"`{structural_policy_component_row_chain.get('latest_accepted_final_residual_inf_n')}`"
        )
        lines.append(
            "- `first_no_descent_stop_reason`: "
            f"`{structural_policy_component_row_chain.get('first_no_descent_stop_reason')}`"
        )
        lines.append(
            "- `first_no_descent_best_residual_inf_n`: "
            f"`{structural_policy_component_row_chain.get('first_no_descent_best_residual_inf_n')}`"
        )
        lines.append(
            "- `claim_boundary`: "
            f"`{structural_policy_component_row_chain.get('claim_boundary')}`"
        )
    if structural_policy_ownership:
        lines.extend(["", "## Active Frontier Structural Policy Residual Ownership", ""])
        lines.append(f"- `present`: `{structural_policy_ownership.get('present')}`")
        lines.append(
            "- `top_residual_inf_n`: "
            f"`{structural_policy_ownership.get('top_residual_inf_n')}`"
        )
        lines.append(
            "- `top_row_node_id`: "
            f"`{structural_policy_ownership.get('top_row_node_id')}`"
        )
        lines.append(
            "- `top_row_dof_label`: "
            f"`{structural_policy_ownership.get('top_row_dof_label')}`"
        )
        lines.append(
            "- `top_row_dominant_internal_component`: "
            f"`{structural_policy_ownership.get('top_row_dominant_internal_component')}`"
        )
        lines.append(
            "- `top_row_balance_driver`: "
            f"`{structural_policy_ownership.get('top_row_balance_driver')}`"
        )
        lines.append(
            "- `top_row_inferred_external_load_n`: "
            f"`{structural_policy_ownership.get('top_row_inferred_external_load_n')}`"
        )
        lines.append(
            "- `top_row_load_derivative_n_per_load`: "
            f"`{structural_policy_ownership.get('top_row_load_derivative_n_per_load')}`"
        )
    if structural_policy_linearized_after:
        lines.extend(
            [
                "",
                "## Active Frontier Structural Policy Linearized After Two-Step",
                "",
            ]
        )
        lines.append(
            "- `best_linear_active_residual_after_inf_n`: "
            f"`{structural_policy_linearized_after.get('best_linear_active_residual_after_inf_n')}`"
        )
        lines.append(
            "- `linearized_active_descent_observed`: "
            f"`{structural_policy_linearized_after.get('linearized_active_descent_observed')}`"
        )
        lines.append(
            "- `direct_replay_required_for_candidate`: "
            f"`{structural_policy_linearized_after.get('direct_replay_required_for_candidate')}`"
        )
    if shell_rotation_candidate:
        lines.extend(["", "## Active Frontier Shell Rotation Row Candidate", ""])
        lines.append(f"- `present`: `{shell_rotation_candidate.get('present')}`")
        lines.append(
            f"- `fd_consistent`: `{shell_rotation_candidate.get('fd_consistent')}`"
        )
        lines.append(
            "- `selected_rotation_row_count`: "
            f"`{shell_rotation_candidate.get('selected_rotation_row_count')}`"
        )
        lines.append(
            "- `best_direct_residual_inf_n`: "
            f"`{shell_rotation_candidate.get('best_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `best_improvement_inf_n`: "
            f"`{shell_rotation_candidate.get('best_improvement_inf_n')}`"
        )
        lines.append(
            "- `checkpoint_path`: "
            f"`{shell_rotation_candidate.get('checkpoint_path')}`"
        )
        lines.append(
            "- `checkpoint_best_alpha`: "
            f"`{shell_rotation_candidate.get('checkpoint_best_alpha')}`"
        )
    if shell_rotation_no_descent:
        lines.extend(["", "## Active Frontier Shell Rotation Row No-Descent Probe", ""])
        lines.append(f"- `present`: `{shell_rotation_no_descent.get('present')}`")
        lines.append(
            "- `base_residual_inf_n`: "
            f"`{shell_rotation_no_descent.get('base_residual_inf_n')}`"
        )
        lines.append(
            "- `best_improvement_inf_n`: "
            f"`{shell_rotation_no_descent.get('best_improvement_inf_n')}`"
        )
        lines.append(
            "- `direct_descent_observed`: "
            f"`{shell_rotation_no_descent.get('direct_descent_observed')}`"
        )
    if shell_rotation_candidate_ownership:
        lines.extend(
            [
                "",
                "## Active Frontier Shell Rotation Candidate Residual Ownership",
                "",
            ]
        )
        lines.append(
            "- `top_residual_inf_n`: "
            f"`{shell_rotation_candidate_ownership.get('top_residual_inf_n')}`"
        )
        lines.append(
            "- `top_row_dof_label`: "
            f"`{shell_rotation_candidate_ownership.get('top_row_dof_label')}`"
        )
        lines.append(
            "- `top_row_dominant_internal_component`: "
            f"`{shell_rotation_candidate_ownership.get('top_row_dominant_internal_component')}`"
        )
        lines.append(
            "- `top_row_balance_driver`: "
            f"`{shell_rotation_candidate_ownership.get('top_row_balance_driver')}`"
        )
    if sparse_scaled_lsmr:
        lines.extend(
            [
                "",
                "## Sparse Direct Scaled-LSMR Frontier Probe",
                "",
            ]
        )
        lines.append(f"- `present`: `{sparse_scaled_lsmr.get('present')}`")
        lines.append(f"- `status`: `{sparse_scaled_lsmr.get('status')}`")
        lines.append(
            "- `jvp_parity_pass`: "
            f"`{sparse_scaled_lsmr.get('jvp_parity_pass')}`"
        )
        lines.append(
            "- `assembled_tangent_parity_pass`: "
            f"`{sparse_scaled_lsmr.get('assembled_tangent_parity_pass')}`"
        )
        lines.append(
            "- `direction_status`: "
            f"`{sparse_scaled_lsmr.get('direction_status')}`"
        )
        lines.append(
            "- `direction_iterations`: "
            f"`{sparse_scaled_lsmr.get('direction_iterations')}`"
        )
        lines.append(
            "- `line_search_status`: "
            f"`{sparse_scaled_lsmr.get('line_search_status')}`"
        )
        lines.append(
            "- `line_search_residual_after_n`: "
            f"`{sparse_scaled_lsmr.get('line_search_residual_after_n')}`"
        )
        lines.append(
            "- `line_search_residual_reduction_ratio`: "
            f"`{sparse_scaled_lsmr.get('line_search_residual_reduction_ratio')}`"
        )
        lines.append(
            "- `output_checkpoint_written`: "
            f"`{sparse_scaled_lsmr.get('output_checkpoint_written')}`"
        )
        lines.append(
            "- `output_checkpoint_path`: "
            f"`{sparse_scaled_lsmr.get('output_checkpoint_path')}`"
        )
        lines.append(
            "- `output_checkpoint_direct_residual_inf_n`: "
            f"`{sparse_scaled_lsmr.get('output_checkpoint_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `output_checkpoint_residual_gate_passed`: "
            f"`{sparse_scaled_lsmr.get('output_checkpoint_residual_gate_passed')}`"
        )
    if sparse_scaled_lsmr_second:
        lines.extend(
            [
                "",
                "## Sparse Direct Scaled-LSMR Second Step Probe",
                "",
            ]
        )
        lines.append(f"- `present`: `{sparse_scaled_lsmr_second.get('present')}`")
        lines.append(f"- `status`: `{sparse_scaled_lsmr_second.get('status')}`")
        lines.append(
            "- `line_search_status`: "
            f"`{sparse_scaled_lsmr_second.get('line_search_status')}`"
        )
        lines.append(
            "- `line_search_residual_after_n`: "
            f"`{sparse_scaled_lsmr_second.get('line_search_residual_after_n')}`"
        )
        lines.append(
            "- `line_search_residual_reduction_ratio`: "
            f"`{sparse_scaled_lsmr_second.get('line_search_residual_reduction_ratio')}`"
        )
        lines.append(
            "- `output_checkpoint_written`: "
            f"`{sparse_scaled_lsmr_second.get('output_checkpoint_written')}`"
        )
        lines.append(
            "- `output_checkpoint_path`: "
            f"`{sparse_scaled_lsmr_second.get('output_checkpoint_path')}`"
        )
        lines.append(
            "- `output_checkpoint_direct_residual_inf_n`: "
            f"`{sparse_scaled_lsmr_second.get('output_checkpoint_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `output_checkpoint_residual_gate_passed`: "
            f"`{sparse_scaled_lsmr_second.get('output_checkpoint_residual_gate_passed')}`"
        )
    if sparse_scaled_lsmr_from_incomplete_preview:
        lines.extend(
            [
                "",
                "## Sparse Direct Scaled-LSMR From Incomplete Preview",
                "",
            ]
        )
        lines.append(
            f"- `present`: `{sparse_scaled_lsmr_from_incomplete_preview.get('present')}`"
        )
        lines.append(
            f"- `status`: `{sparse_scaled_lsmr_from_incomplete_preview.get('status')}`"
        )
        lines.append(
            "- `line_search_residual_after_n`: "
            f"`{sparse_scaled_lsmr_from_incomplete_preview.get('line_search_residual_after_n')}`"
        )
        lines.append(
            "- `line_search_residual_reduction_ratio`: "
            f"`{sparse_scaled_lsmr_from_incomplete_preview.get('line_search_residual_reduction_ratio')}`"
        )
        lines.append(
            "- `output_checkpoint_path`: "
            f"`{sparse_scaled_lsmr_from_incomplete_preview.get('output_checkpoint_path')}`"
        )
        lines.append(
            "- `output_checkpoint_direct_residual_inf_n`: "
            f"`{sparse_scaled_lsmr_from_incomplete_preview.get('output_checkpoint_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `output_checkpoint_residual_gate_passed`: "
            f"`{sparse_scaled_lsmr_from_incomplete_preview.get('output_checkpoint_residual_gate_passed')}`"
        )
    if sparse_scaled_lsmr_from_incomplete_preview_chain:
        lines.extend(
            [
                "",
                "## Sparse Direct Scaled-LSMR From Incomplete Preview Chain",
                "",
            ]
        )
        lines.append(
            f"- `path`: `{sparse_scaled_lsmr_from_incomplete_preview_chain.get('path')}`"
        )
        lines.append(
            f"- `status`: `{sparse_scaled_lsmr_from_incomplete_preview_chain.get('status')}`"
        )
        lines.append(
            "- `step_count`: "
            f"`{sparse_scaled_lsmr_from_incomplete_preview_chain.get('step_count')}`"
        )
        lines.append(
            "- `final_residual_n`: "
            f"`{sparse_scaled_lsmr_from_incomplete_preview_chain.get('final_residual_n')}`"
        )
        lines.append(
            "- `final_residual_over_gate`: "
            f"`{sparse_scaled_lsmr_from_incomplete_preview_chain.get('final_residual_over_gate')}`"
        )
        lines.append(
            "- `estimated_steps_to_gate_at_last_reduction`: "
            f"`{sparse_scaled_lsmr_from_incomplete_preview_chain.get('estimated_steps_to_gate_at_last_reduction')}`"
        )
        lines.append(
            "- `gate_convergence_assessment`: "
            f"`{sparse_scaled_lsmr_from_incomplete_preview_chain.get('gate_convergence_assessment')}`"
        )
        lines.append(
            "- `recommended_next_action`: "
            f"`{sparse_scaled_lsmr_from_incomplete_preview_chain.get('recommended_next_action')}`"
        )
        lines.append(
            "- `latest_checkpoint_path`: "
            f"`{sparse_scaled_lsmr_from_incomplete_preview_chain.get('latest_checkpoint_path')}`"
        )
    for label, probe in (
        (
            "Sparse Direct Shifted-SPLU From Incomplete Preview Chain",
            shifted_splu_from_incomplete_preview_chain,
        ),
        (
            "Sparse Direct Shifted-SPLU From Gate Candidate Step 2",
            shifted_splu_from_gate_step2,
        ),
    ):
        if not probe:
            continue
        lines.extend(["", f"## {label}", ""])
        lines.append(f"- `path`: `{probe.get('path')}`")
        lines.append(f"- `status`: `{probe.get('status')}`")
        lines.append(f"- `shift_mu`: `{probe.get('shifted_operator_shift_mu')}`")
        lines.append(
            "- `line_search_residual_before_n`: "
            f"`{probe.get('line_search_residual_before_n')}`"
        )
        lines.append(
            "- `line_search_residual_after_n`: "
            f"`{probe.get('line_search_residual_after_n')}`"
        )
        lines.append(
            "- `line_search_residual_reduction_ratio`: "
            f"`{probe.get('line_search_residual_reduction_ratio')}`"
        )
        lines.append(
            "- `output_checkpoint_path`: "
            f"`{probe.get('output_checkpoint_path')}`"
        )
        lines.append(
            "- `output_checkpoint_direct_residual_inf_n`: "
            f"`{probe.get('output_checkpoint_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `output_checkpoint_residual_gate_passed`: "
            f"`{probe.get('output_checkpoint_residual_gate_passed')}`"
        )
        lines.append(
            "- `recommended_next_action`: "
            f"`{probe.get('recommended_next_action')}`"
        )
    if sparse_scaled_lsmr_chain:
        lines.extend(
            [
                "",
                "## Sparse Direct Scaled-LSMR Accepted-Step Chain",
                "",
            ]
        )
        lines.append(
            f"- `step_count`: `{sparse_scaled_lsmr_chain.get('step_count')}`"
        )
        lines.append(
            "- `ready_step_count`: "
            f"`{sparse_scaled_lsmr_chain.get('ready_step_count')}`"
        )
        lines.append(
            "- `monotonic_residual_descent`: "
            f"`{sparse_scaled_lsmr_chain.get('monotonic_residual_descent')}`"
        )
        lines.append(
            "- `initial_residual_n`: "
            f"`{sparse_scaled_lsmr_chain.get('initial_residual_n')}`"
        )
        lines.append(
            "- `final_residual_n`: "
            f"`{sparse_scaled_lsmr_chain.get('final_residual_n')}`"
        )
        lines.append(
            "- `total_reduction_n`: "
            f"`{sparse_scaled_lsmr_chain.get('total_reduction_n')}`"
        )
        lines.append(
            "- `total_reduction_ratio`: "
            f"`{sparse_scaled_lsmr_chain.get('total_reduction_ratio')}`"
        )
        lines.append(
            "- `latest_checkpoint_path`: "
            f"`{sparse_scaled_lsmr_chain.get('latest_checkpoint_path')}`"
        )
        lines.append(
            "- `latest_checkpoint_residual_gate_passed`: "
            f"`{sparse_scaled_lsmr_chain.get('latest_checkpoint_residual_gate_passed')}`"
        )
    if sparse_scaled_lsmr_chain_probe:
        lines.extend(
            [
                "",
                "## Sparse Direct Scaled-LSMR Chain Receipt",
                "",
            ]
        )
        lines.append(f"- `path`: `{sparse_scaled_lsmr_chain_probe.get('path')}`")
        lines.append(
            f"- `status`: `{sparse_scaled_lsmr_chain_probe.get('status')}`"
        )
        lines.append(
            "- `final_residual_n`: "
            f"`{sparse_scaled_lsmr_chain_probe.get('final_residual_n')}`"
        )
        lines.append(
            "- `latest_checkpoint_path`: "
            f"`{sparse_scaled_lsmr_chain_probe.get('latest_checkpoint_path')}`"
        )
    if sparse_scaled_lsmr_long_chain_probe:
        lines.extend(
            [
                "",
                "## Sparse Direct Scaled-LSMR Long-Chain Receipt",
                "",
            ]
        )
        lines.append(
            f"- `path`: `{sparse_scaled_lsmr_long_chain_probe.get('path')}`"
        )
        lines.append(
            f"- `status`: `{sparse_scaled_lsmr_long_chain_probe.get('status')}`"
        )
        lines.append(
            "- `step_count`: "
            f"`{sparse_scaled_lsmr_long_chain_probe.get('step_count')}`"
        )
        lines.append(
            "- `final_residual_n`: "
            f"`{sparse_scaled_lsmr_long_chain_probe.get('final_residual_n')}`"
        )
        lines.append(
            "- `final_residual_over_gate`: "
            f"`{sparse_scaled_lsmr_long_chain_probe.get('final_residual_over_gate')}`"
        )
        lines.append(
            "- `estimated_steps_to_gate_at_last_reduction`: "
            f"`{sparse_scaled_lsmr_long_chain_probe.get('estimated_steps_to_gate_at_last_reduction')}`"
        )
        lines.append(
            "- `gate_convergence_assessment`: "
            f"`{sparse_scaled_lsmr_long_chain_probe.get('gate_convergence_assessment')}`"
        )
        lines.append(
            "- `recommended_next_action`: "
            f"`{sparse_scaled_lsmr_long_chain_probe.get('recommended_next_action')}`"
        )
        lines.append(
            "- `latest_checkpoint_path`: "
            f"`{sparse_scaled_lsmr_long_chain_probe.get('latest_checkpoint_path')}`"
        )
    adaptive_ilu = payload.get("sparse_direct_adaptive_jvp_eps_gmres_ilu_probe")
    adaptive_matrix_free = payload.get(
        "sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe"
    )
    adaptive_shifted_ilu = payload.get(
        "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe"
    )
    adaptive_shifted_ilu_preview = payload.get(
        "sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe"
    )
    if (
        isinstance(adaptive_ilu, dict)
        or isinstance(adaptive_matrix_free, dict)
        or isinstance(adaptive_shifted_ilu, dict)
        or isinstance(adaptive_shifted_ilu_preview, dict)
    ):
        lines.extend(["", "## Sparse Direct Adaptive-JVP GMRES Receipts", ""])
        for label, probe in (
            ("gmres_ilu", adaptive_ilu),
            ("gmres_matrix_free", adaptive_matrix_free),
            ("gmres_shifted_ilu", adaptive_shifted_ilu),
            ("gmres_shifted_ilu_incomplete_preview", adaptive_shifted_ilu_preview),
        ):
            if not isinstance(probe, dict):
                continue
            lines.append(f"- `{label}.path`: `{probe.get('path')}`")
            lines.append(f"- `{label}.status`: `{probe.get('status')}`")
            lines.append(f"- `{label}.reason_code`: `{probe.get('reason_code')}`")
            lines.append(f"- `{label}.jvp_eps`: `{probe.get('jvp_eps')}`")
            lines.append(
                f"- `{label}.jvp_parity_max_absolute_error_n`: "
                f"`{probe.get('jvp_parity_max_absolute_error_n')}`"
            )
            lines.append(
                f"- `{label}.direction_status`: `{probe.get('direction_status')}`"
            )
            lines.append(
                f"- `{label}.direction_residual_after_n`: "
                f"`{probe.get('direction_residual_after_n')}`"
            )
            lines.append(
                f"- `{label}.line_search_status`: "
                f"`{probe.get('line_search_status')}`"
            )
            lines.append(
                f"- `{label}.line_search_residual_after_n`: "
                f"`{probe.get('line_search_residual_after_n')}`"
            )
            lines.append(
                f"- `{label}.incomplete_direction_preview`: "
                f"`{probe.get('incomplete_direction_preview')}`"
            )
            lines.append(
                f"- `{label}.recommended_next_action`: "
                f"`{probe.get('recommended_next_action')}`"
            )
    if adaptive_frontier:
        lines.extend(["", "## Adaptive All-Components Frontier", ""])
        lines.append(f"- `present`: `{adaptive_frontier.get('present')}`")
        lines.append(f"- `status`: `{adaptive_frontier.get('status')}`")
        lines.append(
            f"- `shell_pressure_load_path_policy`: `{adaptive_frontier.get('shell_pressure_load_path_policy')}`"
        )
        lines.append(
            f"- `final_residual_n`: `{adaptive_frontier.get('final_residual_n')}`"
        )
        lines.append(
            f"- `residual_gate_passed`: `{adaptive_frontier.get('residual_gate_passed')}`"
        )
        lines.append(
            f"- `checkpoint_path`: `{adaptive_frontier.get('checkpoint_path')}`"
        )
    if shell_jvp or shell_diag:
        lines.extend(["", "## Shell Hotspot Narrowing", ""])
        lines.append(f"- `jvp_present`: `{shell_jvp.get('present')}`")
        lines.append(
            f"- `jvp_fd_consistent`: `{shell_jvp.get('fd_consistent')}`"
        )
        lines.append(
            "- `jvp_max_relative_inf_error`: "
            f"`{shell_jvp.get('max_relative_inf_error')}`"
        )
        lines.append(f"- `diagonal_present`: `{shell_diag.get('present')}`")
        lines.append(
            f"- `diagonal_descent_observed`: `{shell_diag.get('descent_observed')}`"
        )
        lines.append(
            "- `diagonal_best_direct_residual_inf_n`: "
            f"`{shell_diag.get('best_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `diagonal_best_improvement_inf_n`: "
            f"`{shell_diag.get('best_improvement_inf_n')}`"
        )
    if global_tangent:
        lines.extend(["", "## Global Tangent Sweep", ""])
        lines.append(f"- `present`: `{global_tangent.get('present')}`")
        lines.append(f"- `evaluated`: `{global_tangent.get('evaluated')}`")
        lines.append(f"- `scaling_mode`: `{global_tangent.get('scaling_mode')}`")
        lines.append(
            f"- `descent_observed`: `{global_tangent.get('descent_observed')}`"
        )
        lines.append(
            "- `linear_relative_residual_inf`: "
            f"`{global_tangent.get('linear_relative_residual_inf')}`"
        )
        lines.append(
            "- `best_direct_residual_inf_n`: "
            f"`{global_tangent.get('best_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `best_improvement_inf_n`: "
            f"`{global_tangent.get('best_improvement_inf_n')}`"
        )
    if residual_gradient:
        lines.extend(["", "## Residual-Norm Gradient Sweep", ""])
        lines.append(f"- `present`: `{residual_gradient.get('present')}`")
        lines.append(f"- `evaluated`: `{residual_gradient.get('evaluated')}`")
        lines.append(f"- `trust_radius_m`: `{residual_gradient.get('trust_radius_m')}`")
        lines.append(
            f"- `inf_descent_observed`: `{residual_gradient.get('inf_descent_observed')}`"
        )
        lines.append(
            f"- `l2_descent_observed`: `{residual_gradient.get('l2_descent_observed')}`"
        )
        lines.append(
            "- `best_l2_direct_residual_l2_n`: "
            f"`{residual_gradient.get('best_l2_direct_residual_l2_n')}`"
        )
        lines.append(
            "- `best_l2_improvement_l2_n`: "
            f"`{residual_gradient.get('best_l2_improvement_l2_n')}`"
        )
    if active_set:
        lines.extend(["", "## Active-Set LS Sweep", ""])
        lines.append(f"- `present`: `{active_set.get('present')}`")
        lines.append(f"- `evaluated`: `{active_set.get('evaluated')}`")
        lines.append(
            f"- `selected_hotspot_row_count`: `{active_set.get('selected_hotspot_row_count')}`"
        )
        lines.append(
            f"- `full_inf_descent_observed`: `{active_set.get('full_inf_descent_observed')}`"
        )
        lines.append(
            f"- `active_inf_descent_observed`: `{active_set.get('active_inf_descent_observed')}`"
        )
        lines.append(
            "- `best_full_direct_residual_inf_n`: "
            f"`{active_set.get('best_full_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `best_full_improvement_inf_n`: "
            f"`{active_set.get('best_full_improvement_inf_n')}`"
        )
    if active_set_candidate:
        lines.extend(["", "## Active-Set LS Trust Candidate", ""])
        lines.append(f"- `present`: `{active_set_candidate.get('present')}`")
        lines.append(f"- `status`: `{active_set_candidate.get('status')}`")
        lines.append(
            f"- `checkpoint_written`: `{active_set_candidate.get('checkpoint_written')}`"
        )
        lines.append(
            f"- `final_residual_n`: `{active_set_candidate.get('final_residual_n')}`"
        )
        lines.append(
            f"- `total_reduction_n`: `{active_set_candidate.get('total_reduction_n')}`"
        )
        lines.append(
            f"- `residual_gate_passed`: `{active_set_candidate.get('residual_gate_passed')}`"
        )
        lines.append(
            f"- `checkpoint_path`: `{active_set_candidate.get('checkpoint_path')}`"
        )
    if active_set_schedule:
        lines.extend(["", "## Active-Set LS Schedule Candidate", ""])
        lines.append(f"- `present`: `{active_set_schedule.get('present')}`")
        lines.append(f"- `status`: `{active_set_schedule.get('status')}`")
        lines.append(
            f"- `active_row_count_schedule`: `{active_set_schedule.get('active_row_count_schedule')}`"
        )
        lines.append(
            f"- `final_residual_n`: `{active_set_schedule.get('final_residual_n')}`"
        )
        lines.append(
            f"- `total_reduction_n`: `{active_set_schedule.get('total_reduction_n')}`"
        )
    if active_set_tangent_jvp:
        lines.extend(["", "## Active-Set Trust Tangent FD JVP", ""])
        lines.append(f"- `present`: `{active_set_tangent_jvp.get('present')}`")
        lines.append(
            f"- `fd_consistent`: `{active_set_tangent_jvp.get('fd_consistent')}`"
        )
        lines.append(
            "- `evaluated_row_count`: "
            f"`{active_set_tangent_jvp.get('evaluated_row_count')}`"
        )
        lines.append(
            "- `max_relative_inf_error`: "
            f"`{active_set_tangent_jvp.get('max_relative_inf_error')}`"
        )
        lines.append(
            "- `max_relative_l2_error`: "
            f"`{active_set_tangent_jvp.get('max_relative_l2_error')}`"
        )
    if active_set_minimax:
        lines.extend(["", "## Active-Set Minimax Trust Candidate", ""])
        lines.append(f"- `present`: `{active_set_minimax.get('present')}`")
        lines.append(f"- `status`: `{active_set_minimax.get('status')}`")
        lines.append(
            f"- `final_residual_n`: `{active_set_minimax.get('final_residual_n')}`"
        )
        lines.append(
            f"- `total_reduction_n`: `{active_set_minimax.get('total_reduction_n')}`"
        )
        lines.append(f"- `steps_taken`: `{active_set_minimax.get('steps_taken')}`")
        lines.append(
            "- `best_linear_active_inf_improvement_n`: "
            f"`{active_set_minimax.get('best_linear_active_inf_improvement_n')}`"
        )
    if hip_required_frontier:
        lines.extend(["", "## HIP-Required Full-Load Residual/JVP Frontier", ""])
        lines.append(f"- `present`: `{hip_required_frontier.get('present')}`")
        lines.append(f"- `status`: `{hip_required_frontier.get('status')}`")
        lines.append(
            "- `load_scale`: "
            f"`{hip_required_frontier.get('load_scale')}`"
        )
        lines.append(
            "- `base_direct_residual_inf_n`: "
            f"`{hip_required_frontier.get('base_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `final_direct_residual_inf_n`: "
            f"`{hip_required_frontier.get('final_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `direct_residual_gate_passed`: "
            f"`{hip_required_frontier.get('direct_residual_gate_passed')}`"
        )
        lines.append(
            "- `matrix_free_global_krylov_hip_solver_used`: "
            f"`{hip_required_frontier.get('matrix_free_global_krylov_hip_solver_used')}`"
        )
        lines.append(
            "- `hip_required_components_passed`: "
            f"`{hip_required_frontier.get('hip_required_components_passed')}`"
        )
        lines.append(
            "- `output_checkpoint_path`: "
            f"`{hip_required_frontier.get('output_checkpoint_path')}`"
        )
        lines.append(
            "- `claim_boundary`: "
            f"`{hip_required_frontier.get('claim_boundary')}`"
        )
    if hip_required_consistency_direct:
        lines.extend(["", "## HIP-Required Consistency Direct Probe", ""])
        lines.append(f"- `present`: `{hip_required_consistency_direct.get('present')}`")
        lines.append(f"- `executed`: `{hip_required_consistency_direct.get('executed')}`")
        lines.append(f"- `status`: `{hip_required_consistency_direct.get('status')}`")
        lines.append(
            "- `load_scale`: "
            f"`{hip_required_consistency_direct.get('load_scale')}`"
        )
        lines.append(
            "- `base_direct_residual_inf_n`: "
            f"`{hip_required_consistency_direct.get('base_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `final_direct_residual_inf_n`: "
            f"`{hip_required_consistency_direct.get('final_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `direct_residual_gate_passed`: "
            f"`{hip_required_consistency_direct.get('direct_residual_gate_passed')}`"
        )
        lines.append(
            "- `residual_jvp_worker_path_ready`: "
            f"`{hip_required_consistency_direct.get('residual_jvp_worker_path_ready')}`"
        )
        lines.append(
            "- `matrix_free_global_krylov_jvp_rows_retained`: "
            f"`{hip_required_consistency_direct.get('matrix_free_global_krylov_jvp_rows_retained')}`"
        )
        lines.append(
            "- `output_checkpoint_path`: "
            f"`{hip_required_consistency_direct.get('output_checkpoint_path')}`"
        )
        lines.append(
            "- `blocker_count`: "
            f"`{hip_required_consistency_direct.get('blocker_count')}`"
        )
        lines.append(
            "- `claim_boundary`: "
            f"`{hip_required_consistency_direct.get('claim_boundary')}`"
        )
    if hip_required_no_descent_receipts:
        lines.extend(["", "## HIP-Required Frontier No-Descent Receipts", ""])
        for receipt in hip_required_no_descent_receipts:
            variant = receipt.get("variant")
            lines.append(f"- `{variant}.path`: `{receipt.get('path')}`")
            lines.append(f"- `{variant}.receipt_kind`: `{receipt.get('receipt_kind')}`")
            lines.append(f"- `{variant}.status`: `{receipt.get('status')}`")
            lines.append(f"- `{variant}.no_descent`: `{receipt.get('no_descent')}`")
            lines.append(
                f"- `{variant}.base_direct_residual_inf_n`: "
                f"`{receipt.get('base_direct_residual_inf_n')}`"
            )
            lines.append(
                f"- `{variant}.final_direct_residual_inf_n`: "
                f"`{receipt.get('final_direct_residual_inf_n')}`"
            )
            lines.append(
                f"- `{variant}.output_checkpoint_written`: "
                f"`{receipt.get('output_checkpoint_written')}`"
            )
            lines.append(
                f"- `{variant}.output_checkpoint_path`: "
                f"`{receipt.get('output_checkpoint_path')}`"
            )
            if receipt.get("output_checkpoint_reason"):
                lines.append(
                    f"- `{variant}.output_checkpoint_reason`: "
                    f"`{receipt.get('output_checkpoint_reason')}`"
                )
            lines.append(
                f"- `{variant}.matrix_free_global_krylov_scaling_mode`: "
                f"`{receipt.get('matrix_free_global_krylov_scaling_mode')}`"
            )
            lines.append(
                f"- `{variant}.matrix_free_global_krylov_best_residual_inf_n`: "
                f"`{receipt.get('matrix_free_global_krylov_best_residual_inf_n')}`"
            )
            lines.append(
                f"- `{variant}.current_tangent_residual_row_best_residual_inf_n`: "
                f"`{receipt.get('current_tangent_residual_row_best_residual_inf_n')}`"
            )
            lines.append(
                f"- `{variant}.claim_boundary`: "
                f"`{receipt.get('claim_boundary')}`"
            )
    if current_frontier_operator_mismatch:
        frontier = _as_dict(current_frontier_operator_mismatch.get("frontier_probe"))
        no_descent = _as_dict(
            current_frontier_operator_mismatch.get("current_frontier_no_descent")
        )
        scaled_global = _as_dict(no_descent.get("scaled_global_krylov"))
        row_correction = _as_dict(
            no_descent.get("current_tangent_residual_row_correction")
        )
        operator_summary = _as_dict(
            current_frontier_operator_mismatch.get("operator_mismatch_summary")
        )
        mismatch = _as_dict(
            current_frontier_operator_mismatch.get("current_operator_mismatch")
        )
        lines.extend(["", "## Current Frontier Operator Mismatch Audit", ""])
        lines.append(f"- `status`: `{current_frontier_operator_mismatch.get('status')}`")
        lines.append(
            f"- `audit_complete`: `{current_frontier_operator_mismatch.get('audit_complete')}`"
        )
        lines.append(
            f"- `full_load_no_descent`: `{frontier.get('full_load_no_descent')}`"
        )
        lines.append(
            "- `base_direct_residual_inf_n`: "
            f"`{frontier.get('base_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `scaled_global_krylov.best_direct_residual_inf_n`: "
            f"`{scaled_global.get('best_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `current_tangent_residual_row_correction.best_direct_residual_inf_n`: "
            f"`{row_correction.get('best_direct_residual_inf_n')}`"
        )
        lines.append(
            "- `global_and_row_operator_family_no_descent`: "
            f"`{no_descent.get('global_and_row_operator_family_no_descent')}`"
        )
        lines.append(
            f"- `mismatch_reasons`: `{mismatch.get('mismatch_reasons')}`"
        )
        lines.append(
            f"- `next_required_operator`: `{operator_summary.get('next_required_operator')}`"
        )
        lines.append(
            f"- `claim_boundary`: `{current_frontier_operator_mismatch.get('claim_boundary')}`"
        )
    if material_breadth or material_seed_suite:
        lines.extend(["", "## State-Updated Material Newton Breadth Seeds", ""])
        lines.append(f"- `summary_status`: `{material_breadth.get('status')}`")
        lines.append(
            "- `seed_coverage_ready`: "
            f"`{material_breadth.get('state_updated_material_newton_breadth_seed_coverage_ready')}`"
        )
        lines.append(
            "- `seed_case_count`: "
            f"`{material_breadth.get('state_updated_material_newton_seed_case_count')}`"
        )
        lines.append(
            "- `frame_material_newton_seed_pass`: "
            f"`{material_breadth.get('frame_material_newton_seed_pass')}`"
        )
        lines.append(
            "- `shell_material_newton_seed_pass`: "
            f"`{material_breadth.get('shell_material_newton_seed_pass')}`"
        )
        lines.append(
            "- `material_state_persistence_replay_seed_passed`: "
            f"`{material_breadth.get('material_state_persistence_replay_seed_passed')}`"
        )
        lines.append(
            "- `material_jvp_relative_error_pass`: "
            f"`{material_breadth.get('material_jvp_relative_error_pass')}`"
        )
        lines.append(
            "- `state_updated_material_newton_breadth_closed`: "
            f"`{material_breadth.get('state_updated_material_newton_breadth_closed')}`"
        )
        lines.append(
            "- `state_updated_seed_suite_case_count`: "
            f"`{material_seed_suite.get('state_updated_material_newton_seed_case_count')}`"
        )
        lines.append(
            f"- `claim_boundary`: `{material_breadth.get('claim_boundary')}`"
        )
    if payload.get("next_actions"):
        lines.extend(["", "## Next Actions", ""])
        for item in _as_list(payload.get("next_actions")):
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- `{item.get('id')}`: owner=`{item.get('owner')}`, "
                f"status=`{item.get('status')}`"
            )
    if payload["blockers"]:
        lines.extend(["", "## Contract Blockers", ""])
        lines.extend(f"- `{item}`" for item in payload["blockers"])
    repair_plan = _as_dict(payload.get("worker_path_repair_plan"))
    if repair_plan:
        lines.extend(["", "## Worker Path Repair Plan", ""])
        lines.append(f"- `next_action_id`: `{repair_plan.get('next_action_id')}`")
        lines.append(f"- `blocker_count`: `{repair_plan.get('blocker_count')}`")
        for category in _as_list(repair_plan.get("category_order")):
            lines.append(
                f"- `{category}`: "
                f"`{_as_dict(repair_plan.get('category_counts')).get(category, 0)}`"
            )
    operator_sequence = _as_list(payload.get("worker_path_operator_sequence"))
    if operator_sequence:
        lines.extend(["", "## Worker Path Operator Sequence", ""])
        for item in operator_sequence:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- `{item.get('step_id')}`: owner=`{item.get('owner')}`, "
                f"status=`{item.get('status')}`"
            )
    if payload["closure_blockers"]:
        lines.extend(["", "## Closure Blockers", ""])
        lines.extend(f"- `{item}`" for item in payload["closure_blockers"])
    lines.extend(["", "## Claim Boundary", "", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_runner_packet(
    *,
    repo_root: Path = ROOT,
    g1_lane_path: Path = DEFAULT_G1_LANE,
    cause_narrowing_path: Path = DEFAULT_CAUSE_NARROWING,
    hip_probe_path: Path = DEFAULT_HIP_PROBE,
    global_connectivity_path: Path = DEFAULT_GLOBAL_CONNECTIVITY,
    assembly_contract_seed_path: Path = DEFAULT_ASSEMBLY_CONTRACT_SEED,
    cpu_live_assembly_contract_probe_path: Path = (
        DEFAULT_CPU_LIVE_ASSEMBLY_CONTRACT_PROBE
    ),
    true_newton_load_sweep_path: Path = DEFAULT_TRUE_NEWTON_LOAD_SWEEP,
    true_newton_full_load_checkpoint_candidate_path: Path = (
        DEFAULT_TRUE_NEWTON_FULL_LOAD_CHECKPOINT_CANDIDATE
    ),
    true_newton_from_active_set_ls_trust_candidate_path: Path = (
        DEFAULT_TRUE_NEWTON_FROM_ACTIVE_SET_LS_TRUST_CANDIDATE
    ),
    true_newton_from_active_set_service_tangent_ls_trust_candidate_path: Path = (
        DEFAULT_TRUE_NEWTON_FROM_ACTIVE_SET_SERVICE_TANGENT_LS_TRUST_CANDIDATE
    ),
    adaptive_all_components_frontier_path: Path = DEFAULT_ADAPTIVE_ALL_COMPONENTS_FRONTIER,
    shell_hotspot_tangent_fd_jvp_probe_path: Path = (
        DEFAULT_SHELL_HOTSPOT_TANGENT_FD_JVP_PROBE
    ),
    shell_hotspot_diagonal_sweep_probe_path: Path = (
        DEFAULT_SHELL_HOTSPOT_DIAGONAL_SWEEP_PROBE
    ),
    global_tangent_scaled_sweep_probe_path: Path = (
        DEFAULT_GLOBAL_TANGENT_SCALED_SWEEP_PROBE
    ),
    residual_norm_gradient_tiny_sweep_probe_path: Path = (
        DEFAULT_RESIDUAL_NORM_GRADIENT_TINY_SWEEP_PROBE
    ),
    active_set_ls_sweep_probe_path: Path = DEFAULT_ACTIVE_SET_LS_SWEEP_PROBE,
    active_set_ls_trust_candidate_path: Path = DEFAULT_ACTIVE_SET_LS_TRUST_CANDIDATE,
    active_set_ls_trust_schedule_candidate_path: Path = (
        DEFAULT_ACTIVE_SET_LS_TRUST_SCHEDULE_CANDIDATE
    ),
    active_set_ls_trust_tangent_fd_jvp_probe_path: Path = (
        DEFAULT_ACTIVE_SET_LS_TRUST_TANGENT_FD_JVP_PROBE
    ),
    active_set_minimax_trust_candidate_path: Path = (
        DEFAULT_ACTIVE_SET_MINIMAX_TRUST_CANDIDATE
    ),
    frame_tangent_fd_epsilon_sweep_probe_path: Path = (
        DEFAULT_FRAME_TANGENT_FD_EPSILON_SWEEP_PROBE
    ),
    true_newton_from_active_set_mu_sweep_probe_path: Path = (
        DEFAULT_TRUE_NEWTON_FROM_ACTIVE_SET_MU_SWEEP_PROBE
    ),
    active_set_load_parameter_probe_path: Path = (
        DEFAULT_ACTIVE_SET_LOAD_PARAMETER_PROBE
    ),
    active_set_load_parameter_tiny_trust_probe_path: Path = (
        DEFAULT_ACTIVE_SET_LOAD_PARAMETER_TINY_TRUST_PROBE
    ),
    active_frontier_residual_ownership_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_RESIDUAL_OWNERSHIP_PROBE
    ),
    active_frontier_shell_load_neighborhood_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_SHELL_LOAD_NEIGHBORHOOD_PROBE
    ),
    active_frontier_shell_policy_replay_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_SHELL_POLICY_REPLAY_PROBE
    ),
    active_frontier_shell_policy_linearized_active_set_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_SHELL_POLICY_LINEARIZED_ACTIVE_SET_PROBE
    ),
    active_frontier_structural_policy_active_set_ls_trust_candidate_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_LS_TRUST_CANDIDATE
    ),
    active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_LS_TRUST_ALPHA_SWEEP
    ),
    active_frontier_structural_policy_active_set_direct_material_replay_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_DIRECT_MATERIAL_REPLAY_PROBE
    ),
    active_frontier_structural_policy_active_set_current_component_row_correction_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_CURRENT_COMPONENT_ROW_CORRECTION_PROBE
    ),
    active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_CURRENT_COMPONENT_ROW_CORRECTION_STEP2_PROBE
    ),
    active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_CURRENT_COMPONENT_ROW_CORRECTION_STEP3_PROBE
    ),
    active_frontier_structural_policy_residual_ownership_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_RESIDUAL_OWNERSHIP_PROBE
    ),
    active_frontier_structural_policy_linearized_active_set_after_two_step_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_LINEARIZED_ACTIVE_SET_AFTER_TWO_STEP_PROBE
    ),
    active_frontier_structural_policy_shell_rotation_row_candidate_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_SHELL_ROTATION_ROW_CANDIDATE
    ),
    active_frontier_structural_policy_shell_rotation_row_no_descent_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_SHELL_ROTATION_ROW_NO_DESCENT_PROBE
    ),
    active_frontier_structural_policy_shell_rotation_candidate_ownership_probe_path: Path = (
        DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_SHELL_ROTATION_CANDIDATE_OWNERSHIP_PROBE
    ),
    sparse_direct_scaled_lsmr_frontier_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FRONTIER_PROBE
    ),
    sparse_direct_scaled_lsmr_second_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SCALED_LSMR_SECOND_PROBE
    ),
    sparse_direct_scaled_lsmr_third_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SCALED_LSMR_THIRD_PROBE
    ),
    sparse_direct_scaled_lsmr_chain_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SCALED_LSMR_CHAIN_PROBE
    ),
    sparse_direct_scaled_lsmr_long_chain_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SCALED_LSMR_LONG_CHAIN_PROBE
    ),
    sparse_direct_scaled_lsmr_from_incomplete_preview_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FROM_INCOMPLETE_PREVIEW_PROBE
    ),
    sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FROM_INCOMPLETE_PREVIEW_CHAIN_PROBE
    ),
    sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SHIFTED_SPLU_FROM_INCOMPLETE_PREVIEW_CHAIN_PROBE
    ),
    sparse_direct_shifted_splu_from_gate_candidate_step2_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_SHIFTED_SPLU_FROM_GATE_CANDIDATE_STEP2_PROBE
    ),
    sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_ILU_PROBE
    ),
    sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_MATRIX_FREE_PROBE
    ),
    sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_SHIFTED_ILU_PROBE
    ),
    sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_path: Path = (
        DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_SHIFTED_ILU_INCOMPLETE_PREVIEW_PROBE
    ),
    hip_required_full_load_residual_jvp_frontier_probe_path: Path = (
        DEFAULT_HIP_REQUIRED_FULL_LOAD_RESIDUAL_JVP_FRONTIER_PROBE
    ),
    hip_required_full_load_residual_jvp_frontier_candidate_path: Path = (
        DEFAULT_HIP_REQUIRED_FULL_LOAD_RESIDUAL_JVP_FRONTIER_CANDIDATE
    ),
    hip_required_consistency_no_descent_probe_path: Path = (
        DEFAULT_HIP_REQUIRED_CONSISTENCY_NO_DESCENT_PROBE
    ),
    hip_required_scaled_global_krylov_no_descent_probe_path: Path = (
        DEFAULT_HIP_REQUIRED_SCALED_GLOBAL_KRYLOV_NO_DESCENT_PROBE
    ),
    current_frontier_operator_mismatch_audit_path: Path = (
        DEFAULT_CURRENT_FRONTIER_OPERATOR_MISMATCH_AUDIT
    ),
    phase2_material_newton_breadth_summary_path: Path = (
        DEFAULT_PHASE2_MATERIAL_NEWTON_BREADTH_SUMMARY
    ),
    phase2_material_newton_breadth_state_updated_seeds_path: Path = (
        DEFAULT_PHASE2_MATERIAL_NEWTON_BREADTH_STATE_UPDATED_SEEDS
    ),
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_runner_packet(
        repo_root=repo_root,
        g1_lane_path=g1_lane_path,
        cause_narrowing_path=cause_narrowing_path,
        hip_probe_path=hip_probe_path,
        global_connectivity_path=global_connectivity_path,
        assembly_contract_seed_path=assembly_contract_seed_path,
        cpu_live_assembly_contract_probe_path=cpu_live_assembly_contract_probe_path,
        true_newton_load_sweep_path=true_newton_load_sweep_path,
        true_newton_full_load_checkpoint_candidate_path=(
            true_newton_full_load_checkpoint_candidate_path
        ),
        true_newton_from_active_set_ls_trust_candidate_path=(
            true_newton_from_active_set_ls_trust_candidate_path
        ),
        true_newton_from_active_set_service_tangent_ls_trust_candidate_path=(
            true_newton_from_active_set_service_tangent_ls_trust_candidate_path
        ),
        adaptive_all_components_frontier_path=adaptive_all_components_frontier_path,
        shell_hotspot_tangent_fd_jvp_probe_path=(
            shell_hotspot_tangent_fd_jvp_probe_path
        ),
        shell_hotspot_diagonal_sweep_probe_path=(
            shell_hotspot_diagonal_sweep_probe_path
        ),
        global_tangent_scaled_sweep_probe_path=(
            global_tangent_scaled_sweep_probe_path
        ),
        residual_norm_gradient_tiny_sweep_probe_path=(
            residual_norm_gradient_tiny_sweep_probe_path
        ),
        active_set_ls_sweep_probe_path=active_set_ls_sweep_probe_path,
        active_set_ls_trust_candidate_path=active_set_ls_trust_candidate_path,
        active_set_ls_trust_schedule_candidate_path=(
            active_set_ls_trust_schedule_candidate_path
        ),
        active_set_ls_trust_tangent_fd_jvp_probe_path=(
            active_set_ls_trust_tangent_fd_jvp_probe_path
        ),
        active_set_minimax_trust_candidate_path=(
            active_set_minimax_trust_candidate_path
        ),
        frame_tangent_fd_epsilon_sweep_probe_path=(
            frame_tangent_fd_epsilon_sweep_probe_path
        ),
        true_newton_from_active_set_mu_sweep_probe_path=(
            true_newton_from_active_set_mu_sweep_probe_path
        ),
        active_set_load_parameter_probe_path=active_set_load_parameter_probe_path,
        active_set_load_parameter_tiny_trust_probe_path=(
            active_set_load_parameter_tiny_trust_probe_path
        ),
        active_frontier_residual_ownership_probe_path=(
            active_frontier_residual_ownership_probe_path
        ),
        active_frontier_shell_load_neighborhood_probe_path=(
            active_frontier_shell_load_neighborhood_probe_path
        ),
        active_frontier_shell_policy_replay_probe_path=(
            active_frontier_shell_policy_replay_probe_path
        ),
        active_frontier_shell_policy_linearized_active_set_probe_path=(
            active_frontier_shell_policy_linearized_active_set_probe_path
        ),
        active_frontier_structural_policy_active_set_ls_trust_candidate_path=(
            active_frontier_structural_policy_active_set_ls_trust_candidate_path
        ),
        active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_path=(
            active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_path
        ),
        active_frontier_structural_policy_active_set_direct_material_replay_probe_path=(
            active_frontier_structural_policy_active_set_direct_material_replay_probe_path
        ),
        active_frontier_structural_policy_active_set_current_component_row_correction_probe_path=(
            active_frontier_structural_policy_active_set_current_component_row_correction_probe_path
        ),
        active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe_path=(
            active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe_path
        ),
        active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe_path=(
            active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe_path
        ),
        active_frontier_structural_policy_residual_ownership_probe_path=(
            active_frontier_structural_policy_residual_ownership_probe_path
        ),
        active_frontier_structural_policy_linearized_active_set_after_two_step_probe_path=(
            active_frontier_structural_policy_linearized_active_set_after_two_step_probe_path
        ),
        active_frontier_structural_policy_shell_rotation_row_candidate_path=(
            active_frontier_structural_policy_shell_rotation_row_candidate_path
        ),
        active_frontier_structural_policy_shell_rotation_row_no_descent_probe_path=(
            active_frontier_structural_policy_shell_rotation_row_no_descent_probe_path
        ),
        active_frontier_structural_policy_shell_rotation_candidate_ownership_probe_path=(
            active_frontier_structural_policy_shell_rotation_candidate_ownership_probe_path
        ),
        sparse_direct_scaled_lsmr_frontier_probe_path=(
            sparse_direct_scaled_lsmr_frontier_probe_path
        ),
        sparse_direct_scaled_lsmr_second_probe_path=(
            sparse_direct_scaled_lsmr_second_probe_path
        ),
        sparse_direct_scaled_lsmr_third_probe_path=(
            sparse_direct_scaled_lsmr_third_probe_path
        ),
        sparse_direct_scaled_lsmr_chain_probe_path=(
            sparse_direct_scaled_lsmr_chain_probe_path
        ),
        sparse_direct_scaled_lsmr_long_chain_probe_path=(
            sparse_direct_scaled_lsmr_long_chain_probe_path
        ),
        sparse_direct_scaled_lsmr_from_incomplete_preview_probe_path=(
            sparse_direct_scaled_lsmr_from_incomplete_preview_probe_path
        ),
        sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_path=(
            sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_path
        ),
        sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_path=(
            sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_path
        ),
        sparse_direct_shifted_splu_from_gate_candidate_step2_probe_path=(
            sparse_direct_shifted_splu_from_gate_candidate_step2_probe_path
        ),
        sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_path=(
            sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_path
        ),
        sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_path=(
            sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_path
        ),
        sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_path=(
            sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_path
        ),
        sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_path=(
            sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_path
        ),
        hip_required_full_load_residual_jvp_frontier_probe_path=(
            hip_required_full_load_residual_jvp_frontier_probe_path
        ),
        hip_required_full_load_residual_jvp_frontier_candidate_path=(
            hip_required_full_load_residual_jvp_frontier_candidate_path
        ),
        hip_required_consistency_no_descent_probe_path=(
            hip_required_consistency_no_descent_probe_path
        ),
        hip_required_scaled_global_krylov_no_descent_probe_path=(
            hip_required_scaled_global_krylov_no_descent_probe_path
        ),
        current_frontier_operator_mismatch_audit_path=(
            current_frontier_operator_mismatch_audit_path
        ),
        phase2_material_newton_breadth_summary_path=(
            phase2_material_newton_breadth_summary_path
        ),
        phase2_material_newton_breadth_state_updated_seeds_path=(
            phase2_material_newton_breadth_state_updated_seeds_path
        ),
    )
    resolved_out = _resolve(repo_root, out)
    resolved_out_md = _resolve(repo_root, out_md)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_out_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_out_md.write_text(_markdown(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--g1-lane", type=Path, default=DEFAULT_G1_LANE)
    parser.add_argument("--cause-narrowing", type=Path, default=DEFAULT_CAUSE_NARROWING)
    parser.add_argument("--hip-probe", type=Path, default=DEFAULT_HIP_PROBE)
    parser.add_argument("--global-connectivity", type=Path, default=DEFAULT_GLOBAL_CONNECTIVITY)
    parser.add_argument(
        "--assembly-contract-seed",
        type=Path,
        default=DEFAULT_ASSEMBLY_CONTRACT_SEED,
    )
    parser.add_argument(
        "--cpu-live-assembly-contract-probe",
        type=Path,
        default=DEFAULT_CPU_LIVE_ASSEMBLY_CONTRACT_PROBE,
    )
    parser.add_argument(
        "--true-newton-load-sweep",
        type=Path,
        default=DEFAULT_TRUE_NEWTON_LOAD_SWEEP,
    )
    parser.add_argument(
        "--true-newton-full-load-checkpoint-candidate",
        type=Path,
        default=DEFAULT_TRUE_NEWTON_FULL_LOAD_CHECKPOINT_CANDIDATE,
    )
    parser.add_argument(
        "--true-newton-from-active-set-ls-trust-candidate",
        type=Path,
        default=DEFAULT_TRUE_NEWTON_FROM_ACTIVE_SET_LS_TRUST_CANDIDATE,
    )
    parser.add_argument(
        "--true-newton-from-active-set-service-tangent-ls-trust-candidate",
        type=Path,
        default=DEFAULT_TRUE_NEWTON_FROM_ACTIVE_SET_SERVICE_TANGENT_LS_TRUST_CANDIDATE,
    )
    parser.add_argument(
        "--frame-tangent-fd-epsilon-sweep-probe",
        type=Path,
        default=DEFAULT_FRAME_TANGENT_FD_EPSILON_SWEEP_PROBE,
    )
    parser.add_argument(
        "--true-newton-from-active-set-mu-sweep-probe",
        type=Path,
        default=DEFAULT_TRUE_NEWTON_FROM_ACTIVE_SET_MU_SWEEP_PROBE,
    )
    parser.add_argument(
        "--active-set-load-parameter-probe",
        type=Path,
        default=DEFAULT_ACTIVE_SET_LOAD_PARAMETER_PROBE,
    )
    parser.add_argument(
        "--active-set-load-parameter-tiny-trust-probe",
        type=Path,
        default=DEFAULT_ACTIVE_SET_LOAD_PARAMETER_TINY_TRUST_PROBE,
    )
    parser.add_argument(
        "--active-frontier-residual-ownership-probe",
        type=Path,
        default=DEFAULT_ACTIVE_FRONTIER_RESIDUAL_OWNERSHIP_PROBE,
    )
    parser.add_argument(
        "--active-frontier-shell-load-neighborhood-probe",
        type=Path,
        default=DEFAULT_ACTIVE_FRONTIER_SHELL_LOAD_NEIGHBORHOOD_PROBE,
    )
    parser.add_argument(
        "--active-frontier-shell-policy-replay-probe",
        type=Path,
        default=DEFAULT_ACTIVE_FRONTIER_SHELL_POLICY_REPLAY_PROBE,
    )
    parser.add_argument(
        "--active-frontier-shell-policy-linearized-active-set-probe",
        type=Path,
        default=DEFAULT_ACTIVE_FRONTIER_SHELL_POLICY_LINEARIZED_ACTIVE_SET_PROBE,
    )
    parser.add_argument(
        "--active-frontier-structural-policy-active-set-ls-trust-candidate",
        type=Path,
        default=DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_LS_TRUST_CANDIDATE,
    )
    parser.add_argument(
        "--active-frontier-structural-policy-active-set-ls-trust-alpha-sweep",
        type=Path,
        default=DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_LS_TRUST_ALPHA_SWEEP,
    )
    parser.add_argument(
        "--active-frontier-structural-policy-active-set-direct-material-replay-probe",
        type=Path,
        default=(
            DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_DIRECT_MATERIAL_REPLAY_PROBE
        ),
    )
    parser.add_argument(
        "--active-frontier-structural-policy-active-set-current-component-row-correction-probe",
        type=Path,
        default=(
            DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_CURRENT_COMPONENT_ROW_CORRECTION_PROBE
        ),
    )
    parser.add_argument(
        "--active-frontier-structural-policy-active-set-current-component-row-correction-step2-probe",
        type=Path,
        default=(
            DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_CURRENT_COMPONENT_ROW_CORRECTION_STEP2_PROBE
        ),
    )
    parser.add_argument(
        "--active-frontier-structural-policy-active-set-current-component-row-correction-step3-probe",
        type=Path,
        default=(
            DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_ACTIVE_SET_CURRENT_COMPONENT_ROW_CORRECTION_STEP3_PROBE
        ),
    )
    parser.add_argument(
        "--active-frontier-structural-policy-residual-ownership-probe",
        type=Path,
        default=DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_RESIDUAL_OWNERSHIP_PROBE,
    )
    parser.add_argument(
        "--active-frontier-structural-policy-linearized-active-set-after-two-step-probe",
        type=Path,
        default=(
            DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_LINEARIZED_ACTIVE_SET_AFTER_TWO_STEP_PROBE
        ),
    )
    parser.add_argument(
        "--active-frontier-structural-policy-shell-rotation-row-candidate",
        type=Path,
        default=DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_SHELL_ROTATION_ROW_CANDIDATE,
    )
    parser.add_argument(
        "--active-frontier-structural-policy-shell-rotation-row-no-descent-probe",
        type=Path,
        default=DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_SHELL_ROTATION_ROW_NO_DESCENT_PROBE,
    )
    parser.add_argument(
        "--active-frontier-structural-policy-shell-rotation-candidate-ownership-probe",
        type=Path,
        default=(
            DEFAULT_ACTIVE_FRONTIER_STRUCTURAL_POLICY_SHELL_ROTATION_CANDIDATE_OWNERSHIP_PROBE
        ),
    )
    parser.add_argument(
        "--sparse-direct-scaled-lsmr-frontier-probe",
        type=Path,
        default=DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FRONTIER_PROBE,
    )
    parser.add_argument(
        "--sparse-direct-scaled-lsmr-second-probe",
        type=Path,
        default=DEFAULT_SPARSE_DIRECT_SCALED_LSMR_SECOND_PROBE,
    )
    parser.add_argument(
        "--sparse-direct-scaled-lsmr-third-probe",
        type=Path,
        default=DEFAULT_SPARSE_DIRECT_SCALED_LSMR_THIRD_PROBE,
    )
    parser.add_argument(
        "--sparse-direct-scaled-lsmr-chain-probe",
        type=Path,
        default=DEFAULT_SPARSE_DIRECT_SCALED_LSMR_CHAIN_PROBE,
    )
    parser.add_argument(
        "--sparse-direct-scaled-lsmr-long-chain-probe",
        type=Path,
        default=DEFAULT_SPARSE_DIRECT_SCALED_LSMR_LONG_CHAIN_PROBE,
    )
    parser.add_argument(
        "--sparse-direct-scaled-lsmr-from-incomplete-preview-probe",
        type=Path,
        default=DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FROM_INCOMPLETE_PREVIEW_PROBE,
    )
    parser.add_argument(
        "--sparse-direct-scaled-lsmr-from-incomplete-preview-chain-probe",
        type=Path,
        default=DEFAULT_SPARSE_DIRECT_SCALED_LSMR_FROM_INCOMPLETE_PREVIEW_CHAIN_PROBE,
    )
    parser.add_argument(
        "--sparse-direct-shifted-splu-from-incomplete-preview-chain-probe",
        type=Path,
        default=DEFAULT_SPARSE_DIRECT_SHIFTED_SPLU_FROM_INCOMPLETE_PREVIEW_CHAIN_PROBE,
    )
    parser.add_argument(
        "--sparse-direct-shifted-splu-from-gate-candidate-step2-probe",
        type=Path,
        default=DEFAULT_SPARSE_DIRECT_SHIFTED_SPLU_FROM_GATE_CANDIDATE_STEP2_PROBE,
    )
    parser.add_argument(
        "--sparse-direct-adaptive-jvp-eps-gmres-ilu-probe",
        type=Path,
        default=DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_ILU_PROBE,
    )
    parser.add_argument(
        "--sparse-direct-adaptive-jvp-eps-gmres-matrix-free-probe",
        type=Path,
        default=DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_MATRIX_FREE_PROBE,
    )
    parser.add_argument(
        "--sparse-direct-adaptive-jvp-eps-gmres-shifted-ilu-probe",
        type=Path,
        default=DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_SHIFTED_ILU_PROBE,
    )
    parser.add_argument(
        "--sparse-direct-adaptive-jvp-eps-gmres-shifted-ilu-incomplete-preview-probe",
        type=Path,
        default=(
            DEFAULT_SPARSE_DIRECT_ADAPTIVE_JVP_EPS_GMRES_SHIFTED_ILU_INCOMPLETE_PREVIEW_PROBE
        ),
    )
    parser.add_argument(
        "--hip-required-full-load-residual-jvp-frontier-probe",
        type=Path,
        default=DEFAULT_HIP_REQUIRED_FULL_LOAD_RESIDUAL_JVP_FRONTIER_PROBE,
    )
    parser.add_argument(
        "--hip-required-full-load-residual-jvp-frontier-candidate",
        type=Path,
        default=DEFAULT_HIP_REQUIRED_FULL_LOAD_RESIDUAL_JVP_FRONTIER_CANDIDATE,
    )
    parser.add_argument(
        "--hip-required-consistency-no-descent-probe",
        type=Path,
        default=DEFAULT_HIP_REQUIRED_CONSISTENCY_NO_DESCENT_PROBE,
    )
    parser.add_argument(
        "--hip-required-scaled-global-krylov-no-descent-probe",
        type=Path,
        default=DEFAULT_HIP_REQUIRED_SCALED_GLOBAL_KRYLOV_NO_DESCENT_PROBE,
    )
    parser.add_argument(
        "--current-frontier-operator-mismatch-audit",
        type=Path,
        default=DEFAULT_CURRENT_FRONTIER_OPERATOR_MISMATCH_AUDIT,
    )
    parser.add_argument(
        "--phase2-material-newton-breadth-summary",
        type=Path,
        default=DEFAULT_PHASE2_MATERIAL_NEWTON_BREADTH_SUMMARY,
    )
    parser.add_argument(
        "--phase2-material-newton-breadth-state-updated-seeds",
        type=Path,
        default=DEFAULT_PHASE2_MATERIAL_NEWTON_BREADTH_STATE_UPDATED_SEEDS,
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_runner_packet(
        repo_root=args.repo_root,
        g1_lane_path=args.g1_lane,
        cause_narrowing_path=args.cause_narrowing,
        hip_probe_path=args.hip_probe,
        global_connectivity_path=args.global_connectivity,
        assembly_contract_seed_path=args.assembly_contract_seed,
        cpu_live_assembly_contract_probe_path=args.cpu_live_assembly_contract_probe,
        true_newton_load_sweep_path=args.true_newton_load_sweep,
        true_newton_full_load_checkpoint_candidate_path=(
            args.true_newton_full_load_checkpoint_candidate
        ),
        true_newton_from_active_set_ls_trust_candidate_path=(
            args.true_newton_from_active_set_ls_trust_candidate
        ),
        true_newton_from_active_set_service_tangent_ls_trust_candidate_path=(
            args.true_newton_from_active_set_service_tangent_ls_trust_candidate
        ),
        frame_tangent_fd_epsilon_sweep_probe_path=(
            args.frame_tangent_fd_epsilon_sweep_probe
        ),
        true_newton_from_active_set_mu_sweep_probe_path=(
            args.true_newton_from_active_set_mu_sweep_probe
        ),
        active_set_load_parameter_probe_path=args.active_set_load_parameter_probe,
        active_set_load_parameter_tiny_trust_probe_path=(
            args.active_set_load_parameter_tiny_trust_probe
        ),
        active_frontier_residual_ownership_probe_path=(
            args.active_frontier_residual_ownership_probe
        ),
        active_frontier_shell_load_neighborhood_probe_path=(
            args.active_frontier_shell_load_neighborhood_probe
        ),
        active_frontier_shell_policy_replay_probe_path=(
            args.active_frontier_shell_policy_replay_probe
        ),
        active_frontier_shell_policy_linearized_active_set_probe_path=(
            args.active_frontier_shell_policy_linearized_active_set_probe
        ),
        active_frontier_structural_policy_active_set_ls_trust_candidate_path=(
            args.active_frontier_structural_policy_active_set_ls_trust_candidate
        ),
        active_frontier_structural_policy_active_set_ls_trust_alpha_sweep_path=(
            args.active_frontier_structural_policy_active_set_ls_trust_alpha_sweep
        ),
        active_frontier_structural_policy_active_set_direct_material_replay_probe_path=(
            args.active_frontier_structural_policy_active_set_direct_material_replay_probe
        ),
        active_frontier_structural_policy_active_set_current_component_row_correction_probe_path=(
            args.active_frontier_structural_policy_active_set_current_component_row_correction_probe
        ),
        active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe_path=(
            args.active_frontier_structural_policy_active_set_current_component_row_correction_step2_probe
        ),
        active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe_path=(
            args.active_frontier_structural_policy_active_set_current_component_row_correction_step3_probe
        ),
        active_frontier_structural_policy_residual_ownership_probe_path=(
            args.active_frontier_structural_policy_residual_ownership_probe
        ),
        active_frontier_structural_policy_linearized_active_set_after_two_step_probe_path=(
            args.active_frontier_structural_policy_linearized_active_set_after_two_step_probe
        ),
        active_frontier_structural_policy_shell_rotation_row_candidate_path=(
            args.active_frontier_structural_policy_shell_rotation_row_candidate
        ),
        active_frontier_structural_policy_shell_rotation_row_no_descent_probe_path=(
            args.active_frontier_structural_policy_shell_rotation_row_no_descent_probe
        ),
        active_frontier_structural_policy_shell_rotation_candidate_ownership_probe_path=(
            args.active_frontier_structural_policy_shell_rotation_candidate_ownership_probe
        ),
        sparse_direct_scaled_lsmr_frontier_probe_path=(
            args.sparse_direct_scaled_lsmr_frontier_probe
        ),
        sparse_direct_scaled_lsmr_second_probe_path=(
            args.sparse_direct_scaled_lsmr_second_probe
        ),
        sparse_direct_scaled_lsmr_third_probe_path=(
            args.sparse_direct_scaled_lsmr_third_probe
        ),
        sparse_direct_scaled_lsmr_chain_probe_path=(
            args.sparse_direct_scaled_lsmr_chain_probe
        ),
        sparse_direct_scaled_lsmr_long_chain_probe_path=(
            args.sparse_direct_scaled_lsmr_long_chain_probe
        ),
        sparse_direct_scaled_lsmr_from_incomplete_preview_probe_path=(
            args.sparse_direct_scaled_lsmr_from_incomplete_preview_probe
        ),
        sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe_path=(
            args.sparse_direct_scaled_lsmr_from_incomplete_preview_chain_probe
        ),
        sparse_direct_shifted_splu_from_incomplete_preview_chain_probe_path=(
            args.sparse_direct_shifted_splu_from_incomplete_preview_chain_probe
        ),
        sparse_direct_shifted_splu_from_gate_candidate_step2_probe_path=(
            args.sparse_direct_shifted_splu_from_gate_candidate_step2_probe
        ),
        sparse_direct_adaptive_jvp_eps_gmres_ilu_probe_path=(
            args.sparse_direct_adaptive_jvp_eps_gmres_ilu_probe
        ),
        sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe_path=(
            args.sparse_direct_adaptive_jvp_eps_gmres_matrix_free_probe
        ),
        sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe_path=(
            args.sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_probe
        ),
        sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe_path=(
            args.sparse_direct_adaptive_jvp_eps_gmres_shifted_ilu_incomplete_preview_probe
        ),
        hip_required_full_load_residual_jvp_frontier_probe_path=(
            args.hip_required_full_load_residual_jvp_frontier_probe
        ),
        hip_required_full_load_residual_jvp_frontier_candidate_path=(
            args.hip_required_full_load_residual_jvp_frontier_candidate
        ),
        hip_required_consistency_no_descent_probe_path=(
            args.hip_required_consistency_no_descent_probe
        ),
        hip_required_scaled_global_krylov_no_descent_probe_path=(
            args.hip_required_scaled_global_krylov_no_descent_probe
        ),
        current_frontier_operator_mismatch_audit_path=(
            args.current_frontier_operator_mismatch_audit
        ),
        phase2_material_newton_breadth_summary_path=(
            args.phase2_material_newton_breadth_summary
        ),
        phase2_material_newton_breadth_state_updated_seeds_path=(
            args.phase2_material_newton_breadth_state_updated_seeds
        ),
        out=args.out,
        out_md=args.out_md,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
