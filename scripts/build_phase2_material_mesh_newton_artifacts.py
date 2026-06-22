#!/usr/bin/env python3
"""Build Phase 2 material-mesh Newton assembly seed artifacts for a 1D axial chain."""

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
from structural_analysis.assembly.nonlinear_static import (  # noqa: E402
    default_phase2_axial_chain_mesh_problem,
    finite_difference_assembled_jacobian_check,
    mesh_problem_with_scaled_external_load,
    mesh_series_force_equilibrium_check,
    refined_strain_cubic_axial_chain_mesh_problem,
    solve_axial_chain_mesh,
)
from structural_analysis.solvers.nonlinear.newton import (  # noqa: E402
    GLOBALIZATION,
    RESIDUAL_FORMULA,
    VECTOR_MATRIX_BACKEND,
    VECTOR_SPARSE_MATRIX_BACKEND,
    NewtonRaphsonConfig,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_MESH_OUT = PRODUCTIZATION / "phase2_material_mesh_newton_axial_chain_result.json"
DEFAULT_SUMMARY_OUT = PRODUCTIZATION / "phase2_material_mesh_newton_summary.json"
SCHEMA_VERSION = "phase2-material-mesh-newton-artifacts.v1"
DISPLACEMENT_TOLERANCE_M = 1.0e-10
LOAD_STEP_FACTORS = (0.5, 1.0)
MESH_REFINEMENT_ELEMENT_COUNTS = (1, 2, 4)
MESH_REFINEMENT_TOLERANCE_M = 1.0e-10


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _material_law_payload(material: Any) -> dict[str, Any]:
    payload = {
        "model_kind": material.model_kind,
    }
    for key in (
        "linear_stiffness_kn_per_m",
        "cubic_stiffness_kn_per_m3",
        "linear_strain_stiffness_kn",
        "cubic_strain_stiffness_kn",
        "length_m",
    ):
        if hasattr(material, key):
            payload[key] = getattr(material, key)
    return payload


def _mesh_problem_payload(problem: Any) -> dict[str, Any]:
    material = problem.elements[0].material
    return {
        "case_id": problem.case_id,
        "truth_class": "assembled_mesh_truth",
        "model_kind": material.model_kind,
        "units": {"length": "m", "force": "kN"},
        "node_count": problem.node_count,
        "element_count": len(problem.elements),
        "fixed_nodes": list(problem.fixed_nodes),
        "external_forces_kn": [
            {"node_index": node_index, "force_kn": force_kn}
            for node_index, force_kn in problem.external_forces_kn
        ],
        "elements": [
            {
                "element_id": element.element_id,
                "node_i": element.node_i,
                "node_j": element.node_j,
                "length_m": element.length_m,
            }
            for element in problem.elements
        ],
        "material_law": _material_law_payload(material),
        "residual_contract": RESIDUAL_FORMULA,
        "claim_boundary": (
            "Deterministic 1D axial chain mesh assembly only. "
            "Not a full frame, shell, sparse production, or GPU/HIP solver."
        ),
    }


def _assembly_payload(state: Any) -> dict[str, Any]:
    return {
        "residual_formula": state.residual_formula,
        "free_node_indices": list(state.free_node_indices),
        "displacements_m": state.displacements_m.tolist(),
        "residual_kn": state.residual_kn.tolist(),
        "jacobian_kn_per_m": state.jacobian_kn_per_m.tolist(),
        "internal_forces_kn": state.internal_forces_kn.tolist(),
        "external_forces_kn": state.external_forces_kn.tolist(),
        "reactions_kn": state.reactions_kn.tolist(),
        "element_forces_kn": list(state.element_forces_kn),
    }


def _solution_payload(solution: Any, final_state: Any) -> dict[str, Any]:
    metrics = solution.metrics
    return {
        "schema_version": "phase2-material-mesh-newton-axial-chain-result.v1",
        "status": solution.status,
        "contract_pass": bool(metrics.get("contract_pass")),
        "case_id": solution.problem.case_id,
        "truth_class": "assembled_mesh_truth",
        "model_kind": "scalar_nonlinear_axial_cubic_spring",
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "tangent_definition": metrics.get("tangent_definition"),
        "globalization": GLOBALIZATION,
        "matrix_backend": metrics.get("matrix_backend"),
        "sparse_backend_used": metrics.get("sparse_backend_used"),
        "metrics": metrics,
        "assembly": _assembly_payload(final_state),
        "convergence_history": solution.convergence_history,
        "line_search_history": solution.line_search_history,
        "unsupported_features": solution.unsupported_features,
        "warnings": solution.warnings,
        "regularization_used": metrics.get("regularization_used"),
        "fallback_used": metrics.get("fallback_used"),
        "g1_closure_claim": False,
        "material_newton_closure_claim": False,
        "full_mesh_closure_claim": False,
        "claim_boundary": (
            "This records one tiny 1D axial mesh where scalar material laws are "
            "assembled into global residual/Jacobian and solved with Newton "
            "residual/increment gates without regularization or fallback false PASS. "
            "It does not close G1 full-mesh/full-load nonlinear equilibrium, general "
            "frame/shell/material coupling, sparse production matrix backends, broad "
            "material Newton breadth, or GPU/HIP parity."
        ),
    }


def _run_mesh_load_step_partition(
    base_problem: Any,
    *,
    config: NewtonRaphsonConfig,
    step_factors: tuple[float, ...],
) -> dict[str, Any]:
    displacements = tuple(base_problem.initial_displacements_m)
    steps: list[dict[str, Any]] = []
    for step_index, load_factor in enumerate(step_factors, start=1):
        step_problem = mesh_problem_with_scaled_external_load(
            base_problem,
            load_factor=load_factor,
            initial_displacements_m=displacements,
        )
        solution, final_state = solve_axial_chain_mesh(step_problem, config=config)
        metrics = solution.metrics
        tip_node = max(node_index for node_index, _ in base_problem.external_forces_kn)
        tip_displacement_m = float(final_state.displacements_m[tip_node])
        steps.append(
            {
                "step_index": step_index,
                "load_factor": load_factor,
                "status": solution.status,
                "contract_pass": bool(metrics.get("contract_pass")),
                "residual_gate_passed": bool(metrics.get("residual_gate_passed")),
                "increment_gate_passed": bool(metrics.get("increment_gate_passed")),
                "tip_displacement_m": tip_displacement_m,
                "iteration_count": int(metrics.get("iteration_count", 0)),
                "regularization_used": metrics.get("regularization_used"),
                "fallback_used": metrics.get("fallback_used"),
            }
        )
        displacements = tuple(final_state.displacements_m.tolist())
    return {
        "step_factors": list(step_factors),
        "steps": steps,
        "final_tip_displacement_m": steps[-1]["tip_displacement_m"],
    }


def _run_mesh_refinement_suite(*, config: NewtonRaphsonConfig) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for element_count in MESH_REFINEMENT_ELEMENT_COUNTS:
        problem = refined_strain_cubic_axial_chain_mesh_problem(
            element_count=element_count,
        )
        solution, final_state = solve_axial_chain_mesh(problem, config=config)
        metrics = solution.metrics
        tip_node = max(node_index for node_index, _ in problem.external_forces_kn)
        tip_displacement_m = float(final_state.displacements_m[tip_node])
        jacobian_check = finite_difference_assembled_jacobian_check(
            problem,
            solution.free_displacements_m,
        )
        series_check = mesh_series_force_equilibrium_check(final_state)
        rows.append(
            {
                "case_id": problem.case_id,
                "node_count": problem.node_count,
                "element_count": len(problem.elements),
                "total_length_m": sum(element.length_m for element in problem.elements),
                "status": solution.status,
                "contract_pass": bool(metrics.get("contract_pass")),
                "residual_gate_passed": bool(metrics.get("residual_gate_passed")),
                "increment_gate_passed": bool(metrics.get("increment_gate_passed")),
                "tip_displacement_m": tip_displacement_m,
                "iteration_count": int(metrics.get("iteration_count", 0)),
                "regularization_used": metrics.get("regularization_used"),
                "fallback_used": metrics.get("fallback_used"),
                "tangent_gate_passed": bool(jacobian_check["pass"]),
                "series_force_gate_passed": bool(series_check["pass"]),
                "series_force_spread_kn": float(series_check.get("force_spread_kn", 0.0)),
                "residual_norm_kn": float(metrics.get("residual_norm", 0.0)),
                "final_increment_abs_m": float(metrics.get("final_increment_abs_m", 0.0)),
            }
        )
    tip_values = [row["tip_displacement_m"] for row in rows]
    spread_m = max(tip_values) - min(tip_values)
    pass_gate = (
        all(row["contract_pass"] for row in rows)
        and all(row["tangent_gate_passed"] for row in rows)
        and all(row["series_force_gate_passed"] for row in rows)
        and all(row["regularization_used"] is False for row in rows)
        and all(row["fallback_used"] is False for row in rows)
        and spread_m <= MESH_REFINEMENT_TOLERANCE_M
    )
    return {
        "model_kind": "strain_nonlinear_axial_cubic_bar",
        "element_counts": list(MESH_REFINEMENT_ELEMENT_COUNTS),
        "rows": rows,
        "tip_displacements_m": tip_values,
        "tip_displacement_spread_m": spread_m,
        "tolerance_m": MESH_REFINEMENT_TOLERANCE_M,
        "narrow_mesh_refinement_gate_passed": pass_gate,
        "claim_boundary": (
            "Length-aware 1D strain-cubic axial bar mesh refinement only. "
            "This does not close general frame/shell/material mesh convergence."
        ),
    }


def _run_sparse_backend_equivalence(
    mesh_problem: Any,
    *,
    dense_config: NewtonRaphsonConfig,
) -> dict[str, Any]:
    sparse_config = NewtonRaphsonConfig(
        residual_tolerance=dense_config.residual_tolerance,
        increment_tolerance=dense_config.increment_tolerance,
        max_iterations=dense_config.max_iterations,
        line_search_alphas=dense_config.line_search_alphas,
        matrix_backend=VECTOR_SPARSE_MATRIX_BACKEND,
    )
    dense_solution, dense_state = solve_axial_chain_mesh(mesh_problem, config=dense_config)
    sparse_solution, sparse_state = solve_axial_chain_mesh(mesh_problem, config=sparse_config)
    displacement_delta_m = [
        abs(float(a) - float(b))
        for a, b in zip(
            dense_state.displacements_m.tolist(),
            sparse_state.displacements_m.tolist(),
            strict=True,
        )
    ]
    residual_delta_kn = [
        abs(float(a) - float(b))
        for a, b in zip(
            dense_state.residual_kn.tolist(),
            sparse_state.residual_kn.tolist(),
            strict=True,
        )
    ]
    max_displacement_delta_m = max(displacement_delta_m) if displacement_delta_m else 0.0
    max_residual_delta_kn = max(residual_delta_kn) if residual_delta_kn else 0.0
    pass_gate = (
        dense_solution.status == "ready"
        and sparse_solution.status == "ready"
        and bool(dense_solution.metrics.get("contract_pass"))
        and bool(sparse_solution.metrics.get("contract_pass"))
        and sparse_solution.metrics.get("matrix_backend") == VECTOR_SPARSE_MATRIX_BACKEND
        and sparse_solution.metrics.get("sparse_backend_used") is True
        and sparse_solution.metrics.get("regularization_used") is False
        and sparse_solution.metrics.get("fallback_used") is False
        and max_displacement_delta_m <= DISPLACEMENT_TOLERANCE_M
        and max_residual_delta_kn <= 1.0e-10
    )
    return {
        "dense_backend": dense_solution.metrics.get("matrix_backend"),
        "sparse_backend": sparse_solution.metrics.get("matrix_backend"),
        "sparse_backend_used": sparse_solution.metrics.get("sparse_backend_used"),
        "sparse_stiffness_storage": sparse_solution.metrics.get("stiffness_storage"),
        "dense_status": dense_solution.status,
        "sparse_status": sparse_solution.status,
        "dense_contract_pass": bool(dense_solution.metrics.get("contract_pass")),
        "sparse_contract_pass": bool(sparse_solution.metrics.get("contract_pass")),
        "dense_free_displacements_m": dense_solution.free_displacements_m.tolist(),
        "sparse_free_displacements_m": sparse_solution.free_displacements_m.tolist(),
        "max_displacement_delta_m": max_displacement_delta_m,
        "max_residual_delta_kn": max_residual_delta_kn,
        "regularization_used": sparse_solution.metrics.get("regularization_used"),
        "fallback_used": sparse_solution.metrics.get("fallback_used"),
        "narrow_sparse_backend_equivalence_gate_passed": pass_gate,
        "claim_boundary": (
            "Scoped scipy sparse vector Newton solve on the tiny 1D material mesh seed only. "
            "This does not close production sparse assembly for general frame/shell/material systems."
        ),
    }


def build_material_mesh_newton_artifacts(
    *,
    repo_root: Path = ROOT,
    mesh_out: Path = DEFAULT_MESH_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    repo_root = repo_root.resolve()
    mesh_problem = default_phase2_axial_chain_mesh_problem()
    config = NewtonRaphsonConfig(
        residual_tolerance=1.0e-10,
        increment_tolerance=1.0e-12,
        max_iterations=25,
    )
    solution, final_state = solve_axial_chain_mesh(mesh_problem, config=config)
    metrics = solution.metrics
    tip_node = max(node_index for node_index, _ in mesh_problem.external_forces_kn)
    tip_displacement_m = float(final_state.displacements_m[tip_node])

    jacobian_check = finite_difference_assembled_jacobian_check(
        mesh_problem,
        solution.free_displacements_m,
    )
    series_force_check = mesh_series_force_equilibrium_check(final_state)
    full_load_partition = _run_mesh_load_step_partition(
        mesh_problem,
        config=config,
        step_factors=(1.0,),
    )
    ramped_partition = _run_mesh_load_step_partition(
        mesh_problem,
        config=config,
        step_factors=LOAD_STEP_FACTORS,
    )
    load_step_spread_m = abs(
        full_load_partition["final_tip_displacement_m"]
        - ramped_partition["final_tip_displacement_m"]
    )
    load_step_gate_passed = load_step_spread_m <= DISPLACEMENT_TOLERANCE_M
    mesh_refinement_suite = _run_mesh_refinement_suite(config=config)
    narrow_mesh_refinement_gate_passed = bool(
        mesh_refinement_suite["narrow_mesh_refinement_gate_passed"]
    )
    sparse_backend_equivalence = _run_sparse_backend_equivalence(
        mesh_problem,
        dense_config=config,
    )
    narrow_sparse_backend_gate_passed = bool(
        sparse_backend_equivalence["narrow_sparse_backend_equivalence_gate_passed"]
    )

    residual_gate_passed = bool(metrics.get("residual_gate_passed"))
    increment_gate_passed = bool(metrics.get("increment_gate_passed"))
    no_regularization_or_fallback = (
        metrics.get("regularization_used") is False and metrics.get("fallback_used") is False
    )
    tangent_gate_passed = bool(jacobian_check["pass"])
    series_force_gate_passed = bool(series_force_check["pass"])
    mesh_contract_pass = (
        solution.status == "ready"
        and bool(metrics.get("contract_pass"))
        and residual_gate_passed
        and increment_gate_passed
        and no_regularization_or_fallback
        and tangent_gate_passed
        and series_force_gate_passed
        and load_step_gate_passed
        and narrow_mesh_refinement_gate_passed
        and narrow_sparse_backend_gate_passed
        and metrics.get("residual_formula") == RESIDUAL_FORMULA
        and full_load_partition["steps"][0]["contract_pass"] is True
        and ramped_partition["steps"][-1]["contract_pass"] is True
    )

    result_payload = _solution_payload(solution, final_state)
    result_payload["problem"] = _mesh_problem_payload(mesh_problem)
    result_payload["verification"] = {
        "tip_node_index": tip_node,
        "tip_displacement_m": tip_displacement_m,
        "assembled_jacobian_finite_difference_check": jacobian_check,
        "tangent_gate_passed": tangent_gate_passed,
        "series_force_equilibrium_check": series_force_check,
        "series_force_gate_passed": series_force_gate_passed,
        "mesh_load_step_consistency": {
            "full_load_partition": full_load_partition,
            "ramped_partition": ramped_partition,
            "final_tip_displacement_spread_m": load_step_spread_m,
            "load_step_gate_passed": load_step_gate_passed,
        },
        "mesh_refinement_suite": mesh_refinement_suite,
        "sparse_backend_equivalence": sparse_backend_equivalence,
    }

    mesh_payload = {
        "schema_version": "phase2-material-mesh-newton-axial-chain.v1",
        "status": "ready" if mesh_contract_pass else "blocked",
        "contract_pass": mesh_contract_pass,
        "truth_class": "assembled_mesh_truth",
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "g1_closure_claim": False,
        "material_newton_closure_claim": False,
        "full_mesh_closure_claim": False,
        "node_count": mesh_problem.node_count,
        "element_count": len(mesh_problem.elements),
        "model_kind": "scalar_nonlinear_axial_cubic_spring",
        "solver_config": {
            "residual_tolerance": config.residual_tolerance,
            "increment_tolerance": config.increment_tolerance,
            "max_iterations": config.max_iterations,
        },
        "mesh_result": result_payload,
        "claim_boundary": result_payload["claim_boundary"],
    }

    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": ANALYSIS_ENGINE_VERSION,
        "input_checksums": input_checksums(
            [
                Path("src/structural_analysis/assembly/__init__.py"),
                Path("src/structural_analysis/assembly/nonlinear_static.py"),
                Path("src/structural_analysis/solvers/nonlinear/__init__.py"),
                Path("src/structural_analysis/solvers/nonlinear/newton.py"),
                Path("scripts/build_phase2_material_mesh_newton_artifacts.py"),
                Path("scripts/verify_quality_gate.py"),
                Path("tests/test_build_phase2_material_mesh_newton_artifacts.py"),
            ],
            repo_root=repo_root,
        ),
        "status": "ready" if mesh_contract_pass else "blocked",
        "contract_pass": mesh_contract_pass,
        "claim_boundary_version": CLAIM_BOUNDARY_VERSION,
        "g1_closure_claim": False,
        "material_newton_closure_claim": False,
        "full_mesh_closure_claim": False,
        "analysis_type": "nonlinear_static_material_mesh_newton_seed",
        "truth_class": "assembled_mesh_truth",
        "residual_contract": RESIDUAL_FORMULA,
        "residual_formula": RESIDUAL_FORMULA,
        "globalization": GLOBALIZATION,
        "matrix_backend": VECTOR_MATRIX_BACKEND,
        "sparse_backend_used": False,
        "sparse_backend_equivalence_matrix_backend": VECTOR_SPARSE_MATRIX_BACKEND,
        "node_count": mesh_problem.node_count,
        "element_count": len(mesh_problem.elements),
        "model_kind": "scalar_nonlinear_axial_cubic_spring",
        "tip_displacement_m": tip_displacement_m,
        "tangent_gate_passed": tangent_gate_passed,
        "series_force_gate_passed": series_force_gate_passed,
        "load_step_gate_passed": load_step_gate_passed,
        "narrow_mesh_refinement_gate_passed": narrow_mesh_refinement_gate_passed,
        "narrow_sparse_backend_equivalence_gate_passed": narrow_sparse_backend_gate_passed,
        "final_tip_displacement_spread_m": load_step_spread_m,
        "mesh_refinement_tip_displacement_spread_m": mesh_refinement_suite[
            "tip_displacement_spread_m"
        ],
        "mesh_refinement_element_counts": list(MESH_REFINEMENT_ELEMENT_COUNTS),
        "blockers_remaining": [
            "full_mesh_full_load_nonlinear_equilibrium_not_closed",
            "frame_shell_material_coupling_not_closed",
            "general_mesh_load_step_nonlinear_convergence_suite_not_closed",
            "general_sparse_matrix_backend_not_closed",
            "production_rocm_hip_parity_not_closed",
            "broad_material_newton_breadth_not_closed",
        ],
        "artifacts": {
            "axial_chain_result": str(mesh_out),
            "summary": str(summary_out),
            "related_material_newton_breadth_summary": str(
                PRODUCTIZATION / "phase2_material_newton_breadth_summary.json"
            ),
        },
        "claim_boundary": mesh_payload["claim_boundary"],
    }
    return {
        "mesh": mesh_payload,
        "summary": summary_payload,
    }


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


def check_material_mesh_newton_artifacts(
    *,
    repo_root: Path = ROOT,
    mesh_out: Path = DEFAULT_MESH_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> tuple[bool, str]:
    expected = build_material_mesh_newton_artifacts(
        repo_root=repo_root,
        mesh_out=mesh_out,
        summary_out=summary_out,
    )
    targets = {
        "mesh": mesh_out,
        "summary": summary_out,
    }
    for key, path in targets.items():
        resolved = path if path.is_absolute() else repo_root / path
        if not resolved.exists():
            return False, f"phase2_material_mesh_newton_missing:{path.as_posix()}"
        try:
            existing = _read_json(resolved)
        except Exception as exc:
            return False, (
                f"phase2_material_mesh_newton_unreadable:{path.as_posix()}:"
                f"{exc.__class__.__name__}"
            )
        if _strip_volatile(existing) != _strip_volatile(expected[key]):
            return False, f"phase2_material_mesh_newton_mismatch:{key}"
    return True, "phase2_material_mesh_newton_consistent"


def write_material_mesh_newton_artifacts(
    *,
    repo_root: Path = ROOT,
    mesh_out: Path = DEFAULT_MESH_OUT,
    summary_out: Path = DEFAULT_SUMMARY_OUT,
) -> dict[str, dict[str, Any]]:
    artifacts = build_material_mesh_newton_artifacts(
        repo_root=repo_root,
        mesh_out=mesh_out,
        summary_out=summary_out,
    )
    for key, path in {
        "mesh": mesh_out,
        "summary": summary_out,
    }.items():
        resolved = path if path.is_absolute() else repo_root / path
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(_json_text(artifacts[key]), encoding="utf-8")
    return artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh-out", type=Path, default=DEFAULT_MESH_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_material_mesh_newton_artifacts(
            mesh_out=args.mesh_out,
            summary_out=args.summary_out,
        )
        print(f"Phase 2 material mesh Newton check: {message}")
        return 0 if ok else 1
    artifacts = write_material_mesh_newton_artifacts(
        mesh_out=args.mesh_out,
        summary_out=args.summary_out,
    )
    summary = artifacts["summary"]
    print(
        "Phase 2 material mesh Newton: "
        f"{summary['status']} | nodes={summary['node_count']} | "
        f"elements={summary['element_count']} | tip_u={summary['tip_displacement_m']}"
    )
    return 0 if summary["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
