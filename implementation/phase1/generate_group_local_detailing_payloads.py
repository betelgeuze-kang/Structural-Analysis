#!/usr/bin/env python3
"""Project group-local detailing payloads from active optimization changes."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from export_design_optimization_to_mgt import (
    _as_float,
    _build_model_maps,
    _infer_action_family,
    _load_group_element_map,
    _load_json,
    _resolve_group_element_ids_with_source,
    _write_json,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _group_signature(group_id: str) -> str:
    parts = str(group_id or "").split(":")
    return str(parts[-1]).strip() if parts else ""


def _group_zone_label(group_id: str) -> str:
    parts = str(group_id or "").split(":")
    return str(parts[1]).strip() if len(parts) >= 2 else ""


def _group_member_type(group_id: str) -> str:
    parts = str(group_id or "").split(":")
    return str(parts[3]).strip().lower() if len(parts) >= 4 else ""


def _resolve_detailing_element_ids(
    *,
    row: dict[str, Any],
    group_to_elements: dict[str, list[int]],
) -> tuple[list[int], str]:
    element_ids, mapping_source = _resolve_group_element_ids_with_source(row=row, group_to_elements=group_to_elements)
    if element_ids:
        return element_ids, mapping_source

    group_id = str(row.get("group_id", "") or "")
    member_type = str(row.get("member_type", "") or "").strip().lower()
    zone_label = str(row.get("zone_label", "") or "").strip().lower() or _group_zone_label(group_id).lower()
    signature = _group_signature(group_id)
    candidates = [
        candidate_group_id
        for candidate_group_id in group_to_elements.keys()
        if _group_signature(candidate_group_id) == signature
        and _group_zone_label(candidate_group_id).lower() == zone_label
        and _group_member_type(candidate_group_id) == member_type
    ]
    if len(candidates) == 1:
        return [int(v) for v in group_to_elements.get(candidates[0], [])], "signature_zone_member_fallback"
    return [], "unmapped_group_id"


def main() -> int:
    p = argparse.ArgumentParser(description="Project group-local detailing payloads from optimization deltas.")
    p.add_argument("--parsed-model-json", default="implementation/phase1/open_data/midas/midas_model.json")
    p.add_argument("--dataset-npz", default="implementation/phase1/release/design_optimization/design_optimization_dataset.npz")
    p.add_argument("--changes-json", default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_changes.json")
    p.add_argument(
        "--projection-json-out",
        default="implementation/phase1/open_data/midas/midas_generator_33.detailing_payload_projection.json",
    )
    args = p.parse_args()

    model_json_path = Path(args.parsed_model_json)
    dataset_npz_path = Path(args.dataset_npz)
    changes_json_path = Path(args.changes_json)
    projection_json_out_path = Path(args.projection_json_out)

    reason_code = "PASS"
    reason = "projected internal group-local detailing payloads were generated"
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

    if reason_code == "PASS":
        changes_payload = _load_json(changes_json_path)
        changes = changes_payload.get("changes") if isinstance(changes_payload.get("changes"), list) else []
        group_to_elements = _load_group_element_map(dataset_npz_path)
        element_map, _ = _build_model_maps(model_json_path)

        for row in changes:
            if not isinstance(row, dict):
                continue
            action_family = _infer_action_family(row)
            if action_family != "detailing":
                continue

            before_detailing = _as_float(row.get("before_detailing_quality"))
            after_detailing = _as_float(row.get("after_detailing_quality"))
            if (
                before_detailing is None
                or after_detailing is None
                or abs(float(after_detailing) - float(before_detailing)) <= 1.0e-12
            ):
                blocked_rows.append(
                    {
                        "group_id": str(row.get("group_id", "") or ""),
                        "member_type": str(row.get("member_type", "") or "").strip().lower(),
                        "action_family": action_family,
                        "reason": "invalid_detailing_delta",
                    }
                )
                continue

            group_id = str(row.get("group_id", "") or "")
            member_type = str(row.get("member_type", "") or "").strip().lower()
            element_ids, mapping_source = _resolve_detailing_element_ids(
                row=row,
                group_to_elements=group_to_elements,
            )
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
                    if isinstance(elem, dict) and elem.get("material_id") is not None
                }
            )
            section_ids = sorted(
                {
                    int(elem.get("section_id"))
                    for eid in element_ids
                    for elem in [element_map.get(int(eid))]
                    if isinstance(elem, dict) and elem.get("section_id") is not None
                }
            )
            projected_rows.append(
                {
                    "group_id": group_id,
                    "member_type": member_type,
                    "action_family": action_family,
                    "payload_present": True,
                    "payload_basis": "detailing_quality_delta_projection",
                    "payload_source_class": "internal_group_local_detailing_projection",
                    "mapping_source": str(mapping_source),
                    "element_id_count": int(len(element_ids)),
                    "element_ids_head": [int(v) for v in element_ids[:16]],
                    "section_ids": [int(v) for v in section_ids],
                    "material_ids": [int(v) for v in material_ids],
                    "section_signature": _group_signature(group_id),
                    "zone_label": str(row.get("zone_label", "") or ""),
                    "story_band": int(row.get("story_band", 0) or 0),
                    "semantic_group": str(row.get("semantic_group", "") or ""),
                    "action_name": str(row.get("action_name", "") or ""),
                    "baseline_detailing_quality": float(before_detailing),
                    "target_detailing_quality": float(after_detailing),
                    "detailing_quality_delta": float(after_detailing) - float(before_detailing),
                    "baseline_rebar_ratio": _as_float(row.get("before_rebar_ratio")),
                    "target_rebar_ratio": _as_float(row.get("after_rebar_ratio")),
                    "review_priority": "medium",
                    "followup_type": "detailing_manual_review",
                    "review_owner": "licensed_engineer",
                    "validation_boundary": "internal_engine_complete_external_validation_optional",
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
        "source_kind": "internal_group_local_detailing_payload_projection",
        "summary": {
            "group_local_detailing_payload_row_count": int(len(projected_rows)),
            "group_local_detailing_payload_available_count": int(
                sum(1 for row in projected_rows if bool(row.get("payload_present", False)))
            ),
            "blocked_group_local_detailing_payload_row_count": int(len(blocked_rows)),
            "blocked_reason_counts": {
                str(k): int(v) for k, v in sorted(Counter(str(row.get("reason", "")) for row in blocked_rows).items())
            },
            "projected_member_type_counts": {
                str(k): int(v) for k, v in sorted(Counter(str(row.get("member_type", "")) for row in projected_rows).items())
            },
            "projected_zone_label_counts": {
                str(k): int(v) for k, v in sorted(Counter(str(row.get("zone_label", "")) for row in projected_rows).items())
            },
        },
        "contract_pass": bool(reason_code == "PASS" and projected_rows),
        "reason_code": "PASS" if projected_rows else ("ERR_NO_PROJECTABLE_DETAILING_GROUPS" if reason_code == "PASS" else reason_code),
        "reason": reason if projected_rows else ("no detailing groups were projectable" if reason_code == "PASS" else reason),
        "group_local_detailing_payloads": projected_rows,
        "blocked_group_local_detailing_payload_rows": blocked_rows,
    }
    _write_json(projection_json_out_path, payload)
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
