#!/usr/bin/env python3
"""Cross-check the G1 direct-residual terminal residual and increment gates."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


SCHEMA_VERSION = "mgt-g1-direct-residual-terminal-gate-report.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_DIRECT_REPLAY = PRODUCTIZATION / "mgt_direct_residual_attached_policy_followup365_gate_replay_probe.json"
DEFAULT_TERMINAL_EQUILIBRIUM = (
    PRODUCTIZATION / "mgt_equilibrium_newton_focused_followup375_structural_terminal_increment_gate_probe.json"
)
DEFAULT_GATE_SUMMARY = PRODUCTIZATION / "mgt_g1_followup362_365_attached_equilibrium_newton_gate_summary.json"
DEFAULT_OUT = PRODUCTIZATION / "mgt_g1_direct_residual_terminal_gate_report.json"
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _input_checksums(paths: list[Path]) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in paths:
        checksums[str(path)] = _sha256(path) if path.exists() else "missing"
    return checksums


def _load_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_iteration(payload: dict[str, Any]) -> dict[str, Any]:
    iterations = _as_list(payload.get("newton_iterations"))
    first = iterations[0] if iterations and isinstance(iterations[0], dict) else {}
    return first


def _first_float(*values: Any) -> float | None:
    for value in values:
        parsed = _float_or_none(value)
        if parsed is not None:
            return parsed
    return None


def build_report(
    *,
    direct_replay_path: Path = DEFAULT_DIRECT_REPLAY,
    terminal_equilibrium_path: Path = DEFAULT_TERMINAL_EQUILIBRIUM,
    gate_summary_path: Path = DEFAULT_GATE_SUMMARY,
) -> dict[str, Any]:
    direct_replay = _load_json_dict(direct_replay_path)
    terminal_equilibrium = _load_json_dict(terminal_equilibrium_path)
    gate_summary = _load_json_dict(gate_summary_path)

    final_direct = _as_dict(direct_replay.get("final_direct_residual"))
    direct_gate = _as_dict(direct_replay.get("gate_assessment"))
    direct_base = _as_dict(direct_replay.get("base_direct_residual"))
    direct_checkpoint = _as_dict(direct_replay.get("checkpoint"))
    first_terminal_iteration = _first_iteration(terminal_equilibrium)
    summary_replay = _as_dict(gate_summary.get("direct_residual_gate_replay"))
    summary_assessment = _as_dict(summary_replay.get("gate_assessment"))

    final_direct_residual = _float_or_none(final_direct.get("direct_residual_inf_n"))
    terminal_final_residual = _float_or_none(terminal_equilibrium.get("final_residual_inf_n"))
    summary_latest_residual = _float_or_none(gate_summary.get("latest_direct_residual_inf_n"))
    direct_tolerance = _float_or_none(direct_gate.get("residual_tolerance_n"))
    terminal_tolerance = _float_or_none(terminal_equilibrium.get("residual_tolerance_n"))
    residual_tolerances = [
        value for value in (direct_tolerance, terminal_tolerance) if value is not None
    ]
    strict_residual_tolerance = min(residual_tolerances) if residual_tolerances else None
    increment_tolerance = _float_or_none(direct_gate.get("relative_increment_tolerance"))
    terminal_relative_increment = _float_or_none(first_terminal_iteration.get("relative_increment"))
    residual_match_abs_tol = 1.0e-12
    full_load_tolerance = 1.0e-12
    terminal_load_scale = _first_float(
        direct_gate.get("load_scale_at_closure"),
        direct_gate.get("observed_load_scale"),
        _as_dict(direct_gate.get("full_load_closure_gate")).get("observed_load_scale"),
        direct_base.get("load_scale"),
        direct_checkpoint.get("load_scale"),
        gate_summary.get("load_scale"),
    )

    checks = {
        "direct_replay_present": bool(direct_replay),
        "terminal_equilibrium_present": bool(terminal_equilibrium),
        "gate_summary_present": bool(gate_summary),
        "direct_replay_schema_pass": direct_replay.get("schema_version") == "mgt-direct-residual-newton-probe.v1",
        "terminal_equilibrium_schema_pass": (
            terminal_equilibrium.get("schema_version") == "mgt-equilibrium-newton-focused-probe.v1"
        ),
        "gate_summary_schema_pass": (
            gate_summary.get("schema_version")
            == "mgt-g1-followup362-365-attached-equilibrium-newton-gate-summary.v1"
        ),
        "direct_replay_residual_gate_passed": bool(direct_gate.get("direct_residual_gate_passed")),
        "direct_replay_not_promoted_without_increment": (
            direct_replay.get("direct_residual_newton_ready") is False
            and "relative_increment_gate_not_closed_or_not_verified"
            in _as_list(direct_replay.get("blockers"))
        ),
        "terminal_equilibrium_ready": (
            terminal_equilibrium.get("status") == "ready"
            and terminal_equilibrium.get("equilibrium_newton_ready") is True
            and _as_list(terminal_equilibrium.get("blockers")) == []
        ),
        "terminal_increment_gate_passed": (
            terminal_relative_increment is not None
            and increment_tolerance is not None
            and terminal_relative_increment <= increment_tolerance
            and first_terminal_iteration.get("stop_reason")
            == "residual_gate_stationary_no_descent_increment_gate_met"
        ),
        "summary_direct_residual_gate_passed": bool(gate_summary.get("direct_residual_gate_passed")),
        "summary_keeps_full_g1_partial": gate_summary.get("status") == "partial",
        "summary_increment_gap_matches_replay": (
            summary_assessment.get("relative_increment_gate_verified") is False
        ),
    }
    checks["residuals_match"] = bool(
        final_direct_residual is not None
        and terminal_final_residual is not None
        and summary_latest_residual is not None
        and abs(final_direct_residual - terminal_final_residual) <= residual_match_abs_tol
        and abs(final_direct_residual - summary_latest_residual) <= residual_match_abs_tol
    )
    checks["strict_residual_gate_passed"] = bool(
        final_direct_residual is not None
        and strict_residual_tolerance is not None
        and final_direct_residual <= strict_residual_tolerance
    )
    blockers = [name for name, passed in checks.items() if not passed]
    ready = not blockers
    full_load_gate_passed = bool(
        terminal_load_scale is not None and terminal_load_scale >= 1.0 - full_load_tolerance
    )
    full_g1_closure_blockers = [
        *(["full_load_gate_not_closed"] if not full_load_gate_passed else []),
        "full_mesh_nonlinear_equilibrium_not_closed",
        "material_newton_breadth_not_closed",
        "production_rocm_hip_residency_not_closed",
    ]
    full_g1_closure_ready = bool(ready and not full_g1_closure_blockers)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "input_checksums": _input_checksums(
            [direct_replay_path, terminal_equilibrium_path, gate_summary_path]
        ),
        "reused_evidence": True,
        "reuse_policy": "status_rebuilt_from_existing_g1_terminal_gate_receipts",
        "status": "ready" if ready else "partial",
        "contract_pass": ready,
        "direct_residual_terminal_gate_ready": ready,
        "direct_residual_newton_gate_ready": ready,
        "full_g1_closure_ready": full_g1_closure_ready,
        "full_g1_closure_blockers": full_g1_closure_blockers,
        "reason_code": "PASS" if ready else "ERR_G1_DIRECT_RESIDUAL_TERMINAL_GATE_BLOCKED",
        "summary_line": (
            "G1 direct residual terminal gate: "
            f"{'PASS' if ready else 'BLOCKED'} | "
            f"direct_residual={final_direct_residual} | "
            f"increment={terminal_relative_increment}"
        ),
        "checks": checks,
        "full_g1_closure_checks": {
            "terminal_checkpoint_gate_ready": ready,
            "full_load_gate_passed": full_load_gate_passed,
            "full_mesh_nonlinear_equilibrium_closed": False,
            "material_newton_breadth_closed": False,
            "production_rocm_hip_residency_closed": False,
        },
        "blockers": blockers,
        "thresholds": {
            "direct_residual_replay_tolerance_n": direct_tolerance,
            "terminal_equilibrium_tolerance_n": terminal_tolerance,
            "strict_residual_tolerance_n": strict_residual_tolerance,
            "relative_increment_tolerance": increment_tolerance,
            "residual_match_abs_tolerance_n": residual_match_abs_tol,
            "full_load_tolerance": full_load_tolerance,
        },
        "measurements": {
            "direct_replay_final_residual_inf_n": final_direct_residual,
            "terminal_equilibrium_final_residual_inf_n": terminal_final_residual,
            "summary_latest_direct_residual_inf_n": summary_latest_residual,
            "terminal_relative_increment": terminal_relative_increment,
            "terminal_load_scale": terminal_load_scale,
            "terminal_stop_reason": first_terminal_iteration.get("stop_reason"),
        },
        "artifacts": {
            "direct_replay": str(direct_replay_path),
            "terminal_equilibrium": str(terminal_equilibrium_path),
            "gate_summary": str(gate_summary_path),
        },
        "claim_boundary": (
            "This report closes only the G1 attached-policy terminal direct-residual residual+increment "
            "gate at the retained 0.656 checkpoint by cross-checking the direct residual replay against "
            "the terminal equilibrium Newton increment-gate receipt. It does not close full-mesh/full-load "
            "3D nonlinear equilibrium, production ROCm/HIP residency, material Newton breadth, or full G1."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--direct-replay", type=Path, default=DEFAULT_DIRECT_REPLAY)
    parser.add_argument("--terminal-equilibrium", type=Path, default=DEFAULT_TERMINAL_EQUILIBRIUM)
    parser.add_argument("--gate-summary", type=Path, default=DEFAULT_GATE_SUMMARY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(
        direct_replay_path=args.direct_replay,
        terminal_equilibrium_path=args.terminal_equilibrium,
        gate_summary_path=args.gate_summary,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and not payload["direct_residual_terminal_gate_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
