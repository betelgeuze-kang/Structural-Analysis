#!/usr/bin/env python3
"""Project member-local hinge refresh rows from optimization changes and NPZ scope."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np


RUN_ID = "phase1-pbd-hinge-refresh-source"
SCHEMA_VERSION = "1.0"
SOURCE_KIND = "hinge_refresh_projected_from_optimization_changes"

DEFAULT_BASE_ROTATION_BY_TYPE = {
    "beam": 0.0080,
    "column": 0.0060,
    "wall": 0.0045,
    "slab": 0.0035,
    "connection": 0.0050,
}

REBAR_SENSITIVE_FAMILIES = {
    "rebar",
    "perimeter_frame",
    "connection_detailing",
    "beam_section",
}

GEOMETRY_AFFECTING_FAMILIES = {
    "beam_section",
    "wall_thickness",
    "slab_thickness",
    "perimeter_frame",
}

DETAILING_FAMILIES = {
    "connection_detailing",
    "detailing",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: object, default: int = -1) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _ordered_unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = str(value or "").strip()
        if token and token not in seen:
            out.append(token)
            seen.add(token)
    return out


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    if not path.exists():
        return {}
    try:
        data = np.load(path, allow_pickle=True)
    except Exception:
        return {}
    return {str(key): data[key] for key in data.files}


def _group_index_map(npz_state: dict[str, np.ndarray]) -> dict[int, list[int]]:
    group_index = np.asarray(npz_state.get("group_index_per_member", np.asarray([], dtype=np.int32)))
    out: dict[int, list[int]] = {}
    for idx, raw in enumerate(group_index.tolist()):
        key = _safe_int(raw, -1)
        if key < 0:
            continue
        out.setdefault(key, []).append(idx)
    return out


def _group_id_map(npz_state: dict[str, np.ndarray]) -> dict[str, list[int]]:
    group_ids = np.asarray(npz_state.get("group_ids", np.asarray([], dtype=object)), dtype=object)
    out: dict[str, list[int]] = {}
    for idx, raw in enumerate(group_ids.tolist()):
        key = str(raw or "").strip()
        if not key:
            continue
        out.setdefault(key, []).append(idx)
    return out


def _member_field(npz_state: dict[str, np.ndarray], key: str, idx: int, default: object = "") -> object:
    arr = np.asarray(npz_state.get(key, np.asarray([], dtype=object)))
    if idx >= int(arr.shape[0]):
        return default
    return arr[idx]


def _default_base_rotation(member_type: str) -> float:
    return float(DEFAULT_BASE_ROTATION_BY_TYPE.get(member_type, 0.0050))


def _is_rebar_sensitive(change: dict[str, Any]) -> bool:
    action_family = str(change.get("action_family", "") or "").strip().lower()
    before_ratio = _safe_float(change.get("before_rebar_ratio"), np.nan)
    after_ratio = _safe_float(change.get("after_rebar_ratio"), np.nan)
    if np.isfinite(before_ratio) and np.isfinite(after_ratio) and abs(after_ratio - before_ratio) > 1e-9:
        return True
    return action_family in REBAR_SENSITIVE_FAMILIES


def _refresh_rotations(
    *,
    member_type: str,
    base_plastic_rotation: float,
    dcr: float,
    action_family: str,
    before_ratio: float,
    after_ratio: float,
    rebar_sensitive: bool,
) -> tuple[float, float, float]:
    base = max(base_plastic_rotation, _default_base_rotation(member_type))
    dcr_factor = 1.0 + min(max(dcr - 1.0, 0.0), 1.0) * 0.08
    ratio_delta = abs(after_ratio - before_ratio) if np.isfinite(before_ratio) and np.isfinite(after_ratio) else 0.0
    ratio_factor = 1.0 - min(0.35, ratio_delta * 10.0)
    geometry_factor = 0.96 if action_family in GEOMETRY_AFFECTING_FAMILIES else 1.0
    detailing_factor = 0.97 if action_family in DETAILING_FAMILIES else 1.0
    sensitivity_factor = 0.98 if rebar_sensitive else 1.0
    refresh_scale = max(0.60, (ratio_factor * geometry_factor * detailing_factor * sensitivity_factor) / dcr_factor)
    yield_rotation = max(0.00035, base * 0.32 * refresh_scale)
    ultimate_rotation = max(yield_rotation * 1.85, base * max(0.78, 1.08 * refresh_scale))
    plastic_rotation_capacity = max(0.00050, ultimate_rotation - yield_rotation)
    return float(yield_rotation), float(ultimate_rotation), float(plastic_rotation_capacity)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--design-optimization-dataset",
        default="implementation/phase1/release/design_optimization/design_optimization_dataset_report.json",
    )
    parser.add_argument(
        "--design-optimization-npz",
        default="implementation/phase1/release/design_optimization/design_optimization_dataset.npz",
    )
    parser.add_argument(
        "--cost-reduction-changes",
        default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_changes.json",
    )
    parser.add_argument("--out", default="implementation/phase1/pbd_hinge_refresh_source.json")
    args = parser.parse_args()

    dataset_path = Path(args.design_optimization_dataset)
    dataset = _load_json(dataset_path)
    npz_path = Path(args.design_optimization_npz)
    npz_state = _load_npz(npz_path)
    changes_path = Path(args.cost_reduction_changes)
    change_payload = _load_json(changes_path)
    change_rows = [row for row in change_payload.get("changes", []) if isinstance(row, dict)]

    member_ids = np.asarray(npz_state.get("member_ids", np.asarray([], dtype=object)), dtype=object)
    group_index_map = _group_index_map(npz_state)
    group_id_map = _group_id_map(npz_state)

    hinge_rows: list[dict[str, Any]] = []
    matched_group_indices: list[int] = []
    unmatched_change_refs: list[str] = []
    group_id_fallback_match_count = 0
    group_index_match_count = 0
    rebar_sensitive_members: set[str] = set()

    for row in change_rows:
        change_group_index = _safe_int(row.get("group_index"), -1)
        change_group_id = str(row.get("group_id", "") or "").strip()
        matched_indices: list[int] = []
        match_mode = ""
        if change_group_index >= 0 and change_group_index in group_index_map:
            matched_indices = list(group_index_map.get(change_group_index, []))
            match_mode = "group_index"
            group_index_match_count += 1
        elif change_group_id and change_group_id in group_id_map:
            matched_indices = list(group_id_map.get(change_group_id, []))
            match_mode = "group_id"
            group_id_fallback_match_count += 1

        if not matched_indices:
            unmatched_change_refs.append(change_group_id or str(change_group_index))
            continue

        if change_group_index >= 0:
            matched_group_indices.append(change_group_index)
        action_family = str(row.get("action_family", "") or "").strip().lower()
        rebar_sensitive = _is_rebar_sensitive(row)
        before_ratio = _safe_float(row.get("before_rebar_ratio"), np.nan)
        after_ratio = _safe_float(row.get("after_rebar_ratio"), np.nan)

        for idx in matched_indices:
            member_id = str(member_ids[idx] if idx < int(member_ids.shape[0]) else "").strip()
            if not member_id:
                continue
            member_type = str(_member_field(npz_state, "member_types", idx, row.get("member_type", "")) or "").strip().lower()
            base_ratio = _safe_float(_member_field(npz_state, "rebar_ratio", idx, 0.0), 0.0)
            before_ratio_value = before_ratio if np.isfinite(before_ratio) else base_ratio
            after_ratio_value = after_ratio if np.isfinite(after_ratio) else before_ratio_value
            base_plastic_rotation = _safe_float(_member_field(npz_state, "member_plastic_rotation_rad", idx, 0.0), 0.0)
            governing_dcr = _safe_float(
                _member_field(npz_state, "member_governing_dcr", idx, _member_field(npz_state, "max_dcr", idx, 0.0)),
                0.0,
            )
            yield_rotation, ultimate_rotation, plastic_rotation_capacity = _refresh_rotations(
                member_type=member_type,
                base_plastic_rotation=base_plastic_rotation,
                dcr=governing_dcr,
                action_family=action_family,
                before_ratio=before_ratio_value,
                after_ratio=after_ratio_value,
                rebar_sensitive=rebar_sensitive,
            )
            hinge_row = {
                "member_id": member_id,
                "member_type": member_type,
                "group_id": change_group_id or str(_member_field(npz_state, "group_ids", idx, "")),
                "group_index": change_group_index,
                "action_family": action_family,
                "yield_rotation": yield_rotation,
                "yield_rotation_rad": yield_rotation,
                "ultimate_rotation": ultimate_rotation,
                "ultimate_rotation_rad": ultimate_rotation,
                "plastic_rotation_capacity": plastic_rotation_capacity,
                "theta_y": yield_rotation,
                "theta_u": ultimate_rotation,
                "ls_rotation": yield_rotation + plastic_rotation_capacity * 0.55,
                "cp_rotation": ultimate_rotation,
                "before_rebar_ratio": before_ratio_value,
                "after_rebar_ratio": after_ratio_value,
                "rebar_delta_ratio": after_ratio_value - before_ratio_value,
                "governing_dcr": governing_dcr,
                "member_hinge_state_source_before": str(_member_field(npz_state, "member_hinge_state_source", idx, "") or ""),
                "source_projection_match_mode": match_mode,
            }
            if rebar_sensitive:
                hinge_row["rebar_sensitive"] = True
                hinge_row["recomputed_from_rebar"] = True
                rebar_sensitive_members.add(member_id)
            hinge_rows.append(hinge_row)

    unique_member_ids = _ordered_unique([str(row.get("member_id", "") or "") for row in hinge_rows])
    matched_group_indices = sorted({idx for idx in matched_group_indices if idx >= 0})
    reason_code = "PASS" if hinge_rows else "ERR_NO_MEMBER_MATCH"
    reason = (
        "member-local hinge refresh rows were projected from optimization changes"
        if hinge_rows
        else "optimization changes did not match any active NPZ members"
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "design_optimization_dataset": str(dataset_path),
            "design_optimization_npz": str(npz_path),
            "cost_reduction_changes": str(changes_path),
        },
        "source_kind": SOURCE_KIND,
        "source_provenance": {
            "source_artifact_kind": SOURCE_KIND,
            "projection_backend": "optimization_change_group_index_projection",
            "dataset_contract_pass": bool(dataset.get("contract_pass", False)),
            "change_row_count": int(len(change_rows)),
            "npz_member_count": int(member_ids.shape[0]),
            "group_index_match_count": int(group_index_match_count),
            "group_id_fallback_match_count": int(group_id_fallback_match_count),
            "matched_group_index_count": int(len(matched_group_indices)),
            "unique_member_count": int(len(unique_member_ids)),
            "rebar_sensitive_member_count": int(len(rebar_sensitive_members)),
            "unmatched_change_refs_head": unmatched_change_refs[:16],
        },
        "summary": {
            "source_artifact_kind": SOURCE_KIND,
            "source_mode": "projected_member_local_hinge_refresh",
            "change_row_count": int(len(change_rows)),
            "matched_group_index_count": int(len(matched_group_indices)),
            "hinge_refresh_row_count": int(len(hinge_rows)),
            "unique_member_count": int(len(unique_member_ids)),
            "rebar_sensitive_member_count": int(len(rebar_sensitive_members)),
        },
        "checks": {
            "npz_present": bool(npz_state),
            "changes_present": bool(change_rows),
            "member_rows_present": bool(hinge_rows),
            "rebar_sensitive_member_present": bool(rebar_sensitive_members),
        },
        "contract_pass": bool(hinge_rows),
        "reason_code": reason_code,
        "reason": reason,
        "hinge_refresh_rows": hinge_rows,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote PBD hinge refresh source: {out}")


if __name__ == "__main__":
    main()
