#!/usr/bin/env python3
"""Build a typed load/load-combination/stage semantics contract artifact."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_ROUNDTRIP = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
DEFAULT_CONSTRUCTION = REPO_ROOT / "implementation/phase1/construction_sequence_gate_report.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def build_load_stage_semantics_contract(
    *,
    productization_dir: Path = PRODUCTIZATION,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
    construction_gate_json: Path = DEFAULT_CONSTRUCTION,
    output_json: Path | None = None,
) -> dict[str, Any]:
    roundtrip = _load(roundtrip_json)
    model = roundtrip.get("model") if isinstance(roundtrip.get("model"), dict) else {}
    loads = model.get("loads") if isinstance(model.get("loads"), dict) else {}
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    load_gate = _load(productization_dir / "load_combination_engine_gate.json")
    construction = _load(construction_gate_json)

    load_summary = load_gate.get("summary") if isinstance(load_gate.get("summary"), dict) else {}
    artifact_rows = load_summary.get("artifact_rows") if isinstance(load_summary.get("artifact_rows"), list) else []
    first_row = artifact_rows[0] if artifact_rows and isinstance(artifact_rows[0], dict) else {}
    construction_summary = (
        construction.get("summary")
        if isinstance(construction.get("summary"), dict)
        else {}
    )

    case_entities = [
        {
            "id": f"CASE:{row.get('name')}",
            "name": row.get("name"),
            "type": row.get("type") or row.get("category"),
            "source": "model.loads.static_load_cases",
            "active": row.get("name") in set(loads.get("active_static_case_sequence") or []),
        }
        for row in (loads.get("static_load_cases") or [])
        if isinstance(row, dict) and str(row.get("name") or "").strip()
    ]
    combo_entities = [
        {
            "id": f"COMBO:{row.get('name')}",
            "name": row.get("name"),
            "limit_state": row.get("limit_state"),
            "combination_type": row.get("combination_type"),
            "referenced_cases": row.get("referenced_cases") or row.get("referenced_leaf_cases") or [],
            "referenced_combinations": row.get("referenced_combinations") or [],
            "expansion_depth": row.get("expansion_depth"),
            "factor_map": row.get("expanded_factor_map") or row.get("factor_map") or {},
            "raw_row_count": len(row.get("raw_rows") or []),
        }
        for row in (loads.get("load_combinations") or [])
        if isinstance(row, dict) and str(row.get("name") or "").strip()
    ]
    graph = loads.get("load_combination_graph") if isinstance(loads.get("load_combination_graph"), dict) else {}
    pattern_library = (
        metadata.get("load_pattern_library")
        if isinstance(metadata.get("load_pattern_library"), dict)
        else {}
    )
    editor_seed = (
        metadata.get("load_combination_editor_seed")
        if isinstance(metadata.get("load_combination_editor_seed"), dict)
        else {}
    )

    load_engine_pass = bool(load_gate.get("contract_pass"))
    construction_pass = bool(construction.get("contract_pass"))
    unresolved_refs = int(first_row.get("runtime_unresolved_reference_count") or 0)
    coverage_ratio = float(first_row.get("required_load_pattern_coverage_ratio") or 0.0)
    stage_count = int(construction_summary.get("stage_count") or 0)
    combo_count = int(load_summary.get("runtime_combo_count_total") or len(combo_entities))
    case_count = int(len(case_entities))
    typed_runtime_entities_ready = bool(
        load_engine_pass
        and case_count > 0
        and combo_count > 0
        and unresolved_refs == 0
        and coverage_ratio >= 1.0
        and graph.get("node_count")
        and graph.get("edge_count")
        and pattern_library
        and editor_seed
    )
    stage_semantics_ready = bool(construction_pass and stage_count > 0)
    status = "ready" if typed_runtime_entities_ready and stage_semantics_ready else "partial"

    payload = {
        "schema_version": "load-stage-semantics-contract.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "typed_runtime_entities_ready": typed_runtime_entities_ready,
        "stage_semantics_ready": stage_semantics_ready,
        "roundtrip_json": str(roundtrip_json),
        "load_combination_engine_gate": str(productization_dir / "load_combination_engine_gate.json"),
        "construction_sequence_gate": str(construction_gate_json),
        "summary": {
            "case_entity_count": case_count,
            "combination_entity_count": len(combo_entities),
            "graph_node_count": int(graph.get("node_count") or 0),
            "graph_edge_count": int(graph.get("edge_count") or 0),
            "runtime_max_nested_depth": load_summary.get("runtime_max_nested_depth_global"),
            "unresolved_reference_count": unresolved_refs,
            "required_load_pattern_coverage_ratio": coverage_ratio,
            "construction_stage_count": stage_count,
            "construction_case_count": construction_summary.get("case_count"),
        },
        "case_entities": case_entities,
        "combination_entities": combo_entities,
        "stage_semantics": {
            "contract_pass": construction_pass,
            "stage_count": stage_count,
            "construction_years": construction_summary.get("construction_years"),
            "all_stages_converged": (construction.get("checks") or {}).get("all_stages_converged"),
            "stagewise_monotonic_load_pass": (construction.get("checks") or {}).get(
                "stagewise_monotonic_load_pass"
            ),
            "creep_shrinkage_applied": (construction.get("checks") or {}).get("creep_shrinkage_applied"),
        },
        "audit_contract": {
            "raw_load_case_row_count": len(model.get("load_cases_raw") or []),
            "raw_load_combination_row_count": len(model.get("load_combinations_raw") or []),
            "pattern_library_present": bool(pattern_library),
            "editor_seed_present": bool(editor_seed),
            "roundtrip_exact_ready": bool(load_summary.get("exact_roundtrip_ready_artifact_count")),
        },
        "limitations": [
            "Current MIDAS33 optimized lane has gravity/nested combinations; wind/seismic combination breadth is tracked by separate benchmark gates.",
            "Construction sequence evidence is a staged analysis gate, not a full arbitrary MGT construction-stage editor.",
        ],
        "blockers": [] if status == "ready" else ["load_stage_semantics_contract_incomplete"],
    }
    out = output_json or (productization_dir / "load_stage_semantics_contract.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--productization-dir", type=Path, default=PRODUCTIZATION)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--construction-gate-json", type=Path, default=DEFAULT_CONSTRUCTION)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    payload = build_load_stage_semantics_contract(
        productization_dir=args.productization_dir,
        roundtrip_json=args.roundtrip_json,
        construction_gate_json=args.construction_gate_json,
        output_json=args.output_json,
    )
    out = args.output_json or (args.productization_dir / "load_stage_semantics_contract.json")
    print(
        "load-stage-semantics: "
        f"status={payload['status']} typed={payload['typed_runtime_entities_ready']} "
        f"stage={payload['stage_semantics_ready']} "
        f"-> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
