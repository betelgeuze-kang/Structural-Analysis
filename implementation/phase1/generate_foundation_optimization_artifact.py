#!/usr/bin/env python3
"""Generate a foundation optimization artifact from the design-optimization dataset."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

import numpy as np


FOUNDATION_KEYWORDS = {
    "foundation",
    "mat",
    "raft",
    "pile",
    "caisson",
    "pilecap",
    "pile_cap",
    "footing",
    "ground",
}

FOUNDATION_TOKEN_RE = re.compile(
    r"\b(?:foundation|footing|pile\s*cap|mat|raft|pile|caisson|ground)\b",
    re.IGNORECASE,
)


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    if not path.exists():
        return {}
    try:
        data = np.load(path, allow_pickle=True)
    except Exception:
        return {}
    return {str(key): data[key] for key in data.files}


def _load_json_rows(path: Path, key: str) -> list[dict[str, Any]]:
    payload = _load_json(path)
    rows = payload.get(key, []) if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "y", "yes", "true", "on"}:
            return True
        if v in {"0", "n", "no", "false", "off"}:
            return False
    try:
        return bool(value)
    except Exception:
        return bool(default)


def _normalize_foundation_key(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[-\s/]+", "_", text)
    return text


def _member_is_foundation(row: dict) -> bool:
    member_type = _normalize_foundation_key(row.get("member_type", ""))
    if member_type in FOUNDATION_KEYWORDS:
        return True
    semantic_group = str(row.get("semantic_group", "") or "").strip().lower()
    section_signature = str(row.get("section_signature", "") or "").strip().lower()
    section_name = str(row.get("section_name", "") or "").strip().lower()
    exact_family_key = str(row.get("exact_family_key", "") or "").strip().lower()
    group_family_key = str(row.get("group_family_key", "") or "").strip().lower()
    combined = f"{member_type} {semantic_group} {section_signature} {section_name} {exact_family_key} {group_family_key}"
    normalized = re.sub(r"[-_/]+", " ", combined)
    return bool(FOUNDATION_TOKEN_RE.search(normalized))


def _default_npz_path(dataset_report: Path) -> Path:
    if dataset_report.name.endswith("_report.json"):
        return dataset_report.with_name(dataset_report.name.replace("_report.json", ".npz"))
    return dataset_report.with_suffix(".npz")


def _foundation_rows_from_npz(state: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    if not state:
        return []
    member_ids = np.asarray(state.get("member_ids", np.asarray([], dtype=object)))
    member_types = np.asarray(state.get("member_types", np.asarray([], dtype=object)))
    group_ids = np.asarray(state.get("group_ids", np.asarray([], dtype=object)))
    semantic_groups = np.asarray(state.get("semantic_groups", np.asarray([], dtype=object)))
    section_signatures = np.asarray(state.get("section_signatures", np.asarray([], dtype=object)))
    section_names = np.asarray(state.get("section_names", np.asarray([], dtype=object)))
    exact_family_keys = np.asarray(state.get("exact_family_keys", np.asarray([], dtype=object)))
    count = int(min(member_ids.size, member_types.size, group_ids.size, semantic_groups.size, section_signatures.size))
    rows: list[dict[str, Any]] = []
    for idx in range(count):
        row = {
            "member_id": str(member_ids[idx]),
            "member_type": str(member_types[idx]),
            "group_id": str(group_ids[idx]),
            "semantic_group": str(semantic_groups[idx]),
            "section_signature": str(section_signatures[idx]),
            "section_name": str(section_names[idx]) if idx < int(section_names.size) else "",
            "exact_family_key": str(exact_family_keys[idx]) if idx < int(exact_family_keys.size) else "",
        }
        if _member_is_foundation(row):
            rows.append(row)
    return rows


def _foundation_group_rows_from_npz(state: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    if not state:
        return []
    group_ids = np.asarray(state.get("unique_group_ids", np.asarray([], dtype=object)))
    member_types = np.asarray(state.get("member_type_per_group", np.asarray([], dtype=object)))
    semantic_groups = np.asarray(state.get("semantic_group_per_group", np.asarray([], dtype=object)))
    section_signatures = np.asarray(state.get("section_signature_per_group", np.asarray([], dtype=object)))
    section_names = np.asarray(state.get("section_name_per_group", np.asarray([], dtype=object)))
    group_family_keys = np.asarray(state.get("group_family_key", np.asarray([], dtype=object)))
    count = int(min(group_ids.size, member_types.size, semantic_groups.size, section_signatures.size))
    rows: list[dict[str, Any]] = []
    for idx in range(count):
        row = {
            "member_id": str(group_ids[idx]),
            "member_type": str(member_types[idx]),
            "group_id": str(group_ids[idx]),
            "semantic_group": str(semantic_groups[idx]),
            "section_signature": str(section_signatures[idx]),
            "section_name": str(section_names[idx]) if idx < int(section_names.size) else "",
            "group_family_key": str(group_family_keys[idx]) if idx < int(group_family_keys.size) else "",
        }
        if _member_is_foundation(row):
            rows.append(row)
    return rows


def _normalize_group_id(row: dict[str, Any]) -> str:
    return str(row.get("group_id", "") or "").strip()


def _canonical_group_scope(group_id: object) -> str:
    text = str(group_id or "").strip()
    if not text:
        return ""
    parts = text.split(":")
    # Group ids are emitted as Sxx:zone:semantic:member_type:section_signature.
    # When dataset promotion upgrades a below-grade vertical beam into foundation,
    # the member_type slot changes but the structural scope remains the same.
    if len(parts) >= 5 and parts[0].startswith("S"):
        return ":".join(parts[:3] + parts[4:])
    return text


def _normalize_member_id(row: dict[str, Any]) -> str:
    return str(row.get("member_id", "") or "").strip()


def _action_row_matches_foundation(
    row: dict[str, Any],
    foundation_group_ids: set[str],
    foundation_group_scopes: set[str],
    foundation_member_ids: set[str],
) -> bool:
    group_id = _normalize_group_id(row)
    if group_id and group_id in foundation_group_ids:
        return True
    canonical_scope = _canonical_group_scope(group_id)
    if canonical_scope and canonical_scope in foundation_group_scopes:
        return True
    member_id = _normalize_member_id(row)
    if member_id and member_id in foundation_member_ids:
        return True
    return _member_is_foundation(row)


def _foundation_text_hits(values: list[str]) -> list[str]:
    hits: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and FOUNDATION_TOKEN_RE.search(re.sub(r"[-_/]+", " ", text.lower())):
            hits.append(text)
    return hits


def _text_path_foundation_provenance(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "checked": False,
            "path": str(path),
            "foundation_label_count": 0,
            "hits_head": [],
        }
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return {
            "checked": False,
            "path": str(path),
            "foundation_label_count": 0,
            "hits_head": [],
        }
    hits: list[str] = []
    for line in lines:
        text = str(line or "").strip()
        if text and FOUNDATION_TOKEN_RE.search(re.sub(r"[-_/]+", " ", text.lower())):
            hits.append(text)
    return {
        "checked": True,
        "path": str(path),
        "foundation_label_count": int(len(hits)),
        "hits_head": hits[:16],
    }


def _upstream_foundation_provenance(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "checked": False,
            "path": str(path),
            "foundation_label_count": 0,
            "generic_section_name_count": 0,
            "section_count": 0,
            "group_count": 0,
            "section_hits_head": [],
            "group_hits_head": [],
            "element_hits_head": [],
        }
    payload = _load_json(path)
    model = payload.get("model") if isinstance(payload.get("model"), dict) else payload
    if not isinstance(model, dict):
        return {
            "checked": False,
            "path": str(path),
            "foundation_label_count": 0,
            "generic_section_name_count": 0,
            "section_count": 0,
            "group_count": 0,
            "section_hits_head": [],
            "group_hits_head": [],
            "element_hits_head": [],
        }
    sections = model.get("sections", []) if isinstance(model.get("sections"), list) else []
    elements = model.get("elements", []) if isinstance(model.get("elements"), list) else []
    metadata = model.get("metadata", {}) if isinstance(model.get("metadata"), dict) else {}
    groups = metadata.get("groups", []) if isinstance(metadata.get("groups"), list) else []
    section_names = [str((row or {}).get("name", "") or "") for row in sections if isinstance(row, dict)]
    section_signatures = [
        str(raw_tokens[0]).strip()
        for row in sections
        if isinstance(row, dict)
        for raw_tokens in [row.get("raw_tokens") if isinstance(row.get("raw_tokens"), list) else []]
        if raw_tokens and str(raw_tokens[0]).strip()
    ]
    group_names = [str((row or {}).get("name", "") or "") for row in groups if isinstance(row, dict)]
    group_plane_types = [str((row or {}).get("plane_type", "") or "") for row in groups if isinstance(row, dict)]
    element_names = [
        " ".join(
            part
            for part in (
                str((row or {}).get("name", "") or "").strip(),
                str((row or {}).get("type", "") or "").strip(),
            )
            if part
        )
        for row in elements
        if isinstance(row, dict)
    ]
    section_hits = _foundation_text_hits(section_names)
    section_signature_hits = _foundation_text_hits(section_signatures)
    group_hits = _foundation_text_hits(group_names)
    group_plane_type_hits = _foundation_text_hits(group_plane_types)
    element_hits = _foundation_text_hits(element_names)
    generic_section_name_count = sum(1 for name in section_names if str(name).strip().upper() == "DBUSER")
    source = payload.get("source", {}) if isinstance(payload.get("source"), dict) else {}
    raw_source_path = Path(str(source.get("path", "") or ""))
    raw_source = _text_path_foundation_provenance(raw_source_path) if str(raw_source_path).strip() else {
        "checked": False,
        "path": "",
        "foundation_label_count": 0,
        "hits_head": [],
    }
    parsed_label_count = int(
        len(section_hits)
        + len(section_signature_hits)
        + len(group_hits)
        + len(group_plane_type_hits)
        + len(element_hits)
    )
    if int(raw_source.get("foundation_label_count", 0)) > 0 and parsed_label_count <= 0:
        provenance_status = "parser_drop_suspected"
    elif parsed_label_count > 0:
        provenance_status = "parsed_model_labels_present"
    else:
        provenance_status = "upstream_source_absent"
    return {
        "checked": True,
        "path": str(path),
        "foundation_label_count": int(parsed_label_count),
        "generic_section_name_count": int(generic_section_name_count),
        "section_count": int(len(section_names)),
        "group_count": int(len(group_names)),
        "section_label_count": int(len(section_hits)),
        "section_signature_label_count": int(len(section_signature_hits)),
        "group_label_count": int(len(group_hits)),
        "group_plane_type_label_count": int(len(group_plane_type_hits)),
        "element_label_count": int(len(element_hits)),
        "section_hits_head": section_hits[:16],
        "section_signature_hits_head": section_signature_hits[:16],
        "group_hits_head": group_hits[:16],
        "group_plane_type_hits_head": group_plane_type_hits[:16],
        "element_hits_head": element_hits[:16],
        "raw_source_checked": bool(raw_source.get("checked", False)),
        "raw_source_path": str(raw_source.get("path", "") or ""),
        "raw_source_foundation_label_count": int(raw_source.get("foundation_label_count", 0)),
        "raw_source_hits_head": list(raw_source.get("hits_head", [])),
        "provenance_status": provenance_status,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--design-optimization-dataset",
        default="implementation/phase1/release/design_optimization/design_optimization_dataset_report.json",
    )
    p.add_argument("--design-optimization-npz", default="")
    p.add_argument("--midas-model", default="")
    p.add_argument(
        "--cost-reduction-changes",
        default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_changes.json",
    )
    p.add_argument(
        "--cost-reduction-blocked-actions",
        default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_blocked_actions.json",
    )
    p.add_argument("--out", default="implementation/phase1/release/design_optimization/foundation_optimization_artifact.json")
    args = p.parse_args()

    dataset_path = Path(args.design_optimization_dataset)
    dataset = _load_json(dataset_path)
    summary = dataset.get("summary", {}) if isinstance(dataset.get("summary"), dict) else {}
    rows = dataset.get("rows_head", [])
    if not isinstance(rows, list):
        rows = []
    npz_path = Path(args.design_optimization_npz) if str(args.design_optimization_npz).strip() else _default_npz_path(dataset_path)
    npz_state = _load_npz(npz_path)
    npz_rows = _foundation_rows_from_npz(npz_state)
    npz_group_rows = _foundation_group_rows_from_npz(npz_state)
    if npz_rows or npz_group_rows:
        row_source = "npz_full"
    elif npz_state:
        row_source = "npz_full_empty"
    else:
        row_source = "rows_head"

    foundation_rows: list[dict] = []
    preferred_rows = npz_rows if npz_rows else npz_group_rows if npz_group_rows else rows
    for row in preferred_rows:
        if isinstance(row, dict) and _member_is_foundation(row):
            foundation_rows.append(
                {
                    "member_id": str(row.get("member_id", row.get("group_id", "")) or ""),
                    "member_type": str(row.get("member_type", "") or ""),
                    "group_id": str(row.get("group_id", "") or ""),
                    "semantic_group": str(row.get("semantic_group", "") or ""),
                    "section_signature": str(row.get("section_signature", "") or ""),
                    "section_name": str(row.get("section_name", "") or ""),
                }
            )

    member_type_counts = summary.get("member_type_counts", {}) if isinstance(summary.get("member_type_counts"), dict) else {}
    if not foundation_rows and isinstance(member_type_counts, dict):
        for key, count in member_type_counts.items():
            if str(key).strip().lower() in FOUNDATION_KEYWORDS and _safe_int(count, 0) > 0:
                foundation_rows.append(
                    {
                        "member_id": str(key),
                        "member_type": str(key),
                        "group_id": "",
                        "semantic_group": "",
                        "section_signature": "",
                    }
                )

    foundation_count = sum(
        _safe_int(count, 0)
        for key, count in member_type_counts.items()
        if str(key).strip().lower() in FOUNDATION_KEYWORDS
    )
    foundation_count = max(int(foundation_count), int(len(foundation_rows)))
    foundation_group_ids = {_normalize_group_id(row) for row in foundation_rows if _normalize_group_id(row)}
    foundation_group_scopes = {_canonical_group_scope(group_id) for group_id in foundation_group_ids if _canonical_group_scope(group_id)}
    foundation_member_ids = {_normalize_member_id(row) for row in foundation_rows if _normalize_member_id(row)}
    cost_reduction_changes_path = Path(args.cost_reduction_changes)
    cost_reduction_blocked_path = Path(args.cost_reduction_blocked_actions)
    optimized_rows = [
        row
        for row in _load_json_rows(cost_reduction_changes_path, "changes")
        if _action_row_matches_foundation(row, foundation_group_ids, foundation_group_scopes, foundation_member_ids)
    ]
    blocked_rows = [
        row
        for row in _load_json_rows(cost_reduction_blocked_path, "blocked_rows")
        if _action_row_matches_foundation(row, foundation_group_ids, foundation_group_scopes, foundation_member_ids)
    ]
    optimized_group_ids = sorted({_normalize_group_id(row) for row in optimized_rows if _normalize_group_id(row)})
    blocked_group_ids = sorted({_normalize_group_id(row) for row in blocked_rows if _normalize_group_id(row)})
    dataset_inputs = dataset.get("inputs", {}) if isinstance(dataset.get("inputs"), dict) else {}
    upstream_midas_path = Path(args.midas_model) if str(args.midas_model).strip() else Path(str(dataset_inputs.get("midas_model", "") or ""))
    upstream_provenance = _upstream_foundation_provenance(upstream_midas_path) if str(upstream_midas_path).strip() else {
        "checked": False,
        "path": "",
        "foundation_label_count": 0,
        "generic_section_name_count": 0,
        "section_count": 0,
        "group_count": 0,
        "section_label_count": 0,
        "section_signature_label_count": 0,
        "group_label_count": 0,
        "group_plane_type_label_count": 0,
        "element_label_count": 0,
        "section_hits_head": [],
        "section_signature_hits_head": [],
        "group_hits_head": [],
        "group_plane_type_hits_head": [],
        "element_hits_head": [],
        "raw_source_checked": False,
        "raw_source_path": "",
        "raw_source_foundation_label_count": 0,
        "raw_source_hits_head": [],
        "provenance_status": "upstream_source_absent",
    }
    dataset_contract_pass = bool(_safe_bool(dataset.get("contract_pass", False)))
    contract_pass = bool(dataset_contract_pass and foundation_count > 0)
    reason_code = "PASS" if contract_pass else ("ERR_INPUT" if not dataset else "ERR_NO_FOUNDATION_SCOPE")
    if not contract_pass:
        if str(upstream_provenance.get("provenance_status", "")) == "parser_drop_suspected":
            reason = "raw MIDAS source carries foundation-like labels, but parsed model/dataset did not promote them"
        elif int(upstream_provenance.get("foundation_label_count", 0)) > 0:
            reason = "upstream MIDAS model carries foundation-like labels, but the active design-optimization dataset did not promote them"
        elif row_source == "npz_full_empty":
            reason = "full design-optimization NPZ scan found no foundation members"
        else:
            reason = "design-optimization dataset did not expose foundation members"
    elif optimized_group_ids:
        reason = "foundation optimization scope and cost-reduction evidence were captured"
    else:
        reason = "foundation optimization scope was detected, but no foundation-specific cost-reduction actions were emitted"
    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-foundation-optimization-artifact",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "design_optimization_dataset": str(args.design_optimization_dataset),
            "design_optimization_npz": str(npz_path),
            "midas_model": str(upstream_midas_path),
            "cost_reduction_changes": str(cost_reduction_changes_path),
            "cost_reduction_blocked_actions": str(cost_reduction_blocked_path),
        },
        "summary": {
            "candidate_scan_mode": row_source,
            "member_count": _safe_int(summary.get("member_count", 0)),
            "group_count": _safe_int(summary.get("group_count", 0)),
            "foundation_member_type_count": int(foundation_count),
            "optimized_foundation_member_count": int(len(optimized_group_ids)),
            "optimized_foundation_group_count": int(len(optimized_group_ids)),
            "blocked_foundation_group_count": int(len(blocked_group_ids)),
            "rows_head_foundation_row_count": int(sum(1 for row in rows if isinstance(row, dict) and _member_is_foundation(row))),
            "npz_foundation_member_row_count": int(len(npz_rows)),
            "npz_foundation_group_row_count": int(len(npz_group_rows)),
            "foundation_member_type_counts": {
                str(k): _safe_int(v, 0)
                for k, v in sorted(member_type_counts.items())
                if str(k).strip().lower() in FOUNDATION_KEYWORDS
            },
            "candidate_member_ids_head": [row["member_id"] for row in foundation_rows[:16]],
            "dataset_contract_pass": bool(dataset_contract_pass),
            "optimization_evidence_mode": "cost_reduction_outputs",
            "design_optimization_npz_present": bool(npz_state),
            "upstream_foundation_provenance_mode": (
                str(upstream_provenance.get("provenance_status", "") or "")
                if foundation_count <= 0
                else "dataset_scope_only"
            ),
            "upstream_foundation_label_count": int(upstream_provenance.get("foundation_label_count", 0)),
            "upstream_generic_section_name_count": int(upstream_provenance.get("generic_section_name_count", 0)),
            "upstream_section_count": int(upstream_provenance.get("section_count", 0)),
            "upstream_group_count": int(upstream_provenance.get("group_count", 0)),
            "upstream_section_signature_label_count": int(upstream_provenance.get("section_signature_label_count", 0)),
            "upstream_group_plane_type_label_count": int(upstream_provenance.get("group_plane_type_label_count", 0)),
            "raw_source_foundation_label_count": int(upstream_provenance.get("raw_source_foundation_label_count", 0)),
        },
        "artifacts": {
            "optimized_foundation_member_count": int(len(optimized_group_ids)),
            "optimized_foundation_group_ids_head": optimized_group_ids[:16],
            "optimized_foundation_rows_head": optimized_rows[:16],
            "blocked_foundation_group_ids_head": blocked_group_ids[:16],
            "blocked_foundation_rows_head": blocked_rows[:16],
            "foundation_candidate_rows_head": foundation_rows[:16],
            "upstream_foundation_section_hits_head": list(upstream_provenance.get("section_hits_head", [])),
            "upstream_foundation_section_signature_hits_head": list(
                upstream_provenance.get("section_signature_hits_head", [])
            ),
            "upstream_foundation_group_hits_head": list(upstream_provenance.get("group_hits_head", [])),
            "upstream_foundation_group_plane_type_hits_head": list(
                upstream_provenance.get("group_plane_type_hits_head", [])
            ),
            "upstream_foundation_element_hits_head": list(upstream_provenance.get("element_hits_head", [])),
            "raw_source_foundation_hits_head": list(upstream_provenance.get("raw_source_hits_head", [])),
            "source_provenance": {
                "dataset_report": str(args.design_optimization_dataset),
                "dataset_npz": str(npz_path),
                "midas_model": str(upstream_midas_path),
                "raw_source": str(upstream_provenance.get("raw_source_path", "") or ""),
                "candidate_scan_mode": row_source,
            },
        },
        "checks": {
            "dataset_contract_pass": bool(dataset_contract_pass),
            "foundation_members_present": bool(foundation_count > 0),
            "foundation_optimization_evidence_present": bool(len(optimized_group_ids) > 0),
            "full_dataset_scanned": bool(npz_state),
            "upstream_model_checked": bool(upstream_provenance.get("checked", False)),
            "upstream_foundation_label_present": bool(int(upstream_provenance.get("foundation_label_count", 0)) > 0),
            "raw_source_checked": bool(upstream_provenance.get("raw_source_checked", False)),
            "parser_drop_suspected": str(upstream_provenance.get("provenance_status", "")) == "parser_drop_suspected",
        },
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": reason,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote foundation optimization artifact: {out}")


if __name__ == "__main__":
    main()
