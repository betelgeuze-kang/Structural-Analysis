"""Noncommitting same-parent seed observations; never a solver acceptance gate."""

from time import perf_counter_ns

from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
    StatefulFiberFrame2DDisplacementControlConfig,
    StatefulFiberFrame2DDisplacementControlStepAdapter,
)
from structural_analysis.solvers.nonlinear.newton import _relative_residual_vector


def observe_rc_control_initial_residuals(
    problem, parent, *, control_global_dof, target_m, candidates, config=None
):
    """Assemble up to sixteen named seeds without Newton or checkpoint commit.

    All inputs are validated before any assembly. On an assembly exception, retain
    its attempt and stop; partial work is explicitly unknown. The parent must
    remain byte-identical on both successful and failed observations.
    """
    started = perf_counter_ns()
    if type(candidates) is not dict or not 1 <= len(candidates) <= 16:
        raise ValueError("one to sixteen named candidates required")
    if any(type(name) is not str or not name or len(name) > 128 for name in candidates):
        raise ValueError("bounded nonempty candidate names required")
    cfg = (
        config
        if config is not None
        else StatefulFiberFrame2DDisplacementControlConfig()
    )
    adapters = [
        (
            name,
            StatefulFiberFrame2DDisplacementControlStepAdapter(
                problem, parent, control_global_dof, target_m, cfg, coordinates
            ),
        )
        for name, coordinates in candidates.items()
    ]
    # A missing seed would implicitly request the parent's initial guess.
    if any(adapter.initial_augmented_coordinates_m is None for _, adapter in adapters):
        raise ValueError("explicit candidate coordinates required")
    before = parent.canonical_bytes()
    rows = []
    for name, adapter in adapters:
        tick = perf_counter_ns()
        row = {
            "name": name,
            "status": "failed",
            "assembly_attempts": 0,
            "unknown_work": True,
        }
        try:
            coordinates = adapter.initial_free_displacements_m()
            row["assembly_attempts"] = 1
            observation = adapter.observe(coordinates)
            relative = _relative_residual_vector(
                adapter, observation.augmented_residual_kn
            )
            row.update(
                status="observed",
                unknown_work=False,
                initial_augmented_coordinates_m=list(
                    adapter.initial_augmented_coordinates_m
                ),
                initial_solver_coordinates_m=coordinates.tolist(),
                residual_kn=observation.augmented_residual_kn.tolist(),
                relative_residual=relative,
                residual_gate_passed=relative <= cfg.newton.residual_tolerance,
                control_error_m=observation.control_error_m,
            )
        except Exception as exc:
            row["error_type"] = type(exc).__name__
            row["error"] = str(exc)
        finally:
            row["wall_ns"] = perf_counter_ns() - tick
            if parent.canonical_bytes() != before:
                raise RuntimeError("residual observation mutated the accepted parent")
        rows.append(row)
        if row["unknown_work"]:
            break
    return {
        "schema_version": "rc-control-initial-residual-observation.v1",
        "parent_hash": parent.state_hash,
        "requested_candidates": len(adapters),
        "control_global_dof": control_global_dof,
        "target_m": float(target_m),
        "residual_tolerance": cfg.newton.residual_tolerance,
        "control_tolerance_m": cfg.control_tolerance_m,
        "load_factor_coordinate_scale_m": cfg.load_factor_coordinate_scale_m,
        "reference_force_scale": adapters[0][1].reference_force_scale(),
        "rows": rows,
        "complete": len(rows) == len(adapters)
        and all(row["status"] == "observed" for row in rows),
        "parent_unchanged": True,
        "newton_solves": 0,
        "committed": False,
        "candidate_selected": False,
        "wall_ns": perf_counter_ns() - started,
        "cost_scope": "validation and full residual/tangent assemblies; no nonlinear solve",
        "qualification_claim": False,
    }
