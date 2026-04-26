#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_MODEL = Path("implementation/phase1/open_data/midas/midas_generator_33.json")
DEFAULT_BENCHMARK_CASES = Path("implementation/phase1/commercial_benchmark_cases.from_csv.json")
DEFAULT_CODECHECK_REPORT = Path("implementation/phase1/release/kds_compliance/code_check_report.json")
DEFAULT_OUT = Path("implementation/phase1/open_data/midas/kds_geometry_bridge_registry.heuristic.json")
DEFAULT_EXACT_REGISTRY = Path("implementation/phase1/open_data/midas/kds_geometry_bridge_registry.exact.json")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return payload


def _row_review_keys(row: dict[str, Any]) -> list[str]:
    keys = {
        str(row.get("review_member_id", "") or "").strip(),
        str(row.get("review_case_id", "") or "").strip(),
    }
    keys.update(str(item).strip() for item in (row.get("review_keys") or []) if str(item).strip())
    keys.discard("")
    return sorted(keys)


def _registry_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("mappings") if isinstance(payload.get("mappings"), list) else payload.get("bridge_rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _source_label(payload: dict[str, Any]) -> str:
    return str(
        payload.get("source", "")
        or payload.get("provenance", "")
        or payload.get("registry_kind", "")
        or "external_registry"
    ).strip() or "external_registry"


def _row_is_heuristic(row: dict[str, Any]) -> bool:
    confidence = str(row.get("match_confidence", "") or "").strip().lower()
    return confidence.startswith("heuristic")


def _row_is_reviewer_verified(row: dict[str, Any]) -> bool:
    if _is_truthy(row.get("reviewer_verified")):
        return True
    strategy = str(row.get("match_strategy", "") or "").strip().lower()
    confidence = str(row.get("match_confidence", "") or "").strip().lower()
    source_label = str(row.get("registry_source_label", "") or row.get("source", "") or "").strip().lower()
    return any(
        token in strategy or token in confidence or token in source_label
        for token in ("reviewer_verified", "manual_verified", "external_registry_manual")
    )


def _unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _row_sort_key(row: dict[str, Any]) -> tuple[float, str, str, str]:
    try:
        dcr = float(row.get("dcr", 0.0) or 0.0)
    except (TypeError, ValueError):
        dcr = 0.0
    return (
        -dcr,
        str(row.get("combination", "") or ""),
        str(row.get("component", "") or ""),
        str(row.get("clause", "") or ""),
    )


def _top_row_label(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "n/a"
    top_row = sorted(rows, key=_row_sort_key)[0]
    try:
        dcr = float(top_row.get("dcr", 0.0) or 0.0)
    except (TypeError, ValueError):
        dcr = 0.0
    return (
        f"{str(top_row.get('combination', '') or '').strip()} | "
        f"{str(top_row.get('component', '') or '').strip()} | "
        f"{str(top_row.get('clause', '') or '').strip()} | "
        f"D/C={dcr:.3f}"
    )


def _model_member_handle_inventory(model_payload: dict[str, Any]) -> tuple[set[str], str]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    member_rows = [row for row in (metadata.get("members") or []) if isinstance(row, dict)]
    member_handles = {
        str(row.get("id", "") or "").strip()
        for row in member_rows
        if str(row.get("id", "") or "").strip()
    }
    if member_handles:
        return member_handles, "aggregate_member_id"
    element_handles = {
        str(row.get("id", "") or "").strip()
        for row in (model.get("elements") or [])
        if isinstance(row, dict) and str(row.get("id", "") or "").strip()
    }
    return element_handles, "element_id"


def _model_section_inventory(model_payload: dict[str, Any]) -> set[str]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    return {
        str(row.get("section_id", "") or "").strip()
        for row in (model.get("elements") or [])
        if isinstance(row, dict) and str(row.get("section_id", "") or "").strip()
    }


def _code_check_load_inventory(code_check_report: dict[str, Any]) -> set[str]:
    return {
        str(row.get("combination", "") or "").strip()
        for row in (code_check_report.get("member_check_rows") or [])
        if isinstance(row, dict) and str(row.get("combination", "") or "").strip()
    }


def _crosswalk_status(count: int, expected: int) -> str:
    return "PASS" if expected == 0 or count >= expected else "CHECK"


def _mapping_member_handle(row: dict[str, Any]) -> str:
    return (
        str(row.get("full_crosswalk_target_member_handle", "") or "").strip()
        or str(row.get("surrogate_aggregate_member_id", "") or "").strip()
        or str(row.get("baseline_focus_member_id", "") or "").strip()
    )


def _mapping_member_handles(row: dict[str, Any]) -> set[str]:
    if isinstance(row.get("full_crosswalk_member_handles"), list):
        return {
            str(item).strip()
            for item in (row.get("full_crosswalk_member_handles") or [])
            if str(item).strip()
        }
    handle = _mapping_member_handle(row)
    return {handle} if handle else set()


def _mapping_section_id(row: dict[str, Any]) -> str:
    text = str(row.get("full_crosswalk_target_section_id", "") or "").strip()
    if text:
        return text
    snapshot = row.get("review_geometry_snapshot")
    if isinstance(snapshot, dict):
        return str(snapshot.get("section_id", "") or "").strip()
    return ""


def _mapping_section_ids(row: dict[str, Any]) -> set[str]:
    if isinstance(row.get("full_crosswalk_section_ids"), list):
        return {
            str(item).strip()
            for item in (row.get("full_crosswalk_section_ids") or [])
            if str(item).strip()
        }
    section_id = _mapping_section_id(row)
    return {section_id} if section_id else set()


def _mapping_load_names(row: dict[str, Any]) -> list[str]:
    values = row.get("full_crosswalk_load_combination_names")
    if isinstance(values, list):
        return _unique_strings(values)
    values = row.get("row_provenance_combination_names")
    if isinstance(values, list):
        return _unique_strings(values)
    return []


def _summary_crosswalk_handles(summary: dict[str, Any], key: str) -> set[str]:
    values = summary.get(key)
    if not isinstance(values, list):
        return set()
    return {str(item).strip() for item in values if str(item).strip()}


def _registry_full_crosswalk_summary(
    *,
    mappings: list[dict[str, Any]],
    model_payload: dict[str, Any],
    code_check_report: dict[str, Any],
) -> dict[str, Any]:
    expected_member_handles, member_handle_kind = _model_member_handle_inventory(model_payload)
    expected_sections = _model_section_inventory(model_payload)
    expected_loads = _code_check_load_inventory(code_check_report)

    bridged_member_handles = {
        handle
        for row in mappings
        for handle in _mapping_member_handles(row)
    }
    bridged_sections = {
        section_id
        for row in mappings
        for section_id in _mapping_section_ids(row)
    }
    bridged_loads = {
        str(item).strip()
        for row in mappings
        for item in _mapping_load_names(row)
        if str(item).strip()
    }

    member_count = len(bridged_member_handles & expected_member_handles)
    section_count = len(bridged_sections & expected_sections)
    load_count = len(bridged_loads & expected_loads)

    member_expected = len(expected_member_handles)
    section_expected = len(expected_sections)
    load_expected = len(expected_loads)

    member_status = _crosswalk_status(member_count, member_expected)
    section_status = _crosswalk_status(section_count, section_expected)
    load_status = _crosswalk_status(load_count, load_expected)
    expected_member_handle_list = sorted(expected_member_handles)
    expected_section_id_list = sorted(expected_sections)
    expected_load_name_list = sorted(expected_loads)
    missing_member_handles = sorted(expected_member_handles - bridged_member_handles)
    missing_section_ids = sorted(expected_sections - bridged_sections)
    missing_load_names = sorted(expected_loads - bridged_loads)

    return {
        "full_member_crosswalk_count": member_count,
        "full_member_crosswalk_expected": member_expected,
        "full_member_crosswalk_status": member_status,
        "full_member_crosswalk_handle_kind": member_handle_kind,
        "full_member_crosswalk_handles": sorted(bridged_member_handles),
        "full_member_crosswalk_expected_handles": expected_member_handle_list,
        "full_member_crosswalk_missing_handles": missing_member_handles,
        "full_section_crosswalk_count": section_count,
        "full_section_crosswalk_expected": section_expected,
        "full_section_crosswalk_status": section_status,
        "full_section_crosswalk_ids": sorted(bridged_sections),
        "full_section_crosswalk_expected_ids": expected_section_id_list,
        "full_section_crosswalk_missing_ids": missing_section_ids,
        "full_load_crosswalk_count": load_count,
        "full_load_crosswalk_expected": load_expected,
        "full_load_crosswalk_status": load_status,
        "full_load_crosswalk_names": sorted(bridged_loads),
        "full_load_crosswalk_expected_names": expected_load_name_list,
        "full_load_crosswalk_missing_names": missing_load_names,
        "full_crosswalk_summary_label": (
            f"members={member_count}/{member_expected} {member_status} | "
            f"sections={section_count}/{section_expected} {section_status} | "
            f"loads={load_count}/{load_expected} {load_status}"
        ),
    }


def _with_full_crosswalk_summary(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    summary = out.get("summary") if isinstance(out.get("summary"), dict) else {}
    mappings = _registry_rows(out)
    member_expected = int(summary.get("full_member_crosswalk_expected", 0) or 0)
    section_expected = int(summary.get("full_section_crosswalk_expected", 0) or 0)
    load_expected = int(summary.get("full_load_crosswalk_expected", 0) or 0)
    member_handle_kind = str(summary.get("full_member_crosswalk_handle_kind", "") or "")
    if (
        "full_member_crosswalk_count" in summary
        and "full_section_crosswalk_count" in summary
        and "full_load_crosswalk_count" in summary
    ):
        return out
    bridged_member_handles = {
        handle
        for row in mappings
        for handle in _mapping_member_handles(row)
    }
    bridged_section_ids = {
        section_id
        for row in mappings
        for section_id in _mapping_section_ids(row)
    }
    bridged_load_names = {
        str(item).strip()
        for row in mappings
        for item in _mapping_load_names(row)
        if str(item).strip()
    }
    member_count = len(bridged_member_handles)
    section_count = len(bridged_section_ids)
    load_count = len(bridged_load_names)
    merged_summary = {
        **summary,
        "full_member_crosswalk_count": member_count,
        "full_member_crosswalk_expected": member_expected,
        "full_member_crosswalk_status": _crosswalk_status(member_count, member_expected),
        "full_member_crosswalk_handle_kind": member_handle_kind,
        "full_member_crosswalk_handles": sorted(bridged_member_handles),
        "full_member_crosswalk_expected_handles": sorted(
            _summary_crosswalk_handles(summary, "full_member_crosswalk_expected_handles") or bridged_member_handles
        ),
        "full_member_crosswalk_missing_handles": sorted(
            _summary_crosswalk_handles(summary, "full_member_crosswalk_missing_handles")
        ),
        "full_section_crosswalk_count": section_count,
        "full_section_crosswalk_expected": section_expected,
        "full_section_crosswalk_status": _crosswalk_status(section_count, section_expected),
        "full_section_crosswalk_ids": sorted(bridged_section_ids),
        "full_section_crosswalk_expected_ids": sorted(
            _summary_crosswalk_handles(summary, "full_section_crosswalk_expected_ids") or bridged_section_ids
        ),
        "full_section_crosswalk_missing_ids": sorted(
            _summary_crosswalk_handles(summary, "full_section_crosswalk_missing_ids")
        ),
        "full_load_crosswalk_count": load_count,
        "full_load_crosswalk_expected": load_expected,
        "full_load_crosswalk_status": _crosswalk_status(load_count, load_expected),
        "full_load_crosswalk_names": sorted(bridged_load_names),
        "full_load_crosswalk_expected_names": sorted(
            _summary_crosswalk_handles(summary, "full_load_crosswalk_expected_names") or bridged_load_names
        ),
        "full_load_crosswalk_missing_names": sorted(
            _summary_crosswalk_handles(summary, "full_load_crosswalk_missing_names")
        ),
        "full_crosswalk_summary_label": (
            f"members={member_count}/{member_expected} {_crosswalk_status(member_count, member_expected)} | "
            f"sections={section_count}/{section_expected} {_crosswalk_status(section_count, section_expected)} | "
            f"loads={load_count}/{load_expected} {_crosswalk_status(load_count, load_expected)}"
        ),
    }
    out["summary"] = merged_summary
    return out


def _row_provenance_payload(
    *,
    review_member_id: str,
    review_case_id: str,
    baseline_focus_member_id: str,
    case_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = sorted((dict(row) for row in case_rows if isinstance(row, dict)), key=_row_sort_key)
    member_type_names = _unique_strings([row.get("member_type") for row in rows])
    combination_names = _unique_strings([row.get("combination") for row in rows])
    clause_names = _unique_strings([row.get("clause") for row in rows])
    component_names = _unique_strings([row.get("component") for row in rows])
    rule_family_names = _unique_strings([row.get("rule_family") for row in rows])
    hazard_names = _unique_strings([row.get("hazard_type") for row in rows])
    topology_names = _unique_strings([row.get("topology_type") for row in rows])
    top_row_label = _top_row_label(rows)
    member_type_label = ", ".join(member_type_names) if member_type_names else "unknown"
    return {
        "mapped": bool(rows),
        "review_keys_label": ", ".join(_unique_strings([review_member_id, review_case_id])),
        "member_inventory_count": len(member_type_names),
        "member_inventory_member_type_names": member_type_names,
        "member_inventory_member_type_label": member_type_label,
        "member_inventory_summary_label": (
            f"review={review_member_id} | case={review_case_id} | "
            f"baseline={baseline_focus_member_id} | member_types={member_type_label}"
        ),
        "row_provenance_row_count": len(rows),
        "row_provenance_combination_count": len(combination_names),
        "row_provenance_clause_count": len(clause_names),
        "row_provenance_component_count": len(component_names),
        "row_provenance_rule_family_count": len(rule_family_names),
        "row_provenance_hazard_count": len(hazard_names),
        "row_provenance_topology_count": len(topology_names),
        "row_provenance_combination_names": combination_names,
        "row_provenance_clause_names": clause_names,
        "row_provenance_component_names": component_names,
        "row_provenance_rule_family_names": rule_family_names,
        "row_provenance_hazard_names": hazard_names,
        "row_provenance_topology_names": topology_names,
        "row_provenance_top_row_label": top_row_label,
        "row_provenance_summary_label": (
            f"rows={len(rows)} | combos={len(combination_names)} | "
            f"clauses={len(clause_names)} | top={top_row_label}"
        ),
        "clause_provenance_summary_label": (
            f"clauses={len(clause_names)} | rules={len(rule_family_names)} | "
            f"hazards={len(hazard_names)} | top={top_row_label}"
        ),
        "clause_provenance_clause_names": clause_names,
        "clause_provenance_rule_family_names": rule_family_names,
        "clause_provenance_hazard_names": hazard_names,
        "clause_provenance_topology_names": topology_names,
        "row_provenance_rows": rows,
    }


def _normalize_registry_row(
    row: dict[str, Any],
    *,
    source_label: str,
    contract_version: str,
) -> dict[str, Any] | None:
    baseline_focus_member_id = str(row.get("baseline_focus_member_id", "") or "").strip()
    review_keys = _row_review_keys(row)
    if not baseline_focus_member_id or not review_keys:
        return None
    normalized = dict(row)
    normalized["review_member_id"] = str(row.get("review_member_id", "") or review_keys[0]).strip()
    normalized["review_case_id"] = str(row.get("review_case_id", "") or normalized["review_member_id"]).strip()
    normalized["review_keys"] = review_keys
    normalized["review_keys_label"] = str(row.get("review_keys_label", "") or ", ".join(review_keys)).strip()
    normalized["baseline_focus_member_id"] = baseline_focus_member_id
    normalized["match_strategy"] = str(row.get("match_strategy", "") or "external_registry").strip() or "external_registry"
    normalized["match_confidence"] = str(row.get("match_confidence", "") or "external_map").strip() or "external_map"
    normalized["registry_source_label"] = source_label
    normalized["registry_contract_version"] = contract_version
    normalized["reviewer_verified"] = _is_truthy(row.get("reviewer_verified")) or _row_is_reviewer_verified(
        {**row, "registry_source_label": source_label}
    )
    normalized["mapped"] = _is_truthy(row.get("mapped")) if "mapped" in row else True
    review_geometry_snapshot = row.get("review_geometry_snapshot")
    if isinstance(review_geometry_snapshot, dict) and review_geometry_snapshot:
        normalized["review_geometry_snapshot"] = dict(review_geometry_snapshot)
    return normalized


def _row_priority(row: dict[str, Any]) -> tuple[int, int, str, str]:
    heuristic = _row_is_heuristic(row)
    reviewer_verified = _row_is_reviewer_verified(row)
    strategy = str(row.get("match_strategy", "") or "").strip().lower()
    confidence = str(row.get("match_confidence", "") or "").strip().lower()
    if reviewer_verified and not heuristic:
        band = 4
    elif not heuristic:
        band = 3
    else:
        band = 2
    directness = 1 if strategy.endswith("direct") or confidence == "exact_id" else 0
    return (band, directness, confidence, strategy)


def merge_registry_payloads(*registry_payloads: dict[str, Any] | None) -> dict[str, Any]:
    payloads = [payload for payload in registry_payloads if isinstance(payload, dict)]
    rowful_payloads = [payload for payload in payloads if _registry_rows(payload)]
    if rowful_payloads:
        payloads = rowful_payloads
    if not payloads:
        return {}
    if len(payloads) == 1:
        return _with_full_crosswalk_summary(payloads[0])

    selected_by_review_key: dict[str, dict[str, Any]] = {}
    limitations: list[str] = []
    for payload in payloads:
        source_label = _source_label(payload)
        contract_version = str(payload.get("contract_version", "") or "0.1.0").strip() or "0.1.0"
        rows = _registry_rows(payload)
        payload_limitations = payload.get("limitations") if isinstance(payload.get("limitations"), list) else []
        for item in payload_limitations:
            text = str(item).strip()
            if text and text not in limitations:
                limitations.append(text)
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized = _normalize_registry_row(row, source_label=source_label, contract_version=contract_version)
            if normalized is None:
                continue
            for review_key in normalized["review_keys"]:
                existing = selected_by_review_key.get(review_key)
                if existing is None or _row_priority(normalized) > _row_priority(existing):
                    selected_by_review_key[review_key] = normalized

    merged_rows_by_signature: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in selected_by_review_key.values():
        signature = (
            tuple(row.get("review_keys") or []),
            str(row.get("baseline_focus_member_id", "") or ""),
            str(row.get("match_strategy", "") or ""),
            str(row.get("match_confidence", "") or ""),
            str(row.get("registry_source_label", "") or ""),
        )
        merged_rows_by_signature[signature] = row

    merged_rows = list(merged_rows_by_signature.values())
    source_counts: Counter[str] = Counter(str(row.get("registry_source_label", "") or "external_registry") for row in merged_rows)
    confidence_counts: Counter[str] = Counter(str(row.get("match_confidence", "") or "external_map") for row in merged_rows)
    exact_mapping_count = sum(1 for row in merged_rows if not _row_is_heuristic(row))
    heuristic_mapping_count = sum(1 for row in merged_rows if _row_is_heuristic(row))
    reviewer_verified_mapping_count = sum(1 for row in merged_rows if _row_is_reviewer_verified(row))
    source_labels = sorted(source_counts)
    contract_versions = sorted({str(row.get("registry_contract_version", "") or "0.1.0") for row in merged_rows})
    expected_member_handles = {
        handle
        for payload in payloads
        if isinstance(payload.get("summary"), dict)
        for handle in _summary_crosswalk_handles(payload.get("summary") or {}, "full_member_crosswalk_expected_handles")
        or _summary_crosswalk_handles(payload.get("summary") or {}, "full_member_crosswalk_handles")
    }
    expected_section_ids = {
        section_id
        for payload in payloads
        if isinstance(payload.get("summary"), dict)
        for section_id in _summary_crosswalk_handles(payload.get("summary") or {}, "full_section_crosswalk_expected_ids")
        or _summary_crosswalk_handles(payload.get("summary") or {}, "full_section_crosswalk_ids")
    }
    expected_load_names = {
        load_name
        for payload in payloads
        if isinstance(payload.get("summary"), dict)
        for load_name in _summary_crosswalk_handles(payload.get("summary") or {}, "full_load_crosswalk_expected_names")
        or _summary_crosswalk_handles(payload.get("summary") or {}, "full_load_crosswalk_names")
    }
    full_member_crosswalk_expected = max(
        (
            int((payload.get("summary") or {}).get("full_member_crosswalk_expected", 0) or 0)
            for payload in payloads
            if isinstance(payload.get("summary"), dict)
        ),
        default=0,
    )
    if expected_member_handles:
        full_member_crosswalk_expected = len(expected_member_handles)
    full_section_crosswalk_expected = max(
        (
            int((payload.get("summary") or {}).get("full_section_crosswalk_expected", 0) or 0)
            for payload in payloads
            if isinstance(payload.get("summary"), dict)
        ),
        default=0,
    )
    if expected_section_ids:
        full_section_crosswalk_expected = len(expected_section_ids)
    full_load_crosswalk_expected = max(
        (
            int((payload.get("summary") or {}).get("full_load_crosswalk_expected", 0) or 0)
            for payload in payloads
            if isinstance(payload.get("summary"), dict)
        ),
        default=0,
    )
    if expected_load_names:
        full_load_crosswalk_expected = len(expected_load_names)
    full_member_crosswalk_handle_kind = next(
        (
            str((payload.get("summary") or {}).get("full_member_crosswalk_handle_kind", "") or "")
            for payload in payloads
            if isinstance(payload.get("summary"), dict)
            and str((payload.get("summary") or {}).get("full_member_crosswalk_handle_kind", "") or "")
        ),
        "",
    )
    merged_member_handles = {
        handle
        for row in merged_rows
        for handle in _mapping_member_handles(row)
    }
    merged_section_ids = {
        section_id
        for row in merged_rows
        for section_id in _mapping_section_ids(row)
    }
    merged_load_names = {
        str(item).strip()
        for row in merged_rows
        for item in _mapping_load_names(row)
        if str(item).strip()
    }
    full_member_crosswalk_count = len(
        merged_member_handles & expected_member_handles
    ) if expected_member_handles else len(merged_member_handles)
    full_section_crosswalk_count = len(
        merged_section_ids & expected_section_ids
    ) if expected_section_ids else len(merged_section_ids)
    full_load_crosswalk_count = len(
        merged_load_names & expected_load_names
    ) if expected_load_names else len(merged_load_names)
    full_member_crosswalk_status = _crosswalk_status(
        full_member_crosswalk_count,
        full_member_crosswalk_expected,
    )
    full_section_crosswalk_status = _crosswalk_status(
        full_section_crosswalk_count,
        full_section_crosswalk_expected,
    )
    full_load_crosswalk_status = _crosswalk_status(
        full_load_crosswalk_count,
        full_load_crosswalk_expected,
    )
    return {
        "contract_version": "0.4.0",
        "registry_kind": "kds_geometry_bridge_registry",
        "source": "merged_registry",
        "source_labels": source_labels,
        "merge_strategy": "reviewer_verified_exact_overrides_heuristic_by_review_key",
        "limitations": limitations,
        "summary": {
            "mapping_count": len(merged_rows),
            "source_counts": {str(key): int(value) for key, value in sorted(source_counts.items())},
            "confidence_counts": {str(key): int(value) for key, value in sorted(confidence_counts.items())},
            "exact_mapping_count": int(exact_mapping_count),
            "heuristic_mapping_count": int(heuristic_mapping_count),
            "reviewer_verified_mapping_count": int(reviewer_verified_mapping_count),
            "merged_contract_versions": contract_versions,
            "full_member_crosswalk_count": int(full_member_crosswalk_count),
            "full_member_crosswalk_expected": int(full_member_crosswalk_expected),
            "full_member_crosswalk_status": full_member_crosswalk_status,
            "full_member_crosswalk_handle_kind": full_member_crosswalk_handle_kind,
            "full_member_crosswalk_handles": sorted(merged_member_handles),
            "full_member_crosswalk_expected_handles": sorted(expected_member_handles or merged_member_handles),
            "full_member_crosswalk_missing_handles": sorted(expected_member_handles - merged_member_handles) if expected_member_handles else [],
            "full_section_crosswalk_count": int(full_section_crosswalk_count),
            "full_section_crosswalk_expected": int(full_section_crosswalk_expected),
            "full_section_crosswalk_status": full_section_crosswalk_status,
            "full_section_crosswalk_ids": sorted(merged_section_ids),
            "full_section_crosswalk_expected_ids": sorted(expected_section_ids or merged_section_ids),
            "full_section_crosswalk_missing_ids": sorted(expected_section_ids - merged_section_ids) if expected_section_ids else [],
            "full_load_crosswalk_count": int(full_load_crosswalk_count),
            "full_load_crosswalk_expected": int(full_load_crosswalk_expected),
            "full_load_crosswalk_status": full_load_crosswalk_status,
            "full_load_crosswalk_names": sorted(merged_load_names),
            "full_load_crosswalk_expected_names": sorted(expected_load_names or merged_load_names),
            "full_load_crosswalk_missing_names": sorted(expected_load_names - merged_load_names) if expected_load_names else [],
            "full_crosswalk_summary_label": (
                f"members={full_member_crosswalk_count}/{full_member_crosswalk_expected} {full_member_crosswalk_status} | "
                f"sections={full_section_crosswalk_count}/{full_section_crosswalk_expected} {full_section_crosswalk_status} | "
                f"loads={full_load_crosswalk_count}/{full_load_crosswalk_expected} {full_load_crosswalk_status}"
            ),
        },
        "mappings": [
            {
                key: value
                for key, value in row.items()
                if key
                in {
                    "review_member_id",
                    "review_case_id",
                    "review_keys",
                    "review_keys_label",
                    "baseline_focus_member_id",
                    "match_strategy",
                    "match_confidence",
                    "selector_kind",
                    "source_family",
                    "source_topology_type",
                    "source_member_type",
                    "source_hazard_type",
                    "source_element_mix",
                    "surrogate_geometry_kind",
                    "surrogate_aggregate_member_id",
                    "full_crosswalk_target_member_handle",
                    "full_crosswalk_target_section_id",
                    "full_crosswalk_member_groups",
                    "full_crosswalk_member_handles",
                    "full_crosswalk_member_handle_count",
                    "full_crosswalk_section_groups",
                    "full_crosswalk_section_ids",
                    "full_crosswalk_section_id_count",
                    "full_crosswalk_load_combination_names",
                    "full_crosswalk_load_combination_count",
                    "full_crosswalk_global_member_handles",
                    "full_crosswalk_global_member_handle_count",
                    "full_crosswalk_global_section_ids",
                    "full_crosswalk_global_section_id_count",
                    "full_crosswalk_global_load_combination_names",
                    "full_crosswalk_global_load_combination_count",
                    "full_crosswalk_inventory_scope",
                    "full_crosswalk_global_inventory_scope",
                    "full_crosswalk_inventory_summary_label",
                    "note",
                    "mapped",
                    "review_geometry_snapshot",
                    "member_inventory_count",
                    "member_inventory_member_type_names",
                    "member_inventory_member_type_label",
                    "member_inventory_summary_label",
                    "row_provenance_row_count",
                    "row_provenance_combination_count",
                    "row_provenance_clause_count",
                    "row_provenance_component_count",
                    "row_provenance_rule_family_count",
                    "row_provenance_hazard_count",
                    "row_provenance_topology_count",
                    "row_provenance_combination_names",
                    "row_provenance_clause_names",
                    "row_provenance_component_names",
                    "row_provenance_rule_family_names",
                    "row_provenance_hazard_names",
                    "row_provenance_topology_names",
                    "row_provenance_top_row_label",
                    "row_provenance_summary_label",
                    "clause_provenance_summary_label",
                    "clause_provenance_clause_names",
                    "clause_provenance_rule_family_names",
                    "clause_provenance_hazard_names",
                    "clause_provenance_topology_names",
                    "row_provenance_rows",
                    "registry_source_label",
                    "registry_contract_version",
                    "reviewer_verified",
                }
            }
            for row in merged_rows
        ],
    }


def _classify_element_kind(dx: float, dy: float, dz: float) -> str:
    adx, ady, adz = abs(dx), abs(dy), abs(dz)
    horiz = math.hypot(dx, dy)
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length <= 1e-9:
        return "point"
    if adz / length > 0.85 and horiz / length < 0.3:
        return "vertical"
    if adz / length < 0.15 and horiz / length > 0.85:
        if horiz <= 1e-9:
            return "point"
        if adx / horiz > 0.85:
            return "x_beam"
        if ady / horiz > 0.85:
            return "y_beam"
        return "plan_diagonal"
    return "space_diagonal"


def _full_crosswalk_group_for_kind(kind: str) -> str:
    if kind in {"x_beam", "y_beam"}:
        return "horizontal_beam"
    if kind == "plan_diagonal":
        return "plan_diagonal"
    if kind == "vertical":
        return "vertical"
    return "other"


def _selector_full_crosswalk_groups(selector_kind: str) -> tuple[list[str], list[str]]:
    normalized = str(selector_kind or "").strip().lower()
    if "plan_diagonal" in normalized:
        return ["plan_diagonal"], ["plan_diagonal"]
    if "vertical" in normalized:
        return ["vertical"], ["vertical", "other"]
    if "x_beam" in normalized:
        return ["horizontal_beam"], ["horizontal_beam"]
    return [], []


def _inventory_union(values_by_group: dict[str, list[str]], groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in values_by_group.get(group, []):
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return merged


def _build_member_lookup(model: dict[str, Any]) -> dict[str, str]:
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    member_rows = [row for row in (metadata.get("members") or []) if isinstance(row, dict)]
    lookup: dict[str, str] = {}
    for row in member_rows:
        aggregate_id = str(row.get("id", "") or "").strip()
        if not aggregate_id:
            continue
        element_seed = str(row.get("element_seed", "") or "").strip()
        if element_seed:
            lookup.setdefault(element_seed, aggregate_id)
        for element_id in (str(item).strip() for item in (row.get("element_ids") or []) if str(item).strip()):
            lookup.setdefault(element_id, aggregate_id)
    return lookup


def _build_element_catalog(model_payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, float]]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    nodes = {
        int(row.get("id")): row
        for row in (model.get("nodes") or [])
        if isinstance(row, dict) and row.get("id") is not None
    }
    member_lookup = _build_member_lookup(model)
    centroid_x = 0.0
    centroid_y = 0.0
    if nodes:
        centroid_x = sum(float(row.get("x", 0.0) or 0.0) for row in nodes.values()) / float(len(nodes))
        centroid_y = sum(float(row.get("y", 0.0) or 0.0) for row in nodes.values()) / float(len(nodes))
    catalog: list[dict[str, Any]] = []
    for row in (model.get("elements") or []):
        if not isinstance(row, dict):
            continue
        element_id = str(row.get("id", "") or "").strip()
        node_ids = [int(item) for item in (row.get("node_ids") or []) if isinstance(item, (int, float))]
        if len(node_ids) != 2 or not element_id:
            continue
        pts = [nodes.get(node_ids[0]), nodes.get(node_ids[1])]
        if not all(isinstance(item, dict) for item in pts):
            continue
        p0 = pts[0]
        p1 = pts[1]
        dx = float(p1.get("x", 0.0) or 0.0) - float(p0.get("x", 0.0) or 0.0)
        dy = float(p1.get("y", 0.0) or 0.0) - float(p0.get("y", 0.0) or 0.0)
        dz = float(p1.get("z", 0.0) or 0.0) - float(p0.get("z", 0.0) or 0.0)
        kind = _classify_element_kind(dx, dy, dz)
        if kind == "point":
            continue
        xmid = (float(p0.get("x", 0.0) or 0.0) + float(p1.get("x", 0.0) or 0.0)) / 2.0
        ymid = (float(p0.get("y", 0.0) or 0.0) + float(p1.get("y", 0.0) or 0.0)) / 2.0
        zmid = (float(p0.get("z", 0.0) or 0.0) + float(p1.get("z", 0.0) or 0.0)) / 2.0
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        catalog.append(
            {
                "element_id": element_id,
                "aggregate_member_id": member_lookup.get(element_id, ""),
                "family": str(row.get("family", "") or "").strip() or "unknown",
                "section_id": str(row.get("section_id", "") or "").strip(),
                "geometry_kind": kind,
                "xmid": xmid,
                "ymid": ymid,
                "zmid": zmid,
                "length": length,
                "centroid_distance": math.hypot(xmid - centroid_x, ymid - centroid_y),
            }
        )
    return catalog, {"x": centroid_x, "y": centroid_y}


def _build_full_crosswalk_inventory(model_payload: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    nodes = {
        int(row.get("id")): row
        for row in (model.get("nodes") or [])
        if isinstance(row, dict) and row.get("id") is not None
    }
    member_lookup = _build_member_lookup(model)
    section_ids_by_group: dict[str, set[str]] = {}
    member_handles_by_group: dict[str, set[str]] = {}
    for row in (model.get("elements") or []):
        if not isinstance(row, dict):
            continue
        element_id = str(row.get("id", "") or "").strip()
        if not element_id:
            continue
        node_ids = [int(item) for item in (row.get("node_ids") or []) if isinstance(item, (int, float))]
        section_id = str(row.get("section_id", "") or "").strip()
        group = "other"
        if len(node_ids) == 2:
            node0 = nodes.get(node_ids[0])
            node1 = nodes.get(node_ids[1])
            if isinstance(node0, dict) and isinstance(node1, dict):
                group = _full_crosswalk_group_for_kind(
                    _classify_element_kind(
                        float(node1.get("x", 0.0) or 0.0) - float(node0.get("x", 0.0) or 0.0),
                        float(node1.get("y", 0.0) or 0.0) - float(node0.get("y", 0.0) or 0.0),
                        float(node1.get("z", 0.0) or 0.0) - float(node0.get("z", 0.0) or 0.0),
                    )
                )
        if section_id:
            section_ids_by_group.setdefault(group, set()).add(section_id)
        aggregate_member_id = member_lookup.get(element_id, "")
        if aggregate_member_id:
            member_handles_by_group.setdefault(group, set()).add(aggregate_member_id)
    return {
        "member_handles_by_group": {
            group: sorted(values)
            for group, values in sorted(member_handles_by_group.items())
        },
        "section_ids_by_group": {
            group: sorted(values)
            for group, values in sorted(section_ids_by_group.items())
        },
    }


def _selector_kind(member_type: str, topology_type: str, element_mix: str) -> str:
    member = str(member_type or "").strip().lower()
    topology = str(topology_type or "").strip().lower()
    mix = str(element_mix or "").strip().lower()
    if member == "brace" or topology == "truss":
        return "plan_diagonal_surrogate"
    if member == "wall" or topology == "wall-frame":
        return "vertical_perimeter_surrogate"
    if member == "column" or topology == "outrigger" or mix == "shell_beam_mix":
        return "vertical_core_surrogate"
    return "x_beam_surrogate"


def _pick_candidate(catalog: list[dict[str, Any]], selector_kind: str) -> dict[str, Any] | None:
    if selector_kind == "plan_diagonal_surrogate":
        rows = [row for row in catalog if row.get("geometry_kind") == "plan_diagonal"]
        rows.sort(key=lambda row: (-float(row.get("zmid", 0.0)), -float(row.get("length", 0.0)), float(row.get("centroid_distance", 0.0)), str(row.get("element_id", ""))))
        return rows[0] if rows else None
    if selector_kind == "vertical_core_surrogate":
        rows = [row for row in catalog if row.get("geometry_kind") == "vertical"]
        rows.sort(key=lambda row: (-float(row.get("zmid", 0.0)), float(row.get("centroid_distance", 0.0)), -float(row.get("length", 0.0)), str(row.get("element_id", ""))))
        return rows[0] if rows else None
    if selector_kind == "vertical_perimeter_surrogate":
        rows = [row for row in catalog if row.get("geometry_kind") == "vertical"]
        rows.sort(key=lambda row: (-float(row.get("zmid", 0.0)), -float(row.get("centroid_distance", 0.0)), -float(row.get("length", 0.0)), str(row.get("element_id", ""))))
        return rows[0] if rows else None
    rows = [row for row in catalog if row.get("geometry_kind") == "x_beam"]
    rows.sort(key=lambda row: (-float(row.get("zmid", 0.0)), -float(row.get("length", 0.0)), float(row.get("centroid_distance", 0.0)), str(row.get("element_id", ""))))
    return rows[0] if rows else None


def build_registry(
    *,
    model_payload: dict[str, Any],
    benchmark_payload: dict[str, Any],
    code_check_report: dict[str, Any],
) -> dict[str, Any]:
    catalog, centroid = _build_element_catalog(model_payload)
    full_crosswalk_inventory = _build_full_crosswalk_inventory(model_payload)
    benchmark_cases = {
        str(row.get("case_id", "") or "").strip(): row
        for row in (benchmark_payload.get("cases") or [])
        if isinstance(row, dict) and str(row.get("case_id", "") or "").strip()
    }
    member_rows = [row for row in (code_check_report.get("member_check_rows") or []) if isinstance(row, dict)]
    case_row_groups: dict[str, list[dict[str, Any]]] = {}
    for row in member_rows:
        case_id = str(row.get("case_id", "") or row.get("member_id", "")).strip()
        if not case_id:
            continue
        case_row_groups.setdefault(case_id, []).append(dict(row))
    review_profiles: dict[str, dict[str, str]] = {}
    for row in member_rows:
        case_id = str(row.get("case_id", "") or row.get("member_id", "")).strip()
        if not case_id:
            continue
        review_profiles.setdefault(
            case_id,
            {
                "review_member_id": str(row.get("member_id", "") or case_id).strip(),
                "review_case_id": case_id,
                "source_member_type": str(row.get("member_type", "") or "unknown").strip() or "unknown",
                "source_hazard_type": str(row.get("hazard_type", "") or "unknown").strip() or "unknown",
                "source_topology_type": str(row.get("topology_type", "") or "unknown").strip() or "unknown",
            },
        )
    mappings: list[dict[str, Any]] = []
    selector_counts: Counter[str] = Counter()
    geometry_counts: Counter[str] = Counter()
    for case_id, profile in sorted(review_profiles.items()):
        benchmark_row = benchmark_cases.get(case_id, {}) if isinstance(benchmark_cases.get(case_id), dict) else {}
        source_family = str(benchmark_row.get("source_family", "") or "commercial_export").strip() or "commercial_export"
        source_topology_type = str(benchmark_row.get("topology_type", "") or profile.get("source_topology_type", "unknown")).strip() or "unknown"
        source_hazard_type = str(benchmark_row.get("hazard_type", "") or profile.get("source_hazard_type", "unknown")).strip() or "unknown"
        source_member_type = str(profile.get("source_member_type", "unknown") or "unknown").strip() or "unknown"
        source_element_mix = str(benchmark_row.get("element_mix", "") or "unknown").strip() or "unknown"
        selector_kind = _selector_kind(source_member_type, source_topology_type, source_element_mix)
        candidate = _pick_candidate(catalog, selector_kind)
        if candidate is None:
            continue
        selector_counts[selector_kind] += 1
        geometry_counts[str(candidate.get("geometry_kind", "unknown"))] += 1
        review_member_id = str(profile.get("review_member_id", case_id) or case_id)
        review_keys = _unique_strings([review_member_id, case_id])
        provenance_payload = _row_provenance_payload(
            review_member_id=review_member_id,
            review_case_id=case_id,
            baseline_focus_member_id=str(candidate.get("element_id", "") or ""),
            case_rows=case_row_groups.get(case_id, []),
        )
        member_groups, section_groups = _selector_full_crosswalk_groups(selector_kind)
        full_member_handles = _inventory_union(
            full_crosswalk_inventory.get("member_handles_by_group", {}),
            member_groups,
        )
        full_section_ids = _inventory_union(
            full_crosswalk_inventory.get("section_ids_by_group", {}),
            section_groups,
        )
        full_load_names = list(provenance_payload.get("row_provenance_combination_names") or [])
        note = (
            "heuristic semantic-case surrogate derived from commercial_export case profile; "
            f"member_type={source_member_type}, topology={source_topology_type}, hazard={source_hazard_type}, mix={source_element_mix}. "
            f"Canonical MIDAS geometry is beam-family-only, so this bridge points to representative {candidate.get('geometry_kind', 'geometry')} "
            f"element {candidate.get('element_id', '')} (zmid={float(candidate.get('zmid', 0.0)):.3f}, length={float(candidate.get('length', 0.0)):.3f}, "
            f"centroid_distance={float(candidate.get('centroid_distance', 0.0)):.3f}) instead of an exact reviewer-verified member id."
        )
        mappings.append(
            {
                "review_member_id": review_member_id,
                "review_case_id": case_id,
                "review_keys": review_keys,
                "baseline_focus_member_id": str(candidate.get("element_id", "") or ""),
                "match_strategy": f"heuristic_case_profile_{selector_kind}",
                "match_confidence": "heuristic_case_profile",
                "selector_kind": selector_kind,
                "source_family": source_family,
                "source_topology_type": source_topology_type,
                "source_member_type": source_member_type,
                "source_hazard_type": source_hazard_type,
                "source_element_mix": source_element_mix,
                "surrogate_geometry_kind": str(candidate.get("geometry_kind", "") or "unknown"),
                "surrogate_aggregate_member_id": str(candidate.get("aggregate_member_id", "") or ""),
                "full_crosswalk_target_member_handle": (
                    str(candidate.get("aggregate_member_id", "") or "")
                    or str(candidate.get("element_id", "") or "")
                ),
                "full_crosswalk_target_section_id": str(candidate.get("section_id", "") or ""),
                "full_crosswalk_member_groups": member_groups,
                "full_crosswalk_member_handles": full_member_handles,
                "full_crosswalk_member_handle_count": len(full_member_handles),
                "full_crosswalk_section_groups": section_groups,
                "full_crosswalk_section_ids": full_section_ids,
                "full_crosswalk_section_id_count": len(full_section_ids),
                "full_crosswalk_load_combination_names": full_load_names,
                "full_crosswalk_load_combination_count": len(full_load_names),
                "note": note,
                **provenance_payload,
            }
        )
    full_crosswalk_summary = _registry_full_crosswalk_summary(
        mappings=mappings,
        model_payload=model_payload,
        code_check_report=code_check_report,
    )
    global_member_handles = list(full_crosswalk_summary.get("full_member_crosswalk_expected_handles") or [])
    global_section_ids = list(full_crosswalk_summary.get("full_section_crosswalk_expected_ids") or [])
    global_load_names = list(full_crosswalk_summary.get("full_load_crosswalk_expected_names") or [])
    for row in mappings:
        row["full_crosswalk_global_member_handles"] = global_member_handles
        row["full_crosswalk_global_member_handle_count"] = len(global_member_handles)
        row["full_crosswalk_global_section_ids"] = global_section_ids
        row["full_crosswalk_global_section_id_count"] = len(global_section_ids)
        row["full_crosswalk_global_load_combination_names"] = global_load_names
        row["full_crosswalk_global_load_combination_count"] = len(global_load_names)
        row["full_crosswalk_inventory_scope"] = "selector_group"
        row["full_crosswalk_global_inventory_scope"] = "model_and_codecheck_expected"
        row["full_crosswalk_inventory_summary_label"] = (
            f"groups=members:{len(row.get('full_crosswalk_member_groups') or [])}/"
            f"sections:{len(row.get('full_crosswalk_section_groups') or [])} | "
            f"selector=members:{row.get('full_crosswalk_member_handle_count', 0)}/"
            f"sections:{row.get('full_crosswalk_section_id_count', 0)}/"
            f"loads:{row.get('full_crosswalk_load_combination_count', 0)} | "
            f"global=members:{len(global_member_handles)}/sections:{len(global_section_ids)}/loads:{len(global_load_names)}"
        )
    return {
        "contract_version": "0.3.0",
        "registry_kind": "kds_geometry_bridge_registry",
        "source": "heuristic_semantic_case_profile_registry",
        "limitations": [
            "This registry is heuristic and productized for guided navigation. It does not replace reviewer-verified exact member mapping.",
            "Canonical MIDAS 33 geometry is beam-family-only, so wall/brace/column semantic ids are bridged to representative surrogate beam/vertical geometry.",
        ],
        "summary": {
            "mapping_count": len(mappings),
            "selector_counts": {str(key): int(value) for key, value in sorted(selector_counts.items())},
            "surrogate_geometry_counts": {str(key): int(value) for key, value in sorted(geometry_counts.items())},
            "model_centroid": centroid,
            "full_member_crosswalk_handles_by_group": dict(full_crosswalk_inventory.get("member_handles_by_group", {})),
            "full_member_crosswalk_group_count": len(full_crosswalk_inventory.get("member_handles_by_group", {})),
            "full_section_crosswalk_ids_by_group": dict(full_crosswalk_inventory.get("section_ids_by_group", {})),
            "full_section_crosswalk_group_count": len(full_crosswalk_inventory.get("section_ids_by_group", {})),
            **full_crosswalk_summary,
        },
        "mappings": mappings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a heuristic KDS review-id -> MIDAS geometry bridge registry.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--benchmark-cases", type=Path, default=DEFAULT_BENCHMARK_CASES)
    parser.add_argument("--code-check-report", type=Path, default=DEFAULT_CODECHECK_REPORT)
    parser.add_argument(
        "--explicit-registry",
        dest="registry_paths",
        action="append",
        type=Path,
        default=None,
        help="Optional explicit registry JSON. Can be passed multiple times and is merged over the generated heuristic registry by review key.",
    )
    parser.add_argument(
        "--exact-registry",
        dest="registry_paths",
        action="append",
        type=Path,
        default=None,
        help="Optional reviewer-verified exact registry JSON. This is an alias for --explicit-registry.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    registry = build_registry(
        model_payload=_load_json(args.model),
        benchmark_payload=_load_json(args.benchmark_cases),
        code_check_report=_load_json(args.code_check_report),
    )
    registry_paths = [path for path in (args.registry_paths or []) if isinstance(path, Path) and path.exists()]
    if registry_paths:
        registry = merge_registry_payloads(registry, *(_load_json(path) for path in registry_paths))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = registry.get("summary") if isinstance(registry.get("summary"), dict) else {}
    print(
        f"{args.out}: mappings={int(summary.get('mapping_count', 0) or 0)} "
        f"exact={int(summary.get('exact_mapping_count', 0) or 0)} "
        f"heuristic={int(summary.get('heuristic_mapping_count', 0) or 0)} "
        f"selectors={summary.get('selector_counts', {})} "
        f"geometry={summary.get('surrogate_geometry_counts', {})} "
        f"registry_sources={summary.get('source_counts', {})} "
        f"full_crosswalk={summary.get('full_crosswalk_summary_label', 'n/a')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
