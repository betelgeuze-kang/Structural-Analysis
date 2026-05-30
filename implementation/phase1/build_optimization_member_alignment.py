#!/usr/bin/env python3
"""Member ID alignment contract for baseline vs optimized models (gap §1.4)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "design-optimization-member-alignment.v1"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _element_ids(payload: dict[str, Any]) -> set[str]:
    model = payload.get("model") if isinstance(payload.get("model"), dict) else payload
    elements = model.get("elements") if isinstance(model.get("elements"), list) else []
    ids: set[str] = set()
    for element in elements:
        if not isinstance(element, dict):
            continue
        for key in ("id", "member_id"):
            value = str(element.get(key) or "").strip()
            if value:
                ids.add(value)
                break
    return ids


def _merge_actions(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        if str(change.get("action_name") or "").strip() != "group_merge":
            continue
        rows.append(
            {
                "group_id": str(change.get("group_id") or ""),
                "group_index": change.get("group_index"),
                "story_band": change.get("story_band"),
                "zone_label": str(change.get("zone_label") or ""),
            }
        )
    return rows


def build_member_alignment(
    *,
    baseline_payload: dict[str, Any],
    optimized_payload: dict[str, Any],
    changes: list[dict[str, Any]] | None = None,
    baseline_path: str = "",
    optimized_path: str = "",
) -> dict[str, Any]:
    baseline_ids = _element_ids(baseline_payload)
    optimized_ids = _element_ids(optimized_payload)
    removed = sorted(baseline_ids - optimized_ids)
    added = sorted(optimized_ids - baseline_ids)
    retained = sorted(baseline_ids & optimized_ids)
    merge_rows = _merge_actions(changes or [])
    return {
        "schema_version": CONTRACT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_artifact_path": baseline_path,
        "optimized_artifact_path": optimized_path,
        "baseline_member_count": len(baseline_ids),
        "optimized_member_count": len(optimized_ids),
        "retained_member_count": len(retained),
        "removed_member_ids": removed,
        "added_member_ids": added,
        "group_merge_actions": merge_rows,
        "group_merge_count": len(merge_rows),
        "alignment_status": "aligned" if not removed and not added else "delta_present",
    }


def enrich_changes_payload(
    changes_payload: dict[str, Any],
    *,
    baseline_payload: dict[str, Any],
    optimized_payload: dict[str, Any],
    baseline_path: str = "",
    optimized_path: str = "",
) -> dict[str, Any]:
    changes = changes_payload.get("changes") if isinstance(changes_payload.get("changes"), list) else []
    alignment = build_member_alignment(
        baseline_payload=baseline_payload,
        optimized_payload=optimized_payload,
        changes=changes,
        baseline_path=baseline_path,
        optimized_path=optimized_path,
    )
    enriched = dict(changes_payload)
    enriched["contract_version"] = "1.1"
    enriched["member_alignment"] = alignment
    return enriched


def enrich_changes_file(
    changes_path: Path,
    *,
    baseline_path: Path,
    optimized_path: Path,
) -> dict[str, Any]:
    changes_payload = _load_json(changes_path)
    baseline_payload = _load_json(baseline_path)
    optimized_payload = _load_json(optimized_path)
    enriched = enrich_changes_payload(
        changes_payload,
        baseline_payload=baseline_payload,
        optimized_payload=optimized_payload,
        baseline_path=str(baseline_path),
        optimized_path=str(optimized_path),
    )
    changes_path.write_text(json.dumps(enriched, indent=2) + "\n", encoding="utf-8")
    return enriched
