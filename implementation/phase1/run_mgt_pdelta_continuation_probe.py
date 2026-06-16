#!/usr/bin/env python3
"""Probe load-step continuation limits for the full 6-DOF MGT frame P-Delta path."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
from scipy.sparse import eye
from scipy.sparse.linalg import spsolve

from parse_mgt_section_material_properties import load_mgt_section_material_properties
from run_mgt_full_frame_6dof_sparse_equilibrium import (
    DEFAULT_ROUNDTRIP,
    DOF_PER_NODE,
    PRODUCTIZATION,
    _beam_end_offset_lookup,
    _component_gravity_axial_forces,
    _component_restraints,
    _element_angle_array_from_props,
    _assemble_sparse_frame,
    _linear_solver_refinement_policy,
    _select_full_line_mesh,
    _solve_deformed_state_pdelta_fixed_point,
    _solve_sparse_system,
    _translation_metrics,
)
from run_story_model_reanalysis import build_mgt_reanalysis_provenance


SCHEMA_VERSION = "mgt-pdelta-continuation-probe.v1"
DEFAULT_OUT = PRODUCTIZATION / "mgt_pdelta_continuation_probe.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _regularized_residual_system(
    *,
    elements: list[Any],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    base_axial_forces: dict[int, float],
    restrained: set[int],
    target_load_scale: float,
    displacement: np.ndarray,
) -> tuple[np.ndarray, Any, np.ndarray, np.ndarray, float, float]:
    translations = (
        displacement.reshape((-1, DOF_PER_NODE))[:, :3]
        if displacement.size
        else np.zeros((0, 3), dtype=np.float64)
    )
    axial_forces = {
        int(elem_id): float(force) * float(target_load_scale)
        for elem_id, force in base_axial_forces.items()
    }
    tangent, f_step, _meta = _assemble_sparse_frame(
        elements=elements,
        node_xyz=node_xyz + translations,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=axial_forces,
        include_geometric=True,
    )
    free = np.asarray([idx for idx in range(displacement.size) if idx not in restrained], dtype=np.int64)
    k_ff = tangent[free, :][:, free].tocsc()
    diag = np.asarray(k_ff.diagonal(), dtype=np.float64)
    regularization = 1.0e-8 * max(float(np.mean(np.abs(diag))), 1.0)
    k_reg = k_ff + eye(k_ff.shape[0], format="csc") * regularization
    rhs = f_step[free] * float(target_load_scale)
    residual = np.asarray(k_reg @ displacement[free] - rhs, dtype=np.float64)
    residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
    return free, k_reg, rhs, residual, residual_inf, float(regularization)


def _one_step_line_search_probe(
    *,
    elements: list[Any],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    base_axial_forces: dict[int, float],
    restrained: set[int],
    target_load_scale: float,
    seed_displacement: np.ndarray,
    alphas: tuple[float, ...] = (1.0, 0.5, 0.25, 0.125),
) -> dict[str, Any]:
    started = time.perf_counter()
    seed = np.asarray(seed_displacement, dtype=np.float64).copy()
    free, k_reg, _rhs, residual, seed_residual_inf, regularization = _regularized_residual_system(
        elements=elements,
        node_xyz=node_xyz,
        section_props=section_props,
        material_props=material_props,
        base_axial_forces=base_axial_forces,
        restrained=restrained,
        target_load_scale=target_load_scale,
        displacement=seed,
    )
    correction_free = np.asarray(spsolve(k_reg, -residual), dtype=np.float64)
    correction = np.zeros_like(seed)
    correction[free] = correction_free
    correction_norm_inf = float(np.max(np.abs(correction))) if correction.size else 0.0
    candidates: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    best_displacement = seed
    for alpha in alphas:
        candidate = seed + float(alpha) * correction
        _free2, _k2, _rhs2, _residual2, candidate_residual_inf, _reg2 = _regularized_residual_system(
            elements=elements,
            node_xyz=node_xyz,
            section_props=section_props,
            material_props=material_props,
            base_axial_forces=base_axial_forces,
            restrained=restrained,
            target_load_scale=target_load_scale,
            displacement=candidate,
        )
        metrics = _translation_metrics(candidate, node_xyz)
        row = {
            "alpha": float(alpha),
            "residual_inf_n": float(candidate_residual_inf),
            "residual_reduction_factor": float(candidate_residual_inf / max(seed_residual_inf, 1.0e-30)),
            "max_translation_m": metrics["max_translation_m"],
            "max_drift_ratio_pct": metrics["max_drift_ratio_pct"],
        }
        candidates.append(row)
        if best is None or row["residual_inf_n"] < float(best["residual_inf_n"]):
            best = row
            best_displacement = candidate
    best = best or {}
    best_metrics = _translation_metrics(best_displacement, node_xyz)
    threshold_n = 1.0e-3
    ready = bool(float(best.get("residual_inf_n") or float("inf")) <= threshold_n)
    return {
        "target_load_scale": float(target_load_scale),
        "seed_residual_inf_n": float(seed_residual_inf),
        "correction_norm_inf_m": correction_norm_inf,
        "regularization": regularization,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "best_alpha": best.get("alpha"),
        "best_residual_inf_n": best.get("residual_inf_n"),
        "best_residual_reduction_factor": best.get("residual_reduction_factor"),
        "best_max_translation_m": best_metrics["max_translation_m"],
        "ready": ready,
        "threshold_n": threshold_n,
        "linear_solver": {
            "strategy": "single_direct_spsolve_on_regularized_residual_system",
            "uses_frame_solver_iterative_refinement": False,
        },
        "seconds": time.perf_counter() - started,
        "claim_boundary": (
            "One-step approximate Newton correction with residual-based alpha scan at the first failed "
            "continuation load. This is diagnostic evidence for the consistent Newton/Jacobian gap, not "
            "a full nonlinear path closure."
        ),
        "blockers": [] if ready else ["one_step_line_search_newton_not_closed"],
    }


def _frontier_residual_jacobian_probe(
    *,
    elements: list[Any],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    base_axial_forces: dict[int, float],
    restrained: set[int],
    seed_load_scale: float,
    seed_displacement: np.ndarray,
    target_load_scale: float,
    fixed_point_relaxation: float = 0.25,
    fixed_point_iterations: int = 60,
    correction_passes: int = 4,
    alphas: tuple[float, ...] = (1.0, 0.5, 0.25, 0.125, 0.0625),
) -> dict[str, Any]:
    started = time.perf_counter()
    fixed_point_result, base_u = _solve_deformed_state_pdelta_fixed_point(
        elements=elements,
        node_xyz=node_xyz,
        section_props=section_props,
        material_props=material_props,
        base_axial_forces=base_axial_forces,
        restrained=restrained,
        target_load_scale=target_load_scale,
        max_iterations=fixed_point_iterations,
        initial_displacement=seed_displacement,
        relaxation_factor=fixed_point_relaxation,
        displacement_cap_m=80.0,
    )
    _base_free, _base_k, _base_rhs, _base_residual, base_residual_inf, regularization = (
        _regularized_residual_system(
            elements=elements,
            node_xyz=node_xyz,
            section_props=section_props,
            material_props=material_props,
            base_axial_forces=base_axial_forces,
            restrained=restrained,
            target_load_scale=target_load_scale,
            displacement=base_u,
        )
    )
    _mapped0, map_residual, _map_regularization = _fixed_point_map(
        elements=elements,
        node_xyz=node_xyz,
        section_props=section_props,
        material_props=material_props,
        base_axial_forces=base_axial_forces,
        restrained=restrained,
        target_load_scale=target_load_scale,
        displacement=base_u,
    )
    residual_tolerance_n = 1.0e-3
    relative_increment_tolerance = 1.0e-4
    pass_rows: list[dict[str, Any]] = []
    current_u = np.asarray(base_u, dtype=np.float64).copy()
    best_u = current_u.copy()
    best_row: dict[str, Any] | None = None
    previous_correction: np.ndarray | None = None
    accepted_correction_count = 0
    breakdown = ""
    ready = False

    for pass_index in range(1, int(correction_passes) + 1):
        free, k_reg, _rhs, residual, residual_before, pass_regularization = _regularized_residual_system(
            elements=elements,
            node_xyz=node_xyz,
            section_props=section_props,
            material_props=material_props,
            base_axial_forces=base_axial_forces,
            restrained=restrained,
            target_load_scale=target_load_scale,
            displacement=current_u,
        )
        directions: list[tuple[str, np.ndarray]] = []
        try:
            direct_free = np.asarray(spsolve(k_reg, -residual), dtype=np.float64)
            direct = np.zeros_like(current_u)
            direct[free] = direct_free
            directions.append(("regularized_tangent_newton", direct))
        except Exception:
            direct = np.zeros_like(current_u)
        mapped, pass_map_residual, _map_regularization = _fixed_point_map(
            elements=elements,
            node_xyz=node_xyz,
            section_props=section_props,
            material_props=material_props,
            base_axial_forces=base_axial_forces,
            restrained=restrained,
            target_load_scale=target_load_scale,
            displacement=current_u,
        )
        directions.append(("fixed_point_delta", np.asarray(mapped - current_u, dtype=np.float64)))
        directions.append(("load_path_secant_delta", np.asarray(current_u - seed_displacement, dtype=np.float64)))
        if previous_correction is not None:
            directions.append(("previous_residual_jacobian_correction", previous_correction))

        filtered: list[tuple[str, np.ndarray]] = []
        for label, direction in directions:
            direction = np.asarray(direction, dtype=np.float64)
            norm_inf = float(np.max(np.abs(direction))) if direction.size else 0.0
            if direction.shape == current_u.shape and np.all(np.isfinite(direction)) and norm_inf > 1.0e-12:
                filtered.append((label, direction))

        jvp_rows: list[dict[str, Any]] = []
        jvp_columns: list[np.ndarray] = []
        for label, direction in filtered:
            _free_d, _k_d, _rhs_d, residual_d, residual_d_inf, _reg_d = _regularized_residual_system(
                elements=elements,
                node_xyz=node_xyz,
                section_props=section_props,
                material_props=material_props,
                base_axial_forces=base_axial_forces,
                restrained=restrained,
                target_load_scale=target_load_scale,
                displacement=current_u + direction,
            )
            jvp = np.asarray(residual_d - residual, dtype=np.float64)
            jvp_columns.append(jvp)
            jvp_rows.append(
                {
                    "label": label,
                    "direction_norm_inf_m": float(np.max(np.abs(direction))) if direction.size else 0.0,
                    "trial_residual_inf_n": float(residual_d_inf),
                    "jvp_norm_inf_n": float(np.max(np.abs(jvp))) if jvp.size else 0.0,
                }
            )

        coefficient_values: list[float] = []
        ls_backend = ""
        combined = np.zeros_like(current_u)
        if jvp_columns:
            jvp_matrix = np.column_stack(jvp_columns)
            try:
                coefficients = np.linalg.lstsq(jvp_matrix, -residual, rcond=None)[0]
                ls_backend = "numpy_lstsq_finite_difference_residual_jacobian"
            except np.linalg.LinAlgError:
                coefficients = np.zeros(len(filtered), dtype=np.float64)
                ls_backend = "numpy_lstsq_failed_zero_correction"
            coefficient_values = [float(value) for value in coefficients.tolist()]
            for coefficient, (_label, direction) in zip(coefficients, filtered):
                combined += float(coefficient) * direction

        candidate_rows: list[dict[str, Any]] = []
        pass_best_row: dict[str, Any] | None = None
        pass_best_u = current_u.copy()
        pass_best_correction = np.zeros_like(current_u)
        for alpha in alphas:
            candidate_correction = float(alpha) * combined
            candidate = current_u + candidate_correction
            _free_c, _k_c, _rhs_c, _residual_c, candidate_residual_inf, _reg_c = _regularized_residual_system(
                elements=elements,
                node_xyz=node_xyz,
                section_props=section_props,
                material_props=material_props,
                base_axial_forces=base_axial_forces,
                restrained=restrained,
                target_load_scale=target_load_scale,
                displacement=candidate,
            )
            remapped, remap_residual, _remap_regularization = _fixed_point_map(
                elements=elements,
                node_xyz=node_xyz,
                section_props=section_props,
                material_props=material_props,
                base_axial_forces=base_axial_forces,
                restrained=restrained,
                target_load_scale=target_load_scale,
                displacement=candidate,
            )
            fixed_point_increment = float(np.max(np.abs(remapped - candidate))) if candidate.size else 0.0
            remapped_max_abs = max(float(np.max(np.abs(remapped))) if remapped.size else 0.0, 1.0e-9)
            fixed_point_relative_increment = fixed_point_increment / remapped_max_abs
            metrics = _translation_metrics(candidate, node_xyz)
            row = {
                "alpha": float(alpha),
                "residual_inf_n": float(candidate_residual_inf),
                "fixed_point_remap_residual_inf_n": float(remap_residual),
                "fixed_point_increment_m": fixed_point_increment,
                "fixed_point_relative_increment": fixed_point_relative_increment,
                "max_translation_m": metrics["max_translation_m"],
                "max_drift_ratio_pct": metrics["max_drift_ratio_pct"],
                "residual_gate_passed": bool(candidate_residual_inf <= residual_tolerance_n),
                "relative_increment_gate_passed": bool(
                    fixed_point_relative_increment <= relative_increment_tolerance
                ),
            }
            row["ready"] = bool(row["residual_gate_passed"] and row["relative_increment_gate_passed"])
            candidate_rows.append(row)
            if pass_best_row is None or (
                not bool(row["ready"]),
                float(row["residual_inf_n"]),
                float(row["fixed_point_relative_increment"]),
            ) < (
                not bool(pass_best_row["ready"]),
                float(pass_best_row["residual_inf_n"]),
                float(pass_best_row["fixed_point_relative_increment"]),
            ):
                pass_best_row = row
                pass_best_u = candidate
                pass_best_correction = candidate_correction

        pass_best_row = pass_best_row or {}
        accepted = bool(
            np.isfinite(float(pass_best_row.get("residual_inf_n") or float("inf")))
            and float(pass_best_row.get("residual_inf_n") or float("inf")) < residual_before
        )
        if best_row is None or (
            not bool(pass_best_row.get("ready")),
            float(pass_best_row.get("residual_inf_n") or float("inf")),
            float(pass_best_row.get("fixed_point_relative_increment") or float("inf")),
        ) < (
            not bool(best_row.get("ready")),
            float(best_row.get("residual_inf_n") or float("inf")),
            float(best_row.get("fixed_point_relative_increment") or float("inf")),
        ):
            best_row = pass_best_row
            best_u = pass_best_u
        pass_rows.append(
            {
                "pass": int(pass_index),
                "residual_inf_n_before": float(residual_before),
                "map_residual_inf_n_before": float(pass_map_residual),
                "regularization": float(pass_regularization),
                "direction_count": len(filtered),
                "direction_labels": [label for label, _direction in filtered],
                "jvp_rows": jvp_rows,
                "least_squares_backend": ls_backend,
                "coefficient_values": coefficient_values,
                "coefficient_l1": float(sum(abs(value) for value in coefficient_values)),
                "combined_correction_norm_inf_m": float(np.max(np.abs(combined))) if combined.size else 0.0,
                "candidate_count": len(candidate_rows),
                "candidate_rows": candidate_rows,
                "best_alpha": pass_best_row.get("alpha"),
                "best_residual_inf_n": pass_best_row.get("residual_inf_n"),
                "best_fixed_point_relative_increment": pass_best_row.get("fixed_point_relative_increment"),
                "accepted": accepted,
            }
        )
        if bool(pass_best_row.get("ready")):
            ready = True
            current_u = pass_best_u
            previous_correction = pass_best_correction
            break
        if accepted:
            accepted_correction_count += 1
            current_u = pass_best_u
            previous_correction = pass_best_correction
            continue
        breakdown = "no_residual_jacobian_candidate_improved_direct_residual"
        break

    first_pass = pass_rows[0] if pass_rows else {}
    best_row = best_row or {}
    final_residual_inf = float(best_row.get("residual_inf_n") or base_residual_inf)
    ready = bool(best_row.get("ready"))
    return {
        "seed_load_scale": float(seed_load_scale),
        "target_load_scale": float(target_load_scale),
        "ready": ready,
        "converged": ready,
        "base_fixed_point_ready": bool(fixed_point_result.get("ready")),
        "base_fixed_point_iteration_count": int(fixed_point_result.get("iteration_count") or 0),
        "base_fixed_point_relaxation": float(fixed_point_relaxation),
        "base_residual_inf_n": float(base_residual_inf),
        "base_fixed_point_map_residual_inf_n": float(map_residual),
        "regularization": float(regularization),
        "correction_pass_count": len(pass_rows),
        "requested_correction_passes": int(correction_passes),
        "accepted_correction_count": int(accepted_correction_count),
        "direction_count": int(first_pass.get("direction_count") or 0),
        "direction_labels": first_pass.get("direction_labels") or [],
        "jvp_rows": first_pass.get("jvp_rows") or [],
        "least_squares_backend": first_pass.get("least_squares_backend") or "",
        "coefficient_values": first_pass.get("coefficient_values") or [],
        "coefficient_l1": float(first_pass.get("coefficient_l1") or 0.0),
        "combined_correction_norm_inf_m": float(first_pass.get("combined_correction_norm_inf_m") or 0.0),
        "candidate_count": int(first_pass.get("candidate_count") or 0),
        "candidate_rows": first_pass.get("candidate_rows") or [],
        "pass_rows": pass_rows,
        "best_alpha": best_row.get("alpha"),
        "best_residual_inf_n": best_row.get("residual_inf_n"),
        "best_fixed_point_relative_increment": best_row.get("fixed_point_relative_increment"),
        "final_residual_inf_n": final_residual_inf,
        "best_residual_reduction_factor": final_residual_inf / max(float(base_residual_inf), 1.0e-30),
        "residual_tolerance_n": residual_tolerance_n,
        "relative_increment_tolerance": relative_increment_tolerance,
        "breakdown": breakdown,
        "seconds": time.perf_counter() - started,
        "claim_boundary": (
            "Finite-difference residual-Jacobian probe at the nearest failed P-Delta frontier bracket. "
            "It builds a small Newton-Krylov correction from tangent, fixed-point, and load-path directions "
            "and accepts only after both direct residual and remapped fixed-point increment gates pass. "
            "It is a local frontier closure only, not full-load material/shell Newton closure."
        ),
        "_accepted_displacement": best_u if ready else None,
        "blockers": [] if ready else ["frontier_residual_jacobian_not_closed"],
    }


def _fixed_point_map(
    *,
    elements: list[Any],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    base_axial_forces: dict[int, float],
    restrained: set[int],
    target_load_scale: float,
    displacement: np.ndarray,
) -> tuple[np.ndarray, float, float]:
    n_dof = int(node_xyz.shape[0]) * DOF_PER_NODE
    free = np.asarray([idx for idx in range(n_dof) if idx not in restrained], dtype=np.int64)
    translations = (
        displacement.reshape((-1, DOF_PER_NODE))[:, :3]
        if displacement.size
        else np.zeros((0, 3), dtype=np.float64)
    )
    axial_forces = {
        int(elem_id): float(force) * float(target_load_scale)
        for elem_id, force in base_axial_forces.items()
    }
    tangent, f_step, _meta = _assemble_sparse_frame(
        elements=elements,
        node_xyz=node_xyz + translations,
        section_props=section_props,
        material_props=material_props,
        element_axial_forces=axial_forces,
        include_geometric=True,
    )
    u_free, residual_inf, regularization = _solve_sparse_system(
        stiffness=tangent,
        f_ext=f_step * float(target_load_scale),
        free=free,
    )
    candidate = np.zeros(n_dof, dtype=np.float64)
    candidate[free] = np.asarray(u_free, dtype=np.float64)
    return candidate, float(residual_inf), float(regularization)


def _anderson_acceleration_probe(
    *,
    elements: list[Any],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    base_axial_forces: dict[int, float],
    restrained: set[int],
    target_load_scale: float,
    seed_displacement: np.ndarray,
    max_iterations: int = 48,
    history_depth: int = 8,
    residual_tolerance_n: float = 1.0e-3,
    relative_increment_tolerance: float = 1.0e-4,
    displacement_cap_m: float = 80.0,
    coefficient_l1_limit: float | None = None,
    label: str = "constrained_anderson",
) -> dict[str, Any]:
    started = time.perf_counter()
    u = np.asarray(seed_displacement, dtype=np.float64).copy()
    fixed_point_history: list[np.ndarray] = []
    map_history: list[np.ndarray] = []
    rows: list[dict[str, Any]] = []
    best_map_residual = float("inf")
    best_relative_increment = float("inf")
    max_coefficient_l1 = 0.0
    max_unbounded_coefficient_l1 = 0.0
    coefficient_bounded_count = 0
    breakdown = ""
    ready = False
    for iteration in range(1, int(max_iterations) + 1):
        mapped, map_residual, regularization = _fixed_point_map(
            elements=elements,
            node_xyz=node_xyz,
            section_props=section_props,
            material_props=material_props,
            base_axial_forces=base_axial_forces,
            restrained=restrained,
            target_load_scale=target_load_scale,
            displacement=u,
        )
        fixed_point = np.asarray(mapped - u, dtype=np.float64)
        fixed_point_history.append(fixed_point)
        map_history.append(np.asarray(mapped, dtype=np.float64))
        if len(fixed_point_history) > int(history_depth):
            fixed_point_history = fixed_point_history[-int(history_depth) :]
            map_history = map_history[-int(history_depth) :]
        candidate = mapped
        coefficient_l1 = 1.0
        unbounded_coefficient_l1 = 1.0
        coefficient_l1_was_bounded = False
        if len(fixed_point_history) >= 2:
            matrix = np.column_stack(fixed_point_history)
            gram = matrix.T @ matrix + np.eye(matrix.shape[1], dtype=np.float64) * 1.0e-18
            ones = np.ones((1, matrix.shape[1]), dtype=np.float64)
            kkt = np.block(
                [
                    [gram, ones.T],
                    [ones, np.zeros((1, 1), dtype=np.float64)],
                ]
            )
            rhs = np.zeros(matrix.shape[1] + 1, dtype=np.float64)
            rhs[-1] = 1.0
            try:
                coefficients = np.linalg.solve(kkt, rhs)[: matrix.shape[1]]
            except np.linalg.LinAlgError:
                coefficients = np.linalg.lstsq(kkt, rhs, rcond=None)[0][: matrix.shape[1]]
                breakdown = "anderson_kkt_lstsq_fallback"
            if np.all(np.isfinite(coefficients)):
                unbounded_coefficient_l1 = float(np.sum(np.abs(coefficients)))
                max_unbounded_coefficient_l1 = max(
                    max_unbounded_coefficient_l1,
                    unbounded_coefficient_l1,
                )
                if (
                    coefficient_l1_limit is not None
                    and unbounded_coefficient_l1 > float(coefficient_l1_limit)
                    and len(coefficients) > 0
                ):
                    theta = (
                        (float(coefficient_l1_limit) - 1.0)
                        / max(unbounded_coefficient_l1 - 1.0, 1.0e-12)
                    )
                    theta = min(max(theta, 0.0), 1.0)
                    coefficients = coefficients * theta
                    coefficients[-1] += 1.0 - theta
                    coefficient_bounded_count += 1
                    coefficient_l1_was_bounded = True
                coefficient_l1 = float(np.sum(np.abs(coefficients)))
                candidate = np.zeros_like(mapped)
                for coefficient, mapped_row in zip(coefficients, map_history):
                    candidate += float(coefficient) * mapped_row
            else:
                breakdown = "anderson_nonfinite_coefficients"
                candidate = mapped
        increment = float(np.max(np.abs(candidate - u))) if candidate.size else 0.0
        max_abs = max(float(np.max(np.abs(candidate))) if candidate.size else 0.0, 1.0e-9)
        relative_increment = increment / max_abs
        metrics = _translation_metrics(candidate, node_xyz)
        best_map_residual = min(best_map_residual, float(map_residual))
        best_relative_increment = min(best_relative_increment, float(relative_increment))
        max_coefficient_l1 = max(max_coefficient_l1, coefficient_l1)
        rows.append(
            {
                "iteration": int(iteration),
                "map_residual_inf_n": float(map_residual),
                "regularization": float(regularization),
                "max_increment_m": increment,
                "relative_increment": relative_increment,
                "max_translation_m": metrics["max_translation_m"],
                "max_drift_ratio_pct": metrics["max_drift_ratio_pct"],
                "anderson_history_count": len(fixed_point_history),
                "anderson_coefficient_l1": coefficient_l1,
                "anderson_unbounded_coefficient_l1": unbounded_coefficient_l1,
                "coefficient_l1_was_bounded": coefficient_l1_was_bounded,
            }
        )
        ready = bool(
            map_residual <= residual_tolerance_n
            and relative_increment <= relative_increment_tolerance
            and metrics["max_translation_m"] <= displacement_cap_m
        )
        u = candidate
        if ready:
            break
    return {
        "target_load_scale": float(target_load_scale),
        "ready": ready,
        "converged": ready,
        "label": label,
        "iteration_count": len(rows),
        "max_iterations": int(max_iterations),
        "history_depth": int(history_depth),
        "coefficient_l1_limit": (
            float(coefficient_l1_limit) if coefficient_l1_limit is not None else None
        ),
        "coefficient_bounded_count": int(coefficient_bounded_count),
        "best_map_residual_inf_n": float(best_map_residual),
        "best_relative_increment": float(best_relative_increment),
        "final_map_residual_inf_n": rows[-1]["map_residual_inf_n"] if rows else None,
        "final_relative_increment": rows[-1]["relative_increment"] if rows else None,
        "relative_increment_tolerance": float(relative_increment_tolerance),
        "residual_tolerance_n": float(residual_tolerance_n),
        "max_coefficient_l1": max_coefficient_l1,
        "max_unbounded_coefficient_l1": max_unbounded_coefficient_l1,
        "history_tail": rows[-6:],
        "seconds": time.perf_counter() - started,
        "breakdown": breakdown,
        "claim_boundary": (
            "Constrained Anderson acceleration on the existing deformed-state P-Delta fixed-point map. "
            "Optional coefficient L1 limiting blends unstable extrapolation back toward the latest mapped "
            "state. This is a path-following diagnostic only; it does not provide a consistent "
            "Newton/Jacobian or material Newton closure."
        ),
        "_final_displacement": u if ready else None,
        "blockers": [] if ready else ["anderson_acceleration_pdelta_not_closed"],
    }


def _residual_trust_region_anderson_probe(
    *,
    elements: list[Any],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    base_axial_forces: dict[int, float],
    restrained: set[int],
    target_load_scale: float,
    seed_displacement: np.ndarray,
    max_iterations: int = 8,
    history_depth: int = 8,
    residual_tolerance_n: float = 1.0e-3,
    relative_increment_tolerance: float = 1.0e-4,
    displacement_cap_m: float = 80.0,
    blend_factors: tuple[float, ...] = (1.0, 0.5, 0.25),
) -> dict[str, Any]:
    started = time.perf_counter()
    u = np.asarray(seed_displacement, dtype=np.float64).copy()
    fixed_point_history: list[np.ndarray] = []
    map_history: list[np.ndarray] = []
    rows: list[dict[str, Any]] = []
    best_fixed_point_relative_increment = float("inf")
    best_residual = float("inf")
    best_candidate_label = ""
    max_coefficient_l1 = 0.0
    breakdown = ""
    ready = False
    for iteration in range(1, int(max_iterations) + 1):
        mapped, map_residual, regularization = _fixed_point_map(
            elements=elements,
            node_xyz=node_xyz,
            section_props=section_props,
            material_props=material_props,
            base_axial_forces=base_axial_forces,
            restrained=restrained,
            target_load_scale=target_load_scale,
            displacement=u,
        )
        fixed_point = np.asarray(mapped - u, dtype=np.float64)
        fixed_point_history.append(fixed_point)
        map_history.append(np.asarray(mapped, dtype=np.float64))
        if len(fixed_point_history) > int(history_depth):
            fixed_point_history = fixed_point_history[-int(history_depth) :]
            map_history = map_history[-int(history_depth) :]

        candidate_specs: list[tuple[str, np.ndarray, float]] = [("fixed_point_map", mapped, 1.0)]
        coefficient_l1 = 1.0
        if len(fixed_point_history) >= 2:
            matrix = np.column_stack(fixed_point_history)
            gram = matrix.T @ matrix + np.eye(matrix.shape[1], dtype=np.float64) * 1.0e-18
            ones = np.ones((1, matrix.shape[1]), dtype=np.float64)
            kkt = np.block(
                [
                    [gram, ones.T],
                    [ones, np.zeros((1, 1), dtype=np.float64)],
                ]
            )
            rhs = np.zeros(matrix.shape[1] + 1, dtype=np.float64)
            rhs[-1] = 1.0
            try:
                coefficients = np.linalg.solve(kkt, rhs)[: matrix.shape[1]]
            except np.linalg.LinAlgError:
                coefficients = np.linalg.lstsq(kkt, rhs, rcond=None)[0][: matrix.shape[1]]
                breakdown = "trust_region_anderson_kkt_lstsq_fallback"
            if np.all(np.isfinite(coefficients)):
                coefficient_l1 = float(np.sum(np.abs(coefficients)))
                raw_anderson = np.zeros_like(mapped)
                for coefficient, mapped_row in zip(coefficients, map_history):
                    raw_anderson += float(coefficient) * mapped_row
                for blend in blend_factors:
                    blend_value = float(blend)
                    candidate_specs.append(
                        (
                            f"anderson_blend_{blend_value:g}",
                            mapped + blend_value * (raw_anderson - mapped),
                            blend_value,
                        )
                    )
            else:
                breakdown = "trust_region_anderson_nonfinite_coefficients"
        max_coefficient_l1 = max(max_coefficient_l1, coefficient_l1)

        candidate_rows: list[dict[str, Any]] = []
        for label, candidate, blend in candidate_specs:
            remapped, candidate_residual, candidate_regularization = _fixed_point_map(
                elements=elements,
                node_xyz=node_xyz,
                section_props=section_props,
                material_props=material_props,
                base_axial_forces=base_axial_forces,
                restrained=restrained,
                target_load_scale=target_load_scale,
                displacement=candidate,
            )
            fixed_point_increment = float(np.max(np.abs(remapped - candidate))) if candidate.size else 0.0
            remapped_max_abs = max(
                float(np.max(np.abs(remapped))) if remapped.size else 0.0,
                1.0e-9,
            )
            fixed_point_relative_increment = fixed_point_increment / remapped_max_abs
            metrics = _translation_metrics(candidate, node_xyz)
            candidate_ready = bool(
                candidate_residual <= residual_tolerance_n
                and fixed_point_relative_increment <= relative_increment_tolerance
                and metrics["max_translation_m"] <= displacement_cap_m
            )
            candidate_rows.append(
                {
                    "label": label,
                    "blend_factor": blend,
                    "residual_inf_n": float(candidate_residual),
                    "regularization": float(candidate_regularization),
                    "fixed_point_increment_m": fixed_point_increment,
                    "fixed_point_relative_increment": fixed_point_relative_increment,
                    "max_translation_m": metrics["max_translation_m"],
                    "max_drift_ratio_pct": metrics["max_drift_ratio_pct"],
                    "residual_gate_passed": bool(candidate_residual <= residual_tolerance_n),
                    "relative_increment_gate_passed": bool(
                        fixed_point_relative_increment <= relative_increment_tolerance
                    ),
                    "ready": candidate_ready,
                }
            )

        selected = min(
            candidate_rows,
            key=lambda row: (
                not bool(row.get("ready")),
                not bool(row.get("residual_gate_passed")),
                float(row.get("fixed_point_relative_increment") or float("inf")),
                float(row.get("residual_inf_n") or float("inf")),
            ),
        )
        selected_index = candidate_rows.index(selected)
        selected_candidate = candidate_specs[selected_index][1]
        best_fixed_point_relative_increment = min(
            best_fixed_point_relative_increment,
            float(selected.get("fixed_point_relative_increment") or float("inf")),
        )
        best_residual = min(best_residual, float(selected.get("residual_inf_n") or float("inf")))
        best_candidate_label = str(selected.get("label") or best_candidate_label)
        rows.append(
            {
                "iteration": int(iteration),
                "input_map_residual_inf_n": float(map_residual),
                "input_regularization": float(regularization),
                "anderson_history_count": len(fixed_point_history),
                "anderson_coefficient_l1": coefficient_l1,
                "candidate_count": len(candidate_rows),
                "selected_label": selected.get("label"),
                "selected_fixed_point_relative_increment": selected.get(
                    "fixed_point_relative_increment"
                ),
                "selected_residual_inf_n": selected.get("residual_inf_n"),
                "candidate_rows": candidate_rows,
            }
        )
        ready = bool(selected.get("ready"))
        u = selected_candidate
        if ready:
            break

    return {
        "target_load_scale": float(target_load_scale),
        "ready": ready,
        "converged": ready,
        "label": "residual_trust_region_anderson",
        "iteration_count": len(rows),
        "max_iterations": int(max_iterations),
        "history_depth": int(history_depth),
        "blend_factors": [float(value) for value in blend_factors],
        "best_fixed_point_relative_increment": float(best_fixed_point_relative_increment),
        "best_residual_inf_n": float(best_residual),
        "best_candidate_label": best_candidate_label,
        "relative_increment_tolerance": float(relative_increment_tolerance),
        "residual_tolerance_n": float(residual_tolerance_n),
        "max_coefficient_l1": max_coefficient_l1,
        "history_tail": rows[-6:],
        "seconds": time.perf_counter() - started,
        "breakdown": breakdown,
        "claim_boundary": (
            "Residual-trust-region Anderson probe. Unlike damped update diagnostics, every candidate is "
            "remapped through the P-Delta fixed-point operator and closure requires the remapped true "
            "fixed-point relative increment, residual, and displacement gates to pass."
        ),
        "_final_displacement": u if ready else None,
        "blockers": [] if ready else ["residual_trust_region_anderson_not_closed"],
    }


def _micro_step_probe(
    *,
    elements: list[Any],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    base_axial_forces: dict[int, float],
    restrained: set[int],
    seed_load_scale: float,
    seed_displacement: np.ndarray,
    micro_increment: float = 0.005,
    max_iterations: int = 40,
) -> dict[str, Any]:
    target = float(seed_load_scale) + float(micro_increment)
    started = time.perf_counter()
    result, _next_u = _solve_deformed_state_pdelta_fixed_point(
        elements=elements,
        node_xyz=node_xyz,
        section_props=section_props,
        material_props=material_props,
        base_axial_forces=base_axial_forces,
        restrained=restrained,
        target_load_scale=target,
        max_iterations=max_iterations,
        initial_displacement=seed_displacement,
        relaxation_factor=0.5,
        displacement_cap_m=80.0,
    )
    residual = float(result.get("residual_inf_n") or 0.0)
    relative_increment = float(result.get("relative_increment") or 0.0)
    ready = bool(result.get("ready"))
    return {
        "seed_load_scale": float(seed_load_scale),
        "target_load_scale": target,
        "micro_increment": float(micro_increment),
        "ready": ready,
        "converged": bool(result.get("converged")),
        "iteration_count": int(result.get("iteration_count") or 0),
        "residual_inf_n": residual,
        "relative_increment": relative_increment,
        "max_increment_m": float(result.get("max_increment_m") or 0.0),
        "fixed_point_increment_m": float(result.get("fixed_point_increment_m") or 0.0),
        "convergence_increment_metric": str(
            result.get("convergence_increment_metric") or "unrelaxed_fixed_point_relative_increment"
        ),
        "max_translation_m": float(result.get("max_translation_m") or 0.0),
        "max_drift_ratio_pct": float(result.get("max_drift_ratio_pct") or 0.0),
        "residual_tolerance_n": 1.0e-3,
        "relative_increment_tolerance": 1.0e-4,
        "near_displacement_fixed_point": bool(relative_increment <= 1.0e-4),
        "residual_floor_above_tolerance": bool(residual > 1.0e-3),
        "linear_solver_refinement": result.get("linear_solver_refinement")
        or _linear_solver_refinement_policy(),
        "seconds": time.perf_counter() - started,
        "claim_boundary": (
            "A micro-step continuation probe immediately above the last converged load. A ready result proves "
            "local post-converged path-following improvement only; it does not close the later failed load step "
            "or replace a consistent nonlinear Newton/Jacobian."
        ),
        "blockers": [] if ready else ["post_converged_micro_step_not_closed"],
    }


def _adaptive_micro_continuation_probe(
    *,
    elements: list[Any],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    base_axial_forces: dict[int, float],
    restrained: set[int],
    seed_load_scale: float,
    seed_displacement: np.ndarray,
    target_load_scale: float,
    initial_increment: float = 0.005,
    min_increment: float = 0.0025,
    max_attempts: int = 3,
    max_iterations_per_attempt: int = 40,
    relaxation_factor: float = 0.5,
) -> dict[str, Any]:
    started = time.perf_counter()
    current_load = float(seed_load_scale)
    current_u = np.asarray(seed_displacement, dtype=np.float64).copy()
    increment = float(initial_increment)
    rows: list[dict[str, Any]] = []
    first_failed_load: float | None = None
    while len(rows) < int(max_attempts) and current_load < float(target_load_scale) - 1.0e-12:
        attempt_load = min(current_load + increment, float(target_load_scale))
        attempt_started = time.perf_counter()
        result, next_u = _solve_deformed_state_pdelta_fixed_point(
            elements=elements,
            node_xyz=node_xyz,
            section_props=section_props,
            material_props=material_props,
            base_axial_forces=base_axial_forces,
            restrained=restrained,
            target_load_scale=attempt_load,
            max_iterations=max_iterations_per_attempt,
            initial_displacement=current_u,
            relaxation_factor=relaxation_factor,
            displacement_cap_m=80.0,
        )
        residual = float(result.get("residual_inf_n") or 0.0)
        relative_increment = float(result.get("relative_increment") or 0.0)
        ready = bool(result.get("ready"))
        row = {
            "attempt_index": len(rows) + 1,
            "seed_load_scale": float(current_load),
            "target_load_scale": float(attempt_load),
            "micro_increment": float(attempt_load - current_load),
            "ready": ready,
            "accepted_as_path_state": ready,
            "converged": bool(result.get("converged")),
            "iteration_count": int(result.get("iteration_count") or 0),
            "residual_inf_n": residual,
            "relative_increment": relative_increment,
            "max_increment_m": float(result.get("max_increment_m") or 0.0),
            "fixed_point_increment_m": float(result.get("fixed_point_increment_m") or 0.0),
            "convergence_increment_metric": str(
                result.get("convergence_increment_metric")
                or "unrelaxed_fixed_point_relative_increment"
            ),
            "max_translation_m": float(result.get("max_translation_m") or 0.0),
            "max_drift_ratio_pct": float(result.get("max_drift_ratio_pct") or 0.0),
            "residual_tolerance_n": 1.0e-3,
            "relative_increment_tolerance": 1.0e-4,
            "near_displacement_fixed_point": bool(relative_increment <= 1.0e-4),
            "residual_floor_above_tolerance": bool(residual > 1.0e-3),
            "relaxation_factor": float(relaxation_factor),
            "linear_solver_refinement": result.get("linear_solver_refinement")
            or _linear_solver_refinement_policy(),
            "seconds": time.perf_counter() - attempt_started,
            "blockers": [] if ready else ["adaptive_micro_step_not_closed"],
        }
        rows.append(row)
        if ready:
            current_load = float(attempt_load)
            current_u = next_u
            increment = float(initial_increment)
            continue
        if first_failed_load is None:
            first_failed_load = float(attempt_load)
        next_increment = increment * 0.5
        if next_increment < float(min_increment) - 1.0e-12:
            break
        increment = next_increment

    reached_target = current_load >= float(target_load_scale) - 1.0e-12
    return {
        "ready": bool(reached_target),
        "target_load_scale": float(target_load_scale),
        "seed_load_scale": float(seed_load_scale),
        "max_converged_load_scale": float(current_load),
        "first_failed_load_scale": first_failed_load,
        "initial_increment": float(initial_increment),
        "min_increment": float(min_increment),
        "max_attempts": int(max_attempts),
        "attempt_count": len(rows),
        "max_iterations_per_attempt": int(max_iterations_per_attempt),
        "relaxation_factor": float(relaxation_factor),
        "rows": rows,
        "accepted_step_count": int(sum(1 for row in rows if bool(row.get("accepted_as_path_state")))),
        "seconds": time.perf_counter() - started,
        "claim_boundary": (
            "Bounded adaptive micro-step continuation above the last direct converged load. It can promote "
            "accepted micro-steps into the continuation path, but it is not full-load closure unless the "
            "target load is reached."
        ),
        "_final_displacement": current_u,
        "blockers": [] if reached_target else ["adaptive_micro_continuation_not_full_load_closed"],
    }


def _post_failed_relaxation_sensitivity_probe(
    *,
    elements: list[Any],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    base_axial_forces: dict[int, float],
    restrained: set[int],
    seed_load_scale: float,
    seed_displacement: np.ndarray,
    target_load_scale: float,
    relaxation_factors: tuple[float, ...] = (0.25,),
    max_iterations: int = 40,
) -> dict[str, Any]:
    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    for relaxation in relaxation_factors:
        attempt_started = time.perf_counter()
        result, next_u = _solve_deformed_state_pdelta_fixed_point(
            elements=elements,
            node_xyz=node_xyz,
            section_props=section_props,
            material_props=material_props,
            base_axial_forces=base_axial_forces,
            restrained=restrained,
            target_load_scale=float(target_load_scale),
            max_iterations=max_iterations,
            initial_displacement=seed_displacement,
            relaxation_factor=float(relaxation),
            displacement_cap_m=80.0,
        )
        residual = float(result.get("residual_inf_n") or 0.0)
        relative_increment = float(result.get("relative_increment") or 0.0)
        row = {
            "seed_load_scale": float(seed_load_scale),
            "target_load_scale": float(target_load_scale),
            "relaxation_factor": float(relaxation),
            "ready": bool(result.get("ready")),
            "converged": bool(result.get("converged")),
            "iteration_count": int(result.get("iteration_count") or 0),
            "max_iterations": int(max_iterations),
            "residual_inf_n": residual,
            "relative_increment": relative_increment,
            "fixed_point_increment_m": float(result.get("fixed_point_increment_m") or 0.0),
            "max_increment_m": float(result.get("max_increment_m") or 0.0),
            "convergence_increment_metric": str(
                result.get("convergence_increment_metric")
                or "unrelaxed_fixed_point_relative_increment"
            ),
            "max_translation_m": float(result.get("max_translation_m") or 0.0),
            "max_drift_ratio_pct": float(result.get("max_drift_ratio_pct") or 0.0),
            "residual_tolerance_n": 1.0e-3,
            "relative_increment_tolerance": 1.0e-4,
            "near_displacement_fixed_point": bool(relative_increment <= 1.0e-4),
            "residual_floor_above_tolerance": bool(residual > 1.0e-3),
            "seconds": time.perf_counter() - attempt_started,
            "blockers": [] if bool(result.get("ready")) else ["relaxation_sensitivity_not_closed"],
        }
        rows.append(row)
    ready = any(bool(row.get("ready")) for row in rows)
    best_by_residual = min(rows, key=lambda row: float(row.get("residual_inf_n") or float("inf"))) if rows else {}
    best_by_increment = (
        min(rows, key=lambda row: float(row.get("relative_increment") or float("inf"))) if rows else {}
    )
    return {
        "ready": bool(ready),
        "seed_load_scale": float(seed_load_scale),
        "target_load_scale": float(target_load_scale),
        "relaxation_factors": [float(value) for value in relaxation_factors],
        "max_iterations": int(max_iterations),
        "row_count": len(rows),
        "rows": rows,
        "best_residual_inf_n": best_by_residual.get("residual_inf_n"),
        "best_residual_relaxation_factor": best_by_residual.get("relaxation_factor"),
        "best_relative_increment": best_by_increment.get("relative_increment"),
        "best_increment_relaxation_factor": best_by_increment.get("relaxation_factor"),
        "seconds": time.perf_counter() - started,
        "claim_boundary": (
            "Relaxation sensitivity at the first failed post-accepted micro-step. This tests whether a "
            "more conservative fixed-point update can recover the path, but it is not closure unless both "
            "the residual and unrelaxed fixed-point increment meet tolerance."
        ),
        "blockers": [] if ready else ["post_failed_relaxation_sensitivity_not_closed"],
    }


def _secant_predictor_probe(
    *,
    elements: list[Any],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    base_axial_forces: dict[int, float],
    restrained: set[int],
    previous_load_scale: float,
    previous_displacement: np.ndarray,
    seed_load_scale: float,
    seed_displacement: np.ndarray,
    target_load_scale: float,
    relaxation_factors: tuple[float, ...] = (0.5, 0.25),
    max_iterations: int = 50,
) -> dict[str, Any]:
    started = time.perf_counter()
    previous = np.asarray(previous_displacement, dtype=np.float64)
    seed = np.asarray(seed_displacement, dtype=np.float64)
    denominator = max(float(seed_load_scale) - float(previous_load_scale), 1.0e-12)
    extrapolation_factor = (float(target_load_scale) - float(seed_load_scale)) / denominator
    predicted = seed + extrapolation_factor * (seed - previous)
    predictor_increment = float(np.max(np.abs(predicted - seed))) if predicted.size else 0.0
    rows: list[dict[str, Any]] = []
    accepted_displacement: np.ndarray | None = None
    accepted_relaxation_factor: float | None = None
    for relaxation in relaxation_factors:
        attempt_started = time.perf_counter()
        result, next_u = _solve_deformed_state_pdelta_fixed_point(
            elements=elements,
            node_xyz=node_xyz,
            section_props=section_props,
            material_props=material_props,
            base_axial_forces=base_axial_forces,
            restrained=restrained,
            target_load_scale=float(target_load_scale),
            max_iterations=max_iterations,
            initial_displacement=predicted,
            relaxation_factor=float(relaxation),
            displacement_cap_m=80.0,
        )
        residual = float(result.get("residual_inf_n") or 0.0)
        relative_increment = float(result.get("relative_increment") or 0.0)
        row = {
            "previous_load_scale": float(previous_load_scale),
            "seed_load_scale": float(seed_load_scale),
            "target_load_scale": float(target_load_scale),
            "extrapolation_factor": float(extrapolation_factor),
            "predictor_increment_m": predictor_increment,
            "relaxation_factor": float(relaxation),
            "ready": bool(result.get("ready")),
            "converged": bool(result.get("converged")),
            "iteration_count": int(result.get("iteration_count") or 0),
            "max_iterations": int(max_iterations),
            "residual_inf_n": residual,
            "relative_increment": relative_increment,
            "fixed_point_increment_m": float(result.get("fixed_point_increment_m") or 0.0),
            "max_increment_m": float(result.get("max_increment_m") or 0.0),
            "convergence_increment_metric": str(
                result.get("convergence_increment_metric")
                or "unrelaxed_fixed_point_relative_increment"
            ),
            "max_translation_m": float(result.get("max_translation_m") or 0.0),
            "max_drift_ratio_pct": float(result.get("max_drift_ratio_pct") or 0.0),
            "residual_tolerance_n": 1.0e-3,
            "relative_increment_tolerance": 1.0e-4,
            "residual_gate_passed": bool(residual <= 1.0e-3),
            "relative_increment_gate_passed": bool(relative_increment <= 1.0e-4),
            "accepted_as_path_state": bool(result.get("ready")),
            "seconds": time.perf_counter() - attempt_started,
            "blockers": [] if bool(result.get("ready")) else ["secant_predictor_not_closed"],
        }
        rows.append(row)
        if bool(result.get("ready")) and accepted_displacement is None:
            accepted_displacement = np.asarray(next_u, dtype=np.float64)
            accepted_relaxation_factor = float(relaxation)
    ready = any(bool(row.get("ready")) for row in rows)
    best_by_residual = min(rows, key=lambda row: float(row.get("residual_inf_n") or float("inf"))) if rows else {}
    best_by_increment = (
        min(rows, key=lambda row: float(row.get("relative_increment") or float("inf"))) if rows else {}
    )
    return {
        "ready": bool(ready),
        "previous_load_scale": float(previous_load_scale),
        "seed_load_scale": float(seed_load_scale),
        "target_load_scale": float(target_load_scale),
        "extrapolation_factor": float(extrapolation_factor),
        "predictor_increment_m": predictor_increment,
        "relaxation_factors": [float(value) for value in relaxation_factors],
        "max_iterations": int(max_iterations),
        "row_count": len(rows),
        "rows": rows,
        "best_residual_inf_n": best_by_residual.get("residual_inf_n"),
        "best_residual_relaxation_factor": best_by_residual.get("relaxation_factor"),
        "best_relative_increment": best_by_increment.get("relative_increment"),
        "best_increment_relaxation_factor": best_by_increment.get("relaxation_factor"),
        "residual_gate_passed_by_any": any(bool(row.get("residual_gate_passed")) for row in rows),
        "relative_increment_gate_passed_by_any": any(
            bool(row.get("relative_increment_gate_passed")) for row in rows
        ),
        "accepted_as_path_state": bool(accepted_displacement is not None),
        "accepted_load_scale": float(target_load_scale) if accepted_displacement is not None else None,
        "accepted_relaxation_factor": accepted_relaxation_factor,
        "seconds": time.perf_counter() - started,
        "claim_boundary": (
            "Secant displacement predictor from two accepted P-Delta states. It tests whether a path "
            "predictor can improve the failed next micro-step. It is not closure unless one row passes "
            "both residual and unrelaxed fixed-point increment gates."
        ),
        "_accepted_displacement": accepted_displacement,
        "blockers": [] if ready else ["secant_predictor_not_closed"],
    }


def _secant_micro_continuation_probe(
    *,
    elements: list[Any],
    node_xyz: np.ndarray,
    section_props: dict[int, dict[str, Any]],
    material_props: dict[int, dict[str, Any]],
    base_axial_forces: dict[int, float],
    restrained: set[int],
    previous_load_scale: float,
    previous_displacement: np.ndarray,
    seed_load_scale: float,
    seed_displacement: np.ndarray,
    target_load_scale: float,
    initial_increment: float = 0.0025,
    min_increment: float = 0.00125,
    max_attempts: int = 2,
    relaxation_factors: tuple[float, ...] = (0.25,),
    max_iterations_per_attempt: int = 50,
) -> dict[str, Any]:
    started = time.perf_counter()
    previous_load = float(previous_load_scale)
    previous_u = np.asarray(previous_displacement, dtype=np.float64).copy()
    current_load = float(seed_load_scale)
    current_u = np.asarray(seed_displacement, dtype=np.float64).copy()
    increment = float(initial_increment)
    rows: list[dict[str, Any]] = []
    accepted_count = 0
    first_failed_load: float | None = None
    while len(rows) < int(max_attempts) and current_load < float(target_load_scale) - 1.0e-12:
        attempt_load = min(current_load + increment, float(target_load_scale))
        attempt = _secant_predictor_probe(
            elements=elements,
            node_xyz=node_xyz,
            section_props=section_props,
            material_props=material_props,
            base_axial_forces=base_axial_forces,
            restrained=restrained,
            previous_load_scale=previous_load,
            previous_displacement=previous_u,
            seed_load_scale=current_load,
            seed_displacement=current_u,
            target_load_scale=attempt_load,
            relaxation_factors=relaxation_factors,
            max_iterations=max_iterations_per_attempt,
        )
        accepted_u = attempt.pop("_accepted_displacement", None)
        row = {
            "attempt_index": len(rows) + 1,
            "previous_load_scale": previous_load,
            "seed_load_scale": current_load,
            "target_load_scale": float(attempt_load),
            "micro_increment": float(attempt_load - current_load),
            "ready": bool(attempt.get("ready")),
            "accepted_as_path_state": bool(attempt.get("accepted_as_path_state")),
            "best_residual_inf_n": attempt.get("best_residual_inf_n"),
            "best_relative_increment": attempt.get("best_relative_increment"),
            "best_residual_relaxation_factor": attempt.get("best_residual_relaxation_factor"),
            "best_increment_relaxation_factor": attempt.get("best_increment_relaxation_factor"),
            "residual_gate_passed_by_any": attempt.get("residual_gate_passed_by_any"),
            "relative_increment_gate_passed_by_any": attempt.get(
                "relative_increment_gate_passed_by_any"
            ),
            "predictor": attempt,
            "blockers": [] if bool(attempt.get("ready")) else ["secant_micro_step_not_closed"],
        }
        rows.append(row)
        if bool(attempt.get("ready")) and accepted_u is not None:
            accepted_count += 1
            previous_load = current_load
            previous_u = current_u
            current_load = float(attempt_load)
            current_u = np.asarray(accepted_u, dtype=np.float64)
            increment = float(initial_increment)
            continue
        if first_failed_load is None:
            first_failed_load = float(attempt_load)
        next_increment = increment * 0.5
        if next_increment < float(min_increment) - 1.0e-12:
            break
        increment = next_increment

    reached_target = current_load >= float(target_load_scale) - 1.0e-12
    return {
        "ready": bool(reached_target),
        "target_load_scale": float(target_load_scale),
        "initial_previous_load_scale": float(previous_load_scale),
        "initial_seed_load_scale": float(seed_load_scale),
        "max_converged_load_scale": float(current_load),
        "first_failed_load_scale": first_failed_load,
        "initial_increment": float(initial_increment),
        "min_increment": float(min_increment),
        "max_attempts": int(max_attempts),
        "attempt_count": len(rows),
        "accepted_step_count": int(accepted_count),
        "relaxation_factors": [float(value) for value in relaxation_factors],
        "max_iterations_per_attempt": int(max_iterations_per_attempt),
        "rows": rows,
        "seconds": time.perf_counter() - started,
        "claim_boundary": (
            "Bounded secant-predictor micro-continuation after the first accepted secant step. It can "
            "advance the accepted P-Delta frontier, but it is not full-load closure unless the target "
            "load is reached and every accepted row passes both residual and unrelaxed fixed-point gates."
        ),
        "_final_displacement": current_u,
        "blockers": [] if reached_target else ["secant_micro_continuation_not_full_load_closed"],
    }


def run_mgt_pdelta_continuation_probe(
    *,
    roundtrip_json: Path = DEFAULT_ROUNDTRIP,
    roundtrip_npz: Path | None = None,
    output_json: Path | None = None,
    load_steps: tuple[float, ...] = (0.5, 0.55, 1.0),
    max_iterations_per_step: int = 28,
    frontier_correction_passes: int = 4,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    roundtrip_npz = roundtrip_npz or roundtrip_json.with_suffix(".npz")
    if not roundtrip_npz.is_file():
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "status": "blocked",
            "blockers": ["roundtrip_npz_missing"],
        }
        if output_json is not None:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload

    provenance = build_mgt_reanalysis_provenance(roundtrip_json=roundtrip_json)
    mgt_path = Path(str(provenance.get("mgt_path") or ""))
    props = load_mgt_section_material_properties(mgt_path) if mgt_path.is_file() else {"sections": {}, "materials": {}}
    section_props = props.get("sections") if isinstance(props.get("sections"), dict) else {}
    material_props = props.get("materials") if isinstance(props.get("materials"), dict) else {}
    beam_end_offsets = _beam_end_offset_lookup(props.get("beam_end_offsets"))
    roundtrip = _load_json(roundtrip_json)

    with np.load(roundtrip_npz, allow_pickle=False) as archive:
        elem_id = np.asarray(archive["elem_id"], dtype=np.int64)
        elem_angle_deg = (
            np.asarray(archive["elem_angle_deg"], dtype=np.float64)
            if "elem_angle_deg" in archive.files
            else _element_angle_array_from_props(props, elem_id)
        )
        elements, node_xyz_sub, select_meta = _select_full_line_mesh(
            node_xyz=np.asarray(archive["node_xyz"], dtype=np.float64),
            edge_index=np.asarray(archive["edge_index"], dtype=np.int64),
            elem_id=elem_id,
            elem_type_code=np.asarray(archive["elem_type_code"], dtype=np.int32),
            elem_section_id=np.asarray(archive["elem_section_id"], dtype=np.int32),
            elem_material_id=np.asarray(archive["elem_material_id"], dtype=np.int32),
            elem_angle_deg=elem_angle_deg,
            beam_end_offsets=beam_end_offsets,
        )

    restrained, component_count, base_node_count = _component_restraints(elements, node_xyz_sub)
    axial_forces = _component_gravity_axial_forces(
        elements=elements,
        node_xyz=node_xyz_sub,
        section_props=section_props,
        material_props=material_props,
    )
    n_dof = int(node_xyz_sub.shape[0]) * DOF_PER_NODE
    u = np.zeros(n_dof, dtype=np.float64)
    step_results: list[dict[str, Any]] = []
    max_converged = 0.0
    first_failed: float | None = None
    line_search_probe: dict[str, Any] | None = None
    anderson_probe: dict[str, Any] | None = None
    coefficient_bounded_anderson_probe: dict[str, Any] | None = None
    residual_trust_region_anderson_probe: dict[str, Any] | None = None
    post_converged_micro_step_probe: dict[str, Any] | None = None
    adaptive_micro_continuation_probe: dict[str, Any] | None = None
    post_failed_relaxation_sensitivity_probe: dict[str, Any] | None = None
    secant_predictor_probe: dict[str, Any] | None = None
    secant_micro_continuation_probe: dict[str, Any] | None = None
    fine_secant_micro_continuation_probe: dict[str, Any] | None = None
    frontier_residual_jacobian_probe: dict[str, Any] | None = None
    direct_max_converged = 0.0
    started = time.perf_counter()
    pdelta_fixed_point_linear_solver_refinement = _linear_solver_refinement_policy()
    for idx, step in enumerate(load_steps):
        step_started = time.perf_counter()
        relaxation = 1.0 if idx == 0 else 0.7
        result, next_u = _solve_deformed_state_pdelta_fixed_point(
            elements=elements,
            node_xyz=node_xyz_sub,
            section_props=section_props,
            material_props=material_props,
            base_axial_forces=axial_forces,
            restrained=restrained,
            target_load_scale=float(step),
            max_iterations=max_iterations_per_step,
            initial_displacement=None if idx == 0 else u,
            relaxation_factor=relaxation,
            displacement_cap_m=80.0,
        )
        row = {
            "load_step": float(step),
            "seconds": time.perf_counter() - step_started,
            "ready": bool(result.get("ready")),
            "converged": bool(result.get("converged")),
            "iteration_count": int(result.get("iteration_count") or 0),
            "residual_inf_n": float(result.get("residual_inf_n") or 0.0),
            "relative_increment": float(result.get("relative_increment") or 0.0),
            "max_translation_m": float(result.get("max_translation_m") or 0.0),
            "max_drift_ratio_pct": float(result.get("max_drift_ratio_pct") or 0.0),
            "fixed_point_increment_m": float(result.get("fixed_point_increment_m") or 0.0),
            "convergence_increment_metric": str(
                result.get("convergence_increment_metric")
                or "unrelaxed_fixed_point_relative_increment"
            ),
            "relaxation_factor": float(result.get("relaxation_factor") or relaxation),
            "initial_displacement_was_seeded": bool(result.get("initial_displacement_was_seeded")),
            "linear_solver_refinement_enabled": bool(
                (result.get("linear_solver_refinement") or {}).get("enabled")
            ),
            "linear_solver_refinement_strategy": str(
                (result.get("linear_solver_refinement") or {}).get("strategy") or ""
            ),
            "blockers": result.get("blockers") or [],
        }
        step_results.append(row)
        if bool(result.get("ready")):
            max_converged = float(step)
            direct_max_converged = float(step)
            u = next_u
            continue
        first_failed = float(step)
        if max_converged > 0.0:
            adaptive_micro_continuation_probe = _adaptive_micro_continuation_probe(
                elements=elements,
                node_xyz=node_xyz_sub,
                section_props=section_props,
                material_props=material_props,
                base_axial_forces=axial_forces,
                restrained=restrained,
                seed_load_scale=max_converged,
                seed_displacement=u,
                target_load_scale=float(step),
            )
            adaptive_final_u = adaptive_micro_continuation_probe.pop("_final_displacement", None)
            adaptive_rows = adaptive_micro_continuation_probe.get("rows") or []
            post_converged_micro_step_probe = (
                adaptive_rows[0] if adaptive_rows and isinstance(adaptive_rows[0], dict) else None
            )
            failed_half_step_rows = [
                row
                for row in adaptive_rows
                if isinstance(row, dict)
                and not bool(row.get("ready"))
                and float(row.get("target_load_scale") or 0.0) < float(step)
            ]
            if adaptive_final_u is not None and failed_half_step_rows:
                post_failed_relaxation_sensitivity_probe = _post_failed_relaxation_sensitivity_probe(
                    elements=elements,
                    node_xyz=node_xyz_sub,
                    section_props=section_props,
                    material_props=material_props,
                    base_axial_forces=axial_forces,
                    restrained=restrained,
                    seed_load_scale=float(adaptive_micro_continuation_probe.get("max_converged_load_scale") or max_converged),
                    seed_displacement=np.asarray(adaptive_final_u, dtype=np.float64),
                    target_load_scale=float(failed_half_step_rows[-1].get("target_load_scale") or step),
                )
                secant_predictor_probe = _secant_predictor_probe(
                    elements=elements,
                    node_xyz=node_xyz_sub,
                    section_props=section_props,
                    material_props=material_props,
                    base_axial_forces=axial_forces,
                    restrained=restrained,
                    previous_load_scale=float(max_converged),
                    previous_displacement=u,
                    seed_load_scale=float(
                        adaptive_micro_continuation_probe.get("max_converged_load_scale")
                        or max_converged
                    ),
                    seed_displacement=np.asarray(adaptive_final_u, dtype=np.float64),
                    target_load_scale=float(failed_half_step_rows[-1].get("target_load_scale") or step),
                )
                secant_accepted_u = secant_predictor_probe.pop("_accepted_displacement", None)
                if secant_accepted_u is not None:
                    secant_accepted_load = float(
                        secant_predictor_probe.get("accepted_load_scale") or 0.0
                    )
                    secant_micro_continuation_probe = _secant_micro_continuation_probe(
                        elements=elements,
                        node_xyz=node_xyz_sub,
                        section_props=section_props,
                        material_props=material_props,
                        base_axial_forces=axial_forces,
                        restrained=restrained,
                        previous_load_scale=float(
                            adaptive_micro_continuation_probe.get("max_converged_load_scale")
                            or max_converged
                        ),
                        previous_displacement=np.asarray(adaptive_final_u, dtype=np.float64),
                        seed_load_scale=secant_accepted_load,
                        seed_displacement=np.asarray(secant_accepted_u, dtype=np.float64),
                        target_load_scale=float(step),
                    )
                    secant_micro_final_u = secant_micro_continuation_probe.pop(
                        "_final_displacement",
                        None,
                    )
                    fine_secant_final_u = None
                    if not bool(secant_micro_continuation_probe.get("ready")):
                        fine_secant_micro_continuation_probe = _secant_micro_continuation_probe(
                            elements=elements,
                            node_xyz=node_xyz_sub,
                            section_props=section_props,
                            material_props=material_props,
                            base_axial_forces=axial_forces,
                            restrained=restrained,
                            previous_load_scale=float(
                                adaptive_micro_continuation_probe.get("max_converged_load_scale")
                                or max_converged
                            ),
                            previous_displacement=np.asarray(adaptive_final_u, dtype=np.float64),
                            seed_load_scale=secant_accepted_load,
                            seed_displacement=np.asarray(secant_accepted_u, dtype=np.float64),
                            target_load_scale=float(step),
                            initial_increment=0.000625,
                            min_increment=0.000078125,
                            max_attempts=4,
                            relaxation_factors=(0.25,),
                            max_iterations_per_attempt=60,
                        )
                        fine_secant_final_u = fine_secant_micro_continuation_probe.pop(
                            "_final_displacement",
                            None,
                        )
                    max_converged = max(
                        max_converged,
                        secant_accepted_load,
                        float(
                            secant_micro_continuation_probe.get("max_converged_load_scale")
                            or 0.0
                        ),
                        float(
                            (fine_secant_micro_continuation_probe or {}).get(
                                "max_converged_load_scale"
                            )
                            or 0.0
                        ),
                    )
                    u = (
                        np.asarray(fine_secant_final_u, dtype=np.float64)
                        if fine_secant_final_u is not None
                        else
                        np.asarray(secant_micro_final_u, dtype=np.float64)
                        if secant_micro_final_u is not None
                        else np.asarray(secant_accepted_u, dtype=np.float64)
                    )
                    failed_frontier_rows = [
                        row
                        for row in (fine_secant_micro_continuation_probe or {}).get("rows", [])
                        if isinstance(row, dict)
                        and not bool(row.get("ready"))
                        and float(row.get("target_load_scale") or 0.0) > max_converged
                    ]
                    if failed_frontier_rows:
                        nearest_failed_after_frontier = min(
                            float(row.get("target_load_scale") or step)
                            for row in failed_frontier_rows
                        )
                        frontier_residual_jacobian_probe = _frontier_residual_jacobian_probe(
                            elements=elements,
                            node_xyz=node_xyz_sub,
                            section_props=section_props,
                            material_props=material_props,
                            base_axial_forces=axial_forces,
                            restrained=restrained,
                            seed_load_scale=max_converged,
                            seed_displacement=u,
                            target_load_scale=nearest_failed_after_frontier,
                            correction_passes=frontier_correction_passes,
                        )
                        frontier_newton_u = frontier_residual_jacobian_probe.pop(
                            "_accepted_displacement",
                            None,
                        )
                        if (
                            bool(frontier_residual_jacobian_probe.get("ready"))
                            and frontier_newton_u is not None
                        ):
                            max_converged = max(max_converged, nearest_failed_after_frontier)
                            u = np.asarray(frontier_newton_u, dtype=np.float64)
            max_converged = max(
                max_converged,
                float(adaptive_micro_continuation_probe.get("max_converged_load_scale") or 0.0),
            )
        line_search_probe = _one_step_line_search_probe(
            elements=elements,
            node_xyz=node_xyz_sub,
            section_props=section_props,
            material_props=material_props,
            base_axial_forces=axial_forces,
            restrained=restrained,
            target_load_scale=float(step),
            seed_displacement=u,
        )
        anderson_probe = _anderson_acceleration_probe(
            elements=elements,
            node_xyz=node_xyz_sub,
            section_props=section_props,
            material_props=material_props,
            base_axial_forces=axial_forces,
            restrained=restrained,
            target_load_scale=float(step),
            seed_displacement=u,
        )
        anderson_final_u = anderson_probe.pop("_final_displacement", None)
        if bool(anderson_probe.get("ready")) and anderson_final_u is not None:
            max_converged = max(max_converged, float(step))
            u = np.asarray(anderson_final_u, dtype=np.float64)
        else:
            coefficient_bounded_anderson_probe = _anderson_acceleration_probe(
                elements=elements,
                node_xyz=node_xyz_sub,
                section_props=section_props,
                material_props=material_props,
                base_axial_forces=axial_forces,
                restrained=restrained,
                target_load_scale=float(step),
                seed_displacement=u,
                coefficient_l1_limit=8.0,
                label="coefficient_bounded_anderson_l1_8",
            )
            bounded_anderson_final_u = coefficient_bounded_anderson_probe.pop(
                "_final_displacement",
                None,
            )
            if (
                bool(coefficient_bounded_anderson_probe.get("ready"))
                and bounded_anderson_final_u is not None
            ):
                max_converged = max(max_converged, float(step))
                u = np.asarray(bounded_anderson_final_u, dtype=np.float64)
            else:
                residual_trust_region_anderson_probe = _residual_trust_region_anderson_probe(
                    elements=elements,
                    node_xyz=node_xyz_sub,
                    section_props=section_props,
                    material_props=material_props,
                    base_axial_forces=axial_forces,
                    restrained=restrained,
                    target_load_scale=float(step),
                    seed_displacement=u,
                )
                trust_region_final_u = residual_trust_region_anderson_probe.pop(
                    "_final_displacement",
                    None,
                )
                if (
                    bool(residual_trust_region_anderson_probe.get("ready"))
                    and trust_region_final_u is not None
                ):
                    max_converged = max(max_converged, float(step))
                    u = np.asarray(trust_region_final_u, dtype=np.float64)
        break

    full_load_ready = max_converged >= 1.0
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if full_load_ready else "partial",
        "roundtrip_json": str(roundtrip_json),
        "roundtrip_npz": str(roundtrip_npz),
        "mgt_path": str(mgt_path),
        "mgt_sha256": str((roundtrip.get("source") or {}).get("sha256") or ""),
        "solve_scope": "full_mgt_6dof_frame_deformed_state_pdelta_load_step_continuation_probe",
        "full_load_pdelta_continuation_ready": full_load_ready,
        "full_load_nonlinear_newton_ready": False,
        "material_newton_ready": False,
        "pdelta_fixed_point_linear_solver_refinement": pdelta_fixed_point_linear_solver_refinement,
        "line_search_linear_solver": {
            "strategy": "single_direct_spsolve_on_regularized_residual_system",
            "uses_frame_solver_iterative_refinement": False,
            "claim_boundary": (
                "The one-step line-search probe diagnoses the nonlinear residual/Jacobian gap. "
                "It deliberately does not hide that gap with the frame fixed-point refinement policy."
            ),
        },
        "frontier_residual_jacobian_requested_correction_passes": int(
            frontier_correction_passes
        ),
        "max_converged_load_scale": float(max_converged),
        "direct_load_step_max_converged_load_scale": float(direct_max_converged),
        "first_failed_load_scale": first_failed,
        "post_converged_micro_step_probe": post_converged_micro_step_probe,
        "adaptive_micro_continuation_probe": adaptive_micro_continuation_probe,
        "post_failed_relaxation_sensitivity_probe": post_failed_relaxation_sensitivity_probe,
        "secant_predictor_probe": secant_predictor_probe,
        "secant_micro_continuation_probe": secant_micro_continuation_probe,
        "fine_secant_micro_continuation_probe": fine_secant_micro_continuation_probe,
        "frontier_residual_jacobian_probe": frontier_residual_jacobian_probe,
        "first_failed_one_step_line_search_probe": line_search_probe,
        "first_failed_anderson_acceleration_probe": anderson_probe,
        "first_failed_coefficient_bounded_anderson_probe": coefficient_bounded_anderson_probe,
        "first_failed_residual_trust_region_anderson_probe": residual_trust_region_anderson_probe,
        "load_steps_requested": [float(value) for value in load_steps],
        "step_results": step_results,
        "mesh_fingerprint": {
            **select_meta,
            "line_elements_solved": int(len(elements)),
            "line_nodes_solved": int(node_xyz_sub.shape[0]),
            "component_count": int(component_count),
            "base_node_count": int(base_node_count),
            "dof_count": int(n_dof),
        },
        "runtime_metrics": {
            "backend": "scipy_sparse_spsolve_cpu_6dof_frame_pdelta_continuation_probe",
            "total_seconds": time.perf_counter() - started,
        },
        "claim_boundary": (
            "This is a deterministic continuation probe for the existing deformed-state P-Delta fixed-point "
            "path. A failed step is evidence that full-load closure needs a consistent Newton/Jacobian or "
            "stronger path-following method; it is not itself a full-load nonlinear closure."
        ),
        "blockers": []
        if full_load_ready
        else [
            "full_load_pdelta_continuation_not_converged",
            "consistent_newton_jacobian_required",
            *(
                []
                if (anderson_probe or {}).get("ready")
                else ["anderson_acceleration_pdelta_not_closed"]
            ),
        ],
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip-json", type=Path, default=DEFAULT_ROUNDTRIP)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--max-iterations-per-step", type=int, default=28)
    parser.add_argument("--frontier-correction-passes", type=int, default=4)
    parser.add_argument("--load-steps", default="0.5,0.55,1.0")
    args = parser.parse_args()
    load_steps = tuple(float(value.strip()) for value in str(args.load_steps).split(",") if value.strip())
    payload = run_mgt_pdelta_continuation_probe(
        roundtrip_json=args.roundtrip_json,
        roundtrip_npz=args.roundtrip_npz,
        output_json=args.output_json,
        load_steps=load_steps,
        max_iterations_per_step=int(args.max_iterations_per_step),
        frontier_correction_passes=int(args.frontier_correction_passes),
    )
    print(
        f"mgt-pdelta-continuation: {payload['status']} "
        f"max_load={payload['max_converged_load_scale']} "
        f"failed={payload['first_failed_load_scale']} -> {args.output_json}"
    )


if __name__ == "__main__":
    main()
