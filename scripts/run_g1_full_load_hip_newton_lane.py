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
ROOT = Path(__file__).resolve().parent.parent
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_CHECKPOINT = (
    PRODUCTIZATION
    / "mgt_shell_material_rowcorr_budget_controller_followup398_after_global_krylov_target4_support4_children"
    / "mgt_shell_material_rowcorr_budget_controller_followup398_after_global_krylov_target4_support4_candidate1_target4_support4_final_checkpoint.npz"
)
DEFAULT_OUT = PRODUCTIZATION / "g1_full_load_hip_newton_lane_report.json"
DEFAULT_CHILD_OUT = PRODUCTIZATION / "g1_full_load_hip_newton_direct_probe.json"
DEFAULT_HIP_CONSISTENCY_PROOF = (
    PRODUCTIZATION / "mgt_residual_jacobian_consistency_hip_required_probe.json"
)
DIRECT_PROBE = Path("implementation/phase1/run_mgt_direct_residual_newton_probe.py")
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"
CHECKPOINT_EVIDENCE_SOURCES: tuple[Path, ...] = (
    PRODUCTIZATION / "g1_checkpoint_retention_manifest.json",
    PRODUCTIZATION / "mgt_g1_followup387_shell_material_budgeted_continuation_status.json",
)
NPZ_PATH_KEYS: tuple[str, ...] = (
    "compact_checkpoint",
    "latest_frontier_compact_checkpoint",
    "retained_checkpoint",
    "retained_checkpoint_npz",
    "retained_checkpoint_at_time",
    "checkpoint_path",
    "checkpoint_npz",
)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
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


def _normalize_workspace_path(value: object) -> Path | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or not stripped.lower().endswith(".npz"):
        return None
    candidate = Path(stripped)
    if candidate.is_absolute():
        return candidate
    return candidate


def _collect_npz_paths_from_json(payload: object) -> list[Path]:
    found: list[Path] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in NPZ_PATH_KEYS and isinstance(value, str):
                resolved = _normalize_workspace_path(value)
                if resolved is not None:
                    found.append(resolved)
                continue
            if isinstance(value, dict):
                inner_path = value.get("path")
                if isinstance(inner_path, str) and key in NPZ_PATH_KEYS:
                    resolved = _normalize_workspace_path(inner_path)
                    if resolved is not None:
                        found.append(resolved)
            found.extend(_collect_npz_paths_from_json(value))
    elif isinstance(payload, list):
        for entry in payload:
            found.extend(_collect_npz_paths_from_json(entry))
    return found


def _scan_evidence_checkpoint_paths(
    sources: tuple[Path, ...] = CHECKPOINT_EVIDENCE_SOURCES,
) -> tuple[list[Path], list[dict[str, Any]]]:
    candidates: list[Path] = []
    per_source: list[dict[str, Any]] = []
    for source in sources:
        entry: dict[str, Any] = {
            "path": str(source),
            "available": False,
            "candidate_count": 0,
            "candidate_paths_sample": [],
        }
        if not source.exists():
            per_source.append(entry)
            continue
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except Exception as exc:
            entry["error"] = exc.__class__.__name__
            per_source.append(entry)
            continue
        entry["available"] = True
        paths: list[Path] = []
        for path in _collect_npz_paths_from_json(payload):
            if path not in paths:
                paths.append(path)
        for path in paths:
            if path not in candidates:
                candidates.append(path)
        entry["candidate_count"] = len(paths)
        entry["candidate_paths_sample"] = [str(p) for p in paths[:12]]
        per_source.append(entry)
    return candidates, per_source


def _auto_select_checkpoint(
    *,
    required_load_scale: float,
    full_load_tolerance: float,
    sources: tuple[Path, ...] = CHECKPOINT_EVIDENCE_SOURCES,
) -> dict[str, Any]:
    candidates, per_source = _scan_evidence_checkpoint_paths(sources)
    observed: list[dict[str, Any]] = []
    for index, path in enumerate(candidates):
        meta, _blockers = _load_checkpoint_meta(path)
        entry = {
            "path": str(path),
            "candidate_index": index,
            "exists": path.exists(),
            "load_scale": meta.get("load_scale"),
            "schema": meta.get("schema", ""),
            "dof_count": meta.get("dof_count"),
        }
        observed.append(entry)
    loadable = [
        entry
        for entry in observed
        if entry["exists"] and isinstance(entry["load_scale"], (int, float))
    ]
    if not loadable:
        return {
            "mode": "auto_select",
            "sources": per_source,
            "candidate_count": len(candidates),
            "loadable_count": 0,
            "unloadable_count": len(observed),
            "highest_observed_load_scale": None,
            "loadable_candidates": [],
            "selected_checkpoint": None,
            "selection_reason": "no_loadable_candidates",
        }
    ranked = sorted(
        loadable,
        key=lambda e: (float(e["load_scale"]), int(e["candidate_index"])),
        reverse=True,
    )
    best = ranked[0]
    best_load = float(best["load_scale"])
    meets_full_load = best_load >= float(required_load_scale) - float(full_load_tolerance)
    reason = (
        "full_load_candidate_selected"
        if meets_full_load
        else "highest_sub_full_load_candidate_selected"
    )
    return {
        "mode": "auto_select",
        "sources": per_source,
        "candidate_count": len(candidates),
        "loadable_count": len(loadable),
        "unloadable_count": len(observed) - len(loadable),
        "highest_observed_load_scale": best_load,
        "loadable_candidates": ranked[:12],
        "selected_checkpoint": {
            "path": str(best["path"]),
            "load_scale": best_load,
            "meets_full_load": meets_full_load,
            "schema": best.get("schema", ""),
            "dof_count": best.get("dof_count"),
        },
        "selection_reason": reason,
    }


def _resolve_checkpoint(
    *,
    requested: Path | None,
    required_load_scale: float,
    full_load_tolerance: float,
    sources: tuple[Path, ...] = CHECKPOINT_EVIDENCE_SOURCES,
) -> tuple[Path | None, dict[str, Any]]:
    if requested is None:
        selection = _auto_select_checkpoint(
            required_load_scale=required_load_scale,
            full_load_tolerance=full_load_tolerance,
            sources=sources,
        )
        selected = selection.get("selected_checkpoint") or {}
        selected_path = selected.get("path")
        if not selected_path:
            return None, {
                "requested_path": None,
                "mode": "auto_select",
                "selection": selection,
            }
        return Path(selected_path), {
            "requested_path": None,
            "mode": "auto_select",
            "selection": selection,
        }
    return requested, {
        "requested_path": str(requested),
        "mode": "explicit",
        "selection": None,
    }


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


def _load_json_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _hip_consistency_proof_assessment(
    *,
    proof_json: Path,
    lane_source_commit_sha: str,
) -> tuple[dict[str, Any], list[str]]:
    payload = _load_json_payload(proof_json)
    blockers: list[str] = []
    if not payload:
        blockers.append("hip_consistency_proof_receipt_missing_or_unreadable")
    if payload.get("reused_evidence") is not False:
        blockers.append("hip_consistency_proof_reused_evidence_not_false")
    proof_source_commit = str(payload.get("source_commit_sha", "") or "")
    if not proof_source_commit:
        blockers.append("hip_consistency_proof_source_commit_sha_missing")
    elif lane_source_commit_sha and proof_source_commit != lane_source_commit_sha:
        blockers.append("hip_consistency_proof_source_commit_sha_mismatch")
    if payload.get("rocm_hip_required") is not True:
        blockers.append("hip_consistency_proof_rocm_hip_not_required")
    if payload.get("consistent_residual_jacobian_newton_gate_passed") is not True:
        blockers.append("hip_consistency_proof_gate_not_passed")
    proof_blockers = payload.get("blockers")
    if isinstance(proof_blockers, list) and proof_blockers:
        blockers.append("hip_consistency_proof_has_blockers")
    return {
        "path": str(proof_json),
        "present": proof_json.exists(),
        "status": payload.get("status"),
        "source_commit_sha": proof_source_commit,
        "reused_evidence": payload.get("reused_evidence"),
        "rocm_hip_required": payload.get("rocm_hip_required"),
        "consistent_residual_jacobian_newton_gate_passed": payload.get(
            "consistent_residual_jacobian_newton_gate_passed"
        ),
        "receipt_blockers": proof_blockers if isinstance(proof_blockers, list) else [],
    }, blockers


def build_lane_report(
    *,
    checkpoint_npz: Path | None = None,
    output_json: Path = DEFAULT_CHILD_OUT,
    mgt_path: Path | None = None,
    required_load_scale: float = 1.0,
    full_load_tolerance: float = 1.0e-12,
    dry_run: bool = False,
    evidence_sources: tuple[Path, ...] = CHECKPOINT_EVIDENCE_SOURCES,
    hip_consistency_proof_json: Path = DEFAULT_HIP_CONSISTENCY_PROOF,
) -> tuple[dict[str, Any], int]:
    generated_at = _now_utc_iso()
    resolved_checkpoint, checkpoint_resolution = _resolve_checkpoint(
        requested=checkpoint_npz,
        required_load_scale=required_load_scale,
        full_load_tolerance=full_load_tolerance,
        sources=evidence_sources,
    )
    if resolved_checkpoint is None:
        checkpoint_meta = {"path": None, "load_scale": None}
        blockers = ["auto_select_no_loadable_candidates"]
    else:
        checkpoint_meta, blockers = _load_checkpoint_meta(resolved_checkpoint)
    observed_load_scale = checkpoint_meta.get("load_scale")
    full_load_input_pass = bool(
        observed_load_scale is not None
        and float(observed_load_scale) >= float(required_load_scale) - float(full_load_tolerance)
    )
    if not full_load_input_pass and "checkpoint_load_scale_missing" not in blockers:
        blockers.append("checkpoint_load_scale_below_required_full_load")
    command = _direct_probe_command(
        checkpoint_npz=resolved_checkpoint or DEFAULT_CHECKPOINT,
        output_json=output_json,
        mgt_path=mgt_path,
    )
    source_commit_sha = _git_head()
    hip_consistency_proof, hip_consistency_blockers = _hip_consistency_proof_assessment(
        proof_json=hip_consistency_proof_json,
        lane_source_commit_sha=source_commit_sha,
    )
    base_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_commit_sha": source_commit_sha,
        "engine_version": ENGINE_VERSION,
        "reused_evidence": False,
        "checkpoint": checkpoint_meta,
        "checkpoint_resolution": checkpoint_resolution,
        "required_load_scale": float(required_load_scale),
        "full_load_tolerance": float(full_load_tolerance),
        "full_load_input_pass": full_load_input_pass,
        "dry_run": bool(dry_run),
        "command": command,
        "hip_consistency_proof": hip_consistency_proof,
        "child_safety_requirements": [
            "child_reused_evidence_false",
            "child_source_commit_matches_lane",
            "child_observed_load_scale_at_required_full_load",
            "child_hip_residual_engine_contract_passed",
            "child_consistent_residual_jacobian_newton_passed",
            "external_hip_consistency_proof_gate_passed",
            "child_material_newton_breadth_passed",
            "child_cpu_acceptance_refresh_not_blocked",
            "child_fallback_zero_passed",
        ],
        "claim_boundary": (
            "This lane is a strict execution wrapper for representative full-load "
            "G1 HIP Newton evidence. It does not synthesize residual, increment, "
            "consistent residual/Jacobian Newton closure, material Newton breadth, "
            "customer, validation, or ROCm/HIP closure evidence. "
            "The child probe must explicitly prove full-load closure, HIP residual residency, "
            "consistent residual/Jacobian Newton closure, fallback-zero behavior, "
            "and material Newton breadth. The separate HIP-required residual/Jacobian "
            "consistency receipt must also pass without blockers. A checkpoint below "
            "load_scale 1.0 is blocked before execution."
        ),
    }
    if blockers:
        return {
            **base_payload,
            "status": "blocked",
            "contract_pass": False,
            "blockers": [*blockers, *hip_consistency_blockers],
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
    safety_blockers.extend(hip_consistency_blockers)
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
    consistent_jacobian_passed = bool(
        child_gate.get("consistent_residual_jacobian_newton_passed") is True
        or child_gate.get("residual_jacobian_consistency_ready") is True
        or residual_contract.get("consistent_residual_jacobian_newton_gate_passed")
        is True
    )
    if not consistent_jacobian_passed:
        blockers.append("child_consistent_residual_jacobian_newton_not_proven")
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


def _checkpoint_path_arg(value: str) -> Path | None:
    stripped = value.strip()
    if stripped.lower() == "auto":
        return None
    return Path(stripped)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint-npz",
        type=_checkpoint_path_arg,
        default=None,
        help=(
            "Path to the G1 checkpoint .npz to feed the direct residual Newton probe. "
            "Omit this option, or pass the literal value 'auto', to scan configured "
            "status/manifest JSON files and select the highest-load candidate."
        ),
    )
    parser.add_argument("--child-output-json", type=Path, default=DEFAULT_CHILD_OUT)
    parser.add_argument("--mgt-path", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--required-load-scale", type=float, default=1.0)
    parser.add_argument("--full-load-tolerance", type=float, default=1.0e-12)
    parser.add_argument(
        "--hip-consistency-proof-json",
        type=Path,
        default=DEFAULT_HIP_CONSISTENCY_PROOF,
        help=(
            "HIP-required residual/Jacobian consistency receipt that must pass before "
            "the G1 lane can be promoted."
        ),
    )
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
        hip_consistency_proof_json=args.hip_consistency_proof_json,
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
