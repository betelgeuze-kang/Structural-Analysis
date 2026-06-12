#!/usr/bin/env python3
"""Build KDS/code-check/detailing support matrix and unsupported-claim queue."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


SCHEMA_VERSION = "kds-detailing-support-matrix.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
KDS_RULE_ENGINE = REPO_ROOT / "implementation/phase1/kds_rc_rule_engine.py"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_clause_map() -> dict[str, str]:
    if not KDS_RULE_ENGINE.is_file():
        return {}
    spec = importlib.util.spec_from_file_location("kds_rc_rule_engine_matrix", KDS_RULE_ENGINE)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    clause_map = getattr(module, "CLAUSE_MAP", {})
    return dict(clause_map) if isinstance(clause_map, dict) else {}


def build_kds_detailing_support_matrix(
    *,
    productization_dir: Path = PRODUCTIZATION,
    output_json: Path | None = None,
) -> dict[str, Any]:
    clause_map = _load_clause_map()
    code_guard = _load(productization_dir / "ai_code_reasoning_guard.json")
    optimization_audit = _load(productization_dir / "optimization_productization_audit.json")
    review_queue = _load(productization_dir / "ai_review_queue.json")
    load_stage = _load(productization_dir / "load_stage_semantics_contract.json")

    family_counts: Counter[str] = Counter()
    component_counts: Counter[str] = Counter()
    for key in clause_map:
        family, _, component = str(key).partition(":")
        family_counts[family] += 1
        component_counts[f"{family}:{component or 'general'}"] += 1

    required_rc_families = {"beam", "column", "wall", "slab", "foundation", "connection"}
    covered_rc_families = {family for family in required_rc_families if family_counts.get(family, 0) > 0}
    unsupported_clause_queue = [
        {
            **row,
            "required_action_before_claim": row.get("required_action_before_claim")
            or "attach explicit deterministic KDS clause or keep engineer-review-required state",
        }
        for row in (code_guard.get("unsupported_clause_queue") or [])
        if isinstance(row, dict)
    ]
    broader_unsupported_queue = [
        {
            "family": "steel_composite_code_breadth",
            "status": "unsupported_or_engineer_review_required",
            "reason": "Current deterministic rule engine is RC-focused; steel/composite automatic detailing claims are not promoted.",
            "required_action_before_claim": "attach KDS steel/composite clause map, solver-result crosswalk, and regression rows",
        },
        {
            "family": "seismic_special_detailing_breadth",
            "status": "unsupported_or_engineer_review_required",
            "reason": "Special seismic detailing beyond current bounded drift/moment guard is not automatically claimed.",
            "required_action_before_claim": "attach jurisdiction profile, member family checks, load-combo trace, and reviewer workflow",
        },
        {
            "family": "connection_foundation_project_specific_detailing",
            "status": "unsupported_or_engineer_review_required",
            "reason": "Project-specific connection/foundation detailing needs source-specific review before automatic claim.",
            "required_action_before_claim": "attach source detail rows, governing clauses, and signed review disposition",
        },
    ]
    unsupported_queue_ready = all(
        row.get("reason") and row.get("required_action_before_claim")
        for row in [*unsupported_clause_queue, *broader_unsupported_queue]
    )
    clause_breadth_ready = bool(required_rc_families <= covered_rc_families and len(clause_map) >= 20)
    optimization_rows_guarded = bool(
        code_guard.get("status") == "ready"
        and code_guard.get("all_rows_have_clause_or_review_guard")
        and int(code_guard.get("review_guarded_row_count") or 0) == int(code_guard.get("change_row_count") or -1)
    )
    trace_ready = bool(
        optimization_audit.get("status") == "ready"
        and optimization_audit.get("accepted_rows_have_code")
        and load_stage.get("status") == "ready"
        and review_queue.get("status") == "ready"
    )
    ready = bool(clause_breadth_ready and optimization_rows_guarded and trace_ready and unsupported_queue_ready)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if ready else "partial",
        "rule_engine_present": KDS_RULE_ENGINE.is_file(),
        "clause_breadth_ready": clause_breadth_ready,
        "optimization_rows_guarded": optimization_rows_guarded,
        "trace_ready": trace_ready,
        "unsupported_queue_ready": unsupported_queue_ready,
        "claim_boundary": (
            "Deterministic KDS RC clause/detailing support matrix plus automatic-claim guard; "
            "unsupported steel/composite/seismic/project-specific claims remain engineer-review-required."
        ),
        "rule_engine_path": str(KDS_RULE_ENGINE),
        "clause_inventory": {
            "clause_count": len(clause_map),
            "required_rc_families": sorted(required_rc_families),
            "covered_rc_families": sorted(covered_rc_families),
            "family_counts": dict(sorted(family_counts.items())),
            "component_counts": dict(sorted(component_counts.items())),
            "clause_ids": sorted(set(clause_map.values())),
        },
        "optimization_code_guard": {
            "status": code_guard.get("status"),
            "jurisdiction_profile": code_guard.get("jurisdiction_profile"),
            "change_row_count": code_guard.get("change_row_count"),
            "explicit_clause_row_count": code_guard.get("explicit_clause_row_count"),
            "missing_governing_clause_count": code_guard.get("missing_governing_clause_count"),
            "review_guarded_row_count": code_guard.get("review_guarded_row_count"),
            "all_rows_have_clause_or_review_guard": code_guard.get("all_rows_have_clause_or_review_guard"),
            "governing_clause_ids": code_guard.get("governing_clause_ids"),
            "hallucination_guard": code_guard.get("hallucination_guard"),
        },
        "support_matrix": [
            {
                "family": family,
                "status": "deterministic_rule_engine_supported",
                "clause_count": int(family_counts.get(family, 0)),
                "components": sorted(
                    key.split(":", 1)[1]
                    for key in component_counts
                    if key.startswith(f"{family}:")
                ),
            }
            for family in sorted(required_rc_families)
        ],
        "unsupported_clause_queue": unsupported_clause_queue,
        "broader_unsupported_claim_queue": broader_unsupported_queue,
        "blockers": [] if ready else ["kds_detailing_support_matrix_not_ready"],
    }
    out = output_json or productization_dir / "kds_detailing_support_matrix.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--productization-dir", type=Path, default=PRODUCTIZATION)
    parser.add_argument("--output-json", type=Path, default=PRODUCTIZATION / "kds_detailing_support_matrix.json")
    args = parser.parse_args()
    payload = build_kds_detailing_support_matrix(
        productization_dir=args.productization_dir,
        output_json=args.output_json,
    )
    print(
        "kds-detailing-support: "
        f"status={payload['status']} clauses={payload['clause_inventory']['clause_count']} "
        f"guarded={payload['optimization_rows_guarded']} -> {args.output_json}"
    )
    return 0 if payload.get("status") == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
