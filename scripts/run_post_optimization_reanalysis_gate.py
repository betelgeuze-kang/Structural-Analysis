#!/usr/bin/env python3
"""Post-optimization re-analysis gate (delivery evidence).

Validates inputs, summarizes optimization change safety metrics, and records
provenance. Native MGT full re-analysis is not wired; story-model checks use
change-row solver fields (drift/DCR) until the engine loop is connected.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_proxy_solver_divergence_gate import analyze_changes  # noqa: E402
from run_mgt_native_reanalysis_pipeline import verify_mgt_roundtrip_integrity  # noqa: E402
from run_story_model_reanalysis import (  # noqa: E402
    build_mgt_reanalysis_provenance,
    run_story_model_reanalysis,
)
from sync_mgt_roundtrip_provenance import sync_roundtrip_source_from_mgt  # noqa: E402


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _summarize_roundtrip(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    parser = payload.get("parser") if isinstance(payload.get("parser"), dict) else {}
    section_counts = parser.get("section_counts") if isinstance(parser.get("section_counts"), dict) else {}
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    return {
        "schema_version": payload.get("schema_version"),
        "run_id": payload.get("run_id"),
        "element_count": int(section_counts.get("ELEMENT") or 0),
        "node_count": int(section_counts.get("NODE") or 0),
        "source_path": source.get("path"),
        "source_sha256": source.get("sha256"),
    }


def _summarize_changes(changes: dict[str, Any]) -> dict[str, Any]:
    rows = changes.get("changes") if isinstance(changes.get("changes"), list) else []
    cost_delta_sum = 0.0
    max_dcr_after = 0.0
    max_drift_after = 0.0
    for row in rows:
        if not isinstance(row, dict):
            continue
        cost_delta_sum += _safe_float(row.get("cost_proxy_delta"))
        max_dcr_after = max(max_dcr_after, _safe_float(row.get("governing_member_governing_dcr_after")))
        max_drift_after = max(max_drift_after, _safe_float(row.get("drift_after_pct")))
    return {
        "change_count": len(rows),
        "cost_proxy_delta_sum": round(cost_delta_sum, 4),
        "max_governing_dcr_after": round(max_dcr_after, 4),
        "max_drift_after_pct": round(max_drift_after, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--optimized-roundtrip-json", type=Path, required=True)
    parser.add_argument("--changes-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument(
        "--require-changes",
        action="store_true",
        help="Fail when changes.json has zero change rows.",
    )
    parser.add_argument(
        "--max-governing-dcr",
        type=float,
        default=1.35,
        help="Record blocker when any change row exceeds this governing DCR after value.",
    )
    parser.add_argument(
        "--fail-on-proxy-divergence",
        action="store_true",
        help="Fail when proxy/solver divergence gate reports issues.",
    )
    parser.add_argument(
        "--strict-blockers",
        action="store_true",
        help="Exit non-zero when blockers are present (default: record only).",
    )
    parser.add_argument(
        "--solver-state-npz",
        type=Path,
        default=REPO_ROOT
        / "implementation/phase1/release/design_optimization/design_optimization_solver_loop_state.npz",
    )
    parser.add_argument(
        "--run-story-reanalysis",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run story-model solver reanalysis on optimization state NPZ.",
    )
    parser.add_argument(
        "--optimized-mgt",
        type=Path,
        default=REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt",
    )
    parser.add_argument(
        "--sync-mgt-provenance",
        action="store_true",
        help="Refresh roundtrip source.sha256 from on-disk optimized MGT before checks.",
    )
    parser.add_argument(
        "--fail-on-mgt-integrity",
        action="store_true",
        help="Record blocker when MGT sha256 does not match roundtrip JSON source.",
    )
    args = parser.parse_args()

    missing = [
        label
        for label, path in (
            ("optimized roundtrip", args.optimized_roundtrip_json),
            ("changes", args.changes_json),
        )
        if not path.is_file()
    ]
    if missing:
        print(f"gate: missing inputs: {', '.join(missing)}", file=sys.stderr)
        return 2

    changes = _load_json(args.changes_json)
    change_rows = changes.get("changes") if isinstance(changes.get("changes"), list) else []
    if args.require_changes and not change_rows:
        print("gate: changes.json has no rows", file=sys.stderr)
        return 3

    mgt_sync: dict[str, Any] | None = None
    if args.sync_mgt_provenance and args.optimized_mgt.is_file():
        mgt_sync = sync_roundtrip_source_from_mgt(
            roundtrip_json=args.optimized_roundtrip_json,
            mgt_path=args.optimized_mgt,
        )

    roundtrip_summary = _summarize_roundtrip(args.optimized_roundtrip_json)
    change_summary = _summarize_changes(changes)
    mgt_integrity = verify_mgt_roundtrip_integrity(
        roundtrip_json=args.optimized_roundtrip_json,
        mgt_path=args.optimized_mgt if args.optimized_mgt.is_file() else None,
    )
    proxy_report = analyze_changes(changes, max_governing_dcr_after=args.max_governing_dcr)

    blockers: list[str] = []
    if change_summary["max_governing_dcr_after"] > args.max_governing_dcr:
        blockers.append("governing_dcr_after_exceeds_limit")
    if args.fail_on_proxy_divergence and proxy_report.get("divergence_count", 0) > 0:
        blockers.append("proxy_solver_divergence")
    if args.fail_on_mgt_integrity and mgt_integrity.get("integrity_status") == "sha_mismatch":
        blockers.append("mgt_sha256_mismatch")
    elif mgt_integrity.get("integrity_status") == "missing_mgt":
        blockers.append("mgt_file_missing")

    story_receipt: dict[str, Any] | None = None
    mgt_provenance: dict[str, Any] | None = None
    if args.run_story_reanalysis and args.solver_state_npz.is_file():
        try:
            story_receipt = run_story_model_reanalysis(
                state_npz_path=args.solver_state_npz,
                changes_payload=changes,
            )
            mgt_provenance = build_mgt_reanalysis_provenance(roundtrip_json=args.optimized_roundtrip_json)
            if story_receipt.get("status") == "blocked":
                for item in story_receipt.get("blockers") or []:
                    recorded = f"story_reanalysis_{item}"
                    if recorded not in blockers:
                        blockers.append(recorded)
        except Exception as exc:  # noqa: BLE001
            blockers.append("story_reanalysis_failed")
            story_receipt = {"status": "error", "error": str(exc)}

    status = "pass_with_story_proxy_check" if not blockers else "pass_with_blockers_recorded"
    payload = {
        "schema_version": "post-optimization-reanalysis-gate.v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "claim": "Reduced story-model change-row check; not licensed structural approval.",
        "optimized_roundtrip_json": str(args.optimized_roundtrip_json),
        "changes_json": str(args.changes_json),
        "roundtrip_summary": roundtrip_summary,
        "change_summary": change_summary,
        "proxy_solver_divergence": proxy_report,
        "story_model_reanalysis": story_receipt,
        "mgt_provenance": mgt_provenance,
        "mgt_integrity": mgt_integrity,
        "mgt_sync": mgt_sync,
        "blockers": blockers,
        "thresholds": {"max_governing_dcr": args.max_governing_dcr},
        "next_step": "Wire MGT→global FEA native solve; roundtrip parse+sha sync is available via sync_optimized_mgt_roundtrip.py.",
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"gate: {status} -> {args.output_json}")
    if blockers:
        print(f"gate: blockers={','.join(blockers)}", file=sys.stderr)
        if args.strict_blockers:
            return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
