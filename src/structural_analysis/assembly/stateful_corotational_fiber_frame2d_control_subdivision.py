"""Bounded retry subdivision for internal corotational displacement histories."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from typing import Iterable

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DProblem,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
    StatefulCorotationalFiberFrame2DDisplacementControlStepResult,
    _controlled_free_index,
    _finite,
    _free_generalized_coordinates,
    _require_connected_member_graph,
    solve_stateful_corotational_fiber_frame2d_displacement_control_step,
)


@dataclass(frozen=True)
class CorotationalControlSubdivisionResult:
    status: str
    terminal_reason: str
    authored_targets: tuple[float, ...]
    completed_target_count: int
    initial_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    final_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    attempts: tuple[StatefulCorotationalFiberFrame2DDisplacementControlStepResult, ...]

    @property
    def contract_pass(self) -> bool:
        return self.status == "ready" and self.completed_target_count == len(
            self.authored_targets
        )


def run_corotational_control_subdivision(
    problem: StatefulCorotationalFiberFrame2DProblem,
    control_displacements_m: Iterable[float],
    *,
    control_global_dof: int,
    initial_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint | None = None,
    maximum_attempt_count: int = 255,
    maximum_subdivision_depth: int = 8,
    config: StatefulCorotationalFiberFrame2DDisplacementControlConfig | None = None,
) -> CorotationalControlSubdivisionResult:
    """Retry failed increments by bisection; every solver attempt spends budget.

    All successful intermediate states remain committed. This function provides
    no durable attempt-budget authority or automatic resume protocol.
    """
    if type(maximum_attempt_count) is not int or not 1 <= maximum_attempt_count <= 4096:
        raise ValueError("maximum_attempt_count must be an integer in [1, 4096]")
    if (
        type(maximum_subdivision_depth) is not int
        or not 0 <= maximum_subdivision_depth <= 20
    ):
        raise ValueError("maximum_subdivision_depth must be an integer in [0, 20]")
    targets = tuple(
        _finite(v, name="control displacement")
        for v in islice(control_displacements_m, 256)
    )
    if not 1 <= len(targets) <= 255:
        raise ValueError("control targets must contain 1 to 255 entries")
    _require_connected_member_graph(problem)
    index = _controlled_free_index(problem, control_global_dof)
    first = (
        initial_stateful_corotational_fiber_frame2d_checkpoint(problem)
        if initial_checkpoint is None
        else initial_checkpoint
    )
    validate_stateful_corotational_fiber_frame2d_checkpoint(problem, first)
    previous = float(_free_generalized_coordinates(problem, first)[index])
    for target in targets:
        if target == previous:
            raise ValueError("consecutive control targets must differ")
        previous = target
    cfg = (
        StatefulCorotationalFiberFrame2DDisplacementControlConfig()
        if config is None
        else config
    )
    if type(cfg) is not StatefulCorotationalFiberFrame2DDisplacementControlConfig:
        raise ValueError("config type is invalid")
    accepted = first
    attempts = []
    completed = 0
    reason = "all_authored_targets_reached"
    pending = [(value, 0, i) for i, value in reversed(tuple(enumerate(targets)))]
    while pending:
        if len(attempts) >= maximum_attempt_count:
            reason = "attempt_budget_exhausted"
            break
        target, depth, authored_index = pending.pop()
        parent_bytes = accepted.canonical_bytes()
        start = float(_free_generalized_coordinates(problem, accepted)[index])
        step = solve_stateful_corotational_fiber_frame2d_displacement_control_step(
            problem,
            accepted,
            control_global_dof=control_global_dof,
            target_control_displacement_m=target,
            config=cfg,
        )
        attempts.append(step)
        if accepted.canonical_bytes() != parent_bytes:
            raise ValueError("solver changed the accepted parent")
        if step.committed:
            accepted = step.accepted_checkpoint
            if target == targets[authored_index]:
                completed += 1
            continue
        if step.accepted_checkpoint.canonical_bytes() != parent_bytes:
            raise ValueError("failed solver attempt did not preserve accepted state")
        if depth >= maximum_subdivision_depth:
            reason = "subdivision_depth_exhausted"
            break
        midpoint = start / 2.0 + target / 2.0
        if midpoint == start or midpoint == target:
            reason = "subdivision_has_no_representable_progress"
            break
        pending.extend(
            ((target, depth + 1, authored_index), (midpoint, depth + 1, authored_index))
        )
    ready = not pending and completed == len(targets)
    return CorotationalControlSubdivisionResult(
        "ready" if ready else "blocked",
        reason,
        targets,
        completed,
        first,
        accepted,
        tuple(attempts),
    )
