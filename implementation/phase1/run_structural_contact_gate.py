#!/usr/bin/env python3
"""Classify broader structural contact readiness using existing repo evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from runtime_contracts import InputContractError, validate_input_contract
try:
    from foundation_link_library import describe_foundation_link_library
except Exception:  # pragma: no cover - additive fallback when the library is unavailable.
    def describe_foundation_link_library() -> dict[str, object]:
        return {}

try:
    from device_library import describe_device_library
except Exception:  # pragma: no cover - additive fallback when the library is unavailable.
    def describe_device_library() -> dict[str, object]:
        return {}


CATEGORY_ORDER = (
    "gap",
    "uplift",
    "compression_only",
    "bearing",
    "friction",
    "pounding",
)

CATEGORY_LABELS = {
    "gap": "gap",
    "uplift": "uplift",
    "compression_only": "compression-only",
    "bearing": "bearing",
    "friction": "friction",
    "pounding": "pounding",
}

CATEGORY_KEYWORDS = {
    "gap": ("gap",),
    "uplift": ("uplift",),
    "compression_only": ("compression-only", "compression only"),
    "bearing": ("bearing",),
    "friction": ("friction",),
    "pounding": ("pounding",),
}

REASONS = {
    "PASS": "broader structural contact evidence is present for gap/uplift/compression-only/bearing/friction/pounding",
    "ERR_INVALID_INPUT": "invalid structural contact gate input",
    "ERR_BOUNDED_CONTACT_EVIDENCE_FAIL": "bounded upstream contact evidence is missing or does not pass",
    "ERR_STRUCTURAL_CONTACT_IMPLEMENTATION_MISSING": "broader structural contact implementation evidence is missing",
    "ERR_STRUCTURAL_CONTACT_VALIDATION_MISSING": "broader structural contact validation evidence is missing or incomplete",
    "ERR_STRUCTURAL_CONTACT_GAP_TRACKED": "roadmap still tracks broader structural contact as an open gap",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "contact_readiness_report",
        "roadmap",
        "kds_rc_rule_engine",
        "special_link_library",
        "structural_contact_validation_report",
        "out",
    ],
    "properties": {
        "contact_readiness_report": {"type": "string", "minLength": 1},
        "roadmap": {"type": "string", "minLength": 1},
        "kds_rc_rule_engine": {"type": "string", "minLength": 1},
        "special_link_library": {"type": "string", "minLength": 1},
        "structural_contact_validation_report": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in phrases)


def _join_labels(keys: list[str]) -> str:
    return ",".join(CATEGORY_LABELS[key] for key in keys) if keys else "none"


def _sorted_string_list(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    return sorted({str(item).strip() for item in items if str(item).strip()})


def _sorted_string_union(*sources: object) -> list[str]:
    merged: set[str] = set()
    for source in sources:
        if isinstance(source, (list, tuple, set)):
            candidates = source
        else:
            continue
        for item in candidates:
            text = str(item).strip()
            if text:
                merged.add(text)
    return sorted(merged)


def _int_map(items: object) -> dict[str, int]:
    if not isinstance(items, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, value in items.items():
        label = str(key).strip()
        if not label:
            continue
        try:
            normalized[label] = int(value)
        except Exception:
            continue
    return normalized


def _merge_int_maps_max(*sources: object) -> dict[str, int]:
    merged: dict[str, int] = {}
    for source in sources:
        for key, value in _int_map(source).items():
            merged[key] = max(merged.get(key, 0), int(value))
    return merged


def _contact_readiness_evidence(payload: dict) -> dict:
    summary_line = str(payload.get("summary_line", "") or "").strip()
    coverage_scope = str(payload.get("coverage_scope", "") or "").strip()
    upstream_pass = bool(payload.get("contract_pass", False))
    bounded_scope_pass = coverage_scope == "wheel_rail_hertzian_contact_only"

    structural_contact_label = ""
    marker = "structural_contact="
    if marker in summary_line:
        structural_contact_label = summary_line.split(marker, 1)[1].strip().split()[0]

    return {
        "report_present": bool(payload),
        "contract_pass": bool(upstream_pass),
        "bounded_scope_pass": bool(bounded_scope_pass),
        "upstream_contact_ready": bool(payload and upstream_pass and bounded_scope_pass),
        "coverage_scope": coverage_scope,
        "summary_line": summary_line,
        "structural_contact_label": structural_contact_label,
    }


def _roadmap_contact_gap_state(roadmap_text: str) -> dict:
    lowered = roadmap_text.lower()
    category_markers = {
        key: _contains_any(lowered, CATEGORY_KEYWORDS[key]) for key in CATEGORY_ORDER
    }
    tracked_gap_markers = {
        "broad_contact_gap": "contact / gap / uplift / compression-only" in lowered,
        "special_link_gap": "gap, uplift, bearing, isolator, friction, pounding" in lowered,
        "event_sequence_target": "contact / uplift event sequence mismatch" in lowered
        or "event sequence mismatch" in lowered,
    }
    return {
        "tracked_gap": bool(any(tracked_gap_markers.values())),
        "tracked_gap_markers": tracked_gap_markers,
        "category_markers": category_markers,
    }


def _design_rule_partial_evidence(rule_engine_text: str) -> dict:
    lowered = rule_engine_text.lower()
    bearing_design_rule_present = "foundation:bearing" in lowered
    friction_design_rule_present = "connection:shear_friction" in lowered or "shear_friction" in lowered
    partial_categories = {
        "gap": False,
        "uplift": False,
        "compression_only": False,
        "bearing": bool(bearing_design_rule_present),
        "friction": bool(friction_design_rule_present),
        "pounding": False,
    }
    return {
        "bearing_design_rule_present": bool(bearing_design_rule_present),
        "friction_design_rule_present": bool(friction_design_rule_present),
        "partial_categories": partial_categories,
    }


def _implementation_evidence(library_text: str, *, exists: bool) -> dict:
    per_category = {}
    for key in CATEGORY_ORDER:
        per_category[key] = bool(exists and _contains_any(library_text, CATEGORY_KEYWORDS[key]))
    return {
        "library_present": bool(exists),
        "per_category": per_category,
        "all_categories_present": bool(exists and all(per_category.values())),
    }


def _validation_evidence(payload: dict) -> dict:
    categories = payload.get("categories") if isinstance(payload.get("categories"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}

    event_sequence_mismatch = summary.get("contact_uplift_event_sequence_mismatch")
    if event_sequence_mismatch is None:
        event_sequence_mismatch = payload.get("contact_uplift_event_sequence_mismatch")
    try:
        event_sequence_mismatch_value = int(event_sequence_mismatch)
    except Exception:
        event_sequence_mismatch_value = None

    per_category = {}
    for key in CATEGORY_ORDER:
        item = categories.get(key) if isinstance(categories.get(key), dict) else {}
        per_category[key] = bool(item.get("validated", False))

    return {
        "report_present": bool(payload),
        "event_sequence_zero_pass": event_sequence_mismatch_value == 0,
        "event_sequence_mismatch": event_sequence_mismatch_value,
        "per_category": per_category,
        "all_categories_validated": bool(payload and all(per_category.values())),
    }


def _build_report(
    *,
    input_payload: dict,
    contact_payload: dict,
    roadmap_text: str,
    rule_engine_text: str,
    special_link_text: str,
    special_link_path: Path,
    validation_payload: dict,
) -> dict:
    contact_evidence = _contact_readiness_evidence(contact_payload)
    roadmap_evidence = _roadmap_contact_gap_state(roadmap_text)
    design_partial = _design_rule_partial_evidence(rule_engine_text)
    implementation_evidence = _implementation_evidence(special_link_text, exists=special_link_path.exists())
    validation_evidence = _validation_evidence(validation_payload)
    validation_summary = validation_payload.get("summary") if isinstance(validation_payload.get("summary"), dict) else {}
    categories = validation_payload.get("categories") if isinstance(validation_payload.get("categories"), dict) else {}
    foundation_catalog = describe_foundation_link_library()
    device_catalog = describe_device_library()
    foundation_support_model_types = _sorted_string_union(
        validation_summary.get("foundation_support_model_types"),
        list(foundation_catalog.keys()),
    )
    device_model_types = _sorted_string_union(
        validation_summary.get("device_model_types"),
        list(device_catalog.keys()),
    )
    derived_support_search_model_types = sorted(
        {
            name
            for name, item in {**foundation_catalog, **device_catalog}.items()
            if isinstance(item, dict) and bool(item.get("support_search_ready"))
        }
    )
    support_search_model_types = _sorted_string_union(
        validation_summary.get("support_search_model_types"),
        derived_support_search_model_types,
    )
    derived_node_to_surface_proxy_model_types = sorted(
        {
            name
            for name, item in {**foundation_catalog, **device_catalog}.items()
            if isinstance(item, dict) and bool(item.get("node_to_surface_proxy"))
        }
    )
    node_to_surface_proxy_model_types = _sorted_string_union(
        validation_summary.get("node_to_surface_proxy_model_types"),
        derived_node_to_surface_proxy_model_types,
    )
    derived_contact_search_surface_types = sorted(
        {
            str(item.get("link_model_type", "")).strip()
            for item in categories.values()
            if isinstance(item, dict) and str(item.get("link_model_type", "")).strip()
        }
    )
    contact_search_surface_types = _sorted_string_union(
        validation_summary.get("contact_search_surface_types"),
        derived_contact_search_surface_types,
    )
    derived_search_surface_mode_counts: dict[str, int] = {}
    for item in [*foundation_catalog.values(), *device_catalog.values()]:
        if not isinstance(item, dict):
            continue
        mode = str(item.get("search_surface_mode", "")).strip()
        if not mode:
            continue
        derived_search_surface_mode_counts[mode] = derived_search_surface_mode_counts.get(mode, 0) + 1
    search_surface_mode_counts = _merge_int_maps_max(
        validation_summary.get("search_surface_mode_counts"),
        derived_search_surface_mode_counts,
    )
    derived_search_family_counts: dict[str, int] = {}
    for item in [*foundation_catalog.values(), *device_catalog.values()]:
        if not isinstance(item, dict):
            continue
        family = str(item.get("search_family", "")).strip()
        if not family:
            continue
        derived_search_family_counts[family] = derived_search_family_counts.get(family, 0) + 1
    search_family_counts = _merge_int_maps_max(
        validation_summary.get("search_family_counts"),
        derived_search_family_counts,
    )
    search_ready_group_counts = _int_map(validation_summary.get("search_ready_group_counts"))
    if not search_ready_group_counts:
        search_ready_group_counts = {
            "contact": len([key for key in CATEGORY_ORDER if validation_evidence["per_category"][key]]),
            "support_ready": len(support_search_model_types),
            "node_to_surface_proxy": len(node_to_surface_proxy_model_types),
        }
    support_search_evidence_rows = [
        row for row in (validation_summary.get("support_search_evidence_rows") or []) if isinstance(row, dict)
    ]
    if not support_search_evidence_rows:
        support_search_evidence_rows = []
        for name, item in [*foundation_catalog.items(), *device_catalog.items()]:
            if not isinstance(item, dict) or not bool(item.get("support_search_ready")):
                continue
            support_search_evidence_rows.append(
                {
                    "link_name": str(item.get("link_name", name) or name),
                    "support_role": str(item.get("support_role", "") or ""),
                    "search_surface_mode": str(item.get("search_surface_mode", "") or ""),
                    "node_to_surface_proxy": bool(item.get("node_to_surface_proxy")),
                    "support_search_ready": bool(item.get("support_search_ready")),
                    "sample_probe_state": str(item.get("sample_probe_state", "") or ""),
                    "sample_probe_engaged": bool(item.get("sample_probe_engaged")),
                    "search_family": str(item.get("search_family", "") or ""),
                }
            )
    support_search_family_types = _sorted_string_union(
        validation_summary.get("support_search_family_types"),
        list(search_family_counts.keys()),
    )
    derived_node_to_surface_proxy_family_types = sorted(
        {
            str(row.get("search_family", "")).strip()
            for row in support_search_evidence_rows
            if bool(row.get("node_to_surface_proxy", False)) and str(row.get("search_family", "")).strip()
        }
    )
    if not derived_node_to_surface_proxy_family_types:
        derived_node_to_surface_proxy_family_types = sorted(
            {
                str(item.get("search_family", "")).strip()
                for item in [*foundation_catalog.values(), *device_catalog.values()]
                if isinstance(item, dict)
                and bool(item.get("node_to_surface_proxy"))
                and str(item.get("search_family", "")).strip()
            }
        )
    node_to_surface_proxy_family_types = _sorted_string_union(
        validation_summary.get("node_to_surface_proxy_family_types"),
        derived_node_to_surface_proxy_family_types,
    )
    support_search_family_requirements = _sorted_string_list(validation_summary.get("support_search_family_requirements"))
    if not support_search_family_requirements:
        support_search_family_requirements = ["device_support_search", "foundation_support_search"]
    try:
        support_depth_score = int(validation_summary.get("support_depth_score", 0) or 0)
    except Exception:
        support_depth_score = 0
    derived_support_depth_score = sum(
        int(item.get("support_depth_rank", 0) or 0)
        for item in [*foundation_catalog.values(), *device_catalog.values()]
        if isinstance(item, dict) and bool(item.get("support_search_ready"))
    )
    support_depth_score = max(support_depth_score, derived_support_depth_score)
    try:
        explicit_contact_family_count = int(validation_summary.get("contact_family_count", 0) or 0)
    except Exception:
        explicit_contact_family_count = 0
    derived_contact_family_count = max(
        int(search_ready_group_counts.get("contact", 0) or 0),
        len(contact_search_surface_types),
        len([key for key in CATEGORY_ORDER if validation_evidence["per_category"][key]]),
    )
    contact_family_count = max(explicit_contact_family_count, derived_contact_family_count)
    support_surface_evidence = {
        "foundation_support_model_types": foundation_support_model_types,
        "device_model_types": device_model_types,
        "support_search_model_types": support_search_model_types,
        "node_to_surface_proxy_model_types": node_to_surface_proxy_model_types,
        "contact_search_surface_types": contact_search_surface_types,
        "contact_family_count": int(contact_family_count),
        "support_link_group_counts": {
            "contact": int(contact_family_count),
            "foundation": len(foundation_support_model_types),
            "device": len(device_model_types),
        },
        "search_surface_mode_counts": search_surface_mode_counts,
        "search_family_counts": search_family_counts,
        "support_search_family_types": support_search_family_types,
        "node_to_surface_proxy_family_types": node_to_surface_proxy_family_types,
        "support_search_family_requirements": support_search_family_requirements,
        "search_ready_group_counts": search_ready_group_counts,
        "support_search_evidence_rows": support_search_evidence_rows,
        "support_search_model_count": len(support_search_model_types),
        "node_to_surface_proxy_count": len(node_to_surface_proxy_model_types),
        "support_depth_score": support_depth_score,
    }

    category_rows = []
    ready_categories: list[str] = []
    missing_categories: list[str] = []
    partial_only_categories: list[str] = []

    for key in CATEGORY_ORDER:
        implementation_present = bool(implementation_evidence["per_category"][key])
        validation_present = bool(validation_evidence["per_category"][key])
        partial_only = bool(design_partial["partial_categories"][key] and not implementation_present)
        ready = bool(
            contact_evidence["upstream_contact_ready"]
            and implementation_present
            and validation_present
            and validation_evidence["event_sequence_zero_pass"]
        )
        if ready:
            ready_categories.append(key)
        else:
            missing_categories.append(key)
        if partial_only:
            partial_only_categories.append(key)
        category_rows.append(
            {
                "category": CATEGORY_LABELS[key],
                "implementation_present": bool(implementation_present),
                "validated": bool(validation_present),
                "partial_design_rule_only": bool(partial_only),
                "roadmap_gap_tracked": bool(roadmap_evidence["category_markers"][key]),
                "ready": bool(ready),
            }
        )

    checks = {
        "bounded_contact_evidence_pass": bool(contact_evidence["upstream_contact_ready"]),
        "roadmap_tracks_broader_structural_contact_gap": bool(roadmap_evidence["tracked_gap"]),
        "special_link_library_present": bool(implementation_evidence["library_present"]),
        "special_link_categories_present": bool(implementation_evidence["all_categories_present"]),
        "structural_contact_validation_present": bool(validation_evidence["report_present"]),
        "structural_contact_event_sequence_zero_pass": bool(validation_evidence["event_sequence_zero_pass"]),
        "bearing_design_rule_present": bool(design_partial["bearing_design_rule_present"]),
        "friction_design_rule_present": bool(design_partial["friction_design_rule_present"]),
        "foundation_support_surface_present": bool(foundation_support_model_types),
        "device_model_surface_present": bool(device_model_types),
        "contact_search_surface_present": bool(contact_search_surface_types),
        "support_search_surface_present": bool(support_search_model_types),
        "node_to_surface_proxy_surface_present": bool(node_to_surface_proxy_model_types),
        "support_depth_surface_present": support_depth_score > 0,
        "contact_family_surface_present": contact_family_count >= len(CATEGORY_ORDER),
        "support_search_family_surface_present": bool(
            support_search_family_types
            and all(label in support_search_family_types for label in support_search_family_requirements)
        ),
        "node_to_surface_proxy_family_surface_present": bool(
            node_to_surface_proxy_family_types
            and all(label in node_to_surface_proxy_family_types for label in support_search_family_requirements)
        ),
        "gap_ready": bool(any(row["category"] == "gap" and row["ready"] for row in category_rows)),
        "uplift_ready": bool(any(row["category"] == "uplift" and row["ready"] for row in category_rows)),
        "compression_only_ready": bool(any(row["category"] == "compression-only" and row["ready"] for row in category_rows)),
        "bearing_ready": bool(any(row["category"] == "bearing" and row["ready"] for row in category_rows)),
        "friction_ready": bool(any(row["category"] == "friction" and row["ready"] for row in category_rows)),
        "pounding_ready": bool(any(row["category"] == "pounding" and row["ready"] for row in category_rows)),
        "all_structural_contact_categories_ready": len(ready_categories) == len(CATEGORY_ORDER),
    }

    contract_pass = bool(
        checks["bounded_contact_evidence_pass"]
        and checks["special_link_categories_present"]
        and checks["structural_contact_validation_present"]
        and checks["structural_contact_event_sequence_zero_pass"]
        and checks["contact_family_surface_present"]
        and checks["support_search_family_surface_present"]
        and checks["node_to_surface_proxy_family_surface_present"]
        and checks["all_structural_contact_categories_ready"]
        and not checks["roadmap_tracks_broader_structural_contact_gap"]
    )

    if not checks["bounded_contact_evidence_pass"]:
        reason_code = "ERR_BOUNDED_CONTACT_EVIDENCE_FAIL"
    elif not checks["special_link_categories_present"]:
        reason_code = "ERR_STRUCTURAL_CONTACT_IMPLEMENTATION_MISSING"
    elif not (
        checks["structural_contact_validation_present"]
        and checks["structural_contact_event_sequence_zero_pass"]
        and checks["contact_family_surface_present"]
        and checks["support_search_family_surface_present"]
        and checks["node_to_surface_proxy_family_surface_present"]
        and checks["all_structural_contact_categories_ready"]
    ):
        reason_code = "ERR_STRUCTURAL_CONTACT_VALIDATION_MISSING"
    elif checks["roadmap_tracks_broader_structural_contact_gap"]:
        reason_code = "ERR_STRUCTURAL_CONTACT_GAP_TRACKED"
    else:
        reason_code = "PASS"

    summary_line = (
        f"Structural contact readiness: {('PASS' if contract_pass else 'GAP')} | "
        f"bounded_contact={('yes' if checks['bounded_contact_evidence_pass'] else 'no')} | "
        f"impl={len([k for k in CATEGORY_ORDER if implementation_evidence['per_category'][k]])}/{len(CATEGORY_ORDER)} | "
        f"validated={len([k for k in CATEGORY_ORDER if validation_evidence['per_category'][k]])}/{len(CATEGORY_ORDER)} | "
        f"ready={len(ready_categories)}/{len(CATEGORY_ORDER)} | "
        f"support=contact:{support_surface_evidence['support_link_group_counts']['contact']},"
        f"foundation:{support_surface_evidence['support_link_group_counts']['foundation']},"
        f"device:{support_surface_evidence['support_link_group_counts']['device']} | "
        f"support_search={support_surface_evidence['support_search_model_count']} | "
        f"node_surface_proxy={support_surface_evidence['node_to_surface_proxy_count']} | "
        f"support_depth={support_surface_evidence['support_depth_score']} | "
        f"support_families={len(support_surface_evidence['support_search_family_types'])} | "
        f"proxy_families={len(support_surface_evidence['node_to_surface_proxy_family_types'])} | "
        f"partial_only={_join_labels(partial_only_categories)} | "
        f"missing={_join_labels(missing_categories)}"
    )

    return {
        "schema_version": "1.0",
        "run_id": "phase1-structural-contact-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": input_payload,
        "summary_line": summary_line,
        "contract_pass": bool(contract_pass),
        "checks": checks,
        "category_readiness": category_rows,
        "limitations": [
            "Bounded wheel-rail Hertzian contact evidence does not certify broader structural contact readiness by itself.",
            "Bearing and shear-friction design checks count as partial evidence only and do not satisfy nonlinear link readiness for gap/uplift/compression-only/bearing/friction/pounding.",
            "This gate requires separate broader-link implementation evidence plus validation evidence before any structural contact category is marked ready.",
        ],
        "contact_readiness_evidence": contact_evidence,
        "roadmap_evidence": roadmap_evidence,
        "design_rule_partial_evidence": design_partial,
        "implementation_evidence": implementation_evidence,
        "validation_evidence": validation_evidence,
        "support_surface_evidence": support_surface_evidence,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contact-readiness-report", default="implementation/phase1/contact_readiness_report.json")
    parser.add_argument("--roadmap", default="implementation/phase1/commercial_tool_replacement_roadmap.md")
    parser.add_argument("--kds-rc-rule-engine", default="implementation/phase1/kds_rc_rule_engine.py")
    parser.add_argument("--special-link-library", default="implementation/phase1/special_link_library.py")
    parser.add_argument(
        "--structural-contact-validation-report",
        default="implementation/phase1/structural_contact_validation_report.json",
    )
    parser.add_argument("--out", default="implementation/phase1/structural_contact_gate_report.json")
    args = parser.parse_args()

    input_payload = {
        "contact_readiness_report": str(args.contact_readiness_report),
        "roadmap": str(args.roadmap),
        "kds_rc_rule_engine": str(args.kds_rc_rule_engine),
        "special_link_library": str(args.special_link_library),
        "structural_contact_validation_report": str(args.structural_contact_validation_report),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_structural_contact_gate")

        contact_path = Path(args.contact_readiness_report)
        roadmap_path = Path(args.roadmap)
        rule_engine_path = Path(args.kds_rc_rule_engine)
        special_link_path = Path(args.special_link_library)
        validation_path = Path(args.structural_contact_validation_report)

        payload = _build_report(
            input_payload=input_payload,
            contact_payload=_load_json(contact_path),
            roadmap_text=_load_text(roadmap_path),
            rule_engine_text=_load_text(rule_engine_path),
            special_link_text=_load_text(special_link_path),
            special_link_path=special_link_path,
            validation_payload=_load_json(validation_path),
        )
        payload["evidence_paths"] = {
            "contact_readiness_report": {
                "path": str(contact_path),
                "sha256": _sha256(contact_path) if contact_path.exists() else "",
            },
            "roadmap": {
                "path": str(roadmap_path),
                "sha256": _sha256(roadmap_path) if roadmap_path.exists() else "",
            },
            "kds_rc_rule_engine": {
                "path": str(rule_engine_path),
                "sha256": _sha256(rule_engine_path) if rule_engine_path.exists() else "",
            },
            "special_link_library": {
                "path": str(special_link_path),
                "sha256": _sha256(special_link_path) if special_link_path.exists() else "",
            },
            "structural_contact_validation_report": {
                "path": str(validation_path),
                "sha256": _sha256(validation_path) if validation_path.exists() else "",
            },
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote structural contact gate report: {out}")
        if not payload["contract_pass"]:
            raise SystemExit(1)
    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-structural-contact-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "summary_line": "Structural contact readiness: GAP | invalid_input=yes",
            "contract_pass": False,
            "checks": {"input_valid": False},
            "limitations": [],
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote structural contact gate report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
