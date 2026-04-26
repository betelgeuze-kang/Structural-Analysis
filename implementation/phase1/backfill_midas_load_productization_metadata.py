#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from parse_midas_mgt_to_json_npz import (
        derive_load_combination_editor_seed_for_model_payload,
        derive_load_productization_from_raw_combination_payload,
        derive_load_pattern_productization_for_model_payload,
        enrich_kds_geometry_bridge_full_crosswalk_metadata,
    )
except ImportError:  # pragma: no cover - package import fallback
    from implementation.phase1.parse_midas_mgt_to_json_npz import (
        derive_load_combination_editor_seed_for_model_payload,
        derive_load_productization_from_raw_combination_payload,
        derive_load_pattern_productization_for_model_payload,
        enrich_kds_geometry_bridge_full_crosswalk_metadata,
    )


CANONICAL_MIDAS_ARTIFACTS = (
    Path("implementation/phase1/open_data/midas/midas_generator_33.json"),
    Path("implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json"),
    Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"),
)
RAW_RECOVERY_MODE = "combination_only_raw_recovery"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return payload


def _embedded_summary(load_pattern_library: dict[str, Any], editor_seed: dict[str, Any]) -> dict[str, Any]:
    pattern_summary = load_pattern_library.get("summary") if isinstance(load_pattern_library.get("summary"), dict) else {}
    editor_summary = editor_seed.get("summary") if isinstance(editor_seed.get("summary"), dict) else {}
    return {
        "patterns": int(pattern_summary.get("pattern_count", 0) or 0),
        "primitives": int(pattern_summary.get("primitive_count", 0) or 0),
        "combos": int((load_pattern_library.get("combination_summary") or {}).get("combination_count", 0) or 0),
        "editor_combo_nodes": int(editor_summary.get("combination_count", 0) or 0),
        "editor_case_nodes": int(editor_summary.get("case_count", 0) or 0),
        "editor_edges": int(editor_summary.get("graph_edge_count", 0) or 0),
        "editor_stages": int(editor_summary.get("stage_count", 0) or 0),
    }


def _embedded_geometry_bridge_summary(bridge_payload: dict[str, Any]) -> dict[str, Any]:
    summary = bridge_payload.get("summary") if isinstance(bridge_payload.get("summary"), dict) else {}
    return {
        "geometry_full_member_crosswalk_count": int(summary.get("full_member_crosswalk_count", 0) or 0),
        "geometry_full_member_crosswalk_expected": int(summary.get("full_member_crosswalk_expected", 0) or 0),
        "geometry_full_member_crosswalk_status": str(summary.get("full_member_crosswalk_status", "") or ""),
        "geometry_full_section_crosswalk_count": int(summary.get("full_section_crosswalk_count", 0) or 0),
        "geometry_full_section_crosswalk_expected": int(summary.get("full_section_crosswalk_expected", 0) or 0),
        "geometry_full_section_crosswalk_status": str(summary.get("full_section_crosswalk_status", "") or ""),
        "geometry_full_load_crosswalk_count": int(summary.get("full_load_crosswalk_count", 0) or 0),
        "geometry_full_load_crosswalk_expected": int(summary.get("full_load_crosswalk_expected", 0) or 0),
        "geometry_full_load_crosswalk_status": str(summary.get("full_load_crosswalk_status", "") or ""),
        "geometry_full_crosswalk_summary_label": str(summary.get("full_crosswalk_summary_label", "") or ""),
    }


def _design_situation_to_static_type(design_situation: str) -> str:
    normalized = str(design_situation or "").strip().lower()
    return {
        "dead": "D",
        "live": "L",
        "wind": "W",
        "snow": "S",
        "seismic": "E",
        "thermal": "T",
    }.get(normalized, "USER")


def _design_situation_to_category(design_situation: str) -> str:
    normalized = str(design_situation or "").strip().lower()
    return {
        "dead": "Dead",
        "live": "Live",
        "wind": "Wind",
        "snow": "Snow",
        "seismic": "Seismic",
        "thermal": "Thermal",
    }.get(normalized, "Static")


def _build_minimal_loads_from_recovery(
    *,
    load_pattern_library: dict[str, Any],
    load_combination_editor_seed: dict[str, Any],
    recovery_summary: dict[str, Any],
) -> dict[str, Any]:
    pattern_summary = (
        load_pattern_library.get("pattern_summary")
        if isinstance(load_pattern_library.get("pattern_summary"), dict)
        else {}
    )
    pattern_rows = [row for row in (pattern_summary.get("patterns") or []) if isinstance(row, dict)]
    semantic_case_rows = [
        row for row in (load_pattern_library.get("case_semantic_rows") or []) if isinstance(row, dict)
    ]
    case_nodes = [row for row in (load_combination_editor_seed.get("case_nodes") or []) if isinstance(row, dict)]
    combination_nodes = [
        row for row in (load_combination_editor_seed.get("combination_nodes") or []) if isinstance(row, dict)
    ]
    graph_edges = [row for row in (load_combination_editor_seed.get("graph_edges") or []) if isinstance(row, dict)]

    case_names: list[str] = []
    case_context: dict[str, dict[str, Any]] = {}
    for row in pattern_rows:
        name = str(row.get("label", "") or "").strip()
        if not name:
            continue
        case_names.append(name)
        case_context.setdefault(name, {}).update(row)
    for row in semantic_case_rows:
        name = str(row.get("load_case", "") or "").strip()
        if not name:
            continue
        if name not in case_names:
            case_names.append(name)
        case_context.setdefault(name, {}).update(row)
    for row in case_nodes:
        name = str(row.get("name", "") or "").strip()
        if not name:
            continue
        if name not in case_names:
            case_names.append(name)
        case_context.setdefault(name, {}).update(row)

    static_load_cases = []
    load_cases = []
    for case_name in case_names:
        context = case_context.get(case_name, {})
        design_situation = str(context.get("design_situation", "") or "service")
        static_load_cases.append(
            {
                "name": case_name,
                "type": _design_situation_to_static_type(design_situation),
            }
        )
        load_cases.append(
            {
                "name": case_name,
                "category": _design_situation_to_category(design_situation),
            }
        )

    load_combinations = []
    graph_nodes = []
    combo_summaries = []
    for row in case_nodes:
        case_name = str(row.get("name", "") or "").strip()
        if not case_name:
            continue
        graph_nodes.append(
            {
                "id": str(row.get("id", "") or f"CASE:{case_name}"),
                "kind": "case",
                "name": case_name,
            }
        )
    for row in combination_nodes:
        combo_name = str(row.get("name", "") or "").strip()
        if not combo_name:
            continue
        referenced_cases = [
            str(item).strip()
            for item in (
                row.get("referenced_leaf_cases")
                or row.get("referenced_cases")
                or list((row.get("factor_map") or {}).keys())
                or []
            )
            if str(item).strip()
        ]
        referenced_combinations = [
            str(item).strip() for item in (row.get("referenced_combinations") or []) if str(item).strip()
        ]
        factor_map = {
            str(key): float(value)
            for key, value in ((row.get("factor_map") or {}).items() if isinstance(row.get("factor_map"), dict) else [])
            if str(key).strip()
        }
        entry_rows = []
        for entry in (row.get("entry_rows") or []):
            if not isinstance(entry, dict):
                continue
            reference_name = str(entry.get("reference_name", "") or "").strip()
            reference_kind = str(entry.get("reference_kind", "") or "").strip().upper()
            if not reference_name or reference_kind not in {"ST", "CB"}:
                continue
            entry_rows.append(
                {
                    "reference_kind": reference_kind,
                    "reference_name": reference_name,
                    "factor": float(entry.get("factor", 0.0) or 0.0),
                }
            )
        load_combinations.append(
            {
                "name": combo_name,
                "limit_state": str(row.get("limit_state", "") or "unspecified"),
                "combination_type": str(row.get("combination_type", "") or "GEN"),
                "referenced_cases": referenced_cases,
                "referenced_combinations": referenced_combinations,
                "expanded_factor_map": factor_map,
                "factor_map": factor_map,
                "expansion_mode": str(row.get("expansion_mode", "") or "linear_combination"),
                "expansion_depth": int(row.get("expansion_depth", 0) or 0),
                "referenced_leaf_cases": referenced_cases,
                "expression": str(row.get("expression", "") or ""),
                "entries": entry_rows,
                "entry_count": int(row.get("entry_count", len(entry_rows)) or 0),
            }
        )
        combo_summaries.append(
            {
                "name": combo_name,
                "expansion_depth": int(row.get("expansion_depth", 0) or 0),
                "referenced_leaf_cases": referenced_cases,
                "expanded_factor_map": factor_map,
            }
        )
        graph_nodes.append(
            {
                "id": str(row.get("id", "") or f"COMBO:{combo_name}"),
                "kind": "combo",
                "name": combo_name,
            }
        )

    load_combination_graph = {
        "node_count": int(len(graph_nodes)),
        "edge_count": int(len(graph_edges)),
        "combo_node_count": int(len(combination_nodes)),
        "case_node_count": int(len(case_nodes)),
        "nodes": graph_nodes,
        "edges": [
            {
                "src": str(edge.get("src", "") or ""),
                "dst": str(edge.get("dst", "") or ""),
                "kind": str(edge.get("kind", "") or "edge"),
                "factor": float(edge.get("factor", 0.0) or 0.0),
            }
            for edge in graph_edges
            if str(edge.get("src", "") or "").strip() and str(edge.get("dst", "") or "").strip()
        ],
        "combo_summaries": combo_summaries,
    }
    case_force_summaries = [
        {
            "load_case": str(row.get("load_case", "") or "").strip(),
            "semantic_status": str(row.get("semantic_status", "") or RAW_RECOVERY_MODE),
            "reference_count": int(row.get("reference_count", 0) or 0),
            "notes": str(row.get("notes", "") or ""),
        }
        for row in semantic_case_rows
        if str(row.get("load_case", "") or "").strip()
    ]
    return {
        "provenance": RAW_RECOVERY_MODE,
        "limitations": [
            str(item)
            for item in (load_pattern_library.get("limitations") or [])
            if str(item).strip()
        ],
        "static_load_cases": static_load_cases,
        "load_cases": load_cases,
        "load_combinations": load_combinations,
        "load_combination_graph": load_combination_graph,
        "semantic_load_summary": {
            "case_force_summaries": case_force_summaries,
            "case_count": int(len(case_force_summaries)),
            "combination_count": int(len(load_combinations)),
            "bound_nodal_load_row_count": 0,
            "bound_selfweight_row_count": 0,
            "bound_pressure_row_count": 0,
            "unbound_nodal_load_row_count": 0,
            "unbound_selfweight_row_count": 0,
            "unbound_pressure_row_count": 0,
        },
        "nodal_loads": [],
        "selfweight": [],
        "pressure_loads": [],
        "recovery_summary": {
            str(key): value for key, value in recovery_summary.items()
        },
    }


def backfill_artifact(path: Path, *, write: bool = False) -> dict[str, Any]:
    payload = _load_json(path)
    model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
    if not isinstance(model, dict):
        raise ValueError(f"{path} is missing a model object")
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    loads = model.get("loads") if isinstance(model.get("loads"), dict) else {}
    use_raw_recovery = (not loads) or str(loads.get("provenance", "") or "") == RAW_RECOVERY_MODE

    recovery_summary: dict[str, Any] = {}
    materialized_loads: dict[str, Any] = {}
    if use_raw_recovery:
        recovered = derive_load_productization_from_raw_combination_payload(payload)
        load_pattern_library = recovered.get("load_pattern_library") if isinstance(recovered.get("load_pattern_library"), dict) else {}
        load_combination_editor_seed = recovered.get("load_combination_editor_seed") if isinstance(recovered.get("load_combination_editor_seed"), dict) else {}
        recovery_summary = recovered.get("recovery_summary") if isinstance(recovered.get("recovery_summary"), dict) else {}
        if load_pattern_library and load_combination_editor_seed:
            materialized_loads = _build_minimal_loads_from_recovery(
                load_pattern_library=load_pattern_library,
                load_combination_editor_seed=load_combination_editor_seed,
                recovery_summary=recovery_summary,
            )
    else:
        load_pattern_library = derive_load_pattern_productization_for_model_payload(payload)
        load_combination_editor_seed = derive_load_combination_editor_seed_for_model_payload(payload)
    if not load_pattern_library:
        return {
            "path": str(path),
            "supported": False,
            "missing_load_contract": True,
            "patterns": 0,
            "primitives": 0,
            "combos": 0,
            "editor_combo_nodes": 0,
            "editor_case_nodes": 0,
            "editor_edges": 0,
            "editor_stages": 0,
            "changed": False,
            "had_embedded_load_pattern_library": bool(metadata.get("load_pattern_library")),
            "had_embedded_load_combination_editor_seed": bool(metadata.get("load_combination_editor_seed")),
            "written": False,
            "recovery_mode": str(recovery_summary.get("mode", "") or ""),
        }
    if not load_combination_editor_seed:
        return {
            "path": str(path),
            "supported": False,
            "missing_load_contract": True,
            "patterns": 0,
            "primitives": 0,
            "combos": 0,
            "editor_combo_nodes": 0,
            "editor_case_nodes": 0,
            "editor_edges": 0,
            "editor_stages": 0,
            "changed": False,
            "had_embedded_load_pattern_library": bool(metadata.get("load_pattern_library")),
            "had_embedded_load_combination_editor_seed": bool(metadata.get("load_combination_editor_seed")),
            "written": False,
            "recovery_mode": str(recovery_summary.get("mode", "") or ""),
        }

    existing_pattern = metadata.get("load_pattern_library") if isinstance(metadata.get("load_pattern_library"), dict) else {}
    existing_seed = metadata.get("load_combination_editor_seed") if isinstance(metadata.get("load_combination_editor_seed"), dict) else {}
    existing_recovery = metadata.get("load_contract_recovery") if isinstance(metadata.get("load_contract_recovery"), dict) else {}
    existing_bridge = metadata.get("kds_geometry_bridge") if isinstance(metadata.get("kds_geometry_bridge"), dict) else {}
    recovery_payload = recovery_summary if recovery_summary else {}
    prospective_metadata = dict(metadata)
    prospective_metadata["load_pattern_library"] = load_pattern_library
    prospective_metadata["load_combination_editor_seed"] = load_combination_editor_seed
    if recovery_payload:
        prospective_metadata["load_contract_recovery"] = recovery_payload
    else:
        prospective_metadata.pop("load_contract_recovery", None)
    prospective_model = dict(model)
    prospective_model["metadata"] = prospective_metadata
    if materialized_loads:
        prospective_model["loads"] = materialized_loads
    prospective_payload = dict(payload)
    prospective_payload["model"] = prospective_model
    prospective_bridge = prospective_metadata.get("kds_geometry_bridge") if isinstance(prospective_metadata.get("kds_geometry_bridge"), dict) else {}
    enriched_bridge = (
        enrich_kds_geometry_bridge_full_crosswalk_metadata(prospective_payload, prospective_bridge)
        if prospective_bridge
        else {}
    )
    changed = (
        existing_pattern != load_pattern_library
        or existing_seed != load_combination_editor_seed
        or existing_recovery != recovery_payload
        or (bool(prospective_bridge) and prospective_bridge != enriched_bridge)
        or (bool(materialized_loads) and loads != materialized_loads)
    )
    if write and changed:
        metadata = prospective_metadata
        if enriched_bridge:
            metadata["kds_geometry_bridge"] = enriched_bridge
        model = prospective_model
        model["metadata"] = metadata
        payload = prospective_payload
        payload["model"] = model
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = _embedded_summary(load_pattern_library, load_combination_editor_seed)
    summary.update(_embedded_geometry_bridge_summary(enriched_bridge))
    summary.update(
        {
            "path": str(path),
            "supported": True,
            "missing_load_contract": False,
            "changed": changed,
            "had_embedded_load_pattern_library": bool(existing_pattern),
            "had_embedded_load_combination_editor_seed": bool(existing_seed),
            "had_embedded_kds_geometry_bridge": bool(existing_bridge),
            "recovery_mode": str(recovery_payload.get("mode", "") or ""),
            "written": bool(write and changed),
        }
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Embed load_pattern_library and load_combination_editor_seed metadata into canonical MIDAS JSON artifacts."
    )
    parser.add_argument("paths", nargs="*", type=Path, default=list(CANONICAL_MIDAS_ARTIFACTS))
    parser.add_argument("--write", action="store_true", help="Write updated payloads back to disk.")
    args = parser.parse_args()

    for path in args.paths:
        summary = backfill_artifact(path, write=args.write)
        if not bool(summary.get("supported", False)):
            print(f"{path}: unsupported load artifact | loads block unavailable | written=False")
            continue
        recovery_suffix = f" recovery={summary['recovery_mode']}" if str(summary.get("recovery_mode", "") or "") else ""
        print(
            f"{path}: patterns={summary['patterns']} primitives={summary['primitives']} combos={summary['combos']} "
            f"editor_nodes={summary['editor_combo_nodes']}/{summary['editor_case_nodes']} "
            f"editor_edges={summary['editor_edges']} stages={summary['editor_stages']}{recovery_suffix} "
            f"changed={summary['changed']} written={summary['written']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
