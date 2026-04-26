#!/usr/bin/env python3
"""Generate a bounded PBD hinge-refresh artifact from optional upstream rows."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np


RUN_ID = "phase1-pbd-hinge-refresh-artifact"
SCHEMA_VERSION = "1.0"

REASONS = {
    "PASS": "rebar-sensitive dynamic hinge-refresh rows are attached for optimized members",
    "ERR_SOURCE_MISSING": "no hinge-refresh source rows are attached",
    "ERR_SOURCE_ROWS_INVALID": "hinge-refresh source exists but does not contain valid member-local hinge rows",
    "ERR_SOURCE_MEMBER_OVERLAP_MISSING": "hinge-refresh source rows do not overlap optimized member ids",
    "ERR_REBAR_SENSITIVE_REFRESH_MISSING": "hinge-refresh source rows overlap members but do not prove rebar-sensitive refresh",
}

SOURCE_CONTAINER_KEYS = (
    "hinge_refresh",
    "pbd_hinge_refresh",
    "solver_export",
    "solver_results",
    "results",
    "artifacts",
)

SOURCE_ROW_KEYS = (
    "hinge_rows",
    "hinge_refresh_rows",
    "member_hinge_rows",
    "plastic_hinges",
    "updated_hinge_rows",
    "rows",
)

HingeParamKeys = (
    "yield_rotation",
    "yield_rotation_rad",
    "ultimate_rotation",
    "ultimate_rotation_rad",
    "plastic_rotation_capacity",
    "theta_y",
    "theta_u",
    "ls_rotation",
    "cp_rotation",
    "m_phi_yield",
    "m_phi_ultimate",
    "curvature_yield",
    "curvature_ultimate",
)

RebarSensitiveKeys = (
    "rebar_sensitive",
    "updated_after_optimization",
    "optimization_updated",
    "recomputed_from_rebar",
    "rebar_delta_applied",
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"1", "y", "yes", "true", "on"}:
            return True
        if token in {"0", "n", "no", "false", "off"}:
            return False
    try:
        return bool(value)
    except Exception:
        return bool(default)


def _extract_rows(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    for key in SOURCE_ROW_KEYS:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)], "direct_rows"
    for key in SOURCE_CONTAINER_KEYS:
        nested = payload.get(key)
        if not isinstance(nested, dict):
            continue
        rows, mode = _extract_rows(nested)
        if rows:
            return rows, f"nested:{key}:{mode}"
    return [], "missing"


def _candidate_member_ids(dataset: dict[str, Any]) -> list[str]:
    rows = dataset.get("rows_head", [])
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        member_id = str(row.get("member_id", "") or "").strip()
        if member_id and member_id not in seen:
            out.append(member_id)
            seen.add(member_id)
    return out


def _default_npz_path(dataset_report: Path) -> Path:
    if dataset_report.name.endswith("_report.json"):
        return dataset_report.with_name(dataset_report.name.replace("_report.json", ".npz"))
    return dataset_report.with_suffix(".npz")


def _load_npz_scope(path: Path) -> tuple[list[str], list[str]]:
    if not path.exists():
        return [], []
    try:
        data = np.load(path, allow_pickle=True)
    except Exception:
        return [], []
    member_ids = [str(value).strip() for value in np.asarray(data.get("member_ids", np.asarray([], dtype=object))).tolist()]
    group_ids = [str(value).strip() for value in np.asarray(data.get("group_ids", np.asarray([], dtype=object))).tolist()]
    return member_ids, group_ids


def _ordered_unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = str(value or "").strip()
        if token and token not in seen:
            out.append(token)
            seen.add(token)
    return out


def _load_change_group_ids(path: Path) -> tuple[list[str], int]:
    payload = _load_json(path)
    rows = payload.get("changes", [])
    if not isinstance(rows, list):
        return [], 0
    group_ids = [
        str(row.get("group_id", "") or "").strip()
        for row in rows
        if isinstance(row, dict) and str(row.get("group_id", "") or "").strip()
    ]
    return _ordered_unique(group_ids), int(sum(1 for row in rows if isinstance(row, dict)))


def _candidate_member_scope(
    dataset: dict[str, Any],
    *,
    dataset_npz_path: Path,
    cost_reduction_changes_path: Path,
) -> dict[str, Any]:
    rows_head_member_ids = _candidate_member_ids(dataset)
    npz_member_ids, npz_group_ids = _load_npz_scope(dataset_npz_path)
    optimized_group_ids, change_row_count = _load_change_group_ids(cost_reduction_changes_path)
    optimized_group_id_set = set(optimized_group_ids)
    optimized_member_ids = _ordered_unique(
        [
            str(npz_member_ids[idx]).strip()
            for idx in range(min(len(npz_member_ids), len(npz_group_ids)))
            if str(npz_group_ids[idx]).strip() in optimized_group_id_set and str(npz_member_ids[idx]).strip()
        ]
    )
    if optimized_member_ids:
        candidate_member_ids = optimized_member_ids
        candidate_scope_mode = "optimized_groups_from_npz"
    elif npz_member_ids:
        candidate_member_ids = _ordered_unique(npz_member_ids)
        candidate_scope_mode = "dataset_npz_member_ids"
    else:
        candidate_member_ids = rows_head_member_ids
        candidate_scope_mode = "dataset_rows_head_member_ids"
    return {
        "candidate_member_ids": candidate_member_ids,
        "candidate_scope_mode": candidate_scope_mode,
        "rows_head_member_count": int(len(rows_head_member_ids)),
        "npz_member_count": int(len(_ordered_unique(npz_member_ids))),
        "optimized_group_count": int(len(optimized_group_ids)),
        "optimized_target_member_count": int(len(optimized_member_ids)),
        "cost_change_row_count": int(change_row_count),
        "design_optimization_npz_present": bool(dataset_npz_path.exists() and bool(npz_member_ids)),
    }


def _is_valid_row(row: dict[str, Any]) -> bool:
    member_id = str(row.get("member_id", "") or "").strip()
    if not member_id:
        return False
    return any(row.get(key) not in {None, ""} for key in HingeParamKeys)


def _is_rebar_sensitive(row: dict[str, Any]) -> bool:
    return any(_safe_bool(row.get(key), False) for key in RebarSensitiveKeys)


def _source_kind(payload: dict[str, Any]) -> str:
    source_provenance = payload.get("source_provenance", {})
    if not isinstance(source_provenance, dict):
        source_provenance = {}
    return str(
        payload.get("source_kind")
        or source_provenance.get("source_kind")
        or source_provenance.get("source_artifact_kind")
        or payload.get("kind")
        or "hinge_refresh_source_json"
    ).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--design-optimization-dataset",
        default="implementation/phase1/release/design_optimization/design_optimization_dataset_report.json",
    )
    parser.add_argument("--design-optimization-npz", default="")
    parser.add_argument(
        "--cost-reduction-changes",
        default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_changes.json",
    )
    parser.add_argument(
        "--source-input",
        default="",
        help="Optional upstream JSON with member-local hinge refresh rows.",
    )
    parser.add_argument("--out", default="implementation/phase1/pbd_hinge_refresh_artifact.json")
    args = parser.parse_args()

    dataset_path = Path(args.design_optimization_dataset)
    dataset = _load_json(dataset_path)
    dataset_npz_path = Path(args.design_optimization_npz) if str(args.design_optimization_npz).strip() else _default_npz_path(dataset_path)
    cost_reduction_changes_path = Path(args.cost_reduction_changes)
    candidate_scope = _candidate_member_scope(
        dataset,
        dataset_npz_path=dataset_npz_path,
        cost_reduction_changes_path=cost_reduction_changes_path,
    )
    candidate_member_ids = list(candidate_scope["candidate_member_ids"])
    candidate_member_id_set = set(candidate_member_ids)
    source_input_path = Path(args.source_input) if str(args.source_input).strip() else Path()
    source_input_present = bool(str(args.source_input).strip()) and source_input_path.exists()
    source_payload = _load_json(source_input_path) if source_input_present else {}
    source_rows, source_bundle_mode = _extract_rows(source_payload) if source_input_present else ([], "missing")
    valid_source_rows = [row for row in source_rows if _is_valid_row(row)]
    overlap_rows = [
        row for row in valid_source_rows if str(row.get("member_id", "") or "").strip() in candidate_member_id_set
    ]
    rebar_sensitive_rows = [row for row in overlap_rows if _is_rebar_sensitive(row)]
    overlap_member_ids = sorted({str(row.get("member_id", "") or "").strip() for row in overlap_rows if str(row.get("member_id", "") or "").strip()})
    rebar_sensitive_member_ids = sorted(
        {str(row.get("member_id", "") or "").strip() for row in rebar_sensitive_rows if str(row.get("member_id", "") or "").strip()}
    )

    if not source_input_present:
        reason_code = "ERR_SOURCE_MISSING"
        source_mode = "proxy_only_dataset_heuristic"
        hinge_state_mode = "proxy_only_hinge_visualization"
    elif not valid_source_rows:
        reason_code = "ERR_SOURCE_ROWS_INVALID"
        source_mode = "source_present_no_valid_rows"
        hinge_state_mode = "proxy_only_hinge_visualization"
    elif not overlap_rows:
        reason_code = "ERR_SOURCE_MEMBER_OVERLAP_MISSING"
        source_mode = "member_local_refresh_no_overlap"
        hinge_state_mode = "proxy_only_hinge_visualization"
    elif not rebar_sensitive_rows:
        reason_code = "ERR_REBAR_SENSITIVE_REFRESH_MISSING"
        source_mode = "member_local_refresh_without_rebar_delta"
        hinge_state_mode = "proxy_only_hinge_visualization"
    else:
        reason_code = "PASS"
        source_mode = "rebar_sensitive_member_local_refresh"
        hinge_state_mode = "computed_member_local_hinge_refresh"

    contract_pass = reason_code == "PASS"
    reason = REASONS[reason_code]
    if reason_code == "ERR_SOURCE_MISSING":
        if int(candidate_scope["optimized_target_member_count"]) > 0:
            reason = (
                "no hinge-refresh source rows are attached for optimized member scope "
                f"({int(candidate_scope['optimized_target_member_count'])} members across "
                f"{int(candidate_scope['optimized_group_count'])} changed groups)"
            )
        else:
            reason = (
                "no hinge-refresh source rows are attached for active dataset scope "
                f"({int(len(candidate_member_ids))} candidate members via {str(candidate_scope['candidate_scope_mode'])})"
            )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "design_optimization_dataset": str(dataset_path),
            "design_optimization_npz": str(dataset_npz_path),
            "cost_reduction_changes": str(cost_reduction_changes_path),
            "source_input": str(source_input_path) if source_input_present else str(args.source_input or ""),
        },
        "source_provenance": {
            "source_artifact_present": bool(source_input_present),
            "source_artifact_kind": _source_kind(source_payload),
            "source_bundle_mode": source_bundle_mode,
            "source_row_count": int(len(source_rows)),
            "valid_source_row_count": int(len(valid_source_rows)),
            "candidate_member_count": int(len(candidate_member_ids)),
            "candidate_scope_mode": str(candidate_scope["candidate_scope_mode"]),
            "dataset_rows_head_member_count": int(candidate_scope["rows_head_member_count"]),
            "dataset_npz_member_count": int(candidate_scope["npz_member_count"]),
            "optimized_group_count": int(candidate_scope["optimized_group_count"]),
            "optimized_target_member_count": int(candidate_scope["optimized_target_member_count"]),
            "cost_change_row_count": int(candidate_scope["cost_change_row_count"]),
            "overlap_member_count": int(len(overlap_member_ids)),
            "rebar_sensitive_member_count": int(len(rebar_sensitive_member_ids)),
            "candidate_member_ids_head": candidate_member_ids[:16],
            "overlap_member_ids_head": overlap_member_ids[:16],
            "rebar_sensitive_member_ids_head": rebar_sensitive_member_ids[:16],
        },
        "summary": {
            "hinge_state_mode": hinge_state_mode,
            "source_mode": source_mode,
            "source_artifact_kind": _source_kind(source_payload),
            "source_bundle_mode": source_bundle_mode,
            "source_row_count": int(len(source_rows)),
            "valid_source_row_count": int(len(valid_source_rows)),
            "design_opt_member_count": int(len(candidate_member_ids)),
            "candidate_scope_mode": str(candidate_scope["candidate_scope_mode"]),
            "dataset_rows_head_member_count": int(candidate_scope["rows_head_member_count"]),
            "dataset_npz_member_count": int(candidate_scope["npz_member_count"]),
            "optimized_group_count": int(candidate_scope["optimized_group_count"]),
            "optimized_target_member_count": int(candidate_scope["optimized_target_member_count"]),
            "cost_change_row_count": int(candidate_scope["cost_change_row_count"]),
            "overlap_member_count": int(len(overlap_member_ids)),
            "rebar_sensitive_member_count": int(len(rebar_sensitive_member_ids)),
            "reason": reason,
        },
        "checks": {
            "source_artifact_present": bool(source_input_present),
            "valid_source_rows_present": bool(len(valid_source_rows) > 0),
            "member_overlap_present": bool(len(overlap_member_ids) > 0),
            "rebar_sensitive_refresh_present": bool(len(rebar_sensitive_member_ids) > 0),
            "optimized_scope_present": bool(int(candidate_scope["optimized_target_member_count"]) > 0),
            "design_optimization_npz_present": bool(candidate_scope["design_optimization_npz_present"]),
        },
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": reason,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote PBD hinge refresh artifact: {out}")


if __name__ == "__main__":
    main()
