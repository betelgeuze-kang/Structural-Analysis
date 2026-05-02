#!/usr/bin/env python3
"""Project group-local rebar payloads from active optimization changes."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from export_design_optimization_to_mgt import (  # noqa: E402
    _as_float,
    _as_int,
    _build_model_maps,
    _infer_action_family,
    _infer_fy_from_text,
    _load_group_element_map,
    _load_json,
    _load_material_payload_rows_with_fallback,
    _resolve_group_element_ids_with_source,
    _write_json,
)


BAR_SERIES = ["D10", "D13", "D16", "D19", "D22", "D25", "D29", "D32"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_material_type_by_id(model_json_path: Path) -> dict[int, str]:
    model = _load_json(model_json_path)
    materials = model.get("model", {}).get("materials", []) if isinstance(model.get("model"), dict) else []
    out: dict[int, str] = {}
    for row in materials if isinstance(materials, list) else []:
        if not isinstance(row, dict):
            continue
        material_id = _as_int(row.get("id"))
        if material_id is None:
            continue
        out[int(material_id)] = str(row.get("name", "") or "").strip().upper()
    return out


def _load_section_geometry_by_signature(model_json_path: Path) -> dict[str, tuple[float, float]]:
    model = _load_json(model_json_path)
    metadata = model.get("model", {}).get("metadata", {}) if isinstance(model.get("model"), dict) else {}
    rows = metadata.get("design_sections", []) if isinstance(metadata, dict) else []
    out: dict[str, tuple[float, float]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        row_tokens = row.get("row_tokens") if isinstance(row.get("row_tokens"), list) else []
        first = row_tokens[0] if row_tokens and isinstance(row_tokens[0], list) else []
        if len(first) < 16:
            continue
        signature = str(first[2]).strip()
        width_m = _as_float(first[14])
        depth_m = _as_float(first[15])
        if not signature or width_m is None or depth_m is None:
            continue
        out[signature] = (float(width_m), float(depth_m))
    return out


def _group_signature(group_id: str) -> str:
    parts = str(group_id or "").split(":")
    return str(parts[-1]).strip() if parts else ""


def _default_rebar_code_context(model_json_path: Path) -> tuple[str, float]:
    model = _load_json(model_json_path)
    metadata = model.get("model", {}).get("metadata", {}) if isinstance(model.get("model"), dict) else {}
    rows = metadata.get("rebar_material_codes", []) if isinstance(metadata, dict) else []
    default_code = "GB10(RC)"
    default_fy = 400.0
    if isinstance(rows, list) and rows:
        first = rows[0]
        if isinstance(first, dict):
            tokens = first.get("tokens") if isinstance(first.get("tokens"), list) else []
            if len(tokens) >= 1 and str(tokens[0]).strip():
                default_code = str(tokens[0]).strip()
            if len(tokens) >= 2:
                fy = _infer_fy_from_text(tokens[1])
                if fy is not None and fy > 0.0:
                    default_fy = float(fy)
    return default_code, default_fy


def _select_bar_pair(
    *,
    member_type: str,
    target_rebar_ratio: float,
    width_m: float,
    depth_m: float,
) -> tuple[str, str]:
    member = str(member_type or "").strip().lower()
    if member in {"wall", "slab", "foundation"}:
        thresholds = [0.0045, 0.0075, 0.0120, 0.0200, 0.0300, 0.0450, 0.0600]
        start_index = 0
        if max(width_m, depth_m) >= 1.0:
            start_index += 1
        if min(width_m, depth_m) >= 0.35:
            start_index += 1
    else:
        thresholds = [0.0180, 0.0280, 0.0400, 0.0550, 0.0700, 0.0850, 0.1000]
        start_index = 1
        if max(width_m, depth_m) >= 0.7:
            start_index += 1
    idx = len(thresholds) - 1
    for pos, limit in enumerate(thresholds):
        if float(target_rebar_ratio) <= float(limit):
            idx = pos
            break
    main_idx = min(len(BAR_SERIES) - 1, max(0, start_index + idx))
    sub_idx = max(0, main_idx - 1)
    return BAR_SERIES[main_idx], BAR_SERIES[sub_idx]


def _supports_projected_rebar_payload(material_types: list[str], *, action_family: str) -> bool:
    normalized = {str(v or "").strip().upper() for v in material_types if str(v or "").strip()}
    if not normalized:
        return False
    if normalized <= {"CONC"}:
        return True
    if str(action_family or "").strip() == "perimeter_frame" and normalized <= {"SRC"}:
        return True
    return False


def main() -> int:
    p = argparse.ArgumentParser(description="Project group-local rebar payloads from optimization deltas.")
    p.add_argument("--parsed-model-json", default="implementation/phase1/open_data/midas/midas_model.json")
    p.add_argument("--dataset-npz", default="implementation/phase1/release/design_optimization/design_optimization_dataset.npz")
    p.add_argument("--changes-json", default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_changes.json")
    p.add_argument(
        "--projection-json-out",
        default="implementation/phase1/open_data/midas/midas_generator_33.rebar_payload_projection.json",
    )
    args = p.parse_args()

    model_json_path = Path(args.parsed_model_json)
    dataset_npz_path = Path(args.dataset_npz)
    changes_json_path = Path(args.changes_json)
    projection_json_out_path = Path(args.projection_json_out)

    reason_code = "PASS"
    reason = "projected internal group-local rebar payloads were generated"
    if not model_json_path.exists():
        reason_code = "ERR_PARSED_MODEL_MISSING"
        reason = "parsed MIDAS model JSON was missing"
    elif not dataset_npz_path.exists():
        reason_code = "ERR_DATASET_MISSING"
        reason = "design optimization dataset NPZ was missing"
    elif not changes_json_path.exists():
        reason_code = "ERR_CHANGES_MISSING"
        reason = "design optimization changes JSON was missing"

    projected_rows: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []
    design_material_rebar_payloads: list[dict[str, Any]] = []

    if reason_code == "PASS":
        changes_payload = _load_json(changes_json_path)
        changes = changes_payload.get("changes") if isinstance(changes_payload.get("changes"), list) else []
        design_material_rebar_payloads = _load_material_payload_rows_with_fallback(model_json_path)
        default_rbcode, default_fy = _default_rebar_code_context(model_json_path)
        group_to_elements = _load_group_element_map(dataset_npz_path)
        element_map, _ = _build_model_maps(model_json_path)
        material_type_by_id = _load_material_type_by_id(model_json_path)
        section_geometry_by_signature = _load_section_geometry_by_signature(model_json_path)

        for row in changes:
            if not isinstance(row, dict):
                continue
            action_family = _infer_action_family(row)
            if action_family not in {"rebar", "perimeter_frame"}:
                continue
            before_rebar = _as_float(row.get("before_rebar_ratio"))
            after_rebar = _as_float(row.get("after_rebar_ratio"))
            if before_rebar is None or after_rebar is None or abs(float(after_rebar) - float(before_rebar)) <= 1.0e-12:
                blocked_rows.append(
                    {
                        "group_id": str(row.get("group_id", "") or ""),
                        "member_type": str(row.get("member_type", "") or "").strip().lower(),
                        "action_family": action_family,
                        "reason": "invalid_rebar_delta",
                    }
                )
                continue

            group_id = str(row.get("group_id", "") or "")
            member_type = str(row.get("member_type", "") or "").strip().lower()
            element_ids, mapping_source = _resolve_group_element_ids_with_source(row=row, group_to_elements=group_to_elements)
            if not element_ids:
                blocked_rows.append(
                    {
                        "group_id": group_id,
                        "member_type": member_type,
                        "action_family": action_family,
                        "reason": "unmapped_group_to_elements",
                    }
                )
                continue

            material_ids = sorted(
                {
                    int(elem.get("material_id"))
                    for eid in element_ids
                    for elem in [element_map.get(int(eid))]
                    if isinstance(elem, dict) and _as_int(elem.get("material_id")) is not None
                }
            )
            material_types = sorted({material_type_by_id.get(int(mid), "") for mid in material_ids})
            if not material_ids:
                blocked_rows.append(
                    {
                        "group_id": group_id,
                        "member_type": member_type,
                        "action_family": action_family,
                        "reason": "unmapped_elements_to_materials",
                    }
                )
                continue
            if not _supports_projected_rebar_payload(material_types, action_family=action_family):
                blocked_rows.append(
                    {
                        "group_id": group_id,
                        "member_type": member_type,
                        "action_family": action_family,
                        "reason": "non_concrete_material_scope",
                        "material_ids": [int(v) for v in material_ids],
                        "material_types": material_types,
                    }
                )
                continue

            signature = _group_signature(group_id)
            width_m, depth_m = section_geometry_by_signature.get(signature, (0.6, 0.3))
            rbmain, rbsub = _select_bar_pair(
                member_type=member_type,
                target_rebar_ratio=float(after_rebar),
                width_m=float(width_m),
                depth_m=float(depth_m),
            )
            projected_rows.append(
                {
                    "group_id": group_id,
                    "member_type": member_type,
                    "action_family": action_family,
                    "payload_present": True,
                    "payload_basis": "target_rebar_ratio_projection",
                    "payload_source_class": "internal_ratio_projected_payload",
                    "mapping_source": str(mapping_source),
                    "element_id_count": int(len(element_ids)),
                    "material_ids": [int(v) for v in material_ids],
                    "material_types": material_types,
                    "section_signature": signature,
                    "section_width_m": float(width_m),
                    "section_depth_m": float(depth_m),
                    "baseline_rebar_ratio": float(before_rebar),
                    "target_rebar_ratio": float(after_rebar),
                    "rbcode": default_rbcode,
                    "rbmain": rbmain,
                    "rbsub": rbsub,
                    "fy_r": float(default_fy),
                    "fys": float(default_fy),
                }
            )

    payload = {
        "schema_version": "1.0",
        "generated_at": _utc_now(),
        "inputs": {
            "parsed_model_json": str(model_json_path),
            "dataset_npz": str(dataset_npz_path),
            "changes_json": str(changes_json_path),
        },
        "source_kind": "internal_group_local_rebar_payload_projection",
        "summary": {
            "design_material_rebar_payload_row_count": int(len(design_material_rebar_payloads)),
            "design_material_rebar_payload_available_count": int(
                sum(1 for row in design_material_rebar_payloads if bool(row.get("payload_present", False)))
            ),
            "group_local_rebar_payload_row_count": int(len(projected_rows)),
            "group_local_rebar_payload_available_count": int(
                sum(1 for row in projected_rows if bool(row.get("payload_present", False)))
            ),
            "blocked_group_local_payload_row_count": int(len(blocked_rows)),
            "blocked_reason_counts": {
                str(k): int(v) for k, v in sorted(Counter(str(row.get("reason", "")) for row in blocked_rows).items())
            },
            "projected_action_family_counts": {
                str(k): int(v) for k, v in sorted(Counter(str(row.get("action_family", "")) for row in projected_rows).items())
            },
            "projected_member_type_counts": {
                str(k): int(v) for k, v in sorted(Counter(str(row.get("member_type", "")) for row in projected_rows).items())
            },
        },
        "contract_pass": bool(reason_code == "PASS" and projected_rows),
        "reason_code": "PASS" if projected_rows else ("ERR_NO_PROJECTABLE_GROUPS" if reason_code == "PASS" else reason_code),
        "reason": reason if projected_rows else ("no concrete-backed rebar groups were projectable" if reason_code == "PASS" else reason),
        "design_material_rebar_payloads": design_material_rebar_payloads,
        "group_local_rebar_payloads": projected_rows,
        "blocked_group_local_payload_rows": blocked_rows,
    }
    _write_json(projection_json_out_path, payload)
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
