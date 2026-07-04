#!/usr/bin/env python3
"""Build a non-promoting G1 true-Newton full-load checkpoint candidate receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
PHASE1 = ROOT / "implementation" / "phase1"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402
from run_g1_true_newton_reference_candidate import (  # noqa: E402
    CHECKPOINT_SCHEMA,
    run_g1_true_newton_reference_candidate,
)


SCHEMA_VERSION = "g1-true-newton-full-load-checkpoint-candidate-status.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "g1_true_newton_full_load_checkpoint_candidate_status.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_CHECKPOINT_NPZ = PRODUCTIZATION / "g1_true_newton_full_load_checkpoint_candidate.npz"
DEFAULT_INITIAL_CHECKPOINT_NPZ: Path | None = None
DEFAULT_LOAD_SCALE = 1.0
DEFAULT_MAX_NEWTON_STEPS = 36
DEFAULT_RESIDUAL_GATE_N = 5.0e-4
DEFAULT_REGULARIZATION_MODE = "relative_diagonal_shift"
DEFAULT_REGULARIZATION_MU = 0.1


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _repo_relative_string(repo_root: Path, path_text: str) -> str:
    if not path_text:
        return ""
    try:
        path = Path(path_text)
        if path.is_absolute():
            return path.relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path_text
    return path.as_posix()


def build_g1_true_newton_full_load_checkpoint_candidate_status(
    *,
    repo_root: Path = ROOT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT_NPZ,
    initial_checkpoint_npz: Path | None = DEFAULT_INITIAL_CHECKPOINT_NPZ,
    load_scale: float = DEFAULT_LOAD_SCALE,
    max_newton_steps: int = DEFAULT_MAX_NEWTON_STEPS,
    residual_gate_n: float = DEFAULT_RESIDUAL_GATE_N,
    regularization_mode: str = DEFAULT_REGULARIZATION_MODE,
    regularization_mu: float = DEFAULT_REGULARIZATION_MU,
    allow_signed_direction_globalization: bool = False,
) -> dict[str, Any]:
    resolved_checkpoint = _resolve(repo_root, checkpoint_npz)
    candidate = run_g1_true_newton_reference_candidate(
        load_scale=float(load_scale),
        max_newton_steps=int(max_newton_steps),
        residual_gate_n=float(residual_gate_n),
        regularization_mode=str(regularization_mode),
        regularization_mu=float(regularization_mu),
        allow_signed_direction_globalization=bool(allow_signed_direction_globalization),
        initial_checkpoint_npz=(
            _resolve(repo_root, initial_checkpoint_npz)
            if initial_checkpoint_npz is not None
            else None
        ),
        output_json=None,
        output_final_checkpoint_npz=resolved_checkpoint,
    )
    true_candidate = _dict(candidate.get("true_newton_candidate"))
    checkpoint = dict(_dict(candidate.get("output_final_checkpoint")))
    if checkpoint.get("path"):
        checkpoint["path"] = _repo_relative_string(repo_root, str(checkpoint.get("path")))
    checkpoint_written = bool(checkpoint.get("written") is True)
    checkpoint_schema_pass = bool(checkpoint.get("schema") == CHECKPOINT_SCHEMA)
    full_load_pass = bool(
        (_float_or_none(checkpoint.get("load_scale")) or 0.0) >= float(load_scale)
    )
    residual_gate_passed = bool(true_candidate.get("residual_gate_passed") is True)
    residual_descent_observed = bool(
        (_float_or_none(true_candidate.get("final_residual_n")) or float("inf"))
        < (_float_or_none(true_candidate.get("initial_residual_n")) or 0.0)
    )
    contract_pass = bool(
        candidate.get("uses_real_mgt_model") is True
        and checkpoint_written
        and checkpoint_schema_pass
        and full_load_pass
        and residual_descent_observed
    )
    blockers: list[str] = []
    if not checkpoint_written:
        blockers.append("true_newton_full_load_checkpoint_candidate_not_written")
    if not checkpoint_schema_pass:
        blockers.append("checkpoint_schema_not_mgt_direct_residual_newton_state_v1")
    if not full_load_pass:
        blockers.append("checkpoint_load_scale_below_1p0")
    if not residual_descent_observed:
        blockers.append("full_load_true_newton_residual_descent_not_observed")
    if not residual_gate_passed:
        blockers.append("full_load_true_newton_checkpoint_residual_gate_not_passed")
    blockers.extend(
        [
            "production_rocm_hip_not_executed_by_true_newton_checkpoint_candidate",
            "full_mesh_nonlinear_equilibrium_not_proven_by_true_newton_checkpoint_candidate",
            "material_newton_breadth_not_proven_by_true_newton_checkpoint_candidate",
        ]
    )
    status = "candidate_created" if contract_pass else "blocked"
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_g1_true_newton_full_load_checkpoint_candidate_status.py"),
                Path("implementation/phase1/run_g1_true_newton_reference_candidate.py"),
                Path("implementation/phase1/run_g1_regularized_reference_newton_candidate.py"),
                Path("implementation/phase1/run_g1_mgt_physical_line_search_smoke.py"),
                Path("implementation/phase1/g1_assembled_tangent_solve.py"),
                Path("implementation/phase1/g1_regularized_direction.py"),
            ],
            reused_evidence=False,
            reuse_policy="executes_true_newton_full_load_probe_and_writes_non_promoting_checkpoint_candidate",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": contract_pass,
        "evidence_closure_pass": False,
        "promotes_g1_closure": False,
        "summary_line": (
            "G1 true-Newton full-load checkpoint candidate: "
            f"{status.upper()} | checkpoint_written={checkpoint_written} | "
            f"final_residual={true_candidate.get('final_residual_n')} | "
            f"residual_gate={residual_gate_passed}"
        ),
        "required_load_scale": float(load_scale),
        "max_newton_steps": int(max_newton_steps),
        "residual_gate_n": float(residual_gate_n),
        "regularization": {
            "mode": str(regularization_mode),
            "mu": float(regularization_mu),
        },
        "initial_checkpoint_npz": (
            _repo_relative_string(repo_root, str(_resolve(repo_root, initial_checkpoint_npz)))
            if initial_checkpoint_npz is not None
            else None
        ),
        "initial_state": _dict(candidate.get("initial_state")),
        "true_newton_candidate": {
            "status": candidate.get("status"),
            "reason_code": candidate.get("reason_code"),
            "steps": true_candidate.get("steps"),
            "initial_residual_n": true_candidate.get("initial_residual_n"),
            "final_residual_n": true_candidate.get("final_residual_n"),
            "total_reduction_ratio": true_candidate.get("total_reduction_ratio"),
            "monotonic_residual_decrease": true_candidate.get(
                "monotonic_residual_decrease"
            ),
            "residual_gate_passed": residual_gate_passed,
            "stop_reason": true_candidate.get("stop_reason"),
            "signed_direction_globalization_used": true_candidate.get(
                "signed_direction_globalization_used"
            ),
            "signed_direction_step_count": true_candidate.get(
                "signed_direction_step_count"
            ),
        },
        "signed_direction_globalization": {
            "enabled": bool(allow_signed_direction_globalization),
            "used": bool(
                true_candidate.get("signed_direction_globalization_used") is True
            ),
            "signed_direction_step_count": true_candidate.get(
                "signed_direction_step_count"
            ),
            "claim_boundary": "non_promoting_diagnostic_globalization_only",
        },
        "checkpoint_candidate": checkpoint,
        "checkpoint_written": checkpoint_written,
        "checkpoint_schema_pass": checkpoint_schema_pass,
        "checkpoint_load_scale_pass": full_load_pass,
        "full_load_true_newton_residual_descent_observed": residual_descent_observed,
        "full_load_true_newton_residual_gate_passed": residual_gate_passed,
        "blockers": blockers,
        "next_actions": [
            "run_full_load_direct_residual_probe_against_true_newton_checkpoint_candidate",
            "run_hip_required_residual_jvp_probe_against_true_newton_checkpoint_candidate",
            "replace_candidate_with_gate_passing_checkpoint_after_residual_increment_material_hip_pass",
        ],
        "claim_boundary": (
            "This receipt creates a loadable full-load true-Newton checkpoint candidate. "
            "It is not a G1 closure and does not replace direct residual, increment, "
            "full-mesh nonlinear equilibrium, material Newton breadth, or production "
            "ROCm/HIP proof."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    candidate = _dict(payload.get("true_newton_candidate"))
    checkpoint = _dict(payload.get("checkpoint_candidate"))
    lines = [
        "# G1 True-Newton Full-Load Checkpoint Candidate Status",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `evidence_closure_pass`: `{payload['evidence_closure_pass']}`",
        f"- `checkpoint_path`: `{checkpoint.get('path')}`",
        f"- `checkpoint_schema`: `{checkpoint.get('schema')}`",
        f"- `checkpoint_load_scale`: `{checkpoint.get('load_scale')}`",
        f"- `steps`: `{candidate.get('steps')}`",
        f"- `final_residual_n`: `{candidate.get('final_residual_n')}`",
        f"- `residual_gate_passed`: `{candidate.get('residual_gate_passed')}`",
    ]
    if payload["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{item}`" for item in payload["blockers"])
    lines.extend(["", "## Claim Boundary", "", payload["claim_boundary"], ""])
    return "\n".join(lines)


def write_g1_true_newton_full_load_checkpoint_candidate_status(
    *,
    repo_root: Path = ROOT,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT_NPZ,
    initial_checkpoint_npz: Path | None = DEFAULT_INITIAL_CHECKPOINT_NPZ,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
    load_scale: float = DEFAULT_LOAD_SCALE,
    max_newton_steps: int = DEFAULT_MAX_NEWTON_STEPS,
    residual_gate_n: float = DEFAULT_RESIDUAL_GATE_N,
    regularization_mode: str = DEFAULT_REGULARIZATION_MODE,
    regularization_mu: float = DEFAULT_REGULARIZATION_MU,
    allow_signed_direction_globalization: bool = False,
) -> dict[str, Any]:
    payload = build_g1_true_newton_full_load_checkpoint_candidate_status(
        repo_root=repo_root,
        checkpoint_npz=checkpoint_npz,
        initial_checkpoint_npz=initial_checkpoint_npz,
        load_scale=load_scale,
        max_newton_steps=max_newton_steps,
        residual_gate_n=residual_gate_n,
        regularization_mode=regularization_mode,
        regularization_mu=regularization_mu,
        allow_signed_direction_globalization=allow_signed_direction_globalization,
    )
    resolved_out = _resolve(repo_root, out)
    resolved_out_md = _resolve(repo_root, out_md)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_out_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_out_md.write_text(_markdown(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT_NPZ)
    parser.add_argument("--initial-checkpoint-npz", type=Path, default=DEFAULT_INITIAL_CHECKPOINT_NPZ)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--load-scale", type=float, default=DEFAULT_LOAD_SCALE)
    parser.add_argument("--max-newton-steps", type=int, default=DEFAULT_MAX_NEWTON_STEPS)
    parser.add_argument("--residual-gate-n", type=float, default=DEFAULT_RESIDUAL_GATE_N)
    parser.add_argument("--regularization-mode", default=DEFAULT_REGULARIZATION_MODE)
    parser.add_argument("--regularization-mu", type=float, default=DEFAULT_REGULARIZATION_MU)
    parser.add_argument("--allow-signed-direction-globalization", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_g1_true_newton_full_load_checkpoint_candidate_status(
        repo_root=args.repo_root,
        checkpoint_npz=args.checkpoint_npz,
        initial_checkpoint_npz=args.initial_checkpoint_npz,
        out=args.out,
        out_md=args.out_md,
        load_scale=args.load_scale,
        max_newton_steps=args.max_newton_steps,
        residual_gate_n=args.residual_gate_n,
        regularization_mode=args.regularization_mode,
        regularization_mu=args.regularization_mu,
        allow_signed_direction_globalization=args.allow_signed_direction_globalization,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
