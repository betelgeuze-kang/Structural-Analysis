#!/usr/bin/env python3
"""Build a non-promoting G1 F2g/F2h cause-narrowing receipt."""

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


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_F2G_AUDIT = PRODUCTIZATION / "g1_support_elastic_link_reconciliation_audit.local.json"
DEFAULT_F2H_STATUS = PRODUCTIZATION / "f2h_lightweight_continuation_status.local.json"
DEFAULT_G1_FULL_LOAD = PRODUCTIZATION / "g1_full_load_hip_newton_lane_report.json"
DEFAULT_OUT = PRODUCTIZATION / "g1_f2g_f2h_cause_narrowing_status.json"
SCHEMA_VERSION = "g1-f2g-f2h-cause-narrowing-status.v1"
REUSE_POLICY = "non_promoting_f2g_f2h_diagnostic_receipts_aggregated_for_next_g1_slice"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
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


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _first(items: list[str], limit: int = 12) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _finding_ids(f2g_audit: dict[str, Any]) -> set[str]:
    return {
        str(row.get("finding_id") or "")
        for row in _as_list(f2g_audit.get("ranked_findings"))
        if isinstance(row, dict)
    }


def _residual_growth_factor(f2h_status: dict[str, Any]) -> float | None:
    values = [
        _as_float(row.get("residual_inf_n"))
        for row in _as_list(f2h_status.get("residual_history"))
        if isinstance(row, dict) and row.get("residual_inf_n") is not None
    ]
    if len(values) < 2 or values[0] == 0.0:
        return None
    return values[-1] / values[0]


def build_status(
    *,
    repo_root: Path = ROOT,
    f2g_audit_path: Path = DEFAULT_F2G_AUDIT,
    f2h_status_path: Path = DEFAULT_F2H_STATUS,
    g1_full_load_path: Path = DEFAULT_G1_FULL_LOAD,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    f2g_audit = _load_json(repo_root, f2g_audit_path)
    f2h_status = _load_json(repo_root, f2h_status_path)
    g1_full_load = _load_json(repo_root, g1_full_load_path)

    blockers: list[str] = []
    if not f2g_audit:
        blockers.append(f"missing_or_invalid_f2g_audit:{f2g_audit_path}")
    if not f2h_status:
        blockers.append(f"missing_or_invalid_f2h_status:{f2h_status_path}")
    if not g1_full_load:
        blockers.append(f"missing_or_invalid_g1_full_load_report:{g1_full_load_path}")
    if f2g_audit and f2g_audit.get("status") != "ready":
        blockers.append("f2g_support_elastic_reconciliation_not_ready")
    if f2h_status and f2h_status.get("status") != "ready":
        blockers.append("f2h_lightweight_continuation_not_ready")

    f2g_summary = _as_dict(f2g_audit.get("summary"))
    f2h_summary = _as_dict(f2h_status.get("summary"))
    finding_ids = _finding_ids(f2g_audit)
    dominant_rows = _as_int(f2g_summary.get("dominant_dof_row_count"))
    direct_support = _as_int(f2g_summary.get("direct_support_member_count"))
    direct_link = _as_int(f2g_summary.get("direct_elastic_link_endpoint_count"))
    reachable = _as_int(f2g_summary.get("elastic_link_reachable_to_support_count"))
    global_tangent_ready = f2g_summary.get("global_frame_shell_tangent_integration_ready") is True

    direct_row_gap_disfavored = bool(dominant_rows > 0 and direct_support == 0 and direct_link == 0)
    elastic_link_transfer_disfavored = bool(dominant_rows > 0 and reachable == 0)
    boundary_not_global = bool(not global_tangent_ready)
    distributed_modes = "near_null_packet_is_distributed_translation_rotation" in finding_ids
    f2h_sequence_ready = bool(
        f2h_summary.get("required_sequence_proven") is True
        and f2h_summary.get("all_steps_ready") is True
        and _as_float(f2h_summary.get("max_converged_load_scale")) >= 0.4
    )
    f2h_residual_trend = str(f2h_summary.get("residual_trend_across_increasing_load") or "")
    residual_growth = _residual_growth_factor(f2h_status)

    evidence_signals = {
        "dominant_near_null_rows": dominant_rows,
        "direct_support_member_count": direct_support,
        "direct_elastic_link_endpoint_count": direct_link,
        "elastic_link_reachable_to_support_count": reachable,
        "support_or_link_row_gap_disfavored": direct_row_gap_disfavored,
        "elastic_link_graph_transfer_disfavored": elastic_link_transfer_disfavored,
        "global_frame_shell_tangent_integration_ready": global_tangent_ready,
        "boundary_subsystem_not_full_global_tangent": boundary_not_global,
        "distributed_translation_rotation_packet_present": distributed_modes,
        "f2h_lightweight_0p1_0p2_0p4_ready": f2h_sequence_ready,
        "f2h_residual_trend_across_increasing_load": f2h_residual_trend,
        "f2h_residual_growth_factor_0p1_to_0p4": residual_growth,
    }

    hypotheses = [
        {
            "hypothesis": "direct_support_or_elastic_link_row_missing",
            "classification": "deprioritized",
            "evidence": [
                f"direct_support_member_count={direct_support}/{dominant_rows}",
                f"direct_elastic_link_endpoint_count={direct_link}/{dominant_rows}",
                f"elastic_link_reachable_to_support_count={reachable}/{dominant_rows}",
            ],
            "next_action": "stop_row_only_support_or_elastic_link_corrections_unless_new_authoritative_rows_are_found",
        },
        {
            "hypothesis": "global_connectivity_or_load_path_transfer_gap",
            "classification": "primary_next_slice",
            "evidence": [
                "dominant near-null rows are not support members or elastic-link endpoints",
                "elastic-link graph does not reach authored supports for dominant rows",
                "boundary spring context is not full global frame/shell tangent integration",
            ],
            "next_action": "audit_full_structural_connectivity_and_load_path_transfer_before_more_row_corrections",
        },
        {
            "hypothesis": "weak_restraint_or_geometric_softening",
            "classification": "active_secondary",
            "evidence": [
                "near-null packet is distributed translation/rotation-like",
                f"F2h 0.1->0.2->0.4 status={f2h_status.get('status', 'missing')}",
                f"residual_trend={f2h_residual_trend}",
            ],
            "next_action": "compare load-dependent near-null packets and geometric stiffness contributions at 0.2 and 0.4",
        },
        {
            "hypothesis": "consistent_residual_jacobian_newton_gap",
            "classification": "required_for_closure",
            "evidence": [
                *[str(item) for item in _as_list(g1_full_load.get("blockers")) if "jacobian" in str(item).lower() or "newton" in str(item).lower()],
                "G1 full-load HIP/Newton lane remains blocked",
            ],
            "next_action": "continue consistent residual/Jacobian Newton path before any G1 promotion",
        },
        {
            "hypothesis": "production_rocm_hip_residual_jvp_lane_gap",
            "classification": "required_for_production_residency",
            "evidence": [
                *[str(item) for item in _as_list(g1_full_load.get("blockers")) if "hip" in str(item).lower() or "rocm" in str(item).lower()],
                "production HIP/JVP lane is not proven by the non-promoting F2g/F2h receipts",
            ],
            "next_action": "build/execute production ROCm HIP residual/JVP worker when runtime devices are available",
        },
    ]

    ready = bool(not blockers and direct_row_gap_disfavored and f2h_sequence_ready)
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_g1_f2g_f2h_cause_narrowing_status.py"),
                f2g_audit_path,
                f2h_status_path,
                g1_full_load_path,
            ],
            reused_evidence=True,
            reuse_policy=REUSE_POLICY,
            repo_root=repo_root,
        ),
        "status": "ready" if ready else "blocked",
        "contract_pass": ready,
        "reason_code": "PASS" if ready else "ERR_G1_F2G_F2H_CAUSE_NARROWING_NOT_READY",
        "promotes_g1_closure": False,
        "claim_boundary": (
            "This receipt narrows the next G1 diagnostic direction from existing F2g/F2h evidence. "
            "It does not close G1, promote full-load 1.0, or prove production ROCm/HIP residency."
        ),
        "summary_line": (
            "G1 F2g/F2h cause narrowing: "
            f"{'READY' if ready else 'BLOCKED'} | "
            f"support_or_link_row_gap_disfavored={direct_row_gap_disfavored} | "
            f"f2h_0p4_ready={f2h_sequence_ready} | "
            "next=global_connectivity_consistent_newton_rocm_lane"
        ),
        "evidence_signals": evidence_signals,
        "hypothesis_rank": hypotheses,
        "next_actions": [
            "stop_row_only_support_or_elastic_link_correction_loop",
            "audit_full_structural_graph_connectivity_and_load_path_transfer",
            "compare_load_dependent_near_null_and_geometric_stiffness_at_0p2_0p4",
            "continue_consistent_residual_jacobian_newton_path",
            "build_production_rocm_hip_residual_jvp_worker_when_runtime_available",
        ],
        "blockers": _first(blockers),
        "disallowed_promotions": [
            "no_G1_closure_claim",
            "no_full_load_1p0_claim",
            "no_row_only_correction_promotion",
            "no_production_rocm_hip_residency_claim",
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--f2g-audit-json", type=Path, default=DEFAULT_F2G_AUDIT)
    parser.add_argument("--f2h-status-json", type=Path, default=DEFAULT_F2H_STATUS)
    parser.add_argument("--g1-full-load-json", type=Path, default=DEFAULT_G1_FULL_LOAD)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_status(
        repo_root=args.repo_root,
        f2g_audit_path=args.f2g_audit_json,
        f2h_status_path=args.f2h_status_json,
        g1_full_load_path=args.g1_full_load_json,
    )
    output = args.out if args.out.is_absolute() else args.repo_root / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_json_text(payload), encoding="utf-8")
    print(payload["summary_line"])
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
