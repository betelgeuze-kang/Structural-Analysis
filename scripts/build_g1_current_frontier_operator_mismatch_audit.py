#!/usr/bin/env python3
"""Build a non-promoting current-frontier G1 operator mismatch audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "g1-current-frontier-operator-mismatch-audit.v1"
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_FRONTIER_PROBE = (
    PRODUCTIZATION / "mgt_residual_jacobian_step16_scaled_global_krylov_direct_probe.json"
)
DEFAULT_OUT = PRODUCTIZATION / "g1_current_frontier_operator_mismatch_audit.json"
SHELL_ELASTIC_RATIO_BAND = 5.0e-3


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.is_file():
        return {}
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _all_candidates_no_descent(rows: list[Any], base_residual: float) -> bool:
    candidate_rows = [row for row in rows if isinstance(row, dict)]
    if not candidate_rows:
        return False
    return all(
        _as_float(row.get("direct_residual_inf_n"), float("inf")) >= base_residual
        for row in candidate_rows
    )


def _candidate_summary(payload: dict[str, Any], *, base_residual: float) -> dict[str, Any]:
    best = _as_dict(payload.get("best_gate_eligible_candidate"))
    if not best:
        best = _as_dict(payload.get("best_candidate"))
    rows = _as_list(payload.get("trial_rows"))
    best_residual = _as_float(best.get("direct_residual_inf_n"), float("inf"))
    return {
        "attempted": payload.get("attempted") is True,
        "promoted_to_final_state": payload.get("promoted_to_final_state") is True,
        "best_direct_residual_inf_n": best_residual,
        "best_improvement_inf_n": _as_float(best.get("improvement_inf_n")),
        "best_alpha": _as_float(best.get("alpha")),
        "best_alpha_source": str(best.get("alpha_source") or ""),
        "trial_count": len(rows),
        "all_trial_candidates_no_descent": _all_candidates_no_descent(
            rows,
            base_residual,
        ),
        "best_candidate_no_descent": best_residual >= base_residual,
        "residual_batch_backend": str(best.get("residual_batch_backend") or ""),
    }


def _shell_material_summary(mesh: dict[str, Any]) -> dict[str, Any]:
    shell_meta = _as_dict(mesh.get("service_shell_material_meta"))
    nonlinear_count = int(_as_float(shell_meta.get("nonlinear_tangent_surface_element_count")))
    min_ratio = _as_float(shell_meta.get("min_tangent_ratio"), 1.0)
    elastic_passive = (
        nonlinear_count == 0
        and (1.0 - min_ratio) <= SHELL_ELASTIC_RATIO_BAND
    )
    return {
        "shell_tangent_ratio_min": min_ratio,
        "shell_tangent_ratio_mean": _as_float(shell_meta.get("mean_tangent_ratio"), 1.0),
        "shell_max_abs_strain": _as_float(shell_meta.get("max_abs_strain")),
        "shell_nonlinear_surface_element_count": nonlinear_count,
        "shell_state_tag_counts": _as_dict(shell_meta.get("state_tag_counts")),
        "shell_material_tangent_elastic_passive_at_checkpoint": elastic_passive,
        "shell_material_tangent_is_stall_driver": not elastic_passive,
    }


def build_g1_current_frontier_operator_mismatch_audit(
    *,
    repo_root: Path = ROOT,
    frontier_probe_path: Path = DEFAULT_FRONTIER_PROBE,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    probe = _load_json(repo_root, frontier_probe_path)
    base = _as_dict(probe.get("base_direct_residual"))
    final = _as_dict(probe.get("final_direct_residual"))
    output = _as_dict(probe.get("output_final_checkpoint"))
    residual_contract = _as_dict(probe.get("residual_contract"))
    mesh = _as_dict(probe.get("mesh_fingerprint"))
    frame_meta = _as_dict(mesh.get("frame_material_meta"))
    service_meta = _as_dict(mesh.get("service_material_meta"))
    live_contract = _as_dict(probe.get("live_g1_assembly_contract"))
    global_krylov = _as_dict(probe.get("matrix_free_global_krylov"))
    row_correction = _as_dict(probe.get("current_tangent_residual_row_correction"))

    base_residual = _as_float(base.get("direct_residual_inf_n"))
    final_residual = _as_float(final.get("direct_residual_inf_n"), base_residual)
    load_scale = _as_float(base.get("load_scale") or output.get("load_scale"))
    normalization_lambda = _as_float(base.get("linear_correction_regularization"))
    frame_min_ratio = _as_float(frame_meta.get("min_solver_tangent_ratio"), 1.0)
    service_min_ratio = _as_float(service_meta.get("service_min_tangent_ratio"), 1.0)
    global_summary = _candidate_summary(global_krylov, base_residual=base_residual)
    row_summary = _candidate_summary(row_correction, base_residual=base_residual)
    shell_summary = _shell_material_summary(mesh)

    frame_reduced = frame_min_ratio < 0.98
    service_reduced = service_min_ratio < 0.98
    lambda_excluded_from_residual = (
        normalization_lambda > 0.0
        and residual_contract.get("direct_residual_uses_solver_regularization") is False
        and residual_contract.get("regularization_used_only_for_linear_correction_direction")
        is True
    )
    mismatch_reasons = [
        *(["frame_service_material_tangent_reduced_below_elastic"] if frame_reduced else []),
        *(["assembled_service_material_tangent_reduced_below_elastic"] if service_reduced else []),
        *(
            ["lambda_damping_available_to_corrector_but_excluded_from_physical_residual"]
            if lambda_excluded_from_residual
            else []
        ),
        *(
            ["state_dependent_shell_material_tangent_refresh_is_host_side_not_production_residency"]
            if residual_contract.get(
                "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency"
            )
            is True
            else []
        ),
    ]
    global_no_descent = (
        global_summary["attempted"]
        and not global_summary["promoted_to_final_state"]
        and global_summary["best_candidate_no_descent"]
        and global_summary["all_trial_candidates_no_descent"]
    )
    row_no_descent = (
        row_summary["attempted"]
        and not row_summary["promoted_to_final_state"]
        and row_summary["best_candidate_no_descent"]
        and row_summary["all_trial_candidates_no_descent"]
    )
    full_load_no_descent = (
        load_scale >= 1.0
        and output.get("written") is not True
        and str(output.get("reason") or "") == "no_residual_descent"
        and final_residual >= base_residual
        and global_no_descent
        and row_no_descent
    )
    terminal_criteria = {
        "frontier_probe_present": bool(probe),
        "full_load_checkpoint_input": load_scale >= 1.0,
        "live_g1_assembly_contract_passed": live_contract.get("contract_pass") is True,
        "physical_residual_contract_preserved": (
            residual_contract.get("definition")
            == "R(u, lambda) = F_int(u) - lambda * F_ext"
            and residual_contract.get("direct_residual_uses_solver_regularization")
            is False
        ),
        "hip_residual_engine_contract_passed": (
            residual_contract.get("hip_residual_engine_contract_passed") is True
        ),
        "current_scaled_global_krylov_no_descent": global_no_descent,
        "current_row_correction_no_descent": row_no_descent,
        "shell_material_tangent_elastic_passive_evidence_present": (
            shell_summary["shell_material_tangent_elastic_passive_at_checkpoint"]
        ),
        "current_operator_mismatch_named": bool(mismatch_reasons),
    }
    audit_complete = all(terminal_criteria.values())
    payload = {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                frontier_probe_path,
                Path("scripts/build_g1_current_frontier_operator_mismatch_audit.py"),
            ],
            reused_evidence=True,
            reuse_policy=(
                "Derived from the current full-load HIP step16 no-descent probe. "
                "It does not run the solver or promote G1."
            ),
            repo_root=repo_root,
        ),
        "status": "ready" if audit_complete else "partial",
        "audit_complete": audit_complete,
        "is_audit_only": True,
        "promotes_g1_closure": False,
        "frontier_probe": {
            "path": frontier_probe_path.as_posix(),
            "status": str(probe.get("status") or "missing"),
            "source_commit_sha": str(probe.get("source_commit_sha") or ""),
            "load_scale": load_scale,
            "base_direct_residual_inf_n": base_residual,
            "final_direct_residual_inf_n": final_residual,
            "output_checkpoint_written": output.get("written") is True,
            "output_checkpoint_reason": str(output.get("reason") or ""),
            "output_checkpoint_path": str(output.get("path") or ""),
            "full_load_no_descent": full_load_no_descent,
        },
        "live_g1_assembly_contract": {
            "present": bool(live_contract),
            "contract_pass": live_contract.get("contract_pass") is True,
            "assembly_result_schema": str(live_contract.get("assembly_result_schema") or ""),
            "residual_formula": str(live_contract.get("residual_formula") or ""),
            "residual_source": str(live_contract.get("residual_source") or ""),
            "tangent_definition": str(live_contract.get("tangent_definition") or ""),
            "residual_inf_norm": _as_float(live_contract.get("residual_inf_norm")),
            "free_dof_count": int(_as_float(live_contract.get("free_dof_count"))),
        },
        "current_operator_mismatch": {
            "linearized_tangent_description": str(
                _as_dict(probe.get("newton_direction")).get("linearized_tangent") or ""
            ),
            "normalization_lambda": normalization_lambda,
            "direct_residual_uses_solver_regularization": (
                residual_contract.get("direct_residual_uses_solver_regularization")
                is True
            ),
            "regularization_used_only_for_linear_correction_direction": (
                residual_contract.get("regularization_used_only_for_linear_correction_direction")
                is True
            ),
            "service_material_tangent_used_for_newton_direction_only": (
                residual_contract.get("service_material_tangent_used_for_newton_direction_only")
                is True
            ),
            "frame_tangent_ratio_min": frame_min_ratio,
            "frame_tangent_reduction_element_count": int(
                _as_float(frame_meta.get("tangent_reduction_element_count"))
            ),
            "service_material_scale_min": service_min_ratio,
            "service_material_scale_mean": _as_float(
                service_meta.get("service_mean_tangent_ratio"),
                1.0,
            ),
            "frame_geometric_delta_stiffness_nnz": int(
                _as_float(mesh.get("frame_geometric_delta_stiffness_nnz"))
            ),
            "mismatch_reasons": mismatch_reasons,
        },
        "shell_material_state": shell_summary,
        "current_frontier_no_descent": {
            "scaled_global_krylov": global_summary,
            "current_tangent_residual_row_correction": row_summary,
            "global_and_row_operator_family_no_descent": (
                global_no_descent and row_no_descent
            ),
        },
        "hip_residual_engine": {
            "contract_passed": (
                residual_contract.get("hip_residual_engine_contract_passed") is True
            ),
            "required_lane_count": int(
                _as_float(residual_contract.get("hip_residual_engine_required_lane_count"))
            ),
            "passed_lane_count": int(
                _as_float(residual_contract.get("hip_residual_engine_passed_lane_count"))
            ),
            "backends": _as_list(residual_contract.get("hip_residual_engine_backends")),
        },
        "operator_mismatch_summary": {
            "stall_driver": (
                "current_full_load_scaled_global_krylov_and_row_correction_operator_"
                "family_no_descent"
            ),
            "named_current_operator": (
                "service-material reduced frame tangent + frame geometric delta + "
                "state shell material tangent + finite springs, evaluated through "
                "HIP residual replay but not a convergent physical-consistent "
                "Newton operator at the current full-load frontier"
            ),
            "next_required_operator": (
                "physical_consistent_frame_shell_material_geometric_with_state_"
                "updated_material_tangent_and_full_residual_globalization"
            ),
            "disfavored_retries": [
                "repeat_scaled_global_krylov_with_residual_diagonal_displacement",
                "repeat_largest_rows_current_tangent_residual_row_correction",
                "promote_fixed_point_or_regularized_residual_as_physical_residual",
            ],
        },
        "terminal_criteria": terminal_criteria,
        "blockers_remaining": [
            "direct_residual_gate_not_closed",
            "consistent_residual_jacobian_newton_gate_not_closed",
            "state_updated_material_newton_breadth_not_closed",
            "state_dependent_shell_material_tangent_refresh_not_production_rocm_hip_residency",
        ],
        "claim_boundary": (
            "This is a non-promoting current-frontier operator mismatch audit. "
            "It proves only that the current full-load HIP scaled global-Krylov "
            "and row-correction operator family produced no residual descent while "
            "preserving the physical residual contract. It does not close G1, "
            "material Newton breadth, direct residual, or production ROCm/HIP residency."
        ),
    }
    return payload


def write_g1_current_frontier_operator_mismatch_audit(
    *,
    repo_root: Path = ROOT,
    frontier_probe_path: Path = DEFAULT_FRONTIER_PROBE,
    out: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_g1_current_frontier_operator_mismatch_audit(
        repo_root=repo_root,
        frontier_probe_path=frontier_probe_path,
    )
    resolved = _resolve(repo_root, out)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--frontier-probe", type=Path, default=DEFAULT_FRONTIER_PROBE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_g1_current_frontier_operator_mismatch_audit(
        repo_root=args.repo_root,
        frontier_probe_path=args.frontier_probe,
        out=args.out,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        frontier = payload["frontier_probe"]
        print(
            "G1 current frontier operator mismatch audit: "
            f"{payload['status']} | full_load_no_descent="
            f"{frontier['full_load_no_descent']} | "
            f"global_row_no_descent="
            f"{payload['current_frontier_no_descent']['global_and_row_operator_family_no_descent']}"
        )
    return 1 if args.fail_blocked and not payload["audit_complete"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
