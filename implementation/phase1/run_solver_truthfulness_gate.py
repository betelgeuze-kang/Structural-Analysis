#!/usr/bin/env python3
"""Aggregate top-level solver truthfulness evidence.

This gate does not pretend every top-level phase1 path is already a production
solver kernel. Instead, it makes the current state explicit:
- top-level training/eval/data paths must declare their runtime truthfully
- surrogate runtime markers must be absent
- CPU execution must be explicitly declared rather than hidden as fallback
- production-kernel proof still comes from the dedicated solver HIP contract
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from runtime_contracts import InputContractError, validate_input_contract

REASONS = {
    "PASS": "top-level solver truthfulness evidence is explicit and surrogate-free, with production-kernel proof delegated to solver HIP",
    "ERR_INVALID_INPUT": "invalid solver truthfulness gate input",
    "ERR_SOLVER_TRUTHFULNESS_FAIL": "one or more top-level reports do not declare truthful explicit runtime state",
    "ERR_SOLVER_HIP_E2E_FAIL": "solver HIP end-to-end contract is incomplete for production-kernel proof",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "winning_ticket_report",
        "physics_branching_report",
        "track_dataset_report",
        "tunnel_dataset_report",
        "solver_hip_report",
        "out",
    ],
    "properties": {
        "winning_ticket_report": {"type": "string", "minLength": 1},
        "physics_branching_report": {"type": "string", "minLength": 1},
        "track_dataset_report": {"type": "string", "minLength": 1},
        "tunnel_dataset_report": {"type": "string", "minLength": 1},
        "solver_hip_report": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _validate_top_level_runtime(label: str, payload: dict[str, Any]) -> dict[str, Any]:
    runtime = payload.get("runtime_truthfulness") if isinstance(payload.get("runtime_truthfulness"), dict) else {}
    surrogate_markers = [
        str(item).strip()
        for item in (runtime.get("surrogate_runtime_markers") or [])
        if str(item).strip()
    ]
    cpu_backend = bool(runtime.get("cpu_backend", False))
    execution_backend = str(
        runtime.get("execution_backend", "cpu" if cpu_backend else "gpu") or ""
    ).strip().lower()
    cpu_required = bool(runtime.get("cpu_required", cpu_backend))
    cpu_fallback_used = bool(runtime.get("cpu_fallback_used", False))
    metadata_present = bool(runtime)
    runtime_kind = str(runtime.get("solver_path_kind", runtime.get("runtime_kind", "")) or "").strip()
    physical_runtime_declared = bool(
        runtime.get("physical_runtime_declared", False) or runtime_kind
    )
    reduced_order_runtime_declared = bool(
        runtime.get("reduced_order_physical_runtime_used", False)
        or ("explicit" in runtime_kind.lower() if runtime_kind else False)
    )
    production_seeded_runtime_used = bool(runtime.get("production_seeded_runtime_used", False))
    runtime_policy_satisfied = bool(runtime.get("runtime_policy_satisfied", metadata_present))
    kernel_consistent = bool(
        runtime.get("force_jacobian_kernel_consistent", False)
        or runtime.get("force_balance_residual_consistent", False)
        or ("explicit" in runtime_kind.lower() if runtime_kind else False)
    )
    surrogate_free = bool(
        not bool(runtime.get("surrogate_runtime_used", False))
        and not bool(runtime.get("simplified_runtime_used", False))
        and not surrogate_markers
    )
    declaration_consistent = bool(
        execution_backend in {"cpu", "gpu"}
        and str(runtime.get("runtime_backend", "") or "").strip() != ""
        and cpu_backend == (execution_backend == "cpu")
        and cpu_required == (execution_backend == "cpu")
        and not cpu_fallback_used
        and physical_runtime_declared
        and kernel_consistent
        and bool(runtime.get("contract_pass", payload.get("contract_pass", metadata_present)))
        and runtime_policy_satisfied
    )
    contract_pass = bool(metadata_present and surrogate_free and declaration_consistent)
    return {
        "label": label,
        "run_id": str(payload.get("run_id", "") or ""),
        "runtime_backend": str(runtime.get("runtime_backend", "") or ""),
        "execution_backend": execution_backend,
        "solver_path_kind": runtime_kind,
        "production_kernel_path": bool(runtime.get("production_kernel_path", False)),
        "reduced_order_physical_runtime_used": reduced_order_runtime_declared,
        "production_seeded_runtime_used": production_seeded_runtime_used,
        "metadata_present": metadata_present,
        "physical_runtime_declared": physical_runtime_declared,
        "kernel_consistent": kernel_consistent,
        "surrogate_free": surrogate_free,
        "cpu_declared_consistent": declaration_consistent,
        "runtime_policy_satisfied": runtime_policy_satisfied,
        "cpu_fallback_used": cpu_fallback_used,
        "surrogate_runtime_markers": surrogate_markers,
        "contract_pass": contract_pass,
    }


def _validate_solver_hip(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    solver_count = int(summary.get("solver_count", 0) or 0)
    production_count = int(summary.get("production_kernel_solver_count", 0) or 0)
    surrogate_free_count = int(summary.get("surrogate_runtime_free_solver_count", 0) or 0)
    force_jacobian_count = int(summary.get("force_jacobian_consistent_solver_count", 0) or 0)
    contract_pass = bool(
        payload.get("contract_pass", False)
        and bool(checks.get("strict_probe_pass", False))
        and bool(checks.get("all_main_loops_gpu_pass", False))
        and bool(checks.get("all_production_kernel_pass", False))
        and bool(checks.get("no_surrogate_runtime_markers_pass", False))
        and bool(checks.get("no_cpu_backend_pass", False))
        and bool(checks.get("no_cpu_required_pass", False))
        and bool(checks.get("no_cpu_fallback_pass", False))
        and solver_count > 0
        and production_count == solver_count
        and surrogate_free_count == solver_count
        and force_jacobian_count == solver_count
    )
    return {
        "solver_count": solver_count,
        "production_kernel_solver_count": production_count,
        "surrogate_runtime_free_solver_count": surrogate_free_count,
        "force_jacobian_consistent_solver_count": force_jacobian_count,
        "hazard_family_count": int(summary.get("hazard_family_count", 0) or 0),
        "topology_family_count": int(summary.get("topology_family_count", 0) or 0),
        "load_path_family_count": int(summary.get("load_path_family_count", 0) or 0),
        "summary_line": str(payload.get("summary_line", "") or ""),
        "contract_pass": contract_pass,
    }


def run_solver_truthfulness_gate(
    *,
    winning_ticket_report: dict[str, Any],
    physics_branching_report: dict[str, Any],
    track_dataset_report: dict[str, Any],
    tunnel_dataset_report: dict[str, Any],
    solver_hip_report: dict[str, Any],
) -> dict[str, Any]:
    top_level_rows = [
        _validate_top_level_runtime("winning_ticket_backprop", winning_ticket_report),
        _validate_top_level_runtime("physics_guided_branching", physics_branching_report),
        _validate_top_level_runtime("track_dynamics_dataset", track_dataset_report),
        _validate_top_level_runtime("tunnel_dynamics_dataset", tunnel_dataset_report),
    ]
    solver_hip = _validate_solver_hip(solver_hip_report)

    top_level_count = len(top_level_rows)
    metadata_count = sum(1 for row in top_level_rows if row["metadata_present"])
    surrogate_free_count = sum(1 for row in top_level_rows if row["surrogate_free"])
    explicit_declared_count = sum(1 for row in top_level_rows if row["physical_runtime_declared"])
    cpu_declared_count = sum(1 for row in top_level_rows if row["cpu_declared_consistent"])
    reduced_order_count = sum(1 for row in top_level_rows if row["reduced_order_physical_runtime_used"])
    production_seeded_count = sum(1 for row in top_level_rows if row["production_seeded_runtime_used"])
    kernel_consistent_count = sum(1 for row in top_level_rows if row["kernel_consistent"])
    runtime_policy_count = sum(1 for row in top_level_rows if row["runtime_policy_satisfied"])

    checks = {
        "top_level_metadata_present_pass": metadata_count == top_level_count,
        "top_level_surrogate_free_pass": surrogate_free_count == top_level_count,
        "top_level_explicit_runtime_declared_pass": explicit_declared_count == top_level_count,
        "top_level_cpu_declared_consistent_pass": cpu_declared_count == top_level_count,
        "top_level_reduced_order_runtime_declared_pass": reduced_order_count == top_level_count,
        "top_level_runtime_policy_pass": runtime_policy_count == top_level_count,
        "top_level_kernel_consistency_pass": kernel_consistent_count == top_level_count,
        "solver_hip_production_proof_pass": bool(solver_hip["contract_pass"]),
    }
    compatibility_checks = {
        "runtime_truthfulness_pass": bool(
            checks["top_level_metadata_present_pass"]
            and checks["top_level_explicit_runtime_declared_pass"]
            and checks["top_level_cpu_declared_consistent_pass"]
            and checks["top_level_reduced_order_runtime_declared_pass"]
            and checks["top_level_runtime_policy_pass"]
            and checks["top_level_kernel_consistency_pass"]
        ),
        "no_surrogate_runtime_markers_pass": checks["top_level_surrogate_free_pass"],
        "no_cpu_fallback_pass": checks["top_level_cpu_declared_consistent_pass"],
    }
    checks.update(compatibility_checks)

    if not checks["runtime_truthfulness_pass"] or not checks["no_surrogate_runtime_markers_pass"]:
        reason_code = "ERR_SOLVER_TRUTHFULNESS_FAIL"
    elif not checks["solver_hip_production_proof_pass"]:
        reason_code = "ERR_SOLVER_HIP_E2E_FAIL"
    else:
        reason_code = "PASS"

    contract_pass = reason_code == "PASS"
    summary_line = (
        f"Solver truthfulness: {'PASS' if contract_pass else 'GAP'} | "
        f"reports={metadata_count}/{top_level_count} | "
        f"explicit={explicit_declared_count}/{top_level_count} | "
        f"production_seeded={production_seeded_count}/{top_level_count} | "
        f"surrogate_free={surrogate_free_count}/{top_level_count} | "
        f"cpu_fallback={sum(1 for row in top_level_rows if row['cpu_fallback_used'])}/{top_level_count} | "
        f"solver_hip_variants={solver_hip['production_kernel_solver_count']}/{solver_hip['solver_count']} | "
        f"hazards={solver_hip['hazard_family_count']} | topologies={solver_hip['topology_family_count']} | load_paths={solver_hip['load_path_family_count']}"
    )

    return {
        "schema_version": "1.0",
        "run_id": "solver-truthfulness-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "summary": {
            "top_level_count": top_level_count,
            "top_level_metadata_present_count": metadata_count,
            "top_level_surrogate_free_count": surrogate_free_count,
            "top_level_explicit_runtime_declared_count": explicit_declared_count,
            "top_level_cpu_declared_consistent_count": cpu_declared_count,
            "top_level_reduced_order_runtime_declared_count": reduced_order_count,
            "top_level_production_seeded_runtime_count": production_seeded_count,
            "top_level_runtime_policy_satisfied_count": runtime_policy_count,
            "top_level_kernel_consistency_count": kernel_consistent_count,
            "solver_hip_solver_count": solver_hip["solver_count"],
            "solver_hip_production_kernel_solver_count": solver_hip["production_kernel_solver_count"],
            "solver_hip_surrogate_runtime_free_solver_count": solver_hip["surrogate_runtime_free_solver_count"],
            "solver_hip_force_jacobian_consistent_solver_count": solver_hip["force_jacobian_consistent_solver_count"],
            "solver_hip_hazard_family_count": solver_hip["hazard_family_count"],
            "solver_hip_topology_family_count": solver_hip["topology_family_count"],
            "solver_hip_load_path_family_count": solver_hip["load_path_family_count"],
            "runtime_report_count": top_level_count,
            "truthful_runtime_count": sum(1 for row in top_level_rows if row["contract_pass"]),
            "surrogate_marker_count": sum(len(row["surrogate_runtime_markers"]) for row in top_level_rows),
            "cpu_fallback_count": sum(1 for row in top_level_rows if row["cpu_fallback_used"]),
        },
        "top_level_rows": top_level_rows,
        "solver_hip": solver_hip,
        "summary_line": summary_line,
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--winning-ticket-report",
        "--winning-ticket-backprop-report",
        dest="winning_ticket_report",
        default="implementation/phase1/winning_ticket_backprop_report.json",
    )
    parser.add_argument(
        "--physics-branching-report",
        dest="physics_branching_report",
        default="implementation/phase1/physics_branching_report.json",
    )
    parser.add_argument(
        "--track-dataset-report",
        "--track-dynamics-dataset-report",
        dest="track_dataset_report",
        default="implementation/phase1/track_dynamics_dataset_report.json",
    )
    parser.add_argument(
        "--tunnel-dataset-report",
        "--tunnel-dynamics-dataset-report",
        dest="tunnel_dataset_report",
        default="implementation/phase1/tunnel_dynamics_dataset_report.json",
    )
    parser.add_argument("--solver-hip-report", default="implementation/phase1/solver_hip_e2e_contract_report.json")
    parser.add_argument("--out", default="implementation/phase1/solver_truthfulness_gate_report.json")
    args = parser.parse_args()

    input_payload = {
        "winning_ticket_report": str(args.winning_ticket_report),
        "physics_branching_report": str(args.physics_branching_report),
        "track_dataset_report": str(args.track_dataset_report),
        "tunnel_dataset_report": str(args.tunnel_dataset_report),
        "solver_hip_report": str(args.solver_hip_report),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_solver_truthfulness_gate")
    except InputContractError as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "solver-truthfulness-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        raise SystemExit(1)

    report = run_solver_truthfulness_gate(
        winning_ticket_report=_load_json(Path(args.winning_ticket_report)),
        physics_branching_report=_load_json(Path(args.physics_branching_report)),
        track_dataset_report=_load_json(Path(args.track_dataset_report)),
        tunnel_dataset_report=_load_json(Path(args.tunnel_dataset_report)),
        solver_hip_report=_load_json(Path(args.solver_hip_report)),
    )
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote solver truthfulness gate report: {out}")
    if not report.get("contract_pass", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
