#!/usr/bin/env python3
"""Build a non-promoting G1 assembly contract seed report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from release_evidence_metadata import git_head, input_checksums  # noqa: E402
from structural_analysis import ANALYSIS_ENGINE_VERSION, CLAIM_BOUNDARY_VERSION  # noqa: E402
from structural_analysis.assembly.coupled_static import (  # noqa: E402
    assemble_frame_shell_material_coupled_state,
    default_frame_shell_material_coupled_problem,
    solve_frame_shell_material_coupled,
)
from structural_analysis.assembly.g1_contract import (  # noqa: E402
    G1_ASSEMBLY_CONTRACT_SCHEMA,
    PROHIBITED_RESIDUAL_SUBSTITUTES,
    assemble_g1_state,
    direct_residual_newton_parity_check,
    finite_difference_g1_jvp_check,
)
from structural_analysis.assembly.nonlinear_static import (  # noqa: E402
    assemble_axial_chain_state,
    default_phase2_axial_chain_mesh_problem,
    solve_axial_chain_mesh,
)
from structural_analysis.solvers.nonlinear.newton import (  # noqa: E402
    GLOBALIZATION,
    RESIDUAL_FORMULA,
    NewtonRaphsonConfig,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "g1_assembly_contract_seed_report.json"
SCHEMA_VERSION = "g1-assembly-contract-seed-report.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value)
            for key, value in payload.items()
            if key not in {"generated_at"}
        }
    if isinstance(payload, list):
        return [_strip_volatile(item) for item in payload]
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _case_payload(
    *,
    case_id: str,
    assembly_scope: str,
    solution: Any,
    assembly_result: Any,
    jvp_check: dict[str, Any],
    newton_parity_check: dict[str, Any],
) -> dict[str, Any]:
    contract_check = assembly_result.contract_check()
    contract_pass = (
        solution.status == "ready"
        and bool(solution.metrics.get("contract_pass"))
        and bool(contract_check["contract_pass"])
        and bool(jvp_check["pass"])
        and bool(newton_parity_check["cpu_seed_consistent_newton_gate_passed"])
        and solution.metrics.get("regularization_used") is False
        and solution.metrics.get("fallback_used") is False
        and assembly_result.metrics.get("g1_closure_claim") is False
    )
    return {
        "case_id": case_id,
        "assembly_scope": assembly_scope,
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "solution_status": solution.status,
        "solution_contract_pass": bool(solution.metrics.get("contract_pass")),
        "regularization_used": solution.metrics.get("regularization_used"),
        "fallback_used": solution.metrics.get("fallback_used"),
        "assembly_result": assembly_result.to_payload(),
        "assembly_contract_check": contract_check,
        "jvp_finite_difference_check": jvp_check,
        "direct_residual_newton_parity_check": newton_parity_check,
        "g1_closure_claim": False,
    }


def build_g1_assembly_contract_seed_report(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    config = NewtonRaphsonConfig(
        residual_tolerance=1.0e-10,
        increment_tolerance=1.0e-12,
        max_iterations=25,
    )

    axial_problem = default_phase2_axial_chain_mesh_problem()
    axial_solution, axial_state = solve_axial_chain_mesh(axial_problem, config=config)
    axial_assembly = assemble_g1_state(axial_problem, axial_state)
    axial_jvp = finite_difference_g1_jvp_check(
        lambda free_u: assemble_g1_state(
            axial_problem,
            assemble_axial_chain_state(axial_problem, free_u),
        ),
        axial_solution.free_displacements_m,
    )
    axial_newton_parity = direct_residual_newton_parity_check(
        lambda free_u: assemble_g1_state(
            axial_problem,
            assemble_axial_chain_state(axial_problem, free_u),
        ),
        axial_solution,
    )
    axial_case = _case_payload(
        case_id=axial_problem.case_id,
        assembly_scope="narrow_axial_chain_seed",
        solution=axial_solution,
        assembly_result=axial_assembly,
        jvp_check=axial_jvp,
        newton_parity_check=axial_newton_parity,
    )

    coupled_problem = default_frame_shell_material_coupled_problem()
    coupled_solution, coupled_state = solve_frame_shell_material_coupled(
        coupled_problem,
        config=config,
    )
    coupled_assembly = assemble_g1_state(coupled_problem, coupled_state)
    coupled_jvp = finite_difference_g1_jvp_check(
        lambda free_u: assemble_g1_state(
            coupled_problem,
            assemble_frame_shell_material_coupled_state(coupled_problem, free_u),
        ),
        coupled_solution.free_displacements_m,
    )
    coupled_newton_parity = direct_residual_newton_parity_check(
        lambda free_u: assemble_g1_state(
            coupled_problem,
            assemble_frame_shell_material_coupled_state(coupled_problem, free_u),
        ),
        coupled_solution,
    )
    coupled_case = _case_payload(
        case_id=coupled_problem.case_id,
        assembly_scope="frame_shell_material_coupled_2dof_seed",
        solution=coupled_solution,
        assembly_result=coupled_assembly,
        jvp_check=coupled_jvp,
        newton_parity_check=coupled_newton_parity,
    )

    cases = [axial_case, coupled_case]
    contract_pass = all(row["contract_pass"] for row in cases)
    cpu_seed_newton_gate_passed = all(
        row["direct_residual_newton_parity_check"][
            "cpu_seed_consistent_newton_gate_passed"
        ]
        for row in cases
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/assembly/g1_contract.py"),
                Path("src/structural_analysis/assembly/nonlinear_static.py"),
                Path("src/structural_analysis/assembly/coupled_static.py"),
                Path("src/structural_analysis/solvers/nonlinear/newton.py"),
                Path("scripts/build_g1_assembly_contract_seed_report.py"),
                Path("tests/test_g1_assembly_contract.py"),
            ],
            repo_root=repo_root,
        ),
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "promotes_g1_closure": False,
        "g1_closure_claim": False,
        "phase_covered": "phase1_phase2_cpu_seed_contract_and_newton_parity",
        "assembly_contract_schema": G1_ASSEMBLY_CONTRACT_SCHEMA,
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "required_fields": [
            "residual_free",
            "tangent_free",
            "internal_forces",
            "external_forces",
            "material_state_next",
            "metrics",
        ],
        "prohibited_physical_residual_substitutes": list(
            PROHIBITED_RESIDUAL_SUBSTITUTES
        ),
        "fixed_point_residual_promoted_to_physical": False,
        "regularized_fixed_point_substitute": False,
        "cpu_seed_consistent_newton_gate_passed": cpu_seed_newton_gate_passed,
        "consistent_residual_jacobian_newton_gate_passed": False,
        "case_count": len(cases),
        "cases": cases,
        "blockers_remaining": [
            "full_load_gate_not_closed",
            "full_mesh_nonlinear_equilibrium_not_closed",
            "material_newton_breadth_not_closed",
            "production_rocm_hip_residency_not_closed",
            "g1_consistent_residual_jacobian_newton_gate_not_closed_by_cpu_seed",
            "full_load_checkpoint_1p0_not_created_by_this_seed_report",
            "hip_residual_jvp_worker_not_executed_by_this_seed_report",
        ],
        "artifacts": {
            "report": str(out),
            "related_runner_contract": str(
                PRODUCTIZATION / "g1_consistent_newton_full_load_checkpoint_candidate_runner.json"
            ),
            "related_full_load_lane": str(
                PRODUCTIZATION / "g1_full_load_hip_newton_lane_report.json"
            ),
        },
        "claim_boundary": (
            "This report validates the shared AssemblyResult shape, physical "
            "R=F_internal-F_external convention, and central-difference JVP guard "
            "on two deterministic CPU seed assemblies. It also replays each seed "
            "Newton history through the same physical assembly to verify direct "
            "residual/Newton residual parity and residual descent. It does not "
            "create a full-load 1.0 checkpoint, prove full-mesh nonlinear "
            "equilibrium, close state-updated material Newton breadth, execute "
            "ROCm/HIP, or promote G1."
        ),
    }
    return payload


def check_g1_assembly_contract_seed_report(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
) -> tuple[bool, str]:
    expected = build_g1_assembly_contract_seed_report(repo_root=repo_root, out=out)
    resolved = out if out.is_absolute() else repo_root / out
    if not resolved.exists():
        return False, f"g1_assembly_contract_seed_report_missing:{out.as_posix()}"
    try:
        existing = _read_json(resolved)
    except Exception as exc:
        return False, (
            f"g1_assembly_contract_seed_report_unreadable:{out.as_posix()}:"
            f"{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "g1_assembly_contract_seed_report_mismatch"
    return True, "g1_assembly_contract_seed_report_consistent"


def write_g1_assembly_contract_seed_report(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_g1_assembly_contract_seed_report(repo_root=repo_root, out=out)
    resolved = out if out.is_absolute() else repo_root / out
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_g1_assembly_contract_seed_report(out=args.out)
        print(f"G1 assembly contract seed report check: {message}")
        return 0 if ok else 1
    payload = write_g1_assembly_contract_seed_report(out=args.out)
    print(
        "G1 assembly contract seed report: "
        f"{payload['status']} | cases={payload['case_count']} | "
        f"promotes_g1={payload['promotes_g1_closure']}"
    )
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
