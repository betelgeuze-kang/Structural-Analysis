#!/usr/bin/env python3
"""Build a non-promoting G1 load-dependent near-null/geometric-softening receipt."""

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
DEFAULT_F2H_STATUS = PRODUCTIZATION / "f2h_lightweight_continuation_status.local.json"
DEFAULT_F2H_CONTINUATION = PRODUCTIZATION / "f2h_lightweight_pdelta_0p1_0p2_0p4.local.json"
DEFAULT_F2G_AUDIT = PRODUCTIZATION / "g1_support_elastic_link_reconciliation_audit.local.json"
DEFAULT_NEAR_NULL_0P2 = PRODUCTIZATION / "g1_load_dependent_near_null_0p2.local.json"
DEFAULT_NEAR_NULL_0P4 = PRODUCTIZATION / "g1_load_dependent_near_null_0p4.local.json"
DEFAULT_OUT = PRODUCTIZATION / "g1_load_dependent_near_null_geometric_stiffness_comparison.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
SCHEMA_VERSION = "g1-load-dependent-near-null-geometric-stiffness-comparison.v1"
REUSE_POLICY = "non_promoting_f2h_load_response_and_optional_near_null_packets"
REQUIRED_LOADS = (0.1, 0.2, 0.4)
NEAR_NULL_PACKET_LOADS = (0.2, 0.4)
SUPERLINEAR_TOLERANCE = 1.05


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


def _as_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        return float(value)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _step_load(row: dict[str, Any]) -> float | None:
    value = row.get("load_scale", row.get("load_step", row.get("target_load_scale")))
    return _as_float(value, None)


def _rows_by_load(continuation: dict[str, Any], f2h_status: dict[str, Any]) -> dict[float, dict[str, Any]]:
    rows: dict[float, dict[str, Any]] = {}
    for source_row in _as_list(continuation.get("step_results")):
        if not isinstance(source_row, dict):
            continue
        load = _step_load(source_row)
        if load is None:
            continue
        rows[round(float(load), 10)] = {
            "load_scale": float(load),
            "ready": bool(source_row.get("ready", source_row.get("converged", False))),
            "converged": bool(source_row.get("converged", source_row.get("ready", False))),
            "iteration_count": _as_int(source_row.get("iteration_count")),
            "residual_inf_n": _as_float(source_row.get("residual_inf_n"), None),
            "relative_increment": _as_float(source_row.get("relative_increment"), None),
            "max_translation_m": _as_float(source_row.get("max_translation_m"), None),
            "max_drift_ratio_pct": _as_float(source_row.get("max_drift_ratio_pct"), None),
            "fixed_point_increment_m": _as_float(source_row.get("fixed_point_increment_m"), None),
            "relaxation_factor": _as_float(source_row.get("relaxation_factor"), None),
        }
    for source_row in _as_list(f2h_status.get("residual_history")):
        if not isinstance(source_row, dict):
            continue
        load = _step_load(source_row)
        if load is None:
            continue
        key = round(float(load), 10)
        rows.setdefault(key, {"load_scale": float(load)})
        for field in ("ready", "iteration_count", "residual_inf_n", "relative_increment"):
            if field in source_row and rows[key].get(field) is None:
                rows[key][field] = source_row.get(field)
    return rows


def _metric_ratio(rows: dict[float, dict[str, Any]], left: float, right: float, field: str) -> float | None:
    left_value = _as_float(rows.get(round(left, 10), {}).get(field), None)
    right_value = _as_float(rows.get(round(right, 10), {}).get(field), None)
    if left_value in (None, 0.0) or right_value is None:
        return None
    return float(right_value) / float(left_value)


def _segment(rows: dict[float, dict[str, Any]], left: float, right: float) -> dict[str, Any]:
    load_ratio = right / left if left else None
    translation_ratio = _metric_ratio(rows, left, right, "max_translation_m")
    drift_ratio = _metric_ratio(rows, left, right, "max_drift_ratio_pct")
    residual_ratio = _metric_ratio(rows, left, right, "residual_inf_n")
    increment_ratio = _metric_ratio(rows, left, right, "relative_increment")
    superlinear_translation = (
        translation_ratio is not None
        and load_ratio is not None
        and translation_ratio > load_ratio * SUPERLINEAR_TOLERANCE
    )
    superlinear_drift = (
        drift_ratio is not None
        and load_ratio is not None
        and drift_ratio > load_ratio * SUPERLINEAR_TOLERANCE
    )
    return {
        "from_load_scale": left,
        "to_load_scale": right,
        "load_ratio": load_ratio,
        "max_translation_ratio": translation_ratio,
        "max_drift_ratio": drift_ratio,
        "residual_ratio": residual_ratio,
        "relative_increment_ratio": increment_ratio,
        "superlinear_translation_growth": bool(superlinear_translation),
        "superlinear_drift_growth": bool(superlinear_drift),
    }


def _near_null_summary(packet: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(packet.get("summary"))
    context = _as_dict(packet.get("near_null_context"))
    dominant_rows = _as_list(packet.get("dominant_dof_rows"))
    node_ids = []
    for row in dominant_rows:
        if isinstance(row, dict) and row.get("node_id") is not None:
            node_ids.append(int(row["node_id"]))
    return {
        "status": str(packet.get("status") or "missing"),
        "contract_pass": bool(packet.get("contract_pass")),
        "load_scale": _as_float(
            packet.get("load_scale", context.get("load_scale", summary.get("load_scale"))),
            None,
        ),
        "near_null_mode_count": _as_int(
            summary.get("near_null_mode_count", context.get("near_null_mode_count")),
            0,
        ),
        "dominant_dof_row_count": _as_int(
            summary.get("dominant_dof_row_count", len(dominant_rows)),
            0,
        ),
        "dominant_node_ids": sorted(set(node_ids)),
    }


def _node_overlap(left: list[int], right: list[int]) -> dict[str, Any]:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return {"shared_count": 0, "left_count": 0, "right_count": 0, "jaccard": None}
    union = left_set | right_set
    shared = left_set & right_set
    return {
        "shared_count": len(shared),
        "left_count": len(left_set),
        "right_count": len(right_set),
        "jaccard": (len(shared) / len(union)) if union else None,
    }


def build_comparison(
    *,
    repo_root: Path = ROOT,
    f2h_status_path: Path = DEFAULT_F2H_STATUS,
    f2h_continuation_path: Path = DEFAULT_F2H_CONTINUATION,
    f2g_audit_path: Path = DEFAULT_F2G_AUDIT,
    near_null_0p2_path: Path = DEFAULT_NEAR_NULL_0P2,
    near_null_0p4_path: Path = DEFAULT_NEAR_NULL_0P4,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    f2h_status = _load_json(repo_root, f2h_status_path)
    f2h_continuation = _load_json(repo_root, f2h_continuation_path)
    f2g_audit = _load_json(repo_root, f2g_audit_path)
    near_null_0p2 = _load_json(repo_root, near_null_0p2_path)
    near_null_0p4 = _load_json(repo_root, near_null_0p4_path)

    blockers: list[str] = []
    if not f2h_status:
        blockers.append(f"missing_or_invalid_f2h_status:{f2h_status_path}")
    if not f2h_continuation:
        blockers.append(f"missing_or_invalid_f2h_continuation:{f2h_continuation_path}")
    if not f2g_audit:
        blockers.append(f"missing_or_invalid_f2g_audit:{f2g_audit_path}")
    if f2h_status and f2h_status.get("status") != "ready":
        blockers.append("f2h_lightweight_continuation_status_not_ready")
    if f2g_audit and f2g_audit.get("status") != "ready":
        blockers.append("f2g_support_elastic_link_reconciliation_not_ready")

    rows = _rows_by_load(f2h_continuation, f2h_status)
    missing_loads = [load for load in REQUIRED_LOADS if round(load, 10) not in rows]
    for load in missing_loads:
        blockers.append(f"f2h_load_response_missing:{load:g}")
    load_response_ready = bool(not missing_loads and all(rows[round(load, 10)].get("ready", True) for load in REQUIRED_LOADS))
    if not load_response_ready:
        blockers.append("f2h_load_response_sequence_not_ready")

    packet_by_load = {
        0.2: near_null_0p2,
        0.4: near_null_0p4,
    }
    for load, packet in packet_by_load.items():
        if not packet:
            blockers.append(f"load_dependent_near_null_packet_missing:{load:g}")
        elif packet.get("status") != "ready":
            blockers.append(f"load_dependent_near_null_packet_not_ready:{load:g}")

    near_null_ready = bool(all(packet and packet.get("status") == "ready" for packet in packet_by_load.values()))
    ordered_rows = [rows[round(load, 10)] for load in REQUIRED_LOADS if round(load, 10) in rows]
    segments = [
        _segment(rows, 0.1, 0.2),
        _segment(rows, 0.2, 0.4),
        _segment(rows, 0.1, 0.4),
    ]
    superlinear_segments = [
        segment
        for segment in segments
        if segment["superlinear_translation_growth"] or segment["superlinear_drift_growth"]
    ]
    geometric_softening_signal = (
        "active_secondary"
        if superlinear_segments
        else "not_proven_from_f2h_load_response"
        if load_response_ready
        else "insufficient_load_response"
    )

    f2g_summary = _as_dict(f2g_audit.get("summary"))
    baseline_context = _as_dict(f2g_audit.get("near_null_context"))
    baseline_rows = _as_list(f2g_audit.get("dominant_dof_rows"))
    baseline_node_ids = sorted(
        {
            int(row["node_id"])
            for row in baseline_rows
            if isinstance(row, dict) and row.get("node_id") is not None
        }
    )
    packet_summaries = {
        "0.2": _near_null_summary(near_null_0p2) if near_null_0p2 else {"status": "missing"},
        "0.4": _near_null_summary(near_null_0p4) if near_null_0p4 else {"status": "missing"},
    }
    near_null_comparison: dict[str, Any] = {
        "baseline_load_scale": _as_float(baseline_context.get("load_scale"), None),
        "baseline_near_null_mode_count": _as_int(baseline_context.get("near_null_mode_count")),
        "baseline_dominant_dof_row_count": _as_int(f2g_summary.get("dominant_dof_row_count")),
        "baseline_dominant_node_count": len(baseline_node_ids),
        "requested_packet_loads": list(NEAR_NULL_PACKET_LOADS),
        "packet_summaries": packet_summaries,
        "comparison_ready": near_null_ready,
        "claim_boundary": (
            "A load-response trend is not a load-dependent modal comparison. "
            "Near-null packet comparison remains blocked until 0.2 and 0.4 packets are attached."
        ),
    }
    if near_null_ready:
        summary_0p2 = packet_summaries["0.2"]
        summary_0p4 = packet_summaries["0.4"]
        near_null_comparison["baseline_to_0p2_node_overlap"] = _node_overlap(
            baseline_node_ids,
            _as_list(summary_0p2.get("dominant_node_ids")),
        )
        near_null_comparison["baseline_to_0p4_node_overlap"] = _node_overlap(
            baseline_node_ids,
            _as_list(summary_0p4.get("dominant_node_ids")),
        )
        near_null_comparison["0p2_to_0p4_node_overlap"] = _node_overlap(
            _as_list(summary_0p2.get("dominant_node_ids")),
            _as_list(summary_0p4.get("dominant_node_ids")),
        )

    ready = bool(load_response_ready and near_null_ready and not blockers)
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_g1_load_dependent_near_null_geometric_stiffness_comparison.py"),
                f2h_status_path,
                f2h_continuation_path,
                f2g_audit_path,
                near_null_0p2_path,
                near_null_0p4_path,
            ],
            reused_evidence=True,
            reuse_policy=REUSE_POLICY,
            repo_root=repo_root,
        ),
        "status": "ready" if ready else "blocked",
        "contract_pass": ready,
        "reason_code": "PASS" if ready else "ERR_LOAD_DEPENDENT_NEAR_NULL_COMPARISON_INCOMPLETE",
        "promotes_g1_closure": False,
        "claim_boundary": (
            "This receipt compares non-promoting F2h load-response trends and optional "
            "load-dependent near-null packets. It does not close G1, prove full-load 1.0, "
            "or replace the consistent residual/Jacobian Newton and production ROCm/HIP gates."
        ),
        "summary_line": (
            "G1 load-dependent near-null/geometric-softening comparison: "
            f"{'READY' if ready else 'BLOCKED'} | "
            f"load_response_ready={load_response_ready} | "
            f"near_null_packets_ready={near_null_ready} | "
            f"geometric_softening_signal={geometric_softening_signal}"
        ),
        "summary": {
            "load_response_ready": load_response_ready,
            "near_null_packet_comparison_ready": near_null_ready,
            "geometric_softening_signal": geometric_softening_signal,
            "superlinear_segment_count": len(superlinear_segments),
            "missing_load_count": len(missing_loads),
            "missing_near_null_packet_count": sum(1 for packet in packet_by_load.values() if not packet),
            "blocker_count": len(blockers),
        },
        "load_response_rows": ordered_rows,
        "load_response_segments": segments,
        "near_null_comparison": near_null_comparison,
        "root_cause_signal_update": {
            "support_or_elastic_link_row_gap": "deprioritized_by_f2g_audit",
            "weak_restraint_or_geometric_softening": geometric_softening_signal,
            "load_dependent_near_null_comparison": (
                "ready" if near_null_ready else "blocked_missing_0p2_0p4_packets"
            ),
            "primary_next_lane": "consistent_residual_jacobian_newton_rocm_worker",
        },
        "next_actions": [
            {
                "id": "generate_load_dependent_near_null_packets_at_0p2_0p4",
                "status": "required" if not near_null_ready else "complete",
                "required_receipts": [
                    near_null_0p2_path.as_posix(),
                    near_null_0p4_path.as_posix(),
                ],
            },
            {
                "id": "compare_geometric_stiffness_contributions_at_0p2_0p4",
                "status": "blocked_until_near_null_packets_ready" if not near_null_ready else "ready",
                "acceptance": [
                    "0.2 and 0.4 near-null packets are ready",
                    "node/mode overlap and stiffness contribution deltas are recorded",
                    "comparison remains non-promoting unless full-load G1 gates close separately",
                ],
            },
            {
                "id": "continue_consistent_residual_jacobian_newton_rocm_worker_lane",
                "status": "required_for_g1_closure",
            },
        ],
        "blockers": sorted(dict.fromkeys(blockers)),
        "disallowed_promotions": [
            "no_G1_closure_claim",
            "no_full_load_1p0_claim",
            "no_modal_claim_without_0p2_0p4_near_null_packets",
            "no_geometric_softening_promotion_without_consistent_newton_gate",
        ],
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# G1 Load-Dependent Near-Null / Geometric-Softening Comparison",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `promotes_g1_closure`: `{payload['promotes_g1_closure']}`",
        f"- `geometric_softening_signal`: `{payload['summary']['geometric_softening_signal']}`",
        f"- `near_null_packet_comparison_ready`: `{payload['summary']['near_null_packet_comparison_ready']}`",
        "",
        "## Load Response Segments",
    ]
    for segment in payload["load_response_segments"]:
        lines.append(
            "- "
            f"`{segment['from_load_scale']}` -> `{segment['to_load_scale']}`: "
            f"translation_ratio=`{segment['max_translation_ratio']}`, "
            f"drift_ratio=`{segment['max_drift_ratio']}`, "
            f"superlinear_translation=`{segment['superlinear_translation_growth']}`, "
            f"superlinear_drift=`{segment['superlinear_drift_growth']}`"
        )
    lines.extend(["", "## Blockers"])
    for blocker in payload["blockers"]:
        lines.append(f"- `{blocker}`")
    lines.extend(["", "## Claim Boundary", "", payload["claim_boundary"], ""])
    return "\n".join(lines)


def write_comparison(
    *,
    repo_root: Path = ROOT,
    f2h_status_path: Path = DEFAULT_F2H_STATUS,
    f2h_continuation_path: Path = DEFAULT_F2H_CONTINUATION,
    f2g_audit_path: Path = DEFAULT_F2G_AUDIT,
    near_null_0p2_path: Path = DEFAULT_NEAR_NULL_0P2,
    near_null_0p4_path: Path = DEFAULT_NEAR_NULL_0P4,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_comparison(
        repo_root=repo_root,
        f2h_status_path=f2h_status_path,
        f2h_continuation_path=f2h_continuation_path,
        f2g_audit_path=f2g_audit_path,
        near_null_0p2_path=near_null_0p2_path,
        near_null_0p4_path=near_null_0p4_path,
    )
    resolved_out = out if out.is_absolute() else repo_root / out
    resolved_out_md = out_md if out_md.is_absolute() else repo_root / out_md
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_out_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_out_md.write_text(_markdown(payload), encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--f2h-status-json", type=Path, default=DEFAULT_F2H_STATUS)
    parser.add_argument("--f2h-continuation-json", type=Path, default=DEFAULT_F2H_CONTINUATION)
    parser.add_argument("--f2g-audit-json", type=Path, default=DEFAULT_F2G_AUDIT)
    parser.add_argument("--near-null-0p2-json", type=Path, default=DEFAULT_NEAR_NULL_0P2)
    parser.add_argument("--near-null-0p4-json", type=Path, default=DEFAULT_NEAR_NULL_0P4)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = write_comparison(
        repo_root=args.repo_root,
        f2h_status_path=args.f2h_status_json,
        f2h_continuation_path=args.f2h_continuation_json,
        f2g_audit_path=args.f2g_audit_json,
        near_null_0p2_path=args.near_null_0p2_json,
        near_null_0p4_path=args.near_null_0p4_json,
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
