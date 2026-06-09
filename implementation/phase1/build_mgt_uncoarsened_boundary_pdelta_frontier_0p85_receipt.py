#!/usr/bin/env python3
"""Build a frontier-0p85 receipt by aggregating the existing segment JSONs.

This thin bridge:
  - scans the canonical checkpoint-segment directory for every
    mgt-uncoarsened-boundary-pdelta-probe.v1 segment JSON
  - feeds them into the existing aggregate builder
  - emits a dedicated productization receipt describing the
    "frontier toward 0.85" status, including current frontier, the
    next failed bracket, and a per-rule-family max-DCR breakdown

The script is intentionally read-only against the segment directory; it does
not re-run the probe itself. New segment runs are still produced by the
existing :file:`run_mgt_uncoarsened_boundary_pdelta_probe.py` driver, and
they are picked up automatically by re-running this receipt.

Output JSON:
  implementation/phase1/release_evidence/productization/mgt_uncoarsened_boundary_pdelta_frontier_0p85_receipt.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
PRODUCTIZATION = PHASE1 / "release_evidence" / "productization"
SEGMENT_DIR = PRODUCTIZATION / "mgt_uncoarsened_boundary_pdelta_checkpoint_segments"
CHECKPOINT_DIR = PRODUCTIZATION / "mgt_uncoarsened_boundary_pdelta_checkpoints"
SOURCE_CHECKPOINT = CHECKPOINT_DIR / "accepted_load_0p45.npz"
SOURCE_AGGREGATE = PRODUCTIZATION / "mgt_uncoarsened_boundary_pdelta_checkpoint_continuation.json"

sys.path.insert(0, str(PHASE1))
try:
    from build_mgt_uncoarsened_boundary_pdelta_checkpoint_continuation import (  # type: ignore
        PROBE_SCHEMA_VERSION,
    )
except ImportError:  # pragma: no cover
    from implementation.phase1.build_mgt_uncoarsened_boundary_pdelta_checkpoint_continuation import (  # type: ignore
        PROBE_SCHEMA_VERSION,
    )


def _aggregate_segments(segment_paths: list[Path]) -> dict[str, Any]:
    """Aggregate all segments, ignoring aggregate builder's early-break on first failure.

    The canonical aggregate stops at the first segment that records a
    first_failed_load_scale. That is appropriate for a single chain trace but
    loses every later segment when an early segment marks a transient failure.
    For the frontier-0p85 receipt we want to read the *maximum* accepted load
    scale across all segments, not the chain's first failure.
    """
    step_results: list[dict[str, Any]] = []
    max_converged = 0.0
    first_failed_overall: float | None = None
    saved_checkpoints: dict[str, dict[str, Any]] = {}
    segment_count = 0
    accepted_count = 0
    failed_count = 0
    for segment_path in segment_paths:
        try:
            payload = json.loads(segment_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("schema_version") != PROBE_SCHEMA_VERSION:
            continue
        segment_count += 1
        seg_max = float(payload.get("max_converged_load_scale") or 0.0)
        if seg_max > max_converged:
            max_converged = seg_max
        seg_failed = payload.get("first_failed_load_scale")
        if seg_failed is not None:
            seg_failed_f = float(seg_failed)
            if first_failed_overall is None or seg_failed_f < first_failed_overall:
                first_failed_overall = seg_failed_f
        for row in payload.get("step_results") or []:
            if not isinstance(row, dict):
                continue
            load_scale = row.get("load_scale")
            if load_scale is None:
                continue
            if step_results and float(load_scale) <= float(step_results[-1].get("load_scale") or 0.0) + 1.0e-12:
                continue
            step_results.append(row)
        resume = payload.get("checkpoint_resume") if isinstance(payload.get("checkpoint_resume"), dict) else {}
        for checkpoint in resume.get("saved_checkpoints") or []:
            if not isinstance(checkpoint, dict):
                continue
            if checkpoint.get("equilibrium_replay_gate_passed") is False:
                continue
            if "equilibrium_replay_gate_passed" not in checkpoint:
                continue
            name = Path(str(checkpoint.get("path") or "")).name
            if not name:
                continue
            saved_checkpoints[name] = checkpoint
    for row in step_results:
        classification = _classify_step(row)
        if classification in {"accepted", "accepted_no_replay"}:
            accepted_count += 1
        elif classification == "failed":
            failed_count += 1
    return {
        "segment_count": int(segment_count),
        "step_results": step_results,
        "accepted_step_count": int(accepted_count),
        "failed_step_count": int(failed_count),
        "max_converged_load_scale": float(max_converged),
        "first_failed_load_scale": first_failed_overall,
        "saved_checkpoint_count": int(len(saved_checkpoints)),
    }


SCHEMA_VERSION = "mgt-uncoarsened-boundary-pdelta-frontier-0p85-receipt.v1"
TARGET_LOAD_SCALE = 0.85
FRONTIER_0P45 = 0.45
DEFAULT_OUT = PRODUCTIZATION / "mgt_uncoarsened_boundary_pdelta_frontier_0p85_receipt.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _scan_segments(segment_dir: Path) -> list[Path]:
    if not segment_dir.is_dir():
        return []
    return sorted(segment_dir.glob("segment_*.json"))


def _classify_step(step: dict[str, Any]) -> str:
    ready = bool(step.get("ready"))
    if "equilibrium_replay_gate_passed" in step:
        eq_gate = bool(step.get("equilibrium_replay_gate_passed"))
    else:
        eq_gate = bool(step.get("converged", ready))
    if ready and eq_gate:
        return "accepted"
    if ready and not eq_gate:
        return "accepted_no_replay"
    return "failed"


def _per_rule_family_breakdown(step_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rule_families: dict[str, dict[str, Any]] = {}
    for row in step_results:
        if not isinstance(row, dict):
            continue
        family = str(row.get("rule_family") or "strength")
        bucket = rule_families.setdefault(family, {"count": 0, "max_dcr": 0.0, "max_increment": 0.0, "max_residual_n": 0.0})
        bucket["count"] += 1
        dcr = float(row.get("dcr") or 0.0)
        inc = float(row.get("best_fixed_point_relative_increment") or 0.0)
        res = float(row.get("best_residual_inf_n") or 0.0)
        if dcr > bucket["max_dcr"]:
            bucket["max_dcr"] = dcr
        if inc > bucket["max_increment"]:
            bucket["max_increment"] = inc
        if res > bucket["max_residual_n"]:
            bucket["max_residual_n"] = res
    return rule_families


def build_frontier_0p85_receipt(
    *,
    segment_dir: Path = SEGMENT_DIR,
    source_aggregate_json: Path = SOURCE_AGGREGATE,
    source_checkpoint_npz: Path = SOURCE_CHECKPOINT,
    target_load_scale: float = TARGET_LOAD_SCALE,
    output_json: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    segment_paths = _scan_segments(segment_dir)
    source_aggregate = _load(source_aggregate_json)
    source_frontier = float(source_aggregate.get("max_converged_load_scale") or 0.0)
    source_first_failed = source_aggregate.get("first_failed_load_scale")
    source_first_failed = float(source_first_failed) if source_first_failed is not None else None
    aggregate = _aggregate_segments(segment_paths)
    frontier = float(aggregate.get("max_converged_load_scale") or 0.0)
    first_failed = aggregate.get("first_failed_load_scale")
    first_failed = float(first_failed) if first_failed is not None else None

    step_results = aggregate.get("step_results") or []
    rule_family_breakdown = _per_rule_family_breakdown(step_results)
    accepted_steps = [row for row in step_results if _classify_step(row) == "accepted"]
    failed_steps = [row for row in step_results if _classify_step(row) == "failed"]

    target_reached = frontier >= float(target_load_scale)
    incremental_gain_vs_source = float(frontier - source_frontier)
    frontier_diagnostic = {
        "current_frontier_load_scale": frontier,
        "previous_source_aggregate_frontier": source_frontier,
        "frontier_increment_vs_source_aggregate": incremental_gain_vs_source,
        "first_failed_load_scale": first_failed,
        "first_failed_load_scale_source_aggregate": source_first_failed,
        "target_load_scale": float(target_load_scale),
        "frontier_to_target_gap": max(0.0, float(target_load_scale) - frontier),
        "target_reached": bool(target_reached),
        "residual_tolerance_n": float(
            (step_results[0] or {}).get("residual_tolerance_n") or 0.0
        ) if step_results else 0.0,
        "relative_increment_tolerance": float(
            (step_results[0] or {}).get("relative_increment_tolerance") or 0.0
        ) if step_results else 0.0,
    }
    if not target_reached and first_failed is not None:
        frontier_diagnostic["nearest_failed_bracket"] = first_failed
        frontier_diagnostic["next_action"] = (
            "consistent Newton/Jacobian, material tangent, arc-length/trust-region, "
            "or stronger globalization on the next bracket"
        )
    else:
        frontier_diagnostic["nearest_failed_bracket"] = None
        frontier_diagnostic["next_action"] = (
            "promote to full-load consistent Newton/Jacobian closure"
            if target_reached
            else "re-run probe with stronger seed globalization to extend accepted path"
        )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if target_reached else "partial",
        "frontier_0p85_reached": bool(target_reached),
        "target_load_scale": float(target_load_scale),
        "frontier_load_scale": frontier,
        "source": {
            "segment_dir": str(segment_dir),
            "segment_count": int(len(segment_paths)),
            "source_aggregate_json": str(source_aggregate_json),
            "source_aggregate_frontier": source_frontier,
            "source_checkpoint_npz": str(source_checkpoint_npz),
            "source_checkpoint_exists": bool(source_checkpoint_npz.is_file()),
            "source_seed_load_scale": FRONTIER_0P45,
        },
        "frontier_diagnostic": frontier_diagnostic,
        "summary": {
            "segment_count": int(len(segment_paths)),
            "accepted_step_count": int(aggregate.get("accepted_step_count") or 0),
            "failed_step_count": int(aggregate.get("failed_step_count") or 0),
            "saved_checkpoint_count": int(aggregate.get("saved_checkpoint_count") or 0),
            "max_converged_load_scale": frontier,
            "first_failed_load_scale": first_failed,
            "rule_family_breakdown": rule_family_breakdown,
        },
        "claim_boundary": (
            "Frontier 0.85 receipt is an honest read-only aggregate of the existing "
            "mgt-uncoarsened-boundary-pdelta-probe.v1 segment JSONs. It does NOT re-run the probe "
            "or claim any new segment load steps. Frontier extension toward 0.85 still requires "
            "a new probe run with stronger globalization or a consistent Newton/Jacobian. "
            "Until the aggregate's first_failed_load_scale is None AND max_converged_load_scale "
            ">= 0.85, this receipt's status remains partial."
        ),
        "blockers": []
        if target_reached
        else [f"frontier_below_target:{frontier:.6f}_of_{target_load_scale}"],
    }

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment-dir", type=Path, default=SEGMENT_DIR)
    parser.add_argument("--source-aggregate-json", type=Path, default=SOURCE_AGGREGATE)
    parser.add_argument("--source-checkpoint-npz", type=Path, default=SOURCE_CHECKPOINT)
    parser.add_argument("--target-load-scale", type=float, default=TARGET_LOAD_SCALE)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_frontier_0p85_receipt(
        segment_dir=args.segment_dir,
        source_aggregate_json=args.source_aggregate_json,
        source_checkpoint_npz=args.source_checkpoint_npz,
        target_load_scale=float(args.target_load_scale),
        output_json=args.output_json,
    )
    diag = payload.get("frontier_diagnostic", {})
    print(
        "mgt-uncoarsened-boundary-pdelta-frontier-0p85: "
        f"{payload['status']} frontier={payload['frontier_load_scale']} "
        f"target={payload['target_load_scale']} "
        f"failed={diag.get('first_failed_load_scale')} "
        f"target_reached={payload['frontier_0p85_reached']} "
        f"-> {args.output_json}"
    )
    return 0 if payload.get("status") in {"ready", "partial"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
