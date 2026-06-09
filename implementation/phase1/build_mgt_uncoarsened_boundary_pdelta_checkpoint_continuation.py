#!/usr/bin/env python3
"""Build an aggregate receipt for checkpointed uncoarsened-boundary P-Delta continuation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "mgt-uncoarsened-boundary-pdelta-checkpoint-continuation.v1"
PROBE_SCHEMA_VERSION = "mgt-uncoarsened-boundary-pdelta-probe.v1"
CHECKPOINT_SCHEMA_VERSION = "mgt-uncoarsened-boundary-pdelta-checkpoint.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTIZATION = REPO_ROOT / "implementation/phase1/release_evidence/productization"
DEFAULT_OUT = PRODUCTIZATION / "mgt_uncoarsened_boundary_pdelta_checkpoint_continuation.json"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compact_step(row: dict[str, Any]) -> dict[str, Any]:
    out = {
        "load_scale": _float_or_none(row.get("load_scale")),
        "ready": bool(row.get("ready")),
        "iteration_count": int(row.get("iteration_count") or 0),
        "max_iterations": int(row.get("max_iterations") or 0),
        "relaxation_factor": _float_or_none(row.get("relaxation_factor")),
        "best_residual_inf_n": _float_or_none(row.get("best_residual_inf_n")),
        "best_equilibrium_replay_residual_inf_n": _float_or_none(
            row.get("best_equilibrium_replay_residual_inf_n")
        ),
        "best_solver_residual_inf_n": _float_or_none(row.get("best_solver_residual_inf_n")),
        "equilibrium_replay_gate_passed": bool(row.get("equilibrium_replay_gate_passed")),
        "best_fixed_point_relative_increment": _float_or_none(
            row.get("best_fixed_point_relative_increment")
        ),
        "residual_tolerance_n": _float_or_none(row.get("residual_tolerance_n")),
        "relative_increment_tolerance": _float_or_none(row.get("relative_increment_tolerance")),
        "final_max_translation_m": _float_or_none(row.get("final_max_translation_m")),
        "blockers": row.get("blockers") if isinstance(row.get("blockers"), list) else [],
    }
    if "initial_seed_strategy" in row:
        out["initial_seed_strategy"] = row.get("initial_seed_strategy")
    if isinstance(row.get("secant_seed"), dict):
        out["secant_seed"] = row.get("secant_seed")
    if isinstance(row.get("seed_alpha_scan"), dict):
        out["seed_alpha_scan"] = row.get("seed_alpha_scan")
    return out


def _checkpoint_key(checkpoint: dict[str, Any]) -> tuple[float, str]:
    return (
        float(checkpoint.get("load_scale") or 0.0),
        str(Path(str(checkpoint.get("path") or "")).name),
    )


def _normalize_checkpoint_path(checkpoint: dict[str, Any], checkpoint_dir: Path | None) -> dict[str, Any]:
    out = dict(checkpoint)
    if checkpoint_dir is None:
        return out
    name = Path(str(checkpoint.get("path") or "")).name
    if not name:
        return out
    candidate = checkpoint_dir / name
    if candidate.is_file():
        out["path"] = str(candidate)
    return out


def build_checkpoint_continuation_receipt(
    *,
    segment_paths: list[Path],
    output_json: Path | None = None,
    source_checkpoint_npz: Path | None = None,
    checkpoint_dir: Path | None = None,
) -> dict[str, Any]:
    if not segment_paths:
        raise ValueError("at least one segment JSON is required")

    segments: list[dict[str, Any]] = []
    step_results: list[dict[str, Any]] = []
    saved_checkpoints: dict[tuple[float, str], dict[str, Any]] = {}
    initial_resume: dict[str, Any] | None = None
    previous_frontier = 0.0
    first_failed: float | None = None

    for index, segment_path in enumerate(segment_paths, start=1):
        segment = _load(segment_path)
        if segment.get("schema_version") != PROBE_SCHEMA_VERSION:
            raise ValueError(
                f"{segment_path} schema {segment.get('schema_version')!r} does not match "
                f"{PROBE_SCHEMA_VERSION!r}"
            )
        resume = segment.get("checkpoint_resume") if isinstance(segment.get("checkpoint_resume"), dict) else {}
        if initial_resume is None:
            initial_resume = resume.get("resume_checkpoint") if isinstance(resume.get("resume_checkpoint"), dict) else None
        compact_steps = [
            _compact_step(row)
            for row in (segment.get("step_results") or [])
            if isinstance(row, dict)
        ]
        attempted = [
            float(value)
            for value in (resume.get("attempted_load_steps_after_resume") or [])
            if _float_or_none(value) is not None
        ]
        segment_max = _float_or_none(segment.get("max_converged_load_scale")) or previous_frontier
        segment_failed = _float_or_none(segment.get("first_failed_load_scale"))
        segments.append(
            {
                "index": int(index),
                "path": str(segment_path),
                "status": segment.get("status"),
                "resume_from_load_scale": _float_or_none(resume.get("resume_from_load_scale")),
                "max_converged_load_scale": float(segment_max),
                "first_failed_load_scale": segment_failed,
                "attempted_load_steps_after_resume": attempted,
                "step_count": int(len(compact_steps)),
            }
        )
        for checkpoint in resume.get("saved_checkpoints") or []:
            if isinstance(checkpoint, dict):
                if checkpoint.get("equilibrium_replay_gate_passed") is False:
                    continue
                if "equilibrium_replay_gate_passed" not in checkpoint:
                    continue
                normalized_checkpoint = _normalize_checkpoint_path(checkpoint, checkpoint_dir)
                saved_checkpoints[_checkpoint_key(normalized_checkpoint)] = normalized_checkpoint
        for row in compact_steps:
            load_scale = row.get("load_scale")
            if load_scale is None:
                continue
            if step_results and load_scale <= float(step_results[-1]["load_scale"]) + 1.0e-12:
                continue
            step_results.append(row)
        previous_frontier = max(previous_frontier, float(segment_max))
        if segment_failed is not None:
            first_failed = float(segment_failed)
            break

    accepted_steps = [
        row
        for row in step_results
        if bool(row.get("ready")) and bool(row.get("equilibrium_replay_gate_passed"))
    ]
    failed_steps = [row for row in step_results if not bool(row.get("ready"))]
    max_converged = max((float(row["load_scale"]) for row in accepted_steps), default=0.0)
    if failed_steps:
        first_failed = float(failed_steps[0]["load_scale"])
    full_ready = max_converged >= 1.0 and first_failed is None
    frontier_step = max(accepted_steps, key=lambda row: float(row["load_scale"])) if accepted_steps else None
    failed_step = failed_steps[0] if failed_steps else None
    checkpoints = [saved_checkpoints[key] for key in sorted(saved_checkpoints)]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready" if full_ready else "partial",
        "uncoarsened_boundary_pdelta_checkpoint_continuation_ready": bool(full_ready),
        "source_checkpoint_npz": str(source_checkpoint_npz) if source_checkpoint_npz is not None else None,
        "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
        "initial_resume_checkpoint": initial_resume,
        "segment_count": int(len(segments)),
        "segments": segments,
        "step_results": step_results,
        "accepted_step_count": int(len(accepted_steps)),
        "failed_step_count": int(len(failed_steps)),
        "max_converged_load_scale": float(max_converged),
        "first_failed_load_scale": first_failed,
        "frontier_step": frontier_step,
        "first_failed_step": failed_step,
        "saved_checkpoint_count": int(len(checkpoints)),
        "saved_checkpoints": checkpoints,
        "claim_boundary": (
            "This aggregate receipt chains script-generated checkpoint-resume probe segments. "
            "Only load steps and checkpoints that pass the equilibrium replay gate "
            "||F_int(u)-F_ext|| are promoted; solver-only receipts are excluded. "
            "This is still not a consistent Newton/Jacobian, material nonlinear, or full-load closure."
        ),
        "blockers": []
        if full_ready
        else [
            "uncoarsened_boundary_pdelta_not_full_load_closed",
            "consistent_newton_jacobian_required",
            "material_nonlinear_newton_required",
        ],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment-json", type=Path, action="append", required=True)
    parser.add_argument("--source-checkpoint-npz", type=Path)
    parser.add_argument("--checkpoint-dir", type=Path)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_checkpoint_continuation_receipt(
        segment_paths=[Path(path) for path in args.segment_json],
        output_json=args.output_json,
        source_checkpoint_npz=args.source_checkpoint_npz,
        checkpoint_dir=args.checkpoint_dir,
    )
    print(
        "mgt-uncoarsened-boundary-pdelta-checkpoint-continuation: "
        f"{payload['status']} max_load={payload.get('max_converged_load_scale')} "
        f"failed={payload.get('first_failed_load_scale')} -> {args.output_json}"
    )
    return 0 if payload.get("status") in {"ready", "partial"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
