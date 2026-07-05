"""Shared G1 physical residual/Jacobian assembly contract helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from structural_analysis.solvers.nonlinear.newton import RESIDUAL_FORMULA

G1_ASSEMBLY_CONTRACT_SCHEMA = "g1-assembly-result.v1"
PHYSICAL_RESIDUAL_SOURCE = "physical_direct_residual"
TANGENT_DEFINITION = "dR_du_consistent"
PROHIBITED_RESIDUAL_SUBSTITUTES = (
    "fixed_point_residual",
    "map_residual",
    "regularized_residual",
    "solver_normalized_residual",
)
PROHIBITED_SUBSTITUTE_METRIC_KEYS = (
    "fixed_point_residual_used_as_physical",
    "map_residual_used_as_physical",
    "regularized_fixed_point_substitute",
    "solver_normalized_residual_used_as_physical",
)


@dataclass(frozen=True)
class AssemblyResult:
    """Canonical physical assembly envelope for G1-style Newton gates.

    The residual is always the free-DOF block of
    ``F_internal(u, s) - F_external(lambda)``. Solver-only fixed-point, map, or
    regularized residuals can be recorded elsewhere, but this envelope rejects
    them when they are marked as the physical residual.
    """

    residual_formula: str
    residual_free: np.ndarray
    tangent_free: np.ndarray
    internal_forces: np.ndarray
    external_forces: np.ndarray
    material_state_next: dict[str, Any]
    metrics: dict[str, Any] = field(default_factory=dict)
    residual_source: str = PHYSICAL_RESIDUAL_SOURCE
    tangent_definition: str = TANGENT_DEFINITION
    schema_version: str = field(default=G1_ASSEMBLY_CONTRACT_SCHEMA, init=False)

    def __post_init__(self) -> None:
        residual_free = _as_1d_array("residual_free", self.residual_free)
        tangent_free = _as_2d_array("tangent_free", self.tangent_free)
        internal_forces = _as_1d_array("internal_forces", self.internal_forces)
        external_forces = _as_1d_array("external_forces", self.external_forces)
        material_state_next = dict(self.material_state_next)
        metrics = dict(self.metrics)

        if self.residual_formula != RESIDUAL_FORMULA:
            raise ValueError(
                f"AssemblyResult residual_formula must be {RESIDUAL_FORMULA!r}."
            )
        if tangent_free.shape != (residual_free.size, residual_free.size):
            raise ValueError(
                "AssemblyResult tangent_free must be square with one row/column "
                "per free residual DOF."
            )
        if internal_forces.shape != external_forces.shape:
            raise ValueError(
                "AssemblyResult internal_forces and external_forces must share shape."
            )
        _assert_not_prohibited_residual_substitute(self.residual_source, metrics)
        _assert_residual_matches_internal_external(
            residual_free,
            internal_forces,
            external_forces,
            metrics,
        )

        object.__setattr__(self, "residual_free", residual_free)
        object.__setattr__(self, "tangent_free", tangent_free)
        object.__setattr__(self, "internal_forces", internal_forces)
        object.__setattr__(self, "external_forces", external_forces)
        object.__setattr__(self, "material_state_next", material_state_next)
        object.__setattr__(self, "metrics", metrics)

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-serializable non-promoting receipt payload."""

        return {
            "schema_version": self.schema_version,
            "residual_formula": self.residual_formula,
            "residual_source": self.residual_source,
            "tangent_definition": self.tangent_definition,
            "residual_free": self.residual_free.tolist(),
            "tangent_free": self.tangent_free.tolist(),
            "internal_forces": self.internal_forces.tolist(),
            "external_forces": self.external_forces.tolist(),
            "material_state_next": self.material_state_next,
            "metrics": self.metrics,
        }

    def contract_check(self) -> dict[str, Any]:
        """Summarize the contract gates that were enforced at construction."""

        residual_norm = _inf_norm(self.residual_free)
        tangent_norm = _inf_norm(self.tangent_free)
        return {
            "schema_version": "g1-assembly-contract-check.v1",
            "contract_pass": True,
            "residual_formula": self.residual_formula,
            "residual_source": self.residual_source,
            "tangent_definition": self.tangent_definition,
            "free_dof_count": int(self.residual_free.size),
            "residual_inf_norm": residual_norm,
            "tangent_inf_norm": tangent_norm,
            "fixed_point_residual_used_as_physical": False,
            "regularized_fixed_point_substitute": False,
        }


def assembly_result_from_axial_chain_state(state: Any) -> AssemblyResult:
    """Adapt the axial-chain assembly seed into the shared G1 envelope."""

    free_node_indices = tuple(int(index) for index in state.free_node_indices)
    element_material_states = []
    for row in state.element_forces_kn:
        element_material_states.append(
            {
                "element_id": row.get("element_id"),
                "material_state_policy": "stateless_trial_equals_committed_seed",
                "elongation_m": row.get("elongation_m"),
                "internal_force_kn": row.get("internal_force_kn"),
                "tangent_kn_per_m": row.get("tangent_kn_per_m"),
                "path_dependent_state_updated": False,
            }
        )
    return AssemblyResult(
        residual_formula=state.residual_formula,
        residual_free=state.residual_kn,
        tangent_free=state.jacobian_kn_per_m,
        internal_forces=state.internal_forces_kn,
        external_forces=state.external_forces_kn,
        material_state_next={
            "state_schema": "g1-material-state-next.seed.v1",
            "assembly_scope": "narrow_axial_chain_seed",
            "state_updated_material_newton": False,
            "path_dependent_state": False,
            "element_material_states": element_material_states,
        },
        metrics={
            "assembly_scope": "narrow_axial_chain_seed",
            "free_dof_indices": list(free_node_indices),
            "free_dof_count": len(free_node_indices),
            "residual_inf_norm": _inf_norm(state.residual_kn),
            "tangent_inf_norm": _inf_norm(state.jacobian_kn_per_m),
            "fixed_point_residual_used_as_physical": False,
            "map_residual_used_as_physical": False,
            "regularized_fixed_point_substitute": False,
            "solver_normalized_residual_used_as_physical": False,
            "g1_closure_claim": False,
        },
    )


def assembly_result_from_frame_shell_material_coupled_state(state: Any) -> AssemblyResult:
    """Adapt the coupled frame/shell/material seed into the shared G1 envelope."""

    return AssemblyResult(
        residual_formula=state.residual_formula,
        residual_free=state.residual_kn,
        tangent_free=state.jacobian_kn_per_m,
        internal_forces=state.internal_forces_kn,
        external_forces=state.external_forces_kn,
        material_state_next={
            "state_schema": "g1-material-state-next.seed.v1",
            "assembly_scope": "frame_shell_material_coupled_2dof_seed",
            "state_updated_material_newton": False,
            "path_dependent_state": False,
            "component_material_states": list(state.component_forces_kn),
        },
        metrics={
            "assembly_scope": "frame_shell_material_coupled_2dof_seed",
            "free_dof_labels": list(state.free_dof_labels),
            "free_dof_count": len(state.free_dof_labels),
            "residual_inf_norm": _inf_norm(state.residual_kn),
            "tangent_inf_norm": _inf_norm(state.jacobian_kn_per_m),
            "fixed_point_residual_used_as_physical": False,
            "map_residual_used_as_physical": False,
            "regularized_fixed_point_substitute": False,
            "solver_normalized_residual_used_as_physical": False,
            "g1_closure_claim": False,
        },
    )


def assembly_result_from_state_updated_material_newton_state(state: Any) -> AssemblyResult:
    """Adapt the path-dependent material seed into the shared G1 envelope."""

    material_update = dict(state.material_state_update)
    assembly_scope = str(
        material_update.get("assembly_scope")
        or "state_updated_bilinear_material_1dof_seed"
    )
    return AssemblyResult(
        residual_formula=state.residual_formula,
        residual_free=state.residual_kn,
        tangent_free=state.jacobian_kn_per_m,
        internal_forces=state.internal_forces_kn,
        external_forces=state.external_forces_kn,
        material_state_next={
            "state_schema": "g1-material-state-next.state-updated-seed.v1",
            "assembly_scope": assembly_scope,
            "state_updated_material_newton": True,
            "path_dependent_state": True,
            "path_dependent_state_updated": bool(
                material_update.get("path_dependent_state_updated")
            ),
            "material_model": material_update.get("material_model"),
            "material_family": material_update.get("material_family"),
            "section_integration": material_update.get("section_integration"),
            "strain_mode": material_update.get("strain_mode"),
            "structural_component": material_update.get("structural_component"),
            "material_case_kind": material_update.get("material_case_kind"),
            "return_mapping": material_update.get("return_mapping"),
            "committed_state_previous": material_update.get(
                "committed_state_previous"
            ),
            "committed_state_next": material_update.get("committed_state_next"),
            "trial_state": {
                "trial_displacement_m": material_update.get(
                    "trial_displacement_m"
                ),
                "trial_force_kn": material_update.get("trial_force_kn"),
                "yield_function_kn": material_update.get("yield_function_kn"),
                "yielded": material_update.get("yielded"),
            },
            "algorithmic_tangent_kn_per_m": material_update.get(
                "algorithmic_tangent_kn_per_m"
            ),
            "plastic_increment_m": material_update.get("plastic_increment_m"),
            "state_persistence_label": material_update.get(
                "state_persistence_label"
            ),
        },
        metrics={
            "assembly_scope": assembly_scope,
            "free_dof_labels": list(state.free_dof_labels),
            "free_dof_count": len(state.free_dof_labels),
            "residual_inf_norm": _inf_norm(state.residual_kn),
            "tangent_inf_norm": _inf_norm(state.jacobian_kn_per_m),
            "state_updated_material_newton": True,
            "path_dependent_state": True,
            "path_dependent_state_updated": bool(
                material_update.get("path_dependent_state_updated")
            ),
            "material_family": material_update.get("material_family"),
            "section_integration": material_update.get("section_integration"),
            "strain_mode": material_update.get("strain_mode"),
            "structural_component": material_update.get("structural_component"),
            "material_case_kind": material_update.get("material_case_kind"),
            "material_algorithmic_tangent_source": "return_mapping_consistent_tangent",
            "material_state_persistence_required": True,
            "fixed_point_residual_used_as_physical": False,
            "map_residual_used_as_physical": False,
            "regularized_fixed_point_substitute": False,
            "solver_normalized_residual_used_as_physical": False,
            "g1_closure_claim": False,
        },
    )


def assembly_result_from_state_updated_frame_shell_coupled_material_state(
    state: Any,
) -> AssemblyResult:
    """Adapt a coupled frame/shell state-updated material seed into G1."""

    component_material_states = dict(state.component_material_states)
    frame_material = dict(component_material_states.get("frame") or {})
    shell_material = dict(component_material_states.get("shell") or {})
    frame_updated = frame_material.get("path_dependent_state_updated") is True
    shell_updated = shell_material.get("path_dependent_state_updated") is True
    component_return_mappings = {
        "frame": frame_material.get("return_mapping"),
        "shell": shell_material.get("return_mapping"),
    }
    return AssemblyResult(
        residual_formula=state.residual_formula,
        residual_free=state.residual_kn,
        tangent_free=state.jacobian_kn_per_m,
        internal_forces=state.internal_forces_kn,
        external_forces=state.external_forces_kn,
        material_state_next={
            "state_schema": "g1-material-state-next.frame-shell-coupled-state-updated-seed.v1",
            "assembly_scope": "state_updated_frame_shell_coupled_material_seed",
            "state_updated_material_newton": True,
            "path_dependent_state": True,
            "path_dependent_state_updated": frame_updated or shell_updated,
            "frame_shell_state_updated_material_coupling": True,
            "frame_shell_coupling_stiffness_kn_per_m": (
                state.frame_shell_coupling_stiffness_kn_per_m
            ),
            "component_return_mappings": component_return_mappings,
            "component_material_states": component_material_states,
            "component_internal_forces_kn": dict(state.component_internal_forces_kn),
            "frame_material_state_updated": frame_updated,
            "shell_material_state_updated": shell_updated,
        },
        metrics={
            "assembly_scope": "state_updated_frame_shell_coupled_material_seed",
            "free_dof_labels": list(state.free_dof_labels),
            "free_dof_count": len(state.free_dof_labels),
            "residual_inf_norm": _inf_norm(state.residual_kn),
            "tangent_inf_norm": _inf_norm(state.jacobian_kn_per_m),
            "state_updated_material_newton": True,
            "path_dependent_state": True,
            "path_dependent_state_updated": frame_updated or shell_updated,
            "frame_shell_state_updated_material_coupling": True,
            "frame_material_state_updated": frame_updated,
            "shell_material_state_updated": shell_updated,
            "material_algorithmic_tangent_source": (
                "component_return_mapping_consistent_tangent_plus_coupling"
            ),
            "material_state_persistence_required": True,
            "fixed_point_residual_used_as_physical": False,
            "map_residual_used_as_physical": False,
            "regularized_fixed_point_substitute": False,
            "solver_normalized_residual_used_as_physical": False,
            "g1_closure_claim": False,
        },
    )


def assemble_g1_state(model: Any, state: Any | None = None) -> AssemblyResult:
    """Dispatch an existing assembly state into the G1 physical contract.

    ``model`` is accepted for the roadmap-style ``assemble_g1_state(model, state)``
    shape. The current narrow seeds only need the assembled ``state`` object; full
    model-aware G1 assembly remains a separate, non-closed roadmap item.
    """

    candidate = model if state is None else state
    if hasattr(candidate, "component_material_states") and hasattr(
        candidate,
        "frame_shell_coupling_stiffness_kn_per_m",
    ):
        return assembly_result_from_state_updated_frame_shell_coupled_material_state(
            candidate
        )
    if hasattr(candidate, "material_state_update") and hasattr(
        candidate,
        "material_algorithm_tangent_kn_per_m",
    ):
        return assembly_result_from_state_updated_material_newton_state(candidate)
    if hasattr(candidate, "free_node_indices") and hasattr(candidate, "element_forces_kn"):
        return assembly_result_from_axial_chain_state(candidate)
    if hasattr(candidate, "free_dof_labels") and hasattr(candidate, "component_forces_kn"):
        return assembly_result_from_frame_shell_material_coupled_state(candidate)
    raise TypeError(
        "assemble_g1_state supports AxialChainAssemblyState and "
        "FrameShellMaterialCoupledState and state-updated material seeds only."
    )


def finite_difference_g1_jvp_check(
    assemble_result: Callable[[np.ndarray], AssemblyResult],
    free_displacements: np.ndarray,
    *,
    direction: np.ndarray | None = None,
    epsilon: float = 1.0e-7,
    relative_tolerance: float = 1.0e-6,
    absolute_tolerance: float = 1.0e-8,
) -> dict[str, Any]:
    """Check ``Jv`` against central differences of the physical residual."""

    free_displacements = _as_1d_array("free_displacements", free_displacements)
    base = assemble_result(free_displacements)
    direction = (
        _default_direction(base.residual_free.size)
        if direction is None
        else _as_1d_array("direction", direction)
    )
    if direction.shape != base.residual_free.shape:
        raise ValueError("direction must have one entry per free residual DOF.")
    if _inf_norm(direction) <= 0.0:
        raise ValueError("direction must not be the zero vector.")
    if epsilon <= 0.0:
        raise ValueError("epsilon must be positive.")

    forward = assemble_result(free_displacements + epsilon * direction)
    backward = assemble_result(free_displacements - epsilon * direction)
    analytic_jvp = base.tangent_free @ direction
    finite_difference_jvp = (
        forward.residual_free - backward.residual_free
    ) / (2.0 * epsilon)
    max_abs_error = _inf_norm(analytic_jvp - finite_difference_jvp)
    scale = max(_inf_norm(analytic_jvp), _inf_norm(finite_difference_jvp), 1.0)
    relative_error = max_abs_error / scale
    passed = max_abs_error <= absolute_tolerance or relative_error <= relative_tolerance
    return {
        "schema_version": "g1-assembly-jvp-finite-difference-check.v1",
        "pass": passed,
        "residual_formula": base.residual_formula,
        "residual_source": base.residual_source,
        "tangent_definition": base.tangent_definition,
        "finite_difference_scheme": "central",
        "finite_difference_epsilon": epsilon,
        "direction": direction.tolist(),
        "analytic_jvp": analytic_jvp.tolist(),
        "finite_difference_jvp": finite_difference_jvp.tolist(),
        "max_abs_error": max_abs_error,
        "relative_error": relative_error,
        "relative_tolerance": relative_tolerance,
        "absolute_tolerance": absolute_tolerance,
    }


def direct_residual_newton_parity_check(
    assemble_result: Callable[[np.ndarray], AssemblyResult],
    solution: Any,
    *,
    residual_abs_tolerance: float = 1.0e-10,
    residual_relative_tolerance: float = 1.0e-10,
    relative_increment_tolerance: float | None = None,
) -> dict[str, Any]:
    """Replay Newton history through the physical assembly contract.

    This is a CPU-seed Phase 2 guard: it proves that the residual stored by the
    Newton solver for this seed is the same physical residual returned by
    ``assemble_g1_state``. It is intentionally not a full G1 closure signal.
    """

    history_rows: list[dict[str, Any]] = []
    direct_solver_residual_match = True
    for row in getattr(solution, "convergence_history", []):
        if "free_displacements_m" not in row or "residual_kn" not in row:
            direct_solver_residual_match = False
            history_rows.append(
                {
                    "iteration": row.get("iteration"),
                    "direct_solver_residual_match": False,
                    "detail": "missing_free_displacements_or_residual",
                }
            )
            continue
        free_displacements = _as_1d_array(
            "history.free_displacements_m",
            row["free_displacements_m"],
        )
        solver_residual = _as_1d_array("history.residual_kn", row["residual_kn"])
        assembly = assemble_result(free_displacements)
        delta = assembly.residual_free - solver_residual
        max_abs_delta = _inf_norm(delta)
        scale = max(_inf_norm(assembly.residual_free), _inf_norm(solver_residual), 1.0)
        relative_delta = max_abs_delta / scale
        row_match = (
            max_abs_delta <= residual_abs_tolerance
            or relative_delta <= residual_relative_tolerance
        )
        direct_solver_residual_match = direct_solver_residual_match and row_match
        history_rows.append(
            {
                "iteration": row.get("iteration"),
                "direct_solver_residual_match": row_match,
                "direct_residual_inf_norm": _inf_norm(assembly.residual_free),
                "solver_residual_inf_norm": _inf_norm(solver_residual),
                "max_abs_delta": max_abs_delta,
                "relative_delta": relative_delta,
                "line_search_alpha": row.get("line_search_alpha"),
                "accepted": row.get("accepted"),
            }
        )

    line_search_rows: list[dict[str, Any]] = []
    residual_descent_passed = True
    for row in getattr(solution, "line_search_history", []):
        selected_alpha = float(row.get("selected_alpha", 0.0))
        starting = _as_1d_array(
            "line_search.starting_free_displacements_m",
            row.get("starting_free_displacements_m", []),
        )
        increment = _as_1d_array(
            "line_search.newton_increment_m",
            row.get("newton_increment_m", []),
        )
        starting_residual = assemble_result(starting).residual_free
        trial = starting + selected_alpha * increment
        trial_residual = assemble_result(trial).residual_free
        starting_norm = _inf_norm(starting_residual)
        trial_norm = _inf_norm(trial_residual)
        descent_ratio = trial_norm / max(starting_norm, 1.0)
        descent_passed = selected_alpha > 0.0 and trial_norm < starting_norm
        residual_descent_passed = residual_descent_passed and descent_passed
        line_search_rows.append(
            {
                "iteration": row.get("iteration"),
                "selected_alpha": selected_alpha,
                "starting_residual_inf_norm": starting_norm,
                "trial_residual_inf_norm": trial_norm,
                "residual_reduction_ratio": descent_ratio,
                "direct_residual_descent_passed": descent_passed,
            }
        )

    final_displacements = _as_1d_array(
        "solution.free_displacements_m",
        getattr(solution, "free_displacements_m"),
    )
    final_assembly = assemble_result(final_displacements)
    solver_final_residual = _as_1d_array(
        "solution.metrics.residual_kn",
        solution.metrics.get("residual_kn", []),
    )
    final_delta = final_assembly.residual_free - solver_final_residual
    final_max_abs_delta = _inf_norm(final_delta)
    final_scale = max(
        _inf_norm(final_assembly.residual_free),
        _inf_norm(solver_final_residual),
        1.0,
    )
    final_relative_delta = final_max_abs_delta / final_scale
    final_residual_match = (
        final_max_abs_delta <= residual_abs_tolerance
        or final_relative_delta <= residual_relative_tolerance
    )
    direct_solver_residual_match = (
        direct_solver_residual_match and final_residual_match
    )

    final_increment_abs = float(solution.metrics.get("final_increment_abs_m", np.inf))
    displacement_scale = max(_inf_norm(final_displacements), 1.0)
    final_relative_increment = final_increment_abs / displacement_scale
    if relative_increment_tolerance is None:
        relative_increment_tolerance = float(
            getattr(solution, "config").increment_tolerance
        )
    relative_increment_gate_passed = (
        final_relative_increment <= relative_increment_tolerance
    )
    residual_gate_passed = solution.metrics.get("residual_gate_passed") is True
    no_solver_substitute = (
        solution.metrics.get("regularization_used") is False
        and solution.metrics.get("fallback_used") is False
    )
    cpu_seed_gate_passed = (
        direct_solver_residual_match
        and residual_descent_passed
        and residual_gate_passed
        and relative_increment_gate_passed
        and no_solver_substitute
        and final_assembly.metrics.get("regularized_fixed_point_substitute") is False
    )
    return {
        "schema_version": "g1-direct-residual-newton-parity-check.v1",
        "phase": "phase2_cpu_seed_consistent_residual_jacobian_newton",
        "cpu_seed_consistent_newton_gate_passed": cpu_seed_gate_passed,
        "consistent_residual_jacobian_newton_gate_passed": False,
        "promotes_g1_closure": False,
        "residual_formula": final_assembly.residual_formula,
        "residual_source": final_assembly.residual_source,
        "direct_solver_residual_match": direct_solver_residual_match,
        "residual_descent_passed": residual_descent_passed,
        "residual_gate_passed": residual_gate_passed,
        "relative_increment_gate_passed": relative_increment_gate_passed,
        "final_relative_increment": final_relative_increment,
        "relative_increment_tolerance": relative_increment_tolerance,
        "final_direct_residual_inf_norm": _inf_norm(final_assembly.residual_free),
        "final_solver_residual_inf_norm": _inf_norm(solver_final_residual),
        "final_residual_max_abs_delta": final_max_abs_delta,
        "final_residual_relative_delta": final_relative_delta,
        "regularization_used": solution.metrics.get("regularization_used"),
        "fallback_used": solution.metrics.get("fallback_used"),
        "regularized_fixed_point_substitute": False,
        "cpu_diagnostic_substitute_used_as_g1_closure": False,
        "history_replay": history_rows,
        "line_search_replay": line_search_rows,
    }


def _as_1d_array(name: str, value: Any) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.ndim != 1:
        raise ValueError(f"{name} must be a 1D array.")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values.")
    return array.copy()


def _as_2d_array(name: str, value: Any) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.ndim != 2:
        raise ValueError(f"{name} must be a 2D array.")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values.")
    return array.copy()


def _assert_not_prohibited_residual_substitute(
    residual_source: str,
    metrics: dict[str, Any],
) -> None:
    normalized = residual_source.lower().replace("-", "_").replace(" ", "_")
    if any(token in normalized for token in PROHIBITED_RESIDUAL_SUBSTITUTES):
        raise ValueError(
            "AssemblyResult physical residual cannot be a fixed-point, map, "
            "regularized, or solver-normalized substitute."
        )
    for key in PROHIBITED_SUBSTITUTE_METRIC_KEYS:
        if metrics.get(key) is True:
            raise ValueError(
                f"AssemblyResult physical residual substitute guard failed: {key}."
            )


def _assert_residual_matches_internal_external(
    residual_free: np.ndarray,
    internal_forces: np.ndarray,
    external_forces: np.ndarray,
    metrics: dict[str, Any],
) -> None:
    free_indices = metrics.get("free_dof_indices")
    if free_indices is not None:
        indices = np.asarray(free_indices, dtype=int)
        expected = internal_forces[indices] - external_forces[indices]
    elif internal_forces.shape == residual_free.shape:
        expected = internal_forces - external_forces
    else:
        return
    if not np.allclose(residual_free, expected, rtol=1.0e-10, atol=1.0e-10):
        raise ValueError(
            "AssemblyResult residual_free must equal F_internal - F_external on "
            "free DOFs."
        )


def _default_direction(size: int) -> np.ndarray:
    if size <= 0:
        raise ValueError("free residual size must be positive.")
    direction = np.ones(size, dtype=float)
    direction[1::2] = -0.5
    return direction


def _inf_norm(value: Any) -> float:
    array = np.asarray(value, dtype=float)
    if array.size == 0:
        return 0.0
    return float(np.linalg.norm(array, ord=np.inf))
