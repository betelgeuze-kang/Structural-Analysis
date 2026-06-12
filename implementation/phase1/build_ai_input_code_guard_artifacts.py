#!/usr/bin/env python3
"""Build AI input-normalization and code-reasoning guard artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_ROUNDTRIP = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"
KOREA_RECEIPT = REPO_ROOT / "implementation/phase1/open_data/korea/korean_medium_large_ingest_receipt.json"
KDS_RULE_ENGINE = REPO_ROOT / "implementation/phase1/kds_rc_rule_engine.py"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _sha(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_ai_input_code_guard_artifacts(
    *,
    productization_dir: Path = PRODUCTIZATION,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
    output_json: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    roundtrip = _load(roundtrip_json)
    model = roundtrip.get("model") if isinstance(roundtrip.get("model"), dict) else {}
    source = roundtrip.get("source") if isinstance(roundtrip.get("source"), dict) else {}
    topology = roundtrip.get("topology_metrics") if isinstance(roundtrip.get("topology_metrics"), dict) else {}
    korea = _load(KOREA_RECEIPT)
    changes = _load(productization_dir / "design_optimization_cost_reduction_changes.json")
    load_stage = _load(productization_dir / "load_stage_semantics_contract.json")
    review_queue = _load(productization_dir / "ai_review_queue.json")

    per_source = korea.get("per_source") if isinstance(korea.get("per_source"), list) else []
    unsupported_queue = []
    for row in per_source:
        if not isinstance(row, dict):
            continue
        blockers = list(row.get("blockers") or [])
        if row.get("metadata_only"):
            blockers.append("metadata_only_operator_download_required")
        if blockers:
            unsupported_queue.append(
                {
                    "source_id": row.get("source_id"),
                    "format": row.get("format"),
                    "scale": row.get("scale"),
                    "blockers": sorted(set(str(item) for item in blockers)),
                }
            )

    entity_families = [
        {
            "family": "nodes",
            "count": int(len(model.get("nodes") or [])),
            "source": "roundtrip.model.nodes",
            "confidence": "high" if model.get("nodes") else "missing",
        },
        {
            "family": "elements",
            "count": int(len(model.get("elements") or [])),
            "source": "roundtrip.model.elements",
            "confidence": "high" if model.get("elements") else "missing",
        },
        {
            "family": "materials",
            "count": int(len(model.get("materials") or [])),
            "source": "roundtrip.model.materials",
            "confidence": "medium",
        },
        {
            "family": "sections",
            "count": int(len(model.get("sections") or [])),
            "source": "roundtrip.model.sections",
            "confidence": "medium",
        },
        {
            "family": "load_cases",
            "count": int(len(((model.get("loads") or {}).get("static_load_cases") or []))),
            "source": "roundtrip.model.loads.static_load_cases",
            "confidence": "medium",
        },
        {
            "family": "load_combinations",
            "count": int(len(((model.get("loads") or {}).get("load_combinations") or []))),
            "source": "roundtrip.model.loads.load_combinations",
            "confidence": "medium",
        },
    ]
    input_ready = bool(
        source.get("sha256")
        and topology.get("node_count")
        and topology.get("element_count")
        and all(row["count"] > 0 for row in entity_families[:2])
    )
    input_receipt = {
        "schema_version": "ai-input-semantic-normalization-receipt.v1",
        "generated_at": generated_at,
        "status": "ready" if input_ready else "partial",
        "input_semantic_normalization_ready": input_ready,
        "roundtrip_json": str(roundtrip_json),
        "source_path": source.get("path"),
        "source_sha256": source.get("sha256"),
        "roundtrip_sha256": _sha(roundtrip_json),
        "entity_families": entity_families,
        "confidence_policy": {
            "high": "direct parsed geometry/topology identity",
            "medium": "typed semantic row with fallback/coverage caveats",
            "missing": "unsupported or absent entity family",
        },
        "repair_diff": {
            "auto_repair_applied": False,
            "reason": "current lane preserves parsed entities; unsupported cases are queued rather than repaired silently",
        },
        "unsupported_queue": unsupported_queue,
        "load_stage_semantics_status": load_stage.get("status"),
    }

    change_rows = [row for row in (changes.get("changes") or []) if isinstance(row, dict)]
    review_items = [
        row for row in (review_queue.get("queue_items") or []) if isinstance(row, dict)
    ]
    review_guard_by_group = {
        str(row.get("member_or_group_id") or ""): row
        for row in review_items
        if str(row.get("member_or_group_id") or "").strip()
    }
    governing_clauses = sorted(
        {str(row.get("governing_clause")).strip() for row in change_rows if str(row.get("governing_clause") or "").strip()}
    )
    constraint_trace_rows = []
    unsupported_clause_queue = []
    for row in change_rows:
        group_id = str(row.get("group_id") or "")
        action_name = str(row.get("action_name") or "")
        governing_clause = str(row.get("governing_clause") or "").strip()
        review_guard = review_guard_by_group.get(group_id, {})
        review_constraint = str(review_guard.get("governing_constraint") or row.get("selection_gate") or "").strip()
        has_review_guard = bool(
            review_guard
            and str(review_guard.get("queue_state") or "") == "pending_review"
            and str(review_guard.get("unsupported_caveat") or "").strip()
        )
        trace_row = {
            "group_id": group_id,
            "action_name": action_name,
            "governing_clause": governing_clause,
            "governing_constraint": governing_clause or review_constraint,
            "constraint_source": "governing_clause" if governing_clause else "engineer_review_queue",
            "auto_code_claim_allowed": bool(governing_clause),
            "engineer_review_required": bool(not governing_clause or has_review_guard),
            "load_stage_semantics_artifact": str(productization_dir / "load_stage_semantics_contract.json"),
            "review_queue_artifact": str(productization_dir / "ai_review_queue.json"),
        }
        constraint_trace_rows.append(trace_row)
        if not governing_clause:
            unsupported_clause_queue.append(
                {
                    "group_id": group_id,
                    "action_name": action_name,
                    "governing_constraint": review_constraint,
                    "status": "engineer_review_required" if has_review_guard else "missing_review_guard",
                    "reason": (
                        "No explicit deterministic KDS clause was attached to this optimization row; "
                        "automatic code/regulation explanation is blocked and routed to engineer review."
                    ),
                }
            )
    explicit_clause_row_count = sum(1 for row in constraint_trace_rows if row["auto_code_claim_allowed"])
    review_guarded_row_count = sum(
        1
        for row in constraint_trace_rows
        if row["auto_code_claim_allowed"]
        or any(
            item.get("group_id") == row["group_id"] and item.get("status") == "engineer_review_required"
            for item in unsupported_clause_queue
        )
    )
    all_rows_have_clause_or_review_guard = bool(
        change_rows and review_guarded_row_count == len(change_rows)
    )
    code_guard_ready = bool(
        KDS_RULE_ENGINE.is_file()
        and governing_clauses
        and review_queue.get("status") == "ready"
        and load_stage.get("status") == "ready"
        and all_rows_have_clause_or_review_guard
    )
    code_guard = {
        "schema_version": "ai-code-reasoning-guard.v1",
        "generated_at": generated_at,
        "status": "ready" if code_guard_ready else "partial",
        "code_reasoning_guard_ready": code_guard_ready,
        "claim_boundary": "deterministic rule/citation guard only; no autonomous legal approval",
        "rule_engine_path": str(KDS_RULE_ENGINE),
        "rule_engine_present": KDS_RULE_ENGINE.is_file(),
        "jurisdiction_profile": "KDS-2022 bounded lane",
        "governing_clause_ids": governing_clauses,
        "governing_clause_count": len(governing_clauses),
        "change_row_count": len(change_rows),
        "explicit_clause_row_count": explicit_clause_row_count,
        "missing_governing_clause_count": len(unsupported_clause_queue),
        "review_guarded_row_count": review_guarded_row_count,
        "all_rows_have_clause_or_review_guard": all_rows_have_clause_or_review_guard,
        "constraint_trace_rows": constraint_trace_rows,
        "clause_trace_rows": [
            {
                "group_id": row.get("group_id"),
                "action_name": row.get("action_name"),
                "governing_clause": row.get("governing_clause"),
                "load_stage_semantics_artifact": str(productization_dir / "load_stage_semantics_contract.json"),
                "review_queue_artifact": str(productization_dir / "ai_review_queue.json"),
            }
            for row in change_rows
            if row.get("governing_clause")
        ],
        "hallucination_guard": {
            "llm_free_default": True,
            "allowed_claim_source": "explicit governing_clause ids and deterministic KDS rule-engine rows only",
            "unsupported_clause_behavior": "blocked_or_engineer_review_required",
        },
        "unsupported_clause_queue": unsupported_clause_queue,
    }

    productization_dir.mkdir(parents=True, exist_ok=True)
    (productization_dir / "ai_input_semantic_normalization_receipt.json").write_text(
        json.dumps(input_receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (productization_dir / "ai_code_reasoning_guard.json").write_text(
        json.dumps(code_guard, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    index = {
        "schema_version": "ai-input-code-guard-artifacts.v1",
        "generated_at": generated_at,
        "status": "ready" if input_ready and code_guard_ready else "partial",
        "input_semantic_normalization_ready": input_ready,
        "code_reasoning_guard_ready": code_guard_ready,
        "artifacts": {
            "ai_input_semantic_normalization_receipt": str(
                productization_dir / "ai_input_semantic_normalization_receipt.json"
            ),
            "ai_code_reasoning_guard": str(productization_dir / "ai_code_reasoning_guard.json"),
        },
    }
    index_out = output_json or (productization_dir / "ai_input_code_guard_artifacts.json")
    index_out.parent.mkdir(parents=True, exist_ok=True)
    index_out.write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--productization-dir", type=Path, default=PRODUCTIZATION)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    payload = build_ai_input_code_guard_artifacts(
        productization_dir=args.productization_dir,
        roundtrip_json=args.roundtrip_json,
        output_json=args.output_json,
    )
    out = args.output_json or (args.productization_dir / "ai_input_code_guard_artifacts.json")
    print(
        "ai-input-code-guard: "
        f"status={payload['status']} input={payload['input_semantic_normalization_ready']} "
        f"code={payload['code_reasoning_guard_ready']} "
        f"-> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
