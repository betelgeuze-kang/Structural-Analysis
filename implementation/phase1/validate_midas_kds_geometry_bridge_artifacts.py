from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_TARGETS = (
    Path("implementation/phase1/open_data/midas/midas_generator_33.json"),
    Path("implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json"),
    Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"),
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return payload


def _strategy_label(strategy_counts: dict[str, Any]) -> str:
    if not strategy_counts:
        return "none"
    ordered = sorted(
        ((str(key), int(value or 0)) for key, value in strategy_counts.items()),
        key=lambda item: (-item[1], item[0]),
    )
    return ", ".join(f"{key}:{value}" for key, value in ordered[:4])


def _normalized_section_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(int(text))
    except (TypeError, ValueError):
        return text


def _normalized_scalar(value: Any) -> str:
    text = str(value or "").strip()
    return text.upper() if text else ""


def _node_coordinate_index(nodes: list[dict[str, Any]]) -> dict[str, tuple[float, float, float]]:
    out: dict[str, tuple[float, float, float]] = {}
    for row in nodes:
        if not isinstance(row, dict):
            continue
        node_id = str(row.get("id", "") or "").strip()
        if not node_id:
            continue
        out[node_id] = (
            float(row.get("x", 0.0) or 0.0),
            float(row.get("y", 0.0) or 0.0),
            float(row.get("z", 0.0) or 0.0),
        )
    return out


def _model_member_handle_inventory(model: dict[str, Any]) -> tuple[set[str], str]:
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


def _model_section_inventory(model: dict[str, Any]) -> set[str]:
    return {
        _normalized_section_id(row.get("section_id"))
        for row in (model.get("elements") or [])
        if isinstance(row, dict) and _normalized_section_id(row.get("section_id"))
    }


def _normalized_name_list(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _sorted_normalized_name_list(values: list[Any]) -> list[str]:
    return sorted(_normalized_name_list(values))


def _summary_crosswalk_set(summary: dict[str, Any], key: str) -> set[str]:
    values = summary.get(key)
    if not isinstance(values, list):
        return set()
    return {str(item).strip() for item in values if str(item).strip()}


def _summary_crosswalk_complete(
    summary: dict[str, Any],
    *,
    values_key: str,
    count_key: str,
    expected_key: str,
    status_key: str,
) -> tuple[set[str], set[str]]:
    coverage = _summary_crosswalk_set(summary, values_key)
    count = int(summary.get(count_key, len(coverage)) or len(coverage))
    expected = int(summary.get(expected_key, 0) or 0)
    status = str(summary.get(status_key, "") or "").strip().upper()
    inventory = set(coverage)
    if expected > 0 and (len(coverage) < expected or (status != "PASS" and count < expected)):
        inventory.clear()
    return coverage, inventory


def _summary_section_crosswalk_complete(summary: dict[str, Any]) -> tuple[set[str], set[str]]:
    values = summary.get("full_section_crosswalk_ids")
    coverage = {
        _normalized_section_id(item)
        for item in values
        if _normalized_section_id(item)
    } if isinstance(values, list) else set()
    count = int(summary.get("full_section_crosswalk_count", len(coverage)) or len(coverage))
    expected = int(summary.get("full_section_crosswalk_expected", 0) or 0)
    status = str(summary.get("full_section_crosswalk_status", "") or "").strip().upper()
    inventory = set(coverage)
    if expected > 0 and (len(coverage) < expected or (status != "PASS" and count < expected)):
        inventory.clear()
    return coverage, inventory


def _summary_load_crosswalk_complete(summary: dict[str, Any]) -> tuple[set[str], set[str]]:
    return _summary_crosswalk_complete(
        summary,
        values_key="full_load_crosswalk_names",
        count_key="full_load_crosswalk_count",
        expected_key="full_load_crosswalk_expected",
        status_key="full_load_crosswalk_status",
    )


def _member_crosswalk_kind(summary: dict[str, Any], default: str = "") -> str:
    return str(summary.get("full_member_crosswalk_handle_kind", "") or default).strip()


def _candidate_registry_paths(path: Path) -> tuple[Path, ...]:
    return (
        path.parent / "kds_geometry_bridge_registry.heuristic.json",
        path.parent / "kds_geometry_bridge_registry.exact.json",
    )


def _registry_match_score(path: Path, payload: dict[str, Any], registry_source_label: str) -> int:
    source_label = str(payload.get("source", "") or "").strip()
    if not source_label:
        return -1
    score = 0
    normalized_label = registry_source_label.strip().lower()
    normalized_source = source_label.lower()
    if registry_source_label and source_label == registry_source_label:
        score += 10
    if normalized_label and normalized_label == normalized_source:
        score += 8
    if normalized_label and normalized_label in normalized_source:
        score += 4
    if normalized_label and normalized_source in normalized_label:
        score += 2
    if "merged" in normalized_label and "heuristic" in path.name.lower():
        score += 2
    if "exact" in normalized_label and "exact" in path.name.lower():
        score += 2
    return score


def _matching_registry_summary(path: Path, registry_source_label: str) -> tuple[dict[str, Any], str]:
    best_payload: dict[str, Any] = {}
    best_source = ""
    best_score = -1
    for candidate in _candidate_registry_paths(path):
        if not candidate.exists():
            continue
        payload = _load_json(candidate)
        score = _registry_match_score(candidate, payload, registry_source_label)
        if score < 0:
            continue
        if score > best_score:
            best_payload = payload
            best_source = str(candidate)
            best_score = score
    return best_payload, best_source


def _row_member_crosswalk_set(row: dict[str, Any]) -> set[str]:
    values = row.get("full_crosswalk_member_handles")
    if isinstance(values, list):
        return {str(item).strip() for item in values if str(item).strip()}
    handle = str(
        row.get("full_crosswalk_target_member_handle", "")
        or row.get("surrogate_aggregate_member_id", "")
        or row.get("baseline_focus_member_id", "")
        or ""
    ).strip()
    return {handle} if handle else set()


def _row_section_crosswalk_set(row: dict[str, Any]) -> set[str]:
    values = row.get("full_crosswalk_section_ids")
    if isinstance(values, list):
        return {_normalized_section_id(item) for item in values if _normalized_section_id(item)}
    section_id = _normalized_section_id(
        row.get("full_crosswalk_target_section_id")
        or ((row.get("review_geometry_snapshot") or {}).get("section_id") if isinstance(row.get("review_geometry_snapshot"), dict) else "")
    )
    return {section_id} if section_id else set()


def _row_load_crosswalk_set(row: dict[str, Any]) -> set[str]:
    values = row.get("full_crosswalk_load_combination_names")
    if isinstance(values, list):
        names = {str(item).strip() for item in values if str(item).strip()}
        if names:
            return names
    values = row.get("row_provenance_combination_names")
    if isinstance(values, list):
        return {str(item).strip() for item in values if str(item).strip()}
    return set()


def _unique_row_values(rows: list[dict[str, Any]], key: str) -> list[str]:
    return _normalized_name_list([row.get(key) for row in rows if isinstance(row, dict)])


def _crosswalk_status(count: int, expected: int, *, require_complete: bool = False, complete: bool = True) -> str:
    if require_complete and expected > 0 and not complete:
        return "CHECK"
    return "PASS" if expected == 0 or count >= expected else "CHECK"


def _aggregate_status(pass_value: bool, summaries: list[dict[str, Any]]) -> str:
    return "PASS" if bool(pass_value and summaries) else "CHECK"


def _aggregate_metric(
    *,
    summaries: list[dict[str, Any]],
    count_key: str,
    expected_key: str,
    pass_value: bool,
) -> dict[str, Any]:
    count_total = int(sum(int(row.get(count_key, 0) or 0) for row in summaries))
    expected_total = int(sum(int(row.get(expected_key, 0) or 0) for row in summaries))
    metric_pass = bool(pass_value and summaries)
    return {
        "count_total": count_total,
        "expected_total": expected_total,
        "status": _aggregate_status(metric_pass, summaries),
        "pass": metric_pass,
    }


def _set_map(value: Any) -> dict[str, set[str]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, set[str]] = {}
    for key, items in value.items():
        if not isinstance(items, list):
            continue
        normalized_items = {str(item).strip() for item in items if str(item).strip()}
        if normalized_items:
            out[str(key).strip()] = normalized_items
    return out


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _structured_member_aggregate_metric(summaries: list[dict[str, Any]]) -> dict[str, Any] | None:
    positive_rows = [
        row for row in summaries if int(row.get("full_member_crosswalk_expected", 0) or 0) > 0
    ]
    if not positive_rows:
        return {
            "count_total": 0,
            "expected_total": 0,
            "status": "PASS",
            "pass": True,
            "basis": "structured_inventory_union",
            "handle_kind": "",
        }
    candidate_kinds: set[str] = set()
    inventories_by_row: list[dict[str, set[str]]] = []
    coverages_by_row: list[dict[str, set[str]]] = []
    for row in positive_rows:
        inventory_by_kind = _set_map(row.get("full_member_crosswalk_structured_inventory_by_kind"))
        coverage_by_kind = _set_map(row.get("full_member_crosswalk_structured_coverage_by_kind"))
        inventories_by_row.append(inventory_by_kind)
        coverages_by_row.append(coverage_by_kind)
        candidate_kinds.update(kind for kind, values in inventory_by_kind.items() if values)
    best_metric: dict[str, Any] | None = None
    for kind in sorted(candidate_kinds):
        if any(not inventory_by_kind.get(kind) for inventory_by_kind in inventories_by_row):
            continue
        coverage_union: set[str] = set()
        inventory_union: set[str] = set()
        for coverage_by_kind, inventory_by_kind in zip(coverages_by_row, inventories_by_row):
            coverage_union.update(coverage_by_kind.get(kind, set()))
            inventory_union.update(inventory_by_kind.get(kind, set()))
        expected_total = len(inventory_union)
        count_total = len(coverage_union & inventory_union)
        metric = {
            "count_total": count_total,
            "expected_total": expected_total,
            "status": "PASS" if expected_total == 0 or count_total >= expected_total else "CHECK",
            "pass": bool(expected_total == 0 or count_total >= expected_total),
            "basis": "structured_inventory_union",
            "handle_kind": kind,
        }
        if best_metric is None:
            best_metric = metric
            continue
        if (
            int(metric["pass"]) > int(best_metric["pass"])
            or (
                metric["pass"] == best_metric["pass"]
                and int(metric["expected_total"]) > int(best_metric["expected_total"])
            )
            or (
                metric["pass"] == best_metric["pass"]
                and int(metric["expected_total"]) == int(best_metric["expected_total"])
                and int(metric["count_total"]) > int(best_metric["count_total"])
            )
        ):
            best_metric = metric
    return best_metric


def _structured_set_aggregate_metric(
    summaries: list[dict[str, Any]],
    *,
    coverage_key: str,
    inventory_key: str,
    expected_key: str,
) -> dict[str, Any] | None:
    positive_rows = [row for row in summaries if int(row.get(expected_key, 0) or 0) > 0]
    if not positive_rows:
        return {
            "count_total": 0,
            "expected_total": 0,
            "status": "PASS",
            "pass": True,
            "basis": "structured_inventory_union",
        }
    if any(not _string_set(row.get(inventory_key)) for row in positive_rows):
        return None
    coverage_union: set[str] = set()
    inventory_union: set[str] = set()
    for row in positive_rows:
        coverage_union.update(_string_set(row.get(coverage_key)))
        inventory_union.update(_string_set(row.get(inventory_key)))
    expected_total = len(inventory_union)
    count_total = len(coverage_union & inventory_union)
    return {
        "count_total": count_total,
        "expected_total": expected_total,
        "status": "PASS" if expected_total == 0 or count_total >= expected_total else "CHECK",
        "pass": bool(expected_total == 0 or count_total >= expected_total),
        "basis": "structured_inventory_union",
    }


def _exact_bridge_checks(
    *,
    has_bridge: bool,
    review_id_count: int,
    mapped_review_id_count: int,
    exact_mapped_review_id_count: int,
    heuristic_mapped_review_id_count: int,
    review_row_count: int,
    mapped_row_provenance_count: int,
    exact_mapped_row_provenance_count: int,
    heuristic_mapped_row_provenance_count: int,
) -> dict[str, bool]:
    review_ids_present = bool(review_id_count >= 1)
    review_rows_present = bool(review_row_count >= 1)
    review_ids_fully_mapped = bool(review_ids_present and mapped_review_id_count >= review_id_count)
    review_ids_exact_only = bool(
        review_ids_fully_mapped
        and exact_mapped_review_id_count >= review_id_count
        and heuristic_mapped_review_id_count == 0
    )
    row_provenance_fully_mapped = bool(
        review_rows_present and mapped_row_provenance_count >= review_row_count
    )
    row_provenance_exact_only = bool(
        row_provenance_fully_mapped
        and exact_mapped_row_provenance_count >= review_row_count
        and heuristic_mapped_row_provenance_count == 0
    )
    exact_geometry_bridge_pass = bool(
        has_bridge
        and review_ids_present
        and review_rows_present
        and review_ids_exact_only
        and row_provenance_exact_only
    )
    return {
        "review_ids_present": review_ids_present,
        "review_rows_present": review_rows_present,
        "review_ids_fully_mapped": review_ids_fully_mapped,
        "review_ids_exact_only": review_ids_exact_only,
        "row_provenance_fully_mapped": row_provenance_fully_mapped,
        "row_provenance_exact_only": row_provenance_exact_only,
        "exact_geometry_bridge_pass": exact_geometry_bridge_pass,
    }


def summarize_artifact(path: Path, *, min_mapped_review_ids: int = 0) -> dict[str, Any]:
    payload = _load_json(path)
    model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
    elements = model.get("elements") if isinstance(model.get("elements"), list) else []
    nodes = model.get("nodes") if isinstance(model.get("nodes"), list) else []
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    bridge = metadata.get("kds_geometry_bridge") if isinstance(metadata.get("kds_geometry_bridge"), dict) else {}
    summary = bridge.get("summary") if isinstance(bridge.get("summary"), dict) else {}
    bridge_rows = bridge.get("bridge_rows") if isinstance(bridge.get("bridge_rows"), list) else []
    element_index = {
        str(row.get("id", "") or "").strip(): row
        for row in elements
        if isinstance(row, dict) and str(row.get("id", "") or "").strip()
    }
    element_section_index = {
        str(row.get("id", "") or "").strip(): _normalized_section_id(row.get("section_id"))
        for row in elements
        if isinstance(row, dict) and str(row.get("id", "") or "").strip()
    }
    node_index = _node_coordinate_index(nodes)
    expected_member_handles, full_member_crosswalk_handle_kind = _model_member_handle_inventory(model)
    expected_section_ids = _model_section_inventory(model)
    strategy_counts = summary.get("strategy_counts") if isinstance(summary.get("strategy_counts"), dict) else {}
    review_id_count = int(summary.get("review_id_count", 0) or 0)
    mapped_review_id_count = int(summary.get("mapped_review_id_count", 0) or 0)
    exact_mapped_review_id_count = int(summary.get("exact_mapped_review_id_count", 0) or 0)
    heuristic_mapped_review_id_count = int(summary.get("heuristic_mapped_review_id_count", 0) or 0)
    review_row_count = int(summary.get("review_row_count", len(bridge_rows)) or 0)
    mapped_row_provenance_count = int(summary.get("mapped_row_provenance_count", 0) or 0)
    exact_mapped_row_provenance_count = int(summary.get("exact_mapped_row_provenance_count", 0) or 0)
    heuristic_mapped_row_provenance_count = int(summary.get("heuristic_mapped_row_provenance_count", 0) or 0)
    confidence_counts = summary.get("confidence_counts") if isinstance(summary.get("confidence_counts"), dict) else {}
    registry_source_label = str(bridge.get("registry_source_label", "") or "none")
    registry_contract_version = str(bridge.get("registry_contract_version", "") or "0.1.0")
    registry_payload, registry_path = _matching_registry_summary(path, registry_source_label)
    registry_summary = registry_payload.get("summary") if isinstance(registry_payload.get("summary"), dict) else {}
    external_registry_row_count = int(summary.get("external_registry_row_count", 0) or 0)
    external_registry_usable_row_count = int(summary.get("external_registry_usable_row_count", 0) or 0)
    external_registry_exact_row_count = int(summary.get("external_registry_exact_row_count", 0) or 0)
    external_registry_heuristic_row_count = int(summary.get("external_registry_heuristic_row_count", 0) or 0)
    external_registry_source_counts = summary.get("external_registry_source_counts") if isinstance(summary.get("external_registry_source_counts"), dict) else {}
    exact_review_geometry_snapshot_count = int(
        sum(
            1
            for row in bridge_rows
            if isinstance(row, dict)
            and str(row.get("baseline_focus_member_id", "") or "").strip()
            and not str(row.get("match_confidence", "") or "").strip().lower().startswith("heuristic")
            and isinstance(row.get("review_geometry_snapshot"), dict)
            and str((row.get("review_geometry_snapshot") or {}).get("section_id", "") or "").strip()
            and len([item for item in ((row.get("review_geometry_snapshot") or {}).get("node_ids") or []) if str(item).strip()]) >= 2
        )
    )
    exact_review_geometry_snapshot_expected = max(exact_mapped_review_id_count, 0)
    exact_review_geometry_snapshot_status = "PASS" if (
        exact_review_geometry_snapshot_expected == 0
        or exact_review_geometry_snapshot_count >= exact_review_geometry_snapshot_expected
    ) else "CHECK"
    exact_review_geometry_section_parity_expected = int(
        sum(
            1
            for row in bridge_rows
            if isinstance(row, dict)
            and str(row.get("baseline_focus_member_id", "") or "").strip()
            and not str(row.get("match_confidence", "") or "").strip().lower().startswith("heuristic")
            and isinstance(row.get("review_geometry_snapshot"), dict)
            and _normalized_section_id((row.get("review_geometry_snapshot") or {}).get("section_id"))
        )
    )
    exact_review_geometry_section_parity_count = int(
        sum(
            1
            for row in bridge_rows
            if isinstance(row, dict)
            and str(row.get("baseline_focus_member_id", "") or "").strip()
            and not str(row.get("match_confidence", "") or "").strip().lower().startswith("heuristic")
            and isinstance(row.get("review_geometry_snapshot"), dict)
            and _normalized_section_id((row.get("review_geometry_snapshot") or {}).get("section_id"))
            and _normalized_section_id((row.get("review_geometry_snapshot") or {}).get("section_id"))
            == element_section_index.get(str(row.get("baseline_focus_member_id", "") or "").strip(), "")
        )
    )
    exact_review_geometry_section_parity_status = "PASS" if (
        exact_review_geometry_section_parity_expected == 0
        or exact_review_geometry_section_parity_count >= exact_review_geometry_section_parity_expected
    ) else "CHECK"
    exact_review_load_crosswalk_expected = 0
    exact_review_load_crosswalk_count = 0
    exact_review_semantic_crosswalk_expected = 0
    exact_review_semantic_crosswalk_count = 0
    full_member_crosswalk_handles = _summary_crosswalk_set(summary, "full_member_crosswalk_handles")
    full_section_crosswalk_ids = _summary_crosswalk_set(summary, "full_section_crosswalk_ids")
    full_load_crosswalk_declared_names = _summary_crosswalk_set(summary, "full_load_crosswalk_names")
    full_load_crosswalk_actual_names: set[str] = set()
    structured_member_coverage_by_kind: dict[str, set[str]] = {}
    structured_member_inventory_by_kind: dict[str, set[str]] = {}
    structured_section_coverage_ids = set(full_section_crosswalk_ids)
    structured_section_inventory_ids: set[str] = set()
    structured_load_coverage_names = set(full_load_crosswalk_declared_names)
    structured_load_inventory_names: set[str] = set()
    exact_geometry_diff_expected = 0
    exact_geometry_diff_count = 0
    exact_geometry_diff_max_abs = 0.0
    for row in bridge_rows:
        if not isinstance(row, dict):
            continue
        full_member_crosswalk_handles.update(_row_member_crosswalk_set(row))
        full_section_crosswalk_ids.update(_row_section_crosswalk_set(row))
        full_load_crosswalk_declared_names.update(_row_load_crosswalk_set(row))
        member_id = str(row.get("baseline_focus_member_id", "") or "").strip()
        if not member_id or str(row.get("match_confidence", "") or "").strip().lower().startswith("heuristic"):
            continue
        snapshot = row.get("review_geometry_snapshot")
        element = element_index.get(member_id)
        provenance_rows = row.get("row_provenance_rows") if isinstance(row.get("row_provenance_rows"), list) else []
        normalized_provenance_rows = [item for item in provenance_rows if isinstance(item, dict)]
        if normalized_provenance_rows:
            combination_names = _sorted_normalized_name_list(_unique_row_values(normalized_provenance_rows, "combination"))
            full_load_crosswalk_actual_names.update(combination_names)
            clause_names = _sorted_normalized_name_list(_unique_row_values(normalized_provenance_rows, "clause"))
            component_names = _sorted_normalized_name_list(_unique_row_values(normalized_provenance_rows, "component"))
            rule_family_names = _sorted_normalized_name_list(_unique_row_values(normalized_provenance_rows, "rule_family"))
            hazard_names = _sorted_normalized_name_list(_unique_row_values(normalized_provenance_rows, "hazard_type"))
            topology_names = _sorted_normalized_name_list(_unique_row_values(normalized_provenance_rows, "topology_type"))
            member_type_names = _sorted_normalized_name_list(_unique_row_values(normalized_provenance_rows, "member_type"))
            exact_review_load_crosswalk_expected += 1
            combination_declared = _sorted_normalized_name_list(row.get("row_provenance_combination_names") or [])
            combination_count_declared = int(row.get("row_provenance_combination_count", 0) or 0)
            if (
                combination_names == combination_declared
                and combination_count_declared == len(combination_names)
            ):
                exact_review_load_crosswalk_count += 1
            exact_review_semantic_crosswalk_expected += 1
            member_inventory_names = _sorted_normalized_name_list(row.get("member_inventory_member_type_names") or [])
            semantic_crosswalk_pass = (
                int(row.get("row_provenance_row_count", 0) or 0) == len(normalized_provenance_rows)
                and int(row.get("row_provenance_clause_count", 0) or 0) == len(clause_names)
                and int(row.get("row_provenance_component_count", 0) or 0) == len(component_names)
                and int(row.get("row_provenance_rule_family_count", 0) or 0) == len(rule_family_names)
                and int(row.get("row_provenance_hazard_count", 0) or 0) == len(hazard_names)
                and int(row.get("row_provenance_topology_count", 0) or 0) == len(topology_names)
                and int(row.get("member_inventory_count", 0) or 0) == len(member_type_names)
                and _sorted_normalized_name_list(row.get("row_provenance_clause_names") or []) == clause_names
                and _sorted_normalized_name_list(row.get("row_provenance_component_names") or []) == component_names
                and _sorted_normalized_name_list(row.get("row_provenance_rule_family_names") or []) == rule_family_names
                and _sorted_normalized_name_list(row.get("row_provenance_hazard_names") or []) == hazard_names
                and _sorted_normalized_name_list(row.get("row_provenance_topology_names") or []) == topology_names
                and member_inventory_names == member_type_names
                and str(row.get("source_member_type", "") or "").strip() in member_type_names
                and str(row.get("source_hazard_type", "") or "").strip() in hazard_names
                and str(row.get("source_topology_type", "") or "").strip() in topology_names
            )
            if semantic_crosswalk_pass:
                exact_review_semantic_crosswalk_count += 1
        if not isinstance(snapshot, dict) or not isinstance(element, dict):
            continue
        snapshot_node_ids = [str(item).strip() for item in (snapshot.get("node_ids") or []) if str(item).strip()]
        element_node_ids = [str(item).strip() for item in (element.get("node_ids") or []) if str(item).strip()]
        if not snapshot_node_ids or not element_node_ids:
            continue
        exact_geometry_diff_expected += 1
        identity_match = (
            _normalized_scalar(snapshot.get("element_type")) == _normalized_scalar(element.get("type"))
            and _normalized_scalar(snapshot.get("family")) == _normalized_scalar(element.get("family"))
            and _normalized_section_id(snapshot.get("section_id")) == _normalized_section_id(element.get("section_id"))
            and _normalized_scalar(snapshot.get("material_id")) == _normalized_scalar(element.get("material_id"))
            and snapshot_node_ids == element_node_ids
        )
        snapshot_coords = snapshot.get("node_coordinates") if isinstance(snapshot.get("node_coordinates"), list) else []
        coordinate_match = len(snapshot_coords) == len(snapshot_node_ids)
        row_max_abs = 0.0
        for coord_row in snapshot_coords:
            if not isinstance(coord_row, dict):
                coordinate_match = False
                continue
            node_id = str(coord_row.get("id", "") or "").strip()
            expected_xyz = node_index.get(node_id)
            if expected_xyz is None:
                coordinate_match = False
                continue
            deltas = (
                abs(float(coord_row.get("x", 0.0) or 0.0) - expected_xyz[0]),
                abs(float(coord_row.get("y", 0.0) or 0.0) - expected_xyz[1]),
                abs(float(coord_row.get("z", 0.0) or 0.0) - expected_xyz[2]),
            )
            row_max_abs = max(row_max_abs, *deltas)
            if any(delta > 1.0e-9 for delta in deltas):
                coordinate_match = False
        exact_geometry_diff_max_abs = max(exact_geometry_diff_max_abs, row_max_abs)
        if identity_match and coordinate_match:
            exact_geometry_diff_count += 1
    exact_geometry_diff_status = "PASS" if (
        exact_geometry_diff_expected == 0 or exact_geometry_diff_count >= exact_geometry_diff_expected
    ) else "CHECK"
    exact_review_load_crosswalk_status = "PASS" if (
        exact_review_load_crosswalk_expected == 0
        or exact_review_load_crosswalk_count >= exact_review_load_crosswalk_expected
    ) else "CHECK"
    exact_review_semantic_crosswalk_status = "PASS" if (
        exact_review_semantic_crosswalk_expected == 0
        or exact_review_semantic_crosswalk_count >= exact_review_semantic_crosswalk_expected
    ) else "CHECK"
    full_member_crosswalk_expected = int(
        summary.get("full_member_crosswalk_expected", len(expected_member_handles)) or len(expected_member_handles)
    )
    full_section_crosswalk_expected = int(
        summary.get("full_section_crosswalk_expected", len(expected_section_ids)) or len(expected_section_ids)
    )
    full_load_crosswalk_expected = int(
        summary.get("full_load_crosswalk_expected", len(full_load_crosswalk_actual_names)) or len(full_load_crosswalk_actual_names)
    )
    full_member_crosswalk_count = len(full_member_crosswalk_handles & expected_member_handles)
    full_section_crosswalk_count = len(full_section_crosswalk_ids & expected_section_ids)
    full_load_crosswalk_count = len(full_load_crosswalk_declared_names & full_load_crosswalk_actual_names)
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
        require_complete=True,
        complete=bool(review_row_count == 0 or mapped_row_provenance_count >= review_row_count),
    )
    if full_member_crosswalk_handles:
        structured_member_coverage_by_kind.setdefault(full_member_crosswalk_handle_kind, set()).update(
            full_member_crosswalk_handles
        )
    artifact_member_summary, artifact_member_inventory = _summary_crosswalk_complete(
        summary,
        values_key="full_member_crosswalk_handles",
        count_key="full_member_crosswalk_count",
        expected_key="full_member_crosswalk_expected",
        status_key="full_member_crosswalk_status",
    )
    if artifact_member_summary:
        structured_member_coverage_by_kind.setdefault(full_member_crosswalk_handle_kind, set()).update(
            artifact_member_summary
        )
    if artifact_member_inventory:
        structured_member_inventory_by_kind.setdefault(full_member_crosswalk_handle_kind, set()).update(
            artifact_member_inventory
        )
    artifact_section_summary, artifact_section_inventory = _summary_section_crosswalk_complete(summary)
    structured_section_coverage_ids.update(artifact_section_summary)
    structured_section_inventory_ids.update(artifact_section_inventory)
    artifact_load_summary, artifact_load_inventory = _summary_load_crosswalk_complete(summary)
    structured_load_coverage_names.update(artifact_load_summary)
    structured_load_inventory_names.update(artifact_load_inventory)
    registry_member_kind = _member_crosswalk_kind(registry_summary)
    registry_member_summary, registry_member_inventory = _summary_crosswalk_complete(
        registry_summary,
        values_key="full_member_crosswalk_handles",
        count_key="full_member_crosswalk_count",
        expected_key="full_member_crosswalk_expected",
        status_key="full_member_crosswalk_status",
    )
    if registry_member_summary and registry_member_kind:
        structured_member_coverage_by_kind.setdefault(registry_member_kind, set()).update(registry_member_summary)
    if registry_member_inventory and registry_member_kind:
        structured_member_inventory_by_kind.setdefault(registry_member_kind, set()).update(registry_member_inventory)
    registry_section_summary, registry_section_inventory = _summary_section_crosswalk_complete(registry_summary)
    structured_section_coverage_ids.update(registry_section_summary)
    structured_section_inventory_ids.update(registry_section_inventory)
    registry_load_summary, registry_load_inventory = _summary_load_crosswalk_complete(registry_summary)
    structured_load_coverage_names.update(registry_load_summary)
    structured_load_inventory_names.update(registry_load_inventory)
    source_label = str(bridge.get("provenance", "") or bridge.get("bridge_kind", "") or "n/a")
    mapping_gap_active = bool(review_id_count > 0 and mapped_review_id_count < review_id_count)
    pass_threshold = bool(bridge) and mapped_review_id_count >= max(int(min_mapped_review_ids), 0)
    exact_checks = _exact_bridge_checks(
        has_bridge=bool(bridge),
        review_id_count=review_id_count,
        mapped_review_id_count=mapped_review_id_count,
        exact_mapped_review_id_count=exact_mapped_review_id_count,
        heuristic_mapped_review_id_count=heuristic_mapped_review_id_count,
        review_row_count=review_row_count,
        mapped_row_provenance_count=mapped_row_provenance_count,
        exact_mapped_row_provenance_count=exact_mapped_row_provenance_count,
        heuristic_mapped_row_provenance_count=heuristic_mapped_row_provenance_count,
    )
    exact_bridge_status = "PASS" if exact_checks["exact_geometry_bridge_pass"] else "CHECK"
    summary_line = (
        f"MIDAS kds-geometry-bridge: {('ok' if pass_threshold else 'missing')} | "
        f"mapped_review_ids={mapped_review_id_count}/{review_id_count} | "
        f"exact={exact_mapped_review_id_count} | heuristic={heuristic_mapped_review_id_count} | "
        f"rows={review_row_count} | "
        f"row_provenance={mapped_row_provenance_count}/{review_row_count} | "
        f"row_exact={exact_mapped_row_provenance_count} | row_heuristic={heuristic_mapped_row_provenance_count} | "
        f"strategies={_strategy_label(strategy_counts)} | "
        f"confidence={_strategy_label(confidence_counts)} | "
        f"source={source_label} | "
        f"registry={registry_source_label} {external_registry_usable_row_count}/{external_registry_row_count} | "
        f"registry_exact={external_registry_exact_row_count} | "
        f"registry_heuristic={external_registry_heuristic_row_count} | "
        f"registry_sources={_strategy_label(external_registry_source_counts)} | "
        f"exact_bridge={exact_bridge_status} | "
        f"exact_review_ids={exact_mapped_review_id_count}/{review_id_count} | "
        f"exact_rows={exact_mapped_row_provenance_count}/{review_row_count} | "
        f"snapshots={exact_review_geometry_snapshot_count}/{exact_review_geometry_snapshot_expected} {exact_review_geometry_snapshot_status} | "
        f"section_parity={exact_review_geometry_section_parity_count}/{exact_review_geometry_section_parity_expected} {exact_review_geometry_section_parity_status} | "
        f"load_crosswalk={exact_review_load_crosswalk_count}/{exact_review_load_crosswalk_expected} {exact_review_load_crosswalk_status} | "
        f"semantic_crosswalk={exact_review_semantic_crosswalk_count}/{exact_review_semantic_crosswalk_expected} {exact_review_semantic_crosswalk_status} | "
        f"full_member_crosswalk={full_member_crosswalk_count}/{full_member_crosswalk_expected} {full_member_crosswalk_status} | "
        f"full_section_crosswalk={full_section_crosswalk_count}/{full_section_crosswalk_expected} {full_section_crosswalk_status} | "
        f"full_load_crosswalk={full_load_crosswalk_count}/{full_load_crosswalk_expected} {full_load_crosswalk_status} | "
        f"geometry_diff={exact_geometry_diff_count}/{exact_geometry_diff_expected} {exact_geometry_diff_status} max={exact_geometry_diff_max_abs:.6g}"
    )
    return {
        "path": str(path),
        "has_kds_geometry_bridge": bool(bridge),
        "mapped_review_id_count": mapped_review_id_count,
        "exact_mapped_review_id_count": exact_mapped_review_id_count,
        "heuristic_mapped_review_id_count": heuristic_mapped_review_id_count,
        "review_id_count": review_id_count,
        "review_row_count": review_row_count,
        "mapped_row_provenance_count": mapped_row_provenance_count,
        "exact_mapped_row_provenance_count": exact_mapped_row_provenance_count,
        "heuristic_mapped_row_provenance_count": heuristic_mapped_row_provenance_count,
        "strategy_counts": {str(key): int(value or 0) for key, value in strategy_counts.items()},
        "confidence_counts": {str(key): int(value or 0) for key, value in confidence_counts.items()},
        "source_label": source_label,
        "registry_source_label": registry_source_label,
        "registry_contract_version": registry_contract_version,
        "registry_summary_path": registry_path,
        "external_registry_row_count": external_registry_row_count,
        "external_registry_usable_row_count": external_registry_usable_row_count,
        "external_registry_exact_row_count": external_registry_exact_row_count,
        "external_registry_heuristic_row_count": external_registry_heuristic_row_count,
        "external_registry_source_counts": {str(key): int(value or 0) for key, value in external_registry_source_counts.items()},
        "exact_review_geometry_snapshot_count": exact_review_geometry_snapshot_count,
        "exact_review_geometry_snapshot_expected": exact_review_geometry_snapshot_expected,
        "exact_review_geometry_snapshot_status": exact_review_geometry_snapshot_status,
        "exact_review_geometry_section_parity_count": exact_review_geometry_section_parity_count,
        "exact_review_geometry_section_parity_expected": exact_review_geometry_section_parity_expected,
        "exact_review_geometry_section_parity_status": exact_review_geometry_section_parity_status,
        "exact_review_load_crosswalk_count": exact_review_load_crosswalk_count,
        "exact_review_load_crosswalk_expected": exact_review_load_crosswalk_expected,
        "exact_review_load_crosswalk_status": exact_review_load_crosswalk_status,
        "exact_review_semantic_crosswalk_count": exact_review_semantic_crosswalk_count,
        "exact_review_semantic_crosswalk_expected": exact_review_semantic_crosswalk_expected,
        "exact_review_semantic_crosswalk_status": exact_review_semantic_crosswalk_status,
        "full_member_crosswalk_count": full_member_crosswalk_count,
        "full_member_crosswalk_expected": full_member_crosswalk_expected,
        "full_member_crosswalk_status": full_member_crosswalk_status,
        "full_member_crosswalk_handle_kind": full_member_crosswalk_handle_kind,
        "full_member_crosswalk_structured_coverage_by_kind": {
            kind: sorted(values) for kind, values in sorted(structured_member_coverage_by_kind.items()) if values
        },
        "full_member_crosswalk_structured_inventory_by_kind": {
            kind: sorted(values) for kind, values in sorted(structured_member_inventory_by_kind.items()) if values
        },
        "full_section_crosswalk_count": full_section_crosswalk_count,
        "full_section_crosswalk_expected": full_section_crosswalk_expected,
        "full_section_crosswalk_status": full_section_crosswalk_status,
        "full_section_crosswalk_structured_coverage_ids": sorted(structured_section_coverage_ids),
        "full_section_crosswalk_structured_inventory_ids": sorted(structured_section_inventory_ids),
        "full_load_crosswalk_count": full_load_crosswalk_count,
        "full_load_crosswalk_expected": full_load_crosswalk_expected,
        "full_load_crosswalk_status": full_load_crosswalk_status,
        "full_load_crosswalk_structured_coverage_names": sorted(structured_load_coverage_names),
        "full_load_crosswalk_structured_inventory_names": sorted(structured_load_inventory_names),
        "exact_geometry_diff_count": exact_geometry_diff_count,
        "exact_geometry_diff_expected": exact_geometry_diff_expected,
        "exact_geometry_diff_status": exact_geometry_diff_status,
        "exact_geometry_diff_max_abs": float(exact_geometry_diff_max_abs),
        "mapping_gap_active": mapping_gap_active,
        "min_mapped_review_ids": int(min_mapped_review_ids),
        "pass_threshold": pass_threshold,
        "exact_bridge_status": exact_bridge_status,
        "exact_geometry_bridge_pass": bool(exact_checks["exact_geometry_bridge_pass"]),
        "review_ids_present": bool(exact_checks["review_ids_present"]),
        "review_rows_present": bool(exact_checks["review_rows_present"]),
        "review_ids_fully_mapped": bool(exact_checks["review_ids_fully_mapped"]),
        "review_ids_exact_only": bool(exact_checks["review_ids_exact_only"]),
        "row_provenance_fully_mapped": bool(exact_checks["row_provenance_fully_mapped"]),
        "row_provenance_exact_only": bool(exact_checks["row_provenance_exact_only"]),
        "summary_line": summary_line,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate embedded MIDAS kds_geometry_bridge metadata.")
    parser.add_argument(
        "--path",
        dest="paths",
        action="append",
        help="Explicit MIDAS model JSON to inspect. Can be passed multiple times. Defaults to the three canonical MIDAS artifacts.",
    )
    parser.add_argument(
        "--min-mapped-review-ids",
        type=int,
        default=0,
        help="Minimum mapped review id count required for each artifact. Defaults to 0 so the validator tracks coverage without forcing non-zero mapping yet.",
    )
    parser.add_argument(
        "--require",
        action="store_true",
        help="Exit non-zero if any target is missing kds_geometry_bridge metadata or does not satisfy the minimum mapped review-id threshold.",
    )
    parser.add_argument(
        "--require-exact",
        action="store_true",
        help="Exit non-zero unless every target has a fully exact, non-heuristic geometry bridge and exact row provenance coverage.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional JSON report path for the exact-geometry bridge validation surface.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    targets = [Path(item) for item in args.paths] if args.paths else list(DEFAULT_TARGETS)
    summaries = [summarize_artifact(path, min_mapped_review_ids=args.min_mapped_review_ids) for path in targets]
    for row in summaries:
        print(f"{row['summary_line']} | {row['path']}")
    exact_pass_count = int(sum(1 for row in summaries if bool(row.get("exact_geometry_bridge_pass", False))))
    threshold_pass_count = int(sum(1 for row in summaries if bool(row.get("pass_threshold", False))))
    full_member_crosswalk_metric = _structured_member_aggregate_metric(summaries) or _aggregate_metric(
        summaries=summaries,
        count_key="full_member_crosswalk_count",
        expected_key="full_member_crosswalk_expected",
        pass_value=bool(
            all(str(row.get("full_member_crosswalk_status", "") or "") == "PASS" for row in summaries)
            and bool(summaries)
        ),
    )
    full_section_crosswalk_metric = _structured_set_aggregate_metric(
        summaries,
        coverage_key="full_section_crosswalk_structured_coverage_ids",
        inventory_key="full_section_crosswalk_structured_inventory_ids",
        expected_key="full_section_crosswalk_expected",
    ) or _aggregate_metric(
        summaries=summaries,
        count_key="full_section_crosswalk_count",
        expected_key="full_section_crosswalk_expected",
        pass_value=bool(
            all(str(row.get("full_section_crosswalk_status", "") or "") == "PASS" for row in summaries)
            and bool(summaries)
        ),
    )
    full_load_crosswalk_metric = _aggregate_metric(
        summaries=summaries,
        count_key="full_load_crosswalk_count",
        expected_key="full_load_crosswalk_expected",
        pass_value=bool(
            all(str(row.get("full_load_crosswalk_status", "") or "") == "PASS" for row in summaries)
            and bool(summaries)
        ),
    )
    checks = {
        "threshold_pass": bool(threshold_pass_count == len(summaries) and bool(summaries)),
        "exact_geometry_bridge_pass": bool(exact_pass_count == len(summaries) and bool(summaries)),
        "exact_section_parity_pass": bool(
            all(str(row.get("exact_review_geometry_section_parity_status", "") or "") == "PASS" for row in summaries)
            and bool(summaries)
        ),
        "exact_load_crosswalk_pass": bool(
            all(str(row.get("exact_review_load_crosswalk_status", "") or "") == "PASS" for row in summaries)
            and bool(summaries)
        ),
        "exact_semantic_crosswalk_pass": bool(
            all(str(row.get("exact_review_semantic_crosswalk_status", "") or "") == "PASS" for row in summaries)
            and bool(summaries)
        ),
        "full_member_crosswalk_pass": bool(full_member_crosswalk_metric["pass"] and bool(summaries)),
        "full_section_crosswalk_pass": bool(full_section_crosswalk_metric["pass"] and bool(summaries)),
        "full_load_crosswalk_pass": bool(full_load_crosswalk_metric["pass"] and bool(summaries)),
        "exact_geometry_diff_pass": bool(
            all(str(row.get("exact_geometry_diff_status", "") or "") == "PASS" for row in summaries)
            and bool(summaries)
        ),
    }
    aggregate = {
        "exact_review_load_crosswalk": _aggregate_metric(
            summaries=summaries,
            count_key="exact_review_load_crosswalk_count",
            expected_key="exact_review_load_crosswalk_expected",
            pass_value=checks["exact_load_crosswalk_pass"],
        ),
        "exact_review_semantic_crosswalk": _aggregate_metric(
            summaries=summaries,
            count_key="exact_review_semantic_crosswalk_count",
            expected_key="exact_review_semantic_crosswalk_expected",
            pass_value=checks["exact_semantic_crosswalk_pass"],
        ),
        "full_member_crosswalk": full_member_crosswalk_metric,
        "full_section_crosswalk": full_section_crosswalk_metric,
        "full_load_crosswalk": full_load_crosswalk_metric,
    }
    report = {
        "schema_version": "1.0",
        "run_id": "phase1-validate-midas-kds-geometry-bridge-artifacts",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(exact_pass_count == len(summaries) and bool(summaries)),
        "checks": checks,
        "aggregate": aggregate,
        "exact_review_load_crosswalk_count_total": int(aggregate["exact_review_load_crosswalk"]["count_total"]),
        "exact_review_load_crosswalk_expected_total": int(aggregate["exact_review_load_crosswalk"]["expected_total"]),
        "exact_review_load_crosswalk_status": str(aggregate["exact_review_load_crosswalk"]["status"]),
        "exact_review_load_crosswalk_pass": bool(aggregate["exact_review_load_crosswalk"]["pass"]),
        "exact_review_semantic_crosswalk_count_total": int(aggregate["exact_review_semantic_crosswalk"]["count_total"]),
        "exact_review_semantic_crosswalk_expected_total": int(aggregate["exact_review_semantic_crosswalk"]["expected_total"]),
        "exact_review_semantic_crosswalk_status": str(aggregate["exact_review_semantic_crosswalk"]["status"]),
        "exact_review_semantic_crosswalk_pass": bool(aggregate["exact_review_semantic_crosswalk"]["pass"]),
        "full_member_crosswalk_count_total": int(aggregate["full_member_crosswalk"]["count_total"]),
        "full_member_crosswalk_expected_total": int(aggregate["full_member_crosswalk"]["expected_total"]),
        "full_member_crosswalk_status": str(aggregate["full_member_crosswalk"]["status"]),
        "full_member_crosswalk_pass": bool(aggregate["full_member_crosswalk"]["pass"]),
        "full_member_crosswalk_basis": str(aggregate["full_member_crosswalk"].get("basis", "artifact_sum")),
        "full_member_crosswalk_handle_kind": str(aggregate["full_member_crosswalk"].get("handle_kind", "") or ""),
        "full_section_crosswalk_count_total": int(aggregate["full_section_crosswalk"]["count_total"]),
        "full_section_crosswalk_expected_total": int(aggregate["full_section_crosswalk"]["expected_total"]),
        "full_section_crosswalk_status": str(aggregate["full_section_crosswalk"]["status"]),
        "full_section_crosswalk_pass": bool(aggregate["full_section_crosswalk"]["pass"]),
        "full_section_crosswalk_basis": str(aggregate["full_section_crosswalk"].get("basis", "artifact_sum")),
        "full_load_crosswalk_count_total": int(aggregate["full_load_crosswalk"]["count_total"]),
        "full_load_crosswalk_expected_total": int(aggregate["full_load_crosswalk"]["expected_total"]),
        "full_load_crosswalk_status": str(aggregate["full_load_crosswalk"]["status"]),
        "full_load_crosswalk_pass": bool(aggregate["full_load_crosswalk"]["pass"]),
        "summary": {
            "artifact_count": int(len(summaries)),
            "threshold_pass_count": threshold_pass_count,
            "exact_geometry_bridge_pass_count": exact_pass_count,
            "review_id_count_total": int(sum(int(row.get("review_id_count", 0) or 0) for row in summaries)),
            "exact_mapped_review_id_count_total": int(
                sum(int(row.get("exact_mapped_review_id_count", 0) or 0) for row in summaries)
            ),
            "review_row_count_total": int(sum(int(row.get("review_row_count", 0) or 0) for row in summaries)),
            "exact_mapped_row_provenance_count_total": int(
                sum(int(row.get("exact_mapped_row_provenance_count", 0) or 0) for row in summaries)
            ),
            "exact_review_geometry_snapshot_count_total": int(
                sum(int(row.get("exact_review_geometry_snapshot_count", 0) or 0) for row in summaries)
            ),
            "exact_review_geometry_snapshot_expected_total": int(
                sum(int(row.get("exact_review_geometry_snapshot_expected", 0) or 0) for row in summaries)
            ),
            "exact_review_geometry_section_parity_count_total": int(
                sum(int(row.get("exact_review_geometry_section_parity_count", 0) or 0) for row in summaries)
            ),
            "exact_review_geometry_section_parity_expected_total": int(
                sum(int(row.get("exact_review_geometry_section_parity_expected", 0) or 0) for row in summaries)
            ),
            "exact_review_load_crosswalk_count_total": int(aggregate["exact_review_load_crosswalk"]["count_total"]),
            "exact_review_load_crosswalk_expected_total": int(aggregate["exact_review_load_crosswalk"]["expected_total"]),
            "exact_review_semantic_crosswalk_count_total": int(aggregate["exact_review_semantic_crosswalk"]["count_total"]),
            "exact_review_semantic_crosswalk_expected_total": int(aggregate["exact_review_semantic_crosswalk"]["expected_total"]),
            "full_member_crosswalk_count_total": int(aggregate["full_member_crosswalk"]["count_total"]),
            "full_member_crosswalk_expected_total": int(aggregate["full_member_crosswalk"]["expected_total"]),
            "full_member_crosswalk_basis": str(aggregate["full_member_crosswalk"].get("basis", "artifact_sum")),
            "full_member_crosswalk_handle_kind": str(aggregate["full_member_crosswalk"].get("handle_kind", "") or ""),
            "full_section_crosswalk_count_total": int(aggregate["full_section_crosswalk"]["count_total"]),
            "full_section_crosswalk_expected_total": int(aggregate["full_section_crosswalk"]["expected_total"]),
            "full_section_crosswalk_basis": str(aggregate["full_section_crosswalk"].get("basis", "artifact_sum")),
            "full_load_crosswalk_count_total": int(aggregate["full_load_crosswalk"]["count_total"]),
            "full_load_crosswalk_expected_total": int(aggregate["full_load_crosswalk"]["expected_total"]),
            "exact_geometry_diff_count_total": int(
                sum(int(row.get("exact_geometry_diff_count", 0) or 0) for row in summaries)
            ),
            "exact_geometry_diff_expected_total": int(
                sum(int(row.get("exact_geometry_diff_expected", 0) or 0) for row in summaries)
            ),
            "exact_geometry_diff_max_abs": float(
                max((float(row.get("exact_geometry_diff_max_abs", 0.0) or 0.0) for row in summaries), default=0.0)
            ),
            "artifact_rows": summaries,
            "require_exact_active": bool(args.require_exact),
            "min_mapped_review_ids": int(args.min_mapped_review_ids),
        },
        "summary_line": (
            "MIDAS-KDS exact geometry bridge validator: "
            f"{'PASS' if exact_pass_count == len(summaries) and summaries else 'CHECK'} | "
            f"artifacts={exact_pass_count}/{len(summaries)} exact | "
            f"threshold={threshold_pass_count}/{len(summaries)} | "
            f"exact_review_ids={sum(int(row.get('exact_mapped_review_id_count', 0) or 0) for row in summaries)}/"
            f"{sum(int(row.get('review_id_count', 0) or 0) for row in summaries)} | "
            f"exact_rows={sum(int(row.get('exact_mapped_row_provenance_count', 0) or 0) for row in summaries)}/"
            f"{sum(int(row.get('review_row_count', 0) or 0) for row in summaries)} | "
            f"snapshots={sum(int(row.get('exact_review_geometry_snapshot_count', 0) or 0) for row in summaries)}/"
            f"{sum(int(row.get('exact_review_geometry_snapshot_expected', 0) or 0) for row in summaries)} | "
            f"section_parity={sum(int(row.get('exact_review_geometry_section_parity_count', 0) or 0) for row in summaries)}/"
            f"{sum(int(row.get('exact_review_geometry_section_parity_expected', 0) or 0) for row in summaries)} | "
            f"load_crosswalk={sum(int(row.get('exact_review_load_crosswalk_count', 0) or 0) for row in summaries)}/"
            f"{sum(int(row.get('exact_review_load_crosswalk_expected', 0) or 0) for row in summaries)} | "
            f"semantic_crosswalk={sum(int(row.get('exact_review_semantic_crosswalk_count', 0) or 0) for row in summaries)}/"
            f"{sum(int(row.get('exact_review_semantic_crosswalk_expected', 0) or 0) for row in summaries)} | "
            f"full_member_crosswalk={int(aggregate['full_member_crosswalk']['count_total'])}/"
            f"{int(aggregate['full_member_crosswalk']['expected_total'])} "
            f"{str(aggregate['full_member_crosswalk']['status'])} | "
            f"full_section_crosswalk={int(aggregate['full_section_crosswalk']['count_total'])}/"
            f"{int(aggregate['full_section_crosswalk']['expected_total'])} "
            f"{str(aggregate['full_section_crosswalk']['status'])} | "
            f"full_load_crosswalk={int(aggregate['full_load_crosswalk']['count_total'])}/"
            f"{int(aggregate['full_load_crosswalk']['expected_total'])} "
            f"{str(aggregate['full_load_crosswalk']['status'])} | "
            f"geometry_diff={sum(int(row.get('exact_geometry_diff_count', 0) or 0) for row in summaries)}/"
            f"{sum(int(row.get('exact_geometry_diff_expected', 0) or 0) for row in summaries)}"
        ),
    }
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.require and any(not row["pass_threshold"] for row in summaries):
        return 1
    if args.require_exact and any(not row["exact_geometry_bridge_pass"] for row in summaries):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
