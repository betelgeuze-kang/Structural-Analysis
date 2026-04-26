from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected a JSON object at {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()


def _normalize_list(values: Any) -> list[str]:
    if isinstance(values, (list, tuple, set)):
        raw = values
    elif values is None:
        raw = []
    else:
        raw = [values]
    ordered: list[str] = []
    seen: set[str] = set()
    for item in raw:
        normalized = _normalize_string(item)
        if normalized and normalized not in seen:
            ordered.append(normalized)
            seen.add(normalized)
    return ordered


def _collect_interactive_targets(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    targets: list[tuple[str, dict[str, Any]]] = []
    interactive_3d = payload.get("interactive_3d")
    if isinstance(interactive_3d, dict):
        targets.append(("interactive_3d", interactive_3d))
    interactive_3d_payload = payload.get("interactive_3d_payload")
    if isinstance(interactive_3d_payload, dict):
        targets.append(("interactive_3d_payload", interactive_3d_payload))
    if not targets and (
        isinstance(payload.get("baseline_segments"), list)
        or isinstance(payload.get("after_segments"), list)
    ):
        targets.append(("root", payload))
    return targets


def _validate_patch_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    patch_mode = _normalize_string(payload.get("patch_mode"))
    patch_scope = _normalize_string(payload.get("patch_scope"))
    if patch_mode != "working_section_override_patch":
        raise SystemExit(f"Unsupported patch_mode: {patch_mode or 'missing'}")
    if patch_scope != "member_section_override":
        raise SystemExit(f"Unsupported patch_scope: {patch_scope or 'missing'}")
    rows = payload.get("patch_entries")
    if not isinstance(rows, list):
        raise SystemExit("Patch payload must include a patch_entries list")
    normalized_by_member: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        member_id = _normalize_string(row.get("member_id"))
        target_section = _normalize_string(row.get("target_section"))
        if not member_id or not target_section:
            continue
        normalized_by_member[member_id] = dict(row)
    if not normalized_by_member:
        raise SystemExit("Patch payload did not contain any valid member_id/target_section entries")
    return list(normalized_by_member.values())


def _section_modification_label(before_section: str, after_section: str) -> str:
    before = _normalize_string(before_section)
    after = _normalize_string(after_section)
    if before and after and before != after:
        return f"section {before} -> {after}"
    if after:
        return f"section 유지({after})"
    return "같은 자리 속성 조정"


def _extract_impact_label(row: dict[str, Any]) -> str:
    impact = _normalize_string(row.get("impact_snapshot_label"))
    if impact:
        return impact
    existing_note = _normalize_string(row.get("before_after_snapshot_note"))
    if " | " in existing_note:
        return _normalize_string(existing_note.split(" | ", 1)[1])
    return ""


def _build_override_note(row: dict[str, Any], before_section: str, after_section: str) -> tuple[str, str]:
    modification_label = _section_modification_label(before_section, after_section)
    impact_label = _extract_impact_label(row)
    note = f"{modification_label} | {impact_label}" if impact_label else modification_label
    return modification_label, note


def _clone_after_row(
    baseline_row: dict[str, Any],
    patch_entry: dict[str, Any],
    *,
    patch_applied_at: str,
) -> dict[str, Any]:
    member_id = _normalize_string(
        patch_entry.get("member_id") or baseline_row.get("member_id")
    )
    target_section = _normalize_string(patch_entry.get("target_section"))
    before_section = _normalize_string(
        baseline_row.get("section_name")
        or patch_entry.get("current_section_summary")
        or patch_entry.get("source_section_summary")
    )
    modification_label, note = _build_override_note({}, before_section, target_section)
    return {
        "member_id": member_id,
        "group_id": _normalize_string(patch_entry.get("group_id"))
        or f"section-override:{member_id}",
        "action_family": "viewer_override",
        "action_name": "viewer_section_override",
        "story_band_label": _normalize_string(
            baseline_row.get("story_band_label") or patch_entry.get("story_band_label")
        ),
        "zone_label": _normalize_string(
            baseline_row.get("zone_label") or patch_entry.get("zone_label")
        )
        or "n/a",
        "member_type": _normalize_string(
            baseline_row.get("member_type")
            or baseline_row.get("category")
            or patch_entry.get("type_summary")
        )
        or "other",
        "before_section": before_section,
        "after_section": target_section,
        "before_after_snapshot_note": note,
        "modification_snapshot_label": modification_label,
        "optimization_meaning_label": "viewer-applied section override",
        "override_source": "working_section_override_patch",
        "override_applied_at": patch_applied_at,
        "override_selection_source": _normalize_string(patch_entry.get("selection_source")),
        "color": _normalize_string(baseline_row.get("color")) or "#2463eb",
        "p0": baseline_row.get("p0"),
        "p1": baseline_row.get("p1"),
    }


def _update_after_row(
    row: dict[str, Any],
    patch_entry: dict[str, Any],
    *,
    patch_applied_at: str,
) -> None:
    target_section = _normalize_string(patch_entry.get("target_section"))
    before_section = _normalize_string(
        row.get("before_section")
        or patch_entry.get("current_section_summary")
        or patch_entry.get("source_section_summary")
        or row.get("section_name")
    )
    modification_label, note = _build_override_note(row, before_section, target_section)
    if before_section:
        row["before_section"] = before_section
    row["after_section"] = target_section
    row["before_after_snapshot_note"] = note
    row["modification_snapshot_label"] = modification_label
    row["override_source"] = "working_section_override_patch"
    row["override_applied_at"] = patch_applied_at
    row["override_selection_source"] = _normalize_string(patch_entry.get("selection_source"))


def _update_after_family_summary(interactive_payload: dict[str, Any]) -> None:
    after_rows = [
        row for row in (interactive_payload.get("after_segments") or []) if isinstance(row, dict)
    ]
    family_counts = Counter(
        _normalize_string(row.get("action_family") or row.get("action_name")) or "viewer_override"
        for row in after_rows
    )
    interactive_payload["after_segment_count"] = len(after_rows)
    if "after_segment_raw_count" in interactive_payload:
        interactive_payload["after_segment_raw_count"] = len(after_rows)
    interactive_payload["comparison_availability"] = (
        "baseline_vs_changed" if after_rows else "baseline_only"
    )
    if "after_family_options" in interactive_payload or "after_family_label" in interactive_payload:
        ordered = sorted(family_counts.items(), key=lambda item: (-int(item[1]), item[0]))
        interactive_payload["after_family_options"] = [
            {"label": label, "count": count} for label, count in ordered
        ]
        interactive_payload["after_family_label"] = (
            ", ".join(f"{label}={count}" for label, count in ordered) if ordered else "n/a"
        )


def apply_patch_to_artifact(
    *,
    source_artifact_path: Path,
    patch_json_path: Path,
    out_path: Path,
) -> dict[str, Any]:
    if source_artifact_path.resolve() == out_path.resolve():
        raise SystemExit("--out must point to a different file than --source-artifact")
    source_payload = _load_json(source_artifact_path)
    patch_payload = _load_json(patch_json_path)
    patch_entries = _validate_patch_payload(patch_payload)
    interactive_targets = _collect_interactive_targets(source_payload)
    if not interactive_targets:
        raise SystemExit(
            "Source artifact does not expose interactive_3d, interactive_3d_payload, or segment lists"
        )

    requested_member_ids = _normalize_list(
        [row.get("member_id") for row in patch_entries]
    )
    applied_at = _normalize_string(patch_payload.get("applied_at")) or datetime.now(
        timezone.utc
    ).isoformat()
    updated_members: set[str] = set()
    cloned_members: set[str] = set()
    unmatched_members = set(requested_member_ids)

    for _, interactive_payload in interactive_targets:
        baseline_rows = [
            row
            for row in (interactive_payload.get("baseline_segments") or [])
            if isinstance(row, dict)
        ]
        after_rows = [
            row
            for row in (interactive_payload.get("after_segments") or [])
            if isinstance(row, dict)
        ]
        after_by_member: dict[str, list[dict[str, Any]]] = {}
        for row in after_rows:
            member_id = _normalize_string(row.get("member_id"))
            if member_id:
                after_by_member.setdefault(member_id, []).append(row)
        baseline_by_member: dict[str, list[dict[str, Any]]] = {}
        for row in baseline_rows:
            member_id = _normalize_string(row.get("member_id"))
            if member_id:
                baseline_by_member.setdefault(member_id, []).append(row)

        for patch_entry in patch_entries:
            member_id = _normalize_string(patch_entry.get("member_id"))
            if not member_id:
                continue
            if member_id in after_by_member:
                for row in after_by_member[member_id]:
                    _update_after_row(row, patch_entry, patch_applied_at=applied_at)
                updated_members.add(member_id)
                unmatched_members.discard(member_id)
                continue
            if member_id in baseline_by_member:
                clones = [
                    _clone_after_row(
                        baseline_row,
                        patch_entry,
                        patch_applied_at=applied_at,
                    )
                    for baseline_row in baseline_by_member[member_id]
                ]
                after_rows.extend(clones)
                after_by_member[member_id] = clones
                cloned_members.add(member_id)
                unmatched_members.discard(member_id)
        interactive_payload["after_segments"] = after_rows
        _update_after_family_summary(interactive_payload)

    source_payload["working_section_override_patch_apply_receipt"] = {
        "contract_version": int(patch_payload.get("contract_version", 1) or 1),
        "patch_mode": "working_section_override_patch",
        "patch_scope": "member_section_override",
        "patch_source_path": str(patch_json_path),
        "source_artifact_path": str(source_artifact_path),
        "out_path": str(out_path),
        "applied_at": applied_at,
        "requested_member_ids": requested_member_ids,
        "requested_member_count": len(requested_member_ids),
        "updated_existing_after_member_ids": sorted(updated_members),
        "updated_existing_after_member_count": len(updated_members),
        "cloned_from_baseline_member_ids": sorted(cloned_members),
        "cloned_from_baseline_member_count": len(cloned_members),
        "applied_member_ids": sorted(updated_members | cloned_members),
        "applied_member_count": len(updated_members | cloned_members),
        "unmatched_member_ids": sorted(unmatched_members),
        "unmatched_member_count": len(unmatched_members),
        "interactive_payload_targets": [label for label, _ in interactive_targets],
        "selection_source": _normalize_string(patch_payload.get("selection_source")),
        "viewer_url": _normalize_string(patch_payload.get("viewer_url")),
    }
    _write_json(out_path, source_payload)
    return source_payload["working_section_override_patch_apply_receipt"]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-artifact", required=True)
    parser.add_argument("--patch-json", required=True)
    parser.add_argument("--out", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    receipt = apply_patch_to_artifact(
        source_artifact_path=Path(args.source_artifact),
        patch_json_path=Path(args.patch_json),
        out_path=Path(args.out),
    )
    print(
        "Applied working_section_override_patch:"
        f" applied={receipt['applied_member_count']}"
        f" updated={receipt['updated_existing_after_member_count']}"
        f" cloned={receipt['cloned_from_baseline_member_count']}"
        f" unmatched={receipt['unmatched_member_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
