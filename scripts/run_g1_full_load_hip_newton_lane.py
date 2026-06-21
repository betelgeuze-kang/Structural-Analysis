#!/usr/bin/env python3
"""Run the strict G1 full-load HIP Newton lane without promoting diagnostics."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import numpy as np


SCHEMA_VERSION = "g1-full-load-hip-newton-lane.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_CHECKPOINT = (
    PRODUCTIZATION
    / "mgt_shell_material_rowcorr_budget_controller_followup398_after_global_krylov_target4_support4_children"
    / "mgt_shell_material_rowcorr_budget_controller_followup398_after_global_krylov_target4_support4_candidate1_target4_support4_final_checkpoint.npz"
)
DEFAULT_OUT = PRODUCTIZATION / "g1_full_load_hip_newton_lane_report.json"
DEFAULT_CHILD_OUT = PRODUCTIZATION / "g1_full_load_hip_newton_direct_probe.json"
DIRECT_PROBE = Path("implementation/phase1/run_mgt_direct_residual_newton_probe.py")
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _load_checkpoint_meta(path: Path) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    if not path.exists():
        return {"path": str(path), "load_scale": None}, ["checkpoint_missing"]
    try:
        with np.load(path, allow_pickle=False) as archive:
            load_scale = (
                float(np.asarray(archive["load_scale"]).item())
                if "load_scale" in archive.files
                else None
            )
            dof_count = (
                int(np.asarray(archive["displacement_u"]).size)
                if "displacement_u" in archive.files
                else None
            )
            schema = (
                str(np.asarray(archive["checkpoint_schema"]).item())
                if "checkpoint_schema" in archive.files
                else ""
            )
    except Exception as exc:
        return {
            "path": str(path),
            "load_scale": None,
            "error": exc.__class__.__name__,
        }, ["checkpoint_unreadable"]
    if load_scale is None:
        blockers.append("checkpoint_load_scale_missing")
    return {
        "path": str(path),
        "schema": schema,
        "load_scale": load_scale,
        "dof_count": dof_count,
    }, blockers


def _direct_probe_command(
    *,
    checkpoint_npz: Path,
    output_json: Path,
    mgt_path: Path | None,
) -> list[str]:
    command = [
        sys.executable,
        str(DIRECT_PROBE),
        "--checkpoint-npz",
        str(checkpoint_npz),
        "--output-json",
        str(output_json),
        "--apply-shell-material-tangent",
        "--allow-state-dependent-shell-material-tangent-hip-replay",
        "--enable-matrix-free-global-krylov",
        "--matrix-free-global-krylov-batch-replay-backend",
        "hip_full_residual_resident",
        "--matrix-free-global-krylov-require-hip-batch-replay",
        "--matrix-free-global-krylov-linear-solver-backend",
        "torch_hip_gmres",
        "--matrix-free-global-krylov-scaling-mode",
        "residual_diagonal_displacement",
        "--matrix-free-global-krylov-preconditioner-mode",
        "current_tangent",
        "--matrix-free-global-krylov-full-assembly-trial-replay",
        "--enable-current-tangent-residual-row-correction",
        "--current-tangent-residual-row-use-residual-only-assembly",
        "--current-tangent-residual-row-per-state-batch-replay",
        "--current-tangent-residual-row-batch-replay-backend",
        "hip_full_residual",
        "--current-tangent-residual-row-require-hip-batch-replay",
        "--current-tangent-residual-row-jacobian-mode",
        "finite_difference",
    ]
    if mgt_path is not None:
        command.extend(["--mgt-path", str(mgt_path)])
    return command


def build_lane_report(
    *,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT,
    output_json: Path = DEFAULT_CHILD_OUT,
    mgt_path: Path | None = None,
    required_load_scale: float = 1.0,
    full_load_tolerance: float = 1.0e-12,
    dry_run: bool = False,
) -> tuple[dict[str, Any], int]:
    generated_at = _now_utc_iso()
    checkpoint_meta, blockers = _load_checkpoint_meta(checkpoint_npz)
    observed_load_scale = checkpoint_meta.get("load_scale")
    full_load_input_pass = bool(
        observed_load_scale is not None
        and float(observed_load_scale) >= float(required_load_scale) - float(full_load_tolerance)
    )
    if not full_load_input_pass and "checkpoint_load_scale_missing" not in blockers:
        blockers.append("checkpoint_load_scale_below_required_full_load")
    command = _direct_probe_command(
        checkpoint_npz=checkpoint_npz,
        output_json=output_json,
        mgt_path=mgt_path,
    )
    base_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "reused_evidence": False,
        "checkpoint": checkpoint_meta,
        "required_load_scale": float(required_load_scale),
        "full_load_tolerance": float(full_load_tolerance),
        "full_load_input_pass": full_load_input_pass,
        "dry_run": bool(dry_run),
        "command": command,
        "child_safety_requirements": [
            "child_reused_evidence_false",
            "child_source_commit_matches_lane",
            "child_observed_load_scale_at_required_full_load",
            "child_hip_residual_engine_contract_passed",
            "child_material_newton_breadth_passed",
            "child_cpu_acceptance_refresh_not_blocked",
            "child_fallback_zero_passed",
        ],
        "claim_boundary": (
            "This lane is a strict execution wrapper for representative full-load "
            "G1 HIP Newton evidence. It does not synthesize residual, increment, "
            "material Newton breadth, customer, validation, or ROCm/HIP closure evidence. "
            "The child probe must explicitly prove full-load closure, HIP residual residency, "
            "fallback-zero behavior, and material Newton breadth. A checkpoint below "
            "load_scale 1.0 is blocked before execution."
        ),
    }
    if blockers:
        return {
            **base_payload,
            "status": "blocked",
            "contract_pass": False,
            "blockers": blockers,
            "child_exit_code": None,
        }, 1
    if dry_run:
        return {
            **base_payload,
            "status": "ready_to_run",
            "contract_pass": False,
            "blockers": [],
            "child_exit_code": None,
        }, 0

    output_json.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, check=False)
    child_payload: dict[str, Any] = {}
    if output_json.exists():
        try:
            loaded = json.loads(output_json.read_text(encoding="utf-8"))
            child_payload = loaded if isinstance(loaded, dict) else {}
        except Exception:
            child_payload = {}
    child_gate = child_payload.get("gate_assessment") if isinstance(child_payload, dict) else {}
    child_gate = child_gate if isinstance(child_gate, dict) else {}
    safety_blockers = _child_safety_blockers(
        child_payload=child_payload,
        child_gate=child_gate,
        lane_source_commit_sha=base_payload["source_commit_sha"],
        required_load_scale=float(required_load_scale),
        full_load_tolerance=float(full_load_tolerance),
    )
    child_ready = bool(
        result.returncode == 0
        and not safety_blockers
        and child_payload.get("direct_residual_newton_ready") is True
        and child_gate.get("full_load_closure_passed") is True
        and child_gate.get("fallback_zero_passed") is True
    )
    child_blockers = child_payload.get("blockers") if isinstance(child_payload, dict) else []
    return {
        **base_payload,
        "status": "ready" if child_ready else "blocked",
        "contract_pass": child_ready,
        "blockers": [] if child_ready else [
            *safety_blockers,
            *(child_blockers if isinstance(child_blockers, list) else []),
            "g1_full_load_hip_newton_child_not_ready",
        ],
        "child_exit_code": int(result.returncode),
        "child_output_json": str(output_json),
    }, 0 if child_ready else 1


def _child_safety_blockers(
    *,
    child_payload: dict[str, Any],
    child_gate: dict[str, Any],
    lane_source_commit_sha: str,
    required_load_scale: float,
    full_load_tolerance: float,
) -> list[str]:
    """Return safety blockers that prevent diagnostic or reused child evidence from
    being promoted as full G1 closure."""
    blockers: list[str] = []
    if child_payload.get("reused_evidence") is not False:
        blockers.append("child_reused_evidence_not_false")
    child_source_commit = str(child_payload.get("source_commit_sha", "") or "")
    if not child_source_commit:
        blockers.append("child_source_commit_sha_missing")
    elif lane_source_commit_sha and child_source_commit != lane_source_commit_sha:
        blockers.append("child_source_commit_sha_mismatch")
    closure_gate = child_gate.get("full_load_closure_gate") if isinstance(child_gate, dict) else {}
    closure_gate = closure_gate if isinstance(closure_gate, dict) else {}
    observed_child_load = closure_gate.get("observed_load_scale")
    try:
        observed_load_value = float(observed_child_load)
    except (TypeError, ValueError):
        observed_load_value = None
    if observed_load_value is None or not (
        observed_load_value >= float(required_load_scale) - float(full_load_tolerance)
    ):
        blockers.append("child_observed_load_scale_below_required_full_load")
    residual_contract = child_payload.get("residual_contract")
    residual_contract = residual_contract if isinstance(residual_contract, dict) else {}
    if residual_contract.get("hip_residual_engine_contract_passed") is not True:
        blockers.append("child_hip_residual_engine_contract_not_proven")
    material_newton_passed = bool(
        child_gate.get("material_newton_breadth_passed") is True
        or residual_contract.get("material_newton_gate_passed") is True
        or residual_contract.get("state_dependent_material_newton_closure_passed")
        is True
    )
    if not material_newton_passed:
        blockers.append("child_material_newton_breadth_not_proven")
    if child_gate.get("cpu_acceptance_refresh_closure_blocked") is True:
        blockers.append("child_cpu_acceptance_refresh_closure_blocked")
    return blockers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--child-output-json", type=Path, default=DEFAULT_CHILD_OUT)
    parser.add_argument("--mgt-path", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--required-load-scale", type=float, default=1.0)
    parser.add_argument("--full-load-tolerance", type=float, default=1.0e-12)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload, exit_code = build_lane_report(
        checkpoint_npz=args.checkpoint_npz,
        output_json=args.child_output_json,
        mgt_path=args.mgt_path,
        required_load_scale=args.required_load_scale,
        full_load_tolerance=args.full_load_tolerance,
        dry_run=args.dry_run,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"G1 full-load HIP Newton lane: {payload['status']}")
    return exit_code if args.fail_blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
