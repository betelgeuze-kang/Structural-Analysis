"""Experimental direct control using the existing small-displacement RC solver.

Only the equilibrium adapter is new: the existing vector Newton solver operates
on ``[q_free, scale * load_factor]``. Every material trial uses the same immutable
parent and the unchanged fixed-chord fiber assembler. This is not the public
monotonic-load J1--J5 profile or a corotational model.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import math
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_fiber_frame2d import (
    StatefulFiberFrame2DAssembly,
    StatefulFiberFrame2DProblem,
    assemble_stateful_fiber_frame2d,
    validate_stateful_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_fiber_frame2d_state import (
    StatefulFiberFrame2DCheckpoint,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.solvers.nonlinear.newton import (
    VECTOR_MATRIX_BACKEND,
    NewtonRaphsonConfig,
    NewtonRaphsonVectorSolution,
    newton_raphson_vector,
)


STATEFUL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_PROFILE = (
    "small-displacement-rc-fiber-direct-control.v1"
)
STATEFUL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_CLAIM_BOUNDARY = (
    "Experimental small-displacement RC fiber direct control with one free UX/UY "
    "coordinate, proportional reference loads and dense CPU Newton. It reuses "
    "the original material laws and fixed-chord assembler. Step equilibrium, "
    "control, parent binding and exact rollback are internal checks; this is not "
    "the public monotonic-load J1-J5 result, independent physical validation, "
    "geometric nonlinearity, design authority or release approval."
)


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        raise ValueError(f"{name} must be a finite number")
    try:
        normalized = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(normalized) or (positive and normalized <= 0.0):
        raise ValueError(f"{name} is outside its finite numeric domain")
    if isinstance(value, (int, np.integer)) and int(normalized) != value:
        raise ValueError(f"{name} loses integer identity in binary64")
    return normalized


@dataclass(frozen=True)
class StatefulFiberFrame2DDisplacementControlConfig:
    newton: NewtonRaphsonConfig = field(default_factory=NewtonRaphsonConfig)
    control_tolerance_m: float = 1.0e-12
    load_factor_coordinate_scale_m: float = 1.0e-3

    def __post_init__(self) -> None:
        if type(self.newton) is not NewtonRaphsonConfig:
            raise ValueError("newton must be an exact NewtonRaphsonConfig")
        if self.newton.matrix_backend != VECTOR_MATRIX_BACKEND:
            raise ValueError(
                "RC direct control supports only the existing dense backend"
            )
        if self.newton.max_iterations > 200:
            raise ValueError("RC direct control permits at most 200 Newton iterations")
        for name in ("control_tolerance_m", "load_factor_coordinate_scale_m"):
            object.__setattr__(
                self, name, _number(getattr(self, name), name, positive=True)
            )
        increment_bound = (
            self.newton.increment_tolerance / self.load_factor_coordinate_scale_m
        )
        if not math.isfinite(increment_bound) or increment_bound <= 0.0:
            raise ValueError(
                "scaled load-factor increment bound is outside its finite domain"
            )

    def to_manifest(self) -> dict[str, Any]:
        newton = asdict(self.newton)
        newton["line_search_alphas"] = list(self.newton.line_search_alphas)
        return {
            "profile": STATEFUL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_PROFILE,
            "newton": newton,
            "control_tolerance_m": self.control_tolerance_m,
            "load_factor_coordinate_scale_m": self.load_factor_coordinate_scale_m,
            "control_row_weight": "F_reference*residual_tolerance/control_tolerance_m",
            "augmented_coordinates": "[q_free_m,load_factor_coordinate_scale_m*lambda]",
        }

    @property
    def contract_hash(self) -> str:
        return canonical_hash(self.to_manifest())


@dataclass(frozen=True)
class StatefulFiberFrame2DDisplacementControlObservation:
    frame_assembly: StatefulFiberFrame2DAssembly
    augmented_residual_kn: np.ndarray
    augmented_jacobian_kn_per_m: np.ndarray
    control_error_m: float
    load_factor: float


@dataclass(frozen=True)
class StatefulFiberFrame2DDisplacementControlStepAdapter:
    problem: StatefulFiberFrame2DProblem
    accepted_checkpoint: StatefulFiberFrame2DCheckpoint
    control_global_dof: int
    target_control_displacement_m: float
    config: StatefulFiberFrame2DDisplacementControlConfig
    initial_augmented_coordinates_m: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        if type(self.problem) is not StatefulFiberFrame2DProblem:
            raise ValueError(
                "problem must be the original small-displacement fiber frame"
            )
        if type(self.accepted_checkpoint) is not StatefulFiberFrame2DCheckpoint:
            raise ValueError("accepted_checkpoint type is invalid")
        if type(self.config) is not StatefulFiberFrame2DDisplacementControlConfig:
            raise ValueError("config type is invalid")
        if self.problem.global_dof_count > 48 or len(self.problem.members) > 64:
            raise ValueError("RC direct control exceeds its bounded model size")
        if (
            type(self.control_global_dof) is not int
            or self.control_global_dof not in self.problem.free_global_dofs
            or self.control_global_dof % 3 not in (0, 1)
        ):
            raise ValueError(
                "control_global_dof must be a free translational UX/UY DOF"
            )
        adjacency: list[set[int]] = [set() for _ in self.problem.node_coordinates_m]
        for member in self.problem.members:
            adjacency[member.node_i].add(member.node_j)
            adjacency[member.node_j].add(member.node_i)
        visited = {0}
        pending = [0]
        while pending:
            node = pending.pop()
            for neighbor in adjacency[node] - visited:
                visited.add(neighbor)
                pending.append(neighbor)
        if len(visited) != len(adjacency):
            raise ValueError("RC direct control requires a connected member graph")
        free_load = self.problem.reference_external_load_vector()[
            list(self.problem.free_global_dofs)
        ]
        if not np.any(free_load):
            raise ValueError(
                "RC direct control requires nonzero free reference loading"
            )
        validate_stateful_fiber_frame2d_checkpoint(
            self.problem, self.accepted_checkpoint
        )
        target = _number(
            self.target_control_displacement_m, "target_control_displacement_m"
        )
        object.__setattr__(self, "target_control_displacement_m", target)
        if (
            target
            == self.accepted_checkpoint.global_displacements[self.control_global_dof]
        ):
            raise ValueError("target control displacement must differ from the parent")
        if not math.isfinite(self.control_row_weight) or self.control_row_weight <= 0.0:
            raise ValueError("control equation weight must be finite and positive")
        if self.initial_augmented_coordinates_m is not None:
            raw = self.initial_augmented_coordinates_m
            if not isinstance(raw, (tuple, list, np.ndarray)) or np.ndim(raw) != 1:
                raise ValueError("initial augmented coordinates require one vector")
            if len(raw) != len(self.problem.free_global_dofs) + 1:
                raise ValueError("initial augmented coordinate count is invalid")
            # Snapshot caller data; a proposal changes only the Newton start.
            object.__setattr__(
                self,
                "initial_augmented_coordinates_m",
                tuple(_number(value, "initial augmented coordinate") for value in raw),
            )

    @property
    def control_free_index(self) -> int:
        return self.problem.free_global_dofs.index(self.control_global_dof)

    @property
    def control_row_weight(self) -> float:
        return (
            self.reference_force_scale()
            * self.config.newton.residual_tolerance
            / self.config.control_tolerance_m
        )

    @property
    def case_id(self) -> str:
        return (
            f"{self.problem.case_id}@small-displacement-control="
            f"{self.control_global_dof}:{self.target_control_displacement_m:.17g}"
        )

    def reference_force_scale(self) -> float:
        return self.problem.reference_force_scale()

    def initial_free_displacements_m(self) -> np.ndarray:
        if self.initial_augmented_coordinates_m is not None:
            return np.array(self.initial_augmented_coordinates_m, dtype=np.float64)
        physical = np.asarray(
            self.accepted_checkpoint.global_displacements, dtype=np.float64
        )
        free = (physical / self.problem.physical_coordinate_scale)[
            list(self.problem.free_global_dofs)
        ]
        return np.concatenate(
            (
                free,
                [
                    self.config.load_factor_coordinate_scale_m
                    * self.accepted_checkpoint.load_factor
                ],
            )
        )

    def observe(
        self, augmented_coordinates_m: Any
    ) -> StatefulFiberFrame2DDisplacementControlObservation:
        raw = np.asarray(augmented_coordinates_m)
        if raw.dtype.kind not in "iuf":
            raise ValueError("augmented coordinates must be finite real numbers")
        coordinates = np.asarray(raw, dtype=np.float64)
        count = len(self.problem.free_global_dofs)
        if coordinates.shape != (count + 1,) or not np.all(np.isfinite(coordinates)):
            raise ValueError("augmented coordinates have invalid shape or values")
        load_factor = (
            float(coordinates[-1]) / self.config.load_factor_coordinate_scale_m
        )
        frame = assemble_stateful_fiber_frame2d(
            self.problem,
            self.accepted_checkpoint,
            target_load_factor=load_factor,
            trial_free_coordinates_m=coordinates[:-1],
        )
        control_error = float(
            frame.global_displacements[self.control_global_dof]
            - self.target_control_displacement_m
        )
        residual = np.concatenate(
            (frame.residual_kn, [self.control_row_weight * control_error])
        )
        jacobian = np.zeros((count + 1, count + 1), dtype=np.float64)
        jacobian[:-1, :-1] = frame.jacobian_kn_per_m
        free_dofs = list(self.problem.free_global_dofs)
        jacobian[:-1, -1] = (
            -self.problem.physical_coordinate_scale[free_dofs]
            * self.problem.reference_external_load_vector()[free_dofs]
            / self.config.load_factor_coordinate_scale_m
        )
        jacobian[-1, self.control_free_index] = self.control_row_weight
        if not np.all(np.isfinite(residual)) or not np.all(np.isfinite(jacobian)):
            raise ValueError("augmented equilibrium contains nonfinite values")
        return StatefulFiberFrame2DDisplacementControlObservation(
            frame, residual, jacobian, control_error, load_factor
        )

    def assemble(self, augmented_coordinates_m: Any) -> tuple[np.ndarray, np.ndarray]:
        observation = self.observe(augmented_coordinates_m)
        return (
            observation.augmented_residual_kn,
            observation.augmented_jacobian_kn_per_m,
        )


@dataclass(frozen=True)
class StatefulFiberFrame2DDisplacementControlStepResult:
    status: str
    committed: bool
    parent_checkpoint: StatefulFiberFrame2DCheckpoint
    accepted_checkpoint: StatefulFiberFrame2DCheckpoint
    trial_solution: NewtonRaphsonVectorSolution
    trial_assembly: StatefulFiberFrame2DAssembly
    metrics: dict[str, Any]

    def _payload(self) -> dict[str, Any]:
        return deepcopy(
            {
                "schema_version": "small-displacement-rc-fiber-control-step.v1",
                "status": self.status,
                "committed": self.committed,
                "parent_checkpoint": self.parent_checkpoint.to_dict(),
                "accepted_checkpoint": self.accepted_checkpoint.to_dict(),
                "trial_solution": {
                    "status": self.trial_solution.status,
                    "augmented_coordinates_m": self.trial_solution.free_displacements_m.tolist(),
                    "metrics": self.trial_solution.metrics,
                    "convergence_history": self.trial_solution.convergence_history,
                    "line_search_history": self.trial_solution.line_search_history,
                    "unsupported_features": self.trial_solution.unsupported_features,
                },
                "trial_assembly": self.trial_assembly.to_dict(),
                "metrics": dict(self.metrics),
                "claim_boundary": STATEFUL_FIBER_FRAME2D_DISPLACEMENT_CONTROL_CLAIM_BOUNDARY,
            }
        )

    @property
    def step_hash(self) -> str:
        return canonical_hash(self._payload())

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        return {**payload, "step_hash": canonical_hash(payload)}


def _same_vector(left: Any, right: Any) -> bool:
    try:
        left_values = np.asarray(left)
        right_values = np.asarray(right)
        if left_values.dtype.kind not in "iuf" or right_values.dtype.kind not in "iuf":
            return False
        first = np.ascontiguousarray(left_values, dtype="<f8")
        second = np.ascontiguousarray(right_values, dtype="<f8")
        return (
            first.shape == second.shape
            and bool(np.all(np.isfinite(first)))
            and bool(np.all(np.isfinite(second)))
            and first.tobytes() == second.tobytes()
        )
    except (TypeError, ValueError, OverflowError):
        return False


def solve_stateful_fiber_frame2d_displacement_control_step(
    problem: StatefulFiberFrame2DProblem,
    accepted_checkpoint: StatefulFiberFrame2DCheckpoint,
    *,
    control_global_dof: int,
    target_control_displacement_m: float,
    config: StatefulFiberFrame2DDisplacementControlConfig | None = None,
    initial_augmented_coordinates_m: tuple[float, ...] | None = None,
) -> StatefulFiberFrame2DDisplacementControlStepResult:
    """Use ordinary Newton on one augmented target; commit only all passed gates."""
    cfg = (
        config
        if config is not None
        else StatefulFiberFrame2DDisplacementControlConfig()
    )
    adapter = StatefulFiberFrame2DDisplacementControlStepAdapter(
        problem,
        accepted_checkpoint,
        control_global_dof,
        target_control_displacement_m,
        cfg,
        initial_augmented_coordinates_m,
    )
    parent_bytes = accepted_checkpoint.canonical_bytes()
    initial = adapter.initial_augmented_coordinates_m
    solution = newton_raphson_vector(adapter, config=cfg.newton)
    terminal = adapter.observe(solution.free_displacements_m)
    assembly = terminal.frame_assembly
    parent_immutable = (
        accepted_checkpoint.canonical_bytes() == parent_bytes
        and accepted_checkpoint.compute_state_hash() == accepted_checkpoint.state_hash
    )
    parent_binding = (
        assembly.parent_checkpoint_hash == accepted_checkpoint.state_hash
        and all(
            row.response.parent_state_hash == parent.state_hash
            for row, parent in zip(
                assembly.member_assemblies,
                accepted_checkpoint.element_states,
                strict=True,
            )
        )
    )
    relative_equilibrium = float(np.linalg.norm(assembly.residual_kn, ord=np.inf)) / (
        problem.reference_force_scale()
    )
    equilibrium_gate = relative_equilibrium <= cfg.newton.residual_tolerance
    control_gate = abs(terminal.control_error_m) <= cfg.control_tolerance_m
    solver_assembly_binding = (
        solution.problem is adapter
        and adapter.initial_augmented_coordinates_m == initial
        and solution.config is cfg.newton
        and _same_vector(
            solution.metrics.get("free_displacements_m"),
            solution.free_displacements_m,
        )
        and _same_vector(
            solution.metrics.get("residual_kn"), terminal.augmented_residual_kn
        )
        and _same_vector(
            assembly.generalized_coordinates_m[list(problem.free_global_dofs)],
            solution.free_displacements_m[:-1],
        )
    )
    # Recompute these from the actual final assembly, even if a solver result
    # incorrectly advertises readiness. No final coordinate snapping is used.
    committed = bool(
        solution.status == "ready"
        and solution.metrics.get("contract_pass") is True
        and solution.metrics.get("residual_gate_passed") is True
        and solution.metrics.get("increment_gate_passed") is True
        and solution.metrics.get("regularization_used") is False
        and solution.metrics.get("fallback_used") is False
        and parent_immutable
        and parent_binding
        and equilibrium_gate
        and control_gate
        and solver_assembly_binding
    )
    child = accepted_checkpoint
    if committed:
        child = StatefulFiberFrame2DCheckpoint(
            case_id=problem.case_id,
            problem_contract_hash=problem.contract_hash,
            epoch=accepted_checkpoint.epoch + 1,
            step_index=accepted_checkpoint.step_index + 1,
            load_factor=terminal.load_factor,
            parent_state_hash=accepted_checkpoint.state_hash,
            global_displacements=tuple(float(v) for v in assembly.global_displacements),
            element_states=assembly.trial_element_states,
        )
        validate_stateful_fiber_frame2d_checkpoint(problem, child)
    reason = solution.metrics.get("terminal_reason")
    if solution.status == "ready" and not committed:
        reason = "direct_control_terminal_binding_or_gate_failed"
    return StatefulFiberFrame2DDisplacementControlStepResult(
        status="ready" if committed else "blocked",
        committed=committed,
        parent_checkpoint=accepted_checkpoint,
        accepted_checkpoint=child,
        trial_solution=solution,
        trial_assembly=assembly,
        metrics={
            **(
                {
                    "initial_augmented_coordinates_m": list(initial),
                    "initial_augmented_coordinates_hash": canonical_hash(list(initial)),
                    "initialization_profile": "caller_proposal_only_original_parent_and_newton_gates",
                }
                if initial is not None
                else {}
            ),
            "config_hash": cfg.contract_hash,
            "config": cfg.to_manifest(),
            "control_global_dof": control_global_dof,
            "control_unit": "m",
            "target_control_displacement_m": adapter.target_control_displacement_m,
            "accepted_control_displacement_m": child.global_displacements[
                control_global_dof
            ],
            "solved_load_factor": terminal.load_factor,
            "control_error_m": terminal.control_error_m,
            "relative_equilibrium": relative_equilibrium,
            "control_gate_passed": bool(control_gate),
            "equilibrium_gate_passed": bool(equilibrium_gate),
            "solver_contract_pass": committed,
            "parent_checkpoint_immutable": bool(parent_immutable),
            "section_and_element_parent_binding_passed": bool(parent_binding),
            "solver_assembly_coordinate_residual_binding_passed": bool(
                solver_assembly_binding
            ),
            "rollback_exact": None
            if committed
            else (
                child is accepted_checkpoint and child.canonical_bytes() == parent_bytes
            ),
            "committed": committed,
            "terminal_reason": reason,
            "implied_load_factor_increment_tolerance": (
                cfg.newton.increment_tolerance / cfg.load_factor_coordinate_scale_m
            ),
        },
    )
